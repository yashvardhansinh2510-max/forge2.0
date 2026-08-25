"""Regression test: fetching a record by its own ID must authorize against
that record's floor_id, not pre-filter the query by the caller's ambient
active-floor selection (which 404s legitimate requests whenever ambient
state doesn't happen to match the record)."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from auth import get_floor_scoped_or_404
from models import UserPublic


def _user(role: str = "sales", floor_ids: list[str] | None = None, active_floor_id: str = "") -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role=role,
        floor_ids=floor_ids if floor_ids is not None else ["ground-floor", "first-floor"],
        active_floor_id=active_floor_id,
    )


class _FakeCollection:
    def __init__(self, docs: list[dict]):
        self._docs = {d["id"]: d for d in docs}

    async def find_one(self, query, projection=None, session=None):
        return self._docs.get(query.get("id"))


def test_returns_document_even_when_ambient_floor_differs():
    """The exact bug: caller's active_floor_id is 'first-floor' but the
    quotation they're fetching by ID lives on 'ground-floor' — a
    floor_query()-filtered lookup would 404 here; this helper must not."""
    collection = _FakeCollection([{"id": "q1", "floor_id": "ground-floor"}])
    user = _user(active_floor_id="first-floor")

    doc = asyncio.run(get_floor_scoped_or_404(collection, "q1", user))

    assert doc == {"id": "q1", "floor_id": "ground-floor"}


def test_missing_document_is_404():
    collection = _FakeCollection([])
    user = _user()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_floor_scoped_or_404(collection, "missing", user, not_found="Quotation not found"))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Quotation not found"


def test_cross_unit_access_is_404_not_403_ground_caller_vs_first_floor_record():
    """Owner decision 2026-08-02: a 403 confirms "this id exists, just not
    for you" -- an existence oracle across the business-unit boundary. The
    two units must behave as independent companies, so a cross-unit fetch by
    id must 404 exactly like a genuinely missing id, with a byte-identical
    detail -- a different message would reintroduce the oracle in the
    response body."""
    collection = _FakeCollection([{"id": "q1", "floor_id": "first-floor"}])
    user = _user(floor_ids=["ground-floor"])  # no first-floor access

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_floor_scoped_or_404(collection, "q1", user, not_found="Quotation not found"))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Quotation not found"


def test_cross_unit_access_is_404_not_403_first_floor_caller_vs_ground_floor_record():
    """Both directions -- a single-direction test would pass against code
    that hardcoded one floor."""
    collection = _FakeCollection([{"id": "q1", "floor_id": "ground-floor"}])
    user = _user(floor_ids=["first-floor"])  # no ground-floor access

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_floor_scoped_or_404(collection, "q1", user, not_found="Quotation not found"))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Quotation not found"


def test_cross_unit_404_detail_matches_genuinely_missing_record():
    """The detail string must be identical whether the record doesn't exist
    at all or exists on the other business unit -- otherwise the response
    body itself becomes the oracle."""
    missing_collection = _FakeCollection([])
    other_unit_collection = _FakeCollection([{"id": "q1", "floor_id": "ground-floor"}])
    user = _user(floor_ids=["first-floor"])

    with pytest.raises(HTTPException) as exc_missing:
        asyncio.run(get_floor_scoped_or_404(missing_collection, "q1", user, not_found="Quotation not found"))
    with pytest.raises(HTTPException) as exc_other_unit:
        asyncio.run(get_floor_scoped_or_404(other_unit_collection, "q1", user, not_found="Quotation not found"))

    assert exc_missing.value.status_code == exc_other_unit.value.status_code == 404
    assert exc_missing.value.detail == exc_other_unit.value.detail == "Quotation not found"


def test_all_floor_user_bypasses_the_check():
    collection = _FakeCollection([{"id": "q1", "floor_id": "ground-floor"}])
    user = _user(role="owner", floor_ids=[])  # owners get all-floor access regardless of floor_ids

    doc = asyncio.run(get_floor_scoped_or_404(collection, "q1", user))

    assert doc["id"] == "q1"


def test_missing_floor_id_is_inaccessible_not_first_floor():
    """A record with no floor_id must be treated as inaccessible to every
    caller, not silently filed under Sanitary (first-floor) -- the exact
    mistake migration 0014's design rejects."""
    collection = _FakeCollection([{"id": "q1"}])  # legacy doc, no floor_id at all
    user = _user(floor_ids=["first-floor"])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_floor_scoped_or_404(collection, "q1", user, not_found="Quotation not found"))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Quotation not found"


def test_missing_floor_id_is_inaccessible_even_to_ground_floor_caller():
    """Same as above from the other unit -- a floorless record must not be
    reachable from either side."""
    collection = _FakeCollection([{"id": "q1"}])
    user = _user(floor_ids=["ground-floor"])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_floor_scoped_or_404(collection, "q1", user, not_found="Quotation not found"))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Quotation not found"
