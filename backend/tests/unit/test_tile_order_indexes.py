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


def test_ensure_tile_order_indexes_creates_expected_indexes(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(tile_order_indexes, "db", fake_db)

    asyncio.run(tile_order_indexes.ensure_tile_order_indexes())

    assert len(fake_db.customer_orders.calls) == 4
    assert len(fake_db.purchase_orders.calls) == 3
    assert len(fake_db.ready_batches.calls) == 4
    assert len(fake_db.dispatches.calls) == 4
    assert len(fake_db.chalans.calls) == 2
    unique_names = {kwargs.get("name") for _, kwargs in fake_db.chalans.calls}
    assert "chalan_dispatch_unique" in unique_names
    assert "chalan_number_unique" in unique_names
