"""Invalidation is automatic: a write bumps a collection version, the key
changes, and every dependent entry becomes unreachable. Nothing is ever
cleared by hand.

This suite has no pytest-asyncio; async code is driven with asyncio.run,
matching test_tile_orders_delivered.py.
"""
from __future__ import annotations

import asyncio

import pytest

from services.analytics import cache


@pytest.fixture(autouse=True)
def _clean():
    cache.reset_memory_state()
    yield
    cache.reset_memory_state()


def test_key_is_stable_for_identical_inputs():
    async def go():
        a = await cache.cache_key("revenue", ["quotations"], "sig", ["ground-floor"])
        b = await cache.cache_key("revenue", ["quotations"], "sig", ["ground-floor"])
        assert a == b
    asyncio.run(go())


def test_key_changes_when_a_dependency_is_bumped():
    async def go():
        before = await cache.cache_key("revenue", ["quotations"], "sig", None)
        await cache.bump("quotations")
        assert await cache.cache_key("revenue", ["quotations"], "sig", None) != before
    asyncio.run(go())


def test_bumping_an_unrelated_collection_leaves_the_key_alone():
    async def go():
        before = await cache.cache_key("revenue", ["quotations"], "sig", None)
        await cache.bump("payments")
        assert await cache.cache_key("revenue", ["quotations"], "sig", None) == before
    asyncio.run(go())


def test_floor_scope_is_part_of_the_key():
    # Omitting this would serve one user's floor-scoped rows to another.
    async def go():
        ground = await cache.cache_key("revenue", ["quotations"], "sig", ["ground-floor"])
        first = await cache.cache_key("revenue", ["quotations"], "sig", ["first-floor"])
        assert ground != first
    asyncio.run(go())


def test_unrestricted_access_keys_differently_from_a_single_floor():
    async def go():
        unrestricted = await cache.cache_key("revenue", ["quotations"], "sig", None)
        scoped = await cache.cache_key("revenue", ["quotations"], "sig", ["ground-floor"])
        assert unrestricted != scoped
    asyncio.run(go())


def test_floor_order_does_not_change_the_key():
    async def go():
        a = await cache.cache_key("revenue", ["quotations"], "sig", ["ground-floor", "first-floor"])
        b = await cache.cache_key("revenue", ["quotations"], "sig", ["first-floor", "ground-floor"])
        assert a == b
    asyncio.run(go())


def test_a_restricted_caller_with_no_floors_is_not_treated_as_unrestricted():
    """[] means "sees nothing" and None means "sees everything" — sharing a
    cache entry between them would hand a locked-out account the full report."""
    async def go():
        empty = await cache.cache_key("revenue", ["quotations"], "sig", [])
        unrestricted = await cache.cache_key("revenue", ["quotations"], "sig", None)
        assert empty != unrestricted
    asyncio.run(go())


def test_loader_runs_once_then_the_value_is_served_from_cache():
    calls = []

    async def loader():
        calls.append(1)
        return {"revenue": 100}

    async def go():
        first = await cache.cached("revenue", ["quotations"], "sig", None, loader)
        second = await cache.cached("revenue", ["quotations"], "sig", None, loader)
        assert first == second == {"revenue": 100}
        assert len(calls) == 1
    asyncio.run(go())


def test_a_write_makes_the_loader_run_again():
    calls = []

    async def loader():
        calls.append(1)
        return {"revenue": len(calls)}

    async def go():
        await cache.cached("revenue", ["quotations"], "sig", None, loader)
        await cache.bump("quotations")
        result = await cache.cached("revenue", ["quotations"], "sig", None, loader)
        assert result == {"revenue": 2}
        assert len(calls) == 2
    asyncio.run(go())


def test_an_expired_entry_is_recomputed():
    calls = []

    async def loader():
        calls.append(1)
        return {"n": len(calls)}

    async def go():
        await cache.cached("revenue", ["quotations"], "sig", None, loader, ttl=0)
        again = await cache.cached("revenue", ["quotations"], "sig", None, loader, ttl=0)
        assert again == {"n": 2}
    asyncio.run(go())


def test_a_different_filter_signature_is_a_different_entry():
    calls = []

    async def loader():
        calls.append(1)
        return {"n": len(calls)}

    async def go():
        await cache.cached("revenue", ["quotations"], "july", None, loader)
        await cache.cached("revenue", ["quotations"], "august", None, loader)
        assert len(calls) == 2
    asyncio.run(go())
