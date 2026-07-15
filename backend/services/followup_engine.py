"""Follow-ups · Sales Command Center — deterministic scoring + idempotent
reconciliation engine.

NOTHING here calls an LLM. Every score, bucket and recommendation is a plain
explainable rule over real data already living in `quotations`, `payments`,
`purchase_orders` and `customers`. Reuses the existing payment aggregation
helpers from routes/payment_routes.py instead of re-deriving outstanding
balances — per architecture rule, no duplicate business logic.

reconcile_followups() is the single write path for AUTOMATED rows. It is
idempotent: re-running it never duplicates a card (dedupe key = source_key),
refreshes the score/reason of still-valid cards, and auto-resolves cards whose
trigger condition no longer holds (e.g. a payment got fully collected).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from db import db
from models import Followup, now_iso
from services.activity_log import log_event
from services.notifications import notify

IST = timezone(timedelta(hours=5, minutes=30))

# Mutually-exclusive day windows so payment_overdue / payment_partial never
# both fire for the same order.
PAYMENT_OVERDUE_DAYS = 5
QUOTATION_INACTIVE_DAYS = 3
QUOTATION_NEW_WINDOW_DAYS = 2
CUSTOMER_INACTIVE_DAYS = 21
DELIVERED_RECENCY_DAYS = 5

RULE_DEFINITIONS = [
    {"rule_type": "quotation_new", "label": "New quotation", "category": "quotation",
     "description": "Fires within ~2 days of a quotation being created — strike while interest is highest."},
    {"rule_type": "quotation_inactive", "label": "Quotation inactive", "category": "quotation",
     "description": f"No status change for {QUOTATION_INACTIVE_DAYS}+ days on a sent quotation."},
    {"rule_type": "quotation_expiring", "label": "Quotation expiring", "category": "quotation",
     "description": "Valid-until date falls within the next 3 days."},
    {"rule_type": "quotation_expired", "label": "Quotation expired", "category": "quotation",
     "description": "Valid-until date has passed but the quotation is still open."},
    {"rule_type": "payment_overdue", "label": "Payment overdue", "category": "payment",
     "description": f"Outstanding balance {PAYMENT_OVERDUE_DAYS}+ days after order confirmation."},
    {"rule_type": "payment_partial", "label": "Partial payment", "category": "payment",
     "description": "Some payment received; balance still pending, still fresh."},
    {"rule_type": "purchase_dispatched", "label": "Purchase dispatched", "category": "dispatch",
     "description": "Goods have shipped but not every line is delivered yet."},
    {"rule_type": "purchase_delivered", "label": "Purchase delivered", "category": "delivery",
     "description": f"All items delivered within the last {DELIVERED_RECENCY_DAYS} days."},
    {"rule_type": "customer_inactive", "label": "Customer inactive", "category": "sales",
     "description": f"No quotation activity for {CUSTOMER_INACTIVE_DAYS}+ days."},
    {"rule_type": "shortage_reorder", "label": "Awaiting reorder", "category": "purchase",
     "description": "A transfer left this customer's original order under-fulfilled — recommend a reorder PO."},
]


# ─────────────────────────────────────────────────────────────────────────────
# Small date helpers (all UTC storage; bucketing is IST-aware for a good feel)
# ─────────────────────────────────────────────────────────────────────────────
def parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


def age_days(dt: Optional[datetime]) -> int:
    if not dt:
        return 0
    now = datetime.now(timezone.utc)
    return max(0, (now - dt).days)


def money_short(v: float) -> str:
    v = float(v or 0)
    if v >= 100000:
        return f"{v / 100000:.1f}L"
    if v >= 1000:
        return f"{v / 1000:.0f}K"
    return f"{int(v)}"


def ist_day_bounds_utc(offset_days: int = 0) -> tuple[datetime, datetime]:
    """UTC [start, end) of "today + offset_days" measured in IST — used so
    daily insight counters line up with the salesperson's actual day."""
    now_ist = datetime.now(timezone.utc).astimezone(IST) + timedelta(days=offset_days)
    start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    end_ist = start_ist + timedelta(days=1)
    return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)


def compute_bucket(f: dict) -> str:
    """Overdue | today | tomorrow | this_week | later | completed | snoozed."""
    status = f.get("status")
    if status in ("done", "dismissed"):
        return "completed"
    if status == "snoozed" and f.get("snoozed_until"):
        return "snoozed"
    due = parse_iso(f.get("due_at"))
    if not due:
        return "later"
    now = datetime.now(timezone.utc)
    due_date = due.astimezone(IST).date()
    today_date = now.astimezone(IST).date()
    delta = (due_date - today_date).days
    if delta < 0:
        return "overdue"
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if delta <= 7:
        return "this_week"
    return "later"


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic scoring — explainable, no LLM. See PRD for weight rationale:
# value (0-25) + silence (0-20) + urgency (0-35, rule-specific) + tier (0-10).
# ─────────────────────────────────────────────────────────────────────────────
def score_followup(value: float, days_since_contact: int, urgency_pts: int, tier: str) -> tuple[int, str]:
    value_pts = min(25, round((value or 0) / 100000 * 4))
    contact_pts = min(20, days_since_contact * 2)
    tier_pts = {"vip": 10, "trade": 5, "retail": 0}.get(tier, 0)
    urgency_pts = min(35, max(0, urgency_pts))
    score = int(min(100, value_pts + contact_pts + urgency_pts + tier_pts))
    level = "critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 35 else "low"
    return score, level


def reason_factors_for(value: float, days_since_contact: int, urgency_bullet: str, tier: str) -> list[str]:
    out: list[str] = []
    if value and value >= 10000:
        out.append(f"₹{money_short(value)} at stake")
    if days_since_contact >= 2:
        out.append(f"No contact for {days_since_contact} days")
    if urgency_bullet:
        out.append(urgency_bullet)
    if tier == "vip":
        out.append("VIP customer")
    elif tier == "trade":
        out.append("Trade customer")
    return out


def build_whatsapp_message(f: dict) -> str:
    """Generic, honest message builder — no fabricated tracking claims."""
    name = (f.get("customer_name") or "there").split()[0]
    category = f.get("category")
    lines: list[str]
    if category == "payment":
        lines = [
            f"Hi {name},",
            "",
            f"This is a reminder regarding order {f.get('quotation_number') or ''}.",
            f"Outstanding balance: ₹{money_short(f.get('value', 0))}.",
            "",
            "Kindly share the payment update at your convenience. Thank you!",
            "— BuildCon House",
        ]
    elif category == "quotation":
        lines = [
            f"Hi {name},",
            "",
            f"Following up on quotation {f.get('quotation_number') or ''}.",
            f.get("reason") or "",
            "",
            "Happy to answer any questions or share a revised quote.",
            "— BuildCon House",
        ]
    elif category in ("dispatch", "delivery"):
        lines = [f"Hi {name},", "", f.get("reason") or "", "", "— BuildCon House"]
    else:
        lines = [f"Hi {name},", "", f.get("reason") or "Just checking in!", "", "— BuildCon House"]
    return "\n".join([line for line in lines if line is not None])


async def last_contact_map(customer_ids: list[str]) -> dict[str, datetime]:
    if not customer_ids:
        return {}
    docs = await db.followups.find(
        {"customer_id": {"$in": customer_ids}, "last_contacted_at": {"$ne": None}},
        {"_id": 0, "customer_id": 1, "last_contacted_at": 1},
    ).to_list(10000)
    out: dict[str, datetime] = {}
    for d in docs:
        dt = parse_iso(d.get("last_contacted_at"))
        if dt and (d["customer_id"] not in out or dt > out[d["customer_id"]]):
            out[d["customer_id"]] = dt
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Reconciliation — the single write path for automated cards.
# ─────────────────────────────────────────────────────────────────────────────
async def reconcile_followups() -> dict:
    from routes.payment_routes import ORDER_STATUSES, _paid_by_quotation  # local import avoids cycle at module load

    now = datetime.now(timezone.utc)

    customers = {c["id"]: c async for c in db.customers.find({}, {"_id": 0})}
    quotations = await db.quotations.find({}, {"_id": 0}).to_list(10000)
    quotation_ids = [q["id"] for q in quotations]
    paid_map = await _paid_by_quotation(quotation_ids)
    contact_map = await last_contact_map(list(customers.keys()))

    desired: dict[str, dict] = {}

    def upsert(
        key: str, rule_type: str, category: str, customer: dict, *,
        quotation: Optional[dict] = None, purchase: Optional[dict] = None,
        value: float = 0.0, due_at: Optional[str] = None,
        urgency_bullet: str = "", urgency_pts: int = 15,
        reason: str = "", next_action: str = "", next_action_reason: str = "",
        channel: str = "call", tags: Optional[list[str]] = None,
        days_since_contact: int = 0,
    ) -> None:
        tier = customer.get("tier", "retail")
        score, level = score_followup(value, days_since_contact, urgency_pts, tier)
        factors = reason_factors_for(value, days_since_contact, urgency_bullet, tier)
        desired[key] = {
            "rule_type": rule_type, "category": category,
            "customer_id": customer["id"],
            "customer_name": customer.get("company") or customer.get("name"),
            "customer_phone": customer.get("phone"), "customer_tier": tier,
            "quotation_id": quotation.get("id") if quotation else None,
            "quotation_number": quotation.get("number") if quotation else None,
            "purchase_id": purchase.get("id") if purchase else None,
            "purchase_number": purchase.get("number") if purchase else None,
            "project_name": (quotation or {}).get("project_name"),
            "value": round(value, 2), "reason": reason, "reason_factors": factors,
            "next_action": next_action, "next_action_reason": next_action_reason,
            "suggested_channel": channel, "priority_score": score, "priority_level": level,
            "tags": tags or [], "due_at": due_at or now_iso(),
        }

    # ---- Quotation-based rules ------------------------------------------------
    for q in quotations:
        cust = customers.get(q.get("customer_id"))
        if not cust or not q.get("items"):
            continue
        tier = cust.get("tier", "retail")
        value = float(q.get("grand_total") or 0)
        status = q.get("status")
        created_at = parse_iso(q.get("created_at"))
        updated_at = parse_iso(q.get("updated_at")) or created_at
        last_contact = contact_map.get(cust["id"]) or updated_at
        days_since_contact = age_days(last_contact)
        tags = [tier.upper()] + ([q["reference_source"]] if q.get("reference_source") else [])

        if status in ("draft", "sent", "pending_approval"):
            age_created = age_days(created_at)
            age_updated = age_days(updated_at)
            if age_created <= QUOTATION_NEW_WINDOW_DAYS:
                upsert(
                    f"quotation_new:{q['id']}", "quotation_new", "quotation", cust,
                    quotation=q, value=value,
                    due_at=((created_at or now) + timedelta(hours=6)).isoformat(),
                    urgency_bullet="Fresh quotation — high intent window", urgency_pts=18,
                    reason=f"New quotation just created — ₹{money_short(value)}. Reach out while interest is high.",
                    next_action="Call customer",
                    next_action_reason="Fresh quotation — strike while interest is highest.",
                    channel="call", tags=tags, days_since_contact=days_since_contact,
                )
            elif age_updated >= QUOTATION_INACTIVE_DAYS:
                upsert(
                    f"quotation_inactive:{q['id']}", "quotation_inactive", "quotation", cust,
                    quotation=q, value=value, due_at=now_iso(),
                    urgency_bullet=f"No response for {age_updated} days", urgency_pts=18,
                    reason=f"No response for {age_updated} days on a ₹{money_short(value)} quotation.",
                    next_action="Send WhatsApp",
                    next_action_reason="Customer has gone quiet — a nudge message often revives cold quotes.",
                    channel="whatsapp", tags=tags, days_since_contact=days_since_contact,
                )

        if status in ("sent", "pending_approval", "approved") and q.get("valid_until"):
            valid_until = parse_iso(q["valid_until"])
            if valid_until:
                days_left = (valid_until.astimezone(IST).date() - now.astimezone(IST).date()).days
                if 0 <= days_left <= 3:
                    label = "today" if days_left == 0 else "tomorrow" if days_left == 1 else f"in {days_left} days"
                    urgency = {0: 35, 1: 32, 2: 26, 3: 20}.get(days_left, 15)
                    upsert(
                        f"quotation_expiring:{q['id']}", "quotation_expiring", "quotation", cust,
                        quotation=q, value=value, due_at=valid_until.isoformat(),
                        urgency_bullet=f"Quotation expires {label}", urgency_pts=urgency,
                        reason=f"Quotation expires {label} — ₹{money_short(value)}.",
                        next_action="Call customer",
                        next_action_reason=f"Quotation expires {label} — confirm before it lapses.",
                        channel="call", tags=tags, days_since_contact=days_since_contact,
                    )
                elif -14 <= days_left < 0:
                    days_expired = abs(days_left)
                    upsert(
                        f"quotation_expired:{q['id']}", "quotation_expired", "quotation", cust,
                        quotation=q, value=value, due_at=valid_until.isoformat(),
                        urgency_bullet=f"Quotation expired {days_expired}d ago", urgency_pts=34,
                        reason=f"Quotation expired {days_expired} day(s) ago — still open at ₹{money_short(value)}.",
                        next_action="Share revised quotation",
                        next_action_reason="Original quotation has lapsed — send a fresh one to re-engage.",
                        channel="whatsapp", tags=tags, days_since_contact=days_since_contact,
                    )

        if status in ORDER_STATUSES:
            paid = paid_map.get(q["id"], 0.0)
            outstanding = max(0.0, value - paid)
            if outstanding > 1e-6:
                days_since_confirm = age_days(updated_at)
                if days_since_confirm >= PAYMENT_OVERDUE_DAYS:
                    days_overdue = days_since_confirm - PAYMENT_OVERDUE_DAYS
                    channel = "call" if tier == "vip" else "whatsapp"
                    upsert(
                        f"payment_overdue:{q['id']}", "payment_overdue", "payment", cust,
                        quotation=q, value=outstanding,
                        due_at=((updated_at or now) + timedelta(days=PAYMENT_OVERDUE_DAYS)).isoformat(),
                        urgency_bullet=f"Payment overdue by {max(days_overdue,1)}d", urgency_pts=20 + min(15, days_overdue * 2),
                        reason=f"₹{money_short(outstanding)} overdue by {max(days_overdue,1)} day(s) on {q.get('number')}.",
                        next_action="Call customer" if tier == "vip" else "Send WhatsApp reminder",
                        next_action_reason=f"₹{money_short(outstanding)} outstanding for over {PAYMENT_OVERDUE_DAYS} days.",
                        channel=channel, tags=tags, days_since_contact=days_since_contact,
                    )
                elif paid > 0:
                    upsert(
                        f"payment_partial:{q['id']}", "payment_partial", "payment", cust,
                        quotation=q, value=outstanding, due_at=now_iso(),
                        urgency_bullet=f"Partial payment — ₹{money_short(outstanding)} remaining", urgency_pts=14,
                        reason=f"Partial payment received — ₹{money_short(outstanding)} balance remaining on {q.get('number')}.",
                        next_action="Send WhatsApp reminder",
                        next_action_reason="Gentle nudge for the remaining balance.",
                        channel="whatsapp", tags=tags, days_since_contact=days_since_contact,
                    )

    # ---- Purchase-based rules ---------------------------------------------------
    pos = await db.purchase_orders.find({"status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(10000)
    for po in pos:
        cust = customers.get(po.get("customer_id"))
        items = po.get("items") or []
        if not cust or not items:
            continue
        tier = cust.get("tier", "retail")
        last_contact = contact_map.get(cust["id"]) or parse_iso(po.get("updated_at"))
        days_since_contact = age_days(last_contact)
        tags = [tier.upper()]
        value = float(po.get("grand_total") or 0)
        dispatched = [i for i in items if i.get("stage") in ("dispatched", "in_transit")]
        delivered = [i for i in items if i.get("stage") == "delivered"]

        if dispatched and len(delivered) < len(items):
            upsert(
                f"purchase_dispatched:{po['id']}", "purchase_dispatched", "dispatch", cust,
                purchase=po, value=value, due_at=now_iso(),
                urgency_bullet="Order dispatched — inform customer", urgency_pts=16,
                reason=f"{po.get('number')} is dispatched — let the customer know it's on the way.",
                next_action="Send WhatsApp",
                next_action_reason="Customers appreciate a heads-up the moment goods ship.",
                channel="whatsapp", tags=tags, days_since_contact=days_since_contact,
            )

        if items and len(delivered) == len(items):
            moved_ats = [parse_iso(i.get("last_moved_at")) or parse_iso(po.get("updated_at")) for i in delivered]
            moved_ats = [m for m in moved_ats if m]
            most_recent = max(moved_ats) if moved_ats else None
            if most_recent and age_days(most_recent) <= DELIVERED_RECENCY_DAYS:
                upsert(
                    f"purchase_delivered:{po['id']}", "purchase_delivered", "delivery", cust,
                    purchase=po, value=value, due_at=now_iso(),
                    urgency_bullet="Delivered — great moment to reconnect", urgency_pts=12,
                    reason=f"{po.get('number')} was delivered — confirm everything arrived well.",
                    next_action="Call customer",
                    next_action_reason="Delivery complete — the ideal moment to check satisfaction and ask for referrals.",
                    channel="call", tags=tags, days_since_contact=days_since_contact,
                )

    # ---- Shortage-reorder rule (transfer left a customer under-fulfilled) ------
    quotations_by_id = {q["id"]: q for q in quotations}
    shortages = await db.purchase_shortages.find({"status": "awaiting_reorder"}, {"_id": 0}).to_list(2000)
    for s in shortages:
        cust = customers.get(s.get("customer_id"))
        if not cust:
            continue
        tier = cust.get("tier", "retail")
        sq = quotations_by_id.get(s.get("quotation_id"))
        unit_price = 0.0
        if sq:
            line = next((l for l in sq.get("items", []) if l.get("id") == s.get("quotation_line_id")), None)
            if line:
                unit_price = float(line.get("unit_price") or 0)
        value = round(unit_price * float(s.get("shortage_qty") or 0), 2)
        last_contact = contact_map.get(cust["id"]) or parse_iso(s.get("updated_at"))
        days_since_contact = age_days(last_contact)
        shortage_qty = s.get("shortage_qty") or 0
        upsert(
            f"shortage_reorder:{s['id']}", "shortage_reorder", "purchase", cust,
            quotation=sq, value=value, due_at=now_iso(),
            urgency_bullet=f"{shortage_qty:g} unit(s) awaiting reorder", urgency_pts=22,
            reason=(
                f"{shortage_qty:g} × {s.get('name')} still owed after transferring stock to "
                f"{s.get('transferred_to_customer_name') or 'another customer'} — reorder to fulfil "
                f"{cust.get('company') or cust.get('name')}."
            ),
            next_action="Create purchase order",
            next_action_reason="Stock was reallocated to another customer — this order is now short.",
            channel="call", tags=[tier.upper(), "SHORTAGE"], days_since_contact=days_since_contact,
        )

    # ---- Customer-inactivity rule -----------------------------------------------
    quotations_by_customer: dict[str, list[dict]] = {}
    for q in quotations:
        quotations_by_customer.setdefault(q["customer_id"], []).append(q)

    for cid, cust in customers.items():
        cqs = quotations_by_customer.get(cid)
        if not cqs:
            continue
        touches = [parse_iso(q.get("updated_at")) for q in cqs]
        touches = [t for t in touches if t]
        if not touches:
            continue
        last_touch = max(touches)
        days_silent = age_days(last_touch)
        if days_silent >= CUSTOMER_INACTIVE_DAYS:
            last_q = max(cqs, key=lambda q: q.get("updated_at") or "")
            value = float(last_q.get("grand_total") or 0)
            upsert(
                f"customer_inactive:{cid}", "customer_inactive", "sales", cust,
                quotation=last_q, value=value, due_at=now_iso(),
                urgency_bullet=f"No activity for {days_silent} days", urgency_pts=15,
                reason=f"No activity for {days_silent} days — last quotation was ₹{money_short(value)}.",
                next_action="Call customer",
                next_action_reason="Reconnect before they choose another vendor.",
                channel="call", tags=[cust.get("tier", "retail").upper()], days_since_contact=days_silent,
            )

    # ---- Persist: upsert desired, auto-resolve stale --------------------------
    existing = await db.followups.find(
        {"is_automated": True, "status": {"$in": ["open", "snoozed"]}}, {"_id": 0},
    ).to_list(10000)
    existing_by_key = {f["source_key"]: f for f in existing if f.get("source_key")}
    quotation_created_by = {q["id"]: q.get("created_by") for q in quotations}

    created = updated = resolved = 0
    for key, fields in desired.items():
        ex = existing_by_key.pop(key, None)
        if ex:
            if ex.get("status") == "open":
                patch = {k: v for k, v in fields.items() if k != "due_at"}
                patch["updated_at"] = now_iso()
                await db.followups.update_one({"id": ex["id"]}, {"$set": patch})
                updated += 1
            # snoozed rows are left completely untouched — respect the snooze.
        else:
            f = Followup(source_key=key, is_automated=True, **fields)
            await db.followups.insert_one(f.dict())
            created += 1
            # Nudge the rep who owns this customer's quotation the moment a
            # new high-priority follow-up appears — this is the ONLY place
            # in the app that ever wrote a Notification before this fix
            # existed only as a one-time demo seed.
            if fields.get("priority_level") in ("critical", "high"):
                recipient = quotation_created_by.get(fields.get("quotation_id"))
                asyncio.create_task(notify(
                    recipient,
                    f"Follow-up needed · {fields.get('customer_name')}",
                    body=fields.get("reason"),
                    kind="warning" if fields.get("priority_level") == "critical" else "info",
                    link=f"/customers/{fields.get('customer_id')}",
                ))

    for _key, ex in existing_by_key.items():
        await db.followups.update_one({"id": ex["id"]}, {"$set": {
            "status": "done", "auto_resolved": True, "completed_at": now_iso(),
            "resolution_note": "Resolved automatically — the trigger condition no longer applies.",
            "updated_at": now_iso(),
        }})
        resolved += 1
        await log_event(
            event_type="followup.auto_resolved", entity_type="followup", entity_id=ex["id"],
            customer_id=ex.get("customer_id"), quotation_id=ex.get("quotation_id"), purchase_id=ex.get("purchase_id"),
            actor_name="Automation", summary=f"Follow-up resolved automatically — {ex.get('reason')}",
        )

    return {"created": created, "updated": updated, "auto_resolved": resolved, "active": len(desired)}
