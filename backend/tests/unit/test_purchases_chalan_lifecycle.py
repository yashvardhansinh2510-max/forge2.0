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
from services import domain_outbox


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

    def __init__(self, matched_count: int, modified_count: int | None = None):
        self.matched_count = matched_count
        self.modified_count = matched_count if modified_count is None else modified_count


class _AsyncContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _FakeSession(_AsyncContext):
    def start_transaction(self):
        return _AsyncContext()


class _FakeClient:
    async def start_session(self):
        return _FakeSession()


class _FakeEvents:
    def __init__(self):
        self.rows: list[dict] = []

    async def find_one(self, query, *_args, **_kwargs):
        return next((deepcopy(row) for row in self.rows if all(row.get(k) == v for k, v in query.items())), None)

    async def insert_one(self, row, **_kwargs):
        self.rows.append(deepcopy(row))


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

    async def update_one(self, query, update, **_kwargs):
        self.update_calls += 1
        self.update_queries.append(deepcopy(query))
        if not self._matches_floor(query):
            return _FakeUpdateResult(matched_count=0)
        chalan_clause = next((c["chalans"] for c in self._clauses(query) if "chalans" in c), {})
        elem_match = chalan_clause.get("$elemMatch", {})
        if not elem_match:
            if self._po.get("chalan_completion_event_key") is not None:
                return _FakeUpdateResult(matched_count=0, modified_count=0)
            for key, value in update.get("$set", {}).items():
                self._po[key] = value
            return _FakeUpdateResult(matched_count=1, modified_count=1)
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
        self.event_outbox = _FakeEvents()


@pytest.fixture(autouse=True)
def _durable_outbox_harness(monkeypatch):
    monkeypatch.setattr(tracker, "client", _FakeClient())

    async def _enqueue(*, event_type, idempotency_key, payload, actor, session):
        event = {
            "id": f"event-{len(tracker.db.event_outbox.rows) + 1}",
            "event_type": event_type,
            "idempotency_key": idempotency_key,
            "payload": deepcopy(payload),
            "actor_id": actor.id,
            "actor_name": actor.full_name,
            "status": "pending",
        }
        await tracker.db.event_outbox.insert_one(event, session=session)
        return event

    async def _dispatch(_event_id):
        return {}

    monkeypatch.setattr(tracker, "enqueue_after_primary_commit", _enqueue)
    monkeypatch.setattr(tracker, "dispatch_event", _dispatch)


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

    asyncio.run(tracker.mark_chalan_godown_received("po-1", "ch-1", user=_user()))
    with pytest.raises(Exception):
        asyncio.run(tracker.mark_chalan_godown_received("po-1", "ch-1", user=_user()))

    assert len(fake_db.event_outbox.rows) == 1
    payload = fake_db.event_outbox.rows[0]["payload"]
    assert payload["activity_event_type"] == "purchase.chalan_godown_received"
    assert payload["floor_id"] == "first-floor"
    assert payload["po_id"] == "po-1"
    assert payload["chalan_id"] == "ch-1"
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
    body = tracker.DispatchChalanBody(dispatch_note="Delivered by hand")
    result = asyncio.run(tracker.dispatch_chalan("po-1", "ch-1", body, user=_user()))

    assert result["stage"] == "completed"
    assert fake_db.purchase_orders._po["chalans"][0]["stage"] == "dispatched"
    payload = fake_db.event_outbox.rows[0]["payload"]
    assert payload["activity_event_type"] == "purchase.chalan_dispatched"
    assert payload["floor_id"] == "first-floor"
    assert len(payload["notifications"]) == 2
    assert {entry["user_id"] for entry in payload["notifications"]} == {"u-sales", "u-manager"}
    assert all(entry["title"] == "Your purchase order has been dispatched" for entry in payload["notifications"])


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
    result = asyncio.run(tracker.dispatch_chalan(
        "po-1", "ch-1", tracker.DispatchChalanBody(), user=_user(),
    ))

    assert result["stage"] == "dispatch"
    assert fake_db.purchase_orders._po["chalans"][0]["stage"] == "dispatched"
    assert fake_db.purchase_orders._po["chalans"][1]["stage"] == "released"
    assert fake_db.event_outbox.rows[0]["payload"]["notifications"] == []


def test_repeated_dispatch_creates_exactly_one_event_and_notification_set(monkeypatch):
    po = _po_with_chalan("released")
    po["assigned_to"] = "u-manager"
    fake_db = _FakeDb(po)
    monkeypatch.setattr(tracker, "db", fake_db)
    body = tracker.DispatchChalanBody(dispatch_note="Delivered")

    asyncio.run(tracker.dispatch_chalan("po-1", "ch-1", body, user=_user()))
    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.dispatch_chalan("po-1", "ch-1", body, user=_user()))

    assert getattr(exc.value, "status_code", None) == 400
    assert fake_db.purchase_orders.update_calls == 2  # dispatch + order completion claim
    assert len(fake_db.event_outbox.rows) == 1
    assert len(fake_db.event_outbox.rows[0]["payload"]["notifications"]) == 2
    # Activity feed, purchase timeline, and customer history are read models
    # over this same event. Its three identities must therefore all point at
    # the one successful embedded-Chalan transition.
    payload = fake_db.event_outbox.rows[0]["payload"]
    assert payload["po_id"] == "po-1"
    assert payload["customer_id"] == "cust-1"
    assert payload["floor_id"] == "first-floor"
    assert payload["chalan_id"] == "ch-1"


def test_concurrent_distinct_final_chalans_claim_completion_notification_once(monkeypatch):
    po = _po_with_chalan("released")
    po["assigned_to"] = "u-manager"
    po["items"][0]["qty"] = 10
    po["chalans"] = [
        {"id": "ch-1", "number": "CH-0001", "stage": "released", "items": [
            {"po_item_id": "item-1", "qty": 5, "name": "Basin", "unit": "PCS"},
        ]},
        {"id": "ch-2", "number": "CH-0002", "stage": "released", "items": [
            {"po_item_id": "item-1", "qty": 5, "name": "Basin", "unit": "PCS"},
        ]},
    ]
    fake_db = _FakeDb(po)
    fake_db.purchase_orders._synchronize_initial_reads = 2
    monkeypatch.setattr(tracker, "db", fake_db)

    async def _race():
        return await asyncio.gather(
            tracker.dispatch_chalan("po-1", "ch-1", tracker.DispatchChalanBody(), user=_user()),
            tracker.dispatch_chalan("po-1", "ch-2", tracker.DispatchChalanBody(), user=_user()),
        )

    results = asyncio.run(_race())
    notifications = [
        notification
        for event in fake_db.event_outbox.rows
        for notification in event["payload"]["notifications"]
    ]

    assert len(results) == 2
    assert all(result["stage"] in {"dispatch", "completed"} for result in results)
    assert fake_db.purchase_orders._po["chalan_completion_event_key"] == "purchase-chalan:po-1:completed"
    assert len(notifications) == 2
    assert {notification["user_id"] for notification in notifications} == {"u-sales", "u-manager"}


def test_chalan_outbox_handler_persists_idempotent_activity_and_notifications(monkeypatch):
    class _PurchaseOrders:
        async def find_one(self, *_args, **_kwargs):
            return {"id": "po-1", "floor_id": "first-floor"}

    class _Upserts:
        def __init__(self):
            self.rows: dict[str, dict] = {}

        async def update_one(self, query, update, *, upsert=False, **_kwargs):
            assert upsert is True
            self.rows.setdefault(query["automation_key"], deepcopy(update["$setOnInsert"]))

    class _Outbox:
        def __init__(self):
            self.rows: list[dict] = []
            self.sessions: list[object] = []

        async def insert_one(self, row, *, session):
            self.rows.append(deepcopy(row))
            self.sessions.append(session)

    activity = _Upserts()
    notifications = _Upserts()
    outbox = _Outbox()
    fake_db = type("Db", (), {
        "purchase_orders": _PurchaseOrders(),
        "activity_events": activity,
        "notifications": notifications,
        "event_outbox": outbox,
    })()
    monkeypatch.setattr(domain_outbox, "db", fake_db)
    monkeypatch.setattr(domain_outbox, "uuid4", lambda: "event-1")
    session = object()
    payload = {
            "activity_event_type": "purchase.chalan_dispatched",
            "po_id": "po-1",
            "customer_id": "cust-1",
            "quotation_id": None,
            "floor_id": "first-floor",
            "chalan_id": "ch-1",
            "chalan_number": "CH-0001",
            "stage": "completed",
            "summary": "Chalan CH-0001 dispatched",
            "notifications": [
                {
                    "user_id": "u-sales", "title": "Order dispatched", "kind": "success",
                    "automation_key": "purchase-chalan:po-1:completed:notification:u-sales",
                },
            ],
    }
    event = asyncio.run(domain_outbox.enqueue_after_primary_commit(
        event_type=domain_outbox.EVENT_PURCHASE_CHALAN_LIFECYCLE,
        idempotency_key="purchase-chalan:po-1:ch-1:dispatch",
        payload=payload,
        actor=_user(),
        session=session,
    ))

    asyncio.run(domain_outbox._handle_purchase_chalan_lifecycle(event, session=session))
    asyncio.run(domain_outbox._handle_purchase_chalan_lifecycle(event, session=session))

    assert len(outbox.rows) == 1
    assert outbox.rows[0]["id"] == "event-1"
    assert outbox.rows[0]["status"] == "pending"
    assert outbox.rows[0]["idempotency_key"] == "purchase-chalan:po-1:ch-1:dispatch"
    assert outbox.sessions == [session]
    assert len(activity.rows) == 1
    assert len(notifications.rows) == 1
    assert set(activity.rows) == {"purchase-chalan:po-1:ch-1:dispatch:activity"}
    assert set(notifications.rows) == {"purchase-chalan:po-1:completed:notification:u-sales"}
    assert activity.rows["purchase-chalan:po-1:ch-1:dispatch:activity"]["floor_id"] == "first-floor"


def test_concurrent_dispatch_has_one_winner_one_conflict_and_exactly_once_side_effects(monkeypatch):
    po = _po_with_chalan("released")
    po["assigned_to"] = "u-manager"
    fake_db = _FakeDb(po)
    fake_db.purchase_orders._synchronize_initial_reads = 2
    monkeypatch.setattr(tracker, "db", fake_db)
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
    assert len(fake_db.event_outbox.rows) == 1
    assert len(fake_db.event_outbox.rows[0]["payload"]["notifications"]) == 2


def test_dispatch_rejects_unknown_stage_without_mutation_or_event(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("cancelled"))
    monkeypatch.setattr(tracker, "db", fake_db)
    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.dispatch_chalan(
            "po-1", "ch-1", tracker.DispatchChalanBody(), user=_user(),
        ))

    assert getattr(exc.value, "status_code", None) == 400
    assert fake_db.purchase_orders.update_calls == 0
    assert fake_db.event_outbox.rows == []


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
