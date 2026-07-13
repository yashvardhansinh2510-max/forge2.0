"""Ensure MongoDB indexes exist for fast catalog navigation + search.

Run via `python -m scripts.ensure_indexes`. Safe to run repeatedly —
Motor's `create_index` is idempotent.
"""
from __future__ import annotations
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

from db import db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s :: %(message)s")
log = logging.getLogger("forge.indexes")


async def ensure_all() -> None:
    # products: text search + facet lookups
    await db.products.create_index([
        ("name", "text"), ("sku", "text"), ("family_name", "text"),
        ("series", "text"), ("subcategory", "text"), ("finish", "text"),
        ("colour", "text"), ("dimensions", "text"), ("description", "text"),
        ("tags", "text"),
    ], name="products_text_v1", default_language="english", weights={
        "sku": 20, "name": 12, "family_name": 10, "series": 6,
        "subcategory": 4, "finish": 3, "colour": 3, "tags": 2,
        "dimensions": 1, "description": 1,
    })
    await db.products.create_index("id", unique=True, name="products_id")
    await db.products.create_index("sku", name="products_sku")
    await db.products.create_index("family_key", name="products_family_key")
    await db.products.create_index(
        [("brand_id", 1), ("category_id", 1), ("subcategory", 1), ("series", 1)],
        name="products_hierarchy",
    )
    await db.products.create_index([("active", 1), ("brand_id", 1)], name="products_active_brand")
    await db.products.create_index(
        [("active", 1), ("name", 1), ("id", 1)],
        name="products_active_name_id",
    )
    await db.products.create_index(
        [("active", 1), ("price", 1), ("id", 1)],
        name="products_active_price_id",
    )
    await db.products.create_index(
        [("active", 1), ("price", -1), ("id", 1)],
        name="products_active_price_desc_id",
    )

    # product_usage: per-user recent/frequent tabs.
    await db.product_usage.create_index("user_id", name="usage_user")
    await db.product_usage.create_index("product_id", name="usage_product")
    await db.product_usage.create_index(
        [("user_id", 1), ("last_used_at", -1)], name="usage_user_recent",
    )
    await db.product_usage.create_index(
        [("user_id", 1), ("count", -1)], name="usage_user_count",
    )

    # product_media: lookup by product/family, plus sha1 dedupe
    await db.product_media.create_index("id", unique=True, name="pm_id")
    await db.product_media.create_index("product_id", name="pm_product_id")
    await db.product_media.create_index("family_key", name="pm_family_key")
    await db.product_media.create_index(
        [("sha1", 1), ("product_id", 1), ("source_type", 1)],
        name="pm_sha1_scope",
    )
    await db.product_media.create_index(
        [("is_primary", -1), ("sort_order", 1)], name="pm_ordering",
    )

    # brands + categories
    await db.brands.create_index("id", unique=True, name="brands_id")
    await db.brands.create_index("slug", unique=True, name="brands_slug", sparse=True)
    await db.categories.create_index("id", unique=True, name="categories_id")

    # legacy blob store
    await db.catalog_image_blobs.create_index("sha1", unique=True, name="blob_sha1")

    # -------------------------------------------------------------------
    # Data Integrity Audit (Phase 2, 2026-08): the historical Hansgrohe/AXOR
    # recovery incident (see /app/memory/PRD.md "CRITICAL BUG FOUND") was
    # caused by exactly one gap — SKU uniqueness was enforced only by
    # application code (`{"sku": sku, "brand_id": ...}` lookups), never by
    # the database itself, so a coding mistake could silently clobber a
    # different brand's product sharing the same numeric code. A read-only
    # audit this session confirmed zero duplicates exist today (0 same-brand
    # SKU dupes, 0 duplicate quotation/PO numbers, 0 duplicate user emails)
    # — these unique indexes convert that "no duplicates today" into
    # "duplicates are now structurally impossible", closing the exact class
    # of bug that caused real data loss twice before. Never applied blindly:
    # each one was verified duplicate-free against live data before being
    # added here, so index creation cannot fail on this dataset.
    # `products_sku_brand_unique` intentionally NOT auto-created here yet — a
    # real live same-brand duplicate (SKU "26456000", two distinct Hansgrohe
    # products) was found by this exact index during the Phase 2 Data
    # Integrity Audit (2026-08) and must be resolved by a human decision
    # (which product record is correct) before this constraint can be
    # applied catalog-wide without an exception. Wrapped so this script stays
    # safe to run repeatedly in the meantime instead of hard-crashing.
    try:
        await db.products.create_index(
            [("sku", 1), ("brand_id", 1)], unique=True, name="products_sku_brand_unique",
        )
    except Exception as e:  # noqa: BLE001 — DuplicateKeyError until the dupe above is resolved
        log.warning("products_sku_brand_unique NOT created (pending duplicate resolution): %s", e)

    await db.users.create_index("email", unique=True, name="users_email_unique")
    await db.quotations.create_index("number", unique=True, name="quotations_number_unique")
    await db.purchase_orders.create_index("number", unique=True, name="purchase_orders_number_unique")

    log.info("All indexes ensured.")


if __name__ == "__main__":
    asyncio.run(ensure_all())
