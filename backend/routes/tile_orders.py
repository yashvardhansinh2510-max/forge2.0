"""Tile Orders logistics — Ready/Dispatch/Chalan actions and the Company/
Supplier/Customer/Dispatch-List read endpoints. Order placement (creating
the TileCustomerOrder itself) lives in services/domain_outbox.py, not here
— see that file's _handle_order_placed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import floor_query, require_min_role
from db import client, db
from models import UserPublic, now_iso
from models_tile_orders import TileReadyBatch
from services.activity_log import log_event
from services.sequence import next_number
from services.tile_order_status import (
    completion_percentage, derive_current_location, derive_item_status, rollup_status,
)

router = APIRouter(prefix="/tile-orders", tags=["tile-orders"])


class ReadyItemInput(BaseModel):
    po_item_id: str
    qty: float = Field(gt=0)


class BulkReadyBody(BaseModel):
    items: list[ReadyItemInput] = Field(min_length=1)


async def _sync_customer_order_brand_status(co_id: Optional[str], po_id: str, new_status: str, session) -> None:
    """Updates this PO's entry in TileCustomerOrder.brands[], then rolls the
    CustomerOrder's own overall_status/dashboard_summary up from all
    brands. Increments `version` as the defense-in-depth CAS guard the
    design doc calls for — the enclosing transaction is the primary safety
    net (see Task 6's transaction-strategy note)."""
    if not co_id:
        return
    co = await db.customer_orders.find_one({"id": co_id}, {"_id": 0}, session=session)
    if not co:
        return
    brands = co.get("brands", [])
    for brand in brands:
        if brand.get("purchase_order_id") == po_id:
            brand["status"] = new_status
    overall = rollup_status([b.get("status", "Pending") for b in brands])
    summary = {
        "completion_percentage": co.get("completion_percentage", 0),
        "overall_status": overall,
        "supplier_statuses": [{"supplier_name": b.get("supplier_name"), "status": b.get("status")} for b in brands],
    }
    await db.customer_orders.update_one(
        {"id": co_id, "version": co.get("version", 0)},
        {"$set": {
            "brands": brands, "overall_status": overall, "dashboard_summary": summary,
            "last_activity": "Status changed", "last_activity_at": now_iso(),
            "version": co.get("version", 0) + 1, "updated_at": now_iso(),
        }},
        session=session,
    )


@router.post("/purchase-orders/{po_id}/ready")
async def mark_items_ready(
    po_id: str, body: BulkReadyBody, user: UserPublic = Depends(require_min_role("warehouse")),
):
    """'Mark Ready For Pickup' — bulk, one transaction. Never creates a
    Chalan (see Task 8's Dispatch endpoint for that)."""
    session = await client.start_session()
    async with session:
        async with session.start_transaction():
            po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0}, session=session)
            if not po:
                raise HTTPException(status_code=404, detail="Purchase order not found")
            items_by_id = {item["id"]: item for item in po.get("items", [])}
            created_batches: list[dict] = []
            year = datetime.now(timezone.utc).year
            new_status: Optional[str] = None
            for entry in body.items:
                item = items_by_id.get(entry.po_item_id)
                if not item:
                    raise HTTPException(status_code=400, detail=f"Unknown item {entry.po_item_id}")
                pending = float(item.get("boxes_pending") or 0)
                if entry.qty > pending + 1e-6:
                    raise HTTPException(status_code=400, detail=f"Only {pending:g} boxes of '{item.get('name')}' are pending")

                batch_number = await next_number("ready_batch", f"RB-{year}-", collection="ready_batches", session=session)
                batch = TileReadyBatch(
                    batch_number=batch_number, purchase_order_id=po_id, po_item_id=entry.po_item_id,
                    customer_order_id=po.get("customer_order_id") or "", floor_id=po.get("floor_id", "first-floor"),
                    supplier_id=po.get("supplier_id"),
                    supplier_name=po.get("supplier_name") or "Unassigned", customer_id=po.get("customer_id"),
                    customer_name=po.get("customer_name") or "", tile_name=item.get("name", ""),
                    series=item.get("series"), finish=item.get("finish"), size=item.get("size"), sku=item.get("sku"),
                    qty=entry.qty, remaining_qty=entry.qty, created_by=user.id, created_by_name=user.full_name,
                )
                await db.ready_batches.insert_one(batch.dict(), session=session)
                created_batches.append(batch.dict())

                item["boxes_ready"] = float(item.get("boxes_ready") or 0) + entry.qty
                item["boxes_pending"] = pending - entry.qty
                item["overall_status"] = derive_item_status(item["qty"], item["boxes_ready"], float(item.get("boxes_dispatched") or 0))
                item["current_location"] = derive_current_location(item["qty"], item["boxes_ready"], float(item.get("boxes_dispatched") or 0))

            items = list(items_by_id.values())
            ready_boxes = sum(float(i.get("boxes_ready") or 0) for i in items)
            pending_boxes = sum(float(i.get("boxes_pending") or 0) for i in items)
            dispatched_boxes = sum(float(i.get("boxes_dispatched") or 0) for i in items)
            ordered_boxes = sum(float(i.get("qty") or 0) for i in items)
            new_status = rollup_status([i["overall_status"] for i in items])
            now = now_iso()
            await db.purchase_orders.update_one(
                {"id": po_id}, {"$set": {
                    "items": items, "ready_boxes": ready_boxes, "pending_boxes": pending_boxes,
                    "dispatched_boxes": dispatched_boxes, "overall_status": new_status,
                    "completion_percentage": completion_percentage(ordered_boxes, dispatched_boxes),
                    "latest_ready_date": now, "last_supplier_activity_at": now, "updated_at": now,
                }}, session=session,
            )
            await _sync_customer_order_brand_status(po.get("customer_order_id"), po_id, new_status, session)

    for batch in created_batches:
        await log_event(
            event_type="ready_batch.created", entity_type="purchase", entity_id=po_id, actor=user,
            customer_id=po.get("customer_id"), purchase_id=po_id,
            summary=f"Marked {batch['qty']:g} boxes of '{batch['tile_name']}' ready ({batch['batch_number']})",
            payload={"ready_batch_id": batch["id"], "batch_number": batch["batch_number"], "po_item_id": batch["po_item_id"], "qty": batch["qty"]},
        )
    if new_status:
        await log_event(
            event_type="status.changed", entity_type="purchase", entity_id=po_id, actor=user,
            customer_id=po.get("customer_id"), purchase_id=po_id,
            summary=f"Status changed to {new_status}", payload={"to": new_status},
        )
    return {"po_id": po_id, "ready_batches": created_batches, "overall_status": new_status}
