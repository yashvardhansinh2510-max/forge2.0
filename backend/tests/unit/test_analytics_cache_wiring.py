"""Acting on an Attention row must refresh the numbers. Every analytics-visible
write bumps its collection version, which changes every dependent cache key."""
from __future__ import annotations

import asyncio

from services import domain_outbox
from services.analytics import cache


def test_a_quotation_write_invalidates_every_quotation_backed_metric():
    async def go():
        cache.reset_memory_state()
        before = await cache.cache_key("revenue", ["quotations"], "sig", None)
        await cache.bump("quotations")
        assert await cache.cache_key("revenue", ["quotations"], "sig", None) != before
    asyncio.run(go())


def test_every_outbox_event_declares_the_collections_it_invalidates():
    for event_type in (domain_outbox.EVENT_QUOTATION_GENERATED,
                       domain_outbox.EVENT_ORDER_PLACED,
                       domain_outbox.EVENT_PURCHASE_TRANSFERRED):
        assert domain_outbox._EVENT_COLLECTIONS.get(event_type), f"{event_type} bumps nothing"


def test_placing_an_order_invalidates_revenue_and_outstanding():
    async def go():
        cache.reset_memory_state()
        revenue_before = await cache.cache_key("revenue", ["quotations"], "sig", None)
        outstanding_before = await cache.cache_key("outstanding", ["quotations", "payments"], "sig", None)
        await domain_outbox._bump_analytics_versions(domain_outbox.EVENT_ORDER_PLACED)
        assert await cache.cache_key("revenue", ["quotations"], "sig", None) != revenue_before
        assert await cache.cache_key("outstanding", ["quotations", "payments"], "sig", None) != outstanding_before
    asyncio.run(go())


def test_an_unrelated_metric_is_not_invalidated():
    async def go():
        cache.reset_memory_state()
        before = await cache.cache_key("walkins", ["walkins"], "sig", None)
        await domain_outbox._bump_analytics_versions(domain_outbox.EVENT_QUOTATION_GENERATED)
        assert await cache.cache_key("walkins", ["walkins"], "sig", None) == before
    asyncio.run(go())


def test_a_failing_bump_never_fails_the_committed_command(monkeypatch):
    """The business transaction is already committed. A cache problem must
    degrade to TTL expiry, not turn a placed order into an error."""
    async def boom(_collection):
        raise RuntimeError("redis down")

    monkeypatch.setattr(cache, "bump", boom)
    asyncio.run(domain_outbox._bump_analytics_versions(domain_outbox.EVENT_ORDER_PLACED))


def test_the_bump_happens_after_the_transaction_not_inside_it():
    """The 22 Jul fix moved post-commit work strictly after the commit; a bump
    inside the transaction could publish a version for a write that rolls back."""
    import inspect
    source = inspect.getsource(domain_outbox._process_claimed_event) if hasattr(
        domain_outbox, "_process_claimed_event") else inspect.getsource(domain_outbox)
    bump_at = source.index("_bump_analytics_versions(current[")
    commit_block_at = source.index("async with session.start_transaction():")
    assert bump_at > commit_block_at
    # and outside the `async with` body: the bump line is not indented under it
    line = next(line for line in source.splitlines() if "_bump_analytics_versions(current[" in line)
    assert len(line) - len(line.lstrip()) == 4, "bump must sit at function level, not inside the transaction"
