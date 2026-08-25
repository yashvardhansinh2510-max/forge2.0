"""Add non-unique, online-safe indexes for the dashboard's bounded read paths.

This is additive and idempotent.  The indexes serve floor-scoped recent
activity, current-month quotation metrics, and a user's due-follow-up count;
they do not change existing data or constraints.  MongoDB builds these indexes
without taking the collection offline on modern Atlas deployments.
"""
from __future__ import annotations

from pymongo.errors import OperationFailure


async def _create_index_tolerant(collection, keys, **kwargs) -> None:
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as error:
        # A deployment may already have the same key pattern under a legacy
        # name. Keep startup safe while preserving the existing index.
        if error.code != 85:
            raise


async def up(db) -> None:
    await _create_index_tolerant(
        db.quotations, [("floor_id", 1), ("updated_at", -1)],
        name="dashboard_quotations_floor_updated",
    )
    await _create_index_tolerant(
        db.quotations, [("floor_id", 1), ("created_at", -1)],
        name="dashboard_quotations_floor_created",
    )
    await _create_index_tolerant(
        db.followups, [("floor_id", 1), ("assigned_to", 1), ("status", 1), ("due_at", 1)],
        name="dashboard_followups_due",
    )
