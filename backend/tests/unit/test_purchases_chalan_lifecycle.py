"""Sanitary Godown/Dispatch Chalan actions, tracked per batch (an order can
have some chalans dispatched while others are still at the factory or in
the godown — see design doc). Dispatch of the LAST outstanding chalan
notifies the order's creator/assignee that the order is fully complete."""
from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from models import UserPublic
from routes import purchases_tracker as tracker


def _user() -> UserPublic:
    return UserPublic(
        email="wh@forge.app", full_name="Warehouse Rep", role="warehouse",
        floor_ids=["first-floor"], active_floor_id="first-floor",
    )


def _po_with_chalan(stage: str = "released") -> dict:
    return {
        "id": "po-1", "number": "FPO-0001", "customer_id": "cust-1",
        "customer_name": "Nileshbhai Pokiya", "created_by": "u-sales", "assigned_to": "u-sales",
        "floor_id": "first-floor",
        "items": [{"id": "item-1", "name": "Glossy Ivory", "qty": 40}],
        "chalans": [{
            "id": "ch-1", "number": "CH-0001", "stage": stage, "created_at": "2026-07-22T10:00:00+00:00",
            "items": [{"po_item_id": "item-1", "qty": 40, "name": "Glossy Ivory", "unit": "Box"}],
        }],
    }


class _FakeUpdateResult:
    """Mirrors the one field (`matched_count`) the godown-received/dispatch
    compare-and-swap checks read off pymongo's real UpdateResult."""

    def __init__(self, matched_count: int):
        self.matched_count = matched_count


class _FakePOsMulti:
    """Applies `chalans.$.<field>` $set updates to the matching chalan by id
    — enough of Mongo's positional-operator + $elemMatch semantics to test
    these two single-chalan-update endpoints without a live database. A
    query with an $elemMatch condition that doesn't match any chalan (the
    CAS guard failing because the stage moved since the read) reports
    matched_count=0 and applies no update, same as the real driver."""

    def __init__(self, po: dict, *, synchronize_initial_reads: int = 0):
        self._po = deepcopy(po)
        self.update_calls = 0
        self.update_queries: list[dict] = []
        self.find_queries: list[dict] = []
        self._synchronize_initial_reads = synchronize_initial_reads
        self._initial_reads = 0
        self._initial_read_barrier = asyncio.Event()

    @staticmethod
    def _clauses(query: dict):
        yield from query.get("$and", [query])

    def _matches_floor(self, query: dict) -> bool:
        floor_clause = next((c["floor_id"] for c in self._clauses(query) if "floor_id" in c), None)
        return floor_clause == {"$in": [self._po["floor_id"]]} if floor_clause else True

    async def find_one(self, query, *_args, **_kwargs):
        self.find_queries.append(deepcopy(query))
        if not self._matches_floor(query):
            return None
        snapshot = deepcopy(self._po)
        if self._initial_reads < self._synchronize_initial_reads:
            self._initial_reads += 1
            if self._initial_reads == self._synchronize_initial_reads:
                self._initial_read_barrier.set()
            await self._initial_read_barrier.wait()
        return snapshot

    async def update_one(self, query, update):
        self.update_calls += 1
        self.update_queries.append(deepcopy(query))
        if not self._matches_floor(query):
            return _FakeUpdateResult(matched_count=0)
        chalan_clause = next((c["chalans"] for c in self._clauses(query) if "chalans" in c), {})
        elem_match = chalan_clause.get("$elemMatch", {})
        chalan_id = elem_match.get("id")
        expected_stage = elem_match.get("stage")
        matched = next(
            (c for c in self._po["chalans"]
             if c["id"] == chalan_id and (expected_stage is None or c.get("stage") == expected_stage)),
            None,
        )
        if matched is None:
            return _FakeUpdateResult(matched_count=0)
        for key, value in update.get("$set", {}).items():
            if key.startswith("chalans.$."):
                matched[key[len("chalans.$."):]] = value
        return _FakeUpdateResult(matched_count=1)


class _FakeCustomers:
    def __init__(self):
        self.find_queries: list[dict] = []

    async def find_one(self, query, *_args, **_kwargs):
        self.find_queries.append(deepcopy(query))
        return {"phone": "+91 98765 43210"}


class _FakeDb:
    def __init__(self, po: dict):
        self.purchase_orders = _FakePOsMulti(po)
        self.customers = _FakeCustomers()


async def _noop_log_event(**_kwargs):
    return None


def test_godown_received_transitions_stage(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("released"))
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "log_event", _noop_log_event)

    result = asyncio.run(tracker.mark_chalan_godown_received("po-1", "ch-1", user=_user()))

    assert result["stage"] == "godown"
    assert fake_db.purchase_orders._po["chalans"][0]["stage"] == "at_godown"


def test_godown_received_logs_one_floor_scoped_event_and_repeat_does_not_duplicate(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("released"))
    monkeypatch.setattr(tracker, "db", fake_db)
    events: list[dict] = []

    async def _capture_event(**kwargs):
        events.append(kwargs)

    monkeypatch.setattr(tracker, "log_event", _capture_event)

    asyncio.run(tracker.mark_chalan_godown_received("po-1", "ch-1", user=_user()))
    with pytest.raises(Exception):
        asyncio.run(tracker.mark_chalan_godown_received("po-1", "ch-1", user=_user()))

    assert len(events) == 1
    assert events[0]["event_type"] == "purchase.chalan_godown_received"
    assert events[0]["floor_id"] == "first-floor"
    assert events[0]["purchase_id"] == "po-1"
    assert events[0]["payload"]["chalan_id"] == "ch-1"
    assert {"floor_id": {"$in": ["first-floor"]}} in fake_db.purchase_orders.update_queries[0]["$and"]
    assert {"floor_id": {"$in": ["first-floor"]}} in fake_db.purchase_orders.find_queries[-1]["$and"]


def test_godown_received_rejects_when_not_released(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("dispatched"))
    monkeypatch.setattr(tracker, "db", fake_db)

    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.mark_chalan_godown_received("po-1", "ch-1", user=_user()))
    assert getattr(exc.value, "status_code", None) == 400


def test_dispatch_completes_order_and_notifies_when_last_chalan(monkeypatch):
    po = _po_with_chalan("released")
    po["assigned_to"] = "u-manager"
    fake_db = _FakeDb(po)
    monkeypatch.setattr(tracker, "db", fake_db)
    events: list[dict] = []
    notified: list[tuple] = []

    async def _capture_event(**kwargs):
        events.append(kwargs)

    async def _capture_notify(*args, **kwargs):
        notified.append((args, kwargs))

    monkeypatch.setattr(tracker, "log_event", _capture_event)
    monkeypatch.setattr(tracker, "notify", _capture_notify)

    body = tracker.DispatchChalanBody(dispatch_note="Delivered by hand")
    result = asyncio.run(tracker.dispatch_chalan("po-1", "ch-1", body, user=_user()))

    assert result["stage"] == "completed"
    assert fake_db.purchase_orders._po["chalans"][0]["stage"] == "dispatched"
    assert len(events) == 1
    assert events[0]["event_type"] == "purchase.chalan_dispatched"
    assert events[0]["floor_id"] == "first-floor"
    assert events[0]["purchase_id"] == "po-1"
    assert len(notified) == 2
    assert {entry[0][0] for entry in notified} == {"u-sales", "u-manager"}
    assert all(entry[0][1] == "Your purchase order has been dispatched" for entry in notified)
    assert all(entry[1]["floor_id"] == "first-floor" for entry in notified)
    assert all(entry[1]["link"] == "/purchase-orders/po-1" for entry in notified)


def test_dispatch_of_one_of_multiple_chalans_is_partial_and_does_not_notify(monkeypatch):
    po = _po_with_chalan("released")
    po["items"][0]["qty"] = 10
    po["chalans"] = [
        {"id": "ch-1", "number": "CH-0001", "stage": "released", "items": [
            {"po_item_id": "item-1", "qty": 6, "name": "Glossy Ivory", "unit": "Box"},
        ]},
        {"id": "ch-2", "number": "CH-0002", "stage": "released", "items": [
            {"po_item_id": "item-1", "qty": 4, "name": "Glossy Ivory", "unit": "Box"},
        ]},
    ]
    fake_db = _FakeDb(po)
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "log_event", _noop_log_event)
    notified: list[tuple] = []

    async def _capture_notify(*args, **kwargs):
        notified.append((args, kwargs))

    monkeypatch.setattr(tracker, "notify", _capture_notify)

    result = asyncio.run(tracker.dispatch_chalan(
        "po-1", "ch-1", tracker.DispatchChalanBody(), user=_user(),
    ))

    assert result["stage"] == "dispatch"
    assert fake_db.purchase_orders._po["chalans"][0]["stage"] == "dispatched"
    assert fake_db.purchase_orders._po["chalans"][1]["stage"] == "released"
    assert notified == []


def test_repeated_dispatch_creates_exactly_one_event_and_notification_set(monkeypatch):
    po = _po_with_chalan("released")
    po["assigned_to"] = "u-manager"
    fake_db = _FakeDb(po)
    monkeypatch.setattr(tracker, "db", fake_db)
    events: list[dict] = []
    notified: list[tuple] = []

    async def _capture_event(**kwargs):
        events.append(kwargs)

    async def _capture_notify(*args, **kwargs):
        notified.append((args, kwargs))

    monkeypatch.setattr(tracker, "log_event", _capture_event)
    monkeypatch.setattr(tracker, "notify", _capture_notify)
    body = tracker.DispatchChalanBody(dispatch_note="Delivered")

    asyncio.run(tracker.dispatch_chalan("po-1", "ch-1", body, user=_user()))
    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.dispatch_chalan("po-1", "ch-1", body, user=_user()))

    assert getattr(exc.value, "status_code", None) == 400
    assert fake_db.purchase_orders.update_calls == 1
    assert len(events) == 1
    assert len(notified) == 2
    # Activity feed, purchase timeline, and customer history are read models
    # over this same event. Its three identities must therefore all point at
    # the one successful embedded-Chalan transition.
    event = events[0]
    assert event["entity_id"] == "po-1"
    assert event["purchase_id"] == "po-1"
    assert event["customer_id"] == "cust-1"
    assert event["floor_id"] == "first-floor"
    assert event["payload"]["chalan_id"] == "ch-1"


def test_concurrent_dispatch_has_one_winner_one_conflict_and_exactly_once_side_effects(monkeypatch):
    po = _po_with_chalan("released")
    po["assigned_to"] = "u-manager"
    fake_db = _FakeDb(po)
    fake_db.purchase_orders._synchronize_initial_reads = 2
    monkeypatch.setattr(tracker, "db", fake_db)
    events: list[dict] = []
    notified: list[tuple] = []

    async def _capture_event(**kwargs):
        events.append(kwargs)

    async def _capture_notify(*args, **kwargs):
        notified.append((args, kwargs))

    monkeypatch.setattr(tracker, "log_event", _capture_event)
    monkeypatch.setattr(tracker, "notify", _capture_notify)
    body = tracker.DispatchChalanBody()

    async def _race():
        return await asyncio.gather(
            tracker.dispatch_chalan("po-1", "ch-1", body, user=_user()),
            tracker.dispatch_chalan("po-1", "ch-1", body, user=_user()),
            return_exceptions=True,
        )

    results = asyncio.run(_race())

    assert len([result for result in results if isinstance(result, dict)]) == 1
    assert len([result for result in results if getattr(result, "status_code", None) == 409]) == 1
    assert len(events) == 1
    assert len(notified) == 2


def test_dispatch_rejects_unknown_stage_without_mutation_or_event(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("cancelled"))
    monkeypatch.setattr(tracker, "db", fake_db)
    events: list[dict] = []

    async def _capture_event(**kwargs):
        events.append(kwargs)

    monkeypatch.setattr(tracker, "log_event", _capture_event)

    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.dispatch_chalan(
            "po-1", "ch-1", tracker.DispatchChalanBody(), user=_user(),
        ))

    assert getattr(exc.value, "status_code", None) == 400
    assert fake_db.purchase_orders.update_calls == 0
    assert events == []


def test_dispatch_rejects_when_already_dispatched(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("dispatched"))
    monkeypatch.setattr(tracker, "db", fake_db)

    body = tracker.DispatchChalanBody()
    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.dispatch_chalan("po-1", "ch-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 400


async def _fake_pdf_branding():
    return {}


def test_chalan_pdf_returns_pdf_response(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("released"))
    monkeypatch.setattr(tracker, "db", fake_db)
    # _pdf_branding is imported from routes.quotation_routes, which resolves
    # its own `db` reference against that module's globals, not tracker.db —
    # monkeypatching tracker.db above does not stop it from hitting the real
    # database. Mock it directly so this stays a real unit test.
    monkeypatch.setattr(tracker, "_pdf_branding", _fake_pdf_branding)

    response = asyncio.run(tracker.chalan_pdf("po-1", "ch-1", user=_user()))

    assert response.media_type == "application/pdf"
    customer_query = fake_db.customers.find_queries[0]
    assert {"floor_id": {"$in": ["first-floor"]}} in customer_query["$and"]


def test_chalan_pdf_404s_when_chalan_not_found(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("released"))
    monkeypatch.setattr(tracker, "db", fake_db)

    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.chalan_pdf("po-1", "does-not-exist", user=_user()))
    assert getattr(exc.value, "status_code", None) == 404
