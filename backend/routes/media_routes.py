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
from services import media_service

logger = logging.getLogger("forge.media_routes")
router = APIRouter(tags=["media"])


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
    prod = await db.products.find_one({"id": product_id}, {"_id": 0, "family_key": 1})
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    return await media_service.list_media_for_product(product_id, prod.get("family_key"))


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
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    mime = file.content_type or "application/octet-stream"
    doc = await media_service.upload_and_register(
        data=data, mime=mime, brand_slug=slug,
        product_id=product_id, family_key=family_key, brand_id=brand_id,
        source_type=source_type, role=role,  # type: ignore[arg-type]
        is_primary=is_primary, sort_order=sort_order,
        uploaded_by=user.id, notes=notes,
    )
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
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    mime = file.content_type or "application/octet-stream"
    doc = await media_service.upload_and_register(
        data=data, mime=mime, brand_slug=slug,
        family_key=family_key, brand_id=sample["brand_id"],
        source_type=source_type, role=role,  # type: ignore[arg-type]
        is_primary=is_primary, sort_order=sort_order,
        uploaded_by=user.id, notes=notes,
    )
    return doc


@router.delete("/media/{media_id}")
async def delete_media(media_id: str, _: UserPublic = Depends(require_min_role("purchase"))):
    ok = await media_service.delete_media(media_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Media not found")
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
    return {"ok": True}
