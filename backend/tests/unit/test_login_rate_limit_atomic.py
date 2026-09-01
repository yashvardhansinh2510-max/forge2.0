"""Regression tests for atomic, bounded login rate limiting."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from services import rate_limit


@pytest.fixture(autouse=True)
def reset_rate_limiter(monkeypatch):
    rate_limit._attempts.clear()
    monkeypatch.setattr(rate_limit, "_redis", None)
    monkeypatch.setattr(rate_limit, "_redis_checked", True)
    yield
    rate_limit._attempts.clear()


class _AtomicRedis:
    """Small Redis EVAL double: a script call is one atomic transaction."""
    def __init__(self):
        self.values: dict[str, int] = {}

    async def eval(self, _script, key_count, *args):
        keys = args[:key_count]
        limits = [int(value) for value in args[key_count:key_count * 2]]
        if any(self.values.get(key, 0) >= limit for key, limit in zip(keys, limits)):
            return 0
        for key in keys:
            self.values[key] = self.values.get(key, 0) + 1
        return 1


@pytest.mark.asyncio
async def test_redis_failure_record_is_atomic_at_the_limit(monkeypatch):
    redis = _AtomicRedis()
    monkeypatch.setattr(rate_limit, "_redis_client", lambda: redis)
    ip, identifier = "203.0.113.8", "person@example.test"

    await asyncio.gather(*[
        rate_limit.record_login_failure(ip, identifier)
        for _ in range(rate_limit._PER_KEY_LIMIT)
    ])

    with pytest.raises(HTTPException) as exc:
        await rate_limit.record_login_failure(ip, identifier)

    assert exc.value.status_code == 429
    key, _, _ = rate_limit._keys(ip, identifier)
    assert redis.values[key] == rate_limit._PER_KEY_LIMIT


@pytest.mark.asyncio
async def test_memory_failure_record_is_atomic_at_the_limit(monkeypatch):
    monkeypatch.setattr(rate_limit, "_redis_client", lambda: None)
    ip, identifier = "203.0.113.9", "local@example.test"

    outcomes = await asyncio.gather(*[
        rate_limit.record_login_failure(ip, identifier)
        for _ in range(rate_limit._PER_KEY_LIMIT + 1)
    ], return_exceptions=True)

    assert sum(isinstance(result, HTTPException) for result in outcomes) == 1
    key, _, _ = rate_limit._keys(ip, identifier)
    assert len(rate_limit._attempts[key]) == rate_limit._PER_KEY_LIMIT


def test_memory_fallback_never_exceeds_its_key_bound(monkeypatch):
    monkeypatch.setattr(rate_limit, "_MAX_TRACKED_KEYS", 2)

    rate_limit._record_memory(["one"])
    rate_limit._record_memory(["two"])
    rate_limit._record_memory(["three"])

    assert len(rate_limit._attempts) == 2
    assert "three" in rate_limit._attempts
