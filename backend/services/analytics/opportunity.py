"""The Opportunity Center (spec §10) — the mirror of Attention.

Problems say what is broken; opportunities say where to grow. Same `ActionRow`
shape, same purity rule (no Mongo here), same ranking by rupees, and the same
suppression rule for comparisons with no history.

The thresholds are IMPORTED from attention.py rather than redeclared — the two
surfaces tune together or they start contradicting each other.

DELIBERATELY NOT IMPLEMENTED: §10's "Repeat-buyer cross-sell" rule needs
frequently-bought-together affinity data that no service in this codebase
computes. Stubbing it would mean fabricating the affinity, so the rule is
omitted from Phase 1 and recorded as omitted rather than faked.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from services.analytics.attention import THRESHOLDS, _context, _money, age_days
from services.analytics.rows import ActionRow, rank

__all__ = [
    "THRESHOLDS",
    "OpportunityInput",
    "partner_untouched",
    "brand_growing",
    "customer_likely_to_reorder",
    "walkin_unquoted",
    "approved_not_ordered",
    "customer_gone_quiet",
    "salesperson_underloaded",
    "opportunity_rows",
]


@dataclass
class OpportunityInput:
    """Already fetched, already floor-scoped by gather.py."""

    partners: list[dict] = field(default_factory=list)
    brands: list[dict] = field(default_factory=list)
    quotations: list[dict] = field(default_factory=list)
    walkins: list[dict] = field(default_factory=list)
    customers: list[dict] = field(default_factory=list)
    salespeople: list[dict] = field(default_factory=list)


def partner_untouched(partners: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for p in partners:
        open_value = _money(p.get("open_value"))
        if open_value <= 0:
            continue
        # A partner never contacted at all is the strongest form of untouched.
        # Fall back to the age of their oldest open quotation so "no follow-up
        # has ever been logged" is not silently skipped as missing data.
        age = age_days(p.get("last_followup_at"), now)
        if age is None:
            age = age_days(p.get("first_open_quotation_at"), now)
        if age is None or age <= thresholds["PARTNER_UNTOUCHED_DAYS"]:
            continue
        rows.append(ActionRow(
            rule="partner_untouched",
            kind="opportunity",
            headline=f"Open pipeline, no contact in {age} days",
            impact=open_value,
            age_days=age,
            context=_context(
                ("Partner", p.get("referrer_name")),
                ("Open pipeline", open_value),
                ("Quotations", p.get("open_quotations")),
            ),
            destination=f"/(admin)/sales-data/referrer/{p.get('referrer_id') or ''}",
            actions=("call", "whatsapp", "schedule_followup"),
            entity={"referrer_id": p.get("referrer_id") or "", "phone": p.get("phone") or ""},
        ))
    return rows


def brand_growing(brands: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for brand in brands:
        if not brand.get("prior_window_exists"):
            continue
        previous = _money(brand.get("previous"))
        if previous <= 0:
            continue
        current = _money(brand.get("revenue"))
        growth_pct = (current - previous) / previous * 100
        if growth_pct < thresholds["BRAND_GROWTH_PCT"]:
            continue
        rows.append(ActionRow(
            rule="brand_growing",
            kind="opportunity",
            headline=f"{brand.get('brand_name') or 'Brand'} up {round(growth_pct)}%",
            impact=round(current - previous, 2),
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


def customer_likely_to_reorder(customers: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for c in customers:
        if c.get("has_open_quotation"):
            continue
        # A cadence needs at least two orders to exist. Deriving one from a
        # single order would manufacture an opportunity out of nothing.
        if int(c.get("orders") or 0) < 2 or not c.get("mean_gap_days"):
            continue
        average = _money(c.get("average_order"))
        if average <= 0:
            continue
        age = age_days(c.get("last_order_at"), now)
        if age is None or age < float(c["mean_gap_days"]):
            continue
        rows.append(ActionRow(
            rule="customer_likely_to_reorder",
            kind="opportunity",
            headline=f"Reorder due — {age} days since last order",
            impact=average,
            age_days=age,
            context=_context(
                ("Customer", c.get("customer_name")),
                ("Usual gap", f"{round(float(c['mean_gap_days']))} days"),
                ("Average order", average),
            ),
            destination=f"/(admin)/customers/{c.get('customer_id') or ''}",
            actions=("call", "whatsapp", "schedule_followup", "open_customer"),
            entity={"customer_id": c.get("customer_id") or "", "phone": c.get("phone") or ""},
        ))
    return rows


def walkin_unquoted(walkins: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for w in walkins:
        if w.get("selection_quotation_id"):
            continue
        if not (w.get("interested_products") or []):
            continue
        value = _money(w.get("budget"))
        if value <= 0:
            continue
        age = age_days(w.get("visited_at"), now)
        if age is None or age > thresholds["WALKIN_UNQUOTED_DAYS"]:
            continue
        rows.append(ActionRow(
            rule="walkin_unquoted",
            kind="opportunity",
            headline=f"High-intent walk-in not quoted ({age}d)",
            impact=value,
            age_days=age,
            context=_context(
                ("Customer", w.get("customer_name")),
                ("Budget", value),
                ("Interested in", ", ".join(w.get("interested_products") or [])),
            ),
            destination="/(admin)/walkins",
            actions=("call", "whatsapp", "open_customer"),
            entity={
                "walkin_id": w.get("id") or "",
                "customer_id": w.get("customer_id") or "",
                "phone": w.get("customer_phone") or "",
            },
        ))
    return rows


def approved_not_ordered(quotations: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for q in quotations:
        if q.get("status") != "approved":
            continue
        value = _money(q.get("grand_total"))
        if value <= 0:
            continue
        age = age_days(q.get("updated_at"), now)
        if age is None or age <= thresholds["APPROVED_NOT_ORDERED_DAYS"]:
            continue
        rows.append(ActionRow(
            rule="approved_not_ordered",
            kind="opportunity",
            headline=f"Approved {age} days ago, not ordered",
            impact=value,
            age_days=age,
            context=_context(
                ("Customer", q.get("customer_name")),
                ("Quotation", q.get("number")),
                ("Approved", f"{age} days ago"),
            ),
            destination=f"/(admin)/quotations/{q['id']}",
            actions=("open", "call", "whatsapp"),
            entity={
                "quotation_id": q["id"],
                "customer_id": q.get("customer_id") or "",
                "phone": q.get("customer_phone") or "",
            },
        ))
    return rows


def customer_gone_quiet(customers: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    rows = []
    for c in customers:
        average = _money(c.get("average_order"))
        if average <= 0:
            continue
        age = age_days(c.get("last_order_at"), now)
        if age is None or age <= thresholds["CUSTOMER_INACTIVE_DAYS"]:
            continue
        rows.append(ActionRow(
            rule="customer_gone_quiet",
            kind="opportunity",
            headline=f"Top customer quiet {age} days",
            impact=average,
            age_days=age,
            context=_context(
                ("Customer", c.get("customer_name")),
                ("Lifetime revenue", _money(c.get("lifetime_revenue"))),
                ("Average order", average),
            ),
            destination=f"/(admin)/customers/{c.get('customer_id') or ''}",
            actions=("call", "whatsapp", "schedule_followup", "open_customer"),
            entity={"customer_id": c.get("customer_id") or "", "phone": c.get("phone") or ""},
        ))
    return rows


def salesperson_underloaded(salespeople: list[dict], now: datetime, thresholds: dict) -> list[ActionRow]:
    """The best converter with the lightest load, versus the heaviest load.

    Needs at least two people: "underloaded" is a comparison, and with one
    salesperson there is nothing to compare against.
    """
    if len(salespeople) < 2:
        return []
    best = max(salespeople, key=lambda p: float(p.get("conversion_pct") or 0))
    heaviest = max(int(p.get("open_quotations") or 0) for p in salespeople)
    gap = heaviest - int(best.get("open_quotations") or 0)
    average = _money(best.get("average_order"))
    if gap <= 0 or average <= 0:
        return []
    return [ActionRow(
        rule="salesperson_underloaded",
        kind="opportunity",
        headline=f"{best.get('full_name') or 'Top converter'} has capacity for {gap} more",
        impact=round(average * gap, 2),
        age_days=None,
        context=_context(
            ("Salesperson", best.get("full_name")),
            ("Conversion", f"{round(float(best.get('conversion_pct') or 0))}%"),
            ("Open quotations", best.get("open_quotations")),
            ("Capacity gap", gap),
        ),
        destination="/(admin)/followups",
        actions=("open", "assign"),
        entity={"salesperson_id": best.get("id") or ""},
    )]


def opportunity_rows(data: OpportunityInput, now: datetime, thresholds: dict | None = None) -> list[ActionRow]:
    """Every §10 rule implemented in Phase 1, ranked by upside."""
    t = thresholds or THRESHOLDS
    rows: list[ActionRow] = []
    rows += partner_untouched(data.partners, now, t)
    rows += brand_growing(data.brands, now, t)
    rows += customer_likely_to_reorder(data.customers, now, t)
    rows += walkin_unquoted(data.walkins, now, t)
    rows += approved_not_ordered(data.quotations, now, t)
    rows += customer_gone_quiet(data.customers, now, t)
    rows += salesperson_underloaded(data.salespeople, now, t)
    return rank([row for row in rows if row.impact > 0])
