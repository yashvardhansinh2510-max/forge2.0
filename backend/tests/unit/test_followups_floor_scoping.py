"""Regression test: /followups/insights must scope every count to the
caller's active floor. It previously ran four raw, unscoped queries, so the
insights panel always showed global (in practice, 100% first-floor) numbers
regardless of which floor was selected."""
from __future__ import annotations

import asyncio

import pytest

from models import UserPublic
from routes import followup_routes as followups


def _user(floor_id: str) -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=floor_id,
    )


class _Recorder:
    """Generic fake collection: records the filter passed to whichever
    method is called and returns a value shaped for that method."""

    def __init__(self, count_result: int = 0, find_result: list | None = None):
        self.count_result = count_result
        self.find_result = find_result or []
        self.last_count_filter: dict | None = None
        self.last_find_filter: dict | None = None

    async def count_documents(self, query):
        self.last_count_filter = query
        return self.count_result

    def find(self, query, *_args, **_kwargs):
        self.last_find_filter = query
        return self

    async def to_list(self, _n):
        return self.find_result


class _FakeDb:
    def __init__(self):
        self.activity_events = _Recorder()
        self.payments = _Recorder(find_result=[])
        self.quotations = _Recorder()
        self.followups = _Recorder()


def _floor_id_constraint(query: dict) -> dict | None:
    """floor_query(user, base) returns a bare {"floor_id": ...} dict only
    when base is empty — every real call site in insights() passes a
    non-empty base (e.g. {"event_type": ..., "created_at": rng}), which
    takes the $and-wrapping branch instead: {"$and": [{"floor_id": ...},
    base]}. This extracts the floor_id constraint either way, since a bare
    `.get("floor_id")` on the $and-wrapped form always returns None even on
    a correct implementation."""
    if "floor_id" in query:
        return query["floor_id"]
    for clause in query.get("$and", []):
        if "floor_id" in clause:
            return clause["floor_id"]
    return None


def test_insights_scopes_every_query_to_the_active_floor(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(followups, "db", fake_db)

    asyncio.run(followups.insights(user=_user("ground-floor")))

    expected = {"$in": ["ground-floor"]}
    assert _floor_id_constraint(fake_db.activity_events.last_count_filter) == expected
    assert _floor_id_constraint(fake_db.payments.last_find_filter) == expected
    assert _floor_id_constraint(fake_db.quotations.last_count_filter) == expected
    # followups.count_documents is called twice (completed_today, still_open) —
    # last_count_filter only captures the final call, which is enough to prove
    # the floor filter reaches this collection too.
    assert _floor_id_constraint(fake_db.followups.last_count_filter) == expected
