"""Mongo indexes for the four new Tile Orders logistics collections.
Called once at app startup (server.py), alongside the existing
ensure_outbox_indexes()."""
from __future__ import annotations

from db import db


async def ensure_tile_order_indexes() -> None:
    await db.customer_orders.create_index("customer_id", name="customer_order_customer_id")
    await db.customer_orders.create_index("created_at", name="customer_order_created_at")
    await db.customer_orders.create_index("quotation_id", name="customer_order_quotation_id")
    await db.customer_orders.create_index("number", unique=True, name="customer_order_number_unique")
    await db.customer_orders.create_index("automation_key", unique=True, sparse=True, name="customer_order_automation_key")

    await db.purchase_orders.create_index("customer_order_id", name="po_customer_order_id")
    await db.purchase_orders.create_index([("supplier_id", 1), ("overall_status", 1)], name="po_supplier_status")
    await db.purchase_orders.create_index("last_supplier_activity_at", name="po_last_supplier_activity")

    await db.ready_batches.create_index([("purchase_order_id", 1), ("po_item_id", 1)], name="ready_batch_po_item")
    await db.ready_batches.create_index("supplier_id", name="ready_batch_supplier")
    await db.ready_batches.create_index("customer_id", name="ready_batch_customer")
    await db.ready_batches.create_index("batch_number", unique=True, name="ready_batch_number_unique")

    await db.dispatches.create_index([("purchase_order_id", 1), ("dispatch_date", 1)], name="dispatch_po_date")
    await db.dispatches.create_index("supplier_id", name="dispatch_supplier")
    await db.dispatches.create_index("customer_id", name="dispatch_customer")
    await db.dispatches.create_index("dispatch_number", unique=True, name="dispatch_number_unique")

    await db.chalans.create_index("dispatch_id", unique=True, name="chalan_dispatch_unique")
    await db.chalans.create_index("number", unique=True, name="chalan_number_unique")
