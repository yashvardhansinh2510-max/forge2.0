"""GET /quotations gains an optional doc_type filter — backs the new
Quotation Tiles list screen (doc_type=tiles_selection or tiles_quotation).
Omitting it must keep today's "everything the caller's floor scope allows"
behavior."""
from __future__ import annotations

import asyncio

from models import UserPublic
import routes.quotation_routes as quotation_routes


def _user() -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales Rep", role="sales",
        floor_ids=["ground-floor"], active_floor_id="ground-floor",
    )


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def sort(self, *_a, **_kw):
        return self

    async def to_list(self, _n):
        return self._rows


class _Recorder:
    def __init__(self):
        self.last_query = None

    def find(self, query, *_a, **_kw):
        self.last_query = query
        return _Cursor([])


class _FakeDb:
    def __init__(self):
        self.quotations = _Recorder()


def test_list_quotations_with_no_filter_unchanged(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    asyncio.run(quotation_routes.list_quotations(user=_user()))

    assert "doc_type" not in fake_db.quotations.last_query


def test_list_quotations_filters_by_doc_type(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    asyncio.run(quotation_routes.list_quotations(doc_type="tiles_selection", user=_user()))

    assert fake_db.quotations.last_query["doc_type"] == "tiles_selection"
