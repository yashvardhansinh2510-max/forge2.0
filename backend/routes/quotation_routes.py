"""Quotation Builder API — v2 with multi-level discounts, autosave, duplicate."""
import asyncio
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import get_current_customer, get_current_user, require_min_role
from db import db
from models import (
    CustomerPublic, PurchaseOrder, PurchaseOrderItem, PurchaseStatusEvent, PurchaseStageEvent,
    Quotation, QuotationCreate, QuotationLineItem, QuotationRevision,
    QuotationUpdate, RoomDiscountCfg, UserPublic, now_iso,
)
from pdf_generator import build_quotation_pdf
from services import catalog_service
from services.activity_log import log_event
from services.domain_outbox import (
    EVENT_ORDER_PLACED,
    EVENT_QUOTATION_GENERATED,
    dispatch_event,
    enqueue_after_primary_commit,
)
from services.followup_engine import reconcile_followups

router = APIRouter(prefix="/quotations", tags=["quotations"])


def _effective_discount_pct(
    line: QuotationLineItem,
    room_discounts: dict[str, "RoomDiscountCfg"],
    category_discounts: dict[str, float],
    project_discount_pct: float,
) -> tuple[float, str]:
    """Return (pct, source) — Product override > Room > Category > Project.
    Mirrors frontend/src/components/quotation/helpers/pricing.ts effectivePct
    EXACTLY — these two implementations must never drift, or the builder's
    live totals would disagree with what the server persists.
    A room with an "amount" (flat ₹) discount has no single per-line pct —
    it's resolved by _recalc's second pass — so we return pct=0 with source
    "room_amount" here to signal "blocked from category/project, pending
    room-level allocation", exactly like the TS version.
    """
    if line.discount_pct is not None:
        return float(line.discount_pct), "product"
    rd = room_discounts.get(line.room) if line.room else None
    if rd and rd.value > 0:
        if rd.type == "percent":
            return float(rd.value), "room"
        return 0.0, "room_amount"
    if line.category_id and line.category_id in category_discounts:
        return float(category_discounts[line.category_id]), "category"
    if project_discount_pct:
        return float(project_discount_pct), "project"
    return 0.0, "none"


def _recalc(
    items: list[QuotationLineItem],
    project_discount_pct: float = 0.0,
    category_discounts: dict[str, float] | None = None,
    room_discounts: dict[str, "RoomDiscountCfg"] | None = None,
) -> dict:
    category_discounts = category_discounts or {}
    room_discounts = room_discounts or {}
    subtotal = 0.0
    discount_total = 0.0

    # Pass 1 — per-line pct (product / room-percent / category / project).
    rows = []
    for it in items:
        gross = it.qty * it.unit_price
        pct, source = _effective_discount_pct(it, room_discounts, category_discounts, project_discount_pct)
        disc = gross * pct / 100
        rows.append({"gross": gross, "disc": disc, "source": source, "room": it.room})

    # Pass 2 — allocate flat room-amount discounts proportionally across the
    # affected room's eligible (non-product-overridden) lines.
    by_room: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["source"] == "room_amount":
            by_room[row["room"] or ""].append(row)
    for room, room_rows in by_room.items():
        cfg = room_discounts.get(room)
        if not cfg or cfg.type != "amount" or cfg.value <= 0:
            continue
        room_gross = sum(r["gross"] for r in room_rows)
        flat = min(cfg.value, room_gross)
        if room_gross <= 0 or flat <= 0:
            continue
        for row in room_rows:
            row["disc"] = flat * (row["gross"] / room_gross)

    for row in rows:
        subtotal += row["gross"]
        discount_total += row["disc"]

    grand_total = subtotal - discount_total
    return {
        "subtotal": round(subtotal, 2),
        "discount_total": round(discount_total, 2),
        "grand_total": round(grand_total, 2),
    }


async def _next_number() -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"FQ-{year}-"
    count = await db.quotations.count_documents({"number": {"$regex": f"^{prefix}"}})
    return f"{prefix}{count + 1:04d}"


async def _track_product_usage(user_id: str, product_ids: list[str]):
    """Bump usage counters for the picker's Recent/Frequent tabs."""
    now = datetime.now(timezone.utc).isoformat()
    await asyncio.gather(*[
        db.product_usage.update_one(
            {"user_id": user_id, "product_id": pid},
            {"$inc": {"count": 1}, "$set": {"last_used_at": now}},
            upsert=True,
        )
        for pid in set(product_ids)
    ])
    await catalog_service.note_product_usage(user_id, product_ids, now)


@router.get("")
async def list_quotations(_: UserPublic = Depends(get_current_user)):
    docs = await db.quotations.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return docs


@router.get("/recent")
async def recent_quotations(
    limit: int = 8,
    _: UserPublic = Depends(get_current_user),
):
    """Compact list of recent quotations for the Builder V4 left-rail panel.

    Returns just the fields the mini-list card needs — number, customer,
    project, amount, updated_at, status, revision count. Ordered by
    updated_at DESC so the most-recently-touched quote sits on top.
    """
    docs = await db.quotations.find(
        {},
        {
            "_id": 0, "id": 1, "number": 1, "customer_id": 1, "customer_name": 1,
            "project_name": 1, "phone_snapshot": 1, "grand_total": 1, "status": 1,
            "revisions": 1, "updated_at": 1, "created_at": 1,
        },
    ).sort("updated_at", -1).limit(limit).to_list(limit)
    out = []
    for d in docs:
        out.append({
            "id": d.get("id"),
            "number": d.get("number"),
            "customer_id": d.get("customer_id"),
            "customer_name": d.get("customer_name"),
            "project_name": d.get("project_name"),
            "phone": d.get("phone_snapshot"),
            "grand_total": d.get("grand_total") or 0,
            "status": d.get("status") or "draft",
            "revision_count": len(d.get("revisions") or []),
            "updated_at": d.get("updated_at"),
            "created_at": d.get("created_at"),
        })
    return out


@router.post("", response_model=Quotation)
async def create_quotation(
    body: QuotationCreate,
    user: UserPublic = Depends(require_min_role("sales")),
):
    customer = await db.customers.find_one({"id": body.customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Fill category_id on items so category discounts can resolve later.
    items = body.items or []
    for it in items:
        if not it.category_id:
            p = await db.products.find_one({"id": it.product_id}, {"_id": 0, "category_id": 1})
            if p:
                it.category_id = p.get("category_id")

    totals = _recalc(items, body.project_discount_pct or 0, body.category_discounts or {}, body.room_discounts or {})
    quot = Quotation(
        number=await _next_number(),
        customer_id=customer["id"],
        customer_name=customer.get("company") or customer["name"],
        project_name=body.project_name,
        phone_snapshot=body.phone_snapshot or customer.get("phone"),
        reference_source=body.reference_source,
        items=items,
        rooms=body.rooms or [],
        project_discount_pct=body.project_discount_pct or 0,
        category_discounts=body.category_discounts or {},
        room_discounts=body.room_discounts or {},
        notes=body.notes,
        valid_until=body.valid_until,
        created_by=user.id,
        created_by_name=user.full_name,
        **totals,
    )
    await db.quotations.insert_one(quot.dict())
    await _track_product_usage(user.id, [it.product_id for it in items])
    await log_event(
        event_type="quotation.created",
        entity_type="quotation",
        entity_id=quot.id,
        actor=user,
        customer_id=customer["id"],
        quotation_id=quot.id,
        summary=f"{quot.number} · {quot.customer_name} · {len(items)} items",
        payload={"items": len(items), "grand_total": quot.grand_total},
    )
    return quot


@router.get("/{quotation_id}", response_model=Quotation)
async def get_quotation(quotation_id: str, _: UserPublic = Depends(get_current_user)):
    doc = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return Quotation(**doc)


@router.patch("/{quotation_id}", response_model=Quotation)
async def update_quotation(
    quotation_id: str,
    body: QuotationUpdate,
    user: UserPublic = Depends(require_min_role("sales")),
):
    doc = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")

    update: dict = {}
    customer_changed_from: str | None = None
    if body.customer_id is not None and body.customer_id != doc.get("customer_id"):
        new_customer = await db.customers.find_one({"id": body.customer_id}, {"_id": 0})
        if not new_customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        customer_changed_from = doc.get("customer_name")
        update["customer_id"] = new_customer["id"]
        update["customer_name"] = new_customer.get("company") or new_customer["name"]
        # Refresh the frozen phone snapshot to the new customer's phone unless
        # this same request is also explicitly setting one.
        if body.phone_snapshot is None:
            update["phone_snapshot"] = new_customer.get("phone")

    if body.items is not None:
        items_typed = [
            QuotationLineItem(**i.dict()) if not isinstance(i, dict) else QuotationLineItem(**i)
            for i in body.items
        ]
        # Backfill category_id
        for it in items_typed:
            if not it.category_id:
                p = await db.products.find_one({"id": it.product_id}, {"_id": 0, "category_id": 1})
                if p:
                    it.category_id = p.get("category_id")
        update["items"] = [i.dict() for i in items_typed]
        await _track_product_usage(user.id, [it.product_id for it in items_typed])

    if body.rooms is not None:
        update["rooms"] = body.rooms
    if body.collapsed_rooms is not None:
        update["collapsed_rooms"] = body.collapsed_rooms
    if body.notes is not None:
        update["notes"] = body.notes
    if body.valid_until is not None:
        update["valid_until"] = body.valid_until
    if body.project_discount_pct is not None:
        update["project_discount_pct"] = float(body.project_discount_pct)
    if body.category_discounts is not None:
        update["category_discounts"] = body.category_discounts
    if body.room_discounts is not None:
        update["room_discounts"] = {k: v.dict() for k, v in body.room_discounts.items()}
    if body.status is not None:
        update["status"] = body.status
        if body.status == "approved":
            update["approved_by"] = user.id
    if body.project_name is not None:
        update["project_name"] = body.project_name
    if body.phone_snapshot is not None:
        update["phone_snapshot"] = body.phone_snapshot
    if body.reference_source is not None:
        update["reference_source"] = body.reference_source
    if body.ui_state is not None:
        update["ui_state"] = body.ui_state

    # Recalc totals if anything pricing-related changed
    if any(k in update for k in ("items", "project_discount_pct", "category_discounts", "room_discounts")):
        items_for_calc = [
            QuotationLineItem(**i) for i in update.get("items", doc.get("items", []))
        ]
        room_discounts_for_calc = {
            k: RoomDiscountCfg(**v) for k, v in update.get("room_discounts", doc.get("room_discounts", {}) or {}).items()
        }
        totals = _recalc(
            items_for_calc,
            update.get("project_discount_pct", doc.get("project_discount_pct", 0)),
            update.get("category_discounts", doc.get("category_discounts", {})),
            room_discounts_for_calc,
        )
        update.update(totals)

    if not update:
        return Quotation(**doc)

    # revision snapshot (unless silent autosave)
    if not body.silent:
        revisions = doc.get("revisions", [])
        rev = QuotationRevision(
            revision_no=len(revisions) + 1,
            created_by=user.id,
            reason=body.reason,
            snapshot={k: doc.get(k) for k in (
                "items", "rooms", "notes", "status", "grand_total", "project_discount_pct",
                "category_discounts", "room_discounts", "customer_id", "customer_name",
            )},
        )
        update["revisions"] = revisions + [rev.dict()]

    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.quotations.update_one({"id": quotation_id}, {"$set": update})

    # Activity logging (non-silent only — silent = autosave)
    if not body.silent:
        events: list[tuple[str, str, dict]] = []
        prev_items = doc.get("items", [])
        new_items = update.get("items", prev_items)
        if "items" in update:
            prev_ids = {i["product_id"] for i in prev_items}
            new_ids = {i["product_id"] for i in new_items}
            added = new_ids - prev_ids
            removed = prev_ids - new_ids
            for pid in added:
                match = next((i for i in new_items if i["product_id"] == pid), None)
                if match:
                    events.append(("quotation.product_added", f"Added {match.get('name', 'product')}", {"sku": match.get("sku")}))
            for pid in removed:
                match = next((i for i in prev_items if i["product_id"] == pid), None)
                if match:
                    events.append(("quotation.product_removed", f"Removed {match.get('name', 'product')}", {"sku": match.get("sku")}))
            if not added and not removed and prev_items != new_items:
                events.append(("quotation.product_reordered", "Line items updated", {}))
        if "project_discount_pct" in update or "category_discounts" in update:
            events.append(("quotation.discount_changed", "Discount changed", {
                "project": update.get("project_discount_pct", doc.get("project_discount_pct")),
                "categories": update.get("category_discounts", doc.get("category_discounts")),
            }))
        if "rooms" in update:
            prev = doc.get("rooms", [])
            new = update["rooms"]
            added = [r for r in new if r not in prev]
            removed = [r for r in prev if r not in new]
            for r in added:
                events.append(("quotation.room_created", f"Room '{r}' added", {"room": r}))
            for r in removed:
                events.append(("quotation.room_deleted", f"Room '{r}' removed", {"room": r}))
        if "status" in update:
            events.append((
                "quotation.status_changed",
                f"Status changed to {update['status'].replace('_', ' ')}",
                {"from": doc.get("status"), "to": update["status"]},
            ))
        if "notes" in update:
            events.append(("quotation.saved", "Notes updated", {}))
        if customer_changed_from is not None:
            events.append((
                "quotation.customer_changed",
                f"Customer changed from {customer_changed_from} to {update.get('customer_name')}",
                {"from": customer_changed_from, "to": update.get("customer_name"), "to_customer_id": update.get("customer_id")},
            ))
        if "room_discounts" in update and update["room_discounts"] != (doc.get("room_discounts") or {}):
            events.append(("quotation.discount_changed", "Room discount changed", {"room_discounts": update["room_discounts"]}))
        # revision event captured separately below (already appended to revisions)
        events.append(("quotation.revision_created", f"Revision {len(revisions) + 1} saved", {"reason": body.reason}))

        for etype, summary, payload in events:
            await log_event(
                event_type=etype, entity_type="quotation", entity_id=quotation_id,
                actor=user, customer_id=doc.get("customer_id"), quotation_id=quotation_id,
                summary=summary, payload=payload,
            )

    fresh = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if "status" in update:
        # Event-triggered (not cron) reconciliation — a status change is
        # exactly the moment quotation-stage follow-ups should refresh/close.
        asyncio.create_task(reconcile_followups())
    return Quotation(**fresh)


@router.delete("/{quotation_id}")
async def delete_quotation(
    quotation_id: str,
    _: UserPublic = Depends(require_min_role("manager")),
):
    res = await db.quotations.delete_one({"id": quotation_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return {"ok": True}


@router.post("/{quotation_id}/duplicate", response_model=Quotation)
async def duplicate_quotation(
    quotation_id: str,
    user: UserPublic = Depends(require_min_role("sales")),
):
    src = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Quotation not found")

    body = QuotationCreate(
        customer_id=src["customer_id"],
        items=[],
        rooms=src.get("rooms", []),
        notes=src.get("notes"),
        valid_until=src.get("valid_until"),
        project_discount_pct=src.get("project_discount_pct", 0),
        category_discounts=src.get("category_discounts", {}),
        room_discounts=src.get("room_discounts", {}),
    )
    # Build fresh line items so ids are regenerated by the default_factory.
    body.items = [
        QuotationLineItem(
            product_id=i["product_id"], sku=i["sku"], name=i["name"], image=i.get("image"),
            category_id=i.get("category_id"), room=i.get("room"),
            qty=i["qty"], unit_price=i["unit_price"],
            discount_pct=i.get("discount_pct"),
            notes=i.get("notes"), description=i.get("description"),
            sort_order=i.get("sort_order", 0),
        )
        for i in src.get("items", [])
    ]
    return await create_quotation(body, user)


# --- Breakdown (for line + totals transparency) ---
@router.get("/{quotation_id}/breakdown")
async def quotation_breakdown(quotation_id: str, _: UserPublic = Depends(get_current_user)):
    """How the final numbers were calculated — per line + summary."""
    doc = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")

    project_pct = doc.get("project_discount_pct", 0)
    cat_discs = doc.get("category_discounts", {}) or {}
    room_discs_raw = doc.get("room_discounts", {}) or {}
    room_discs = {k: RoomDiscountCfg(**v) for k, v in room_discs_raw.items()}

    rows = []
    for raw in doc.get("items", []):
        it = QuotationLineItem(**raw)
        gross = it.qty * it.unit_price
        pct, source = _effective_discount_pct(it, room_discs, cat_discs, project_pct)
        rows.append({"it": it, "gross": gross, "pct": pct, "source": source, "disc": gross * pct / 100})

    # Second pass — proportional allocation of flat room-amount discounts,
    # mirrors _recalc exactly so the breakdown always adds up to the totals.
    by_room: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["source"] == "room_amount":
            by_room[row["it"].room or ""].append(row)
    for room, room_rows in by_room.items():
        cfg = room_discs.get(room)
        if not cfg or cfg.type != "amount" or cfg.value <= 0:
            continue
        room_gross = sum(r["gross"] for r in room_rows)
        flat = min(cfg.value, room_gross)
        if room_gross <= 0 or flat <= 0:
            continue
        for row in room_rows:
            row["disc"] = flat * (row["gross"] / room_gross)
            row["pct"] = round((row["disc"] / row["gross"]) * 100, 4) if row["gross"] else 0

    lines_out = []
    for row in rows:
        it, gross, disc = row["it"], row["gross"], row["disc"]
        net = gross - disc
        lines_out.append({
            "line_id": it.id, "product_id": it.product_id, "sku": it.sku, "name": it.name,
            "room": it.room, "qty": it.qty, "unit_price": it.unit_price, "gross": round(gross, 2),
            "discount_pct": round(row["pct"], 2), "discount_source": row["source"].replace("room_amount", "room"),
            "discount_amount": round(disc, 2),
            "net": round(net, 2),
            "total": round(net, 2),
        })

    totals = _recalc([QuotationLineItem(**i) for i in doc.get("items", [])], project_pct, cat_discs, room_discs)
    return {
        "lines": lines_out,
        "totals": totals,
        "project_discount_pct": project_pct,
        "category_discounts": cat_discs,
        "room_discounts": room_discs_raw,
    }


def _enriched_items_for_pdf(doc: dict) -> list[dict]:
    """Line items with `discount_pct` overridden to the EFFECTIVE resolved
    pct (product/room/category/project), so the PDF's per-line Disc% column
    always matches the grand total — instead of only ever showing product-
    level overrides and leaving inherited discounts blank."""
    project_pct = doc.get("project_discount_pct", 0)
    cat_discs = doc.get("category_discounts", {}) or {}
    room_discs = {k: RoomDiscountCfg(**v) for k, v in (doc.get("room_discounts") or {}).items()}
    rows = []
    for raw in doc.get("items", []):
        it = QuotationLineItem(**raw)
        gross = it.qty * it.unit_price
        pct, source = _effective_discount_pct(it, room_discs, cat_discs, project_pct)
        rows.append({"raw": raw, "gross": gross, "pct": pct, "source": source})
    by_room: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["source"] == "room_amount":
            by_room[row["raw"].get("room") or ""].append(row)
    for room, room_rows in by_room.items():
        cfg = room_discs.get(room)
        if not cfg or cfg.type != "amount" or cfg.value <= 0:
            continue
        room_gross = sum(r["gross"] for r in room_rows)
        flat = min(cfg.value, room_gross)
        if room_gross <= 0 or flat <= 0:
            continue
        for row in room_rows:
            row["pct"] = round(((flat * (row["gross"] / room_gross)) / row["gross"]) * 100, 2) if row["gross"] else 0
    return [{**row["raw"], "discount_pct": round(row["pct"], 2)} for row in rows]


# --- PDF branding (Settings > Company + Settings > PDF, merged) -----------
async def _pdf_branding() -> dict:
    """Merge Settings > Company + Settings > PDF into the flat dict
    pdf_generator.build_quotation_pdf expects. Every key falls back to the
    same value that used to be hardcoded in pdf_generator.py, so a quotation
    PDF renders identically until someone actually edits these in Settings."""
    company = await db.settings.find_one({"key": "company"}, {"_id": 0}) or {}
    pdf = await db.settings.find_one({"key": "pdf"}, {"_id": 0}) or {}
    return {
        "footer_company_name": pdf.get("footer_company_name") or company.get("name") or "Buildcon House",
        "footer_phone": pdf.get("footer_phone") or company.get("phone") or "+91 99099 06652",
        "footer_email": pdf.get("footer_email") or company.get("email") or "buildconhouse10@gmail.com",
        "footer_tagline": pdf.get("footer_tagline") or company.get("tagline") or "One Destination. Infinite Possibilities.",
        "terms_text": pdf.get("terms_text"),
        "signature_name": pdf.get("signature_name"),
        "signature_title": pdf.get("signature_title"),
        "show_watermark": pdf.get("show_watermark", True),
    }


# --- Official PDF command (staff) ---
@router.get("/{quotation_id}/pdf")
async def quotation_pdf(quotation_id: str, user: UserPublic = Depends(get_current_user)):
    """Build the PDF, then journal QuotationGenerated before dispatching automation.

    The PDF is the primary output. Its outbox record is committed first; timeline
    and follow-up handlers only run after that commit succeeds.
    """
    doc = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    customer = await db.customers.find_one({"id": doc["customer_id"]}, {"_id": 0, "password_hash": 0}) or {}
    pdf_doc = {**doc, "items": _enriched_items_for_pdf(doc)}
    pdf_bytes = build_quotation_pdf(pdf_doc, customer, await _pdf_branding())
    revision = len(doc.get("revisions") or [])
    key = f"quotation-generated:{quotation_id}:revision:{revision}"
    event = await db.event_outbox.find_one({"idempotency_key": key}, {"_id": 0})
    if not event:
        from db import client
        try:
            async with await client.start_session() as session:
                async with session.start_transaction():
                    event = await enqueue_after_primary_commit(
                        event_type=EVENT_QUOTATION_GENERATED,
                        idempotency_key=key,
                        payload={"quotation_id": quotation_id, "revision": revision},
                        actor=user,
                        session=session,
                    )
        except Exception as exc:
            # A unique-index collision is an idempotent duplicate request.
            event = await db.event_outbox.find_one({"idempotency_key": key}, {"_id": 0})
            if not event:
                raise HTTPException(status_code=500, detail=f"Could not journal quotation generation: {exc}") from exc
    await dispatch_event(event["id"])
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc["number"]}.pdf"'},
    )


# --- PDF (customer portal; intentionally read-only) ---
@router.get("/{quotation_id}/portal-pdf")
async def portal_pdf(quotation_id: str, cust: CustomerPublic = Depends(get_current_customer)):
    doc = await db.quotations.find_one({"id": quotation_id, "customer_id": cust.id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    pdf_doc = {**doc, "items": _enriched_items_for_pdf(doc)}
    pdf_bytes = build_quotation_pdf(pdf_doc, cust.dict(), await _pdf_branding())
    return StreamingResponse(iter([pdf_bytes]), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{doc["number"]}.pdf"'})


# --- PDF of a previous revision snapshot (customer portal; read-only) ---
@router.get("/{quotation_id}/portal-pdf/revision/{revision_no}")
async def portal_pdf_revision(
    quotation_id: str, revision_no: int, cust: CustomerPublic = Depends(get_current_customer),
):
    doc = await db.quotations.find_one({"id": quotation_id, "customer_id": cust.id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    rev = next((r for r in (doc.get("revisions") or []) if r.get("revision_no") == revision_no), None)
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")
    snapshot = rev.get("snapshot") or {}
    merged = {**doc, **snapshot}
    room_discs = {k: RoomDiscountCfg(**v) for k, v in (merged.get("room_discounts") or {}).items()}
    totals = _recalc(
        [QuotationLineItem(**i) for i in merged.get("items", [])],
        merged.get("project_discount_pct", 0),
        merged.get("category_discounts", {}) or {},
        room_discs,
    )
    pdf_doc = {**merged, **totals, "items": _enriched_items_for_pdf(merged)}
    pdf_bytes = build_quotation_pdf(pdf_doc, cust.dict(), await _pdf_branding())
    filename = f'{doc["number"]}-rev{revision_no}.pdf'
    return StreamingResponse(iter([pdf_bytes]), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'})


# --- Brand-filtered PDF (customer portal; read-only) ---
@router.get("/{quotation_id}/portal-pdf/brand/{brand_id}")
async def portal_pdf_brand(
    quotation_id: str, brand_id: str, cust: CustomerPublic = Depends(get_current_customer),
):
    doc = await db.quotations.find_one({"id": quotation_id, "customer_id": cust.id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    items = doc.get("items", [])
    product_ids = list({item["product_id"] for item in items})
    products = await db.products.find(
        {"id": {"$in": product_ids}}, {"_id": 0, "id": 1, "brand_id": 1},
    ).to_list(len(product_ids) + 5)
    brand_by_product = {p["id"]: p.get("brand_id") for p in products}
    is_unassigned = brand_id == "unassigned"
    filtered = [
        it for it in items
        if (
            brand_by_product.get(it["product_id"]) is None
            if is_unassigned
            else brand_by_product.get(it["product_id"]) == brand_id
        )
    ]
    if not filtered:
        raise HTTPException(status_code=404, detail="No items for this brand on this quotation")
    room_discs = {k: RoomDiscountCfg(**v) for k, v in (doc.get("room_discounts") or {}).items()}
    totals = _recalc(
        [QuotationLineItem(**i) for i in filtered],
        doc.get("project_discount_pct", 0),
        doc.get("category_discounts", {}) or {},
        room_discs,
    )
    filtered_doc = {**doc, "items": filtered}
    pdf_doc = {**filtered_doc, **totals, "items": _enriched_items_for_pdf(filtered_doc)}
    pdf_bytes = build_quotation_pdf(pdf_doc, cust.dict(), await _pdf_branding())
    brand_doc = None if is_unassigned else await db.brands.find_one({"id": brand_id}, {"_id": 0, "name": 1})
    brand_label = (brand_doc or {}).get("name") or "Other"
    filename = f'{doc["number"]}-{brand_label}.pdf'.replace(" ", "-")
    return StreamingResponse(iter([pdf_bytes]), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'})


# =============================================================================
# Place Order command — primary quotation state + EventOutbox; no side effects.
# =============================================================================
class PlaceOrderConfirmPayload(BaseModel):
    """Retained API shape; downstream defaults are selected by the OrderPlaced handler."""
    supplier_by_brand: dict[str, str] = {}
    notes_by_brand: dict[str, str] = {}
    expected_delivery_at: str | None = None
    project_name: str | None = None


async def _brand_grouped_preview(doc: dict) -> dict:
    items = doc.get("items", [])
    if not items:
        return {"quotation_id": doc["id"], "quotation_number": doc.get("number"), "brands": []}
    product_ids = list({item["product_id"] for item in items})
    products = await db.products.find({"id": {"$in": product_ids}}, {"_id": 0, "id": 1, "brand_id": 1}).to_list(len(product_ids) + 5)
    product_map = {product["id"]: product for product in products}
    brand_ids = list({product.get("brand_id") for product in products if product.get("brand_id")})
    brands = await db.brands.find({"id": {"$in": brand_ids}}, {"_id": 0}).to_list(len(brand_ids) + 5)
    brand_map = {brand["id"]: brand for brand in brands}
    grouped: dict[str, dict] = {}
    for item in items:
        brand_id = product_map.get(item["product_id"], {}).get("brand_id") or "__unassigned__"
        group = grouped.setdefault(brand_id, {"brand_id": None if brand_id == "__unassigned__" else brand_id, "brand_name": brand_map.get(brand_id, {}).get("name", "Unassigned"), "items": [], "subtotal": 0.0})
        group["items"].append(item)
        group["subtotal"] += float(item.get("qty") or 0) * float(item.get("unit_price") or 0)
    cards = [{**group, "subtotal": round(group["subtotal"], 2), "item_count": len(group["items"])} for group in grouped.values()]
    return {"quotation_id": doc["id"], "quotation_number": doc.get("number"), "customer_id": doc.get("customer_id"), "customer_name": doc.get("customer_name"), "brands": sorted(cards, key=lambda card: card["brand_name"]), "total_value": round(sum(card["subtotal"] for card in cards), 2)}


@router.get("/{quotation_id}/place-order/preview")
async def place_order_preview(quotation_id: str, _: UserPublic = Depends(require_min_role("sales"))):
    doc = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if not doc.get("items"):
        raise HTTPException(status_code=400, detail="Cannot place order — quotation has no items")
    return await _brand_grouped_preview(doc)


@router.post("/{quotation_id}/place-order/confirm")
async def place_order_confirm(quotation_id: str, body: PlaceOrderConfirmPayload, user: UserPublic = Depends(require_min_role("sales"))):
    """Commit OrderPlaced once, then dispatch idempotent secondary automation."""
    key = f"order-placed:{quotation_id}"
    event = await db.event_outbox.find_one({"idempotency_key": key}, {"_id": 0})
    if not event:
        from db import client
        try:
            async with await client.start_session() as session:
                async with session.start_transaction():
                    doc = await db.quotations.find_one({"id": quotation_id}, {"_id": 0}, session=session)
                    if not doc:
                        raise HTTPException(status_code=404, detail="Quotation not found")
                    if not doc.get("items"):
                        raise HTTPException(status_code=400, detail="Cannot place order — quotation has no items")
                    await db.quotations.update_one(
                        {"id": quotation_id},
                        {"$set": {"status": "ordered", "updated_at": now_iso()}},
                        session=session,
                    )
                    event = await enqueue_after_primary_commit(
                        event_type=EVENT_ORDER_PLACED,
                        idempotency_key=key,
                        payload={"quotation_id": quotation_id, "project_name": body.project_name, "expected_delivery_at": body.expected_delivery_at},
                        actor=user,
                        session=session,
                    )
        except HTTPException:
            raise
        except Exception as exc:
            event = await db.event_outbox.find_one({"idempotency_key": key}, {"_id": 0})
            if not event:
                raise HTTPException(status_code=500, detail=f"Could not journal order placement: {exc}") from exc
    result = await dispatch_event(event["id"])
    asyncio.create_task(reconcile_followups())
    return {"quotation_id": quotation_id, "idempotent": event.get("status") == "completed", **result}


@router.get("/{quotation_id}/workflow-status")
async def workflow_status(
    quotation_id: str,
    _: UserPublic = Depends(require_min_role("sales")),
):
    """Read-only audit projection for the transactional quotation workflow."""
    quotation = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    events = await db.event_outbox.find({"payload.quotation_id": quotation_id}, {"_id": 0}).sort("created_at", 1).to_list(50)
    purchase_orders = await db.purchase_orders.find({"quotation_id": quotation_id}, {"_id": 0}).sort("created_at", 1).to_list(100)
    payments = await db.payments.find({"quotation_id": quotation_id}, {"_id": 0}).sort("created_at", 1).to_list(100)
    timeline = await db.activity_events.find({"quotation_id": quotation_id, "automation_key": {"$exists": True}}, {"_id": 0}).sort("created_at", 1).to_list(100)
    followups = await db.followups.find({"quotation_id": quotation_id, "automation_key": {"$exists": True}}, {"_id": 0}).sort("created_at", 1).to_list(100)
    return {"quotation_id": quotation_id, "quotation_total": round(float(quotation.get("grand_total") or 0), 2), "events": events, "purchase_orders": purchase_orders, "payments": payments, "timeline": timeline, "followups": followups}
