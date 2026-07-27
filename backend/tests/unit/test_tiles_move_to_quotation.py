"""Move to Quotation: promotes an approved Tiles Selection into the
Quotation stage. Metadata-only — doc_type flips, status resets to draft,
`items` untouched (everything already filled in at Selection carries over
automatically; fields Selection never collects stay absent/open). Also
covers the new Confirmed-status gate on place_order_preview — the same gate
in place_order_confirm runs inside a real Mongo transaction
(client.start_session()), which isn't worth faking here; it's verified live
in Task 12 instead, since it's the exact same can_place_order() call on the
exact same doc shape."""
from __future__ import annotations

import asyncio

import pytest

from fastapi import HTTPException
from models import UserPublic
import routes.quotation_routes as quotation_routes


def _user() -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales Rep", role="sales",
        floor_ids=["ground-floor"], active_floor_id="ground-floor",
    )


class _Recorder:
    def __init__(self, doc: dict | None):
        self._doc = doc
        self.updates: list[dict] = []

    async def find_one(self, query, *_args, **_kwargs):
        if self._doc is None:
            return None
        # Support both {"id": ...} lookups (get_floor_scoped_or_404) and the
        # post-update re-fetch in the same shape this codebase uses elsewhere.
        return dict(self._doc)

    async def update_one(self, _query, update, **_kwargs):
        self.updates.append(update)
        if "$set" in update:
            self._doc.update(update["$set"])


class _FakeDb:
    def __init__(self, doc: dict | None):
        self.quotations = _Recorder(doc)


def _selection_doc(status: str = "approved") -> dict:
    return {
        "id": "q-1", "number": "FQ-2026-0100", "doc_type": "tiles_selection",
        "status": status, "floor_id": "ground-floor", "customer_id": "cust-1",
        "items": [{"id": "line-1", "product_id": "prod-1", "sku": "SKU-1", "name": "Tile A", "room": "Living", "qty": 1, "unit_price": 0}],
    }


def test_move_to_quotation_flips_doc_type_and_resets_status(monkeypatch):
    fake_db = _FakeDb(_selection_doc("approved"))
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    result = asyncio.run(quotation_routes.move_to_quotation("q-1", user=_user()))

    assert result["doc_type"] == "tiles_quotation"
    assert result["status"] == "draft"
    # Promotion is metadata-only — items carried over byte-for-byte, nothing transformed.
    assert result["items"] == _selection_doc("approved")["items"]


def test_move_to_quotation_rejects_when_not_a_selection(monkeypatch):
    doc = _selection_doc("approved")
    doc["doc_type"] = "tiles_quotation"
    fake_db = _FakeDb(doc)
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(quotation_routes.move_to_quotation("q-1", user=_user()))
    assert exc.value.status_code == 400


def test_move_to_quotation_rejects_when_not_approved(monkeypatch):
    fake_db = _FakeDb(_selection_doc("draft"))
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(quotation_routes.move_to_quotation("q-1", user=_user()))
    assert exc.value.status_code == 400


def test_place_order_preview_rejects_unconfirmed_tiles_quotation(monkeypatch):
    doc = {
        "id": "q-2", "number": "FQ-2026-0101", "doc_type": "tiles_quotation",
        "status": "draft", "floor_id": "ground-floor", "customer_id": "cust-1",
        "items": [{"id": "line-1", "product_id": "prod-1", "sku": "SKU-1", "name": "Tile A", "qty": 1, "unit_price": 100}],
    }
    fake_db = _FakeDb(doc)
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(quotation_routes.place_order_preview("q-2", user=_user()))
    assert exc.value.status_code == 400
    assert "confirm" in exc.value.detail.lower()


def test_place_order_preview_allows_confirmed_tiles_quotation(monkeypatch):
    doc = {
        "id": "q-3", "number": "FQ-2026-0102", "doc_type": "tiles_quotation",
        "status": "approved", "floor_id": "ground-floor", "customer_id": "cust-1",
        "items": [],
    }
    fake_db = _FakeDb(doc)
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    # Empty items still 400s (pre-existing "no items" guard) — proves we
    # reached PAST the new confirmed-status check, not that everything passes.
    with pytest.raises(HTTPException) as exc:
        asyncio.run(quotation_routes.place_order_preview("q-3", user=_user()))
    assert "no items" in exc.value.detail.lower()
