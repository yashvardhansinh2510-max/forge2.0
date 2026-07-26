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


def test_unauthorized_floor_is_403_not_404():
    collection = _FakeCollection([{"id": "q1", "floor_id": "ground-floor"}])
    user = _user(floor_ids=["first-floor"])  # no ground-floor access

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_floor_scoped_or_404(collection, "q1", user))

    assert exc.value.status_code == 403


def test_all_floor_user_bypasses_the_check():
    collection = _FakeCollection([{"id": "q1", "floor_id": "ground-floor"}])
    user = _user(role="owner", floor_ids=[])  # owners get all-floor access regardless of floor_ids

    doc = asyncio.run(get_floor_scoped_or_404(collection, "q1", user))

    assert doc["id"] == "q1"


def test_missing_floor_id_defaults_to_first_floor():
    collection = _FakeCollection([{"id": "q1"}])  # legacy doc, no floor_id at all
    user = _user(floor_ids=["first-floor"])

    doc = asyncio.run(get_floor_scoped_or_404(collection, "q1", user))

    assert doc["id"] == "q1"
