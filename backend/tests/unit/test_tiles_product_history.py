"""Customer + product tile history lookup — powers the product picker's
"used last time" hint. Returns the most recent match only, across both
Selection and Quotation documents for that customer, scoped to the exact
product. GET /quotations/tiles/product-history has two extra path segments
vs. GET /quotations/{quotation_id} (one segment) so there is no FastAPI
routing collision regardless of registration order."""
from __future__ import annotations

import asyncio

from models import UserPublic
import routes.quotation_routes as quotation_routes


def _user() -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales Rep", role="sales",
        floor_ids=["ground-floor"], active_floor_id="ground-floor",
    )


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def sort(self, *_a, **_kw):
        return self

    async def to_list(self, _n):
        return self._rows


class _Recorder:
    def __init__(self, rows):
        self._rows = rows

    def find(self, *_a, **_kw):
        return _Cursor(self._rows)


class _FakeDb:
    def __init__(self, rows):
        self.quotations = _Recorder(rows)


def test_product_history_returns_most_recent_match(monkeypatch):
    # Two competing documents for the same customer+product, already ordered
    # newest-first (the fake cursor's .sort() is a no-op — it just returns
    # whatever list it was constructed with, mirroring real Mongo's
    # `.sort("created_at", -1)` behavior). The endpoint must return the FIRST
    # match it finds, so this proves it picks `newer` over `older` rather
    # than e.g. the last match, or being indifferent to order entirely.
    newer = {
        "number": "FQ-2026-0050", "created_at": "2026-06-01T00:00:00+00:00", "doc_date": "01-Jun-26",
        "items": [{"product_id": "prod-1", "size": "1200X1800", "rate_sqft": 135, "unit_price": 220, "pcs_per_box": "BOX"}],
    }
    older = {
        "number": "FQ-2026-0010", "created_at": "2026-01-01T00:00:00+00:00", "doc_date": "01-Jan-26",
        "items": [{"product_id": "prod-1", "size": "600X600", "rate_sqft": 60, "unit_price": 90, "pcs_per_box": "SET"}],
    }
    fake_db = _FakeDb([newer, older])
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    result = asyncio.run(quotation_routes.tiles_product_history(customer_id="cust-1", product_id="prod-1", user=_user()))

    assert result == {
        "found": True, "quotation_number": "FQ-2026-0050", "doc_date": "01-Jun-26",
        "size": "1200X1800", "rate_sqft": 135, "rate_box": 220, "pcs_per_box": "BOX",
        "box_sqft": None,
    }


def test_product_history_not_found_when_no_match(monkeypatch):
    fake_db = _FakeDb([])
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    result = asyncio.run(quotation_routes.tiles_product_history(customer_id="cust-1", product_id="prod-1", user=_user()))

    assert result == {"found": False}
