from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone

from models import UserPublic
from routes import tile_orders as router_module


def _user() -> UserPublic:
    return UserPublic(email="sales@forge.app", full_name="Sales Rep", role="sales", floor_ids=["ground-floor"], active_floor_id="ground-floor")


def _iso_days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def _match_value(doc_value, cond) -> bool:
    """Evaluate a single field condition against a document's value for that
    field. Supports the handful of Mongo operators this codebase actually
    uses ($ne, $in, $regex/$options); anything else falls back to plain
    equality."""
    if isinstance(cond, dict):
        ok = True
        for op, val in cond.items():
            if op == "$ne":
                ok = ok and (doc_value != val)
            elif op == "$in":
                ok = ok and (doc_value in val)
            elif op == "$regex":
                flags = re.IGNORECASE if cond.get("$options") == "i" else 0
                ok = ok and bool(re.search(val, doc_value or "", flags))
            elif op == "$options":
                continue
        return ok
    return doc_value == cond


def _matches(doc: dict, query: dict) -> bool:
    """A real (if minimal) Mongo-filter matcher — including $and/$or — so
    fake find()/find_one() calls actually exercise the production filter
    logic (floor_query's {"$and": [...]} wrapper, and the timeline's
    {"$or": [...]} cross-entity query) instead of unconditionally returning
    every stored doc."""
    if not query:
        return True
    for key, cond in query.items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in cond):
                return False
        elif key == "$and":
            if not all(_matches(doc, sub) for sub in cond):
                return False
        else:
            if not _match_value(doc.get(key), cond):
                return False
    return True


class _FakeFind:
    def __init__(self, items): self._items = items
    async def to_list(self, n=None): return list(self._items)


class _FakeCollection:
    def __init__(self, docs): self.docs = docs

    def find(self, query=None, projection=None, session=None):
        return _FakeFind([d for d in self.docs if _matches(d, query or {})])

    async def find_one(self, query=None, projection=None, session=None):
        for doc in self.docs:
            if _matches(doc, query or {}):
                return dict(doc)
        return None


class _FakeDb:
    def __init__(self, customer_orders, purchase_orders, activity_events=None):
        self.customer_orders = _FakeCollection(customer_orders)
        self.purchase_orders = _FakeCollection(purchase_orders)
        self.activity_events = _FakeCollection(activity_events or [])


def test_list_customer_orders_sorted_oldest_first(monkeypatch):
    fake_db = _FakeDb([
        {"id": "co-1", "number": "TORD-2026-0001", "customer_name": "A", "created_at": _iso_days_ago(2), "is_deleted": False, "brands": [], "overall_status": "Pending", "floor_id": "ground-floor"},
        {"id": "co-2", "number": "TORD-2026-0002", "customer_name": "B", "created_at": _iso_days_ago(16), "is_deleted": False, "brands": [], "overall_status": "Ready", "floor_id": "ground-floor"},
    ], [])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.list_customer_orders(user=_user()))

    assert [o["number"] for o in result["orders"]] == ["TORD-2026-0002", "TORD-2026-0001"]
    assert result["orders"][0]["ageing_band"] == "red"


def test_customer_order_detail_groups_by_supplier(monkeypatch):
    co = {"id": "co-1", "number": "TORD-2026-0001", "customer_name": "Nileshbhai", "created_at": _iso_days_ago(5), "brands": [{"purchase_order_id": "po-1"}, {"purchase_order_id": "po-2"}], "total_products": 2, "total_boxes": 30, "completion_percentage": 0, "overall_status": "Pending", "floor_id": "ground-floor"}
    pos = [
        {"id": "po-1", "customer_order_id": "co-1", "floor_id": "ground-floor", "supplier_name": "Qutone Rajkot", "overall_status": "Pending", "items": [{"id": "i-1", "name": "Tile A", "qty": 20, "boxes_ready": 0, "boxes_dispatched": 0, "boxes_pending": 20, "current_location": "Pending", "overall_status": "Pending"}]},
        {"id": "po-2", "customer_order_id": "co-1", "floor_id": "ground-floor", "supplier_name": "Dimore Rajkot", "overall_status": "Pending", "items": [{"id": "i-2", "name": "Tile B", "qty": 10, "boxes_ready": 0, "boxes_dispatched": 0, "boxes_pending": 10, "current_location": "Pending", "overall_status": "Pending"}]},
    ]
    fake_db = _FakeDb([co], pos)
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.customer_order_detail("co-1", user=_user()))

    assert result["summary"]["brand_count"] == 2
    supplier_names = {s["supplier_name"] for s in result["suppliers"]}
    assert supplier_names == {"Qutone Rajkot", "Dimore Rajkot"}


def test_customer_order_detail_excludes_pos_from_other_customer_orders(monkeypatch):
    """Finding 1 regression coverage: purchase_orders belonging to a
    DIFFERENT CustomerOrder (or a different floor) must never show up in
    this order's supplier breakdown, even though the parent CustomerOrder
    lookup itself is floor-scoped. Guards the floor_query(...) fix applied
    to the child purchase_orders.find() call in customer_order_detail."""
    co = {"id": "co-1", "number": "TORD-2026-0001", "customer_name": "Nileshbhai", "created_at": _iso_days_ago(5), "brands": [{"purchase_order_id": "po-1"}], "total_products": 1, "total_boxes": 20, "completion_percentage": 0, "overall_status": "Pending", "floor_id": "ground-floor"}
    pos = [
        {"id": "po-1", "customer_order_id": "co-1", "floor_id": "ground-floor", "supplier_name": "Qutone Rajkot", "overall_status": "Pending", "items": []},
        {"id": "po-2", "customer_order_id": "co-2", "floor_id": "ground-floor", "supplier_name": "Wrong CO Supplier", "overall_status": "Pending", "items": []},
        {"id": "po-3", "customer_order_id": "co-1", "floor_id": "second-floor", "supplier_name": "Wrong Floor Supplier", "overall_status": "Pending", "items": []},
    ]
    fake_db = _FakeDb([co], pos)
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.customer_order_detail("co-1", user=_user()))

    supplier_names = {s["supplier_name"] for s in result["suppliers"]}
    assert supplier_names == {"Qutone Rajkot"}


def test_timeline_merges_events_across_pos(monkeypatch):
    co = {"id": "co-1", "floor_id": "ground-floor"}
    pos = [
        {"id": "po-1", "customer_order_id": "co-1", "floor_id": "ground-floor"},
        {"id": "po-2", "customer_order_id": "co-1", "floor_id": "ground-floor"},
    ]
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


def test_timeline_excludes_events_for_pos_not_linked_to_this_customer_order(monkeypatch):
    """Finding 2 regression coverage: with the fake find() now actually
    respecting its query (including the $or/$in shape the production code
    builds), an event tagged to a purchase order that belongs to a
    DIFFERENT CustomerOrder must be excluded from this order's timeline.
    A broken/incomplete cross-PO merge (e.g. po_ids computed wrong, or the
    $or filter dropped) would leak e-3 into the result and fail this test —
    something the old always-return-everything fake could never catch."""
    co = {"id": "co-1", "floor_id": "ground-floor"}
    pos = [
        {"id": "po-1", "customer_order_id": "co-1", "floor_id": "ground-floor"},
        {"id": "po-2", "customer_order_id": "co-1", "floor_id": "ground-floor"},
        {"id": "po-3", "customer_order_id": "co-2", "floor_id": "ground-floor"},  # belongs to a different CO
    ]
    events = [
        {"id": "e-1", "event_type": "customer_order.created", "entity_type": "tile_customer_order", "entity_id": "co-1", "created_at": "2026-07-27T10:00:00+00:00"},
        {"id": "e-2", "event_type": "dispatch.created", "entity_type": "purchase", "purchase_id": "po-1", "created_at": "2026-07-28T10:00:00+00:00"},
        {"id": "e-3", "event_type": "dispatch.created", "entity_type": "purchase", "purchase_id": "po-3", "created_at": "2026-07-29T10:00:00+00:00"},  # must NOT appear
    ]
    fake_db = _FakeDb([co], pos, events)
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.customer_order_timeline("co-1", user=_user()))

    event_ids = {e["id"] for e in result["events"]}
    assert event_ids == {"e-1", "e-2"}
    assert "e-3" not in event_ids
