"""Index creation has no live DB in tests/unit, so this records what WOULD
be created against a fake db rather than hitting real Mongo — same
constraint every other index-setup function in this codebase has."""
from __future__ import annotations

import asyncio

from services import tile_order_indexes


class _RecordingCollection:
    def __init__(self):
        self.calls: list[tuple] = []

    async def create_index(self, keys, **kwargs):
        self.calls.append((keys, kwargs))


class _FakeDb:
    def __init__(self):
        self.customer_orders = _RecordingCollection()
        self.purchase_orders = _RecordingCollection()
        self.ready_batches = _RecordingCollection()
        self.dispatches = _RecordingCollection()
        self.chalans = _RecordingCollection()
        self.material_movements = _RecordingCollection()


def test_ensure_tile_order_indexes_creates_expected_indexes(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(tile_order_indexes, "db", fake_db)

    asyncio.run(tile_order_indexes.ensure_tile_order_indexes())

    assert len(fake_db.customer_orders.calls) == 5
    assert len(fake_db.purchase_orders.calls) == 3
    assert len(fake_db.ready_batches.calls) == 4
    assert len(fake_db.dispatches.calls) == 4
    assert len(fake_db.chalans.calls) == 2
    assert len(fake_db.material_movements.calls) == 3

    # Verify customer_orders.number unique index
    customer_order_calls = {kwargs.get("name"): (keys, kwargs) for keys, kwargs in fake_db.customer_orders.calls}
    assert "customer_order_number_unique" in customer_order_calls
    keys, kwargs = customer_order_calls["customer_order_number_unique"]
    assert keys == "number"
    assert kwargs.get("unique") is True

    # Verify customer_orders.automation_key unique sparse index (dedupes
    # TileCustomerOrder creation in domain_outbox.py's find-then-upsert)
    assert "customer_order_automation_key" in customer_order_calls
    keys, kwargs = customer_order_calls["customer_order_automation_key"]
    assert keys == "automation_key"
    assert kwargs.get("unique") is True

    # Verify ready_batches.batch_number unique index
    ready_batch_calls = {kwargs.get("name"): (keys, kwargs) for keys, kwargs in fake_db.ready_batches.calls}
    assert "ready_batch_number_unique" in ready_batch_calls
    keys, kwargs = ready_batch_calls["ready_batch_number_unique"]
    assert keys == "batch_number"
    assert kwargs.get("unique") is True

    # Verify dispatches.dispatch_number unique index
    dispatch_calls = {kwargs.get("name"): (keys, kwargs) for keys, kwargs in fake_db.dispatches.calls}
    assert "dispatch_number_unique" in dispatch_calls
    keys, kwargs = dispatch_calls["dispatch_number_unique"]
    assert keys == "dispatch_number"
    assert kwargs.get("unique") is True

    # Verify chalans indexes
    unique_names = {kwargs.get("name") for _, kwargs in fake_db.chalans.calls}
    assert "chalan_dispatch_unique" in unique_names
    assert "chalan_number_unique" in unique_names

    movement_calls = {kwargs.get("name"): (keys, kwargs) for keys, kwargs in fake_db.material_movements.calls}
    assert movement_calls["movement_floor_active_created"][0] == [
        ("floor_id", 1), ("is_deleted", 1), ("created_at", -1),
    ]
