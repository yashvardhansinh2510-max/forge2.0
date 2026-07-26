"""Regression test: fetching/updating a customer by ID must not 404 just
because the caller's ambient active-floor header doesn't match the
customer's floor (e.g. a tiles-builder save while the global floor
switcher is still on the sanitary floor)."""
from __future__ import annotations

import asyncio

from models import UserPublic
import routes.customer_routes as customer_routes


def _user(active_floor_id: str = "first-floor") -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=active_floor_id,
    )


class _FakeCustomers:
    def __init__(self, doc: dict):
        self._doc = doc
        self.updated_with: dict | None = None
        self.find_one_calls = []
        self.update_one_calls = []

    async def find_one(self, query, projection=None, session=None):
        self.find_one_calls.append({"filter": query, "projection": projection})
        # Handle both flat queries {"id": ...} and $and queries from floor_query
        doc_id = None
        if "id" in query:
            doc_id = query["id"]
        elif "$and" in query:
            # Extract id from $and clause (floor_query wraps in $and)
            for clause in query["$and"]:
                if "id" in clause:
                    doc_id = clause["id"]
                    break
        return self._doc if doc_id == self._doc["id"] else None

    async def update_one(self, query, update, session=None):
        self.update_one_calls.append({"filter": query, "update": update})
        self.updated_with = update
        # Verify the filter is just {"id": ...}, not floor-scoped
        assert query == {"id": self._doc["id"]}, f"Expected {{'id': '{self._doc['id']}'}}, got {query}"
        return {"matched_count": 1, "modified_count": 1}


class _FakeDb:
    def __init__(self, doc: dict):
        self.customers = _FakeCustomers(doc)


def test_get_customer_ignores_ambient_floor_mismatch(monkeypatch):
    doc = {"id": "c1", "floor_id": "ground-floor", "name": "JK"}
    monkeypatch.setattr(customer_routes, "db", _FakeDb(doc))

    result = asyncio.run(customer_routes.get_customer("c1", user=_user(active_floor_id="first-floor")))

    assert result.id == "c1"


def test_update_customer_ignores_ambient_floor_mismatch(monkeypatch):
    from models import CustomerUpdatePayload
    doc = {"id": "c1", "floor_id": "ground-floor", "name": "JK", "portal_enabled": False}
    monkeypatch.setattr(customer_routes, "db", _FakeDb(doc))
    monkeypatch.setattr(customer_routes, "log_event", lambda **_kw: asyncio.sleep(0))

    result = asyncio.run(customer_routes.update_customer(
        "c1", CustomerUpdatePayload(name="JK Updated"), user=_user(active_floor_id="first-floor"),
    ))

    assert result.id == "c1"
    assert customer_routes.db.customers.updated_with["$set"]["name"] == "JK Updated"


def test_update_customer_works_cross_floor(monkeypatch):
    """Regression: update_customer must use bare {"id": ...} filter for
    update_one and find_one when refetching the document, not floor_query().
    Otherwise, ambient floor mismatch causes a silent no-op update, then
    find_one returns None, then CustomerPublic(**None) raises TypeError 500."""
    from models import CustomerUpdatePayload
    doc = {"id": "c1", "floor_id": "ground-floor", "name": "JK", "portal_enabled": False}
    monkeypatch.setattr(customer_routes, "db", _FakeDb(doc))
    monkeypatch.setattr(customer_routes, "log_event", lambda **_kw: asyncio.sleep(0))

    # Call update_customer with a customer on a different floor (ground-floor)
    # but with a user whose ambient active floor is first-floor
    result = asyncio.run(customer_routes.update_customer(
        "c1", CustomerUpdatePayload(name="JK Updated"), user=_user(active_floor_id="first-floor"),
    ))

    # Verify the update succeeded and returned a valid Customer
    assert result.id == "c1"
    assert result.floor_id == "ground-floor"

    # Verify update_one was called with bare {"id": ...} filter
    # (the assertion inside update_one checks this)
    assert len(customer_routes.db.customers.update_one_calls) == 1

    # Verify find_one was called with bare {"id": ...} filter
    # (to refetch the document after the update)
    find_calls_with_bare_filter = [
        call for call in customer_routes.db.customers.find_one_calls
        if call["filter"] == {"id": "c1"}
    ]
    assert len(find_calls_with_bare_filter) > 0, \
        f"Expected find_one to be called with bare filter, got {customer_routes.db.customers.find_one_calls}"
