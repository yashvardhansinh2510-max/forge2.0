"""Ground Floor collection extras preserve the original quotation total."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import routes.payment_routes as payment_routes
from models import PaymentOrderExtraUpdate, UserPublic


def _user() -> UserPublic:
    return UserPublic(email="accounts@forge.app", full_name="Accounts", role="accounts", floor_ids=["ground-floor"], active_floor_id="ground-floor")


class _Quotations:
    def __init__(self, doc: dict):
        self.doc = doc
        self.update = None

    async def find_one(self, _query, _projection=None):
        return self.doc

    async def update_one(self, query, update):
        self.update = (query, update)


class _Db:
    def __init__(self, doc: dict):
        self.quotations = _Quotations(doc)


class _Cache:
    async def bump(self, _key):
        return None


def test_ground_floor_extra_is_persisted_and_added_only_to_collection_total(monkeypatch):
    fake_db = _Db({"id": "q-1", "floor_id": "ground-floor", "grand_total": 1000, "status": "ordered"})
    monkeypatch.setattr(payment_routes, "db", fake_db)
    monkeypatch.setattr(payment_routes, "cache", _Cache())

    result = asyncio.run(payment_routes.update_ground_floor_manual_extra(
        "q-1", PaymentOrderExtraUpdate(amount=250.125), user=_user(),
    ))

    assert result == {"quotation_total": 1000.0, "manual_extra_amount": 250.12, "grand_total": 1250.12}
    assert fake_db.quotations.update[1]["$set"]["payment_extra_amount"] == 250.12


def test_manual_extra_rejects_non_ground_floor_orders(monkeypatch):
    monkeypatch.setattr(payment_routes, "db", _Db({"id": "q-1", "floor_id": "first-floor", "grand_total": 1000, "status": "ordered"}))

    with pytest.raises(HTTPException, match="Ground Floor") as exc:
        asyncio.run(payment_routes.update_ground_floor_manual_extra(
            "q-1", PaymentOrderExtraUpdate(amount=100), user=_user(),
        ))

    assert exc.value.status_code == 400
