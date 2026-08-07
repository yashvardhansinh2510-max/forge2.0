from __future__ import annotations

import asyncio

from models import UserPublic
from routes import tile_orders as router_module


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _limit):
        return [dict(doc) for doc in self.docs]


class _PurchaseOrders:
    def __init__(self, docs):
        self.docs = docs
        self.query = None

    def find(self, query, *_args, **_kwargs):
        self.query = query
        return _Cursor(self.docs)


class _Db:
    def __init__(self, docs):
        self.purchase_orders = _PurchaseOrders(docs)


def _user() -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales Rep", role="sales",
        floor_ids=["ground-floor"], active_floor_id="ground-floor",
    )


def test_inventory_returns_only_requested_fields_and_uses_godown_balance(monkeypatch):
    fake_db = _Db([
        {
            "id": "po-1", "customer_name": "Customer One",
            "brand_name": "Qutone", "created_at": "2026-08-01T09:00:00+00:00",
            "items": [
                {"id": "item-1", "name": "Ivory Tile", "sku": "SKU-1", "size": "600x600",
                 "boxes_godown": 3, "godown_arrived_at": "2026-08-05T10:00:00+00:00"},
                {"id": "item-2", "name": "Zero Tile", "sku": "SKU-2", "boxes_godown": 0},
            ],
        },
    ])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.godown_inventory(user=_user()))

    assert result["total"] == 1
    assert result["rows"] == [{
        "id": "po-1:item-1", "customer": "Customer One", "name": "Ivory Tile",
        "brand": "Qutone", "product": "SKU-1", "size": "600x600",
        "arrival_date": "2026-08-05T10:00:00+00:00",
    }]
    assert fake_db.purchase_orders.query["$and"][1] == {
        "$or": [{"is_deleted": False}, {"is_deleted": {"$exists": False}}],
    }
