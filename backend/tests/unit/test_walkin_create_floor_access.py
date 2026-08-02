"""Critical: `POST /walkins` validated `body.floor_id` for EXISTENCE only,
never for whether the caller may access it. Every downstream floor decision
anchored on that attacker-controlled value:

  * a write leak — a first-floor-only user could POST
    `{"floor_id": "ground-floor", ...}` and insert a walk-in (or, without
    `use_existing_customer_id`, a brand new customer) into Ground Floor's
    book;
  * a PII read leak (reopens finding C-3) — posting a name/phone with the
    other unit's `floor_id` ran `find_customer_matches` against that unit and
    the handler raised 409 with `matches` in the body: name, company, phone,
    alternate_phone, email, city, address and tier for up to 5 other-unit
    customers.

The fix calls `require_floor_access(body.floor_id, user)` immediately after
the floor-existence check, before any customer lookup runs.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import routes.walkin_routes as walkin_routes
import services.duplicate_detection as dupes
from models import UserPublic
from models_walkins import WalkInCreate


def _user(floor_ids: list[str]) -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=floor_ids, active_floor_id=floor_ids[0] if floor_ids else "",
    )


class _FakeFloors:
    """Every floor id named below "exists" — the existence check alone must
    not be enough to authorize the request."""

    def __init__(self, ids):
        self._ids = set(ids)

    async def find_one(self, query, projection=None):
        fid = query.get("id")
        return {"id": fid} if fid in self._ids else None


class _ExplodingCollection:
    """Stands in for db.customers / db.users / db.walkins. Any query against
    it means the handler pressed on past the floor-access check with an
    unauthorized floor_id — which is exactly the bug."""

    async def find_one(self, *a, **kw):
        raise AssertionError("customer/user/walkin lookup ran before floor access was authorized")

    async def find(self, *a, **kw):
        raise AssertionError("customer/user/walkin lookup ran before floor access was authorized")

    async def insert_one(self, *a, **kw):
        raise AssertionError("insert ran before floor access was authorized")


class _Db:
    def __init__(self, floor_ids):
        self.floors = _FakeFloors(floor_ids)
        self.customers = _ExplodingCollection()
        self.users = _ExplodingCollection()
        self.walkins = _ExplodingCollection()


def _body(floor_id: str, **kw) -> WalkInCreate:
    return WalkInCreate(
        customer_name="Priya Menon", customer_phone="9820012345", floor_id=floor_id, **kw,
    )


def _blow_up_if_called(**_kwargs):
    raise AssertionError(
        "find_customer_matches ran for a floor the caller has no access to — "
        "this is exactly the C-3 PII-leak path (409 body carrying other-unit "
        "customer name/phone/email)"
    )


def test_create_walkin_rejects_cross_unit_floor_id_first_floor_caller(monkeypatch):
    monkeypatch.setattr(walkin_routes, "db", _Db(["first-floor", "ground-floor"]))
    monkeypatch.setattr(dupes, "find_customer_matches", _blow_up_if_called)
    user = _user(["first-floor"])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(walkin_routes.create_walkin(_body("ground-floor"), user=user))

    assert exc.value.status_code == 403


def test_create_walkin_rejects_cross_unit_floor_id_ground_floor_caller(monkeypatch):
    """Both directions: a Ground-Floor-only caller must be equally blocked
    from naming Sanitary Bathroom's floor_id."""
    monkeypatch.setattr(walkin_routes, "db", _Db(["first-floor", "ground-floor"]))
    monkeypatch.setattr(dupes, "find_customer_matches", _blow_up_if_called)
    user = _user(["ground-floor"])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(walkin_routes.create_walkin(_body("first-floor"), user=user))

    assert exc.value.status_code == 403


def test_create_walkin_rejects_cross_unit_via_existing_customer_id_path(monkeypatch):
    """Same authorization must guard the `use_existing_customer_id` branch —
    reaching it with an unauthorized floor_id would otherwise still attach
    the walk-in to the other unit's customer record."""
    monkeypatch.setattr(walkin_routes, "db", _Db(["first-floor", "ground-floor"]))
    monkeypatch.setattr(dupes, "find_customer_matches", _blow_up_if_called)
    user = _user(["first-floor"])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(walkin_routes.create_walkin(
            _body("ground-floor", use_existing_customer_id="c-other-unit"), user=user,
        ))

    assert exc.value.status_code == 403


def test_no_customer_data_of_any_kind_appears_for_an_unauthorized_floor(monkeypatch):
    """Belt-and-suspenders: even if the 403 were somehow swallowed, no
    response body may ever surface other-unit customer fields. Assert the
    exception detail itself carries no `matches`/PII payload — the shape the
    409 leak used."""
    monkeypatch.setattr(walkin_routes, "db", _Db(["first-floor", "ground-floor"]))
    monkeypatch.setattr(dupes, "find_customer_matches", _blow_up_if_called)
    user = _user(["first-floor"])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(walkin_routes.create_walkin(_body("ground-floor"), user=user))

    assert exc.value.status_code == 403
    assert "matches" not in str(exc.value.detail)
