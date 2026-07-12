from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

import auth


class FakeCollection:
    def __init__(self, doc: dict | None = None):
        self.doc = doc
        self.find_one_calls = 0
        self.update_calls = 0

    async def find_one(self, *_args, **_kwargs):
        self.find_one_calls += 1
        return self.doc

    async def update_one(self, *_args, **_kwargs):
        self.update_calls += 1
        return None


class FakeDb:
    def __init__(self, session_doc: dict | None = None, user_doc: dict | None = None):
        self.user_sessions = FakeCollection(session_doc)
        self.users = FakeCollection(user_doc)

    def __getitem__(self, name: str):
        return getattr(self, name)



def _staff_doc() -> dict:
    return {
        "id": "user-1",
        "email": "owner@forge.app",
        "full_name": "Owner",
        "role": "owner",
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture(autouse=True)
def clear_auth_cache():
    auth._principal_cache.clear()
    yield
    auth._principal_cache.clear()


def test_get_current_user_reuses_short_lived_principal_cache(monkeypatch):
    fake = FakeDb({"id": "session-1", "revoked": False}, _staff_doc())
    monkeypatch.setattr(auth, "db", fake)
    token = auth.create_token("user-1", "staff", {"role": "owner", "session_id": "session-1"})
    header = f"Bearer {token}"

    async def scenario():
        first = await auth.get_current_user(authorization=header)
        second = await auth.get_current_user(authorization=header)
        return first, second

    first, second = asyncio.run(scenario())

    assert first.id == second.id == "user-1"
    assert fake.user_sessions.find_one_calls == 1
    assert fake.users.find_one_calls == 1


def test_revoked_session_is_never_cached(monkeypatch):
    fake = FakeDb(None, _staff_doc())
    monkeypatch.setattr(auth, "db", fake)
    token = auth.create_token("user-1", "staff", {"role": "owner", "session_id": "session-1"})

    with pytest.raises(Exception) as exc:
        asyncio.run(auth.get_current_user(authorization=f"Bearer {token}"))

    assert getattr(exc.value, "status_code", None) == 401
    assert auth._principal_cache == {}


def test_legacy_staff_token_without_session_still_validates_user(monkeypatch):
    fake = FakeDb(None, _staff_doc())
    monkeypatch.setattr(auth, "db", fake)
    token = auth.create_token("user-1", "staff", {"role": "owner"})

    user = asyncio.run(auth.get_current_user(authorization=f"Bearer {token}"))

    assert user.id == "user-1"
    assert fake.user_sessions.find_one_calls == 0
    assert fake.users.find_one_calls == 1
