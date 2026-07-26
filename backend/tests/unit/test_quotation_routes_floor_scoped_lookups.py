"""Regression test: quotation-by-ID endpoints must not 404 just because the
caller's ambient active-floor header doesn't match the quotation's floor."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import routes.quotation_routes as quotation_routes
from models import UserPublic


def _user(active_floor_id: str = "first-floor") -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=active_floor_id,
    )


class _FakeQuotations:
    def __init__(self, doc: dict | None):
        self._doc = doc

    async def find_one(self, query, projection=None, session=None):
        if self._doc and query.get("id") == self._doc["id"]:
            return self._doc
        return None


class _FakeDb:
    def __init__(self, quotation: dict | None):
        self.quotations = _FakeQuotations(quotation)


def test_get_quotation_ignores_ambient_floor_mismatch(monkeypatch):
    doc = {
        "id": "q1", "floor_id": "ground-floor", "number": "FQ-2026-0001",
        "customer_id": "c1", "customer_name": "Test Customer",
        "created_by": "u1", "created_by_name": "Sales Rep",
        "created_at": "2026-07-26T00:00:00+00:00", "updated_at": "2026-07-26T00:00:00+00:00",
    }
    monkeypatch.setattr(quotation_routes, "db", _FakeDb(doc))

    # Ambient state says first-floor; the quotation is ground-floor. Must
    # still resolve, not 404.
    result = asyncio.run(quotation_routes.get_quotation("q1", user=_user(active_floor_id="first-floor")))

    assert result.id == "q1"


def test_get_quotation_still_404s_for_a_real_miss(monkeypatch):
    monkeypatch.setattr(quotation_routes, "db", _FakeDb(None))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(quotation_routes.get_quotation("missing", user=_user()))

    assert exc.value.status_code == 404


def test_place_order_preview_ignores_ambient_floor_mismatch(monkeypatch):
    doc = {"id": "q1", "floor_id": "ground-floor", "number": "FQ-2026-0001", "items": [
        {"id": "l1", "product_id": "p1", "sku": "SKU1", "name": "Tile", "qty": 2, "unit_price": 100.0},
    ]}
    monkeypatch.setattr(quotation_routes, "db", _FakeDb(doc))
    monkeypatch.setattr(quotation_routes, "per_line_net_amounts", lambda d: {"l1": 200.0})

    class _FakeCursor:
        def __init__(self, items):
            self.items = items
        async def to_list(self, _n):
            return self.items

    class _FakeProducts:
        def find(self, *_a, **_kw):
            return _FakeCursor([{"id": "p1", "brand_id": None}])

    quotation_routes.db.products = _FakeProducts()

    class _FakeBrands:
        def find(self, *_a, **_kw):
            return _FakeCursor([])

    quotation_routes.db.brands = _FakeBrands()

    result = asyncio.run(quotation_routes.place_order_preview("q1", user=_user(active_floor_id="first-floor")))

    assert result["quotation_id"] == "q1"
