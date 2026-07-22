"""Godown/Dispatch chalan actions, tracked per-batch (a single order can
have some chalans dispatched while others are still at the factory or in
the godown — see design doc). Dispatch of the LAST outstanding chalan
notifies the order's creator/assignee that the order is fully complete."""
from __future__ import annotations

import asyncio

import pytest

from models import UserPublic
from routes import purchases_tracker as tracker


def _user() -> UserPublic:
    return UserPublic(
        email="wh@forge.app", full_name="Warehouse Rep", role="warehouse",
        floor_ids=["ground-floor"], active_floor_id="ground-floor",
    )


def _po_with_chalan(stage: str = "released") -> dict:
    return {
        "id": "po-1", "number": "FPO-0001", "customer_id": "cust-1",
        "customer_name": "Nileshbhai Pokiya", "created_by": "u-sales", "assigned_to": "u-sales",
        "items": [{"id": "item-1", "name": "Glossy Ivory", "qty": 40}],
        "chalans": [{
            "id": "ch-1", "number": "CH-0001", "stage": stage, "created_at": "2026-07-22T10:00:00+00:00",
            "items": [{"po_item_id": "item-1", "qty": 40, "name": "Glossy Ivory", "unit": "Box"}],
        }],
    }


class _FakePOsMulti:
    """Applies `chalans.$.<field>` $set updates to the matching chalan by id
    — enough of Mongo's positional-operator semantics to test these two
    single-chalan-update endpoints without a live database."""

    def __init__(self, po: dict):
        self._po = po
        self.update_calls = 0

    async def find_one(self, *_args, **_kwargs):
        return dict(self._po)

    async def update_one(self, query, update):
        self.update_calls += 1
        chalan_id = query.get("chalans.id")
        for chalan in self._po["chalans"]:
            if chalan["id"] == chalan_id:
                for key, value in update.get("$set", {}).items():
                    if key.startswith("chalans.$."):
                        chalan[key[len("chalans.$."):]] = value


class _FakeCustomers:
    async def find_one(self, *_args, **_kwargs):
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


def test_godown_received_rejects_when_not_released(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("dispatched"))
    monkeypatch.setattr(tracker, "db", fake_db)

    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.mark_chalan_godown_received("po-1", "ch-1", user=_user()))
    assert getattr(exc.value, "status_code", None) == 400


def test_dispatch_completes_order_and_notifies_when_last_chalan(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("released"))
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "log_event", _noop_log_event)
    notified: list[tuple] = []

    async def _capture_notify(*args, **kwargs):
        notified.append((args, kwargs))

    monkeypatch.setattr(tracker, "notify", _capture_notify)

    body = tracker.DispatchChalanBody(dispatch_note="Delivered by hand")
    result = asyncio.run(tracker.dispatch_chalan("po-1", "ch-1", body, user=_user()))

    assert result["stage"] == "completed"
    assert fake_db.purchase_orders._po["chalans"][0]["stage"] == "dispatched"
    assert len(notified) == 1
    assert notified[0][0][1] == "Your tile order has been dispatched"


def test_dispatch_rejects_when_already_dispatched(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("dispatched"))
    monkeypatch.setattr(tracker, "db", fake_db)

    body = tracker.DispatchChalanBody()
    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.dispatch_chalan("po-1", "ch-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 400


def test_chalan_pdf_returns_pdf_response(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("released"))
    monkeypatch.setattr(tracker, "db", fake_db)

    response = asyncio.run(tracker.chalan_pdf("po-1", "ch-1", user=_user()))

    assert response.media_type == "application/pdf"


def test_chalan_pdf_404s_when_chalan_not_found(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("released"))
    monkeypatch.setattr(tracker, "db", fake_db)

    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.chalan_pdf("po-1", "does-not-exist", user=_user()))
    assert getattr(exc.value, "status_code", None) == 404
