"""Media service. Business logic layer between routes and the storage driver.

Routes never touch storage directly; they call `media_service.*` functions
which handle metadata persistence, dedupe (via SHA-1), and public/signed URL
generation in one place.
"""
from __future__ import annotations
import hashlib
import io
import logging
import re
from typing import Optional

from PIL import Image

from db import db
from media_storage import get_media_storage, StorageError
from media_storage.factory import public_bucket, private_bucket
from models import ProductMedia, MediaSourceType, MediaRole, MediaQuality

logger = logging.getLogger("forge.media_service")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(s: str) -> str:
    s = _SLUG_RE.sub("-", (s or "").lower()).strip("-")
    return s or "item"


def _detect_dims_and_quality(data: bytes, mime: str) -> tuple[Optional[int], Optional[int], MediaQuality]:
    """Return (width, height, quality). Never fabricates values."""
    if not data:
        return None, None, "missing"
    if not mime.startswith("image/") or mime == "image/svg+xml":
        # SVG is scale-free; treat as excellent unless caller says otherwise.
        return None, None, "excellent" if mime == "image/svg+xml" else "acceptable"
    try:
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        m = min(w, h)
        if m >= 1024:
            q: MediaQuality = "excellent"
        elif m >= 640:
            q = "good"
        elif m >= 320:
            q = "acceptable"
        else:
            q = "poor"
        return w, h, q
    except Exception as e:  # noqa: BLE001
        logger.warning("image inspect failed: %s", e)
        return None, None, "acceptable"


def _ext_for_mime(mime: str) -> str:
    return {
        "image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
        "image/webp": "webp", "image/svg+xml": "svg", "image/gif": "gif",
        "application/pdf": "pdf",
    }.get(mime, "bin")


def make_storage_key(
    *,
    brand_slug: str,
    family_key: Optional[str],
    product_id: Optional[str],
    source_type: MediaSourceType,
    role: MediaRole,
    sha1: str,
    mime: str,
) -> str:
    """Deterministic, SHA-content-addressed key so dedupe is trivial.

    Layout:
        <brand>/<family_or_product>/<source>/<role>-<sha1[:12]>.<ext>
    """
    scope = _slug(family_key) if family_key else _slug(product_id or "orphan")
    ext = _ext_for_mime(mime)
    return f"{_slug(brand_slug)}/{scope}/{source_type}/{role}-{sha1[:12]}.{ext}"


async def upload_and_register(
    *,
    data: bytes,
    mime: str,
    brand_slug: str,
    product_id: Optional[str] = None,
    family_key: Optional[str] = None,
    brand_id: Optional[str] = None,
    source_type: MediaSourceType = "manufacturer",
    role: MediaRole = "gallery",
    is_primary: bool = False,
    sort_order: int = 100,
    uploaded_by: Optional[str] = None,
    notes: Optional[str] = None,
    private: bool = False,
) -> ProductMedia:
    """Upload bytes to storage and persist metadata.

    Idempotent: if an identical SHA-1 already exists for the same target and
    source_type, we return the existing document instead of re-uploading.
    """
    sha1 = hashlib.sha1(data).hexdigest()

    # Dedupe check
    scope_filter: dict = {"sha1": sha1, "source_type": source_type}
    if product_id:
        scope_filter["product_id"] = product_id
    elif family_key:
        scope_filter["family_key"] = family_key
    existing = await db.product_media.find_one(scope_filter, {"_id": 0})
    if existing:
        return ProductMedia(**existing)

    width, height, quality = _detect_dims_and_quality(data, mime)
    bucket = private_bucket() if private else public_bucket()
    key = make_storage_key(
        brand_slug=brand_slug, family_key=family_key, product_id=product_id,
        source_type=source_type, role=role, sha1=sha1, mime=mime,
    )

    storage = get_media_storage()
    obj = await storage.upload(bucket=bucket, key=key, data=data, content_type=mime)

    doc = ProductMedia(
        product_id=product_id, family_key=family_key, brand_id=brand_id,
        source_type=source_type, role=role, bucket=bucket, storage_key=key,
        public_url=obj.public_url, width=width, height=height, quality=quality,
        sha1=sha1, mime=mime, size_bytes=len(data), is_primary=is_primary,
        sort_order=sort_order, uploaded_by=uploaded_by, notes=notes,
    )
    await db.product_media.insert_one(doc.dict())

    # If this is the new primary, demote others
    if is_primary:
        await _demote_other_primaries(product_id=product_id, family_key=family_key, keep_id=doc.id)

    return doc


async def _demote_other_primaries(
    *, product_id: Optional[str], family_key: Optional[str], keep_id: str,
) -> None:
    filt: dict = {"id": {"$ne": keep_id}, "is_primary": True}
    if product_id:
        filt["product_id"] = product_id
    elif family_key:
        filt["family_key"] = family_key
    else:
        return
    await db.product_media.update_many(filt, {"$set": {"is_primary": False}})


async def delete_media(media_id: str) -> bool:
    doc = await db.product_media.find_one({"id": media_id}, {"_id": 0})
    if not doc:
        return False
    storage = get_media_storage()
    try:
        await storage.delete(bucket=doc["bucket"], key=doc["storage_key"])
    except StorageError as e:
        logger.warning("storage delete failed (continuing to remove metadata): %s", e)
    await db.product_media.delete_one({"id": media_id})
    return True


async def list_media_for_product(product_id: str, family_key: Optional[str] = None) -> list[ProductMedia]:
    """Return all media attached to this product OR its family, ordered by
    (source priority: internal > manufacturer > supplier), is_primary desc,
    sort_order asc."""
    or_clauses: list[dict] = [{"product_id": product_id}]
    if family_key:
        or_clauses.append({"family_key": family_key})
    docs = await db.product_media.find({"$or": or_clauses}, {"_id": 0}).to_list(500)
    prio = {"internal": 0, "manufacturer": 1, "supplier": 2}
    docs.sort(key=lambda d: (
        prio.get(d.get("source_type", "supplier"), 3),
        0 if d.get("is_primary") else 1,
        int(d.get("sort_order", 100)),
    ))
    return [ProductMedia(**d) for d in docs]


async def hydrate_product_media(product: dict) -> dict:
    """Attach media_summary + hero_image_url + gallery to a product dict
    from the `product_media` collection (falling back to legacy `images` if
    the new collection is empty for this product)."""
    if not product:
        return product
    media = await list_media_for_product(product["id"], product.get("family_key"))
    summary = {"supplier": 0, "manufacturer": 0, "internal": 0}
    for m in media:
        summary[m.source_type] += 1
    quality_order = ["excellent", "good", "acceptable", "poor", "missing"]
    best_q = "missing"
    for q in quality_order:
        if any(m.quality == q for m in media):
            best_q = q
            break

    hero_url: Optional[str] = None
    gallery: list[dict] = []
    for m in media:
        if not m.public_url:
            continue
        gallery.append({
            "id": m.id, "url": m.public_url, "role": m.role,
            "source_type": m.source_type, "width": m.width, "height": m.height,
            "quality": m.quality, "is_primary": m.is_primary,
        })
        if not hero_url and (m.is_primary or m.role == "hero"):
            hero_url = m.public_url
    if not hero_url and gallery:
        hero_url = gallery[0]["url"]

    # Legacy fallback — read old base64 images from the product doc
    if not gallery and product.get("images"):
        legacy = product.get("images") or []
        gallery = [{"url": u, "role": "gallery", "source_type": "supplier",
                    "quality": product.get("image_quality") or "missing",
                    "width": None, "height": None, "is_primary": i == 0}
                   for i, u in enumerate(legacy) if u]
        if gallery:
            hero_url = legacy[0]
            summary["supplier"] = len(gallery)
            best_q = product.get("image_quality") or best_q

    product["media_summary"] = {**summary, "best_quality": best_q, "total": sum(summary.values())}
    product["hero_image_url"] = hero_url
    product["gallery"] = gallery
    return product
