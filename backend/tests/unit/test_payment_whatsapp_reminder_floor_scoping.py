"""`GET /payments/orders/{order_id}/whatsapp-reminder` bound the caller to
`_` and discarded it, so it never checked the quotation's floor against the
caller's access — every other read on a quotation correctly 404s a
cross-unit caller, but this one leaked the customer's name, phone, order
number, grand total, amount paid and outstanding balance plus a prefilled
wa.me link.

Fix: route through `get_floor_scoped_or_404`, same as sibling endpoints."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import routes.payment_routes as payment_routes
from models import UserPublic


def _user(floor_ids: list[str]) -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=floor_ids, active_floor_id=floor_ids[0] if floor_ids else "",
    )


class _FakeQuotations:
    def __init__(self, docs: list[dict]):
        self._docs = {d["id"]: d for d in docs}

    async def find_one(self, query, projection=None, session=None):
        return self._docs.get(query.get("id"))


class _FakeCustomers:
    def __init__(self, docs: list[dict]):
        self._docs = {d["id"]: d for d in docs}

    async def find_one(self, query, projection=None):
        return self._docs.get(query.get("id"))


class _FakePayments:
    def aggregate(self, pipeline):
        return self

    async def to_list(self, _n):
        return []


class _Db:
    def __init__(self, quotations, customers):
        self.quotations = quotations
        self.customers = customers
        self.payments = _FakePayments()


def _quotation(qid: str, floor_id: str) -> dict:
    return {
        "id": qid, "floor_id": floor_id, "customer_id": "cust-1", "customer_name": "Ramesh",
        "number": "Q-2026-001", "grand_total": 50000,
    }


def test_first_floor_caller_gets_rejected_for_ground_floor_order(monkeypatch):
    db = _Db(
        _FakeQuotations([_quotation("q-ground", "ground-floor")]),
        _FakeCustomers([{"id": "cust-1", "name": "Ramesh", "phone": "9820012345"}]),
    )
    monkeypatch.setattr(payment_routes, "db", db)
    user = _user(["first-floor"])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(payment_routes.whatsapp_reminder("q-ground", user=user))

    # get_floor_scoped_or_404 raises 404 (not 403) for a cross-unit id, with
    # the same detail as a genuinely missing one — owner decision
    # 2026-08-02: a 403 would confirm "this id exists, just not for you",
    # an existence oracle across the business-unit boundary. See
    # test_auth_get_floor_scoped_or_404.py.
    assert exc.value.status_code == 404
    assert exc.value.detail == "Order not found"
    # Nothing about the other unit's customer should be reachable from the error.
    assert "Ramesh" not in str(exc.value.detail)
    assert "9820012345" not in str(exc.value.detail)


def test_ground_floor_caller_gets_rejected_for_first_floor_order(monkeypatch):
    """Both directions."""
    db = _Db(
        _FakeQuotations([_quotation("q-first", "first-floor")]),
        _FakeCustomers([{"id": "cust-1", "name": "Anita", "phone": "9820099999"}]),
    )
    monkeypatch.setattr(payment_routes, "db", db)
    user = _user(["ground-floor"])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(payment_routes.whatsapp_reminder("q-first", user=user))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Order not found"


def test_unknown_order_id_is_404(monkeypatch):
    db = _Db(_FakeQuotations([]), _FakeCustomers([]))
    monkeypatch.setattr(payment_routes, "db", db)
    user = _user(["first-floor"])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(payment_routes.whatsapp_reminder("does-not-exist", user=user))

    assert exc.value.status_code == 404


def test_same_unit_caller_still_succeeds(monkeypatch):
    db = _Db(
        _FakeQuotations([_quotation("q-ground", "ground-floor")]),
        _FakeCustomers([{"id": "cust-1", "name": "Ramesh", "phone": "9820012345"}]),
    )
    monkeypatch.setattr(payment_routes, "db", db)
    user = _user(["ground-floor"])

    result = asyncio.run(payment_routes.whatsapp_reminder("q-ground", user=user))

    assert result["customer_name"] == "Ramesh"


def test_all_floor_owner_still_succeeds(monkeypatch):
    db = _Db(
        _FakeQuotations([_quotation("q-ground", "ground-floor")]),
        _FakeCustomers([{"id": "cust-1", "name": "Ramesh", "phone": "9820012345"}]),
    )
    monkeypatch.setattr(payment_routes, "db", db)
    user = UserPublic(email="owner@forge.app", full_name="Owner", role="owner", floor_ids=[], active_floor_id="")

    result = asyncio.run(payment_routes.whatsapp_reminder("q-ground", user=user))

    assert result["customer_name"] == "Ramesh"
