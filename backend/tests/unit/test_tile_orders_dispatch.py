# backend/tests/unit/test_tile_orders_dispatch.py
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
            "size": "600X600", "sku": "SKU-1", "pieces_per_box": "4", "qty": 20,
            "boxes_ready": 12, "boxes_dispatched": 0, "boxes_pending": 8,
            "overall_status": "Ready", "current_location": "Ready",
        }],
    }
    base.update(overrides)
    return base


def _ready_batch(**overrides) -> dict:
    base = {
        "id": "rb-1", "batch_number": "RB-2026-0001", "purchase_order_id": "po-1", "po_item_id": "item-1",
        "qty": 12, "remaining_qty": 12, "auto_created": False,
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

    async def find_one(self, query, *_a, session=None, **_kw):
        return dict(self.po) if self.po else None

    async def update_one(self, query, update, session=None, **_kw):
        self.po.update(update["$set"])
        class _R: matched_count = 1
        return _R()


class _FakeReadyBatches:
    def __init__(self, batches):
        self.docs = {b["id"]: dict(b) for b in batches}
        self.inserted: list[dict] = []

    async def find_one(self, query, *_a, session=None, **_kw):
        for doc in self.docs.values():
            if doc.get("id") == query.get("id"):
                return dict(doc)
        return None

    async def insert_one(self, doc, session=None):
        self.docs[doc["id"]] = doc
        self.inserted.append(doc)

    async def update_one(self, query, update, session=None, **_kw):
        doc = self.docs[query["id"]]
        doc.update(update["$set"])
        class _R: matched_count = 1
        return _R()


class _FakeDispatches:
    def __init__(self):
        self.inserted: list[dict] = []

    async def insert_one(self, doc, session=None):
        self.inserted.append(doc)


class _FakeChalans:
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
        class _R: matched_count = 1
        return _R()


class _FakeDb:
    def __init__(self, po, ready_batches, co):
        self.purchase_orders = _FakePOs(po)
        self.ready_batches = _FakeReadyBatches(ready_batches)
        self.dispatches = _FakeDispatches()
        self.chalans = _FakeChalans()
        self.customer_orders = _FakeCustomerOrders(co)


def _customer_order():
    return {"id": "co-1", "version": 0, "brands": [{
        "brand_id": "b-1", "brand_name": "Qutone", "supplier_id": "s-1", "supplier_name": "Qutone Rajkot",
        "purchase_order_id": "po-1", "status": "Ready",
    }]}


_DESTINATION = dict(destination_type="Customer", destination_name="Nileshbhai Pokiya", destination_address="123 Ring Road", destination_city="Rajkot")


async def _fake_next_number(kind, *_a, **_kw):
    return "DSP-2026-0001" if kind == "dispatch" else ("RB-2026-0002" if kind == "ready_batch" else "CH-0001")


async def _noop_log_event(**_kwargs):
    return None


def test_preview_never_mutates_state(monkeypatch):
    fake_db = _FakeDb(_po(), [_ready_batch()], _customer_order())
    monkeypatch.setattr(router_module, "db", fake_db)

    body = router_module.DispatchBody(
        items=[router_module.DispatchLineInput(po_item_id="item-1", ready_batch_id="rb-1", qty=5)], **_DESTINATION,
    )
    result = asyncio.run(router_module.preview_dispatch("po-1", body, user=_user()))

    assert result["items"][0]["qty"] == 5
    assert fake_db.dispatches.inserted == []
    assert fake_db.chalans.inserted == []
    assert fake_db.ready_batches.docs["rb-1"]["remaining_qty"] == 12  # untouched


def test_dispatch_from_existing_ready_batch(monkeypatch):
    fake_db = _FakeDb(_po(), [_ready_batch()], _customer_order())
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "client", _FakeClient())
    monkeypatch.setattr(router_module, "next_number", _fake_next_number)
    monkeypatch.setattr(router_module, "log_event", _noop_log_event)

    body = router_module.DispatchBody(
        items=[router_module.DispatchLineInput(po_item_id="item-1", ready_batch_id="rb-1", qty=5)], **_DESTINATION,
    )
    result = asyncio.run(router_module.commit_dispatch("po-1", body, user=_user()))

    assert result["dispatch"]["dispatch_number"] == "DSP-2026-0001"
    assert result["chalan"]["number"] == "CH-0001"
    assert result["chalan"]["items"][0]["quantity"] == 5   # only the dispatched qty, not the whole order
    assert fake_db.ready_batches.docs["rb-1"]["remaining_qty"] == 7
    item = fake_db.purchase_orders.po["items"][0]
    assert item["boxes_ready"] == 7
    assert item["boxes_dispatched"] == 5
    assert item["boxes_pending"] == 8
    assert item["overall_status"] == "Partially Dispatched"


def test_direct_dispatch_from_pending_auto_creates_ready_batch(monkeypatch):
    fake_db = _FakeDb(_po(), [], _customer_order())
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "client", _FakeClient())
    monkeypatch.setattr(router_module, "next_number", _fake_next_number)
    monkeypatch.setattr(router_module, "log_event", _noop_log_event)

    body = router_module.DispatchBody(
        items=[router_module.DispatchLineInput(po_item_id="item-1", ready_batch_id=None, qty=3)], **_DESTINATION,
    )
    result = asyncio.run(router_module.commit_dispatch("po-1", body, user=_user()))

    auto_batch = [b for b in fake_db.ready_batches.inserted if b["auto_created"]][0]
    assert auto_batch["qty"] == 3
    assert auto_batch["remaining_qty"] == 0
    item = fake_db.purchase_orders.po["items"][0]
    assert item["boxes_pending"] == 5      # 8 - 3
    assert item["boxes_dispatched"] == 3
    assert item["boxes_ready"] == 12       # untouched — this dispatch came from pending, not from the existing batch
    assert result["dispatch"]["ready_batches_consumed"][0]["ready_batch_id"] == auto_batch["id"]


def test_dispatch_rejects_over_consuming_a_batch(monkeypatch):
    fake_db = _FakeDb(_po(), [_ready_batch(remaining_qty=2)], _customer_order())
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "client", _FakeClient())

    body = router_module.DispatchBody(
        items=[router_module.DispatchLineInput(po_item_id="item-1", ready_batch_id="rb-1", qty=5)], **_DESTINATION,
    )
    with pytest.raises(Exception) as exc:
        asyncio.run(router_module.commit_dispatch("po-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 400
