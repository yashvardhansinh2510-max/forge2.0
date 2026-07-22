"""Chalan generation endpoint — validates release quantities against what's
actually remaining, writes the chalan onto the PO, and notifies the order's
creator/assignee (never the customer directly — see design doc)."""
from __future__ import annotations

import asyncio

import pytest

from models import UserPublic
from routes import purchases_tracker as tracker


def _user() -> UserPublic:
    return UserPublic(
        email="wh@forge.app", full_name="Warehouse Rep", role="warehouse",
        floor_ids=["ground-floor"], active_floor_id="ground-floor",
    )


def _po(**overrides) -> dict:
    base = {
        "id": "po-1", "number": "FPO-0001", "customer_id": "cust-1",
        "customer_name": "Nileshbhai Pokiya", "created_by": "u-sales", "assigned_to": None,
        "items": [{"id": "item-1", "name": "Glossy Ivory 600x600", "finish": "600X600", "qty": 40}],
        "chalans": [],
    }
    base.update(overrides)
    return base


class _FakePOs:
    def __init__(self, po: dict | None):
        self._po = po
        self.pushed_chalan: dict | None = None
        self.update_calls = 0

    async def find_one(self, *_args, **_kwargs):
        if self._po is None:
            return None
        result = dict(self._po)
        if self.pushed_chalan:
            result["chalans"] = [self.pushed_chalan]
        return result

    async def update_one(self, _query, update):
        self.update_calls += 1
        self.pushed_chalan = update["$push"]["chalans"]


class _FakeDb:
    def __init__(self, po: dict | None):
        self.purchase_orders = _FakePOs(po)


async def _noop_log_event(**_kwargs):
    return None


async def _noop_notify(*_args, **_kwargs):
    return None


async def _fake_next_number(*_args, **_kwargs):
    return "CH-0001"


def test_generate_chalan_happy_path(monkeypatch):
    fake_db = _FakeDb(_po())
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "log_event", _noop_log_event)
    monkeypatch.setattr(tracker, "notify", _noop_notify)
    monkeypatch.setattr(tracker, "next_number", _fake_next_number)

    body = tracker.GenerateChalanBody(
        items=[tracker.ChalanItemInput(po_item_id="item-1", qty=15)],
        receiver_name="Nileshbhai Pokiya", sender_name="Kajaria Rep",
    )
    result = asyncio.run(tracker.generate_chalan("po-1", body, user=_user()))

    assert result["chalan"]["number"] == "CH-0001"
    assert result["chalan"]["items"][0]["qty"] == 15
    assert result["stage"] == "order"  # only 15 of 40 released — not fully released yet
    assert fake_db.purchase_orders.update_calls == 1


def test_generate_chalan_rejects_over_release(monkeypatch):
    fake_db = _FakeDb(_po())
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "next_number", _fake_next_number)

    body = tracker.GenerateChalanBody(items=[tracker.ChalanItemInput(po_item_id="item-1", qty=999)])
    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.generate_chalan("po-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 400


def test_generate_chalan_404s_when_po_not_found(monkeypatch):
    fake_db = _FakeDb(None)
    monkeypatch.setattr(tracker, "db", fake_db)

    body = tracker.GenerateChalanBody(items=[tracker.ChalanItemInput(po_item_id="item-1", qty=1)])
    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.generate_chalan("po-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 404
