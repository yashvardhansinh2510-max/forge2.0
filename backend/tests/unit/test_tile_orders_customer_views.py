from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from models import UserPublic
from routes import tile_orders as router_module


def _user() -> UserPublic:
    return UserPublic(email="sales@forge.app", full_name="Sales Rep", role="sales", floor_ids=["ground-floor"], active_floor_id="ground-floor")


def _iso_days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


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


class _FakeDb:
    def __init__(self, customer_orders, purchase_orders, activity_events=None):
        self.customer_orders = _FakeCollection(customer_orders)
        self.purchase_orders = _FakeCollection(purchase_orders)
        self.activity_events = _FakeCollection(activity_events or [])


def test_list_customer_orders_sorted_oldest_first(monkeypatch):
    fake_db = _FakeDb([
        {"id": "co-1", "number": "TORD-2026-0001", "customer_name": "A", "created_at": _iso_days_ago(2), "is_deleted": False, "brands": [], "overall_status": "Pending"},
        {"id": "co-2", "number": "TORD-2026-0002", "customer_name": "B", "created_at": _iso_days_ago(16), "is_deleted": False, "brands": [], "overall_status": "Ready"},
    ], [])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.list_customer_orders(user=_user()))

    assert [o["number"] for o in result["orders"]] == ["TORD-2026-0002", "TORD-2026-0001"]
    assert result["orders"][0]["ageing_band"] == "red"


def test_customer_order_detail_groups_by_supplier(monkeypatch):
    co = {"id": "co-1", "number": "TORD-2026-0001", "customer_name": "Nileshbhai", "created_at": _iso_days_ago(5), "brands": [{"purchase_order_id": "po-1"}, {"purchase_order_id": "po-2"}], "total_products": 2, "total_boxes": 30, "completion_percentage": 0, "overall_status": "Pending"}
    pos = [
        {"id": "po-1", "supplier_name": "Qutone Rajkot", "overall_status": "Pending", "items": [{"id": "i-1", "name": "Tile A", "qty": 20, "boxes_ready": 0, "boxes_dispatched": 0, "boxes_pending": 20, "current_location": "Pending", "overall_status": "Pending"}]},
        {"id": "po-2", "supplier_name": "Dimore Rajkot", "overall_status": "Pending", "items": [{"id": "i-2", "name": "Tile B", "qty": 10, "boxes_ready": 0, "boxes_dispatched": 0, "boxes_pending": 10, "current_location": "Pending", "overall_status": "Pending"}]},
    ]
    fake_db = _FakeDb([co], pos)
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.customer_order_detail("co-1", user=_user()))

    assert result["summary"]["brand_count"] == 2
    supplier_names = {s["supplier_name"] for s in result["suppliers"]}
    assert supplier_names == {"Qutone Rajkot", "Dimore Rajkot"}


def test_timeline_merges_events_across_pos(monkeypatch):
    co = {"id": "co-1"}
    pos = [{"id": "po-1"}, {"id": "po-2"}]
    events = [
        {"id": "e-1", "event_type": "customer_order.created", "entity_type": "tile_customer_order", "entity_id": "co-1", "created_at": "2026-07-27T10:00:00+00:00"},
        {"id": "e-2", "event_type": "dispatch.created", "entity_type": "purchase", "purchase_id": "po-1", "created_at": "2026-07-28T10:00:00+00:00"},
        {"id": "e-3", "event_type": "dispatch.created", "entity_type": "purchase", "purchase_id": "po-2", "created_at": "2026-07-29T10:00:00+00:00"},
    ]
    fake_db = _FakeDb([co], pos, events)
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.customer_order_timeline("co-1", user=_user()))

    assert len(result["events"]) == 3
    assert result["events"][0]["id"] == "e-3"  # newest first
