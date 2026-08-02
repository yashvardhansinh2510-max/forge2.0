"""`update_customer` authorizes against the RECORD's own floor via
`get_floor_scoped_or_404` (deliberately ignoring the ambient X-Floor-Id — see
test_customer_routes_floor_scoped_lookups.py), but both `log_event` calls
passed only `actor=user`. `services/activity_log.py` falls back to
`actor.active_floor_id` whenever `floor_id` is omitted, so an owner with
`X-Floor-Id: ground-floor` editing a Sanitary customer filed the
`customer.updated` event into Ground Floor's activity feed — a positive
mis-file into the wrong business unit.

Fix: pass `floor_id=floor_inherit(existing)` on both `log_event` calls,
matching `routes/quotation_routes.py:485`.
"""
from __future__ import annotations

import asyncio

import routes.customer_routes as customer_routes
from models import CustomerUpdatePayload, UserPublic


def _user(active_floor_id: str) -> UserPublic:
    # The actor's ambient floor is deliberately the OTHER unit from the
    # customer being edited — a test that used the same value for both
    # would pass even with the bug (the fallback in activity_log.py would
    # coincidentally land on the right floor).
    return UserPublic(
        email="owner@forge.app", full_name="Owner", role="owner",
        floor_ids=[], active_floor_id=active_floor_id,
    )


class _FakeCustomers:
    def __init__(self, doc: dict):
        self._doc = dict(doc)

    async def find_one(self, query, projection=None, session=None):
        # Return a snapshot, not the live object — real Mongo find_one()
        # never hands back a reference an in-place update_one() can mutate
        # out from under an already-fetched `existing` document.
        return dict(self._doc)

    async def update_one(self, query, update, session=None):
        if "$set" in update:
            self._doc.update(update["$set"])
        return {"matched_count": 1, "modified_count": 1}


class _FakeDb:
    def __init__(self, doc: dict):
        self.customers = _FakeCustomers(doc)


def test_customer_updated_event_carries_the_customers_floor_not_the_actors(monkeypatch):
    # Record lives on Sanitary Bathroom (first-floor); actor is ambient on
    # Ground Floor — the exact mismatch the bug needs to manifest.
    doc = {"id": "c1", "floor_id": "first-floor", "name": "JK", "portal_enabled": False}
    monkeypatch.setattr(customer_routes, "db", _FakeDb(doc))

    captured: dict = {}

    async def fake_log_event(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(customer_routes, "log_event", fake_log_event)

    asyncio.run(customer_routes.update_customer(
        "c1", CustomerUpdatePayload(name="JK Updated"), user=_user(active_floor_id="ground-floor"),
    ))

    assert captured.get("event_type") == "customer.updated"
    assert captured.get("floor_id") == "first-floor", (
        f"event was filed under {captured.get('floor_id')!r} — the actor's ambient "
        "floor — instead of the customer record's own floor 'first-floor'"
    )


def test_portal_toggle_event_also_carries_the_customers_floor(monkeypatch):
    """The portal_enabled/disabled branch takes a separate log_event call —
    must be fixed independently of the customer.updated branch above."""
    doc = {"id": "c1", "floor_id": "first-floor", "name": "JK", "portal_enabled": False, "email": "jk@example.com"}
    monkeypatch.setattr(customer_routes, "db", _FakeDb(doc))

    captured: dict = {}

    async def fake_log_event(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(customer_routes, "log_event", fake_log_event)

    asyncio.run(customer_routes.update_customer(
        "c1", CustomerUpdatePayload(portal_enabled=True), user=_user(active_floor_id="ground-floor"),
    ))

    assert captured.get("event_type") == "customer.portal_enabled"
    assert captured.get("floor_id") == "first-floor"
