"""Pure shaping for spec §7 Workspace 3 — Referral Analytics. Reads only
already-aggregated rows; gather_referrals.py is the only place this surface
queries Mongo (spec §5.1: reporting reads quotations.referrer_* directly,
Referrer itself carries zero metrics)."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime

from services.analytics.attention import age_days


@dataclass(frozen=True)
class ReferrerSummary:
    referrer_id: str
    name: str
    type: str
    customers_referred: int
    quotations_total: int
    quotations_approved: int
    quotations_confirmed: int
    revenue: float
    aov: float
    conversion_rate: float | None
    pending_count: int
    pending_value: float
    pending_payments: float
    first_referral_at: str | None
    last_referral_at: str | None
    is_active: bool
    repeat_customers: int


def referrer_summary_rows(raw: list[dict], now: datetime, thresholds: dict) -> list[ReferrerSummary]:
    result: list[ReferrerSummary] = []
    for r in raw:
        total = int(r.get("quotations_total") or 0)
        confirmed = int(r.get("quotations_confirmed") or 0)
        revenue = float(r.get("revenue") or 0)
        last = r.get("last_referral_at")
        age = age_days(last, now)
        result.append(ReferrerSummary(
            referrer_id=r["referrer_id"], name=r.get("name") or "Unknown", type=r.get("type") or "architect",
            customers_referred=int(r.get("customers_referred") or 0),
            quotations_total=total, quotations_approved=int(r.get("quotations_approved") or 0),
            quotations_confirmed=confirmed, revenue=revenue,
            aov=round(revenue / confirmed, 2) if confirmed else 0.0,
            conversion_rate=round(confirmed / total * 100, 1) if total else None,
            pending_count=int(r.get("pending_count") or 0), pending_value=float(r.get("pending_value") or 0),
            pending_payments=float(r.get("pending_payments") or 0),
            first_referral_at=r.get("first_referral_at"), last_referral_at=last,
            is_active=(age is not None and age <= thresholds["REFERRER_QUIET_DAYS"]),
            repeat_customers=int(r.get("repeat_customers") or 0),
        ))
    return sorted(result, key=lambda s: -s.revenue)


def summary_dict(summary: ReferrerSummary) -> dict:
    return asdict(summary)


PREFERENCE_LIMIT = 10


@dataclass(frozen=True)
class ReferrerProfile:
    referrer_id: str
    name: str
    type: str
    phone: str | None
    company: str | None
    summary: ReferrerSummary
    monthly_trend: list[dict]
    brand_preference: list[dict]
    product_preference: list[dict]
    floor_split: dict[str, float]


def _top(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: -float(r.get("revenue") or 0))[:PREFERENCE_LIMIT]


def referrer_profile(
    referrer: dict,
    summary: ReferrerSummary,
    monthly_trend: list[dict],
    brand_rows: list[dict],
    product_rows: list[dict],
    floor_rows: dict[str, float],
) -> ReferrerProfile:
    return ReferrerProfile(
        referrer_id=referrer["id"], name=referrer.get("name") or "Unknown", type=referrer.get("type") or "architect",
        phone=referrer.get("phone"), company=referrer.get("company"),
        summary=summary, monthly_trend=list(monthly_trend),
        brand_preference=_top(brand_rows), product_preference=_top(product_rows),
        floor_split=dict(floor_rows),
    )
