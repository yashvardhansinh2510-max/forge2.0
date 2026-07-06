"""Follow-ups · Sales Command Center — the API surface.

Reuses existing collections/helpers everywhere possible:
  * payment aggregation  -> routes.payment_routes._paid_by_quotation / ORDER_STATUSES / _clean_phone
  * timeline             -> services.activity_log.timeline_for
  * scoring / reconcile   -> services.followup_engine

No new business logic is duplicated — this module is orchestration + reads.
"""
from __future__ import annotations

import csv
import io
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from auth import get_current_user
from db import db
from models import (
    Followup, FollowupCallOutcomePayload, FollowupCompletePayload,
    FollowupContactPayload, FollowupCreate, FollowupSavedView,
    FollowupSavedViewCreate, FollowupSnoozePayload, FollowupUpdate,
    UserPublic, now_iso,
)
from services.activity_log import log_event, timeline_for
from services.followup_engine import (
    RULE_DEFINITIONS, age_days, build_whatsapp_message, compute_bucket,
    ist_day_bounds_utc, money_short, parse_iso, reason_factors_for,
    reconcile_followups, score_followup,
)

router = APIRouter(prefix="/followups", tags=["followups"])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
async def _wake_snoozed() -> None:
    """Self-healing: any snooze whose timer has elapsed flips back to open so
    it resurfaces in the inbox without needing a background job."""
    await db.followups.update_many(
        {"status": "snoozed", "snoozed_until": {"$lte": now_iso()}},
        {"$set": {"status": "open", "updated_at": now_iso()}},
    )


async def _all_with_bucket() -> list[dict]:
    docs = await db.followups.find({}, {"_id": 0}).to_list(10000)
    for d in docs:
        d["bucket"] = compute_bucket(d)
        d["effective_priority_level"] = d.get("manual_priority_override") or d.get("priority_level")
    return docs


async def _rule_counts() -> dict[str, int]:
    pipeline = [
        {"$match": {"status": {"$in": ["open", "snoozed"]}}},
        {"$group": {"_id": "$rule_type", "count": {"$sum": 1}}},
    ]
    rows = await db.followups.aggregate(pipeline).to_list(30)
    return {r["_id"]: r["count"] for r in rows}


def _get(d: dict, key: str, default=None):
    return d.get(key, default)


# ─────────────────────────────────────────────────────────────────────────────
# Automation
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/reconcile")
async def reconcile(_: UserPublic = Depends(get_current_user)):
    return await reconcile_followups()


@router.get("/config/rules")
async def rules_config(_: UserPublic = Depends(get_current_user)):
    counts = await _rule_counts()
    return [{**r, "active_count": counts.get(r["rule_type"], 0)} for r in RULE_DEFINITIONS]


@router.get("/config/assignees")
async def assignees(_: UserPublic = Depends(get_current_user)):
    return await db.users.find(
        {"active": True}, {"_id": 0, "id": 1, "full_name": 1, "role": 1},
    ).sort("full_name", 1).to_list(100)


# ─────────────────────────────────────────────────────────────────────────────
# KPIs / Today's Mission / Insights — all literal paths, MUST precede /{id}
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/stats")
async def stats(_: UserPublic = Depends(get_current_user)):
    await _wake_snoozed()
    docs = await _all_with_bucket()

    counts = {b: 0 for b in ("overdue", "today", "tomorrow", "this_week", "later", "completed", "snoozed")}
    overdue_critical = 0
    for d in docs:
        counts[d["bucket"]] = counts.get(d["bucket"], 0) + 1
        if d["bucket"] == "overdue" and d["effective_priority_level"] in ("critical", "high"):
            overdue_critical += 1

    today_critical = sum(1 for d in docs if d["bucket"] == "today" and d["effective_priority_level"] == "critical")
    waiting_for_customer = sum(
        1 for d in docs if d.get("status") == "open" and d.get("rule_type") in ("quotation_inactive", "payment_partial")
    )

    # Split "overdue" into payment-specific vs generic — fixes the "which
    # payment is overdue" 5-second-scan gap identified in the UX audit.
    overdue_payments_count = sum(1 for d in docs if d.get("status") == "open" and d.get("rule_type") == "payment_overdue")
    overdue_payments_amount = sum(
        d.get("value", 0) for d in docs if d.get("status") == "open" and d.get("rule_type") == "payment_overdue"
    )
    expiring_quotations_count = sum(
        1 for d in docs if d.get("status") == "open" and d.get("rule_type") == "quotation_expiring"
    )

    start, _end = ist_day_bounds_utc(0)
    y_start, y_end = ist_day_bounds_utc(-1)
    completed_today = sum(1 for d in docs if d.get("completed_at") and d["completed_at"] >= start.isoformat())
    completed_yesterday = sum(
        1 for d in docs if d.get("completed_at") and y_start.isoformat() <= d["completed_at"] < y_end.isoformat()
    )

    rules = await _rule_counts()
    return {
        "today_tasks": counts["today"], "today_critical": today_critical,
        "overdue": counts["overdue"], "overdue_critical": overdue_critical,
        "overdue_payments_count": overdue_payments_count,
        "overdue_payments_amount": round(overdue_payments_amount, 2),
        "overdue_payments_amount_short": money_short(overdue_payments_amount),
        "expiring_quotations_count": expiring_quotations_count,
        "tomorrow": counts["tomorrow"],
        "this_week": counts["this_week"],
        "waiting_for_customer": waiting_for_customer,
        "completed_today": completed_today,
        "completed_trend": completed_today - completed_yesterday,
        "snoozed": counts["snoozed"],
        "later": counts["later"],
        "rules": [{**r, "active_count": rules.get(r["rule_type"], 0)} for r in RULE_DEFINITIONS],
    }


@router.get("/mission")
async def mission(user: UserPublic = Depends(get_current_user)):
    await _wake_snoozed()
    docs = await _all_with_bucket()
    actionable = [d for d in docs if d["bucket"] in ("overdue", "today")]

    revenue_at_risk = sum(d.get("value", 0) for d in actionable)
    overdue_payments = sum(1 for d in actionable if d["rule_type"] == "payment_overdue")
    expiring_today = sum(1 for d in docs if d["rule_type"] == "quotation_expiring" and d["bucket"] == "today")
    critical_count = sum(1 for d in actionable if d["effective_priority_level"] == "critical")

    minutes = 0
    for d in actionable:
        minutes += 6 if d["suggested_channel"] == "call" else 2 if d["suggested_channel"] == "whatsapp" else 3

    top = sorted(actionable, key=lambda d: -(d.get("priority_score") or 0))[:3]
    return {
        "due_count": len(actionable),
        "revenue_at_risk": round(revenue_at_risk, 2),
        "revenue_at_risk_short": money_short(revenue_at_risk),
        "overdue_payments": overdue_payments,
        "quotations_expiring_today": expiring_today,
        "critical_count": critical_count,
        "estimated_minutes": minutes,
        "top_priorities": [
            {"id": d["id"], "customer_name": d["customer_name"], "reason": d["reason"], "priority_score": d["priority_score"]}
            for d in top
        ],
        "greeting_name": (user.full_name or "").split()[0] if user.full_name else "there",
    }


@router.get("/insights")
async def insights(_: UserPublic = Depends(get_current_user)):
    start, end = ist_day_bounds_utc(0)
    rng = {"$gte": start.isoformat(), "$lt": end.isoformat()}

    calls = await db.activity_events.count_documents({"event_type": "followup.call_logged", "created_at": rng})
    whatsapps = await db.activity_events.count_documents({
        "event_type": "followup.contacted", "payload.channel": "whatsapp", "created_at": rng,
    })
    pay_docs = await db.payments.find({"paid_at": rng}, {"_id": 0, "amount": 1}).to_list(1000)
    payments_collected = sum(p.get("amount", 0) for p in pay_docs)
    quotations_approved = await db.quotations.count_documents({
        "status": {"$in": ["approved", "won"]}, "updated_at": rng,
    })
    completed_today = await db.followups.count_documents({"completed_at": rng})
    still_open = await db.followups.count_documents({"status": {"$in": ["open", "snoozed"]}})
    response_rate = round(100 * completed_today / max(1, completed_today + still_open))

    return {
        "calls_completed": calls,
        "whatsapps_sent": whatsapps,
        "payments_collected": round(payments_collected, 2),
        "quotations_approved": quotations_approved,
        "response_rate": min(100, response_rate),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Export — CSV / Excel of the current filtered list. Saved Views — persisted
# filter configurations per user. Both literal-path routes; MUST precede /{id}.
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/export")
async def export_followups(
    format: str = Query("xlsx", regex="^(xlsx|csv)$"),
    bucket: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    customer_tier: Optional[str] = None,
    assigned_to: Optional[str] = None,
    q: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    rows = await list_followups(
        bucket=bucket, priority=priority, category=category, channel=None,
        customer_tier=customer_tier, assigned_to=assigned_to, q=q, limit=3000, _=_,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Customer", "Phone", "Type", "Reason", "Next Action", "Value", "Priority", "Score", "Due", "Status", "Assigned To"])
        for d in rows:
            writer.writerow([
                d.get("customer_name"), d.get("customer_phone"), d.get("category"), d.get("reason"),
                d.get("next_action"), d.get("value"), d.get("effective_priority_level") or d.get("priority_level"),
                d.get("priority_score"), d.get("due_at"), d.get("status"), d.get("assigned_to_name"),
            ])
        mem = io.BytesIO(buf.getvalue().encode("utf-8"))
        return StreamingResponse(mem, media_type="text/csv", headers={
            "Content-Disposition": f'attachment; filename="followups-{stamp}.csv"',
        })

    wb = Workbook()
    ws = wb.active
    ws.title = "Follow-ups"
    ws["A1"] = "BuildCon House — Follow-ups Export"
    ws["A1"].font = Font(bold=True, size=14)
    ws.merge_cells("A1:K1")
    ws["A2"] = f"{len(rows)} follow-ups · Exported {datetime.now(timezone.utc).strftime('%d %b %Y · %H:%M UTC')}"
    ws["A2"].font = Font(color="6B7280", size=10)
    ws.merge_cells("A2:K2")

    headers = ["Customer", "Phone", "Type", "Reason", "Next Action", "Value (₹)", "Priority", "Score", "Due", "Status", "Assigned To"]
    header_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.font = Font(bold=True, color="374151", size=11)
        cell.fill = header_fill

    for i, d in enumerate(rows, start=5):
        ws.cell(row=i, column=1, value=d.get("customer_name"))
        ws.cell(row=i, column=2, value=d.get("customer_phone"))
        ws.cell(row=i, column=3, value=d.get("category"))
        ws.cell(row=i, column=4, value=d.get("reason"))
        ws.cell(row=i, column=5, value=d.get("next_action"))
        ws.cell(row=i, column=6, value=d.get("value"))
        ws.cell(row=i, column=7, value=(d.get("effective_priority_level") or d.get("priority_level")))
        ws.cell(row=i, column=8, value=d.get("priority_score"))
        ws.cell(row=i, column=9, value=d.get("due_at"))
        ws.cell(row=i, column=10, value=d.get("status"))
        ws.cell(row=i, column=11, value=d.get("assigned_to_name"))

    for i, w in enumerate([22, 16, 12, 44, 22, 12, 10, 8, 22, 12, 18], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A5"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
        "Content-Disposition": f'attachment; filename="followups-{stamp}.xlsx"',
    })


@router.get("/saved-views")
async def list_saved_views(user: UserPublic = Depends(get_current_user)):
    return await db.followup_saved_views.find({"user_id": user.id}, {"_id": 0}).sort("created_at", -1).to_list(50)


@router.post("/saved-views", response_model=FollowupSavedView)
async def create_saved_view(body: FollowupSavedViewCreate, user: UserPublic = Depends(get_current_user)):
    v = FollowupSavedView(user_id=user.id, name=body.name, filters=body.filters)
    await db.followup_saved_views.insert_one(v.dict())
    return v


@router.delete("/saved-views/{view_id}")
async def delete_saved_view(view_id: str, user: UserPublic = Depends(get_current_user)):
    await db.followup_saved_views.delete_one({"id": view_id, "user_id": user.id})
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# List
# ─────────────────────────────────────────────────────────────────────────────
@router.get("")
async def list_followups(
    bucket: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    channel: Optional[str] = None,
    customer_tier: Optional[str] = None,
    assigned_to: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(1000, ge=1, le=3000),
    _: UserPublic = Depends(get_current_user),
):
    await _wake_snoozed()
    query: dict = {}
    if category:
        query["category"] = category
    if channel:
        query["suggested_channel"] = channel
    if customer_tier:
        query["customer_tier"] = customer_tier
    if assigned_to:
        query["assigned_to"] = assigned_to
    if q:
        term = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [
            {"customer_name": term}, {"customer_phone": term}, {"quotation_number": term},
            {"purchase_number": term}, {"project_name": term}, {"reason": term}, {"tags": term},
        ]

    docs = await db.followups.find(query, {"_id": 0}).to_list(limit * 3)
    for d in docs:
        d["bucket"] = compute_bucket(d)
        d["effective_priority_level"] = d.get("manual_priority_override") or d.get("priority_level")

    if bucket and bucket != "all":
        docs = [d for d in docs if d["bucket"] == bucket]
    if priority:
        docs = [d for d in docs if d["effective_priority_level"] == priority]

    docs.sort(key=lambda d: (-(d.get("priority_score") or 0), d.get("due_at") or ""))
    return docs[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# Detail — powers the Customer Context Panel
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/{followup_id}")
async def get_detail(followup_id: str, _: UserPublic = Depends(get_current_user)):
    from routes.payment_routes import ORDER_STATUSES, _paid_by_quotation

    f = await db.followups.find_one({"id": followup_id}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    f["bucket"] = compute_bucket(f)
    f["effective_priority_level"] = f.get("manual_priority_override") or f.get("priority_level")

    customer = await db.customers.find_one({"id": f["customer_id"]}, {"_id": 0, "password_hash": 0}) or {}
    all_q = await db.quotations.find({"customer_id": f["customer_id"]}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    q_ids = [q["id"] for q in all_q]
    paid_map = await _paid_by_quotation(q_ids)

    lifetime_revenue = sum(q.get("grand_total", 0) for q in all_q if q.get("status") in ORDER_STATUSES)
    outstanding_total = sum(
        max(0.0, q.get("grand_total", 0) - paid_map.get(q["id"], 0.0)) for q in all_q if q.get("status") in ORDER_STATUSES
    )
    pending_quotations = [q for q in all_q if q.get("status") in ("draft", "sent", "pending_approval", "approved")]
    pending_orders = [
        q for q in all_q
        if q.get("status") in ORDER_STATUSES and (q.get("grand_total", 0) - paid_map.get(q["id"], 0.0)) > 1
    ]
    recent_payments = await db.payments.find({"customer_id": f["customer_id"]}, {"_id": 0}).sort("paid_at", -1).to_list(10)
    recent_purchases = await db.purchase_orders.find(
        {"customer_id": f["customer_id"]}, {"_id": 0},
    ).sort("updated_at", -1).to_list(10)
    timeline = await timeline_for(customer_id=f["customer_id"], limit=60)

    # ── Premium context additions (Follow-ups V2) — all derived from data
    # already loaded above, no new integration or LLM call needed. ──────────
    order_count = sum(1 for q in all_q if q.get("status") in ORDER_STATUSES)
    conversion_rate = round(100 * order_count / len(all_q)) if all_q else 0
    average_order_value = round(lifetime_revenue / order_count, 2) if order_count else 0.0
    creator_counts = Counter(q.get("created_by_name") for q in all_q if q.get("created_by_name"))
    preferred_salesperson = creator_counts.most_common(1)[0][0] if creator_counts else None

    last_touch_dt = None
    touches = [parse_iso(q.get("updated_at")) for q in all_q]
    touches = [t for t in touches if t]
    if touches:
        last_touch_dt = max(touches)
    days_silent = age_days(last_touch_dt) if last_touch_dt else 0
    has_overdue_payment = any(
        q.get("status") in ORDER_STATUSES and (q.get("grand_total", 0) - paid_map.get(q["id"], 0.0)) > 1
        and age_days(parse_iso(q.get("updated_at"))) >= 5
        for q in all_q
    )
    if has_overdue_payment:
        risk_level = "high"
    elif outstanding_total > 0 or days_silent >= 14:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "followup": f,
        "customer": customer,
        "stats": {
            "lifetime_revenue": round(lifetime_revenue, 2),
            "outstanding_total": round(outstanding_total, 2),
            "pending_quotations": len(pending_quotations),
            "pending_orders": len(pending_orders),
            "conversion_rate": conversion_rate,
            "average_order_value": average_order_value,
            "preferred_salesperson": preferred_salesperson,
            "risk_level": risk_level,
        },
        "quotations": [
            {"id": q["id"], "number": q["number"], "status": q["status"], "grand_total": q.get("grand_total", 0),
             "valid_until": q.get("valid_until"), "updated_at": q.get("updated_at")}
            for q in all_q[:12]
        ],
        "payments": recent_payments,
        "purchases": [
            {"id": p["id"], "number": p["number"], "status": p["status"], "grand_total": p.get("grand_total", 0),
             "updated_at": p.get("updated_at")}
            for p in recent_purchases
        ],
        "timeline": timeline,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Manual create + edit
# ─────────────────────────────────────────────────────────────────────────────
@router.post("", response_model=Followup)
async def create_followup(body: FollowupCreate, user: UserPublic = Depends(get_current_user)):
    cust = await db.customers.find_one({"id": body.customer_id}, {"_id": 0})
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    quotation = await db.quotations.find_one({"id": body.quotation_id}, {"_id": 0}) if body.quotation_id else None
    tier = cust.get("tier", "retail")
    value = float(quotation.get("grand_total", 0)) if quotation else 0.0
    score, level = score_followup(value, 0, 12, tier)

    assigned_to_name = user.full_name
    if body.assigned_to and body.assigned_to != user.id:
        au = await db.users.find_one({"id": body.assigned_to}, {"_id": 0, "full_name": 1})
        assigned_to_name = au["full_name"] if au else None

    action_label = {"call": "Call customer", "whatsapp": "Send WhatsApp", "email": "Send Email", "visit": "Schedule showroom visit"}
    f = Followup(
        source_key=None, rule_type="manual", category=body.category,
        customer_id=cust["id"], customer_name=cust.get("company") or cust.get("name"),
        customer_phone=cust.get("phone"), customer_tier=tier,
        quotation_id=quotation.get("id") if quotation else None,
        quotation_number=quotation.get("number") if quotation else None,
        purchase_id=body.purchase_id,
        value=value, reason=body.reason,
        reason_factors=reason_factors_for(value, 0, "Manual reminder", tier),
        next_action=action_label.get(body.channel, "Call customer"),
        next_action_reason=body.reason,
        suggested_channel=body.channel, priority_score=score,
        priority_level=body.priority_level or level,
        due_at=body.due_at or now_iso(), is_automated=False,
        assigned_to=body.assigned_to or user.id, assigned_to_name=assigned_to_name,
        notes=body.notes,
    )
    await db.followups.insert_one(f.dict())
    await log_event(
        event_type="followup.created", entity_type="followup", entity_id=f.id, actor=user,
        customer_id=f.customer_id, quotation_id=f.quotation_id,
        summary=f"Manual follow-up created — {f.reason}",
    )
    return f


@router.patch("/{followup_id}")
async def update_followup(followup_id: str, body: FollowupUpdate, user: UserPublic = Depends(get_current_user)):
    f = await db.followups.find_one({"id": followup_id}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    patch = body.dict(exclude_unset=True)
    if "assigned_to" in patch and patch["assigned_to"]:
        au = await db.users.find_one({"id": patch["assigned_to"]}, {"_id": 0, "full_name": 1})
        patch["assigned_to_name"] = au["full_name"] if au else None
        await log_event(
            event_type="followup.assigned", entity_type="followup", entity_id=followup_id, actor=user,
            customer_id=f.get("customer_id"),
            summary=f"Assigned to {patch.get('assigned_to_name') or '—'}",
        )
    if patch.get("status") == "dismissed":
        patch["completed_at"] = now_iso()
        patch["resolution_note"] = "Dismissed — not relevant"
        await log_event(
            event_type="followup.dismissed", entity_type="followup", entity_id=followup_id, actor=user,
            customer_id=f.get("customer_id"),
            summary=f"Follow-up dismissed — {f.get('reason')}",
        )
    if "notes" in patch and patch["notes"] and patch.get("status") != "dismissed" and "assigned_to" not in patch:
        await log_event(
            event_type="followup.note_added", entity_type="followup", entity_id=followup_id, actor=user,
            customer_id=f.get("customer_id"),
            summary=f"Note added: {patch['notes'][:120]}",
        )
    patch["updated_at"] = now_iso()
    await db.followups.update_one({"id": followup_id}, {"$set": patch})
    return await db.followups.find_one({"id": followup_id}, {"_id": 0})


# ─────────────────────────────────────────────────────────────────────────────
# Actions — snooze / complete / contact / call outcome
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/{followup_id}/snooze")
async def snooze_followup(followup_id: str, body: FollowupSnoozePayload, user: UserPublic = Depends(get_current_user)):
    f = await db.followups.find_one({"id": followup_id}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    now = datetime.now(timezone.utc)
    if body.until:
        until = parse_iso(body.until) or (now + timedelta(hours=1))
    elif body.minutes:
        until = now + timedelta(minutes=body.minutes)
    elif body.preset == "15m":
        until = now + timedelta(minutes=15)
    elif body.preset == "1h":
        until = now + timedelta(hours=1)
    elif body.preset == "tomorrow":
        until = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    elif body.preset == "next_week":
        until = (now + timedelta(days=7)).replace(hour=9, minute=0, second=0, microsecond=0)
    else:
        until = now + timedelta(hours=1)

    await db.followups.update_one({"id": followup_id}, {"$set": {
        "status": "snoozed", "snoozed_until": until.isoformat(), "updated_at": now_iso(),
    }})
    await log_event(
        event_type="followup.snoozed", entity_type="followup", entity_id=followup_id, actor=user,
        customer_id=f.get("customer_id"),
        summary=f"Snoozed until {until.strftime('%d %b, %I:%M %p')}",
    )
    return await db.followups.find_one({"id": followup_id}, {"_id": 0})


@router.post("/{followup_id}/complete")
async def complete_followup(followup_id: str, body: FollowupCompletePayload, user: UserPublic = Depends(get_current_user)):
    f = await db.followups.find_one({"id": followup_id}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    await db.followups.update_one({"id": followup_id}, {"$set": {
        "status": "done", "completed_at": now_iso(),
        "notes": body.notes if body.notes is not None else f.get("notes"),
        "updated_at": now_iso(),
    }})
    await log_event(
        event_type="followup.completed", entity_type="followup", entity_id=followup_id, actor=user,
        customer_id=f.get("customer_id"), quotation_id=f.get("quotation_id"), purchase_id=f.get("purchase_id"),
        summary=f"Follow-up marked complete — {f.get('reason')}",
    )
    return await db.followups.find_one({"id": followup_id}, {"_id": 0})


@router.post("/{followup_id}/contact")
async def contact_followup(followup_id: str, body: FollowupContactPayload, user: UserPublic = Depends(get_current_user)):
    from routes.payment_routes import _clean_phone

    f = await db.followups.find_one({"id": followup_id}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    now = now_iso()
    await db.followups.update_one({"id": followup_id}, {"$set": {"last_contacted_at": now, "updated_at": now}})
    await log_event(
        event_type="followup.contacted", entity_type="followup", entity_id=followup_id, actor=user,
        customer_id=f.get("customer_id"), quotation_id=f.get("quotation_id"), purchase_id=f.get("purchase_id"),
        payload={"channel": body.channel},
        summary=f"{body.channel.title()} — {f.get('customer_name')}",
    )
    phone = _clean_phone(f.get("customer_phone"))
    result: dict = {"channel": body.channel, "phone": phone}
    if body.channel == "whatsapp":
        msg = build_whatsapp_message(f)
        result["message"] = msg
        result["wa_url"] = f"https://wa.me/{phone}?text={quote_plus(msg)}" if phone else f"https://wa.me/?text={quote_plus(msg)}"
    elif body.channel == "email":
        cust = await db.customers.find_one({"id": f["customer_id"]}, {"_id": 0, "email": 1})
        result["email"] = cust.get("email") if cust else None
    return result


@router.post("/{followup_id}/log-call")
async def log_call(followup_id: str, body: FollowupCallOutcomePayload, user: UserPublic = Depends(get_current_user)):
    f = await db.followups.find_one({"id": followup_id}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    now_dt = datetime.now(timezone.utc)
    patch: dict = {
        "last_contacted_at": now_dt.isoformat(), "updated_at": now_iso(),
        "notes": body.notes if body.notes is not None else f.get("notes"),
    }
    next_created = None

    if body.outcome in ("interested", "call_back"):
        patch.update({"status": "done", "completed_at": now_iso(), "completed_outcome": body.outcome})
        due = now_dt + timedelta(days=1 if body.outcome == "call_back" else 2)
        nf = Followup(
            rule_type="manual", category=f.get("category", "general"),
            customer_id=f["customer_id"], customer_name=f["customer_name"], customer_phone=f.get("customer_phone"),
            customer_tier=f.get("customer_tier", "retail"), quotation_id=f.get("quotation_id"),
            quotation_number=f.get("quotation_number"), purchase_id=f.get("purchase_id"),
            purchase_number=f.get("purchase_number"), value=f.get("value", 0),
            reason=("Call back requested" if body.outcome == "call_back" else "Customer interested — follow up on their decision"),
            reason_factors=[f.get("reason", "")] if f.get("reason") else [],
            next_action="Call customer", next_action_reason="Scheduled automatically from the previous call outcome.",
            suggested_channel="call", priority_score=f.get("priority_score", 50), priority_level=f.get("priority_level", "medium"),
            due_at=due.isoformat(), is_automated=False,
            assigned_to=f.get("assigned_to") or user.id, assigned_to_name=f.get("assigned_to_name") or user.full_name,
            tags=f.get("tags", []),
        )
        await db.followups.insert_one(nf.dict())
        next_created = nf.id
    elif body.outcome == "no_answer":
        attempts = (f.get("contact_attempts") or 0) + 1
        patch["contact_attempts"] = attempts
        if attempts >= 2:
            # Escalate — stop same-day retries after the 2nd miss; push to
            # tomorrow morning and bump urgency so it doesn't get buried.
            next_due = (now_dt + timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0)
            bumped_score = min(100, (f.get("priority_score") or 0) + 10)
            bumped_level = "critical" if bumped_score >= 80 else "high" if bumped_score >= 60 else f.get("priority_level", "medium")
            patch["due_at"] = next_due.isoformat()
            patch["priority_score"] = bumped_score
            patch["priority_level"] = bumped_level
        else:
            patch["due_at"] = (now_dt + timedelta(hours=4)).isoformat()
    elif body.outcome == "rejected":
        patch.update({
            "status": "dismissed", "completed_at": now_iso(),
            "completed_outcome": "rejected", "resolution_note": "Customer rejected",
        })
    elif body.outcome == "converted":
        patch.update({
            "status": "done", "completed_at": now_iso(),
            "completed_outcome": "converted", "resolution_note": "Converted!",
        })

    await db.followups.update_one({"id": followup_id}, {"$set": patch})
    await log_event(
        event_type="followup.call_logged", entity_type="followup", entity_id=followup_id, actor=user,
        customer_id=f.get("customer_id"), quotation_id=f.get("quotation_id"), purchase_id=f.get("purchase_id"),
        payload={"outcome": body.outcome, "next_followup_id": next_created},
        summary=f"Call logged — {body.outcome.replace('_', ' ').title()}",
    )
    return await db.followups.find_one({"id": followup_id}, {"_id": 0})
