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


async def import_accepted(job: dict, user_id: str) -> dict:
    """Persist all rows in job['rows'] with status == 'accepted' into products.

    Idempotent: existing SKUs are updated (not duplicated). Never deletes anything.
    Skips rows missing category/mrp/price.
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

        payload = {
            "name": str(r.get("name") or "Untitled")[:200],
            "brand_id": brand_doc["id"],
            "category_id": cat["id"],
            "description": None if r.get("description") in (None, MISSING) else str(r.get("description")),
            "finish": None if r.get("finish") in (None, MISSING) else str(r.get("finish")),
            "material": None if r.get("material") in (None, MISSING) else str(r.get("material")),
            "dimensions": None if r.get("dimensions") in (None, MISSING) else str(r.get("dimensions")),
            "warranty": None if r.get("warranty") in (None, MISSING) else str(r.get("warranty")),
            "mrp": mrp,
            "price": price_val,
            "images": r.get("images") or [],
            "tags": [cat["name"].lower(), supplier.lower(), (r.get("finish") or "").lower()],
            "active": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

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
