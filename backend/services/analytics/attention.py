"""The Attention Center (spec §9) — only problems, each with a ₹ impact, an
age, and a one-click destination that resolves it.

Every rule is a PURE function over already-fetched rows. Nothing here touches
Mongo: `gather.py` is the only module that reads, so every query goes through
Phase 0's `build_match` and no rule can quietly bypass floor scoping.

Two invariants hold across every rule:

  * A rule never emits a row with `impact <= 0`. Rows are ranked by rupees, so
    a row without any is unrankable and tells the owner nothing.
  * A rule never fires on an unknown age. Real documents predate half these
    fields, and treating a missing timestamp as infinitely old would fill the
    owner's most important screen with false alarms.

Comparison-based rules (brand decline, referrer quiet) are SUPPRESSED when the
prior window does not exist, rather than fired on a fabricated delta — the same
honesty rule `periods.compare` follows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from services.analytics.rows import ActionRow, rank

# ---------------------------------------------------------------------------
# The one threshold block (spec §9). Never inline a threshold at a rule site:
# tuning the business's sensitivity must be a single-file edit.
# ---------------------------------------------------------------------------
THRESHOLDS: dict[str, float] = {
    "QUOTATION_STALE_DAYS": 7,
    "QUOTATION_HIGH_VALUE": 100000,
    # Overridden per request from settings.analytics_targets.payment_terms_days.
    "PAYMENT_OVERDUE_DAYS": 30,
    "DISPATCH_WAITING_DAYS": 3,
    "RELEASE_STUCK_DAYS": 5,
    "SALESPERSON_INACTIVE_DAYS": 5,
    # A follow-up two hours late IS overdue (health measures it that way), but
    # raising an alarm that fast would bury the owner. The alarm waits a full
    # day; the health signal does not. The difference is deliberate and lives
    # here rather than being an accident of day-granularity arithmetic.
    "FOLLOWUP_ALARM_GRACE_DAYS": 1,
    "SUPPLIER_DELAY_DAYS": 0,
    "BRAND_DECLINE_PCT": 25,
    "REFERRER_QUIET_DAYS": 60,
    "CUSTOMER_INACTIVE_DAYS": 180,
    # Opportunity rules (§10) draw from this same block — one place, not two.
    "BRAND_GROWTH_PCT": 25,
    "PARTNER_UNTOUCHED_DAYS": 14,
    "APPROVED_NOT_ORDERED_DAYS": 3,
    "WALKIN_UNQUOTED_DAYS": 14,
}

OPEN_QUOTATION_STATUSES = ("draft", "sent", "approved", "pending_approval")
SETTLED_PURCHASE_STATUSES = ("fully_received", "cancelled")


def age_days(stamp: str | None, now: datetime) -> int | None:
    """Whole days between an ISO timestamp and now, or None if unknowable.

    None is load-bearing: callers must treat it as "cannot judge", never as 0
    and never as infinity.
    """
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now.tzinfo)
    return max(0, (now - parsed).days)


def is_overdue(stamp: str | None, now: datetime) -> bool:
    """True the moment the deadline passes.

    Deliberately NOT day-granularity: `age_days` floors to whole days, so a
    follow-up due at 09:00 read at 15:00 has an age of 0 and would count as
    on time. Live verification found 115 of 246 open follow-ups in exactly
    that state, inflating the Health Score's follow-up signal to 46.7% when
    the honest figure was 0%.
    """
    if not stamp:
        return False
    try:
        parsed = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now.tzinfo)
    return parsed < now


def _money(value) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class AttentionInput:
    """Everything the rules need, already fetched and already floor-scoped."""

    quotations: list[dict] = field(default_factory=list)
    orders: list[dict] = field(default_factory=list)
    followups: list[dict] = field(default_factory=list)
    ready_items: list[dict] = field(default_factory=list)
    unreleased_items: list[dict] = field(default_factory=list)
    salespeople: list[dict] = field(default_factory=list)
    purchase_orders: list[dict] = field(default_factory=list)
    brands: list[dict] = field(default_factory=list)
    referrers: list[dict] = field(default_factory=list)


def _context(*pairs: tuple[str, object]) -> list[tuple[str, str]]:
    """Label/value pairs, dropping anything the record does not carry."""
    return [(label, str(value)) for label, value in pairs if value not in (None, "", 0)]


def quotation_stalled(quotations: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for q in quotations:
        if q.get("status") not in OPEN_QUOTATION_STATUSES:
            continue
        value = _money(q.get("grand_total"))
        if value < thresholds["QUOTATION_HIGH_VALUE"]:
            continue
        age = age_days(q.get("created_at"), now)
        if age is None or age <= thresholds["QUOTATION_STALE_DAYS"]:
            continue
        rows.append(ActionRow(
            rule="quotation_stalled",
            kind="attention",
            headline=f"Quotation pending {age} days",
            impact=value,
            age_days=age,
            context=_context(
                ("Customer", q.get("customer_name")),
                ("Architect", q.get("referrer_name")),
                ("Salesperson", q.get("created_by_name")),
                ("Days pending", age),
            ),
            destination=f"/(admin)/quotations/{q['id']}",
            actions=("open", "call", "whatsapp", "schedule_followup", "assign"),
            entity={
                "quotation_id": q["id"],
                "customer_id": q.get("customer_id") or "",
                "phone": q.get("customer_phone") or "",
            },
        ))
    return rows


def payment_overdue(orders: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for o in orders:
        outstanding = _money(o.get("grand_total")) - _money(o.get("collected"))
        if outstanding <= 0:
            continue
        age = age_days(o.get("ordered_at"), now)
        if age is None or age <= thresholds["PAYMENT_OVERDUE_DAYS"]:
            continue
        rows.append(ActionRow(
            rule="payment_overdue",
            kind="attention",
            headline=f"Payment overdue {age} days",
            impact=round(outstanding, 2),
            age_days=age,
            context=_context(
                ("Customer", o.get("customer_name")),
                ("Order", o.get("number")),
                ("Salesperson", o.get("created_by_name")),
            ),
            destination="/(admin)/payments",
            actions=("call", "send_reminder", "open_customer", "record_payment"),
            entity={
                "quotation_id": o["id"],
                "customer_id": o.get("customer_id") or "",
                "phone": o.get("customer_phone") or "",
            },
        ))
    return rows


def dispatch_waiting(ready_items: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for item in ready_items:
        value = _money(item.get("value"))
        if value <= 0:
            continue
        age = age_days(item.get("ready_at"), now)
        if age is None or age <= thresholds["DISPATCH_WAITING_DAYS"]:
            continue
        rows.append(ActionRow(
            rule="dispatch_waiting",
            kind="attention",
            headline=f"Customer waiting {age} days for dispatch",
            impact=value,
            age_days=age,
            context=_context(
                ("Customer", item.get("customer_name")),
                ("Boxes ready", item.get("boxes_ready")),
            ),
            destination="/(admin)/tiles/orders",
            actions=("open", "call"),
            entity={
                "purchase_order_id": item.get("purchase_order_id") or "",
                "customer_order_id": item.get("customer_order_id") or "",
            },
        ))
    return rows


def release_stuck(unreleased_items: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for item in unreleased_items:
        value = _money(item.get("value"))
        if value <= 0:
            continue
        age = age_days(item.get("ordered_at"), now)
        if age is None or age <= thresholds["RELEASE_STUCK_DAYS"]:
            continue
        rows.append(ActionRow(
            rule="release_stuck",
            kind="attention",
            headline=f"Material unreleased {age} days",
            impact=value,
            age_days=age,
            context=_context(
                ("Brand", item.get("brand_name")),
                ("Boxes pending", item.get("boxes_pending")),
            ),
            destination="/(admin)/tiles/orders",
            actions=("open",),
            entity={"purchase_order_id": item.get("purchase_order_id") or ""},
        ))
    return rows


def followup_overdue(followups: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for f in followups:
        if f.get("status") != "open":
            continue
        value = _money(f.get("value"))
        if value <= 0:
            continue
        age = age_days(f.get("due_at"), now)
        # The alarm waits out the grace period; the Health Score's follow-up
        # signal uses is_overdue() and does not. See FOLLOWUP_ALARM_GRACE_DAYS.
        if age is None or age < thresholds["FOLLOWUP_ALARM_GRACE_DAYS"]:
            continue
        rows.append(ActionRow(
            rule="followup_overdue",
            kind="attention",
            headline=f"Follow-up overdue {age} days",
            impact=value,
            age_days=age,
            context=_context(
                ("Customer", f.get("customer_name")),
                ("Reason", f.get("reason")),
                ("Assigned to", f.get("assigned_to_name")),
            ),
            destination="/(admin)/followups",
            actions=("call", "whatsapp", "schedule_followup", "assign"),
            entity={
                "followup_id": f["id"],
                "customer_id": f.get("customer_id") or "",
                "phone": f.get("customer_phone") or "",
            },
            # The real, already-stored followup_engine.score_followup output —
            # see the ActionRow docstring. Not recomputed here: the inputs
            # (days_since_contact, urgency_pts, tier) aren't in this dict, and
            # re-deriving them would risk a second implementation drifting
            # from the one the Follow-ups screen itself trusts.
            priority_score=f.get("priority_score"),
            reason_factors=tuple(f.get("reason_factors") or ()),
        ))
    return rows


def salesperson_inactive(salespeople: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for person in salespeople:
        pipeline = _money(person.get("open_pipeline"))
        if pipeline <= 0:
            continue
        age = age_days(person.get("last_activity_at"), now)
        if age is None or age <= thresholds["SALESPERSON_INACTIVE_DAYS"]:
            continue
        rows.append(ActionRow(
            rule="salesperson_inactive",
            kind="attention",
            headline=f"{person.get('full_name') or 'Salesperson'} inactive {age} days",
            impact=pipeline,
            age_days=age,
            context=_context(
                ("Salesperson", person.get("full_name")),
                ("Open pipeline", pipeline),
            ),
            destination="/(admin)/followups",
            actions=("open", "assign"),
            entity={"salesperson_id": person.get("id") or ""},
        ))
    return rows


def supplier_delayed(purchase_orders: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for po in purchase_orders:
        if po.get("status") in SETTLED_PURCHASE_STATUSES:
            continue
        value = _money(po.get("total"))
        if value <= 0:
            continue
        age = age_days(po.get("expected_delivery_at"), now)
        if age is None or age <= thresholds["SUPPLIER_DELAY_DAYS"]:
            continue
        rows.append(ActionRow(
            rule="supplier_delayed",
            kind="attention",
            headline=f"Supplier delayed {age} days",
            impact=value,
            age_days=age,
            context=_context(
                ("Supplier", po.get("supplier_name")),
                ("Purchase order", po.get("number")),
                ("Overdue by", f"{age} days"),
            ),
            destination="/(admin)/purchases",
            actions=("call", "send_reminder", "open_po"),
            entity={
                "purchase_order_id": po["id"],
                "supplier_id": po.get("supplier_id") or "",
                "phone": po.get("supplier_phone") or "",
            },
        ))
    return rows


def brand_declining(brands: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for brand in brands:
        # Suppressed, not fired with a history_state: §9 is explicit that a rule
        # without a comparable window does not produce a row at all.
        if not brand.get("prior_window_exists"):
            continue
        previous = _money(brand.get("previous"))
        if previous <= 0:
            continue
        current = _money(brand.get("revenue"))
        drop_pct = (previous - current) / previous * 100
        if drop_pct < thresholds["BRAND_DECLINE_PCT"]:
            continue
        rows.append(ActionRow(
            rule="brand_declining",
            kind="attention",
            headline=f"{brand.get('brand_name') or 'Brand'} down {round(drop_pct)}%",
            impact=round(previous - current, 2),
            age_days=None,
            context=_context(
                ("Brand", brand.get("brand_name")),
                ("This period", current),
                ("Previous period", previous),
            ),
            destination=f"/(admin)/sales-data/brands/{brand.get('brand_id') or ''}",
            actions=("open",),
            entity={"brand_id": brand.get("brand_id") or ""},
        ))
    return rows


def referrer_quiet(referrers: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for r in referrers:
        monthly = _money(r.get("monthly_revenue"))
        if monthly <= 0:
            continue
        age = age_days(r.get("last_referral_at"), now)
        if age is None or age <= thresholds["REFERRER_QUIET_DAYS"]:
            continue
        rows.append(ActionRow(
            rule="referrer_quiet",
            kind="attention",
            headline=f"No referral in {age} days",
            impact=monthly,
            age_days=age,
            context=_context(
                ("Partner", r.get("referrer_name")),
                ("Historical monthly", monthly),
            ),
            destination=f"/(admin)/sales-data/referrer/{r.get('referrer_id') or ''}",
            actions=("call", "whatsapp", "schedule_followup"),
            entity={"referrer_id": r.get("referrer_id") or "", "phone": r.get("phone") or ""},
        ))
    return rows


def attention_rows(data: AttentionInput, now: datetime, thresholds: dict | None = None) -> list[ActionRow]:
    """Every §9 rule, ranked by rupees at risk."""
    t = thresholds or THRESHOLDS
    rows: list[ActionRow] = []
    rows += quotation_stalled(data.quotations, now, t)
    rows += payment_overdue(data.orders, now, t)
    rows += dispatch_waiting(data.ready_items, now, t)
    rows += release_stuck(data.unreleased_items, now, t)
    rows += followup_overdue(data.followups, now, t)
    rows += salesperson_inactive(data.salespeople, now, t)
    rows += supplier_delayed(data.purchase_orders, now, t)
    rows += brand_declining(data.brands, now, t)
    rows += referrer_quiet(data.referrers, now, t)
    return rank([row for row in rows if row.impact > 0])
