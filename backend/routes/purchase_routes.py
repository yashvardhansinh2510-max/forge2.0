"""Purchase Order routes — draft, review, order, receive, dispatch.

Design notes:
  * A Purchase Order is always scoped to a single BRAND. Multi-brand quotations
    fan out into N POs, one per brand.
  * PO numbers are of the form FPO-YYYY-NNNN, globally unique across brands.
  * Status transitions are validated against ALLOWED_TRANSITIONS. Any state
    change writes a PurchaseStatusEvent AND a domain activity event.
  * Receiving materials auto-transitions status:
        any partial → partial_received
        all lines fully received → fully_received
  * PDF/exports live in a future iteration (Payments Milestone).
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_user, require_min_role
from db import db
from models import (
    PurchaseAttachment, PurchaseAttachmentCreate, PurchaseOrder, PurchaseOrderItem,
    PurchaseOrderUpdate, PurchaseReceivePayload, PurchaseStatusEvent, PurchaseStatusPayload,
    UserPublic,
)
from services.activity_log import log_event

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


# -----------------------------------------------------------------------------
# State machine
# -----------------------------------------------------------------------------
ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["awaiting_review", "ordered", "cancelled"],
    "awaiting_review": ["draft", "ordered", "cancelled"],
    "ordered": ["awaiting_supplier", "partial_received", "fully_received", "cancelled"],
    "awaiting_supplier": ["partial_received", "fully_received", "cancelled"],
    "partial_received": ["partial_received", "fully_received", "cancelled"],
    "fully_received": ["packed"],
    "packed": ["ready_for_dispatch"],
    "ready_for_dispatch": ["ready_for_dispatch"],
    "cancelled": [],
}

STATUS_LABELS = {
    "draft": "Draft",
    "awaiting_review": "Awaiting Review",
    "ordered": "Ordered",
    "awaiting_supplier": "Awaiting Supplier",
    "partial_received": "Partial Received",
    "fully_received": "Fully Received",
    "packed": "Packed",
    "ready_for_dispatch": "Ready for Dispatch",
    "cancelled": "Cancelled",
}

# Statuses shown as columns on the operational dashboard, in board order.
DASHBOARD_COLUMNS = [
    "draft", "awaiting_review", "ordered", "awaiting_supplier",
    "partial_received", "fully_received", "packed", "ready_for_dispatch",
]


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
async def _next_po_number() -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"FPO-{year}-"
    n = await db.purchase_orders.count_documents({"number": {"$regex": f"^{prefix}"}})
    return f"{prefix}{n + 1:04d}"


def _recalc_totals(items: list[PurchaseOrderItem]) -> dict:
    subtotal = 0.0
    tax_total = 0.0
    for it in items:
        gross = it.qty * it.unit_cost
        subtotal += gross
        tax_total += gross * (it.tax_pct or 0) / 100
    return {
        "subtotal": round(subtotal, 2),
        "tax_total": round(tax_total, 2),
        "grand_total": round(subtotal + tax_total, 2),
    }


def _receipt_status(items: list[dict]) -> Optional[str]:
    """Infer status transition purely from received quantities."""
    if not items:
        return None
    any_received = any(float(it.get("qty_received", 0)) > 0 for it in items)
    all_full = all(
        float(it.get("qty_received", 0)) >= float(it.get("qty", 0)) - 1e-6
        for it in items
    )
    if all_full:
        return "fully_received"
    if any_received:
        return "partial_received"
    return None


async def _apply_status_change(
    po: dict, to_status: str, user: UserPublic, note: Optional[str] = None,
) -> dict:
    """Mutates `po` (dict from Mongo), returns update patch for $set."""
    from_status = po.get("status")
    ev = PurchaseStatusEvent(
        from_status=from_status,
        to_status=to_status,
        by_user_id=user.id,
        by_user_name=user.full_name,
        note=note,
    )
    history = po.get("status_history", []) + [ev.dict()]
    patch = {
        "status": to_status,
        "status_history": history,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if to_status == "ready_for_dispatch":
        patch["delivered_at"] = datetime.now(timezone.utc).isoformat()

    await log_event(
        event_type="purchase.status_changed",
        entity_type="purchase",
        entity_id=po["id"],
        actor=user,
        customer_id=po.get("customer_id"),
        quotation_id=po.get("quotation_id"),
        purchase_id=po["id"],
        payload={"from": from_status, "to": to_status, "note": note},
        summary=f"{po.get('number')} → {STATUS_LABELS.get(to_status, to_status)}",
    )
    if to_status == "ready_for_dispatch":
        await log_event(
            event_type="purchase.dispatched",
            entity_type="purchase",
            entity_id=po["id"],
            actor=user,
            customer_id=po.get("customer_id"),
            quotation_id=po.get("quotation_id"),
            purchase_id=po["id"],
            summary=f"{po.get('number')} ready for dispatch",
        )
    return patch


# -----------------------------------------------------------------------------
# List / detail / dashboard
# -----------------------------------------------------------------------------
@router.get("/dashboard")
async def dashboard(_: UserPublic = Depends(get_current_user)):
    """Column counts + preview cards for the ops board."""
    pipeline = [
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "value": {"$sum": "$grand_total"},
        }},
    ]
    rows = await db.purchase_orders.aggregate(pipeline).to_list(50)
    by_status = {r["_id"]: {"count": r["count"], "value": round(r["value"], 2)} for r in rows}
    columns = []
    for st in DASHBOARD_COLUMNS:
        stats = by_status.get(st, {"count": 0, "value": 0})
        columns.append({
            "status": st,
            "label": STATUS_LABELS[st],
            "count": stats["count"],
            "value": stats["value"],
        })
    total_open = sum(c["value"] for c in columns if c["status"] not in ("ready_for_dispatch",))
    return {
        "columns": columns,
        "total_open_value": round(total_open, 2),
    }


@router.get("")
async def list_purchase_orders(
    status: Optional[str] = None,
    brand_id: Optional[str] = None,
    supplier_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    quotation_id: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    _: UserPublic = Depends(get_current_user),
):
    """Search POs. Free-text `q` matches PO number, customer, brand, supplier, SKU."""
    import logging
    logger = logging.getLogger("forge.purchase")
    
    query: dict = {}
    logger.info(f"list_purchase_orders called with status={status}, brand_id={brand_id}")
    
    if status and status != "all":
        query["status"] = status
    if brand_id:
        query["brand_id"] = brand_id
    if supplier_id:
        query["supplier_id"] = supplier_id
    if customer_id:
        query["customer_id"] = customer_id
    if quotation_id:
        query["quotation_id"] = quotation_id
    if q:
        term = {"$regex": q, "$options": "i"}
        query["$or"] = [
            {"number": term},
            {"customer_name": term},
            {"brand_name": term},
            {"supplier_name": term},
            {"quotation_number": term},
            {"items.sku": term},
            {"items.name": term},
        ]
    
    logger.info(f"MongoDB query: {query}")
    docs = await db.purchase_orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    logger.info(f"Found {len(docs)} POs")
    return docs


@router.get("/{po_id}", response_model=PurchaseOrder)
async def get_purchase_order(po_id: str, _: UserPublic = Depends(get_current_user)):
    doc = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return PurchaseOrder(**doc)


# -----------------------------------------------------------------------------
# Update / status / receive / attachments
# -----------------------------------------------------------------------------
@router.patch("/{po_id}", response_model=PurchaseOrder)
async def update_purchase_order(
    po_id: str,
    body: PurchaseOrderUpdate,
    user: UserPublic = Depends(require_min_role("purchase")),
):
    doc = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    patch: dict = {}
    events: list[dict] = []

    if body.supplier_id is not None and body.supplier_id != doc.get("supplier_id"):
        supplier = await db.suppliers.find_one({"id": body.supplier_id}, {"_id": 0}) if body.supplier_id else None
        patch["supplier_id"] = body.supplier_id
        patch["supplier_name"] = supplier.get("name") if supplier else body.supplier_name
        events.append({
            "event_type": "purchase.supplier_changed",
            "summary": f"Supplier set to {patch['supplier_name']}",
            "payload": {"supplier_id": body.supplier_id, "supplier_name": patch["supplier_name"]},
        })

    if body.assigned_to is not None and body.assigned_to != doc.get("assigned_to"):
        assignee = await db.users.find_one({"id": body.assigned_to}, {"_id": 0, "full_name": 1})
        patch["assigned_to"] = body.assigned_to
        patch["assigned_to_name"] = assignee.get("full_name") if assignee else None
        events.append({
            "event_type": "purchase.assigned",
            "summary": f"Assigned to {patch['assigned_to_name']}",
            "payload": {"assigned_to": body.assigned_to},
        })

    if body.internal_notes is not None and body.internal_notes != doc.get("internal_notes"):
        patch["internal_notes"] = body.internal_notes
        events.append({
            "event_type": "purchase.note_updated",
            "summary": "Internal notes updated",
            "payload": {},
        })

    if body.expected_delivery_at is not None:
        patch["expected_delivery_at"] = body.expected_delivery_at

    if body.items is not None:
        items = [i if isinstance(i, PurchaseOrderItem) else PurchaseOrderItem(**i) for i in body.items]
        patch["items"] = [i.dict() for i in items]
        patch.update(_recalc_totals(items))
        events.append({
            "event_type": "purchase.items_updated",
            "summary": f"Line items updated ({len(items)} items)",
            "payload": {"count": len(items)},
        })

    if not patch:
        return PurchaseOrder(**doc)

    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.purchase_orders.update_one({"id": po_id}, {"$set": patch})

    for ev in events:
        await log_event(
            entity_type="purchase",
            entity_id=po_id,
            actor=user,
            customer_id=doc.get("customer_id"),
            quotation_id=doc.get("quotation_id"),
            purchase_id=po_id,
            **ev,
        )

    fresh = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    return PurchaseOrder(**fresh)


@router.post("/{po_id}/status", response_model=PurchaseOrder)
async def change_status(
    po_id: str,
    body: PurchaseStatusPayload,
    user: UserPublic = Depends(require_min_role("purchase")),
):
    doc = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    cur = doc.get("status", "draft")
    if body.to_status not in ALLOWED_TRANSITIONS.get(cur, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot move from '{cur}' to '{body.to_status}'",
        )
    patch = await _apply_status_change(doc, body.to_status, user, body.note)
    await db.purchase_orders.update_one({"id": po_id}, {"$set": patch})
    fresh = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    return PurchaseOrder(**fresh)


@router.post("/{po_id}/receive", response_model=PurchaseOrder)
async def receive_items(
    po_id: str,
    body: PurchaseReceivePayload,
    user: UserPublic = Depends(require_min_role("purchase")),
):
    doc = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    items = doc.get("items", [])
    updated_items = []
    changes = []
    for it in items:
        new_recv = body.receipts.get(it["id"])
        if new_recv is not None:
            clamped = max(0.0, min(float(new_recv), float(it["qty"])))
            if abs(clamped - float(it.get("qty_received", 0))) > 1e-6:
                changes.append({"sku": it["sku"], "from": it.get("qty_received", 0), "to": clamped})
                it = {**it, "qty_received": clamped}
        updated_items.append(it)

    patch: dict = {
        "items": updated_items,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    # Auto-transition based on receipts
    inferred = _receipt_status(updated_items)
    if inferred and inferred != doc.get("status"):
        cur = doc.get("status", "draft")
        if inferred in ALLOWED_TRANSITIONS.get(cur, []) or cur in ("ordered", "awaiting_supplier", "partial_received"):
            patch.update(await _apply_status_change(doc, inferred, user, body.note))

    await db.purchase_orders.update_one({"id": po_id}, {"$set": patch})

    await log_event(
        event_type="purchase.received",
        entity_type="purchase",
        entity_id=po_id,
        actor=user,
        customer_id=doc.get("customer_id"),
        quotation_id=doc.get("quotation_id"),
        purchase_id=po_id,
        summary=(
            f"Recorded receipts on {len(changes)} lines"
            if changes else "Receipt recorded (no changes)"
        ),
        payload={"changes": changes, "note": body.note},
    )

    fresh = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    return PurchaseOrder(**fresh)


@router.post("/{po_id}/attachments", response_model=PurchaseOrder)
async def add_attachment(
    po_id: str,
    body: PurchaseAttachmentCreate,
    user: UserPublic = Depends(require_min_role("purchase")),
):
    doc = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    # Basic size guard — base64 blobs > ~4MB will slow Mongo. We accept but log.
    size = len(body.data_url or "")
    att = PurchaseAttachment(
        by_user_id=user.id,
        by_user_name=user.full_name,
        filename=body.filename,
        mime=body.mime,
        data_url=body.data_url,
        size_bytes=size,
        note=body.note,
    )
    attachments = doc.get("attachments", []) + [att.dict()]
    await db.purchase_orders.update_one(
        {"id": po_id},
        {"$set": {"attachments": attachments, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await log_event(
        event_type="purchase.attachment_added",
        entity_type="purchase",
        entity_id=po_id,
        actor=user,
        customer_id=doc.get("customer_id"),
        quotation_id=doc.get("quotation_id"),
        purchase_id=po_id,
        summary=f"Attached {body.filename}",
        payload={"filename": body.filename, "mime": body.mime, "size_bytes": size},
    )
    fresh = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    return PurchaseOrder(**fresh)


# -----------------------------------------------------------------------------
# Reference config for the frontend (status columns, transitions)
# -----------------------------------------------------------------------------
@router.get("/config/statuses")
async def status_config(_: UserPublic = Depends(get_current_user)):
    return {
        "columns": [{"value": s, "label": STATUS_LABELS[s]} for s in DASHBOARD_COLUMNS],
        "transitions": ALLOWED_TRANSITIONS,
        "labels": STATUS_LABELS,
    }
