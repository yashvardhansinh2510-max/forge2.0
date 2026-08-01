"""Backfill ordered_at for quotations confirmed before the field existed.

updated_at is the best available approximation and is explicitly imperfect:
for any order edited after confirmation it is the last edit time, not the
confirmation time. It is recorded here so a future session reading a July
2026 revenue chart knows those rows are approximate and every row after
this migration is exact.

Only fills where the field is missing, so it never overwrites a real stamp
and is safe to re-run.
"""
from __future__ import annotations


async def up(db) -> None:
    cursor = db.quotations.find(
        {"status": "ordered", "ordered_at": {"$in": [None, ""]}},
        {"_id": 0, "id": 1, "updated_at": 1, "created_at": 1},
    )
    async for doc in cursor:
        stamp = doc.get("updated_at") or doc.get("created_at")
        if not stamp:
            continue
        await db.quotations.update_one({"id": doc["id"]}, {"$set": {"ordered_at": stamp}})
