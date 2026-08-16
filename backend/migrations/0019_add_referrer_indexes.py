"""Indexes for floor-scoped customer referral attribution."""
from __future__ import annotations

from pymongo.errors import OperationFailure


async def _create_index_tolerant(collection, keys, **kwargs) -> None:
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as error:
        if error.code != 85:
            raise


async def up(db) -> None:
    await db.referrers.update_many(
        {"floor_id": {"$exists": False}}, {"$set": {"floor_id": "first-floor", "active": True}},
    )
    await db.referrers.update_many(
        {"normalized_name": {"$exists": False}},
        [{"$set": {"normalized_name": {"$toLower": {"$trim": {"input": "$name"}}}}}],
    )
    await _create_index_tolerant(
        db.referrers, [("floor_id", 1), ("type", 1), ("normalized_name", 1)],
        name="referrers_floor_type_normalized_name",
    )
    await _create_index_tolerant(db.referrers, [("floor_id", 1), ("active", 1), ("name", 1)], name="referrers_floor_active_name")
    await _create_index_tolerant(db.customers, [("floor_id", 1), ("referrer_id", 1)], name="customers_floor_referrer")
    await _create_index_tolerant(db.quotations, [("floor_id", 1), ("referrer_id", 1), ("ordered_at", -1)], name="quotations_floor_referrer_ordered")
