"""Tile Orders logistics — Ready/Dispatch/Chalan actions and the Company/
Supplier/Customer/Dispatch-List read endpoints. Order placement (creating
the TileCustomerOrder itself) lives in services/domain_outbox.py, not here
— see that file's _handle_order_placed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import floor_query, require_min_role
from db import client, db
from models import UserPublic, now_iso
from models_tile_orders import TileChalan, TileChalanItem, TileDispatch, TileDispatchLineConsumed, TileReadyBatch
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


class DispatchLineInput(BaseModel):
    po_item_id: str
    ready_batch_id: Optional[str] = None   # None = dispatch straight from Pending
    qty: float = Field(gt=0)


class DispatchBody(BaseModel):
    items: list[DispatchLineInput] = Field(min_length=1)
    destination_type: Literal["Customer", "Godown"]
    destination_name: str
    destination_address: str
    destination_city: str
    reference_number: Optional[str] = None
    receiver_name: Optional[str] = None
    sender_name: Optional[str] = None


async def _resolve_dispatch_lines(po: dict, body: DispatchBody, session=None) -> tuple[list[dict], list[str]]:
    """Shared by preview and commit. Returns (resolved_lines, warnings) —
    resolved_lines carries per-line {po_item_id, qty, source
    ('existing'|'pending'), item, batch_or_none}. Raises 400 on any error
    that would make the dispatch invalid (unknown item, over-consuming a
    batch, more than what's Pending)."""
    items_by_id = {item["id"]: item for item in po.get("items", [])}
    resolved: list[dict] = []
    warnings: list[str] = []
    for entry in body.items:
        item = items_by_id.get(entry.po_item_id)
        if not item:
            raise HTTPException(status_code=400, detail=f"Unknown item {entry.po_item_id}")
        if entry.ready_batch_id:
            batch = await db.ready_batches.find_one({"id": entry.ready_batch_id}, {"_id": 0}, session=session)
            if not batch or batch.get("po_item_id") != entry.po_item_id:
                raise HTTPException(status_code=400, detail=f"Ready batch {entry.ready_batch_id} not found for this item")
            if entry.qty > float(batch.get("remaining_qty") or 0) + 1e-6:
                raise HTTPException(status_code=400, detail=f"Only {batch['remaining_qty']:g} boxes remain in batch {batch['batch_number']}")
            resolved.append({"po_item_id": entry.po_item_id, "qty": entry.qty, "source": "existing", "item": item, "batch": batch})
        else:
            pending = float(item.get("boxes_pending") or 0)
            if entry.qty > pending + 1e-6:
                raise HTTPException(status_code=400, detail=f"Only {pending:g} boxes of '{item.get('name')}' are pending")
            warnings.append(f"'{item.get('name')}' will be dispatched directly from Pending — a Ready Batch is created automatically for the audit trail.")
            resolved.append({"po_item_id": entry.po_item_id, "qty": entry.qty, "source": "pending", "item": item, "batch": None})
    return resolved, warnings


@router.post("/purchase-orders/{po_id}/dispatch/preview")
async def preview_dispatch(po_id: str, body: DispatchBody, user: UserPublic = Depends(require_min_role("warehouse"))):
    po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    resolved, warnings = await _resolve_dispatch_lines(po, body)
    lines = [{
        "po_item_id": r["po_item_id"], "tile_name": r["item"].get("name"), "qty": r["qty"],
        "source": r["source"], "remaining_pending_after": float(r["item"].get("boxes_pending") or 0) - (r["qty"] if r["source"] == "pending" else 0),
    } for r in resolved]
    return {
        "po_id": po_id, "items": lines, "warnings": warnings,
        "will_create": {"dispatch_number": "assigned on confirm", "chalan_number": "assigned on confirm", "creates_dispatch_list_entry": True},
    }


@router.post("/purchase-orders/{po_id}/dispatch")
async def commit_dispatch(po_id: str, body: DispatchBody, user: UserPublic = Depends(require_min_role("warehouse"))):
    session = await client.start_session()
    async with session:
        async with session.start_transaction():
            po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0}, session=session)
            if not po:
                raise HTTPException(status_code=404, detail="Purchase order not found")
            resolved, _warnings = await _resolve_dispatch_lines(po, body, session=session)
            items_by_id = {item["id"]: item for item in po.get("items", [])}
            year = datetime.now(timezone.utc).year
            consumed: list[TileDispatchLineConsumed] = []
            chalan_items: list[TileChalanItem] = []

            for r in resolved:
                item = items_by_id[r["po_item_id"]]
                qty = r["qty"]
                if r["source"] == "existing":
                    batch = r["batch"]
                    new_remaining = float(batch["remaining_qty"]) - qty
                    await db.ready_batches.update_one({"id": batch["id"]}, {"$set": {"remaining_qty": new_remaining}}, session=session)
                    item["boxes_ready"] = float(item.get("boxes_ready") or 0) - qty
                    ready_batch_id = batch["id"]
                else:
                    batch_number = await next_number("ready_batch", f"RB-{year}-", collection="ready_batches", session=session)
                    auto_batch = TileReadyBatch(
                        batch_number=batch_number, purchase_order_id=po_id, po_item_id=r["po_item_id"],
                        customer_order_id=po.get("customer_order_id") or "", floor_id=po.get("floor_id", "first-floor"),
                        supplier_id=po.get("supplier_id"),
                        supplier_name=po.get("supplier_name") or "Unassigned", customer_id=po.get("customer_id"),
                        customer_name=po.get("customer_name") or "", tile_name=item.get("name", ""),
                        series=item.get("series"), finish=item.get("finish"), size=item.get("size"), sku=item.get("sku"),
                        qty=qty, remaining_qty=0, created_by=user.id, created_by_name=user.full_name, auto_created=True,
                    )
                    await db.ready_batches.insert_one(auto_batch.dict(), session=session)
                    ready_batch_id = auto_batch.id
                    item["boxes_pending"] = float(item.get("boxes_pending") or 0) - qty

                item["boxes_dispatched"] = float(item.get("boxes_dispatched") or 0) + qty
                item["overall_status"] = derive_item_status(item["qty"], item["boxes_ready"], item["boxes_dispatched"])
                item["current_location"] = derive_current_location(item["qty"], item["boxes_ready"], item["boxes_dispatched"])
                consumed.append(TileDispatchLineConsumed(ready_batch_id=ready_batch_id, po_item_id=r["po_item_id"], qty=qty))
                chalan_items.append(TileChalanItem(
                    po_item_id=r["po_item_id"], tile_name=item.get("name", ""), series=item.get("series"),
                    finish=item.get("finish"), size=item.get("size"), sku=item.get("sku"),
                    # boxes == quantity here: pieces_per_box is free text (e.g. "4" or
                    # "BOX", same convention as the old ChalanLineItem.unit field) so it
                    # cannot be reliably multiplied into a separate numeric piece count.
                    boxes=qty, pieces_per_box=item.get("pieces_per_box"), quantity=qty,
                ))

            now = now_iso()
            dispatch_number = await next_number("dispatch", f"DSP-{year}-", collection="dispatches", session=session)
            chalan_number = await next_number("chalan", "CH-", collection="chalans", width=4, session=session)

            chalan = TileChalan(
                number=chalan_number, dispatch_id="", purchase_order_id=po_id, customer_order_id=po.get("customer_order_id") or "",
                floor_id=po.get("floor_id", "first-floor"),
                supplier_name=po.get("supplier_name") or "Unassigned", customer_name=po.get("customer_name") or "",
                customer_phone=body.destination_name and po.get("customer_phone") or "",
                delivery_address=body.destination_address, delivery_city=body.destination_city,
                reference_number=body.reference_number, items=chalan_items,
                receiver_name=body.receiver_name, sender_name=body.sender_name,
                created_by=user.id, created_by_name=user.full_name,
                generated_at=now, generated_by_name=user.full_name,
            )
            dispatch = TileDispatch(
                dispatch_number=dispatch_number, purchase_order_id=po_id, customer_order_id=po.get("customer_order_id") or "",
                floor_id=po.get("floor_id", "first-floor"),
                supplier_id=po.get("supplier_id"), supplier_name=po.get("supplier_name") or "Unassigned",
                customer_id=po.get("customer_id"), customer_name=po.get("customer_name") or "",
                ready_batches_consumed=consumed, destination_type=body.destination_type,
                destination_name=body.destination_name, destination_address=body.destination_address,
                destination_city=body.destination_city, dispatch_date=now[:10], dispatch_time=now[11:16],
                created_by=user.id, created_by_name=user.full_name, chalan_id=chalan.id,
            )
            chalan.dispatch_id = dispatch.id
            await db.chalans.insert_one(chalan.dict(), session=session)
            await db.dispatches.insert_one(dispatch.dict(), session=session)

            items = list(items_by_id.values())
            ordered_boxes = sum(float(i.get("qty") or 0) for i in items)
            dispatched_boxes = sum(float(i.get("boxes_dispatched") or 0) for i in items)
            new_status = rollup_status([i["overall_status"] for i in items])
            await db.purchase_orders.update_one(
                {"id": po_id}, {"$set": {
                    "items": items,
                    "ready_boxes": sum(float(i.get("boxes_ready") or 0) for i in items),
                    "pending_boxes": sum(float(i.get("boxes_pending") or 0) for i in items),
                    "dispatched_boxes": dispatched_boxes, "overall_status": new_status,
                    "completion_percentage": completion_percentage(ordered_boxes, dispatched_boxes),
                    "latest_dispatch_date": now, "last_supplier_activity_at": now, "updated_at": now,
                }}, session=session,
            )
            await _sync_customer_order_brand_status(po.get("customer_order_id"), po_id, new_status, session)

    await log_event(
        event_type="dispatch.created", entity_type="purchase", entity_id=po_id, actor=user,
        customer_id=po.get("customer_id"), purchase_id=po_id,
        summary=f"Dispatch {dispatch.dispatch_number} created — {len(chalan_items)} line(s)",
        payload={"dispatch_id": dispatch.id, "dispatch_number": dispatch.dispatch_number},
    )
    await log_event(
        event_type="chalan.generated", entity_type="purchase", entity_id=po_id, actor=user,
        customer_id=po.get("customer_id"), purchase_id=po_id,
        summary=f"Chalan {chalan.number} generated for Dispatch {dispatch.dispatch_number}",
        payload={"chalan_id": chalan.id, "chalan_number": chalan.number, "dispatch_id": dispatch.id},
    )
    await log_event(
        event_type="status.changed", entity_type="purchase", entity_id=po_id, actor=user,
        customer_id=po.get("customer_id"), purchase_id=po_id,
        summary=f"Status changed to {new_status}", payload={"to": new_status},
    )
    return {"po_id": po_id, "dispatch": dispatch.dict(), "chalan": chalan.dict(), "overall_status": new_status}
