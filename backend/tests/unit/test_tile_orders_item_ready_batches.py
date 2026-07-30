from __future__ import annotations

import asyncio

from models import UserPublic
from routes import tile_orders as router_module


def _user() -> UserPublic:
    return UserPublic(email="wh@forge.app", full_name="Warehouse Rep", role="warehouse", floor_ids=["ground-floor"], active_floor_id="ground-floor")


class _FakeFind:
    def __init__(self, items): self._items = items
    async def to_list(self, n=None): return list(self._items)


class _FakeReadyBatches:
    def __init__(self, docs): self.docs = docs
    def find(self, query=None, projection=None, session=None):
        matched = [d for d in self.docs if d.get("po_item_id") == query.get("po_item_id") and d.get("remaining_qty", 0) > 0]
        return _FakeFind(matched)


class _FakeDb:
    def __init__(self, docs): self.ready_batches = _FakeReadyBatches(docs)


def test_item_ready_batches_excludes_fully_consumed(monkeypatch):
    fake_db = _FakeDb([
        {"id": "rb-1", "po_item_id": "item-1", "remaining_qty": 4, "created_at": "2026-07-27T10:00:00+00:00"},
        {"id": "rb-2", "po_item_id": "item-1", "remaining_qty": 0, "created_at": "2026-07-28T10:00:00+00:00"},
    ])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.item_ready_batches("po-1", "item-1", user=_user()))

    assert [b["id"] for b in result["batches"]] == ["rb-1"]
