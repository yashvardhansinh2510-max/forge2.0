"""Every Referral Analytics read goes through build_match and reads only
quotations.referrer_* (spec §5.1 — Referrer itself carries zero metrics)."""
from __future__ import annotations

import asyncio

from services.analytics import gather_referrals
from services.analytics.filters import AnalyticsFilter
from tests.unit.test_gather_performance import _FakeDb

WINDOW = ("2026-07-01T00:00:00+00:00", "2026-07-31T23:59:59+00:00")


def test_gather_referrer_raw_is_floor_scoped():
    db = _FakeDb(quotations=[], payments=[], referrers=[])
    asyncio.run(gather_referrals.gather_referrer_raw(db, AnalyticsFilter(floor_id="all"), ["ground-floor"], WINDOW, None))
    scoped = [q for q in db.quotations.queries if isinstance(q, dict) and q.get("floor_id")]
    assert scoped


def test_gather_referrer_raw_filters_by_type_when_given():
    db = _FakeDb(quotations=[], payments=[], referrers=[])
    asyncio.run(gather_referrals.gather_referrer_raw(db, AnalyticsFilter(floor_id="all"), None, WINDOW, "architect"))
    typed = [q for q in db.quotations.queries if isinstance(q, dict) and q.get("referrer_type") == "architect"]
    assert typed


def test_gather_referrer_profile_data_returns_none_referrer_when_not_found():
    db = _FakeDb(referrers=[], quotations=[])
    referrer, trend, brands, products, floors = asyncio.run(
        gather_referrals.gather_referrer_profile_data(db, AnalyticsFilter(floor_id="all"), None, "missing-id", "month")
    )
    assert referrer is None
    assert trend == [] and brands == [] and products == []
    assert floors == {}
