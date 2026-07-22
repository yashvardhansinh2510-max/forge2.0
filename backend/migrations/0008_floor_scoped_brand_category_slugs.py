"""Make Brand/Category slugs unique per floor, matching their data model.

Existing global unique slug indexes prevented an isolated ground-floor catalog
from using the same supplier/category names as the sanitary floor. All legacy
documents already default to ``first-floor``, so the new compound constraints
remain safe while allowing independent catalogs going forward.
"""
from __future__ import annotations


async def _replace_global_slug_index(collection, name: str) -> None:
    indexes = await collection.index_information() or {}
    for index_name, spec in indexes.items():
        keys = tuple(spec.get("key", []))
        if keys == (("slug", 1),) and spec.get("unique"):
            await collection.drop_index(index_name)
    await collection.create_index(
        [("floor_id", 1), ("slug", 1)],
        unique=True,
        sparse=True,
        name=name,
    )


async def up(db) -> None:
    await _replace_global_slug_index(db.brands, "brands_floor_slug")
    await _replace_global_slug_index(db.categories, "categories_floor_slug")
