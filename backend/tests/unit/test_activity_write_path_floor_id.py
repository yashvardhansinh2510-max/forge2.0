"""Regression test: activity events written by the two automation write
paths that build ActivityEvent directly — domain_outbox._upsert_activity and
transfer_workflow._upsert_activity — must carry the parent document's
floor_id, not silently insert `floor_id: None`.

Root cause: both functions constructed ActivityEvent without ever setting
floor_id, so every quotation.pdf_generated / quotation.order_placed /
customer_order.created / supplier.assigned / purchase.transferred_in /
purchase.transferred_out event was invisible to every business unit's
Activity feed (floor-scoped reads filter strictly on floor_id, and
`Optional[str] = None` inserts as a real null). This was masked by
migration 0014's one-time backfill, which does not touch new rows.

services.domain_outbox.resolve_activity_floor_id now mirrors
migrations/0014_backfill_activity_notification_floor_id.py's resolution
order exactly:

  1. quotation_id  -> that quotation's floor_id
  2. purchase_id   -> that purchase order's floor_id
  3. entity_type/entity_id -> the referenced document's floor_id
  4. customer_id   -> that customer's floor_id

and both _upsert_activity functions call it before constructing the event.

Both Ground Floor and Sanitary Bathroom cases are covered on purpose: a test
that only ever supplied "first-floor" fixtures would pass even if the code
hardcoded that default, which is the exact failure mode the 0014 migration's
design note rejects.
"""
from __future__ import annotations

import asyncio

import services.domain_outbox as domain_outbox
import services.transfer_workflow as transfer_workflow

_SESSION = object()  # sentinel — every lookup must pass this through


class _Collection:
    """Minimal id-keyed collection. Records the session each find_one was
    called with, so tests can assert lookups run inside the caller's
    transaction rather than outside it."""

    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows or []
        self.find_one_sessions: list[object] = []

    async def find_one(self, query, projection=None, session=None):
        self.find_one_sessions.append(session)
        wanted = query.get("id")
        for row in self.rows:
            if row.get("id") == wanted:
                return {k: v for k, v in row.items() if k != "_id"}
        return None


class _ActivityEvents:
    def __init__(self):
        self.upserts: list[dict] = []

    async def update_one(self, _query, update, upsert=False, session=None):
        assert upsert is True
        assert session is _SESSION, "activity_events write must run inside the caller's transaction"
        self.upserts.append(update["$setOnInsert"])


class _FakeDb:
    def __init__(self, *, quotations=None, purchase_orders=None, customers=None):
        self.quotations = _Collection(quotations)
        self.purchase_orders = _Collection(purchase_orders)
        self.customers = _Collection(customers)
        self.products = _Collection()
        self.followups = _Collection()
        self.payments = _Collection()
        self.walkins = _Collection()
        self.activity_events = _ActivityEvents()

    def __getitem__(self, name):
        return getattr(self, name)


# ── domain_outbox._upsert_activity ──────────────────────────────────────────

def test_domain_outbox_activity_inherits_ground_floor_from_quotation(monkeypatch):
    fake_db = _FakeDb(quotations=[{"id": "q-1", "floor_id": "ground-floor"}])
    monkeypatch.setattr(domain_outbox, "db", fake_db)

    asyncio.run(domain_outbox._upsert_activity(
        key="k1", event_type="quotation.pdf_generated", entity_type="quotation", entity_id="q-1",
        actor_id="u1", actor_name="Sales", customer_id=None, quotation_id="q-1", purchase_id=None,
        summary="Quotation generated", payload={}, session=_SESSION,
    ))

    assert fake_db.activity_events.upserts[0]["floor_id"] == "ground-floor"
    assert _SESSION in fake_db.quotations.find_one_sessions


def test_domain_outbox_activity_inherits_first_floor_from_quotation(monkeypatch):
    # Companion to the ground-floor case above — a test that only ever
    # exercised first-floor would pass even if the code hardcoded that
    # default, so both floors must be proven independently.
    fake_db = _FakeDb(quotations=[{"id": "q-2", "floor_id": "first-floor"}])
    monkeypatch.setattr(domain_outbox, "db", fake_db)

    asyncio.run(domain_outbox._upsert_activity(
        key="k2", event_type="quotation.order_placed", entity_type="quotation", entity_id="q-2",
        actor_id="u1", actor_name="Sales", customer_id=None, quotation_id="q-2", purchase_id=None,
        summary="Order placed", payload={}, session=_SESSION,
    ))

    assert fake_db.activity_events.upserts[0]["floor_id"] == "first-floor"


def test_domain_outbox_supplier_assigned_inherits_ground_floor_via_purchase(monkeypatch):
    # supplier.assigned is emitted with quotation_id set too in production,
    # but purchase_id alone must resolve it (mirrors 0014 precedence #2).
    fake_db = _FakeDb(purchase_orders=[{"id": "po-1", "floor_id": "ground-floor"}])
    monkeypatch.setattr(domain_outbox, "db", fake_db)

    asyncio.run(domain_outbox._upsert_activity(
        key="k3", event_type="supplier.assigned", entity_type="purchase", entity_id="po-1",
        actor_id="u1", actor_name="Sales", customer_id=None, quotation_id=None, purchase_id="po-1",
        summary="Supplier assigned", payload={}, session=_SESSION,
    ))

    assert fake_db.activity_events.upserts[0]["floor_id"] == "ground-floor"


def test_domain_outbox_customer_order_created_inherits_ground_floor(monkeypatch):
    # customer_order.created uses entity_type="tile_customer_order", which is
    # not in the 0014 entity_type map — quotation_id must carry it, exactly
    # as production always passes it for this event.
    fake_db = _FakeDb(quotations=[{"id": "q-3", "floor_id": "ground-floor"}])
    monkeypatch.setattr(domain_outbox, "db", fake_db)

    asyncio.run(domain_outbox._upsert_activity(
        key="k4", event_type="customer_order.created", entity_type="tile_customer_order", entity_id="co-1",
        actor_id="u1", actor_name="Sales", customer_id=None, quotation_id="q-3", purchase_id=None,
        summary="Customer order created", payload={}, session=_SESSION,
    ))

    assert fake_db.activity_events.upserts[0]["floor_id"] == "ground-floor"


def test_domain_outbox_activity_stays_null_when_unresolvable(monkeypatch):
    fake_db = _FakeDb()  # no quotation, purchase order, or customer exists
    monkeypatch.setattr(domain_outbox, "db", fake_db)

    asyncio.run(domain_outbox._upsert_activity(
        key="k5", event_type="quotation.pdf_generated", entity_type="quotation", entity_id="q-missing",
        actor_id="u1", actor_name="Sales", customer_id="cust-missing", quotation_id="q-missing", purchase_id=None,
        summary="Quotation generated", payload={}, session=_SESSION,
    ))

    stored = fake_db.activity_events.upserts[0]
    assert stored["floor_id"] is None
    assert stored["floor_id"] != "first-floor"


# ── transfer_workflow._upsert_activity ──────────────────────────────────────

def test_transfer_workflow_activity_inherits_ground_floor_from_purchase(monkeypatch):
    fake_db = _FakeDb(purchase_orders=[{"id": "po-src", "floor_id": "ground-floor"}])
    monkeypatch.setattr(domain_outbox, "db", fake_db)
    monkeypatch.setattr(transfer_workflow, "db", fake_db)

    asyncio.run(transfer_workflow._upsert_activity(
        key="t1", event_type="purchase.transferred_out", entity_type="purchase", entity_id="po-src",
        actor_id="u1", actor_name="Sales", customer_id="cust-1", quotation_id=None, purchase_id="po-src",
        summary="Transferred out", payload={}, session=_SESSION,
    ))

    assert fake_db.activity_events.upserts[0]["floor_id"] == "ground-floor"


def test_transfer_workflow_activity_inherits_first_floor_from_purchase(monkeypatch):
    fake_db = _FakeDb(purchase_orders=[{"id": "po-dst", "floor_id": "first-floor"}])
    monkeypatch.setattr(domain_outbox, "db", fake_db)
    monkeypatch.setattr(transfer_workflow, "db", fake_db)

    asyncio.run(transfer_workflow._upsert_activity(
        key="t2", event_type="purchase.transferred_in", entity_type="purchase", entity_id="po-dst",
        actor_id="u1", actor_name="Sales", customer_id="cust-2", quotation_id=None, purchase_id="po-dst",
        summary="Transferred in", payload={}, session=_SESSION,
    ))

    assert fake_db.activity_events.upserts[0]["floor_id"] == "first-floor"


def test_transfer_workflow_activity_stays_null_when_unresolvable(monkeypatch):
    fake_db = _FakeDb()  # no purchase order, quotation, or customer exists
    monkeypatch.setattr(domain_outbox, "db", fake_db)
    monkeypatch.setattr(transfer_workflow, "db", fake_db)

    asyncio.run(transfer_workflow._upsert_activity(
        key="t3", event_type="purchase.transferred_out", entity_type="purchase", entity_id="po-missing",
        actor_id="u1", actor_name="Sales", customer_id="cust-missing", quotation_id=None, purchase_id="po-missing",
        summary="Transferred out", payload={}, session=_SESSION,
    ))

    stored = fake_db.activity_events.upserts[0]
    assert stored["floor_id"] is None
    assert stored["floor_id"] != "first-floor"
