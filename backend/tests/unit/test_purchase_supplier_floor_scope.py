"""A purchase order may never be assigned a supplier from another floor."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from routes import purchase_routes


class _Suppliers:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.last_query: dict | None = None

    async def find_one(self, query, *_args, **_kwargs):
        self.last_query = query
        return next((row for row in self.rows if all(row.get(key) == value for key, value in query.items())), None)


class _Db:
    def __init__(self, rows: list[dict]):
        self.suppliers = _Suppliers(rows)


def _po(**overrides):
    return {"id": "po-1", "floor_id": "ground-floor", "brand_id": "tile-brand", **overrides}


def test_supplier_assignment_requires_the_purchase_orders_floor(monkeypatch):
    fake_db = _Db([{"id": "sup-sanitary", "floor_id": "first-floor", "brand_id": "tile-brand"}])
    monkeypatch.setattr(purchase_routes, "db", fake_db)

    with pytest.raises(HTTPException, match="not available on this floor"):
        asyncio.run(purchase_routes._supplier_for_purchase_order("sup-sanitary", _po()))
    assert fake_db.suppliers.last_query == {"id": "sup-sanitary", "floor_id": "ground-floor"}


def test_supplier_assignment_rejects_a_different_brand_on_the_same_floor(monkeypatch):
    fake_db = _Db([{"id": "sup-other", "floor_id": "ground-floor", "brand_id": "other-brand"}])
    monkeypatch.setattr(purchase_routes, "db", fake_db)

    with pytest.raises(HTTPException, match="does not match"):
        asyncio.run(purchase_routes._supplier_for_purchase_order("sup-other", _po()))


def test_supplier_assignment_allows_a_matching_floor_and_brand(monkeypatch):
    supplier = {"id": "sup-tile", "floor_id": "ground-floor", "brand_id": "tile-brand", "name": "Tile Dealer"}
    monkeypatch.setattr(purchase_routes, "db", _Db([supplier]))

    assert asyncio.run(purchase_routes._supplier_for_purchase_order("sup-tile", _po())) == supplier
