"""Regression test: POST /purchases/legacy/items/{item_id}/transfer resolved
its destination customer with a bare `{"id": body.new_customer_id}` lookup —
no floor predicate. Any caller who knew or guessed a customer id from the
OTHER business unit could transfer a purchase item onto them; the handler
then auto-creates a quotation + purchase order for that destination
customer, so this was a cross-unit WRITE, not just a read leak.

Fix mirrors the pattern already used by create_po_for_shortage/
dismiss_shortage in this same file: `floor_query(user, {"id": ...})`. A
cross-unit destination now 404s (same "Destination customer not found"
message as a genuinely missing id) rather than 403ing — a 403 would itself
leak that the id exists in the other business unit.

Both directions are covered: a first-floor caller must not be able to
transfer onto a ground-floor customer, and vice versa. A same-unit transfer
must still succeed.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from models import UserPublic
from routes import purchases_tracker as tracker


def _user(floor_id: str) -> UserPublic:
    return UserPublic(
        email="warehouse@forge.app", full_name="Warehouse Rep", role="warehouse",
        floor_ids=[floor_id], active_floor_id=floor_id,
    )


def _wanted_id(query: dict) -> str | None:
    """floor_query() wraps every filter as {"$and": [{floor_id}, base]} once
    a base filter is present, so the id these fakes match on is one level
    down inside the $and."""
    if "id" in query:
        return query["id"]
    for clause in query.get("$and", []):
        if "id" in clause:
            return clause["id"]
    return None


def _allowed_floor_ids(query: dict) -> list[str] | None:
    if "floor_id" in query and isinstance(query["floor_id"], dict):
        return query["floor_id"].get("$in")
    for clause in query.get("$and", []):
        if isinstance(clause.get("floor_id"), dict):
            return clause["floor_id"].get("$in")
    return None


def _po(floor_id: str, customer_id: str, item_id: str = "item-1", qty: float = 5) -> dict:
    return {
        "id": "po-1", "number": "FPO-2026-0001", "floor_id": floor_id,
        "customer_id": customer_id, "customer_name": "Source Customer",
        "quotation_id": None, "supplier_id": None, "supplier_name": None,
        "brand_id": None, "brand_name": None,
        "items": [{
            "id": item_id, "product_id": "prod-1", "sku": "SKU-1", "name": "Test Item",
            "image": None, "category_id": None, "room": None,
            "qty": qty, "unit_cost": 100.0, "stage": "order_in_company",
            "customer_id": customer_id, "brand_id": None, "brand_name": None,
            "quotation_line_id": None,
        }],
    }


class _FakePurchaseOrders:
    def __init__(self, po: dict):
        self.po = po
        self.inserted: list[dict] = []

    async def find_one(self, query, *_a, **_kw):
        # base filter key is "items.id" here, not "id" — extract it directly
        base_item_id = query.get("items.id")
        if base_item_id is None:
            for clause in query.get("$and", []):
                if "items.id" in clause:
                    base_item_id = clause["items.id"]
        allowed = _allowed_floor_ids(query)
        if allowed is not None and self.po.get("floor_id") not in allowed:
            return None
        if any(i["id"] == base_item_id for i in self.po.get("items", [])):
            return dict(self.po)
        return None

    async def insert_one(self, doc):
        self.inserted.append(doc)

    async def update_one(self, query, update, *_a, **_kw):
        # Only the source PO's own id is ever targeted here.
        if query.get("id") != self.po["id"]:
            class _Result:
                matched_count = 0
            return _Result()
        item_id = query.get("items.id")
        if "$pull" in update:
            pulled_id = update["$pull"]["items"]["id"]
            self.po["items"] = [i for i in self.po["items"] if i["id"] != pulled_id]
        if "$push" in update:
            for key, value in update["$push"].items():
                if key.startswith("items.$."):
                    field = key.split("items.$.", 1)[1]
                    for i in self.po["items"]:
                        if i["id"] == item_id:
                            i.setdefault(field, []).append(value)
        if "$set" in update:
            for key, value in update["$set"].items():
                if key.startswith("items.$."):
                    field = key.split("items.$.", 1)[1]
                    for i in self.po["items"]:
                        if i["id"] == item_id:
                            i[field] = value
                else:
                    self.po[key] = value

        class _Result:
            matched_count = 1
        return _Result()


class _FakeCustomers:
    def __init__(self, customers: list[dict]):
        self.customers = customers

    async def find_one(self, query, *_a, **_kw):
        cid = _wanted_id(query)
        allowed = _allowed_floor_ids(query)
        for c in self.customers:
            if c["id"] != cid:
                continue
            if allowed is not None and c.get("floor_id") not in allowed:
                continue
            return dict(c)
        return None


class _FakeQuotations:
    def __init__(self):
        self.inserted: list[dict] = []

    async def find_one(self, *_a, **_kw):
        return None

    async def insert_one(self, doc):
        self.inserted.append(doc)


class _FakeProducts:
    async def find_one(self, *_a, **_kw):
        return None


class _FakeDb:
    def __init__(self, po: dict, customers: list[dict]):
        self.purchase_orders = _FakePurchaseOrders(po)
        self.customers = _FakeCustomers(customers)
        self.quotations = _FakeQuotations()
        self.products = _FakeProducts()


async def _noop_log_event(**_kwargs):
    return None


async def _noop_reconcile_followups():
    return None


async def _fake_next_po_number():
    return "FPO-2026-0002"


async def _fake_next_quotation_number():
    return "FQ-2026-0001"


def _patch(monkeypatch, fake_db):
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "log_event", _noop_log_event)
    monkeypatch.setattr(tracker, "reconcile_followups", _noop_reconcile_followups)
    monkeypatch.setattr(tracker, "_next_po_number", _fake_next_po_number)
    monkeypatch.setattr(tracker, "_next_quotation_number", _fake_next_quotation_number)


def _customers() -> list[dict]:
    return [
        {"id": "cust-first-floor", "name": "First Floor Customer", "company": None, "floor_id": "first-floor"},
        {"id": "cust-ground-floor", "name": "Ground Floor Customer", "company": None, "floor_id": "ground-floor"},
    ]


def test_first_floor_caller_cannot_transfer_to_ground_floor_customer(monkeypatch):
    po = _po("first-floor", "cust-first-floor-src")
    fake_db = _FakeDb(po, _customers())
    _patch(monkeypatch, fake_db)

    body = tracker.TransferBody(new_customer_id="cust-ground-floor", qty=2)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(tracker.transfer_item("item-1", body, user=_user("first-floor")))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Destination customer not found"
    # Source item must be untouched — the transfer must not have partially applied.
    assert fake_db.purchase_orders.po["items"][0]["qty"] == 5
    assert fake_db.purchase_orders.inserted == []
    assert fake_db.quotations.inserted == []


def test_ground_floor_caller_cannot_transfer_to_first_floor_customer(monkeypatch):
    po = _po("ground-floor", "cust-ground-floor-src")
    fake_db = _FakeDb(po, _customers())
    _patch(monkeypatch, fake_db)

    body = tracker.TransferBody(new_customer_id="cust-first-floor", qty=2)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(tracker.transfer_item("item-1", body, user=_user("ground-floor")))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Destination customer not found"
    assert fake_db.purchase_orders.po["items"][0]["qty"] == 5
    assert fake_db.purchase_orders.inserted == []
    assert fake_db.quotations.inserted == []


def test_same_unit_transfer_still_succeeds(monkeypatch):
    po = _po("ground-floor", "cust-ground-floor-src")
    fake_db = _FakeDb(po, _customers())
    _patch(monkeypatch, fake_db)

    body = tracker.TransferBody(new_customer_id="cust-ground-floor", qty=2)

    result = asyncio.run(tracker.transfer_item("item-1", body, user=_user("ground-floor")))

    assert result["destination"]["customer_id"] == "cust-ground-floor"
    assert result["source"]["remaining_qty"] == 3
    assert fake_db.purchase_orders.po["items"][0]["qty"] == 3
    assert len(fake_db.purchase_orders.inserted) == 1
    assert len(fake_db.quotations.inserted) == 1
