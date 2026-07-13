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

SUPPORTED_BRANDS = ["Hansgrohe", "Axor", "Grohe", "Vitra", "Geberit"]
MISSING = "[MISSING DATA]"

# Security audit (Phase 1, 2026-08): supplier pricelists (PDF/XLSX) legitimately
# run tens of MB with embedded imagery — cap generously but not unbounded.
MAX_IMPORT_BYTES = 80 * 1024 * 1024


def _guard_public_url(url: str) -> None:
    """Block SSRF via /from-url: staff-only, but a fetched URL must never be
    allowed to reach loopback/private/link-local network ranges (internal
    services, cloud metadata endpoints like 169.254.169.254, etc.). Only
    plain http(s) to a resolvable public hostname is allowed."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Only public http(s) URLs are supported")
    host = parsed.hostname.lower()
    if host in ("localhost", "0.0.0.0") or host.endswith(".local"):
        raise HTTPException(status_code=400, detail="URL host is not allowed")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise HTTPException(status_code=400, detail=f"Could not resolve host: {e}") from e
    for info in infos:
        addr = info[4][0]
        ip = ipaddress.ip_address(addr)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(status_code=400, detail="URL resolves to a non-public network address")


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
async def list_jobs(_: UserPublic = Depends(get_current_user)):
    docs = await db.catalog_imports.find({}, {"_id": 0, "rows": 0}).sort("created_at", -1).to_list(200)
    return docs


@router.get("/{job_id}")
async def get_job(job_id: str, _: UserPublic = Depends(get_current_user)):
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
    _guard_public_url(url)

    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            data = r.content
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


@router.patch("/{job_id}/rows/{row_id}")
async def update_row(
    job_id: str, row_id: str, patch: dict,
    _: UserPublic = Depends(require_min_role("purchase")),
):
    doc = await db.catalog_imports.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Import job not found")
    rows = doc.get("rows", [])
    for r in rows:
        if r.get("row_id") == row_id:
            for k, v in patch.items():
                if k in ("name", "sku", "category", "finish", "material", "dimensions",
                         "warranty", "mrp", "dealer_price", "status", "issues"):
                    r[k] = v
            break
    else:
        raise HTTPException(status_code=404, detail="Row not found")
    await db.catalog_imports.update_one({"id": job_id}, {"$set": {"rows": rows}})
    return {"ok": True}


@router.post("/{job_id}/approve")
async def approve_and_import(
    job_id: str,
    user: UserPublic = Depends(require_min_role("purchase")),
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
    n = await rollback_job(job_id)
    catalog_service.schedule_catalog_refresh()
    return {"products_deactivated": n}


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
