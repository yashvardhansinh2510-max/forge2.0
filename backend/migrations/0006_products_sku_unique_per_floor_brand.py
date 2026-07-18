"""SKU uniqueness is now scoped per (floor_id, brand_id) rather than
globally or per-brand-only — the ground-floor tile catalog and the
first-floor sanitary catalog are separate businesses that may legitimately
reuse a supplier SKU code across floors.

PREREQUISITE (manual, human decision — do not automate): as of 2026-07-17
there is one known live duplicate SKU (26456000) under Hansgrohe, both rows
on floor_id="first-floor" — this migration's index will fail to build
against that data until it's resolved (rename one SKU or merge the two
products). See migrations/0003's docstring for the exact failure mode
(OperationFailure code 85) this class of problem produces if left
unresolved and the collision happens to also match on index name; a
brand-new index name here means a genuine duplicate-key error instead,
which is the correct, loud failure for real duplicate data — don't catch or
suppress it.
"""
from __future__ import annotations


async def up(db) -> None:
    await db.products.create_index(
        [("floor_id", 1), ("brand_id", 1), ("sku", 1)],
        unique=True,
        name="products_floor_brand_sku_unique",
    )
