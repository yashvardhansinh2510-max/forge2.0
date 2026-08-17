"""Regression coverage for Kitchen/Furniture quotation-follow-up transfers."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from models import UserPublic
from models_walkins import WalkInUpdate
from routes import walkin_routes


class _Result:
    matched_count = 1


class _Walkins:
    def __init__(self, rows):
        self.rows = {row["id"]: dict(row) for row in rows}
        self.updates = []

    async def find_one(self, query, _projection=None):
        row_id = query.get("id") if "id" in query else next(
            (part.get("id") for part in query.get("$and", []) if "id" in part), None
        )
        row = self.rows.get(row_id)
        if not row:
            return None
        floor_ids = next((part.get("floor_id", {}).get("$in") for part in query.get("$and", []) if "floor_id" in part), None)
        if floor_ids and row["floor_id"] not in floor_ids:
            return None
        return dict(row)

    async def update_one(self, query, update):
        row_id = query["id"]
        self.updates.append((row_id, update["$set"]))
        self.rows[row_id].update(update["$set"])
        return _Result()


def _user(floor_id: str) -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Floor Sales", role="sales",
        floor_ids=[floor_id], active_floor_id=floor_id,
    )


def _row(row_id: str, floor_id: str) -> dict:
    return {
        "id": row_id, "number": f"WI-{row_id}", "customer_id": f"customer-{row_id}",
        "customer_name": "Asha", "customer_phone": "9876543210",
        "visited_at": "2026-08-01T00:00:00+00:00", "floor_id": floor_id,
        "status": "selection_scheduled", "is_deleted": False,
        "interested_products": [], "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00", "notes": None,
    }


@pytest.mark.parametrize("floor_id,row_id", [("second-floor", "kitchen"), ("third-floor", "furniture")])
def test_transfer_marks_each_floor_walkin_converted(monkeypatch, floor_id, row_id):
    walkins = _Walkins([_row(row_id, floor_id)])
    monkeypatch.setattr(walkin_routes, "db", SimpleNamespace(walkins=walkins))
    monkeypatch.setattr(walkin_routes, "log_event", _noop)
    monkeypatch.setattr(walkin_routes, "reconcile_followups", _noop)

    updated = asyncio.run(walkin_routes.update_walkin(row_id, WalkInUpdate(status="converted"), _user(floor_id)))

    assert updated.status == "converted"
    assert walkins.rows[row_id]["status"] == "converted"
    assert walkins.updates[0][0] == row_id

    # Repeating the transfer is safe: it remains one converted walk-in and
    # does not create a second source row for the quotation-follow-up view.
    repeated = asyncio.run(walkin_routes.update_walkin(row_id, WalkInUpdate(status="converted"), _user(floor_id)))
    assert repeated.status == "converted"
    assert len(walkins.rows) == 1


def test_transfer_is_floor_scoped(monkeypatch):
    walkins = _Walkins([_row("kitchen", "second-floor"), _row("furniture", "third-floor")])
    monkeypatch.setattr(walkin_routes, "db", SimpleNamespace(walkins=walkins))
    monkeypatch.setattr(walkin_routes, "log_event", _noop)
    monkeypatch.setattr(walkin_routes, "reconcile_followups", _noop)

    with pytest.raises(HTTPException) as error:
        asyncio.run(walkin_routes.update_walkin("furniture", WalkInUpdate(status="converted"), _user("second-floor")))
    assert error.value.status_code == 404
    assert walkins.rows["furniture"]["status"] == "selection_scheduled"


def _noop(*args, **kwargs):
    async def done():
        return None
    return done()


def test_lost_requires_a_note(monkeypatch):
    walkins = _Walkins([_row("lost", "second-floor")])
    monkeypatch.setattr(walkin_routes, "db", SimpleNamespace(walkins=walkins))

    with pytest.raises(HTTPException) as error:
        asyncio.run(walkin_routes.update_walkin("lost", WalkInUpdate(status="lost"), _user("second-floor")))
    assert error.value.status_code == 422
    assert walkins.rows["lost"]["status"] == "selection_scheduled"


def test_lost_accepts_note_in_same_update_and_persists_reason(monkeypatch):
    walkins = _Walkins([_row("lost", "second-floor")])
    monkeypatch.setattr(walkin_routes, "db", SimpleNamespace(walkins=walkins))
    monkeypatch.setattr(walkin_routes, "log_event", _noop)
    monkeypatch.setattr(walkin_routes, "reconcile_followups", _noop)

    updated = asyncio.run(walkin_routes.update_walkin(
        "lost", WalkInUpdate(status="lost", notes="Client chose another supplier"), _user("second-floor")
    ))

    assert updated.status == "lost"
    assert walkins.rows["lost"]["notes"] == "Client chose another supplier"
    assert walkins.rows["lost"]["lost_reason"] == "Client chose another supplier"
