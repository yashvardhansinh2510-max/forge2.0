"""AI-assisted supplier catalog import (Hansgrohe, Axor, Grohe, Vitra, Geberit).

Pipeline (via `catalog_pipeline/`):
  Upload → Adapter Extract → Validate → Certify → Human Review → Import
"""
from __future__ import annotations
import logging

import httpx
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile

from auth import get_current_user, require_min_role
from catalog_pipeline.orchestrator import import_accepted, rollback_job, run_pipeline
from db import db
from models import CatalogImportJob, UserPublic

from services import catalog_service

router = APIRouter(prefix="/catalog/imports", tags=["catalog-import"])
logger = logging.getLogger("forge.catalog_import")

SUPPORTED_BRANDS = ["Hansgrohe", "Axor", "Grohe", "Vitra", "Geberit", "Oyster"]
MISSING = "[MISSING DATA]"

# Security audit (Phase 1, 2026-08): supplier pricelists (PDF/XLSX) legitimately
# run tens of MB with embedded imagery — cap generously but not unbounded.
MAX_IMPORT_BYTES = 80 * 1024 * 1024


def _validate_public_host(url: str) -> None:
    """Block SSRF: a fetched URL must never be allowed to reach
    loopback/private/link-local network ranges (internal services, cloud
    metadata endpoints like 169.254.169.254, etc.). Only plain http(s) to a
    resolvable public hostname is allowed.

    Security note: this MUST be called on every redirect hop, not just the
    original URL — httpx's `follow_redirects=True` does not re-validate
    hostnames, so a DNS-rebinding or malicious-redirect attacker could pass
    the initial check with a public host and then 302 to a private address.
    See `_fetch_public_url`, which is the only caller that should ever
    actually fetch a URL from this module."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Only public http(s) URLs are supported")
    host = parsed.hostname.lower()
    if host in ("localhost", "0.0.0.0") or host.endswith(".local"):
        raise HTTPException(status_code=400, detail="URL host is not allowed")
    # Supplier pricelists are fetched over standard web ports only — this
    # closes off "public IP, unusual/internal-service port" SSRF variants
    # (e.g. a public host that also exposes an internal admin port on a
    # non-standard port) without needing a large port denylist.
    if parsed.port is not None and parsed.port not in (80, 443):
        raise HTTPException(status_code=400, detail="Only ports 80/443 are allowed")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise HTTPException(status_code=400, detail=f"Could not resolve host: {e}") from e
    for info in infos:
        addr = info[4][0]
        ip = ipaddress.ip_address(addr)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(status_code=400, detail="URL resolves to a non-public network address")


async def _fetch_public_url(url: str, *, max_redirects: int = 5) -> bytes:
    """Fetch a URL with the SSRF guard re-applied on every redirect hop.

    `httpx.AsyncClient(follow_redirects=True)` performs its own DNS
    resolution per-hop with no hook to intercept it, so a URL that passes
    the guard on its original hostname could still redirect to a private
    address and httpx would follow it unchecked. Following redirects
    manually here lets us validate the target of every hop before the
    client ever connects to it."""
    async with httpx.AsyncClient(timeout=180.0, follow_redirects=False) as client:
        current = url
        for hop in range(max_redirects + 1):
            try:
                _validate_public_host(current)
            except HTTPException:
                if hop > 0:
                    logger.warning("SSRF guard blocked redirect to non-public address: %s", current)
                raise
            r = await client.get(current)
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                current = str(httpx.URL(current).join(r.headers["location"]))
                continue
            r.raise_for_status()
            return r.content
    raise HTTPException(status_code=502, detail="Too many redirects while fetching URL")


async def _persist_job(brand: str, filename: str, source_type: str, result: dict, user_id: str) -> dict:
    job = CatalogImportJob(
        filename=filename,
        source_type=source_type,  # type: ignore[arg-type]
        supplier_name=brand,
        total_rows=len(result["rows"]),
        accepted_rows=sum(1 for r in result["rows"] if r.get("status") == "accepted"),
        rejected_rows=sum(1 for r in result["rows"] if r.get("status") == "rejected"),
        status="classified",  # type: ignore[arg-type]
        rows=result["rows"],
        created_by=user_id,
    )
    doc = job.dict()
    doc["extraction"] = result["extraction"]
    doc["certification"] = result["certification"]
    await db.catalog_imports.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_jobs(_: UserPublic = Depends(require_min_role("purchase"))):
    docs = await db.catalog_imports.find({}, {"_id": 0, "rows": 0}).sort("created_at", -1).to_list(200)
    return docs


@router.get("/{job_id}")
async def get_job(job_id: str, _: UserPublic = Depends(require_min_role("purchase"))):
    # Unapproved rows carry unverified MRP/dealer pricing — same access tier
    # as every mutating endpoint on this resource, not every authenticated user.
    doc = await db.catalog_imports.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Import job not found")
    return doc


@router.post("")
async def upload_and_extract(
    file: UploadFile = File(...),
    brand: str = Form(...),
    user: UserPublic = Depends(require_min_role("purchase")),
):
    if brand not in SUPPORTED_BRANDS:
        raise HTTPException(status_code=400, detail=f"Unsupported brand. Choose from: {SUPPORTED_BRANDS}")
    data = await file.read()
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_IMPORT_BYTES // (1024 * 1024)}MB limit")
    filename = file.filename or "upload"
    lower = filename.lower()
    if not lower.endswith((".xlsx", ".xls", ".pdf", ".csv")):
        raise HTTPException(status_code=400, detail="Only .xlsx, .xls, .pdf, .csv are supported")
    source_type = "excel" if lower.endswith((".xlsx", ".xls")) else ("pdf" if lower.endswith(".pdf") else "csv")

    result = await run_pipeline(brand, filename, data)
    if not result["rows"]:
        raise HTTPException(status_code=422, detail="Extraction produced 0 rows. Check the file format.")
    return await _persist_job(brand, filename, source_type, result, user.id)


@router.post("/from-url")
async def import_from_url(
    payload: dict = Body(...),
    user: UserPublic = Depends(require_min_role("purchase")),
):
    """Fetch a public supplier URL, run the pipeline. Perfect for large PDFs the
    frontend can't upload easily. Body: { brand, url, filename? }."""
    brand = payload.get("brand")
    url = payload.get("url")
    filename = payload.get("filename") or (url.rsplit("/", 1)[-1] if url else "download")
    if brand not in SUPPORTED_BRANDS:
        raise HTTPException(status_code=400, detail=f"Unsupported brand. Choose from: {SUPPORTED_BRANDS}")
    if not url or not isinstance(url, str) or not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Provide a valid public https URL")

    try:
        data = await _fetch_public_url(url)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch file: {e}") from e

    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail=f"Fetched file exceeds {MAX_IMPORT_BYTES // (1024 * 1024)}MB limit")

    lower = filename.lower()
    source_type = "excel" if lower.endswith((".xlsx", ".xls")) else ("pdf" if lower.endswith(".pdf") else "csv")

    result = await run_pipeline(brand, filename, data)
    if not result["rows"]:
        raise HTTPException(status_code=422, detail="Extraction produced 0 rows.")
    return await _persist_job(brand, filename, source_type, result, user.id)


_ROW_STRING_FIELDS = ("name", "sku", "category", "finish", "material", "dimensions", "warranty", "status")


def _coerce_row_patch_value(key: str, value):
    """Reject values that would later crash `import_accepted`'s untyped
    `float(r["mrp"])` — a reviewer typing "TBD" into the price field must
    get a 400 now, not silently corrupt the whole import batch later."""
    if key in ("mrp", "dealer_price"):
        if value in (None, MISSING, ""):
            return MISSING
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{key} must be a number, got {value!r}")
        if num < 0:
            raise HTTPException(status_code=400, detail=f"{key} cannot be negative")
        return num
    if key == "issues":
        if not isinstance(value, list):
            raise HTTPException(status_code=400, detail="issues must be a list")
        return value
    if key in _ROW_STRING_FIELDS:
        return None if value is None else str(value)
    raise HTTPException(status_code=400, detail=f"Field {key!r} is not editable")


@router.patch("/{job_id}/rows/{row_id}")
async def update_row(
    job_id: str, row_id: str, patch: dict,
    _: UserPublic = Depends(require_min_role("purchase")),
):
    doc = await db.catalog_imports.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Import job not found")
    rows = doc.get("rows", [])
    validated = {k: _coerce_row_patch_value(k, v) for k, v in patch.items()}
    for r in rows:
        if r.get("row_id") == row_id:
            r.update(validated)
            break
    else:
        raise HTTPException(status_code=404, detail="Row not found")
    await db.catalog_imports.update_one({"id": job_id}, {"$set": {"rows": rows}})
    return {"ok": True}


@router.post("/{job_id}/approve")
async def approve_and_import(
    job_id: str,
    # Maker-checker: the same "purchase" role that uploads/edits a pricelist
    # must not also be the one who approves it into the live catalog —
    # auth.py's documented capability matrix already lists catalog-import
    # approval as a manager action; this endpoint now matches it.
    user: UserPublic = Depends(require_min_role("manager")),
):
    doc = await db.catalog_imports.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Import job not found")

    cert = doc.get("certification") or {}
    if cert and cert.get("duplicates_sku", 0) > 0:
        # Not fatal but flagged in response
        pass

    stats = await import_accepted(doc, user.id)
    catalog_service.schedule_catalog_refresh()
    await db.catalog_imports.update_one(
        {"id": job_id},
        {"$set": {
            "status": "imported",
            "accepted_rows": stats["imported"] + stats["updated"],
            "rejected_rows": stats["skipped"],
        }},
    )
    return stats


@router.post("/{job_id}/rollback")
async def rollback(
    job_id: str,
    _: UserPublic = Depends(require_min_role("manager")),
):
    stats = await rollback_job(job_id)
    catalog_service.schedule_catalog_refresh()
    return stats


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    _: UserPublic = Depends(require_min_role("purchase")),
):
    res = await db.catalog_imports.delete_one({"id": job_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Import job not found")
    return {"ok": True}


@router.get("/config/brands")
async def supported_brands(_: UserPublic = Depends(get_current_user)):
    return {"brands": SUPPORTED_BRANDS}
