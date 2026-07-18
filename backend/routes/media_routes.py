"""Product Media endpoints (Iteration 2A).

All binaries go through the MediaStorage abstraction — this module never
imports the supabase driver directly.
"""
from __future__ import annotations
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from auth import get_current_user, require_min_role
from db import db
from models import ProductMedia, UserPublic
from services import catalog_service, media_service

logger = logging.getLogger("forge.media_routes")
router = APIRouter(tags=["media"])

# Security audit (Phase 1, 2026-08): uploads were previously unbounded —
# `await file.read()` loads the entire body into process memory with no size
# or MIME-type check, i.e. any "purchase" role could exhaust memory with a
# single oversized request. 20MB comfortably covers real product photography
# (largest legitimate assets seen in the catalog are a few MB) while blocking
# abuse. MIME allowlist matches what `_ext_for_mime`/PIL actually understand.
MAX_MEDIA_BYTES = 20 * 1024 * 1024
ALLOWED_MEDIA_MIMES = {
    "image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif",
    "application/pdf",
}


# BACKEND_AUDIT_2026-07-17.md Medium #32: the MIME allowlist above only ever
# checked the client-supplied `Content-Type` header — trivially spoofable
# (rename a .html/.svg to end up served with an attacker-chosen extension,
# or simply lie about the header). Magic-byte signatures verify what the
# file actually IS, independent of anything the client claims.
_MAGIC_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/jpg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "application/pdf": (b"%PDF-",),
    # WEBP has no fixed-offset-0 signature alone — RIFF....WEBP, checked separately below.
}


def _sniffed_mime_matches(data: bytes, mime: str) -> bool:
    if mime == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    sigs = _MAGIC_SIGNATURES.get(mime)
    if not sigs:
        return False
    return any(data.startswith(sig) for sig in sigs)


def _validate_media_upload(data: bytes, mime: str) -> None:
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_MEDIA_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_MEDIA_BYTES // (1024 * 1024)}MB limit")
    if mime not in ALLOWED_MEDIA_MIMES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {mime}")
    if not _sniffed_mime_matches(data, mime):
        raise HTTPException(
            status_code=400,
            detail=f"File content does not match declared type {mime} — upload rejected.",
        )


async def _read_bounded_upload(file: UploadFile) -> bytes:
    """Read only up to the configured limit, preventing unbounded body reads."""
    data = await file.read(MAX_MEDIA_BYTES + 1)
    _validate_media_upload(data, file.content_type or "application/octet-stream")
    return data


async def _brand_slug_for_product(product_id: str) -> tuple[str, Optional[str], Optional[str]]:
    """Return (brand_slug, brand_id, family_key) for a product."""
    prod = await db.products.find_one({"id": product_id}, {"_id": 0, "brand_id": 1, "family_key": 1})
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    brand = await db.brands.find_one({"id": prod.get("brand_id")}, {"_id": 0, "slug": 1, "name": 1})
    slug = (brand or {}).get("slug") or (brand or {}).get("name") or "unknown"
    return slug, prod.get("brand_id"), prod.get("family_key")


@router.get("/products/{product_id}/media", response_model=list[ProductMedia])
async def list_product_media(product_id: str, _: UserPublic = Depends(get_current_user)):
    media = await catalog_service.media_for_product(product_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return media


@router.post("/products/{product_id}/media", response_model=ProductMedia)
async def upload_product_media(
    product_id: str,
    file: UploadFile = File(...),
    source_type: str = Form("manufacturer"),
    role: str = Form("gallery"),
    is_primary: bool = Form(False),
    sort_order: int = Form(100),
    notes: Optional[str] = Form(None),
    user: UserPublic = Depends(require_min_role("purchase")),
):
    if source_type not in ("supplier", "manufacturer", "internal"):
        raise HTTPException(status_code=400, detail="source_type must be supplier|manufacturer|internal")
    slug, brand_id, family_key = await _brand_slug_for_product(product_id)
    data = await _read_bounded_upload(file)
    mime = file.content_type or "application/octet-stream"
    doc = await media_service.upload_and_register(
        data=data, mime=mime, brand_slug=slug,
        product_id=product_id, family_key=family_key, brand_id=brand_id,
        source_type=source_type, role=role,  # type: ignore[arg-type]
        is_primary=is_primary, sort_order=sort_order,
        uploaded_by=user.id, notes=notes, actor=user,
    )
    catalog_service.schedule_catalog_refresh()
    return doc


@router.post("/products/{product_id}/media/{media_id}/replace", response_model=ProductMedia)
async def replace_product_media(
    product_id: str,
    media_id: str,
    file: UploadFile = File(...),
    notes: Optional[str] = Form(None),
    user: UserPublic = Depends(require_min_role("purchase")),
):
    """Swap the file behind an existing image slot — keeps its role, primary
    status and sort position instead of appending a new one at the end. The
    old storage object is deleted as part of this call (no orphan left
    behind); both the upload and the deletion are separately audit-logged."""
    slug, _, _ = await _brand_slug_for_product(product_id)
    data = await _read_bounded_upload(file)
    mime = file.content_type or "application/octet-stream"
    doc = await media_service.replace_media(
        media_id, data=data, mime=mime, brand_slug=slug,
        uploaded_by=user.id, notes=notes, actor=user,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Media not found")
    catalog_service.schedule_catalog_refresh()
    return doc


@router.post("/families/{family_key}/media", response_model=ProductMedia)
async def upload_family_media(
    family_key: str,
    file: UploadFile = File(...),
    source_type: str = Form("manufacturer"),
    role: str = Form("gallery"),
    is_primary: bool = Form(False),
    sort_order: int = Form(100),
    notes: Optional[str] = Form(None),
    user: UserPublic = Depends(require_min_role("purchase")),
):
    if source_type not in ("supplier", "manufacturer", "internal"):
        raise HTTPException(status_code=400, detail="source_type must be supplier|manufacturer|internal")
    # Look up any product in this family to pick a brand slug
    sample = await db.products.find_one({"family_key": family_key}, {"_id": 0, "brand_id": 1})
    if not sample:
        raise HTTPException(status_code=404, detail="Family not found")
    brand = await db.brands.find_one({"id": sample["brand_id"]}, {"_id": 0, "slug": 1, "name": 1})
    slug = (brand or {}).get("slug") or (brand or {}).get("name") or "unknown"
    data = await _read_bounded_upload(file)
    mime = file.content_type or "application/octet-stream"
    doc = await media_service.upload_and_register(
        data=data, mime=mime, brand_slug=slug,
        family_key=family_key, brand_id=sample["brand_id"],
        source_type=source_type, role=role,  # type: ignore[arg-type]
        is_primary=is_primary, sort_order=sort_order,
        uploaded_by=user.id, notes=notes,
    )
    catalog_service.schedule_catalog_refresh()
    return doc


@router.delete("/media/{media_id}")
async def delete_media(media_id: str, user: UserPublic = Depends(require_min_role("purchase"))):
    ok = await media_service.delete_media(media_id, actor=user)
    if not ok:
        raise HTTPException(status_code=404, detail="Media not found")
    catalog_service.schedule_catalog_refresh()
    return {"ok": True}


@router.patch("/media/{media_id}")
async def patch_media(
    media_id: str,
    payload: dict,
    _: UserPublic = Depends(require_min_role("purchase")),
):
    allowed = {"is_primary", "role", "sort_order", "notes", "source_type"}
    updates = {k: v for k, v in (payload or {}).items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No supported fields to update")
    doc = await db.product_media.find_one({"id": media_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Media not found")
    await db.product_media.update_one({"id": media_id}, {"$set": updates})
    if updates.get("is_primary"):
        await media_service._demote_other_primaries(  # type: ignore[attr-defined]
            product_id=doc.get("product_id"),
            family_key=doc.get("family_key"),
            keep_id=media_id,
        )
    catalog_service.schedule_catalog_refresh()
    return {"ok": True}
