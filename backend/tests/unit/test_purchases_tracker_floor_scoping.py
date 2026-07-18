"""Regression test: the Purchases Tracker read endpoints must never return
rows from a floor the caller isn't currently viewing. Root cause (2026-07-17
floor-isolation investigation): `_iter_items()` built its Mongo `$match`
with no floor filter at all, so every tracker view showed every floor's
purchase orders regardless of the selected floor."""
from __future__ import annotations

import asyncio

import pytest

from models import UserPublic
from routes import purchases_tracker as tracker


def _user(floor_id: str) -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=floor_id,
    )


class _FakeAggregateCursor:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    async def to_list(self, _n):
        return self._rows


class _FakePurchaseOrders:
    """Captures the pipeline passed to aggregate() instead of simulating
    real Mongo aggregation semantics — the thing under test is whether the
    floor filter is present in the $match stage, not Mongo's engine."""

    def __init__(self):
        self.last_pipeline: list[dict] | None = None

    def aggregate(self, pipeline):
        self.last_pipeline = pipeline
        return _FakeAggregateCursor([])


class _FakeDb:
    def __init__(self, purchase_orders: _FakePurchaseOrders):
        self.purchase_orders = purchase_orders


def test_iter_items_scopes_pipeline_to_the_active_floor(monkeypatch):
    fake_pos = _FakePurchaseOrders()
    monkeypatch.setattr(tracker, "db", _FakeDb(fake_pos))

    asyncio.run(tracker._iter_items(
        "stock", None, None, None, None, sla_days=7, limit=500,
        floor_ids=["ground-floor"],
    ))

    match_stage = fake_pos.last_pipeline[0]["$match"]
    assert match_stage.get("floor_id") == {"$in": ["ground-floor"]}


def test_iter_items_unscoped_when_floor_ids_is_none(monkeypatch):
    fake_pos = _FakePurchaseOrders()
    monkeypatch.setattr(tracker, "db", _FakeDb(fake_pos))

    asyncio.run(tracker._iter_items(
        "stock", None, None, None, None, sla_days=7, limit=500,
        floor_ids=None,
    ))

    match_stage = fake_pos.last_pipeline[0]["$match"]
    assert "floor_id" not in match_stage
