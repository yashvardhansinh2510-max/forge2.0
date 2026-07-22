"""Customer-wise/Company-wise order views and the order-detail endpoint —
all three read directly from `purchase_orders` (floor-scoped, same as every
other Purchases Tracker read), so there is nothing that can drift out of
sync between the two list views and the detail page."""
from __future__ import annotations

import asyncio

import pytest

from models import UserPublic
from routes import purchases_tracker as tracker


def _user(floor_id: str) -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=floor_id,
    )


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def sort(self, *_a, **_kw):
        return self

    async def to_list(self, _n):
        return self._rows


class _FakePOs:
    def __init__(self, rows):
        self._rows = rows
        self.last_query = None
        self.last_find_one_query = None

    def find(self, query, *_a, **_kw):
        self.last_query = query
        return _FakeCursor(self._rows)

    async def find_one(self, query, *_a, **_kw):
        self.last_find_one_query = query
        return dict(self._rows[0]) if self._rows else None


class _FakeCustomers:
    def find(self, *_a, **_kw):
        return _FakeCursor([])

    async def find_one(self, *_a, **_kw):
        return {"phone": "+91 98765 43210"}


class _FakeDb:
    def __init__(self, rows):
        self.purchase_orders = _FakePOs(rows)
        self.customers = _FakeCustomers()


def _sample_po():
    return {
        "id": "po-1", "number": "FPO-0001", "customer_id": "cust-1",
        "customer_name": "Nileshbhai Pokiya", "supplier_id": "sup-1",
        "supplier_name": "Kajaria", "status": "draft",
        "items": [{"id": "item-1", "qty": 40, "unit_cost": 55}],
        "chalans": [], "created_at": "2026-07-22T10:00:00+00:00",
    }


def test_customer_view_scopes_to_active_floor_and_shapes_cards(monkeypatch):
    fake_db = _FakeDb([_sample_po()])
    monkeypatch.setattr(tracker, "db", fake_db)

    result = asyncio.run(tracker.customer_view_orders(user=_user("ground-floor")))

    assert fake_db.purchase_orders.last_query.get("floor_id") == {"$in": ["ground-floor"]}
    assert result["orders"][0]["stage"] == "order"
    assert result["orders"][0]["total_value"] == 2200.0
    assert result["orders"][0]["total_products"] == 1


def test_company_view_groups_by_supplier(monkeypatch):
    fake_db = _FakeDb([_sample_po()])
    monkeypatch.setattr(tracker, "db", fake_db)

    result = asyncio.run(tracker.company_view_orders(user=_user("ground-floor")))

    assert fake_db.purchase_orders.last_query.get("floor_id") == {"$in": ["ground-floor"]}
    assert result["suppliers"][0]["supplier_name"] == "Kajaria"
    assert len(result["suppliers"][0]["orders"]) == 1


def test_order_detail_includes_stage_and_remaining_qty(monkeypatch):
    fake_db = _FakeDb([_sample_po()])
    monkeypatch.setattr(tracker, "db", fake_db)

    result = asyncio.run(tracker.order_detail("po-1", user=_user("ground-floor")))

    assert fake_db.purchase_orders.last_find_one_query.get("$and")[0] == {"floor_id": {"$in": ["ground-floor"]}}
    assert result["stage"] == "order"
    assert result["remaining_qty_by_item"] == {"item-1": 40.0}
    assert result["customer_phone"] == "+91 98765 43210"


def test_order_detail_404s_when_not_found(monkeypatch):
    fake_db = _FakeDb([])
    monkeypatch.setattr(tracker, "db", fake_db)

    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.order_detail("po-missing", user=_user("ground-floor")))
    assert getattr(exc.value, "status_code", None) == 404
