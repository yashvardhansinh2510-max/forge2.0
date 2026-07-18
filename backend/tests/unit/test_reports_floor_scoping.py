"""Regression test: /reports/overview must only aggregate the caller's own
floor's quotations. It previously ran `db.quotations.find({}, ...)` with no
filter at all."""
from __future__ import annotations

import asyncio

from auth import floor_query
from models import UserPublic
from routes import misc_routes


def _user(floor_id: str) -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=floor_id,
    )


class _FakeQuotations:
    def __init__(self):
        self.last_query: dict | None = None

    def find(self, query, *_args, **_kwargs):
        self.last_query = query
        return self

    async def to_list(self, _n):
        return []


class _FakeDb:
    def __init__(self):
        self.quotations = _FakeQuotations()


def test_reports_overview_scopes_to_the_active_floor(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(misc_routes, "db", fake_db)

    asyncio.run(misc_routes.reports_overview(user=_user("ground-floor")))

    expected = floor_query(_user("ground-floor"), {}).get("floor_id")
    assert fake_db.quotations.last_query.get("floor_id") == expected
