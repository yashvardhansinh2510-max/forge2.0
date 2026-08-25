# backend/tests/unit/test_tile_orders_godown.py
from __future__ import annotations

import asyncio

from models import UserPublic
from routes import tile_orders as router_module


def _user() -> UserPublic:
    return UserPublic(email="wh@forge.app", full_name="Warehouse Rep", role="warehouse", floor_ids=["ground-floor"], active_floor_id="ground-floor")


class _FakeDispatches:
    def __init__(self, dispatch):
        self.doc = dispatch
        self.update_calls: list[dict] = []

    async def find_one(self, query, *_a, **_kw):
        return dict(self.doc) if self.doc else None

    async def update_one(self, query, update, **_kw):
        self.update_calls.append(query)
        if query.get("godown_received_at", "MISSING") != self.doc.get("godown_received_at"):
            class _R: matched_count = 0
            return _R()
        self.doc.update(update["$set"])
        class _R: matched_count = 1
        return _R()


class _FakePOs:
    def __init__(self, po):
        self.po = po

    async def find_one(self, query, *_a, **_kw):
        return dict(self.po) if self.po else None

    async def update_one(self, query, update, **_kw):
        self.po.update(update["$set"])


class _FakeDb:
    def __init__(self, dispatch, po):
        self.dispatches = _FakeDispatches(dispatch)
        self.purchase_orders = _FakePOs(po)


async def _noop_log_event(**_kwargs):
    return None


def _dispatch():
    return {
        "id": "d-1", "dispatch_number": "DSP-2026-0001", "purchase_order_id": "po-1", "customer_id": "cust-1",
        "godown_received_at": None, "ready_batches_consumed": [{"po_item_id": "item-1", "ready_batch_id": "rb-1", "qty": 5}],
    }


def _po():
    return {"id": "po-1", "items": [{"id": "item-1", "qty": 20, "boxes_ready": 7, "boxes_dispatched": 5, "current_location": "Dispatched"}]}


def test_mark_godown_received_updates_location(monkeypatch):
    fake_db = _FakeDb(_dispatch(), _po())
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "log_event", _noop_log_event)

    body = router_module.GodownReceivedBody(note=None)
    result = asyncio.run(router_module.mark_dispatch_godown_received("d-1", body, user=_user()))

    assert result["godown_received_at"] is not None
    assert fake_db.purchase_orders.po["items"][0]["current_location"] == "Godown"


def test_mark_godown_received_rejects_double_call(monkeypatch):
    fake_db = _FakeDb(_dispatch(), _po())
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "log_event", _noop_log_event)

    body = router_module.GodownReceivedBody(note=None)
    asyncio.run(router_module.mark_dispatch_godown_received("d-1", body, user=_user()))
    import pytest
    with pytest.raises(Exception) as exc:
        asyncio.run(router_module.mark_dispatch_godown_received("d-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 400
