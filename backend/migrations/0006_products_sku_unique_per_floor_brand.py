"""SKU uniqueness is now scoped per (floor_id, brand_id) rather than
globally or per-brand-only — the ground-floor tile catalog and the
first-floor sanitary catalog are separate businesses that may legitimately
reuse a supplier SKU code across floors.

The previously reported Hansgrohe collision was verified as already
normalised in production: the two valid products are stored as ``26456000``
and ``26456000-2``. The ``-2`` row is the "With attachment" variant; it is
not a duplicate document. Keep this index strict: any future same-floor,
same-brand SKU collision must use an explicit supplier/variant SKU suffix
rather than silently overwriting a catalog row.

Production startup intentionally does not auto-apply pending migrations by
default. Run the dry-run and controlled migration job in
``OPERATOR_CHECKLIST.md`` before a production restart. This migration performs
its own duplicate preflight so an unresolved data conflict is reported before
the unique index is attempted.
"""
from __future__ import annotations


async def up(db) -> None:
    duplicates = await db.products.aggregate([
        {"$match": {"sku": {"$type": "string", "$ne": ""}}},
        {"$group": {"_id": {"floor_id": "$floor_id", "brand_id": "$brand_id", "sku": "$sku"}, "ids": {"$push": "$id"}, "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 20},
    ]).to_list(20)
    if duplicates:
        raise RuntimeError(
            "Cannot create products_floor_brand_sku_unique: duplicate (floor_id, brand_id, sku) values exist. "
            f"Resolve these records first: {duplicates}"
        )
    await db.products.create_index(
        [("floor_id", 1), ("brand_id", 1), ("sku", 1)],
        unique=True,
        name="products_floor_brand_sku_unique",
    )
