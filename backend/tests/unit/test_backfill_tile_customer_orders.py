# backend/tests/unit/test_backfill_tile_customer_orders.py
from __future__ import annotations

import asyncio
import copy

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


def _mixed_stage_tiles_po():
    """An item whose old chalans array has an 'at_godown' entry FOLLOWED by
    a 'released' entry — the exact ordering the review flagged: the old
    last-chalan-wins code would report this item's location as "Dispatched"
    (from the released chalan, since it's last in the array) even though
    part of the material is actually sitting in Buildcon's own godown."""
    return {
        "id": "po-2", "number": "FPO-2026-0002", "quotation_id": "q-2", "quotation_number": "FQ-2026-0002",
        "customer_id": "cust-2", "customer_name": "Rameshbhai Patel", "supplier_id": "s-1", "supplier_name": "Qutone Rajkot",
        "brand_id": "b-1", "brand_name": "Qutone", "floor_id": "ground-floor", "created_at": "2026-07-22T10:00:00+00:00",
        "items": [{"id": "item-1", "name": "Glossy Ivory 600x600", "qty": 20, "finish": None, "series": None, "size": None, "sku": "SKU-1"}],
        "chalans": [
            {"id": "old-ch-1", "number": "CH-0001", "stage": "at_godown", "items": [{"po_item_id": "item-1", "name": "Glossy Ivory 600x600", "qty": 5, "unit": "Box"}], "created_at": "2026-07-23T10:00:00+00:00", "created_by": "u-1", "created_by_name": "Warehouse Rep"},
            {"id": "old-ch-2", "number": "CH-0002", "stage": "released", "items": [{"po_item_id": "item-1", "name": "Glossy Ivory 600x600", "qty": 3, "unit": "Box"}], "created_at": "2026-07-24T10:00:00+00:00", "created_by": "u-1", "created_by_name": "Warehouse Rep"},
        ],
    }


def _make_db(pos, doc_type="tiles_quotation"):
    db = type("Db", (), {})()
    db.purchase_orders = _FakeCollection(pos)
    quotation_ids = {po["quotation_id"] for po in pos}
    db.quotations = _FakeCollection([{"id": qid, "doc_type": doc_type} for qid in quotation_ids])
    db.customer_orders = _FakeCollection([])
    db.dispatches = _FakeCollection([])
    db.chalans = _FakeCollection([])
    db.ready_batches = _FakeCollection([])
    db.counters = _FakeCounters()
    return db


def test_backfill_current_location_prefers_godown_over_last_chalan(monkeypatch):
    """Finding 1: current_location must be furthest-progress (Godown takes
    precedence over Dispatched), not whichever old chalan happens to be
    last in the array."""
    po = _mixed_stage_tiles_po()
    db = _make_db([po])
    monkeypatch.setattr(backfill_module, "db", db)
    monkeypatch.setattr(backfill_module, "next_number", _fake_next_number)

    asyncio.run(backfill_module.backfill(dry_run=False))

    item = db.purchase_orders.docs[0]["items"][0]
    assert item["boxes_dispatched"] == 8  # 5 (at_godown) + 3 (released)
    assert item["current_location"] == "Godown"  # NOT "Dispatched" (last-wins bug)
    assert item["overall_status"] == "Partially Dispatched"


def test_backfill_destination_type_set_from_old_chalan_stage(monkeypatch):
    """Finding 3: a chalan whose old stage was 'at_godown' must produce a
    TileDispatch with destination_type="Godown" (material routed through
    Buildcon's own warehouse), while every other stage produces "Customer"."""
    po = _mixed_stage_tiles_po()
    db = _make_db([po])
    monkeypatch.setattr(backfill_module, "db", db)
    monkeypatch.setattr(backfill_module, "next_number", _fake_next_number)

    asyncio.run(backfill_module.backfill(dry_run=False))

    assert len(db.dispatches.docs) == 2
    godown_dispatches = [d for d in db.dispatches.docs if d["destination_type"] == "Godown"]
    customer_dispatches = [d for d in db.dispatches.docs if d["destination_type"] == "Customer"]
    assert len(godown_dispatches) == 1  # from the "at_godown" old chalan
    assert len(customer_dispatches) == 1  # from the "released" old chalan
    assert godown_dispatches[0]["godown_received_at"] == "2026-07-23T10:00:00+00:00"


def test_backfill_item_reaches_delivered_when_all_old_chalans_dispatched(monkeypatch):
    """Finding 2: when every old chalan touching an item reached the old
    system's terminal "dispatched" (=reached-customer) stage, BOTH
    current_location AND overall_status must reach "Delivered" — not one
    stuck at "Dispatched" while the other says "Delivered"."""
    po = {
        "id": "po-3", "number": "FPO-2026-0003", "quotation_id": "q-3", "quotation_number": "FQ-2026-0003",
        "customer_id": "cust-3", "customer_name": "Bhavesh Shah", "supplier_id": "s-1", "supplier_name": "Qutone Rajkot",
        "brand_id": "b-1", "brand_name": "Qutone", "floor_id": "ground-floor", "created_at": "2026-07-22T10:00:00+00:00",
        "items": [{"id": "item-1", "name": "Glossy Ivory 600x600", "qty": 8, "finish": None, "series": None, "size": None, "sku": "SKU-1"}],
        "chalans": [{"id": "old-ch-1", "number": "CH-0001", "stage": "dispatched", "items": [{"po_item_id": "item-1", "name": "Glossy Ivory 600x600", "qty": 8, "unit": "Box"}], "created_at": "2026-07-23T10:00:00+00:00", "created_by": "u-1", "created_by_name": "Warehouse Rep"}],
    }
    db = _make_db([po])
    monkeypatch.setattr(backfill_module, "db", db)
    monkeypatch.setattr(backfill_module, "next_number", _fake_next_number)

    asyncio.run(backfill_module.backfill(dry_run=False))

    item = db.purchase_orders.docs[0]["items"][0]
    assert item["current_location"] == "Delivered"
    assert item["overall_status"] == "Delivered"


def test_backfill_retry_after_partial_failure_does_not_duplicate_customer_order(monkeypatch):
    """Finding 4: if a prior run crashed after inserting the TileCustomerOrder
    for a quotation but before every PO in the group got its
    customer_order_id set, a retry must reuse the existing CustomerOrder
    (found by quotation_id) instead of minting a brand-new one."""
    po = _old_tiles_po()
    db = _make_db([po])

    # Simulate the state left behind by a prior partial run: the
    # TileCustomerOrder for this quotation was already inserted (Finding 4
    # step 2), but the PO below was never updated with customer_order_id —
    # i.e. the script crashed somewhere inside the per-PO loop.
    existing_co = backfill_module.TileCustomerOrder(
        number="TORD-2026-0001", quotation_id="q-1", quotation_number="FQ-2026-0001",
        customer_id="cust-1", customer_name="Nileshbhai Pokiya", customer_phone="",
        delivery_name="Nileshbhai Pokiya", delivery_phone="", delivery_address="",
        delivery_city="", delivery_pincode="", delivery_state="", floor_id="ground-floor",
        created_by="system-backfill", created_by_name="Backfill script",
        dashboard_summary=backfill_module.TileCustomerOrderDashboardSummary(),
    )
    db.customer_orders.docs.append(existing_co.dict())

    monkeypatch.setattr(backfill_module, "db", db)
    monkeypatch.setattr(backfill_module, "next_number", _fake_next_number)

    result = asyncio.run(backfill_module.backfill(dry_run=False))

    assert result["customer_orders_created"] == 1
    assert len(db.customer_orders.docs) == 1  # no duplicate CustomerOrder created
    assert db.customer_orders.docs[0]["id"] == existing_co.id
    po_after = db.purchase_orders.docs[0]
    assert po_after["customer_order_id"] == existing_co.id
    # The retry finished the resume: real totals were filled in via the
    # final update, not left at the placeholder values.
    assert db.customer_orders.docs[0]["total_products"] == 1
    assert db.customer_orders.docs[0]["total_boxes"] == 20


def test_backfill_dry_run_makes_no_mutations(monkeypatch):
    """Finding 5: --dry-run must be a true no-op — zero writes to any
    collection, and the original PO document (including its items) left
    byte-for-byte unchanged, not just "unpersisted"."""
    po = _old_tiles_po()
    original_po_snapshot = copy.deepcopy(po)
    db = _make_db([po])
    monkeypatch.setattr(backfill_module, "db", db)
    monkeypatch.setattr(backfill_module, "next_number", _fake_next_number)

    result = asyncio.run(backfill_module.backfill(dry_run=True))

    assert result["customer_orders_created"] == 1
    assert result["chalans_migrated"] == 1
    assert db.customer_orders.docs == []
    assert db.chalans.docs == []
    assert db.dispatches.docs == []
    assert db.ready_batches.docs == []
    assert db.purchase_orders.docs[0] == original_po_snapshot
