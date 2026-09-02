"""Confirmed-order analytics must be anchored to the immutable order stamp."""
from __future__ import annotations

import asyncio

from models import UserPublic
from routes import executive_analytics_routes as routes


class _Cursor:
    async def to_list(self, _limit):
        return []


class _Collection:
    def __init__(self):
        self.pipelines: list[list[dict]] = []

    def aggregate(self, pipeline, **_kwargs):
        self.pipelines.append(pipeline)
        return _Cursor()


class _Db:
    def __init__(self):
        self.quotations = _Collection()
        self.walkins = _Collection()
        self.followups = _Collection()


def _owner() -> UserPublic:
    return UserPublic(id="owner", email="owner@example.com", full_name="Owner", role="owner")


def test_confirmed_order_match_dates_by_ordered_at():
    match = asyncio.run(routes._match(
        _owner(), None, "custom", "2026-08-01T00:00:00+00:00", "2026-08-31T23:59:59+00:00",
        None, None, None,
    ))
    assert match["ordered_at"] == {"$gte": "2026-08-01T00:00:00+00:00", "$lte": "2026-08-31T23:59:59+00:00"}
    assert "updated_at" not in match


def test_dashboard_trend_and_prior_period_use_ordered_at(monkeypatch):
    fake_db = _Db()
    monkeypatch.setattr(routes, "db", fake_db)

    asyncio.run(routes.dashboard(
        preset="custom", date_from="2026-08-01T00:00:00+00:00", date_to="2026-08-31T23:59:59+00:00",
        user=_owner(),
    ))

    quotation_pipelines = fake_db.quotations.pipelines
    assert all("updated_at" not in stage.get("$match", {}) for pipeline in quotation_pipelines for stage in pipeline)
    trend_group = next(
        stage["$group"] for pipeline in quotation_pipelines for stage in pipeline
        if "$group" in stage and stage["$group"].get("_id") == {"$dateToString": {"format": "%Y-%m", "date": {"$dateFromString": {"dateString": "$ordered_at"}}}}
    )
    assert trend_group["revenue"] == {"$sum": "$grand_total"}
