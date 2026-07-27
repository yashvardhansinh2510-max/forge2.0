"""Referrer directory (list + create) — the quotation builder's picker and
the Sales Data dashboard both depend on this being correct."""
from __future__ import annotations

import asyncio

from models import ReferrerCreate, UserPublic
from routes import referrer_routes


def _user(role="sales"):
    return UserPublic(id="user-1", email="s@forge.app", full_name="Sales", role=role)


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_a, **_kw):
        return self

    async def to_list(self, _n):
        return self._docs


class _Collection:
    def __init__(self, docs):
        self._docs = docs
        self.inserted = None

    def find(self, query, *_a, **_kw):
        matched = [d for d in self._docs if all(d.get(k) == v for k, v in query.items())]
        return _Cursor(matched)

    async def insert_one(self, doc):
        self.inserted = doc


class _FakeDb:
    def __init__(self, docs):
        self.referrers = _Collection(docs)


def test_list_referrers_filters_by_type(monkeypatch):
    fake_db = _FakeDb([
        {"id": "r1", "name": "Rakesh Sharma", "type": "architect", "created_at": "t", "updated_at": "t", "created_by": "u"},
        {"id": "r2", "name": "Nikita Shah", "type": "interior_designer", "created_at": "t", "updated_at": "t", "created_by": "u"},
    ])
    monkeypatch.setattr(referrer_routes, "db", fake_db)

    result = asyncio.run(referrer_routes.list_referrers(type="architect", user=_user()))

    assert [r.id for r in result] == ["r1"]


def test_list_referrers_no_filter_returns_all(monkeypatch):
    fake_db = _FakeDb([
        {"id": "r1", "name": "Rakesh Sharma", "type": "architect", "created_at": "t", "updated_at": "t", "created_by": "u"},
        {"id": "r2", "name": "Nikita Shah", "type": "interior_designer", "created_at": "t", "updated_at": "t", "created_by": "u"},
    ])
    monkeypatch.setattr(referrer_routes, "db", fake_db)

    result = asyncio.run(referrer_routes.list_referrers(type=None, user=_user()))

    assert len(result) == 2


def test_create_referrer_stamps_created_by(monkeypatch):
    fake_db = _FakeDb([])
    monkeypatch.setattr(referrer_routes, "db", fake_db)

    body = ReferrerCreate(name="Studio Verve", type="interior_designer")
    result = asyncio.run(referrer_routes.create_referrer(body, user=_user()))

    assert result.created_by == "user-1"
    assert result.name == "Studio Verve"
    assert fake_db.referrers.inserted["name"] == "Studio Verve"
