"""Chalan generation endpoint — validates release quantities against what's
actually remaining, writes the chalan onto the PO, and notifies the order's
creator/assignee (never the customer directly — see design doc)."""
from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from models import UserPublic
from routes import purchases_tracker as tracker
from services import sequence as sequence_service


def _user() -> UserPublic:
    return UserPublic(
        email="wh@forge.app", full_name="Warehouse Rep", role="warehouse",
        floor_ids=["first-floor"], active_floor_id="first-floor",
    )


def _po(**overrides) -> dict:
    base = {
        "id": "po-1", "number": "FPO-0001", "customer_id": "cust-1",
        "customer_name": "Nileshbhai Pokiya", "created_by": "u-sales", "assigned_to": None,
        "floor_id": "first-floor",
        "items": [{"id": "item-1", "name": "Glossy Ivory 600x600", "finish": "600X600", "qty": 40}],
        "chalans": [],
    }
    base.update(overrides)
    return base


class _FakeUpdateResult:
    """Mirrors the one field (`matched_count`) generate_chalan's optimistic-
    concurrency check reads off pymongo's real UpdateResult."""

    def __init__(self, matched_count: int):
        self.matched_count = matched_count


class _FakePOs:
    def __init__(self, po: dict | None, *, synchronize_initial_reads: int = 0):
        self._po = deepcopy(po)
        self.pushed_chalan: dict | None = None
        self.update_calls = 0
        self.update_queries: list[dict] = []
        self.find_queries: list[dict] = []
        self._synchronize_initial_reads = synchronize_initial_reads
        self._initial_reads = 0
        self._initial_read_barrier = asyncio.Event()

    @staticmethod
    def _clauses(query: dict):
        for clause in query.get("$and", [query]):
            yield clause

    def _matches_floor(self, query: dict) -> bool:
        floor_clause = next((c["floor_id"] for c in self._clauses(query) if "floor_id" in c), None)
        return floor_clause == {"$in": [self._po.get("floor_id")]} if floor_clause else True

    async def find_one(self, query, *_args, **_kwargs):
        self.find_queries.append(deepcopy(query))
        if self._po is None:
            return None
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
        if self._po is None or not self._matches_floor(query):
            return _FakeUpdateResult(matched_count=0)

        expected_size = None
        for clause in self._clauses(query):
            if "$or" in clause:
                for option in clause["$or"]:
                    if isinstance(option.get("chalans"), dict) and "$size" in option["chalans"]:
                        expected_size = option["chalans"]["$size"]
            elif isinstance(clause.get("chalans"), dict) and "$size" in clause["chalans"]:
                expected_size = clause["chalans"]["$size"]
        if expected_size is not None and len(self._po.get("chalans", [])) != expected_size:
            return _FakeUpdateResult(matched_count=0)

        self.pushed_chalan = deepcopy(update["$push"]["chalans"])
        self._po.setdefault("chalans", []).append(self.pushed_chalan)
        return _FakeUpdateResult(matched_count=1)


class _FakeDb:
    def __init__(self, po: dict | None):
        self.purchase_orders = _FakePOs(po)


async def _noop_log_event(**_kwargs):
    return None


async def _noop_notify(*_args, **_kwargs):
    return None


async def _fake_next_number(*_args, **_kwargs):
    return "CH-0001"


class _FakeCounters:
    """Backs services.sequence.next_number's `db.counters` calls with an
    already-seeded counter doc, so _seed_from_existing's collection scan
    never runs."""

    def __init__(self):
        self.doc = {"_id": "chalan:CH-", "seq": 0}

    async def find_one(self, query, *_a, **_kw):
        return dict(self.doc) if query.get("_id") == self.doc["_id"] else None

    async def find_one_and_update(self, _query, update, **_kw):
        self.doc["seq"] += update["$inc"]["seq"]
        return dict(self.doc)


class _FakeSequenceDb:
    def __init__(self):
        self.counters = _FakeCounters()


def test_generate_chalan_happy_path(monkeypatch):
    fake_db = _FakeDb(_po())
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "log_event", _noop_log_event)
    monkeypatch.setattr(tracker, "notify", _noop_notify)
    monkeypatch.setattr(tracker, "next_number", _fake_next_number)

    body = tracker.GenerateChalanBody(
        items=[tracker.ChalanItemInput(po_item_id="item-1", qty=15)],
        receiver_name="Nileshbhai Pokiya", sender_name="Kajaria Rep",
    )
    result = asyncio.run(tracker.generate_chalan("po-1", body, user=_user()))

    assert result["chalan"]["number"] == "CH-0001"
    assert result["chalan"]["items"][0]["qty"] == 15
    assert result["stage"] == "order"  # only 15 of 40 released — not fully released yet
    assert fake_db.purchase_orders.update_calls == 1


def test_generate_chalan_supports_multiple_items_and_complete_release(monkeypatch):
    fake_db = _FakeDb(_po(items=[
        {"id": "item-1", "name": "Basin", "finish": "Gloss", "qty": 2},
        {"id": "item-2", "name": "Mixer", "finish": "Chrome", "qty": 3},
    ]))
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "log_event", _noop_log_event)
    monkeypatch.setattr(tracker, "notify", _noop_notify)
    monkeypatch.setattr(tracker, "next_number", _fake_next_number)

    result = asyncio.run(tracker.generate_chalan(
        "po-1",
        tracker.GenerateChalanBody(items=[
            tracker.ChalanItemInput(po_item_id="item-1", qty=2),
            tracker.ChalanItemInput(po_item_id="item-2", qty=3),
        ]),
        user=_user(),
    ))

    assert [(line["po_item_id"], line["qty"]) for line in result["chalan"]["items"]] == [
        ("item-1", 2), ("item-2", 3),
    ]
    assert result["stage"] == "material_released"


def test_generate_chalan_partial_then_complete_never_exceeds_ordered_qty(monkeypatch):
    fake_db = _FakeDb(_po(items=[{"id": "item-1", "name": "Basin", "qty": 10}]))
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "log_event", _noop_log_event)
    monkeypatch.setattr(tracker, "notify", _noop_notify)
    numbers = iter(["CH-0001", "CH-0002"])

    async def _next(*_args, **_kwargs):
        return next(numbers)

    monkeypatch.setattr(tracker, "next_number", _next)

    partial = asyncio.run(tracker.generate_chalan(
        "po-1", tracker.GenerateChalanBody(items=[tracker.ChalanItemInput(po_item_id="item-1", qty=4)]),
        user=_user(),
    ))
    complete = asyncio.run(tracker.generate_chalan(
        "po-1", tracker.GenerateChalanBody(items=[tracker.ChalanItemInput(po_item_id="item-1", qty=6)]),
        user=_user(),
    ))

    released = sum(c["items"][0]["qty"] for c in fake_db.purchase_orders._po["chalans"])
    assert partial["stage"] == "order"
    assert complete["stage"] == "material_released"
    assert released == 10


def test_generate_chalan_repeated_complete_release_has_no_second_mutation_or_events(monkeypatch):
    fake_db = _FakeDb(_po(
        assigned_to="u-manager",
        items=[{"id": "item-1", "name": "Basin", "qty": 10}],
    ))
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "next_number", _fake_next_number)
    events: list[dict] = []
    notifications: list[tuple] = []

    async def _capture_event(**kwargs):
        events.append(kwargs)

    async def _capture_notification(*args, **kwargs):
        notifications.append((args, kwargs))

    monkeypatch.setattr(tracker, "log_event", _capture_event)
    monkeypatch.setattr(tracker, "notify", _capture_notification)
    body = tracker.GenerateChalanBody(items=[tracker.ChalanItemInput(po_item_id="item-1", qty=10)])

    asyncio.run(tracker.generate_chalan("po-1", body, user=_user()))
    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.generate_chalan("po-1", body, user=_user()))

    assert getattr(exc.value, "status_code", None) == 400
    assert fake_db.purchase_orders.update_calls == 1
    assert len(events) == 1
    assert len(notifications) == 2
    assert {entry[0][0] for entry in notifications} == {"u-sales", "u-manager"}
    assert all(entry[1]["floor_id"] == "first-floor" for entry in notifications)
    assert all(entry[1]["link"] == "/purchase-orders/po-1" for entry in notifications)


def test_generate_chalan_concurrent_release_allows_one_winner_without_over_release(monkeypatch):
    fake_db = _FakeDb(
        _po(items=[{"id": "item-1", "name": "Basin", "qty": 10}]),
    )
    fake_db.purchase_orders._synchronize_initial_reads = 2
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "log_event", _noop_log_event)
    monkeypatch.setattr(tracker, "notify", _noop_notify)
    number = 0

    async def _next(*_args, **_kwargs):
        nonlocal number
        number += 1
        return f"CH-{number:04d}"

    monkeypatch.setattr(tracker, "next_number", _next)
    body = tracker.GenerateChalanBody(items=[tracker.ChalanItemInput(po_item_id="item-1", qty=7)])

    async def _race():
        return await asyncio.gather(
            tracker.generate_chalan("po-1", body, user=_user()),
            tracker.generate_chalan("po-1", body, user=_user()),
            return_exceptions=True,
        )

    results = asyncio.run(_race())
    successes = [result for result in results if isinstance(result, dict)]
    conflicts = [result for result in results if getattr(result, "status_code", None) == 409]
    released = sum(line["qty"] for c in fake_db.purchase_orders._po["chalans"] for line in c["items"])

    assert len(successes) == 1
    assert len(conflicts) == 1
    assert released == 7
    assert released <= fake_db.purchase_orders._po["items"][0]["qty"]


def test_generate_chalan_scopes_cas_fresh_read_and_event_to_source_floor(monkeypatch):
    fake_db = _FakeDb(_po())
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "next_number", _fake_next_number)
    events: list[dict] = []

    async def _capture_event(**kwargs):
        events.append(kwargs)

    monkeypatch.setattr(tracker, "log_event", _capture_event)
    monkeypatch.setattr(tracker, "notify", _noop_notify)

    asyncio.run(tracker.generate_chalan(
        "po-1", tracker.GenerateChalanBody(items=[tracker.ChalanItemInput(po_item_id="item-1", qty=1)]),
        user=_user(),
    ))

    update_query = fake_db.purchase_orders.update_queries[0]
    assert {"floor_id": {"$in": ["first-floor"]}} in update_query["$and"]
    assert {"floor_id": {"$in": ["first-floor"]}} in fake_db.purchase_orders.find_queries[-1]["$and"]
    assert events[0]["floor_id"] == "first-floor"
    assert events[0]["purchase_id"] == "po-1"
    assert events[0]["customer_id"] == "cust-1"


def test_generate_chalan_number_uses_hyphenated_prefix(monkeypatch):
    """Regression: services.sequence.next_number concatenates prefix+seq
    with no separator — every other caller in this codebase passes the
    hyphen IN the prefix (e.g. "FPO-2026-"). generate_chalan must do the
    same so the printed Chalan number reads "CH-0001", not "CH0001". Runs
    the REAL next_number (not the tracker.next_number mock used elsewhere
    in this file), so a wrong prefix argument can't hide behind a mock
    that always returns a fixed string regardless of what it was called
    with — which is exactly how this bug shipped undetected the first time."""
    fake_db = _FakeDb(_po())
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "log_event", _noop_log_event)
    monkeypatch.setattr(tracker, "notify", _noop_notify)
    monkeypatch.setattr(sequence_service, "db", _FakeSequenceDb())

    body = tracker.GenerateChalanBody(items=[tracker.ChalanItemInput(po_item_id="item-1", qty=15)])
    result = asyncio.run(tracker.generate_chalan("po-1", body, user=_user()))

    assert result["chalan"]["number"] == "CH-0001"


def test_generate_chalan_rejects_over_release(monkeypatch):
    fake_db = _FakeDb(_po())
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "next_number", _fake_next_number)

    body = tracker.GenerateChalanBody(items=[tracker.ChalanItemInput(po_item_id="item-1", qty=999)])
    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.generate_chalan("po-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 400


def test_generate_chalan_404s_when_po_not_found(monkeypatch):
    fake_db = _FakeDb(None)
    monkeypatch.setattr(tracker, "db", fake_db)

    body = tracker.GenerateChalanBody(items=[tracker.ChalanItemInput(po_item_id="item-1", qty=1)])
    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.generate_chalan("po-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 404
