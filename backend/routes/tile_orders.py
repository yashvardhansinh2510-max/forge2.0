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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth import floor_query, require_min_role
from db import client, db
from models import UserPublic, now_iso
from models_tile_orders import TileChalan, TileChalanItem, TileDispatch, TileDispatchLineConsumed, TileReadyBatch
from pdf_chalan import build_tile_chalan_pdf, tile_chalan_pdf_filename
from services.activity_log import log_event
from services.sequence import next_number
from services.tile_movement_log import record_movement
from services.tile_order_status import (
    ageing_band, completion_percentage, derive_current_location, derive_item_status,
    rollup_status, supplier_silent_days, waiting_days,
)

router = APIRouter(prefix="/tile-orders", tags=["tile-orders"])


class ReadyItemInput(BaseModel):
    po_item_id: str
    qty: float = Field(gt=0)


class BulkReadyBody(BaseModel):
    items: list[ReadyItemInput] = Field(min_length=1)


async def _sync_customer_order_brand_status(
    co_id: Optional[str], po_id: str, new_status: str, session, *, dispatched_boxes: float = 0.0,
) -> None:
    """Updates this PO's entry in TileCustomerOrder.brands[], then rolls the
    CustomerOrder's own overall_status/dashboard_summary up from all
    brands. Increments `version` as the defense-in-depth CAS guard the
    design doc calls for — the enclosing transaction is the primary safety
    net (see Task 6's transaction-strategy note).

    Also recomputes completion_percentage — the same class of bug Task 9
    already fixed once for supplier_analytics (a stored field that only a
    subset of write paths ever touched, so it went permanently stale/0
    everywhere else). Rather than re-querying every sibling PurchaseOrder
    for this order (which the codebase already avoids elsewhere), each
    brand entry carries its own PO's current boxes_dispatched — summed
    across brands, that's the numerator against the order's total_boxes
    (immutable, set once at placement) as the denominator, via the same
    completion_percentage() helper the write endpoints already use."""
    if not co_id:
        return
    co = await db.customer_orders.find_one({"id": co_id, "is_deleted": False}, {"_id": 0}, session=session)
    if not co:
        return
    brands = co.get("brands", [])
    for brand in brands:
        if brand.get("purchase_order_id") == po_id:
            brand["status"] = new_status
            brand["boxes_dispatched"] = dispatched_boxes
    overall = rollup_status([b.get("status", "Pending") for b in brands])
    total_dispatched = sum(float(b.get("boxes_dispatched") or 0) for b in brands)
    pct = completion_percentage(float(co.get("total_boxes") or 0), total_dispatched)
    summary = {
        "completion_percentage": pct,
        "overall_status": overall,
        "supplier_statuses": [{"supplier_name": b.get("supplier_name"), "status": b.get("status")} for b in brands],
    }
    await db.customer_orders.update_one(
        {"id": co_id, "version": co.get("version", 0)},
        {"$set": {
            "brands": brands, "overall_status": overall, "dashboard_summary": summary,
            "completion_percentage": pct,
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
            await _sync_customer_order_brand_status(
                po.get("customer_order_id"), po_id, new_status, session, dispatched_boxes=dispatched_boxes,
            )

    for batch in created_batches:
        await log_event(
            event_type="ready_batch.created", entity_type="purchase", entity_id=po_id, actor=user,
            customer_id=po.get("customer_id"), purchase_id=po_id,
            summary=f"Marked {batch['qty']:g} boxes of '{batch['tile_name']}' ready ({batch['batch_number']})",
            payload={"ready_batch_id": batch["id"], "batch_number": batch["batch_number"], "po_item_id": batch["po_item_id"], "qty": batch["qty"]},
        )
        # Material Movement Register — "Release" row. Logged after the
        # transaction commits (same place the pre-existing activity-log
        # call above already lives), one row per released line.
        await record_movement(
            movement_type="release", purchase_order_id=po_id, po_item_id=batch["po_item_id"],
            customer_order_id=po.get("customer_order_id"), floor_id=po.get("floor_id", "first-floor"),
            customer_id=po.get("customer_id"), customer_name=po.get("customer_name") or "",
            brand_id=po.get("brand_id"), brand_name=po.get("brand_name") or po.get("supplier_name") or "Unassigned",
            tile_name=batch["tile_name"], series=batch.get("series"), finish=batch.get("finish"),
            size=batch.get("size"), sku=batch.get("sku"), boxes=batch["qty"], source="Brand",
            destination="BuildCon", performed_by=user.id, performed_by_name=user.full_name,
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
    batch, more than what's Pending).

    Tracks cumulative qty already claimed per po_item_id (pending source)
    and per ready_batch_id (existing-batch source) as lines are walked, so
    that two lines in the SAME request drawing from the same pending pool
    or the same batch can't each independently pass validation against the
    same stale pre-mutation snapshot (which would double-spend/drive
    counters negative once actually applied)."""
    items_by_id = {item["id"]: item for item in po.get("items", [])}
    resolved: list[dict] = []
    warnings: list[str] = []
    claimed_pending: dict[str, float] = {}
    claimed_batch: dict[str, float] = {}
    for entry in body.items:
        item = items_by_id.get(entry.po_item_id)
        if not item:
            raise HTTPException(status_code=400, detail=f"Unknown item {entry.po_item_id}")
        if entry.ready_batch_id:
            batch = await db.ready_batches.find_one(
                {"id": entry.ready_batch_id, "is_deleted": False}, {"_id": 0}, session=session,
            )
            if not batch or batch.get("po_item_id") != entry.po_item_id:
                raise HTTPException(status_code=400, detail=f"Ready batch {entry.ready_batch_id} not found for this item")
            already_claimed = claimed_batch.get(entry.ready_batch_id, 0.0)
            remaining = float(batch.get("remaining_qty") or 0) - already_claimed
            if entry.qty > remaining + 1e-6:
                raise HTTPException(status_code=400, detail=f"Only {remaining:g} boxes remain in batch {batch['batch_number']}")
            claimed_batch[entry.ready_batch_id] = already_claimed + entry.qty
            resolved.append({"po_item_id": entry.po_item_id, "qty": entry.qty, "source": "existing", "item": item, "batch": batch})
        else:
            already_claimed = claimed_pending.get(entry.po_item_id, 0.0)
            pending = float(item.get("boxes_pending") or 0) - already_claimed
            if entry.qty > pending + 1e-6:
                raise HTTPException(status_code=400, detail=f"Only {pending:g} boxes of '{item.get('name')}' are pending")
            claimed_pending[entry.po_item_id] = already_claimed + entry.qty
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
                    # $inc (not $set off the stale in-memory snapshot) so that
                    # multiple lines against the same batch within one request
                    # — or genuinely concurrent dispatches — always decrement
                    # from the batch's true current state rather than each
                    # overwriting the other's decrement.
                    await db.ready_batches.update_one({"id": batch["id"]}, {"$inc": {"remaining_qty": -qty}}, session=session)
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
                item["overall_status"] = derive_item_status(item["qty"], float(item.get("boxes_ready") or 0), item["boxes_dispatched"])
                item["current_location"] = derive_current_location(item["qty"], float(item.get("boxes_ready") or 0), item["boxes_dispatched"])
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
            # Deliberately shares the "chalan:CH-" counter key with the old
            # chalans-nested-in-purchase_orders path (routes/purchases_tracker.py)
            # so both paths draw from one continuously-incrementing sequence.
            # collection/array_field must match that old path exactly — if a
            # missing counter doc ever triggers re-seeding from THIS call site,
            # it needs to scan where legacy CH- numbers actually live
            # (purchase_orders.chalans[].number), not the (currently empty)
            # top-level chalans collection, or it would silently restart at
            # CH-0001 and collide with already-issued numbers.
            chalan_number = await next_number(
                "chalan", "CH-", collection="purchase_orders", array_field="chalans", width=4, session=session,
            )

            chalan = TileChalan(
                number=chalan_number, dispatch_id="", purchase_order_id=po_id, customer_order_id=po.get("customer_order_id") or "",
                floor_id=po.get("floor_id", "first-floor"),
                supplier_name=po.get("supplier_name") or "Unassigned", customer_name=po.get("customer_name") or "",
                customer_phone=po.get("customer_phone") or "",
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
            await _sync_customer_order_brand_status(
                po.get("customer_order_id"), po_id, new_status, session, dispatched_boxes=dispatched_boxes,
            )

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

async def _consume_released_pool(po_id: str, po_item_id: str, qty: float, session) -> list[TileDispatchLineConsumed]:
    """FIFO-consumes `qty` boxes from this item's active Released pool
    (ready_batches with remaining_qty > 0, oldest first), $inc-ing
    remaining_qty down on each. Used by both 'Move to Godown' and 'Dispatch
    from Released' — Godown-bound boxes are still released material, just
    parked at a different BuildCon-side location, so they draw from the
    exact same batch pool a customer dispatch would."""
    batches = await db.ready_batches.find(
        {"purchase_order_id": po_id, "po_item_id": po_item_id, "remaining_qty": {"$gt": 0}, "is_deleted": False},
        {"_id": 0}, session=session,
    ).to_list(500)
    batches.sort(key=lambda b: b.get("created_at", ""))
    remaining = qty
    consumed: list[TileDispatchLineConsumed] = []
    for batch in batches:
        if remaining <= 1e-9:
            break
        take = min(remaining, float(batch.get("remaining_qty") or 0))
        if take <= 0:
            continue
        await db.ready_batches.update_one({"id": batch["id"]}, {"$inc": {"remaining_qty": -take}}, session=session)
        consumed.append(TileDispatchLineConsumed(ready_batch_id=batch["id"], po_item_id=po_item_id, qty=take))
        remaining -= take
    if remaining > 1e-6:
        raise HTTPException(status_code=400, detail=f"Only {qty - remaining:g} of {qty:g} boxes available in Released stock for this item")
    return consumed


class GodownItemInput(BaseModel):
    po_item_id: str
    qty: float = Field(gt=0)


class MoveToGodownBody(BaseModel):
    items: list[GodownItemInput] = Field(min_length=1)


@router.post("/purchase-orders/{po_id}/items/move-to-godown")
async def move_material_to_godown(
    po_id: str, body: MoveToGodownBody, user: UserPublic = Depends(require_min_role("warehouse")),
):
    """Customer-page-only action ('Move to Godown'). Moves boxes already
    Released by the brand into BuildCon's own warehouse. Never generates a
    Chalan or a Dispatch — per the workflow redesign, Release and Move to
    Godown are internal BuildCon movements; a Chalan is generated only when
    material actually leaves for the customer (see the two dispatch-from-*
    endpoints below)."""
    session = await client.start_session()
    moved_rows: list[dict] = []
    async with session:
        async with session.start_transaction():
            po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0}, session=session)
            if not po:
                raise HTTPException(status_code=404, detail="Purchase order not found")
            items_by_id = {item["id"]: item for item in po.get("items", [])}
            for entry in body.items:
                item = items_by_id.get(entry.po_item_id)
                if not item:
                    raise HTTPException(status_code=400, detail=f"Unknown item {entry.po_item_id}")
                released = float(item.get("boxes_ready") or 0)
                if entry.qty > released + 1e-6:
                    raise HTTPException(status_code=400, detail=f"Only {released:g} boxes of '{item.get('name')}' are Released")
                await _consume_released_pool(po_id, entry.po_item_id, entry.qty, session)
                item["boxes_ready"] = released - entry.qty
                item["boxes_godown"] = float(item.get("boxes_godown") or 0) + entry.qty
                item["current_location"] = derive_current_location(
                    item["qty"], item["boxes_ready"], float(item.get("boxes_dispatched") or 0),
                    any_at_godown=item["boxes_godown"] > 0,
                )
                moved_rows.append({
                    "po_item_id": entry.po_item_id, "qty": entry.qty, "tile_name": item.get("name"),
                    "series": item.get("series"), "finish": item.get("finish"), "size": item.get("size"),
                    "sku": item.get("sku"),
                })

            items = list(items_by_id.values())
            now = now_iso()
            await db.purchase_orders.update_one({"id": po_id}, {"$set": {"items": items, "updated_at": now}}, session=session)

    for row in moved_rows:
        await log_event(
            event_type="item.moved_to_godown", entity_type="purchase", entity_id=po_id, actor=user,
            customer_id=po.get("customer_id"), purchase_id=po_id,
            summary=f"Moved {row['qty']:g} boxes of '{row['tile_name']}' to Godown",
            payload={"po_item_id": row["po_item_id"], "qty": row["qty"]},
        )
        await record_movement(
            movement_type="move_to_godown", purchase_order_id=po_id, po_item_id=row["po_item_id"],
            customer_order_id=po.get("customer_order_id"), floor_id=po.get("floor_id", "first-floor"),
            customer_id=po.get("customer_id"), customer_name=po.get("customer_name") or "",
            brand_id=po.get("brand_id"), brand_name=po.get("brand_name") or po.get("supplier_name") or "Unassigned",
            tile_name=row["tile_name"], series=row.get("series"), finish=row.get("finish"), size=row.get("size"),
            sku=row.get("sku"), boxes=row["qty"], source="Released", destination="BuildCon Godown",
            performed_by=user.id, performed_by_name=user.full_name,
        )
    return {"po_id": po_id, "moved": moved_rows}


class SimpleDispatchItemInput(BaseModel):
    po_item_id: str
    qty: float = Field(gt=0)


class SimpleDispatchBody(BaseModel):
    items: list[SimpleDispatchItemInput] = Field(min_length=1)
    destination_name: Optional[str] = None
    destination_address: Optional[str] = None
    destination_city: Optional[str] = None
    reference_number: Optional[str] = None
    receiver_name: Optional[str] = None
    sender_name: Optional[str] = None


async def _commit_simple_dispatch(
    po_id: str, body: SimpleDispatchBody, source: Literal["released", "godown"], user: UserPublic,
) -> dict:
    """Shared by dispatch-from-released and dispatch-from-godown — both are
    Customer-page-only actions (per the redesign: the Brand/Supplier page's
    only action is Release; deciding Godown vs. Dispatch — and generating
    the Chalan — belongs to BuildCon on the Customer page). Always creates
    a Dispatch + immutable Chalan + PDF-ready record + a Material Movement
    Register row. Destination defaults to the customer's delivery snapshot
    on the parent CustomerOrder but can be overridden per-call."""
    session = await client.start_session()
    async with session:
        async with session.start_transaction():
            po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0}, session=session)
            if not po:
                raise HTTPException(status_code=404, detail="Purchase order not found")
            co_id = po.get("customer_order_id")
            co = None
            if co_id:
                co = await db.customer_orders.find_one({"id": co_id, "is_deleted": False}, {"_id": 0}, session=session)
            destination_name = body.destination_name or (co.get("delivery_name") if co else None) or po.get("customer_name") or ""
            destination_address = body.destination_address or (co.get("delivery_address") if co else None) or ""
            destination_city = body.destination_city or (co.get("delivery_city") if co else None) or ""

            items_by_id = {item["id"]: item for item in po.get("items", [])}
            year = datetime.now(timezone.utc).year
            consumed: list[TileDispatchLineConsumed] = []
            chalan_items: list[TileChalanItem] = []
            movement_rows: list[dict] = []

            for entry in body.items:
                item = items_by_id.get(entry.po_item_id)
                if not item:
                    raise HTTPException(status_code=400, detail=f"Unknown item {entry.po_item_id}")
                qty = entry.qty
                if source == "released":
                    released = float(item.get("boxes_ready") or 0)
                    if qty > released + 1e-6:
                        raise HTTPException(status_code=400, detail=f"Only {released:g} boxes of '{item.get('name')}' are Released")
                    consumed.extend(await _consume_released_pool(po_id, entry.po_item_id, qty, session))
                    item["boxes_ready"] = released - qty
                else:
                    godown = float(item.get("boxes_godown") or 0)
                    if qty > godown + 1e-6:
                        raise HTTPException(status_code=400, detail=f"Only {godown:g} boxes of '{item.get('name')}' are at Godown")
                    item["boxes_godown"] = godown - qty

                item["boxes_dispatched"] = float(item.get("boxes_dispatched") or 0) + qty
                item["overall_status"] = derive_item_status(item["qty"], float(item.get("boxes_ready") or 0), item["boxes_dispatched"])
                item["current_location"] = derive_current_location(
                    item["qty"], float(item.get("boxes_ready") or 0), item["boxes_dispatched"],
                    any_at_godown=float(item.get("boxes_godown") or 0) > 0,
                )
                chalan_items.append(TileChalanItem(
                    po_item_id=entry.po_item_id, tile_name=item.get("name", ""), series=item.get("series"),
                    finish=item.get("finish"), size=item.get("size"), sku=item.get("sku"),
                    boxes=qty, pieces_per_box=item.get("pieces_per_box"), quantity=qty,
                ))
                movement_rows.append({
                    "po_item_id": entry.po_item_id, "tile_name": item.get("name"), "series": item.get("series"),
                    "finish": item.get("finish"), "size": item.get("size"), "sku": item.get("sku"), "qty": qty,
                })

            now = now_iso()
            dispatch_number = await next_number("dispatch", f"DSP-{year}-", collection="dispatches", session=session)
            # Shares the "chalan:CH-" counter key with both the old
            # embedded-chalans path and the generic /dispatch endpoint above
            # — one continuously-incrementing sequence across all 3 code
            # paths, never restarts / collides.
            chalan_number = await next_number(
                "chalan", "CH-", collection="purchase_orders", array_field="chalans", width=4, session=session,
            )
            chalan = TileChalan(
                number=chalan_number, dispatch_id="", purchase_order_id=po_id, customer_order_id=co_id or "",
                floor_id=po.get("floor_id", "first-floor"), supplier_name=po.get("supplier_name") or "Unassigned",
                customer_name=po.get("customer_name") or "", customer_phone=po.get("customer_phone") or "",
                delivery_address=destination_address, delivery_city=destination_city,
                reference_number=body.reference_number, items=chalan_items,
                receiver_name=body.receiver_name, sender_name=body.sender_name,
                created_by=user.id, created_by_name=user.full_name, generated_at=now, generated_by_name=user.full_name,
            )
            dispatch = TileDispatch(
                dispatch_number=dispatch_number, purchase_order_id=po_id, customer_order_id=co_id or "",
                floor_id=po.get("floor_id", "first-floor"), supplier_id=po.get("supplier_id"),
                supplier_name=po.get("supplier_name") or "Unassigned", customer_id=po.get("customer_id"),
                customer_name=po.get("customer_name") or "", ready_batches_consumed=consumed, source=source,
                destination_type="Customer", destination_name=destination_name, destination_address=destination_address,
                destination_city=destination_city, dispatch_date=now[:10], dispatch_time=now[11:16],
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
            await _sync_customer_order_brand_status(co_id, po_id, new_status, session, dispatched_boxes=dispatched_boxes)

    movement_type = "dispatch_from_released" if source == "released" else "dispatch_from_godown"
    source_label = "Released" if source == "released" else "Godown"
    for row in movement_rows:
        await record_movement(
            movement_type=movement_type, purchase_order_id=po_id, po_item_id=row["po_item_id"],
            customer_order_id=co_id, floor_id=po.get("floor_id", "first-floor"), customer_id=po.get("customer_id"),
            customer_name=po.get("customer_name") or "", brand_id=po.get("brand_id"),
            brand_name=po.get("brand_name") or po.get("supplier_name") or "Unassigned",
            tile_name=row["tile_name"], series=row.get("series"), finish=row.get("finish"), size=row.get("size"),
            sku=row.get("sku"), boxes=row["qty"], source=source_label, destination=destination_name,
            dispatch_id=dispatch.id, dispatch_number=dispatch.dispatch_number, chalan_id=chalan.id,
            chalan_number=chalan.number, performed_by=user.id, performed_by_name=user.full_name,
        )
    await log_event(
        event_type="dispatch.created", entity_type="purchase", entity_id=po_id, actor=user,
        customer_id=po.get("customer_id"), purchase_id=po_id,
        summary=f"Dispatch {dispatch.dispatch_number} created from {source_label} — {len(chalan_items)} line(s)",
        payload={"dispatch_id": dispatch.id, "dispatch_number": dispatch.dispatch_number, "source": source},
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


@router.post("/purchase-orders/{po_id}/dispatch-from-released")
async def dispatch_from_released(
    po_id: str, body: SimpleDispatchBody, user: UserPublic = Depends(require_min_role("warehouse")),
):
    return await _commit_simple_dispatch(po_id, body, "released", user)


@router.post("/purchase-orders/{po_id}/dispatch-from-godown")
async def dispatch_from_godown(
    po_id: str, body: SimpleDispatchBody, user: UserPublic = Depends(require_min_role("warehouse")),
):
    return await _commit_simple_dispatch(po_id, body, "godown", user)




@router.get("/chalans/{chalan_id}/pdf")
async def chalan_pdf(chalan_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    chalan = await db.chalans.find_one(floor_query(user, {"id": chalan_id, "is_deleted": False}), {"_id": 0})
    if not chalan:
        raise HTTPException(status_code=404, detail="Chalan not found")
    company = await db.settings.find_one({"key": "company"}, {"_id": 0}) or {}
    pdf_settings = await db.settings.find_one({"key": "pdf"}, {"_id": 0}) or {}
    branding = {
        "footer_company_name": pdf_settings.get("footer_company_name") or company.get("name") or "Buildcon House",
        "footer_phone": pdf_settings.get("footer_phone") or company.get("phone") or "",
    }
    pdf_bytes = build_tile_chalan_pdf(chalan, branding)
    filename = tile_chalan_pdf_filename(chalan, chalan.get("customer_name", "Customer"))
    return StreamingResponse(
        iter([pdf_bytes]), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


class GodownReceivedBody(BaseModel):
    note: Optional[str] = None


@router.post("/dispatches/{dispatch_id}/godown-received")
async def mark_dispatch_godown_received(
    dispatch_id: str, body: GodownReceivedBody, user: UserPublic = Depends(require_min_role("warehouse")),
):
    dispatch = await db.dispatches.find_one(floor_query(user, {"id": dispatch_id, "is_deleted": False}), {"_id": 0})
    if not dispatch:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if dispatch.get("godown_received_at"):
        raise HTTPException(status_code=400, detail="Already marked received at Godown")

    now = now_iso()
    cas_result = await db.dispatches.update_one(
        {"id": dispatch_id, "godown_received_at": None},
        {"$set": {
            "godown_received_at": now, "godown_received_by": user.id,
            "godown_received_by_name": user.full_name, "updated_at": now,
        }},
    )
    if cas_result.matched_count == 0:
        raise HTTPException(status_code=409, detail={"error": "concurrent_modification", "message": "This dispatch was just updated — refresh and try again"})

    po = await db.purchase_orders.find_one(floor_query(user, {"id": dispatch["purchase_order_id"]}), {"_id": 0})
    if po:
        touched_item_ids = {c["po_item_id"] for c in dispatch.get("ready_batches_consumed", [])}
        items = po.get("items", [])
        for item in items:
            if item["id"] in touched_item_ids:
                item["current_location"] = derive_current_location(
                    item["qty"], float(item.get("boxes_ready") or 0), float(item.get("boxes_dispatched") or 0), any_at_godown=True,
                )
        await db.purchase_orders.update_one({"id": po["id"]}, {"$set": {"items": items, "updated_at": now}})

    await log_event(
        event_type="dispatch.godown_received", entity_type="purchase", entity_id=dispatch["purchase_order_id"], actor=user,
        customer_id=dispatch.get("customer_id"), purchase_id=dispatch["purchase_order_id"],
        summary=f"Dispatch {dispatch['dispatch_number']} received at Buildcon Godown" + (f" · {body.note}" if body.note else ""),
        payload={"dispatch_id": dispatch_id},
    )
    return {"dispatch_id": dispatch_id, "godown_received_at": now}


_STATUS_TO_KPI_KEY = {
    "Pending": "pending", "Ready": "ready", "Partially Dispatched": "partially_dispatched",
    "Dispatched": "completed", "Delivered": "completed",
}


@router.get("/suppliers")
async def list_suppliers(user: UserPublic = Depends(require_min_role("sales"))):
    pos = await db.purchase_orders.find(floor_query(user, {"customer_order_id": {"$ne": None}}), {"_id": 0}).to_list(5000)
    grouped: dict[str, dict] = {}
    for po in pos:
        key = po.get("supplier_id") or "unassigned"
        bucket = grouped.setdefault(key, {
            "supplier_id": po.get("supplier_id"), "supplier_name": po.get("supplier_name") or "Unassigned",
            "active_orders": 0, "max_supplier_silent_days": 0,
        })
        if po.get("overall_status") != "Delivered":
            bucket["active_orders"] += 1
        silent = supplier_silent_days(po.get("last_supplier_activity_at"), po["created_at"])
        bucket["max_supplier_silent_days"] = max(bucket["max_supplier_silent_days"], silent)
    suppliers = sorted(grouped.values(), key=lambda g: -g["max_supplier_silent_days"])
    return {"suppliers": suppliers}


@router.get("/brands")
async def list_brands(user: UserPublic = Depends(require_min_role("sales"))):
    """Tile Orders 'Brands' tab landing — one card per Brand (Qutone,
    Dimore, Kajaria…), NOT per dealer/supplier company. A brand and its
    supplier can differ (Supplier.name is 'a dealership we buy from,
    normally one per brand but not strict') — grouping here is on
    PurchaseOrder.brand_id/brand_name, which is set once per-brand at
    order-placement time (services/domain_outbox.py), so this always
    matches the brand the customer actually ordered, never the dealer."""
    pos = await db.purchase_orders.find(floor_query(user, {"customer_order_id": {"$ne": None}}), {"_id": 0}).to_list(5000)
    grouped: dict[str, dict] = {}
    for po in pos:
        key = po.get("brand_id") or "unassigned"
        bucket = grouped.setdefault(key, {
            "brand_id": po.get("brand_id"), "brand_name": po.get("brand_name") or "Unassigned",
            "active_orders": 0, "max_supplier_silent_days": 0,
        })
        if po.get("overall_status") != "Delivered":
            bucket["active_orders"] += 1
        silent = supplier_silent_days(po.get("last_supplier_activity_at"), po["created_at"])
        bucket["max_supplier_silent_days"] = max(bucket["max_supplier_silent_days"], silent)
    brands = sorted(grouped.values(), key=lambda g: g["brand_name"])
    return {"brands": brands}


@router.get("/brands/{brand_id}/orders")
async def brand_orders(
    brand_id: str, page: int = 1, page_size: int = 20, sort: str = "waiting_desc",
    status: Optional[str] = None, search: Optional[str] = None,
    user: UserPublic = Depends(require_min_role("sales")),
):
    """Brand Detail page — this brand's Customer Orders only, one row per
    PO. Mirrors supplier_orders() above but grouped by brand_id, and adds
    `arrival_date` (the date this order was placed with the brand — there's
    no separate 'expected arrival' field on PurchaseOrder today, so this is
    order_date) + `boxes_released`/`boxes_remaining` for the Ordered/
    Released/Remaining columns the Brand page shows."""
    filters: dict = {"brand_id": brand_id}
    if status:
        filters["overall_status"] = status
    if search:
        filters["$or"] = [
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"number": {"$regex": search, "$options": "i"}},
        ]
    all_pos = await db.purchase_orders.find(floor_query(user, filters), {"_id": 0}).to_list(5000)

    kpi = {"orders": len(all_pos), "pending": 0, "ready": 0, "partially_dispatched": 0, "completed": 0,
           "boxes_remaining": 0.0, "boxes_released": 0.0, "boxes_dispatched": 0.0, "oldest_pending_days": 0}
    for po in all_pos:
        kpi[_STATUS_TO_KPI_KEY.get(po.get("overall_status"), "pending")] += 1
        kpi["boxes_remaining"] += float(po.get("pending_boxes") or 0)
        kpi["boxes_released"] += float(po.get("ready_boxes") or 0)
        kpi["boxes_dispatched"] += float(po.get("dispatched_boxes") or 0)
        if po.get("overall_status") == "Pending":
            kpi["oldest_pending_days"] = max(kpi["oldest_pending_days"], waiting_days(po["created_at"]))

    rows = []
    for po in all_pos:
        days = waiting_days(po["created_at"])
        total_boxes = sum(float(i.get("qty") or 0) for i in po.get("items", []))
        boxes_released = sum(float(i.get("boxes_ready") or 0) for i in po.get("items", []))
        boxes_remaining = sum(float(i.get("boxes_pending") or 0) for i in po.get("items", []))
        rows.append({
            "po_id": po["id"], "po_number": po.get("number"), "customer_id": po.get("customer_id"),
            "customer_name": po.get("customer_name"), "order_date": po.get("created_at"),
            "arrival_date": po.get("created_at"), "waiting_days": days, "ageing_band": ageing_band(days),
            "total_products": len(po.get("items", [])), "total_boxes": total_boxes,
            "boxes_released": boxes_released, "boxes_remaining": boxes_remaining,
            "overall_status": po.get("overall_status"), "completion_percentage": po.get("completion_percentage"),
        })
    rows.sort(key=lambda r: r["waiting_days"], reverse=(sort != "waiting_asc"))
    start = (page - 1) * page_size
    return {"kpi": kpi, "orders": rows[start:start + page_size], "page": page, "page_size": page_size, "total": len(rows)}


@router.get("/purchase-orders/{po_id}")
async def purchase_order_detail(po_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    # Delivery snapshot lives on the parent TileCustomerOrder (captured once
    # at placement time by domain_outbox.py's _handle_order_placed), not on
    # the PurchaseOrder itself — a Supplier-side dispatch still needs it to
    # fill in the (otherwise permanently blank) immutable Chalan's delivery
    # address/city. Defaults to "" only if there's no linked CustomerOrder
    # (e.g. a non-tiles PO) or it can't be found.
    delivery_name = delivery_phone = delivery_address = delivery_city = ""
    co_id = po.get("customer_order_id")
    if co_id:
        co = await db.customer_orders.find_one({"id": co_id, "is_deleted": False}, {"_id": 0})
        if co:
            delivery_name = co.get("delivery_name") or ""
            delivery_phone = co.get("delivery_phone") or ""
            delivery_address = co.get("delivery_address") or ""
            delivery_city = co.get("delivery_city") or ""
    return {
        "id": po["id"], "number": po.get("number"), "customer_name": po.get("customer_name"),
        "supplier_name": po.get("supplier_name"), "brand_id": po.get("brand_id"), "brand_name": po.get("brand_name"),
        "overall_status": po.get("overall_status"),
        "delivery_name": delivery_name, "delivery_phone": delivery_phone,
        "delivery_address": delivery_address, "delivery_city": delivery_city,
        "items": [{
            "id": item["id"], "name": item.get("name"), "series": item.get("series"), "finish": item.get("finish"),
            "size": item.get("size"), "sku": item.get("sku"), "qty": item.get("qty"),
            "boxes_ready": item.get("boxes_ready"), "boxes_godown": item.get("boxes_godown") or 0,
            "boxes_dispatched": item.get("boxes_dispatched"),
            "boxes_pending": item.get("boxes_pending"), "current_location": item.get("current_location"),
            "overall_status": item.get("overall_status"),
        } for item in po.get("items", [])],
    }


@router.get("/suppliers/{supplier_id}/orders")
async def supplier_orders(
    supplier_id: str, page: int = 1, page_size: int = 20, sort: str = "waiting_desc",
    status: Optional[str] = None, search: Optional[str] = None,
    user: UserPublic = Depends(require_min_role("sales")),
):
    filters: dict = {"supplier_id": supplier_id}
    if status:
        filters["overall_status"] = status
    if search:
        filters["$or"] = [
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"number": {"$regex": search, "$options": "i"}},
        ]
    all_pos = await db.purchase_orders.find(floor_query(user, filters), {"_id": 0}).to_list(5000)

    kpi = {"orders": len(all_pos), "pending": 0, "ready": 0, "partially_dispatched": 0, "completed": 0,
           "boxes_pending": 0.0, "boxes_ready": 0.0, "boxes_dispatched": 0.0, "oldest_pending_days": 0}
    for po in all_pos:
        kpi[_STATUS_TO_KPI_KEY.get(po.get("overall_status"), "pending")] += 1
        kpi["boxes_pending"] += float(po.get("pending_boxes") or 0)
        kpi["boxes_ready"] += float(po.get("ready_boxes") or 0)
        kpi["boxes_dispatched"] += float(po.get("dispatched_boxes") or 0)
        if po.get("overall_status") == "Pending":
            kpi["oldest_pending_days"] = max(kpi["oldest_pending_days"], waiting_days(po["created_at"]))

    rows = []
    for po in all_pos:
        days = waiting_days(po["created_at"])
        rows.append({
            "po_id": po["id"], "po_number": po.get("number"), "customer_id": po.get("customer_id"),
            "customer_name": po.get("customer_name"), "order_date": po.get("created_at"),
            "waiting_days": days, "ageing_band": ageing_band(days),
            "total_products": len(po.get("items", [])), "total_boxes": sum(float(i.get("qty") or 0) for i in po.get("items", [])),
            "overall_status": po.get("overall_status"), "completion_percentage": po.get("completion_percentage"),
        })
    rows.sort(key=lambda r: r["waiting_days"], reverse=(sort != "waiting_asc"))
    start = (page - 1) * page_size
    return {"kpi": kpi, "orders": rows[start:start + page_size], "page": page, "page_size": page_size, "total": len(rows)}


@router.get("/suppliers/{supplier_id}/analytics")
async def supplier_analytics(supplier_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    pos = await db.purchase_orders.find(floor_query(user, {"supplier_id": supplier_id}), {"_id": 0}).to_list(5000)
    if not pos:
        return {"orders": 0, "waiting_avg_days": 0, "ready_time_avg_days": 0, "dispatch_time_avg_days": 0, "fulfilment_time_avg_days": 0, "oldest_pending_days": 0, "completion_percentage_avg": 0}

    ready_times, dispatch_times, fulfilment_times = [], [], []
    oldest_pending = 0
    for po in pos:
        created = po["created_at"]
        if po.get("overall_status") == "Pending":
            oldest_pending = max(oldest_pending, waiting_days(created))
        if po.get("latest_ready_date"):
            ready_times.append(waiting_days(created) - waiting_days(po["latest_ready_date"]))
        if po.get("latest_ready_date") and po.get("latest_dispatch_date"):
            dispatch_times.append(waiting_days(po["latest_ready_date"]) - waiting_days(po["latest_dispatch_date"]))
        if po.get("overall_status") in ("Dispatched", "Delivered"):
            fulfilment_times.append(waiting_days(created) - waiting_days(po.get("latest_dispatch_date") or created))

    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 1) if values else 0.0

    return {
        "orders": len(pos),
        "waiting_avg_days": _avg([waiting_days(po["created_at"]) for po in pos]),
        "ready_time_avg_days": _avg(ready_times),
        "dispatch_time_avg_days": _avg(dispatch_times),
        "fulfilment_time_avg_days": _avg(fulfilment_times),
        "oldest_pending_days": oldest_pending,
        # Computed live from each PO's ordered/dispatched box counts (the
        # same completion_percentage() used by the write endpoints above)
        # rather than trusted off po["completion_percentage"] — that stored
        # field is a write-time snapshot and this view should reflect the
        # PO's current box counters even if something upstream left it stale.
        "completion_percentage_avg": _avg([
            completion_percentage(
                sum(float(i.get("qty") or 0) for i in po.get("items", [])),
                float(po.get("dispatched_boxes") or 0),
            )
            for po in pos
        ]),
    }


@router.get("/customer-orders")
async def list_customer_orders(
    page: int = 1, page_size: int = 20, sort: str = "waiting_desc",
    status: Optional[str] = None, search: Optional[str] = None,
    user: UserPublic = Depends(require_min_role("sales")),
):
    filters: dict = {"is_deleted": False}
    if status:
        filters["overall_status"] = status
    if search:
        filters["$or"] = [
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"customer_phone": {"$regex": search, "$options": "i"}},
            {"number": {"$regex": search, "$options": "i"}},
        ]
    docs = await db.customer_orders.find(floor_query(user, filters), {"_id": 0}).to_list(5000)
    rows = []
    for co in docs:
        days = waiting_days(co["created_at"])
        rows.append({
            "id": co["id"], "number": co.get("number"), "customer_name": co.get("customer_name"),
            "customer_phone": co.get("customer_phone"), "order_date": co.get("created_at"),
            "waiting_days": days, "ageing_band": ageing_band(days), "brands": co.get("brands", []),
            "total_products": co.get("total_products"), "total_boxes": co.get("total_boxes"),
            "total_value": co.get("total_value"), "overall_status": co.get("overall_status"),
            "completion_percentage": co.get("completion_percentage"),
        })
    rows.sort(key=lambda r: r["waiting_days"], reverse=(sort != "waiting_asc"))
    start = (page - 1) * page_size
    return {"orders": rows[start:start + page_size], "page": page, "page_size": page_size, "total": len(rows)}


@router.get("/customer-orders/{co_id}")
async def customer_order_detail(co_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    co = await db.customer_orders.find_one(floor_query(user, {"id": co_id, "is_deleted": False}), {"_id": 0})
    if not co:
        raise HTTPException(status_code=404, detail="Customer order not found")
    pos = await db.purchase_orders.find(floor_query(user, {"customer_order_id": co_id}), {"_id": 0}).to_list(50)
    suppliers = [{
        "purchase_order_id": po["id"], "supplier_name": po.get("supplier_name") or "Unassigned",
        "brand_id": po.get("brand_id"), "brand_name": po.get("brand_name") or po.get("supplier_name") or "Unassigned",
        "overall_status": po.get("overall_status"),
        "items": [{
            "po_item_id": item["id"], "tile_name": item.get("name"), "series": item.get("series"),
            "finish": item.get("finish"), "size": item.get("size"),
            "boxes_ordered": item.get("qty"), "boxes_ready": item.get("boxes_ready"),
            "boxes_godown": item.get("boxes_godown") or 0,
            "boxes_dispatched": item.get("boxes_dispatched"), "boxes_pending": item.get("boxes_pending"),
            "current_location": item.get("current_location"), "overall_status": item.get("overall_status"),
        } for item in po.get("items", [])],
    } for po in pos]
    days = waiting_days(co["created_at"])
    return {
        "summary": {
            "id": co["id"], "number": co.get("number"), "customer_name": co.get("customer_name"),
            "order_date": co.get("created_at"), "brand_count": len(co.get("brands", [])),
            "total_products": co.get("total_products"), "total_boxes": co.get("total_boxes"),
            "completion_percentage": co.get("completion_percentage"), "waiting_days": days,
            "ageing_band": ageing_band(days), "overall_status": co.get("overall_status"),
        },
        "suppliers": suppliers,
    }


@router.get("/customer-orders/{co_id}/timeline")
async def customer_order_timeline(co_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    co = await db.customer_orders.find_one(floor_query(user, {"id": co_id, "is_deleted": False}), {"_id": 0, "id": 1})
    if not co:
        raise HTTPException(status_code=404, detail="Customer order not found")
    pos = await db.purchase_orders.find(floor_query(user, {"customer_order_id": co_id}), {"_id": 0, "id": 1}).to_list(50)
    po_ids = [po["id"] for po in pos]
    events = await db.activity_events.find(
        {"$or": [{"entity_type": "tile_customer_order", "entity_id": co_id}, {"purchase_id": {"$in": po_ids}}]}, {"_id": 0},
    ).to_list(500)
    events.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return {"events": events}


def _dispatch_status(dispatch: dict) -> str:
    if dispatch.get("delivered_at"):
        return "Delivered"
    if dispatch.get("godown_received_at"):
        return "At Godown"
    return "Dispatched"


@router.get("/dispatches")
async def list_dispatches(
    customer_id: Optional[str] = None, brand_id: Optional[str] = None, product: Optional[str] = None,
    dispatch_number: Optional[str] = None, chalan_number: Optional[str] = None, status: Optional[str] = None,
    date_from: Optional[str] = None, date_to: Optional[str] = None, search: Optional[str] = None,
    page: int = 1, page_size: int = 50, sort: str = "date_desc",
    user: UserPublic = Depends(require_min_role("sales")),
):
    """Dispatch List — operational, dispatch-only view (Tile Orders workflow
    redesign, 2026-08). Every row is ONE dispatched product line — never a
    Release or Move-to-Godown event (those only ever appear on the
    Material Movement Register, see list_material_movements above). Built
    from TileDispatch + its 1:1 TileChalan, one row per Chalan line item."""
    filters: dict = {"is_deleted": False}
    if customer_id:
        filters["customer_id"] = customer_id
    if dispatch_number:
        filters["dispatch_number"] = {"$regex": dispatch_number, "$options": "i"}
    if date_from or date_to:
        date_filter: dict = {}
        if date_from:
            date_filter["$gte"] = date_from
        if date_to:
            date_filter["$lte"] = date_to
        filters["dispatch_date"] = date_filter
    dispatches = await db.dispatches.find(floor_query(user, filters), {"_id": 0}).to_list(5000)
    chalan_ids = [d["chalan_id"] for d in dispatches]
    chalans = await db.chalans.find(
        floor_query(user, {"id": {"$in": chalan_ids}, "is_deleted": False}), {"_id": 0},
    ).to_list(len(chalan_ids) + 5)
    chalan_by_id = {c["id"]: c for c in chalans}

    # TileDispatch itself carries no brand — brand lives on the
    # PurchaseOrder it was raised against (PurchaseOrder.brand_id/brand_name),
    # reachable one hop away via dispatch["purchase_order_id"]. Resolved here
    # so the `brand_id` filter/column below has something real to use.
    po_ids = [d["purchase_order_id"] for d in dispatches]
    purchase_orders = await db.purchase_orders.find(
        floor_query(user, {"id": {"$in": po_ids}}), {"_id": 0, "id": 1, "brand_id": 1, "brand_name": 1},
    ).to_list(len(po_ids) + 5)
    brand_by_po_id = {po["id"]: (po.get("brand_id"), po.get("brand_name")) for po in purchase_orders}

    rows = []
    for dispatch in dispatches:
        dispatch_status = _dispatch_status(dispatch)
        if status and status != dispatch_status:
            continue
        this_brand_id, this_brand_name = brand_by_po_id.get(dispatch["purchase_order_id"], (None, None))
        if brand_id and this_brand_id != brand_id:
            continue
        chalan = chalan_by_id.get(dispatch["chalan_id"], {})
        if chalan_number and chalan_number.lower() not in (chalan.get("number") or "").lower():
            continue
        source_label = "Godown" if dispatch.get("source") == "godown" else "Released"
        for line in chalan.get("items", []):
            if product and product.lower() not in (line.get("tile_name") or "").lower():
                continue
            row = {
                "dispatch_id": dispatch.get("id"), "dispatch_number": dispatch.get("dispatch_number"),
                "dispatch_date": dispatch.get("dispatch_date"),
                "customer_id": dispatch.get("customer_id"), "customer_name": dispatch.get("customer_name"),
                "customer_order_id": dispatch.get("customer_order_id"),
                "brand_id": this_brand_id, "brand_name": this_brand_name or dispatch.get("supplier_name") or "Unassigned",
                "tile_name": line.get("tile_name"), "tile_size": line.get("size"), "boxes": line.get("boxes"),
                "source": source_label,
                "chalan_id": chalan.get("id"), "chalan_number": chalan.get("number"),
                "vehicle_number": chalan.get("vehicle_number"), "driver_name": chalan.get("driver_name"),
                "status": dispatch_status, "performed_by_name": dispatch.get("created_by_name"),
            }
            if search:
                haystack = " ".join(str(row.get(k) or "") for k in (
                    "customer_name", "brand_name", "tile_name", "dispatch_number", "chalan_number",
                )).lower()
                if search.lower() not in haystack:
                    continue
            rows.append(row)
    rows.sort(key=lambda r: r["dispatch_date"] or "", reverse=(sort != "date_asc"))
    start = (page - 1) * page_size
    return {"rows": rows[start:start + page_size], "page": page, "page_size": page_size, "total": len(rows)}


@router.get("/items/{item_id}/history")
async def item_history(item_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    ready_batches = await db.ready_batches.find(
        floor_query(user, {"po_item_id": item_id, "is_deleted": False}), {"_id": 0},
    ).to_list(200)
    dispatches = await db.dispatches.find(
        floor_query(user, {"ready_batches_consumed.po_item_id": item_id, "is_deleted": False}), {"_id": 0},
    ).to_list(200)
    events = [{"kind": "ready_batch", "at": rb.get("created_at"), "detail": rb} for rb in ready_batches]
    events += [{"kind": "dispatch", "at": d.get("created_at"), "detail": d} for d in dispatches]
    events.sort(key=lambda e: e["at"] or "", reverse=True)
    return {"item_id": item_id, "events": events}


@router.get("/dashboard")
async def tile_orders_dashboard(user: UserPublic = Depends(require_min_role("sales"))):
    pos = await db.purchase_orders.find(floor_query(user, {"customer_order_id": {"$ne": None}}), {"_id": 0}).to_list(5000)
    today = now_iso()[:10]
    dispatched_today = await db.dispatches.find(floor_query(user, {"dispatch_date": today, "is_deleted": False}), {"_id": 0}).to_list(2000)
    delivered_today = [d for d in dispatched_today if (d.get("delivered_at") or "")[:10] == today]
    customer_orders = await db.customer_orders.find(floor_query(user, {"is_deleted": False}), {"_id": 0}).to_list(5000)

    pending = sum(1 for po in pos if po.get("overall_status") == "Pending")
    ready = sum(1 for po in pos if po.get("overall_status") == "Ready")
    waiting_over_15 = sum(1 for co in customer_orders if waiting_days(co["created_at"]) > 15)
    boxes_ordered = sum(float(i.get("qty") or 0) for po in pos for i in po.get("items", []))
    boxes_pending = sum(float(po.get("pending_boxes") or 0) for po in pos)
    revenue = sum(float(co.get("total_value") or 0) for co in customer_orders)

    return {
        "customer_orders": len(customer_orders), "supplier_orders": len(pos),
        "dispatched_today": len(dispatched_today), "delivered_today": len(delivered_today),
        "pending": pending, "ready": ready, "waiting_over_15_days": waiting_over_15,
        "boxes_ordered": boxes_ordered, "boxes_pending": boxes_pending, "revenue": round(revenue, 2),
    }


@router.get("/purchase-orders/{po_id}/items/{item_id}/ready-batches")
async def item_ready_batches(po_id: str, item_id: str, user: UserPublic = Depends(require_min_role("warehouse"))):
    batches = await db.ready_batches.find(
        {"purchase_order_id": po_id, "po_item_id": item_id, "remaining_qty": {"$gt": 0}, "is_deleted": False}, {"_id": 0},
    ).to_list(200)
    batches.sort(key=lambda b: b.get("created_at", ""))
    return {"batches": batches}


@router.get("/movements")
async def list_material_movements(
    customer_id: Optional[str] = None, brand_id: Optional[str] = None, movement_type: Optional[str] = None,
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    chalan_number: Optional[str] = None, dispatch_number: Optional[str] = None, search: Optional[str] = None,
    page: int = 1, page_size: int = 50,
    user: UserPublic = Depends(require_min_role("sales")),
):
    """Material Movement Register — the permanent, chronological audit
    trail of every box's journey (Order Created → Release → Move to
    Godown → Dispatch from Released/Godown → Delivered). One immutable row
    per event, written transactionally by services/tile_movement_log.py at
    the moment each action happens — never reconstructed here from other
    collections, so this is a straight filtered read."""
    filters: dict = {"is_deleted": False}
    if customer_id:
        filters["customer_id"] = customer_id
    if brand_id:
        filters["brand_id"] = brand_id
    if movement_type:
        filters["movement_type"] = movement_type
    if chalan_number:
        filters["chalan_number"] = {"$regex": chalan_number, "$options": "i"}
    if dispatch_number:
        filters["dispatch_number"] = {"$regex": dispatch_number, "$options": "i"}
    if date_from or date_to:
        date_filter: dict = {}
        if date_from:
            date_filter["$gte"] = date_from
        if date_to:
            date_filter["$lte"] = date_to + "T23:59:59.999999"
        filters["created_at"] = date_filter
    if search:
        filters["$or"] = [
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"brand_name": {"$regex": search, "$options": "i"}},
            {"tile_name": {"$regex": search, "$options": "i"}},
            {"sku": {"$regex": search, "$options": "i"}},
            {"chalan_number": {"$regex": search, "$options": "i"}},
            {"dispatch_number": {"$regex": search, "$options": "i"}},
        ]
    rows = await db.material_movements.find(floor_query(user, filters), {"_id": 0}).to_list(20000)
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    start = (page - 1) * page_size
    return {"rows": rows[start:start + page_size], "page": page, "page_size": page_size, "total": len(rows)}

