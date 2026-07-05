"""Purchases — Material Tracker.

A per-LINE-ITEM lifecycle tracker built on top of the PO document store.

Each PO line item flows through 6 stages:
    order_in_company → company_billing → in_box → dispatched → in_transit → delivered

Endpoints:
    GET  /purchases/items                     — flat cross-PO items list
    GET  /purchases/brands                    — brand facets w/ counts
    GET  /purchases/customers                 — customer facets w/ counts
    GET  /purchases/stages                    — stage catalog + counts
    GET  /purchases/dispatch-record           — history for dispatched+ stages
    GET  /purchases/settings                  — {sla_days}
    POST /purchases/settings                  — update SLA
    POST /purchases/items/{item_id}/move      — advance a single item
    POST /purchases/items/bulk-move           — advance many items in one call
    POST /purchases/items/{item_id}/transfer  — reduce qty on source, create
                                                new PO for destination customer
    GET  /purchases/export.xlsx               — filtered .xlsx export

The tracker does NOT concern itself with taxes — Forge uses final prices only.
"""
from __future__ import annotations
import io
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, Field

from auth import get_current_user, require_min_role
from db import db
from models import (
    PurchaseOrder, PurchaseOrderItem, PurchaseStageEvent, PurchaseStatusEvent,
    PURCHASE_STAGES, PurchaseStage, UserPublic, now_iso,
)
from services.activity_log import log_event

router = APIRouter(prefix="/purchases", tags=["purchases"])


# =============================================================================
# Stage catalog — the ONE source of truth used by both backend + frontend.
# =============================================================================
STAGE_LABELS: dict[str, str] = {
    "order_in_company": "Order in Company",
    "company_billing":  "Company Billing",
    "in_box":           "In Box",
    "dispatched":       "Dispatched",
    "in_transit":       "In Transit",
    "delivered":        "Delivered",
}

# UI tones aligned with the reference (light-mode badges).
STAGE_TONES: dict[str, dict[str, str]] = {
    "order_in_company": {"bg": "#FFEDD5", "fg": "#9A3412"},   # amber
    "company_billing":  {"bg": "#FEF3C7", "fg": "#92400E"},   # yellow
    "in_box":           {"bg": "#DBEAFE", "fg": "#1E40AF"},   # blue
    "dispatched":       {"bg": "#DCFCE7", "fg": "#166534"},   # green
    "in_transit":       {"bg": "#E9D5FF", "fg": "#6B21A8"},   # purple
    "delivered":        {"bg": "#D1FAE5", "fg": "#065F46"},   # emerald
}

EARLY_STAGES = ("order_in_company", "company_billing", "in_box")
DISPATCH_STAGES = ("dispatched", "in_transit", "delivered")

DEFAULT_SLA_DAYS = 7
SETTINGS_KEY = "purchases_tracker"


# =============================================================================
# Settings — data-driven Blocked SLA (default 7d, configurable)
# =============================================================================
class TrackerSettings(BaseModel):
    sla_days: int = Field(default=DEFAULT_SLA_DAYS, ge=1, le=365)


async def _load_settings() -> TrackerSettings:
    doc = await db.settings.find_one({"key": SETTINGS_KEY}, {"_id": 0})
    if not doc:
        return TrackerSettings()
    return TrackerSettings(**{k: v for k, v in doc.items() if k in TrackerSettings.__fields__})


@router.get("/settings", response_model=TrackerSettings)
async def get_settings(_: UserPublic = Depends(get_current_user)):
    return await _load_settings()


@router.post("/settings", response_model=TrackerSettings)
async def update_settings(
    body: TrackerSettings,
    user: UserPublic = Depends(require_min_role("manager")),
):
    await db.settings.update_one(
        {"key": SETTINGS_KEY},
        {"$set": {
            "key": SETTINGS_KEY,
            "sla_days": int(body.sla_days),
            "updated_at": now_iso(),
            "updated_by": user.id,
            "updated_by_name": user.full_name,
        }},
        upsert=True,
    )
    await log_event(
        event_type="purchase.settings.updated",
        entity_type="settings", entity_id=SETTINGS_KEY, actor=user,
        summary=f"Purchases SLA set to {body.sla_days} days",
        payload={"sla_days": body.sla_days},
    )
    return body


# =============================================================================
# Helpers
# =============================================================================
def _iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.isoformat()


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Support trailing Z
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _age_days(iso_ts: Optional[str]) -> Optional[int]:
    dt = _parse_iso(iso_ts)
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (now - dt).days)


def _flatten_item(po: dict, it: dict, sla_days: int) -> dict:
    """Materialize a single tracker row from a PO doc + its item sub-doc."""
    stage = it.get("stage") or "order_in_company"
    last_moved_at = it.get("last_moved_at") or po.get("created_at")
    age = _age_days(last_moved_at) or 0
    blocked = (stage in EARLY_STAGES) and (age >= sla_days)
    return {
        "item_id": it["id"],
        "po_id": po["id"],
        "po_number": po.get("number"),
        "quotation_id": po.get("quotation_id"),
        "quotation_number": po.get("quotation_number"),
        "quotation_line_id": it.get("quotation_line_id"),
        "product_id": it.get("product_id"),
        "sku": it.get("sku"),
        "name": it.get("name"),
        "image": it.get("image"),
        "customer_id": it.get("customer_id") or po.get("customer_id"),
        "customer_name": it.get("customer_name") or po.get("customer_name"),
        "brand_id": it.get("brand_id") or po.get("brand_id"),
        "brand_name": it.get("brand_name") or po.get("brand_name"),
        "stage": stage,
        "stage_label": STAGE_LABELS.get(stage, stage),
        "stage_tone": STAGE_TONES.get(stage, {"bg": "#F4F4F5", "fg": "#3F3F46"}),
        "qty": float(it.get("qty") or 0),
        "unit_cost": float(it.get("unit_cost") or 0),
        "room": it.get("room"),
        "last_moved_at": last_moved_at,
        "last_moved_by_name": it.get("last_moved_by_name") or po.get("created_by_name"),
        "age_days": age,
        "blocked": blocked,
        "sla_days": sla_days,
    }


async def _iter_items(
    view: str,
    brand: Optional[str],
    customer: Optional[str],
    stage: Optional[str],
    q: Optional[str],
    sla_days: int,
    limit: int = 2000,
) -> list[dict]:
    """Return a flat list of tracker rows across all POs, filtered."""
    match: dict = {"status": {"$ne": "cancelled"}}
    if q:
        term = {"$regex": q, "$options": "i"}
        match["$or"] = [
            {"number": term},
            {"customer_name": term},
            {"items.sku": term},
            {"items.name": term},
        ]
    if brand and brand.lower() != "all":
        match["brand_id"] = brand
    if customer:
        match["customer_id"] = customer

    pipeline: list[dict] = [
        {"$match": match},
        {"$unwind": "$items"},
        {"$project": {
            "_id": 0,
            "id": 1, "number": 1, "customer_id": 1, "customer_name": 1,
            "brand_id": 1, "brand_name": 1, "quotation_id": 1, "quotation_number": 1,
            "created_at": 1, "created_by_name": 1, "status": 1,
            "items": 1,
        }},
    ]

    if view == "dispatch_record":
        pipeline.append({"$match": {"items.stage": {"$in": list(DISPATCH_STAGES)}}})
    elif stage:
        if stage not in PURCHASE_STAGES:
            raise HTTPException(status_code=400, detail=f"Unknown stage '{stage}'")
        pipeline.append({"$match": {"items.stage": stage}})

    docs = await db.purchase_orders.aggregate(pipeline).to_list(limit * 3)

    rows: list[dict] = []
    for d in docs:
        po = {k: v for k, v in d.items() if k != "items"}
        po["id"] = d.get("id")
        it = d.get("items") or {}
        rows.append(_flatten_item(po, it, sla_days))

    # Item-level search (for the sub-doc match already done, but also allow
    # customer_name text search post-unwind).
    if q:
        term = q.lower()
        rows = [r for r in rows if any(term in str(r.get(k) or "").lower() for k in ("sku", "name", "customer_name", "po_number", "brand_name"))]

    if view == "today":
        # Blocked/aging early-stage items first, newest activity next.
        rows = [r for r in rows if r["stage"] not in DISPATCH_STAGES or r["stage"] == "dispatched"]
        rows.sort(key=lambda r: (not r["blocked"], -(r.get("age_days") or 0)))
    elif view == "stock":
        rows.sort(key=lambda r: (r["stage"] == "delivered", -(r.get("age_days") or 0)))
    elif view == "customers":
        rows.sort(key=lambda r: ((r.get("customer_name") or "").lower(), r.get("po_number") or ""))
    elif view == "dispatch_record":
        rows.sort(key=lambda r: r.get("last_moved_at") or "", reverse=True)
    else:
        rows.sort(key=lambda r: r.get("last_moved_at") or "", reverse=True)

    return rows[:limit]


# =============================================================================
# Read endpoints
# =============================================================================
@router.get("/stages")
async def stage_catalog(_: UserPublic = Depends(get_current_user)):
    """Stage list with counts across ALL non-cancelled items."""
    pipeline = [
        {"$match": {"status": {"$ne": "cancelled"}}},
        {"$unwind": "$items"},
        {"$group": {"_id": {"$ifNull": ["$items.stage", "order_in_company"]}, "count": {"$sum": 1}}},
    ]
    rows = await db.purchase_orders.aggregate(pipeline).to_list(20)
    counts = {r["_id"]: r["count"] for r in rows}
    return [
        {"key": k, "label": STAGE_LABELS[k], "count": counts.get(k, 0), "tone": STAGE_TONES[k]}
        for k in PURCHASE_STAGES
    ]


@router.get("/brands")
async def brand_facets(_: UserPublic = Depends(get_current_user)):
    """Brand list with counts of tracked items."""
    pipeline = [
        {"$match": {"status": {"$ne": "cancelled"}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": {"id": "$brand_id", "name": "$brand_name"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
    ]
    rows = await db.purchase_orders.aggregate(pipeline).to_list(50)
    total = sum(r["count"] for r in rows)
    facets = [
        {"id": r["_id"].get("id"), "name": r["_id"].get("name") or "Unbranded", "count": r["count"]}
        for r in rows if r["_id"].get("id")
    ]
    return {"all": total, "brands": facets}


@router.get("/customers")
async def customer_facets(_: UserPublic = Depends(get_current_user)):
    """Customers with open (non-delivered) tracked items."""
    pipeline = [
        {"$match": {"status": {"$ne": "cancelled"}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": {"id": "$customer_id", "name": "$customer_name"},
            "count": {"$sum": 1},
            "open": {"$sum": {"$cond": [{"$in": ["$items.stage", ["delivered"]]}, 0, 1]}},
        }},
        {"$sort": {"open": -1, "count": -1}},
    ]
    rows = await db.purchase_orders.aggregate(pipeline).to_list(500)
    return [
        {
            "id": r["_id"].get("id"),
            "name": r["_id"].get("name"),
            "count": r["count"],
            "open": r["open"],
        }
        for r in rows if r["_id"].get("id")
    ]


@router.get("/items")
async def list_items(
    view: str = Query("stock", regex="^(today|stock|customers|dispatch_record)$"),
    brand: Optional[str] = None,
    customer: Optional[str] = None,
    stage: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    _: UserPublic = Depends(get_current_user),
):
    """Flat tracker rows filtered by view/brand/customer/stage/q."""
    settings = await _load_settings()
    rows = await _iter_items(view, brand, customer, stage, q, settings.sla_days, limit)

    blocked_count = sum(1 for r in rows if r["blocked"])
    return {
        "sla_days": settings.sla_days,
        "count": len(rows),
        "blocked_count": blocked_count,
        "items": rows,
    }


@router.get("/dispatch-record")
async def dispatch_record(
    brand: Optional[str] = None,
    customer: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    _: UserPublic = Depends(get_current_user),
):
    settings = await _load_settings()
    rows = await _iter_items("dispatch_record", brand, customer, None, q, settings.sla_days, limit)
    return {"count": len(rows), "items": rows}


@router.get("/items/{item_id}")
async def get_item(item_id: str, _: UserPublic = Depends(get_current_user)):
    po = await db.purchase_orders.find_one({"items.id": item_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Item not found")
    it = next((i for i in po.get("items", []) if i.get("id") == item_id), None)
    if not it:
        raise HTTPException(status_code=404, detail="Item not found")
    settings = await _load_settings()
    row = _flatten_item(po, it, settings.sla_days)
    row["stage_history"] = it.get("stage_history") or []
    row["po_status"] = po.get("status")
    return row


# =============================================================================
# Mutations — move, bulk move, transfer
# =============================================================================
class MoveBody(BaseModel):
    stage: PurchaseStage
    note: Optional[str] = None


class BulkMoveBody(BaseModel):
    item_ids: list[str]
    stage: PurchaseStage
    note: Optional[str] = None


class TransferBody(BaseModel):
    new_customer_id: str
    qty: float = Field(..., gt=0)
    reason: Optional[str] = None


async def _apply_stage_change(
    item_id: str, to_stage: str, user: UserPublic, note: Optional[str],
) -> dict:
    """Atomic update of a single item's stage — writes stage_history entry."""
    po = await db.purchase_orders.find_one({"items.id": item_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Item not found")
    it = next((i for i in po.get("items", []) if i.get("id") == item_id), None)
    if not it:
        raise HTTPException(status_code=404, detail="Item not found")
    from_stage = it.get("stage") or "order_in_company"
    if from_stage == to_stage:
        return {"po": po, "item": it, "no_change": True}

    now = now_iso()
    ev = PurchaseStageEvent(
        from_stage=from_stage, to_stage=to_stage,
        by_user_id=user.id, by_user_name=user.full_name,
        note=note, action="move",
    ).dict()

    await db.purchase_orders.update_one(
        {"id": po["id"], "items.id": item_id},
        {
            "$set": {
                "items.$.stage": to_stage,
                "items.$.last_moved_at": now,
                "items.$.last_moved_by": user.id,
                "items.$.last_moved_by_name": user.full_name,
                "updated_at": now,
            },
            "$push": {"items.$.stage_history": ev},
        },
    )

    await log_event(
        event_type="purchase.stage_moved",
        entity_type="purchase", entity_id=po["id"], actor=user,
        customer_id=po.get("customer_id"),
        summary=(
            f"{it.get('name')} · {STAGE_LABELS.get(from_stage, from_stage)} → "
            f"{STAGE_LABELS.get(to_stage, to_stage)}"
            + (f" · {note}" if note else "")
        ),
        payload={
            "item_id": item_id, "po_number": po.get("number"),
            "from_stage": from_stage, "to_stage": to_stage,
            "sku": it.get("sku"), "qty": it.get("qty"),
        },
    )
    return {"po_id": po["id"], "item_id": item_id, "from_stage": from_stage, "to_stage": to_stage}


@router.post("/items/{item_id}/move")
async def move_item(
    item_id: str,
    body: MoveBody,
    user: UserPublic = Depends(require_min_role("sales")),
):
    if body.stage not in PURCHASE_STAGES:
        raise HTTPException(status_code=400, detail=f"Unknown stage '{body.stage}'")
    return await _apply_stage_change(item_id, body.stage, user, body.note)


@router.post("/items/bulk-move")
async def bulk_move(
    body: BulkMoveBody,
    user: UserPublic = Depends(require_min_role("sales")),
):
    if body.stage not in PURCHASE_STAGES:
        raise HTTPException(status_code=400, detail=f"Unknown stage '{body.stage}'")
    if not body.item_ids:
        raise HTTPException(status_code=400, detail="No items selected")
    results: list[dict] = []
    for iid in body.item_ids:
        try:
            r = await _apply_stage_change(iid, body.stage, user, body.note)
            results.append({"item_id": iid, "ok": True, **r})
        except HTTPException as e:
            results.append({"item_id": iid, "ok": False, "error": e.detail})
    return {"count": len(results), "results": results}


async def _next_po_number() -> str:
    """Same simple counter used by quotation → PO creation."""
    year = datetime.now(timezone.utc).year
    prefix = f"FPO-{year}-"
    last = await db.purchase_orders.find(
        {"number": {"$regex": f"^{prefix}"}}, {"_id": 0, "number": 1}
    ).sort("number", -1).limit(1).to_list(1)
    n = 1
    if last:
        try:
            n = int(last[0]["number"].split("-")[-1]) + 1
        except Exception:
            n = 1
    return f"{prefix}{n:04d}"


@router.post("/items/{item_id}/transfer")
async def transfer_item(
    item_id: str,
    body: TransferBody,
    user: UserPublic = Depends(require_min_role("sales")),
):
    """Move `qty` units of an item to another customer.

    Steps (atomic per document):
      1. Load source PO and the item.
      2. Validate the requested qty is ≤ current qty.
      3. Reduce qty on source item (deletes the item if it hits 0).
      4. Create a NEW draft PO for the destination customer with a single item
         carrying the transferred qty, at the same stage as the source.
      5. Emit `purchase.transferred_out` on the source and `purchase.transferred_in`
         on the destination — both entries also live in each item's stage_history.
    """
    if body.qty <= 0:
        raise HTTPException(status_code=400, detail="Transfer qty must be > 0")

    po = await db.purchase_orders.find_one({"items.id": item_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Source item not found")
    it = next((i for i in po.get("items", []) if i.get("id") == item_id), None)
    if not it:
        raise HTTPException(status_code=404, detail="Source item not found")

    cur_qty = float(it.get("qty") or 0)
    if body.qty > cur_qty + 1e-6:
        raise HTTPException(status_code=400, detail=f"Only {cur_qty} available for transfer")

    src_customer_id = it.get("customer_id") or po.get("customer_id")
    if body.new_customer_id == src_customer_id:
        raise HTTPException(status_code=400, detail="Destination customer must differ from source")

    new_cust = await db.customers.find_one({"id": body.new_customer_id}, {"_id": 0})
    if not new_cust:
        raise HTTPException(status_code=404, detail="Destination customer not found")

    now = now_iso()
    stage = it.get("stage") or "order_in_company"

    # Build the destination item — same shape, fresh id, transfer bookkeeping.
    dest_item_id = str(uuid4())
    dest_item = PurchaseOrderItem(
        id=dest_item_id,
        product_id=it["product_id"], sku=it["sku"], name=it["name"],
        image=it.get("image"), category_id=it.get("category_id"), room=it.get("room"),
        qty=float(body.qty), unit_cost=float(it.get("unit_cost") or 0),
        quotation_line_id=None,     # detach — new customer owns this line now
        stage=stage,
        customer_id=body.new_customer_id,
        customer_name=new_cust.get("company") or new_cust.get("name"),
        brand_id=it.get("brand_id") or po.get("brand_id"),
        brand_name=it.get("brand_name") or po.get("brand_name"),
        last_moved_at=now, last_moved_by=user.id, last_moved_by_name=user.full_name,
        transferred_from_item_id=item_id,
        transferred_from_po_id=po["id"],
        transferred_from_customer_id=src_customer_id,
        stage_history=[
            PurchaseStageEvent(
                from_stage=None, to_stage=stage,
                by_user_id=user.id, by_user_name=user.full_name,
                note=body.reason or f"Transferred from {po.get('customer_name')}",
                action="transfer_in",
                ref_item_id=item_id, ref_po_id=po["id"],
            )
        ],
    )

    # Create destination PO — one-item, draft.
    number = await _next_po_number()
    dest_po = PurchaseOrder(
        number=number,
        quotation_id=None,
        quotation_number=None,
        customer_id=body.new_customer_id,
        customer_name=new_cust.get("company") or new_cust.get("name"),
        brand_id=it.get("brand_id") or po.get("brand_id"),
        brand_name=it.get("brand_name") or po.get("brand_name"),
        supplier_id=po.get("supplier_id"),
        supplier_name=po.get("supplier_name"),
        status="draft",
        items=[dest_item],
        internal_notes=(
            f"Transferred from {po.get('number')} · "
            f"{po.get('customer_name')}" + (f" — {body.reason}" if body.reason else "")
        ),
        subtotal=round(dest_item.qty * dest_item.unit_cost, 2),
        grand_total=round(dest_item.qty * dest_item.unit_cost, 2),
        created_by=user.id,
        created_by_name=user.full_name,
        status_history=[
            PurchaseStatusEvent(
                from_status=None, to_status="draft",
                by_user_id=user.id, by_user_name=user.full_name,
                note=f"Customer transfer from {po.get('number')}",
            ).dict()
        ],
    )
    await db.purchase_orders.insert_one(dest_po.dict())

    # Update source — reduce qty or drop the item if 0.
    remaining = round(cur_qty - float(body.qty), 4)
    src_event = PurchaseStageEvent(
        from_stage=stage, to_stage=stage,
        by_user_id=user.id, by_user_name=user.full_name,
        note=body.reason or f"Transferred {body.qty} → {new_cust.get('name')}",
        action="transfer_out",
        ref_item_id=dest_item_id, ref_po_id=dest_po.id,
    ).dict()

    if remaining <= 1e-6:
        # Push an audit event onto the item, then pull it from the array.
        await db.purchase_orders.update_one(
            {"id": po["id"], "items.id": item_id},
            {"$push": {"items.$.stage_history": src_event},
             "$set": {"updated_at": now}},
        )
        await db.purchase_orders.update_one(
            {"id": po["id"]},
            {"$pull": {"items": {"id": item_id}}},
        )
    else:
        await db.purchase_orders.update_one(
            {"id": po["id"], "items.id": item_id},
            {
                "$set": {
                    "items.$.qty": remaining,
                    "items.$.last_moved_at": now,
                    "items.$.last_moved_by": user.id,
                    "items.$.last_moved_by_name": user.full_name,
                    "updated_at": now,
                },
                "$push": {"items.$.stage_history": src_event},
            },
        )

    # Activity events on BOTH ends — customer timelines pick these up.
    await log_event(
        event_type="purchase.transferred_out",
        entity_type="purchase", entity_id=po["id"], actor=user,
        customer_id=src_customer_id,
        summary=(
            f"Transferred {body.qty} × {it.get('name')} to "
            f"{new_cust.get('company') or new_cust.get('name')}"
            + (f" — {body.reason}" if body.reason else "")
        ),
        payload={
            "src_po_id": po["id"], "src_po_number": po.get("number"),
            "dest_po_id": dest_po.id, "dest_po_number": dest_po.number,
            "dest_customer_id": body.new_customer_id,
            "item_id": item_id, "new_item_id": dest_item_id,
            "sku": it.get("sku"), "qty": body.qty, "reason": body.reason,
        },
    )
    await log_event(
        event_type="purchase.transferred_in",
        entity_type="purchase", entity_id=dest_po.id, actor=user,
        customer_id=body.new_customer_id,
        summary=(
            f"Received {body.qty} × {it.get('name')} from "
            f"{po.get('customer_name')}"
            + (f" — {body.reason}" if body.reason else "")
        ),
        payload={
            "src_po_id": po["id"], "src_po_number": po.get("number"),
            "dest_po_id": dest_po.id, "dest_po_number": dest_po.number,
            "src_customer_id": src_customer_id,
            "item_id": item_id, "new_item_id": dest_item_id,
            "sku": it.get("sku"), "qty": body.qty, "reason": body.reason,
        },
    )

    return {
        "source": {
            "po_id": po["id"], "po_number": po.get("number"),
            "item_id": item_id, "remaining_qty": max(0, remaining),
            "removed": remaining <= 1e-6,
        },
        "destination": {
            "po_id": dest_po.id, "po_number": dest_po.number,
            "item_id": dest_item_id, "qty": float(body.qty),
            "customer_id": body.new_customer_id,
            "customer_name": new_cust.get("company") or new_cust.get("name"),
        },
    }


# =============================================================================
# Excel export (real .xlsx via openpyxl)
# =============================================================================
@router.get("/export.xlsx")
async def export_xlsx(
    view: str = Query("stock", regex="^(today|stock|customers|dispatch_record)$"),
    brand: Optional[str] = None,
    customer: Optional[str] = None,
    stage: Optional[str] = None,
    q: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    settings = await _load_settings()
    rows = await _iter_items(view, brand, customer, stage, q, settings.sla_days, limit=2000)

    wb = Workbook()
    ws = wb.active
    ws.title = "Purchases"

    # Header block
    ws["A1"] = "Forge — Purchases Tracker Export"
    ws["A1"].font = Font(bold=True, size=14)
    ws.merge_cells("A1:H1")
    stamp = datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC")
    filter_bits = [f"View: {view}"]
    if brand:    filter_bits.append(f"Brand: {brand}")
    if customer: filter_bits.append(f"Customer: {customer}")
    if stage:    filter_bits.append(f"Stage: {STAGE_LABELS.get(stage, stage)}")
    if q:        filter_bits.append(f"Search: {q}")
    ws["A2"] = " · ".join(filter_bits) + f" · Exported {stamp}"
    ws["A2"].font = Font(color="6B7280", size=10)
    ws.merge_cells("A2:H2")

    headers = [
        "PO Number", "SKU", "Product", "Customer", "Brand", "Stage",
        "Qty", "Last Move (UTC)", "Moved By", "Age (days)", "Blocked",
    ]
    header_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.font = Font(bold=True, color="374151", size=11)
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")

    for i, r in enumerate(rows, start=5):
        ws.cell(row=i, column=1, value=r.get("po_number"))
        ws.cell(row=i, column=2, value=r.get("sku"))
        ws.cell(row=i, column=3, value=r.get("name"))
        ws.cell(row=i, column=4, value=r.get("customer_name"))
        ws.cell(row=i, column=5, value=r.get("brand_name"))
        ws.cell(row=i, column=6, value=r.get("stage_label"))
        ws.cell(row=i, column=7, value=r.get("qty"))
        ws.cell(row=i, column=8, value=r.get("last_moved_at"))
        ws.cell(row=i, column=9, value=r.get("last_moved_by_name"))
        ws.cell(row=i, column=10, value=r.get("age_days"))
        ws.cell(row=i, column=11, value="Yes" if r.get("blocked") else "")

    # Column widths — heuristic
    widths = [16, 14, 40, 26, 14, 20, 8, 24, 20, 12, 10]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = "A5"

    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)

    filename = f"forge-purchases-{view}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
