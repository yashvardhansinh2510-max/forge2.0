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


async def _seed_from_existing(
    key: str, collection: str, prefix: str, *, array_field: Optional[str] = None,
) -> None:
    """First allocation for a prefix: never re-issue a number that already
    exists in the collection (pre-counter data). $max keeps concurrent
    seeders from lowering an already-seeded value.

    `array_field`, when given, means the numbers live nested inside an
    embedded array (e.g. Chalan numbers at purchase_orders.chalans[].number)
    rather than at the collection's own top-level `number` field. Scanning
    the top-level field for a prefix that only ever appears nested would
    find nothing and silently re-seed at 0 even with hundreds of numbered
    records already live — Mongo's dotted-path regex match still finds the
    right documents, but the numbers have to be pulled out of the array."""
    max_seq = 0
    number_path = f"{array_field}.number" if array_field else "number"
    projection = {"_id": 0, array_field: 1} if array_field else {"_id": 0, "number": 1}
    async for doc in db[collection].find({number_path: {"$regex": f"^{prefix}"}}, projection):
        numbers = [item.get("number") for item in doc.get(array_field, [])] if array_field else [doc.get("number")]
        for number in numbers:
            tail = str(number or "")[len(prefix):]
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
    array_field: Optional[str] = None,
) -> str:
    key = f"{kind}:{prefix}"
    if not await db.counters.find_one({"_id": key}, {"_id": 1}):
        await _seed_from_existing(key, collection, prefix, array_field=array_field)
    doc = await db.counters.find_one_and_update(
        {"_id": key},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    return f"{prefix}{int(doc['seq']):0{width}d}"
