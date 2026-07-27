"""Sales Data dashboard aggregation — computed in Python over already-`won`
quotations, matching the existing dashboard_routes.py convention. These
tests exercise the computation directly against a fake db, same pattern as
test_dashboard_floor_scoping.py."""
from __future__ import annotations

import asyncio

from auth import accessible_floor_ids
from models import UserPublic
from routes import sales_data_routes as sd


def _owner():
    return UserPublic(id="u-owner", email="o@forge.app", full_name="Owner", role="owner")


def _admin_ground_only():
    return UserPublic(id="u-admin", email="a@forge.app", full_name="Admin", role="admin", floor_ids=["ground-floor"])


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, _n):
        return self._docs


class _Collection:
    def __init__(self, docs):
        self._docs = docs
        self.last_query = None

    def find(self, query, *_a, **_kw):
        self.last_query = query
        return _Cursor(self._docs)


class _FakeDb:
    def __init__(self, docs):
        self.quotations = _Collection(docs)


def test_bucket_label_day():
    assert sd._bucket_label("2026-07-15T10:00:00+00:00", "day") == "2026-07-15"


def test_bucket_label_month():
    assert sd._bucket_label("2026-07-15T10:00:00+00:00", "month") == "2026-07"


def test_bucket_label_quarter():
    assert sd._bucket_label("2026-08-01T00:00:00+00:00", "quarter") == "2026-Q3"


def test_bucket_label_year():
    assert sd._bucket_label("2026-01-05T00:00:00+00:00", "year") == "2026"


def test_resolve_floor_ids_owner_both_means_no_restriction():
    assert sd._resolve_floor_ids(_owner(), "both") is None
    assert sd._resolve_floor_ids(_owner(), None) is None


def test_resolve_floor_ids_owner_picks_one_floor():
    assert sd._resolve_floor_ids(_owner(), "ground-floor") == ["ground-floor"]


def test_resolve_floor_ids_admin_cannot_request_a_floor_outside_their_access():
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        sd._resolve_floor_ids(_admin_ground_only(), "first-floor")
    assert exc.value.status_code == 403


def test_overview_totals_revenue_and_splits_by_floor(monkeypatch):
    fake_db = _FakeDb([
        {"status": "won", "floor_id": "ground-floor", "grand_total": 100000, "updated_at": "2026-07-01T00:00:00+00:00"},
        {"status": "won", "floor_id": "first-floor", "grand_total": 50000, "updated_at": "2026-07-02T00:00:00+00:00"},
    ])
    monkeypatch.setattr(sd, "db", fake_db)

    result = asyncio.run(sd.sales_overview(
        floor_id=None, referrer_type=None, date_from=None, date_to=None,
        granularity="month", user=_owner(),
    ))

    assert result["total_revenue"] == 150000
    by_floor = {r["floor_id"]: r["revenue"] for r in result["revenue_by_floor"]}
    assert by_floor == {"ground-floor": 100000, "first-floor": 50000}
    assert result["trend"] == [{"bucket": "2026-07", "revenue": 150000}]
    assert result["referrers"] is None


def test_overview_referrer_type_filters_and_ranks(monkeypatch):
    fake_db = _FakeDb([
        {
            "status": "won", "floor_id": "first-floor", "grand_total": 80000,
            "updated_at": "2026-07-01T00:00:00+00:00",
            "referrer_type": "architect", "referrer_id": "r1", "referrer_name": "Rakesh Sharma",
        },
        {
            "status": "won", "floor_id": "first-floor", "grand_total": 40000,
            "updated_at": "2026-07-02T00:00:00+00:00",
            "referrer_type": "architect", "referrer_id": "r1", "referrer_name": "Rakesh Sharma",
        },
        {
            "status": "won", "floor_id": "first-floor", "grand_total": 20000,
            "updated_at": "2026-07-02T00:00:00+00:00",
            "referrer_type": "interior_designer", "referrer_id": "r2", "referrer_name": "Nikita Shah",
        },
    ])
    monkeypatch.setattr(sd, "db", fake_db)

    result = asyncio.run(sd.sales_overview(
        floor_id=None, referrer_type="architect", date_from=None, date_to=None,
        granularity="month", user=_owner(),
    ))

    assert result["total_revenue"] == 120000
    assert result["referrers"] == [{"referrer_id": "r1", "name": "Rakesh Sharma", "revenue": 120000}]
