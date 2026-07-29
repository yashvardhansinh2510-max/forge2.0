"""Bulk 'Mark Ready' — creates one ReadyBatch per line in one transaction,
bumps boxes_ready/boxes_pending, recomputes status/location. Uses the same
hand-rolled-fake-db + monkeypatch pattern as test_purchases_chalan_generation.py."""
from __future__ import annotations

import asyncio

import pytest

from models import UserPublic
from routes import tile_orders as router_module


def _user() -> UserPublic:
    return UserPublic(email="wh@forge.app", full_name="Warehouse Rep", role="warehouse", floor_ids=["ground-floor"], active_floor_id="ground-floor")


def _po(**overrides) -> dict:
    base = {
        "id": "po-1", "number": "FPO-2026-0001", "customer_id": "cust-1", "customer_name": "Nileshbhai Pokiya",
        "customer_order_id": "co-1", "supplier_id": "s-1", "supplier_name": "Qutone Rajkot",
        "items": [{
            "id": "item-1", "name": "Glossy Ivory 600x600", "series": "Metropole", "finish": None,
            "size": "600X600", "sku": "SKU-1", "qty": 20, "boxes_ready": 0, "boxes_dispatched": 0,
            "boxes_pending": 20, "overall_status": "Pending", "current_location": "Pending",
        }],
    }
    base.update(overrides)
    return base


class _FakeSession:
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False
    def start_transaction(self): return self


class _FakeClient:
    async def start_session(self): return _FakeSession()


class _FakePOs:
    def __init__(self, po):
        self.po = po
        self.set_calls: list[dict] = []

    async def find_one(self, query, *_a, session=None, **_kw):
        return dict(self.po) if self.po else None

    async def update_one(self, query, update, session=None, **_kw):
        self.set_calls.append(update["$set"])
        self.po.update(update["$set"])
        class _Result:
            matched_count = 1
        return _Result()


class _FakeReadyBatches:
    def __init__(self):
        self.inserted: list[dict] = []

    async def insert_one(self, doc, session=None):
        self.inserted.append(doc)


class _FakeCustomerOrders:
    def __init__(self, co):
        self.co = co

    async def find_one(self, query, *_a, session=None, **_kw):
        return dict(self.co) if self.co else None

    async def update_one(self, query, update, session=None, **_kw):
        self.co.update(update["$set"])
        class _Result:
            matched_count = 1
        return _Result()


class _FakeDb:
    def __init__(self, po, co):
        self.purchase_orders = _FakePOs(po)
        self.ready_batches = _FakeReadyBatches()
        self.customer_orders = _FakeCustomerOrders(co)


async def _fake_next_number(*_a, **_kw):
    return "RB-2026-0001"


async def _noop_log_event(**_kwargs):
    return None


def _customer_order():
    return {
        "id": "co-1", "version": 0, "brands": [{
            "brand_id": "b-1", "brand_name": "Qutone", "supplier_id": "s-1", "supplier_name": "Qutone Rajkot",
            "purchase_order_id": "po-1", "status": "Pending",
        }],
    }


def test_mark_ready_creates_batch_and_updates_counters(monkeypatch):
    fake_db = _FakeDb(_po(), _customer_order())
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "client", _FakeClient())
    monkeypatch.setattr(router_module, "next_number", _fake_next_number)
    monkeypatch.setattr(router_module, "log_event", _noop_log_event)

    body = router_module.BulkReadyBody(items=[router_module.ReadyItemInput(po_item_id="item-1", qty=8)])
    result = asyncio.run(router_module.mark_items_ready("po-1", body, user=_user()))

    assert result["ready_batches"][0]["batch_number"] == "RB-2026-0001"
    updated_item = fake_db.purchase_orders.po["items"][0]
    assert updated_item["boxes_ready"] == 8
    assert updated_item["boxes_pending"] == 12
    assert updated_item["overall_status"] == "Ready"
    assert fake_db.ready_batches.inserted[0]["remaining_qty"] == 8


def test_mark_ready_rejects_over_pending(monkeypatch):
    fake_db = _FakeDb(_po(), _customer_order())
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "client", _FakeClient())
    monkeypatch.setattr(router_module, "next_number", _fake_next_number)

    body = router_module.BulkReadyBody(items=[router_module.ReadyItemInput(po_item_id="item-1", qty=999)])
    with pytest.raises(Exception) as exc:
        asyncio.run(router_module.mark_items_ready("po-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 400
