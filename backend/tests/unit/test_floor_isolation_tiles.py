"""Floor isolation for the Tiles domain.

The Tiles module (tile documents, tile orders, releases, dispatches,
chalans, the material movement register) exists on Ground Floor only. Two
production leaks motivated these tests:

  * an all-floors owner/manager on the "All floors" view sent no
    `X-Floor-Id` header at all, so `floor_query()` produced an unscoped
    Mongo filter and Tile Orders listed The Sanitary Bathroom's Vitra
    purchase orders alongside Ground Floor's Qutone/Dimore ones;
  * a Tiles document builder opened against Sanitary Bathroom products
    saved a `tiles_quotation` stamped `first-floor`, which then produced a
    first-floor TileCustomerOrder — giving The Sanitary Bathroom a Tile
    Orders workflow it must never have.

Both are now impossible by construction rather than by request state.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from auth import TILES_FLOOR_ID, tiles_floor_query
from models import UserPublic
from routes.quotation_routes import _floor_for_tiles_document


def _user(*, role="owner", floors=None, active=None) -> UserPublic:
    return UserPublic(
        email="user@forge.app", full_name="User", role=role,
        floor_ids=floors if floors is not None else ["ground-floor", "first-floor"],
        active_floor_id=active,
    )


def _flatten(query: dict) -> dict:
    flat: dict = {}
    for clause in query.get("$and", [query]):
        flat.update(clause)
    return flat


def test_unset_active_floor_still_scopes_to_ground_floor():
    """The "All floors" case — no X-Floor-Id header — used to yield {}."""
    assert tiles_floor_query(_user(active=None)) == {"floor_id": TILES_FLOOR_ID}


def test_sanitary_active_floor_cannot_redirect_a_tiles_query():
    query = tiles_floor_query(_user(active="first-floor"), {"customer_order_id": {"$ne": None}})
    flat = _flatten(query)
    assert flat["floor_id"] == TILES_FLOOR_ID
    assert flat["customer_order_id"] == {"$ne": None}


def test_caller_without_ground_floor_access_is_refused():
    with pytest.raises(HTTPException) as exc:
        tiles_floor_query(_user(role="sales", floors=["first-floor"], active="first-floor"))
    assert exc.value.status_code == 403


def test_tile_document_floor_is_always_ground_floor():
    assert _floor_for_tiles_document(_user(active="first-floor"), {"ground-floor"}) == TILES_FLOOR_ID
    assert _floor_for_tiles_document(_user(active=None), set()) == TILES_FLOOR_ID


def test_tile_document_rejects_sanitary_products():
    with pytest.raises(HTTPException) as exc:
        _floor_for_tiles_document(_user(active="ground-floor"), {"first-floor"})
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException):
        _floor_for_tiles_document(_user(active="ground-floor"), {"ground-floor", "first-floor"})
