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


def _apply_media_to_product(product: dict, media: list[ProductMedia]) -> None:
    """Pure in-memory step of hydrate_product_media — given the already
    fetched media rows for this product, attach media_summary/hero/gallery.
    Split out so the batched path (hydrate_media_batch) can reuse the exact
    same logic without an extra DB round trip per product."""
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

    # Backfill the legacy `images` field from the real media pipeline.
    # The catalog import stores photos exclusively in `product_media` /
    # Supabase now — the embedded `product.images` array is empty for every
    # supplier product (0/2966 at last audit). A large surface of the app
    # (Quotation Builder cards, picker rows, modal gallery, swap sheet,
    # assistant pane) reads `product.images` directly and predates the
    # `hero_image_url`/`gallery` fields, so we keep that contract honest here
    # — ONE place, every caller benefits, nothing else has to change.
    if gallery:
        product["images"] = [g["url"] for g in gallery if g.get("url")]
    elif hero_url:
        product["images"] = [hero_url]
    return product


async def hydrate_product_media(product: dict) -> dict:
    """Attach media_summary + hero_image_url + gallery to a SINGLE product
    dict. Fine for one-off lookups (product detail page); for any list of
    products always prefer `hydrate_media_batch` below — this issues one
    query per call and turns into an N+1 when looped."""
    if not product:
        return product
    media = await list_media_for_product(product["id"], product.get("family_key"))
    _apply_media_to_product(product, media)
    return product


async def hydrate_media_batch(docs: list[dict]) -> list[dict]:
    """Same result as calling hydrate_product_media() on every doc, but with
    exactly ONE query against `product_media` for the whole page instead of
    one query per product (was the single biggest latency source in the
    Quotation Builder catalog grid — ~60 sequential round trips per page)."""
    if not docs:
        return docs
    ids = [d["id"] for d in docs if d.get("id")]
    family_keys = list({d["family_key"] for d in docs if d.get("family_key")})
    or_clauses: list[dict] = []
    if ids:
        or_clauses.append({"product_id": {"$in": ids}})
    if family_keys:
        or_clauses.append({"family_key": {"$in": family_keys}})
    if not or_clauses:
        return docs
    rows = await db.product_media.find({"$or": or_clauses}, {"_id": 0}).to_list(20000)
    by_product: dict[str, list[dict]] = {}
    by_family: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("product_id"):
            by_product.setdefault(r["product_id"], []).append(r)
        if r.get("family_key"):
            by_family.setdefault(r["family_key"], []).append(r)

    prio = {"internal": 0, "manufacturer": 1, "supplier": 2}

    def _sorted_media(raw: list[dict]) -> list[ProductMedia]:
        raw = sorted(raw, key=lambda d: (
            prio.get(d.get("source_type", "supplier"), 3),
            0 if d.get("is_primary") else 1,
            int(d.get("sort_order", 100)),
        ))
        return [ProductMedia(**d) for d in raw]

    for d in docs:
        raw = list(by_product.get(d.get("id"), []))
        if d.get("family_key"):
            raw += by_family.get(d["family_key"], [])
        # de-dupe (a row could match both product_id and family_key clauses)
        seen_ids = set()
        deduped = []
        for r in raw:
            rid = r.get("id")
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            deduped.append(r)
        _apply_media_to_product(d, _sorted_media(deduped))
    return docs


async def hydrate_variants_batch(docs: list[dict], limit_per_family: int = 8) -> None:
    """Populate `product["variants"]` for every doc that has a `family_key`
    but no variants of its own — using its FAMILY SIBLINGS (each finish/
    colour of a real supplier product is its own full Product document, not
    an embedded row). One batched query for the whole page/list, not N+1.

    Safe no-op for products that already carry real embedded variants (the
    two legacy demo SKUs) or have no family_key.
    """
    targets = [d for d in docs if d.get("family_key") and not d.get("variants")]
    if not targets:
        return
    family_keys = list({d["family_key"] for d in targets})

    siblings = await db.products.find(
        {"family_key": {"$in": family_keys}, "active": True},
        {
            "_id": 0, "id": 1, "sku": 1, "family_key": 1, "finish": 1, "colour": 1,
            "color": 1, "price": 1, "mrp": 1, "stock": 1, "name": 1,
        },
    ).to_list(20000)
    if not siblings:
        return

    sib_ids = [s["id"] for s in siblings]
    media_docs = await db.product_media.find(
        {"product_id": {"$in": sib_ids}},
        {"_id": 0, "product_id": 1, "public_url": 1, "is_primary": 1, "sort_order": 1, "source_type": 1},
    ).to_list(50000)
    prio = {"internal": 0, "manufacturer": 1, "supplier": 2}
    media_docs.sort(key=lambda m: (
        prio.get(m.get("source_type", "supplier"), 3),
        0 if m.get("is_primary") else 1,
        int(m.get("sort_order", 100)),
    ))
    image_by_pid: dict[str, str] = {}
    for m in media_docs:
        pid = m.get("product_id")
        if pid and pid not in image_by_pid and m.get("public_url"):
            image_by_pid[pid] = m["public_url"]

    by_family: dict[str, list[dict]] = {}
    for s in siblings:
        by_family.setdefault(s["family_key"], []).append(s)

    for d in targets:
        fam = by_family.get(d["family_key"], [])
        variants = []
        for s in fam:
            if s["id"] == d["id"]:
                continue
            variants.append({
                "id": s["id"], "sku": s["sku"],
                "finish": s.get("finish"), "color": s.get("colour") or s.get("color"),
                "price": float(s.get("price") or 0), "mrp": float(s.get("mrp") or s.get("price") or 0),
                "stock": int(s.get("stock") or 0),
                "image": image_by_pid.get(s["id"]),
            })
        if variants:
            d["variants"] = variants[:limit_per_family]
