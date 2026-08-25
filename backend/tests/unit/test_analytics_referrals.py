"""Pure shaping for spec §7 Workspace 3 — Referral Analytics. Every one of the
14 cards is a field on ReferrerSummary or its profile; nothing here queries
Mongo (gather_referrals.py does that)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.analytics.attention import THRESHOLDS
from services.analytics.referrals import PREFERENCE_LIMIT, referrer_profile, referrer_summary_rows

NOW = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _raw(**kw) -> dict:
    base = dict(
        referrer_id="r1", name="ABC Architects", type="architect",
        customers_referred=4, quotations_total=10, quotations_approved=6, quotations_confirmed=5,
        revenue=1200000.0, pending_count=2, pending_value=300000.0, pending_payments=50000.0,
        first_referral_at=_iso(400), last_referral_at=_iso(5), repeat_customers=2,
    )
    base.update(kw)
    return base


def _summary():
    return referrer_summary_rows([_raw()], now=NOW, thresholds=THRESHOLDS)[0]


def test_conversion_rate_is_confirmed_over_total_quotations():
    rows = referrer_summary_rows([_raw()], now=NOW, thresholds=THRESHOLDS)
    assert rows[0].conversion_rate == 50.0


def test_conversion_rate_is_none_with_zero_quotations():
    rows = referrer_summary_rows([_raw(quotations_total=0, quotations_confirmed=0)], now=NOW, thresholds=THRESHOLDS)
    assert rows[0].conversion_rate is None


def test_aov_is_revenue_over_confirmed_quotations():
    rows = referrer_summary_rows([_raw(revenue=1000000.0, quotations_confirmed=5)], now=NOW, thresholds=THRESHOLDS)
    assert rows[0].aov == 200000.0


def test_aov_is_zero_without_any_confirmed_quotations():
    rows = referrer_summary_rows([_raw(revenue=0.0, quotations_confirmed=0)], now=NOW, thresholds=THRESHOLDS)
    assert rows[0].aov == 0.0


def test_active_when_the_last_referral_is_inside_the_quiet_window():
    rows = referrer_summary_rows([_raw(last_referral_at=_iso(5))], now=NOW, thresholds=THRESHOLDS)
    assert rows[0].is_active is True


def test_inactive_when_the_last_referral_is_past_the_quiet_window():
    rows = referrer_summary_rows([_raw(last_referral_at=_iso(THRESHOLDS["REFERRER_QUIET_DAYS"] + 1))], now=NOW, thresholds=THRESHOLDS)
    assert rows[0].is_active is False


def test_a_referrer_who_has_never_referred_is_inactive_not_a_crash():
    rows = referrer_summary_rows([_raw(last_referral_at=None, first_referral_at=None)], now=NOW, thresholds=THRESHOLDS)
    assert rows[0].is_active is False


def test_ranked_by_revenue_descending():
    rows = referrer_summary_rows([
        _raw(referrer_id="a", revenue=100.0), _raw(referrer_id="b", revenue=900.0),
    ], now=NOW, thresholds=THRESHOLDS)
    assert [r.referrer_id for r in rows] == ["b", "a"]


def test_an_empty_referrer_list_returns_an_empty_list():
    assert referrer_summary_rows([], now=NOW, thresholds=THRESHOLDS) == []


def test_profile_carries_the_contact_fields_the_summary_does_not():
    profile = referrer_profile(
        {"id": "r1", "name": "ABC Architects", "type": "architect", "phone": "+91900", "company": "ABC & Co"},
        _summary(), monthly_trend=[], brand_rows=[], product_rows=[], floor_rows={},
    )
    assert profile.phone == "+91900" and profile.company == "ABC & Co"
    assert profile.summary.revenue == _summary().revenue


def test_brand_and_product_preference_are_sorted_and_capped():
    brand_rows = [{"brand_id": f"b{i}", "brand_name": f"Brand {i}", "revenue": float(i)} for i in range(15)]
    profile = referrer_profile(
        {"id": "r1", "name": "X", "type": "architect", "phone": None, "company": None},
        _summary(), monthly_trend=[], brand_rows=brand_rows, product_rows=[], floor_rows={},
    )
    assert len(profile.brand_preference) == PREFERENCE_LIMIT
    assert profile.brand_preference[0]["revenue"] == 14.0   # highest first


def test_floor_split_includes_both_floors_even_when_one_is_zero():
    """A floor at 0 must still appear — omitting it would read as 'this
    partner doesn't exist on that floor' rather than 'no revenue yet'."""
    profile = referrer_profile(
        {"id": "r1", "name": "X", "type": "architect", "phone": None, "company": None},
        _summary(), monthly_trend=[], brand_rows=[], product_rows=[],
        floor_rows={"first-floor": 500000.0, "ground-floor": 0.0},
    )
    assert profile.floor_split == {"first-floor": 500000.0, "ground-floor": 0.0}


def test_monthly_trend_passes_through_unchanged():
    trend = [{"bucket": "Jul 2026", "revenue": 100.0}, {"bucket": "Aug 2026", "revenue": 200.0}]
    profile = referrer_profile(
        {"id": "r1", "name": "X", "type": "architect", "phone": None, "company": None},
        _summary(), monthly_trend=trend, brand_rows=[], product_rows=[], floor_rows={},
    )
    assert profile.monthly_trend == trend
