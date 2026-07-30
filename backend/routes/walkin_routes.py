"""Walk-ins — Phase 4 (2026-07-30). Entry point of the BuildCon ERP pipeline.

Department-agnostic by design: `floor_id` ("Interested Department") is the
existing, admin-configurable Floor entity — Tiles/Sanitary today, any future
department tomorrow, with zero schema change.

Reuses (no duplicate logic):
  - services/walkin_service.py     — duplicate-safe customer lookup/create
  - services/followup_engine.py    — reconcile_followups() / score_followup()
  - services/messaging_service.py  — WhatsApp deep-link + templates
  - services/email_service.py      — mailto deep-link + templates
  - services/activity_log.py       — timeline_for() (customer timeline)
  - services/sequence.py           — next_number()
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import floor_query, get_current_user, require_min_role
from db import db
from models import UserPublic, now_iso
from models_walkins import WalkIn, WalkInCreate, WalkInUpdate, WALKIN_OPEN_STATUSES
from services.activity_log import log_event, timeline_for
from services.followup_engine import parse_iso, reconcile_followups
from services.sequence import next_number as _next_number_seq
from services.walkin_service import find_or_create_customer

router = APIRouter(prefix="/walkins", tags=["walkins"])

LEAD_SOURCES_KEY = "lead_sources"


async def _next_walkin_number() -> str:
    year = datetime.now(timezone.utc).year
    return await _next_number_seq("walkin", f"WI-{year}-", collection="walkins")


class LeadSourcesSettingsBody(BaseModel):
    sources: list[str]


# ---------- Lead sources config (Settings-style, db.settings pattern) ----------
@router.get("/config/sources")
async def get_lead_sources(_: UserPublic = Depends(get_current_user)):
    from models_walkins import LeadSourcesSettings
    doc = await db.settings.find_one({"key": LEAD_SOURCES_KEY}, {"_id": 0})
    if not doc:
        return LeadSourcesSettings()
    return LeadSourcesSettings(sources=doc.get("sources") or LeadSourcesSettings().sources)


@router.put("/config/sources")
async def update_lead_sources(body: LeadSourcesSettingsBody, user: UserPublic = Depends(require_min_role("manager"))):
    sources = [s.strip() for s in body.sources if s.strip()]
    await db.settings.update_one(
        {"key": LEAD_SOURCES_KEY},
        {"$set": {"key": LEAD_SOURCES_KEY, "sources": sources, "updated_at": now_iso(), "updated_by": user.id}},
        upsert=True,
    )
    return {"sources": sources}


# ---------- Duplicate check (frontend calls before submit, per spec) ----------
@router.get("/check-duplicate")
async def check_duplicate(phone: Optional[str] = None, alternate_phone: Optional[str] = None, _: UserPublic = Depends(get_current_user)):
    def digits(p):
        return "".join(c for c in (p or "") if c.isdigit())

    candidates = [d for d in (digits(phone), digits(alternate_phone)) if d]
    if not candidates:
        return {"customer": None}
    existing = await db.customers.find_one(
        {"$or": [{"phone": {"$regex": f"{d}$"}} for d in candidates] + [{"alternate_phone": {"$regex": f"{d}$"}} for d in candidates]},
        {"_id": 0, "password_hash": 0},
    )
    return {"customer": existing}


# ---------- Create ----------
@router.post("", response_model=WalkIn)
async def create_walkin(body: WalkInCreate, user: UserPublic = Depends(require_min_role("sales"))):
    if not await db.floors.find_one({"id": body.floor_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Department (floor) not found")
    customer = await find_or_create_customer(
        name=body.customer_name, phone=body.customer_phone, alternate_phone=body.alternate_phone,
        email=body.email, floor_id=body.floor_id, user=user,
    )
    salesperson_id = body.salesperson_id or user.id
    walkin = WalkIn(
        number=await _next_walkin_number(),
        customer_id=customer["id"], customer_name=customer.get("name"),
        customer_phone=body.customer_phone, alternate_phone=body.alternate_phone,
        visited_at=body.visited_at or now_iso(),
        salesperson_id=salesperson_id,
        salesperson_name=user.full_name if salesperson_id == user.id else None,
        source=body.source, floor_id=body.floor_id, interested_products=body.interested_products,
        budget=body.budget, notes=body.notes, manual_priority_override=body.priority,
        next_followup_at=body.next_followup_at,
        created_by=user.id, created_by_name=user.full_name,
    )
    await db.walkins.insert_one(walkin.dict())
    await log_event(
        event_type="walkin.created", entity_type="walkin", entity_id=walkin.id,
        customer_id=customer["id"], actor=user,
        summary=f"{walkin.number} · {customer.get('name')} · {body.source}",
    )
    asyncio.create_task(reconcile_followups())
    return walkin


# ---------- List ----------
@router.get("", response_model=list[WalkIn])
async def list_walkins(
    status: Optional[str] = None, priority: Optional[str] = None, salesperson_id: Optional[str] = None,
    source: Optional[str] = None, floor_id: Optional[str] = None,
    date_from: Optional[str] = None, date_to: Optional[str] = None, search: Optional[str] = None,
    user: UserPublic = Depends(get_current_user),
):
    filters: dict = {"is_deleted": False}
    if status:
        filters["status"] = status
    if salesperson_id:
        filters["salesperson_id"] = salesperson_id
    if source:
        filters["source"] = source
    if floor_id:
        filters["floor_id"] = floor_id
    if date_from or date_to:
        rng: dict = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        filters["visited_at"] = rng
    if search:
        filters["$or"] = [
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"customer_phone": {"$regex": search, "$options": "i"}},
            {"salesperson_name": {"$regex": search, "$options": "i"}},
            {"source": {"$regex": search, "$options": "i"}},
            {"notes": {"$regex": search, "$options": "i"}},
        ]
    docs = await db.walkins.find(floor_query(user, filters), {"_id": 0}).sort("visited_at", -1).to_list(2000)
    if priority:
        docs = [d for d in docs if (d.get("manual_priority_override") or "medium") == priority]
    return [WalkIn(**d) for d in docs]


# ---------- Dashboard KPIs ----------
@router.get("/dashboard")
async def walkins_dashboard(user: UserPublic = Depends(get_current_user)):
    docs = await db.walkins.find(floor_query(user, {"is_deleted": False}), {"_id": 0}).to_list(5000)
    now = datetime.now(timezone.utc)
    today = now.date()
    week_start = today.fromordinal(today.toordinal() - today.weekday())

    def visited_date(d):
        dt = parse_iso(d.get("visited_at"))
        return dt.date() if dt else None

    today_count = sum(1 for d in docs if visited_date(d) == today)
    week_count = sum(1 for d in docs if visited_date(d) and visited_date(d) >= week_start)
    pending = sum(1 for d in docs if d.get("status") in WALKIN_OPEN_STATUSES)
    selection_scheduled = sum(1 for d in docs if d.get("status") == "selection_scheduled")
    converted = sum(1 for d in docs if d.get("status") in ("selection_completed", "quotation_created", "converted"))
    lost = sum(1 for d in docs if d.get("status") == "lost")
    closed = converted + lost
    conversion_rate = round((converted / closed) * 100, 1) if closed else 0.0

    conv_days = []
    for d in docs:
        if d.get("status") in ("selection_completed", "quotation_created", "converted"):
            v = parse_iso(d.get("visited_at"))
            u = parse_iso(d.get("updated_at"))
            if v and u:
                conv_days.append((u - v).total_seconds() / 86400)
    avg_conversion_days = round(sum(conv_days) / len(conv_days), 1) if conv_days else 0.0

    return {
        "today_walkins": today_count, "this_week": week_count, "pending_followups": pending,
        "selections_scheduled": selection_scheduled, "converted": converted, "lost": lost,
        "conversion_rate": conversion_rate, "avg_conversion_days": avg_conversion_days,
        "total": len(docs),
    }


# ---------- Analytics funnel ----------
@router.get("/analytics")
async def walkins_analytics(user: UserPublic = Depends(get_current_user)):
    walkins = await db.walkins.find(floor_query(user, {"is_deleted": False}), {"_id": 0}).to_list(5000)
    customer_ids = list({w["customer_id"] for w in walkins})
    quotations = await db.quotations.find(
        floor_query(user, {"customer_id": {"$in": customer_ids}}), {"_id": 0},
    ).to_list(5000) if customer_ids else []
    selections = sum(1 for q in quotations if q.get("doc_type") == "tiles_selection")
    tiles_quotations = sum(1 for q in quotations if q.get("doc_type") == "tiles_quotation")
    orders = sum(1 for q in quotations if q.get("status") == "ordered")
    revenue = sum(float(q.get("grand_total") or 0) for q in quotations if q.get("status") == "ordered")
    lost = [w for w in walkins if w.get("status") == "lost"]
    revenue_lost = sum(float(w.get("budget") or 0) for w in lost)

    by_salesperson: dict[str, dict] = {}
    for w in walkins:
        key = w.get("salesperson_name") or "Unassigned"
        row = by_salesperson.setdefault(key, {"salesperson": key, "walkins": 0, "converted": 0, "lost": 0})
        row["walkins"] += 1
        if w.get("status") in ("selection_completed", "quotation_created", "converted"):
            row["converted"] += 1
        elif w.get("status") == "lost":
            row["lost"] += 1

    return {
        "funnel": {"walk_ins": len(walkins), "selections": selections, "quotations": tiles_quotations, "orders": orders},
        "conversion_rate_pct": round((orders / len(walkins)) * 100, 1) if walkins else 0.0,
        "lost_leads": len(lost), "revenue_generated": round(revenue, 2), "revenue_lost": round(revenue_lost, 2),
        "salesperson_performance": sorted(by_salesperson.values(), key=lambda r: -r["converted"]),
    }


# ---------- Detail / update / contact / actions ----------
@router.get("/{walkin_id}", response_model=WalkIn)
async def get_walkin(walkin_id: str, user: UserPublic = Depends(get_current_user)):
    doc = await db.walkins.find_one(floor_query(user, {"id": walkin_id}), {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Walk-in not found")
    return WalkIn(**doc)


@router.get("/{walkin_id}/timeline")
async def walkin_timeline(walkin_id: str, user: UserPublic = Depends(get_current_user)):
    doc = await db.walkins.find_one(floor_query(user, {"id": walkin_id}), {"_id": 0, "customer_id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Walk-in not found")
    return await timeline_for(customer_id=doc["customer_id"], limit=60)


@router.patch("/{walkin_id}", response_model=WalkIn)
async def update_walkin(walkin_id: str, body: WalkInUpdate, user: UserPublic = Depends(require_min_role("sales"))):
    doc = await db.walkins.find_one(floor_query(user, {"id": walkin_id}), {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Walk-in not found")
    patch = body.dict(exclude_unset=True)
    patch["updated_at"] = now_iso()
    if patch.get("status") == "converted":
        patch["converted_at"] = now_iso()
    await db.walkins.update_one({"id": walkin_id}, {"$set": patch})
    if "status" in patch:
        await log_event(
            event_type="walkin.status_changed", entity_type="walkin", entity_id=walkin_id,
            customer_id=doc["customer_id"], actor=user,
            summary=f"Walk-in {doc.get('number')} → {patch['status']}",
        )
        asyncio.create_task(reconcile_followups())
    fresh = await db.walkins.find_one({"id": walkin_id}, {"_id": 0})
    return WalkIn(**fresh)


@router.post("/{walkin_id}/contact")
async def contact_walkin(walkin_id: str, channel: str = Query(..., pattern="^(whatsapp|email)$"), user: UserPublic = Depends(get_current_user)):
    from services.email_service import build_email
    from services.messaging_service import build_message

    doc = await db.walkins.find_one(floor_query(user, {"id": walkin_id}), {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Walk-in not found")
    ctx = {"customer_name": (doc.get("customer_name") or "there").split()[0], "salesperson_name": doc.get("salesperson_name") or ""}
    now = now_iso()
    await db.walkins.update_one({"id": walkin_id}, {"$set": {"updated_at": now}})
    if channel == "whatsapp":
        msg = build_message("walk_in", doc.get("customer_phone"), ctx)
        return {"channel": "whatsapp", "message": msg["message"], "wa_url": msg["url"]}
    cust = await db.customers.find_one({"id": doc["customer_id"]}, {"_id": 0, "email": 1})
    email = build_email("quotation", cust.get("email") if cust else None, {**ctx, "quotation_number": ""})
    return {"channel": "email", **email}
