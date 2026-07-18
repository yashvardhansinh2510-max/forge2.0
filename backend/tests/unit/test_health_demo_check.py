"""/api/health reports a monitoring-consumable degraded status when a staff
account is still on the historical default demo password (BACKEND_AUDIT_2026-07-17.md
Critical #1) — instead of only logging a warning at startup."""
from __future__ import annotations

import asyncio

import pytest

import server


class _FakeDb:
    async def command(self, *_args, **_kwargs):
        return {"ok": 1}


@pytest.fixture(autouse=True)
def reset_demo_check_cache():
    server._demo_check_cache["checked_at"] = 0.0
    server._demo_check_cache["emails"] = []
    yield
    server._demo_check_cache["checked_at"] = 0.0
    server._demo_check_cache["emails"] = []


def test_health_ok_when_no_demo_accounts_detected(monkeypatch):
    monkeypatch.setattr(server, "db", _FakeDb())

    async def _no_matches(_db):
        return []

    monkeypatch.setattr(server, "_check_demo_accounts", _no_matches)

    result = asyncio.run(server.health())
    assert result == {"status": "ok"}


def test_health_degraded_when_demo_account_still_on_default_password(monkeypatch):
    monkeypatch.setattr(server, "db", _FakeDb())

    async def _matches(_db):
        return ["owner@forge.app"]

    monkeypatch.setattr(server, "_check_demo_accounts", _matches)

    result = asyncio.run(server.health())
    assert result["status"] == "degraded"
    assert "owner@forge.app" in result["reasons"][0]


def test_health_demo_check_is_ttl_cached(monkeypatch):
    monkeypatch.setattr(server, "db", _FakeDb())
    calls = {"count": 0}

    async def _counting_check(_db):
        calls["count"] += 1
        return []

    monkeypatch.setattr(server, "_check_demo_accounts", _counting_check)

    asyncio.run(server.health())
    asyncio.run(server.health())
    assert calls["count"] == 1  # second call served from the TTL cache, no re-check
