# backend/tests/unit/test_backfill_tile_customer_orders.py
from __future__ import annotations

import asyncio

from scripts import backfill_tile_customer_orders as backfill_module


class _FakeFind:
    def __init__(self, items): self._items = items
    async def to_list(self, n=None): return list(self._items)


class _FakeCollection:
    def __init__(self, docs): self.docs = docs
    def find(self, query=None, projection=None, session=None): return _FakeFind(self.docs)
    async def find_one(self, query=None, projection=None, session=None):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in (query or {}).items() if not k.startswith("$")):
                return dict(doc)
        return None
    async def insert_one(self, doc, session=None): self.docs.append(doc)
    async def update_one(self, query, update, session=None, **_kw):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                doc.update(update.get("$set", {}))


class _FakeCounters:
    def __init__(self): self.docs: dict = {}
    async def find_one(self, query, *_a, **_kw): return self.docs.get(query.get("_id"))
    async def find_one_and_update(self, query, update, **_kw):
        key = query["_id"]
        doc = self.docs.setdefault(key, {"_id": key, "seq": 0})
        doc["seq"] += update["$inc"]["seq"]
        return dict(doc)


# services.sequence.next_number does `from db import db` at its own module
# scope, so patching backfill_module.db alone does NOT redirect its calls —
# it would still hit the real MongoDB configured in backend/.env. Every
# other test in this suite that touches a next_number-calling module (e.g.
# tests/unit/test_tile_orders_dispatch.py) monkeypatches next_number
# directly for the same reason; follow that convention here too.
async def _fake_next_number(kind, prefix, *, collection, **_kw):
    return f"{prefix}0001"


def _old_tiles_po():
    return {
        "id": "po-1", "number": "FPO-2026-0001", "quotation_id": "q-1", "quotation_number": "FQ-2026-0001",
        "customer_id": "cust-1", "customer_name": "Nileshbhai Pokiya", "supplier_id": "s-1", "supplier_name": "Qutone Rajkot",
        "brand_id": "b-1", "brand_name": "Qutone", "floor_id": "ground-floor", "created_at": "2026-07-22T10:00:00+00:00",
        "items": [{"id": "item-1", "name": "Glossy Ivory 600x600", "qty": 20, "finish": None, "series": None, "size": None, "sku": "SKU-1"}],
        "chalans": [{"id": "old-ch-1", "number": "CH-0001", "stage": "released", "items": [{"po_item_id": "item-1", "name": "Glossy Ivory 600x600", "qty": 8, "unit": "Box"}], "created_at": "2026-07-23T10:00:00+00:00", "created_by": "u-1", "created_by_name": "Warehouse Rep"}],
    }


def test_backfill_creates_customer_order_and_migrates_chalans(monkeypatch):
    db = type("Db", (), {})()
    db.purchase_orders = _FakeCollection([_old_tiles_po()])
    db.quotations = _FakeCollection([{"id": "q-1", "doc_type": "tiles_quotation"}])
    db.customer_orders = _FakeCollection([])
    db.dispatches = _FakeCollection([])
    db.chalans = _FakeCollection([])
    db.ready_batches = _FakeCollection([])
    db.counters = _FakeCounters()
    monkeypatch.setattr(backfill_module, "db", db)
    monkeypatch.setattr(backfill_module, "next_number", _fake_next_number)

    result = asyncio.run(backfill_module.backfill(dry_run=False))

    assert result["customer_orders_created"] == 1
    assert result["chalans_migrated"] == 1
    assert len(db.customer_orders.docs) == 1
    po = db.purchase_orders.docs[0]
    assert po["customer_order_id"] == db.customer_orders.docs[0]["id"]
    item = po["items"][0]
    assert item["boxes_dispatched"] == 8
    assert item["boxes_pending"] == 12
    assert item["current_location"] == "Dispatched"  # old stage "released"
    assert len(db.chalans.docs) == 1
    assert len(db.dispatches.docs) == 1
    assert db.ready_batches.docs[0]["auto_created"] is True


def test_backfill_skips_standard_quotation_pos(monkeypatch):
    po = _old_tiles_po()
    db = type("Db", (), {})()
    db.purchase_orders = _FakeCollection([po])
    db.quotations = _FakeCollection([{"id": "q-1", "doc_type": "standard"}])
    db.customer_orders = _FakeCollection([])
    db.dispatches = _FakeCollection([])
    db.chalans = _FakeCollection([])
    db.ready_batches = _FakeCollection([])
    db.counters = _FakeCounters()
    monkeypatch.setattr(backfill_module, "db", db)
    monkeypatch.setattr(backfill_module, "next_number", _fake_next_number)

    result = asyncio.run(backfill_module.backfill(dry_run=False))

    assert result["customer_orders_created"] == 0
    assert db.customer_orders.docs == []


def test_backfill_is_idempotent(monkeypatch):
    po = _old_tiles_po()
    db = type("Db", (), {})()
    db.purchase_orders = _FakeCollection([po])
    db.quotations = _FakeCollection([{"id": "q-1", "doc_type": "tiles_quotation"}])
    db.customer_orders = _FakeCollection([])
    db.dispatches = _FakeCollection([])
    db.chalans = _FakeCollection([])
    db.ready_batches = _FakeCollection([])
    db.counters = _FakeCounters()
    monkeypatch.setattr(backfill_module, "db", db)
    monkeypatch.setattr(backfill_module, "next_number", _fake_next_number)

    asyncio.run(backfill_module.backfill(dry_run=False))
    result_second_run = asyncio.run(backfill_module.backfill(dry_run=False))

    assert result_second_run["customer_orders_created"] == 0  # already has customer_order_id, skipped
    assert len(db.customer_orders.docs) == 1
