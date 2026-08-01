"""Indexes for the Executive Operating System's access patterns (spec §3.3).

Nothing on quotations supported analytics before this: every dashboard query
was a collection scan. Harmless at 78 documents, fatal at 100k.

Every create_index tolerates OperationFailure code 85 — a same-keys index
under a different name. That exact conflict hard-crashed the runner twice on
2026-07-17 (migrations 0002 and 0003), so it is the house pattern.
"""
from __future__ import annotations

from pymongo.errors import OperationFailure

_INDEX_CONFLICT_CODE = 85


async def _create_index_tolerant(collection, keys, **kwargs) -> None:
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as e:
        if e.code != _INDEX_CONFLICT_CODE:
            raise


async def up(db) -> None:
    await _create_index_tolerant(db.quotations, [("status", 1), ("floor_id", 1), ("ordered_at", -1)], name="quotations_analytics_revenue")
    await _create_index_tolerant(db.quotations, [("floor_id", 1), ("created_at", -1)], name="quotations_analytics_created")
    await _create_index_tolerant(db.quotations, [("referrer_id", 1), ("status", 1)], name="quotations_analytics_referrer")
    await _create_index_tolerant(db.quotations, [("customer_id", 1), ("status", 1)], name="quotations_analytics_customer")
    await _create_index_tolerant(db.quotations, [("items.product_id", 1)], name="quotations_analytics_product")

    await _create_index_tolerant(db.payments, [("quotation_id", 1), ("status", 1)], name="payments_analytics_quotation")
    await _create_index_tolerant(db.payments, [("floor_id", 1), ("paid_at", -1)], name="payments_analytics_paid")

    await _create_index_tolerant(db.walkins, [("floor_id", 1), ("created_at", -1)], name="walkins_analytics_created")
    await _create_index_tolerant(db.walkins, [("customer_id", 1)], name="walkins_analytics_customer")

    await _create_index_tolerant(db.followups, [("floor_id", 1), ("status", 1), ("due_at", 1)], name="followups_analytics_due")

    await _create_index_tolerant(db.customer_orders, [("floor_id", 1), ("overall_status", 1), ("created_at", -1)], name="customer_orders_analytics")
    await _create_index_tolerant(db.dispatches, [("floor_id", 1), ("dispatch_date", -1)], name="dispatches_analytics_date")
    await _create_index_tolerant(db.dispatches, [("customer_order_id", 1)], name="dispatches_analytics_order")

    await _create_index_tolerant(db.activity_events, [("customer_id", 1), ("created_at", -1)], name="activity_analytics_customer")
    await _create_index_tolerant(db.activity_events, [("quotation_id", 1), ("created_at", -1)], name="activity_analytics_quotation")
