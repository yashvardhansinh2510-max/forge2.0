from __future__ import annotations

import asyncio

from models import UserPublic
from routes import tile_orders as router_module


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _limit):
        return list(self.docs)


class _Collection:
    def __init__(self, docs):
        self.docs = docs
        self.find_calls = []

    def find(self, query, projection=None):
        self.find_calls.append((query, projection))
        return _Cursor(self.docs)


class _Db:
    def __init__(self):
        self.customer_orders = _Collection([{
            "id": "co-1", "customer_id": "customer-1", "customer_name": "Acme",
            "number": "TORD-1", "total_value": 100, "updated_at": "2026-08-02T10:00:00+00:00",
            "is_deleted": False, "floor_id": "ground-floor",
        }])
        self.purchase_orders = _Collection([{
            "id": "po-1", "customer_order_id": "co-1", "brand_id": "brand-1", "brand_name": "Qutone",
            "floor_id": "ground-floor", "items": [{
                "id": "line-1", "name": "Tile", "qty": 5, "boxes_dispatched": 5,
                "quantity_unit": "Box", "pieces_per_box": 4,
            }],
        }])
        self.dispatches = _Collection([{
            "id": "dispatch-1", "customer_order_id": "co-1", "dispatch_number": "DSP-1",
            "created_at": "2026-08-02T10:00:00+00:00", "delivered_at": "2026-08-02T11:00:00+00:00",
            "is_deleted": False, "floor_id": "ground-floor",
        }])
        self.chalans = _Collection([{
            "id": "chalan-1", "customer_order_id": "co-1", "number": "CH-1",
            "is_deleted": False, "floor_id": "ground-floor",
        }])
        self.activity_events = _Collection([{
            "id": "event-1", "entity_type": "tile_customer_order", "entity_id": "co-1",
            "floor_id": "ground-floor", "created_at": "2026-08-02T10:00:00+00:00",
        }])


def _user():
    return UserPublic(
        email="sales@example.com", full_name="Sales", role="sales",
        floor_ids=["ground-floor"], active_floor_id="ground-floor",
    )


def test_history_batches_related_reads_and_returns_stable_id_facets(monkeypatch):
    fake_db = _Db()
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.completed_tile_order_history(page=1, page_size=30, user=_user()))

    assert result["total"] == 1
    assert result["has_more"] is False
    assert result["rows"][0]["customer_id"] == "customer-1"
    assert result["rows"][0]["brand_refs"] == [{"id": "brand-1", "name": "Qutone"}]
    assert result["facets"] == {
        "customers": [{"id": "customer-1", "name": "Acme"}],
        "brands": [{"id": "brand-1", "name": "Qutone"}],
    }
    assert len(fake_db.purchase_orders.find_calls) == 1
    assert len(fake_db.dispatches.find_calls) == 1
    assert len(fake_db.chalans.find_calls) == 1
    assert len(fake_db.activity_events.find_calls) == 1
