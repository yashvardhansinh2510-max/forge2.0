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

    log.info("All indexes ensured.")


if __name__ == "__main__":
    asyncio.run(ensure_all())
