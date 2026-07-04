"""Orchestrator wiring Extraction → Validation → Certification → Import."""
from __future__ import annotations
import logging
from datetime import datetime, timezone

from db import db
from models import Product

from .base import MISSING, ProductRow
from .certifier import CertificationReport, validate
from .adapters import get_adapter

logger = logging.getLogger("forge.catalog_pipeline")


# ---------------------------------------------------------------------------
# Image blob offload (keeps job doc under MongoDB's 16MB BSON cap)
# ---------------------------------------------------------------------------
async def _offload_row_images(rows: list[dict]) -> dict[str, str]:
    """Move every base64 data-URL out of `rows[].images` into a dedicated
    `catalog_image_blobs` collection keyed by SHA-1.

    Mutates rows in-place: `images` becomes a list of ``blob:<sha1>`` refs,
    and each entry in `image_meta` gets an ``id`` field pointing at the blob.

    Returns the map of ``sha1 → data_url`` that was uploaded (so the caller
    can pipe it straight into ``import_accepted`` without a second DB read).
    """
    blob_map: dict[str, str] = {}
    for r in rows:
        images = r.get("images") or []
        metas = r.get("image_meta") or []
        new_urls: list[str] = []
        for i, img in enumerate(images):
            if not img:
                continue
            if img.startswith("blob:") or not img.startswith("data:"):
                new_urls.append(img)
                continue
            # Compute or reuse sha1 from meta
            sha1 = (metas[i].get("sha1") if i < len(metas) and isinstance(metas[i], dict) else None)
            if not sha1:
                import hashlib
                sha1 = hashlib.sha1(img.encode("utf-8")).hexdigest()[:16]
                if i < len(metas) and isinstance(metas[i], dict):
                    metas[i]["sha1"] = sha1
            blob_map[sha1] = img
            new_urls.append(f"blob:{sha1}")
        r["images"] = new_urls

    # Bulk-upsert blobs (idempotent — same sha1 always maps to same content)
    if blob_map:
        from pymongo import UpdateOne
        ops = [
            UpdateOne(
                {"sha1": sha1},
                {"$setOnInsert": {"sha1": sha1, "data_url": url,
                                  "created_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
            for sha1, url in blob_map.items()
        ]
        # Do in chunks of 100 to bound memory
        for i in range(0, len(ops), 100):
            await db.catalog_image_blobs.bulk_write(ops[i:i + 100], ordered=False)
    return blob_map


async def _resolve_blob(ref: str, blob_map: dict[str, str] | None = None) -> str | None:
    """Resolve a `blob:<sha1>` ref back to its base64 data URL."""
    if not ref:
        return None
    if not ref.startswith("blob:"):
        return ref
    sha1 = ref[len("blob:"):]
    if blob_map and sha1 in blob_map:
        return blob_map[sha1]
    doc = await db.catalog_image_blobs.find_one({"sha1": sha1}, {"_id": 0, "data_url": 1})
    return doc.get("data_url") if doc else None


async def run_pipeline(brand: str, filename: str, data: bytes) -> dict:
    """Extract + validate + certify. Returns everything the UI needs to render Review."""
    adapter = get_adapter(brand)
    rows, extraction = adapter.extract(data, filename)
    validated_rows, cert = validate(rows)

    # Auto-accept high-confidence rows so the reviewer only sees the exceptions
    for r in validated_rows:
        if (
            r.status == "pending"
            and r.confidence >= 0.85
            and r.sku != MISSING and r.mrp != MISSING and r.category != MISSING
        ):
            r.status = "accepted"

    return {
        "extraction": extraction.__dict__,
        "certification": cert.to_public(),
        "rows": [r.to_public() for r in validated_rows],
    }


async def import_accepted(job: dict, user_id: str, blob_map: dict[str, str] | None = None) -> dict:
    """Persist all rows in job['rows'] with status == 'accepted' into products.

    Idempotent: existing SKUs are updated (not duplicated). Never deletes anything.
    Skips rows missing category/mrp/price.

    Image blobs referenced as ``blob:<sha1>`` are resolved from the optional
    in-memory ``blob_map`` first (avoids a DB round-trip per image), then
    falls back to the ``catalog_image_blobs`` collection.
    """
    supplier = job["supplier_name"]
    brand_doc = await db.brands.find_one({"name": supplier}, {"_id": 0})
    if not brand_doc:
        # Autocreate brand if missing
        from models import Brand
        b = Brand(name=supplier, slug=supplier.lower(), country=None)
        await db.brands.insert_one(b.dict())
        brand_doc = b.dict()

    cats = await db.categories.find({}, {"_id": 0}).to_list(80)
    cat_by_name = {c["name"].lower(): c for c in cats}
    # Autocreate categories that don't exist yet (only for allowed labels)
    from catalog_pipeline.base import ALLOWED_CATEGORIES
    from models import Category
    for label in ALLOWED_CATEGORIES:
        if label.lower() not in cat_by_name:
            c = Category(name=label, slug=label.lower().replace(" ", "-"))
            await db.categories.insert_one(c.dict())
            cat_by_name[label.lower()] = c.dict()

    imported = 0
    updated = 0
    skipped = 0

    def _clean(v):
        return None if v in (None, MISSING) else v

    for r in job.get("rows", []):
        if r.get("status") != "accepted":
            continue
        if r.get("mrp") in (None, MISSING) or r.get("category") in (None, MISSING):
            skipped += 1
            continue
        cat = cat_by_name.get(str(r.get("category", "")).lower())
        if not cat:
            skipped += 1
            continue

        mrp = float(r["mrp"])
        price_val = r.get("dealer_price") if r.get("dealer_price") not in (None, MISSING) else mrp
        price_val = float(price_val)

        # Hierarchy fields — never fabricate; missing supplier data stays null.
        subcategory = _clean(r.get("subcategory"))
        series = _clean(r.get("series"))
        family_key = _clean(r.get("family_key"))
        variant_label = _clean(r.get("variant"))
        finish = _clean(r.get("finish"))
        finish_code = _clean(r.get("finish_code"))
        colour = _clean(r.get("colour"))
        description = _clean(r.get("description"))
        specs = r.get("specs") or {}
        image_meta = r.get("image_meta") or []
        image_quality = _clean(r.get("image_quality")) or "missing"

        # family_name is series + form: "Metropole · Wall Hung WC"
        family_name = None
        if series:
            series_clean = str(series).strip()
            if description and str(description).strip():
                desc_clean = str(description).strip()
                # Avoid pathological "SERIES · SERIES · DETAIL" duplication.
                if desc_clean.lower().startswith(series_clean.lower()):
                    family_name = desc_clean
                elif series_clean.lower() in desc_clean.lower():
                    family_name = desc_clean
                else:
                    family_name = f"{series_clean} · {desc_clean}"
            else:
                family_name = series_clean
        elif description:
            family_name = str(description).strip()

        # Resolve any blob:<sha1> references back to data URLs
        raw_images = r.get("images") or []
        resolved_images: list[str] = []
        for ref in raw_images:
            if not ref:
                continue
            if ref.startswith("blob:"):
                data_url = await _resolve_blob(ref, blob_map)
                if data_url:
                    resolved_images.append(data_url)
            else:
                resolved_images.append(ref)

        payload = {
            "name": str(r.get("name") or "Untitled")[:200],
            "brand_id": brand_doc["id"],
            "category_id": cat["id"],
            "subcategory": subcategory,
            "series": series,
            "family_key": family_key,
            "family_name": family_name,
            "variant_label": variant_label,
            "finish_code": finish_code,
            "colour": colour,
            "description": None if description is None else str(description),
            "finish": None if finish is None else str(finish),
            "material": _clean(r.get("material")),
            "dimensions": _clean(r.get("dimensions")),
            "warranty": _clean(r.get("warranty")),
            "mrp": mrp,
            "price": price_val,
            "images": resolved_images,
            "image_meta": image_meta,
            "image_quality": image_quality,
            "specs": specs if isinstance(specs, dict) else {},
            "tags": r.get("tags") or [
                cat["name"].lower(), supplier.lower(),
                (finish or "").lower(),
                (series or "").lower(),
            ],
            "active": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # Drop any tags that ended up empty strings
        payload["tags"] = [t for t in payload["tags"] if t]

        sku = r.get("sku") or ""
        if sku and sku != MISSING:
            existing = await db.products.find_one({"sku": sku}, {"_id": 0})
            if existing:
                await db.products.update_one({"sku": sku}, {"$set": payload})
                updated += 1
                continue
            payload["sku"] = sku
        else:
            skipped += 1
            continue

        p = Product(**payload)
        await db.products.insert_one(p.dict())
        imported += 1

    return {"imported": imported, "updated": updated, "skipped": skipped}


async def rollback_job(job_id: str) -> int:
    """Delete all products imported by this job (matched via a tag)."""
    # We rely on the fact that the import writes both an SKU list into the job doc;
    # but the current schema doesn't persist that yet — rollback marks the job status
    # only, actual product rows aren't destroyed. This preserves quotations that
    # reference these SKUs, per spec ("never delete products automatically").
    await db.catalog_imports.update_one({"id": job_id}, {"$set": {"status": "rolled_back"}})
    return 0
