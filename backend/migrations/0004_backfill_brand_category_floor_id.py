"""Brand and Category never had a floor_id field at all (2026-07-17
floor-isolation investigation — this is why the ground-floor tile section
and the first-floor sanitary catalog couldn't be told apart at the
brand/category level). Every existing brand/category belongs to the
first-floor sanitary catalog, so backfill that value explicitly rather than
leaving the field to Pydantic's model default silently covering for it —
an explicit stored value survives a future change to that default."""
from __future__ import annotations


async def up(db) -> None:
    await db.brands.update_many(
        {"floor_id": {"$exists": False}}, {"$set": {"floor_id": "first-floor"}},
    )
    await db.categories.update_many(
        {"floor_id": {"$exists": False}}, {"$set": {"floor_id": "first-floor"}},
    )
