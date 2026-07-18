"""Atomic business-number allocation.

Replaces the old count+1 pattern, which could hand two concurrent requests
the same quotation/PO number. Counters live in `db.counters`, one document
per (kind, prefix); allocation is a single findOneAndUpdate $inc so it is
race-free. Aborted transactions may leave gaps in the sequence — that is
acceptable and expected for business document numbers.
"""
from typing import Any, Optional

from pymongo import ReturnDocument

from db import db


async def _seed_from_existing(key: str, collection: str, prefix: str) -> None:
    """First allocation for a prefix: never re-issue a number that already
    exists in the collection (pre-counter data). $max keeps concurrent
    seeders from lowering an already-seeded value."""
    max_seq = 0
    async for doc in db[collection].find({"number": {"$regex": f"^{prefix}"}}, {"_id": 0, "number": 1}):
        tail = str(doc.get("number") or "")[len(prefix):]
        if tail.isdigit():
            max_seq = max(max_seq, int(tail))
    await db.counters.update_one({"_id": key}, {"$max": {"seq": max_seq}}, upsert=True)


async def next_number(
    kind: str,
    prefix: str,
    *,
    collection: str,
    width: int = 4,
    session: Optional[Any] = None,
) -> str:
    key = f"{kind}:{prefix}"
    if not await db.counters.find_one({"_id": key}, {"_id": 1}):
        await _seed_from_existing(key, collection, prefix)
    doc = await db.counters.find_one_and_update(
        {"_id": key},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    return f"{prefix}{int(doc['seq']):0{width}d}"
