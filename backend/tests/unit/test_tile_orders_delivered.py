"""Mark Delivered — the workflow's final step.

TileDispatch.delivered_at and the `all_delivered` branches of
derive_item_status/derive_current_location were modelled by the 2026-08
redesign but nothing ever set them, so "Delivered" was a status no order
could reach. These cover the endpoint that closes that gap: the CAS guard
against a double confirmation, and the rule that an ITEM only becomes
Delivered once every dispatch that moved it has been delivered.

Same hand-rolled-fake-db + monkeypatch pattern as test_tile_orders_ready.py.
"""
from __future__ import annotations

import asyncio

import pytest

from models import UserPublic
from routes import tile_orders as router_module


def _user() -> UserPublic:
    return UserPublic(
        email="wh@forge.app", full_name="Warehouse Rep", role="warehouse",
        floor_ids=["ground-floor"], active_floor_id="ground-floor",
    )


def _po() -> dict:
    return {
        "id": "po-1", "number": "FPO-2026-0001", "customer_id": "cust-1", "customer_name": "Nileshbhai Pokiya",
        "customer_order_id": "co-1", "brand_id": "b-1", "brand_name": "Qutone",
        "items": [{
            "id": "item-1", "name": "Glossy Ivory 600x600", "series": None, "finish": None, "size": "600X600",
            "sku": "SKU-1", "qty": 10, "boxes_ready": 0, "boxes_godown": 0, "boxes_dispatched": 10,
            "boxes_pending": 0, "overall_status": "Dispatched", "current_location": "Dispatched",
        }],
    }


def _dispatch(dispatch_id: str, *, delivered: bool = False, items: list[str] | None = None) -> dict:
    return {
        "id": dispatch_id, "dispatch_number": f"DSP-2026-{dispatch_id}", "purchase_order_id": "po-1",
        "customer_order_id": "co-1", "customer_id": "cust-1", "customer_name": "Nileshbhai Pokiya",
        "supplier_name": "Qutone Rajkot", "chalan_id": "ch-1", "source": "released",
        "destination_type": "Customer", "destination_name": "Nileshbhai Pokiya",
        "floor_id": "ground-floor", "is_deleted": False,
        "delivered_at": "2026-07-31T10:00:00+00:00" if delivered else None,
        "godown_received_at": None,
        "ready_batches_consumed": [
            {"ready_batch_id": "rb-1", "po_item_id": item_id, "qty": 5} for item_id in (items or ["item-1"])
        ],
    }


def _chalan() -> dict:
    return {
        "id": "ch-1", "number": "CH-0001", "is_deleted": False, "floor_id": "ground-floor",
        "items": [{"po_item_id": "item-1", "tile_name": "Glossy Ivory 600x600", "boxes": 5,
                   "series": None, "finish": None, "size": "600X600", "sku": "SKU-1"}],
    }


class _FakeSession:
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False
    def start_transaction(self): return self


class _FakeClient:
    async def start_session(self): return _FakeSession()


class _Cursor:
    def __init__(self, docs): self.docs = docs
    async def to_list(self, _limit): return [dict(d) for d in self.docs]


def _wanted_id(query: dict) -> str | None:
    """tiles_floor_query() wraps every filter as {"$and": [{floor_id}, base]},
    so the id these fakes match on is one level down."""
    if "id" in query:
        return query["id"]
    for clause in query.get("$and", []):
        if "id" in clause:
            return clause["id"]
    return None


class _FakeDispatches:
    def __init__(self, docs):
        self.docs = docs
        self.updates: list[dict] = []

    async def find_one(self, query, *_a, session=None, **_kw):
        wanted = _wanted_id(query)
        for doc in self.docs:
            if doc["id"] == wanted:
                return dict(doc)
        return None

    def find(self, _query, *_a, **_kw):
        return _Cursor(self.docs)

    async def update_one(self, query, update, session=None, **_kw):
        matched = 0
        for doc in self.docs:
            if doc["id"] != query.get("id"):
                continue
            # Mirrors the real CAS: `delivered_at: None` only matches a
            # dispatch nobody has confirmed yet.
            if "delivered_at" in query and doc.get("delivered_at") is not None:
                continue
            doc.update(update["$set"])
            matched = 1
        self.updates.append(update["$set"])

        class _Result:
            matched_count = matched
        return _Result()


class _FakeChalans:
    def __init__(self, chalan): self.chalan = chalan
    async def find_one(self, _query, *_a, session=None, **_kw): return dict(self.chalan)
    def find(self, _query, *_a, **_kw):
        row = dict(self.chalan)
        row["dispatch_id"] = "d-1"
        return _Cursor([row])


class _FakePOs:
    def __init__(self, po): self.po = po
    async def find_one(self, _query, *_a, session=None, **_kw): return dict(self.po)

    async def update_one(self, _query, update, session=None, **_kw):
        self.po.update(update["$set"])

        class _Result:
            matched_count = 1
        return _Result()


class _FakeCustomerOrders:
    def __init__(self): self.co = {"id": "co-1", "version": 0, "brands": [
        {"brand_name": "Qutone", "supplier_name": "Qutone Rajkot", "purchase_order_id": "po-1", "status": "Dispatched"},
    ], "total_boxes": 10}

    async def find_one(self, _query, *_a, session=None, **_kw): return dict(self.co)

    async def update_one(self, _query, update, session=None, **_kw):
        self.co.update(update["$set"])

        class _Result:
            matched_count = 1
        return _Result()


class _FakeDb:
    def __init__(self, dispatches, po):
        self.dispatches = _FakeDispatches(dispatches)
        self.chalans = _FakeChalans(_chalan())
        self.purchase_orders = _FakePOs(po)
        self.customer_orders = _FakeCustomerOrders()


async def _noop_log_event(**_kwargs): return None
async def _noop_record_movement(**_kwargs): return {}


def _patch(monkeypatch, fake_db):
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "client", _FakeClient())
    monkeypatch.setattr(router_module, "log_event", _noop_log_event)
    monkeypatch.setattr(router_module, "record_movement", _noop_record_movement)


def test_mark_delivered_sets_status_and_records_receiver(monkeypatch):
    fake_db = _FakeDb([_dispatch("d-1")], _po())
    _patch(monkeypatch, fake_db)

    result = asyncio.run(router_module.mark_dispatch_delivered(
        "d-1", router_module.DeliveredBody(received_by="Site Supervisor"), user=_user(),
    ))

    assert result["delivered_at"]
    delivered = fake_db.dispatches.docs[0]
    assert delivered["delivered_at"]
    # The person who signed for the goods, not the operator who clicked.
    assert delivered["delivered_by_name"] == "Site Supervisor"
    assert fake_db.purchase_orders.po["items"][0]["overall_status"] == "Delivered"
    assert fake_db.purchase_orders.po["items"][0]["current_location"] == "Delivered"
    assert fake_db.purchase_orders.po["overall_status"] == "Delivered"


def test_item_stays_dispatched_while_a_sibling_dispatch_is_undelivered(monkeypatch):
    # Two dispatches moved the same item; only one is being confirmed here.
    fake_db = _FakeDb([_dispatch("d-1"), _dispatch("d-2")], _po())
    _patch(monkeypatch, fake_db)

    asyncio.run(router_module.mark_dispatch_delivered("d-1", router_module.DeliveredBody(), user=_user()))

    assert fake_db.purchase_orders.po["items"][0]["overall_status"] == "Dispatched"
    assert fake_db.purchase_orders.po["overall_status"] == "Dispatched"


def test_mark_delivered_rejects_second_confirmation(monkeypatch):
    fake_db = _FakeDb([_dispatch("d-1", delivered=True)], _po())
    _patch(monkeypatch, fake_db)

    with pytest.raises(Exception) as exc:
        asyncio.run(router_module.mark_dispatch_delivered("d-1", router_module.DeliveredBody(), user=_user()))
    assert getattr(exc.value, "status_code", None) == 400


def test_transport_edit_updates_chalan_and_rejects_empty_body(monkeypatch):
    fake_db = _FakeDb([_dispatch("d-1")], _po())
    _patch(monkeypatch, fake_db)
    updated: dict = {}

    async def _capture_update(_query, update, **_kw):
        updated.update(update["$set"])

        class _Result:
            matched_count = 1
        return _Result()

    fake_db.chalans.update_one = _capture_update

    result = asyncio.run(router_module.update_dispatch_transport(
        "d-1", router_module.DispatchTransportBody(vehicle_number="GJ-01-AB-1234", driver_name="Ramesh"),
        user=_user(),
    ))
    assert result["vehicle_number"] == "GJ-01-AB-1234"
    assert updated["driver_name"] == "Ramesh"
    # Quantities and parties stay immutable — only transport metadata moves.
    assert set(updated) <= {"vehicle_number", "driver_name", "receiver_name", "sender_name", "reference_number", "updated_at"}

    with pytest.raises(Exception) as exc:
        asyncio.run(router_module.update_dispatch_transport(
            "d-1", router_module.DispatchTransportBody(), user=_user(),
        ))
    assert getattr(exc.value, "status_code", None) == 400


def test_history_completion_uses_child_delivery_state_when_parent_rollup_is_stale():
    pos = [{"items": [{"qty": 10, "boxes_dispatched": 10, "overall_status": "Delivered"}]}]
    dispatches = [{"delivered_at": "2026-08-07T10:00:00+00:00"}]

    assert router_module._is_fully_delivered(pos, dispatches)


def test_history_completion_rejects_partial_delivery():
    pos = [{"items": [{"qty": 10, "boxes_dispatched": 9, "overall_status": "Dispatched"}]}]
    dispatches = [{"delivered_at": "2026-08-07T10:00:00+00:00"}]

    assert not router_module._is_fully_delivered(pos, dispatches)


def test_history_completion_uses_100_percent_dispatched_state():
    pos = [{"items": [{"qty": 10, "boxes_dispatched": 10}]}]
    dispatches = [{"created_at": "2026-08-07T10:00:00+00:00", "delivered_at": None}]

    assert router_module._is_fully_dispatched(pos, dispatches)


def test_history_completion_rejects_partial_dispatch():
    pos = [{"items": [{"qty": 10, "boxes_dispatched": 9}]}]
    dispatches = [{"created_at": "2026-08-07T10:00:00+00:00", "delivered_at": None}]

    assert not router_module._is_fully_dispatched(pos, dispatches)


def test_godown_arrival_timestamp_is_first_move_only():
    item = {}
    router_module._ensure_godown_arrival(item, "2026-08-07T10:00:00+00:00")
    router_module._ensure_godown_arrival(item, "2026-08-07T11:00:00+00:00")

    assert item["godown_arrived_at"] == "2026-08-07T10:00:00+00:00"
