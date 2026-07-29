from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from models import UserPublic
from routes import tile_orders as router_module


def _user() -> UserPublic:
    return UserPublic(email="sales@forge.app", full_name="Sales Rep", role="sales", floor_ids=["ground-floor"], active_floor_id="ground-floor")


def _iso_days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def _po(**overrides) -> dict:
    base = {
        "id": "po-1", "number": "FPO-2026-0001", "supplier_id": "s-1", "supplier_name": "Qutone Rajkot",
        "customer_id": "cust-1", "customer_name": "Nileshbhai Pokiya", "created_at": _iso_days_ago(18),
        "items": [{"id": "item-1", "qty": 20}], "overall_status": "Pending",
        "ready_boxes": 0, "pending_boxes": 20, "dispatched_boxes": 0,
        "completion_percentage": 0, "last_supplier_activity_at": None,
    }
    base.update(overrides)
    return base


class _FakeFind:
    def __init__(self, items): self._items = items
    async def to_list(self, n=None): return list(self._items)


class _FakePOs:
    def __init__(self, docs): self.docs = docs
    def find(self, query=None, projection=None, session=None): return _FakeFind(self.docs)
    async def find_one(self, query=None, projection=None, session=None):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in (query or {}).items() if not k.startswith("$")):
                return dict(doc)
        return None


class _FakeDb:
    def __init__(self, docs): self.purchase_orders = _FakePOs(docs)


def test_list_suppliers_sorts_by_most_stalled_first(monkeypatch):
    fake_db = _FakeDb([
        _po(id="po-1", supplier_id="s-1", supplier_name="Qutone Rajkot", created_at=_iso_days_ago(3)),
        _po(id="po-2", supplier_id="s-2", supplier_name="Dimore Rajkot", created_at=_iso_days_ago(18)),
    ])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.list_suppliers(user=_user()))

    assert result["suppliers"][0]["supplier_name"] == "Dimore Rajkot"
    assert result["suppliers"][0]["max_supplier_silent_days"] == 18
    assert result["suppliers"][1]["supplier_name"] == "Qutone Rajkot"


def test_supplier_orders_kpi_bar_and_sort(monkeypatch):
    fake_db = _FakeDb([
        _po(id="po-1", created_at=_iso_days_ago(3), overall_status="Pending"),
        _po(id="po-2", created_at=_iso_days_ago(18), overall_status="Ready", ready_boxes=10, pending_boxes=10),
        _po(id="po-3", created_at=_iso_days_ago(9), overall_status="Dispatched", dispatched_boxes=20, pending_boxes=0),
    ])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.supplier_orders("s-1", user=_user()))

    assert result["kpi"]["orders"] == 3
    assert result["kpi"]["pending"] == 1
    assert result["kpi"]["ready"] == 1
    assert result["kpi"]["completed"] == 1
    assert result["kpi"]["oldest_pending_days"] == 3
    assert [row["po_id"] for row in result["orders"]] == ["po-2", "po-3", "po-1"]  # oldest waiting first


def test_purchase_order_detail_returns_item_box_breakdown(monkeypatch):
    fake_db = _FakeDb([_po(items=[{
        "id": "item-1", "name": "Glossy Ivory 600x600", "series": "Metropole", "finish": None, "size": "600X600",
        "sku": "SKU-1", "qty": 20, "boxes_ready": 4, "boxes_dispatched": 8, "boxes_pending": 8,
        "current_location": "Dispatched", "overall_status": "Partially Dispatched",
    }])])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.purchase_order_detail("po-1", user=_user()))

    assert result["id"] == "po-1"
    assert result["items"][0]["boxes_ready"] == 4
    assert result["items"][0]["boxes_dispatched"] == 8


def test_supplier_analytics_averages(monkeypatch):
    fake_db = _FakeDb([
        _po(id="po-1", overall_status="Dispatched", dispatched_boxes=20, pending_boxes=0,
            latest_ready_date=_iso_days_ago(5), latest_dispatch_date=_iso_days_ago(1), created_at=_iso_days_ago(10)),
    ])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.supplier_analytics("s-1", user=_user()))

    assert result["orders"] == 1
    assert result["completion_percentage_avg"] == 100.0
