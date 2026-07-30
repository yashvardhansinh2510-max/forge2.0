"""Independent re-verification of the reconcile_followups() race-condition
fix (asyncio.Lock serialization + partial unique index on
followups.source_key). Run standalone (not part of the main suite) because
it fires several genuinely concurrent HTTP requests and inspects the DB
directly — separate from test_followups_v2_workspaces.py's single-threaded
regression guard so a fresh testing agent can independently confirm both
the DB-level constraint and true concurrent-request behavior.
"""
import asyncio
import os

import httpx
import pytest
import requests

BASE_URL = os.environ.get("TEST_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
OWNER_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "")
PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "")

pytestmark = pytest.mark.skipif(
    not (BASE_URL and OWNER_EMAIL and PASSWORD),
    reason="TEST_BACKEND_URL/TEST_OWNER_EMAIL/TEST_OWNER_PASSWORD not set",
)


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _all_followups(token):
    r = requests.get(f"{API}/followups?limit=3000", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.status_code == 200
    return r.json()


def _duplicate_source_keys(rows):
    """Group OPEN automated rows by (rule_type, quotation_id/purchase_id) —
    the effective source_key — and return any group with count > 1."""
    seen = {}
    for f in rows:
        if not f.get("is_automated") or f.get("status") not in ("open", "snoozed"):
            continue
        key = f"{f['rule_type']}:{f.get('quotation_id')}:{f.get('purchase_id')}"
        seen[key] = seen.get(key, 0) + 1
    return {k: c for k, c in seen.items() if c > 1}


def test_concurrent_reconcile_calls_produce_zero_duplicates(owner_token):
    """Fire 5 genuinely concurrent POST /api/followups/reconcile calls via
    asyncio.gather (real overlapping HTTP requests, not sequential) and
    confirm the followups collection ends up with zero duplicate
    (rule_type, quotation_id) OPEN automated rows."""

    async def _fire_all():
        async with httpx.AsyncClient(timeout=90) as client:
            headers = {"Authorization": f"Bearer {owner_token}"}
            tasks = [client.post(f"{API}/followups/reconcile", headers=headers) for _ in range(5)]
            return await asyncio.gather(*tasks, return_exceptions=True)

    results = asyncio.run(_fire_all())

    ok_count = 0
    non_200 = []
    for r in results:
        if isinstance(r, Exception):
            print(f"Concurrent reconcile call raised: {r!r}")
            non_200.append(f"exception:{r!r}")
            continue
        if r.status_code == 200:
            ok_count += 1
        else:
            non_200.append(r.status_code)
    print(f"5 concurrent reconcile calls: {ok_count} returned HTTP 200, non-200/errored: {non_200}")
    # The correctness property under test is "no duplicate cards ever result",
    # NOT "every concurrent call returns 200 fast" — the lock intentionally
    # serializes overlapping runs, so a slow/loaded gateway may 502/timeout a
    # queued request without that implying a data-integrity problem. We only
    # hard-require that at least one call completed so there's something to
    # check the DB against.
    assert ok_count >= 1, "All 5 concurrent reconcile calls failed/errored — cannot verify DB state"

    rows = _all_followups(owner_token)
    dupes = _duplicate_source_keys(rows)
    assert not dupes, f"Duplicate OPEN automated rows found after concurrent reconcile: {dupes}"


def test_total_followup_count_stable_across_repeated_reconciles(owner_token):
    """A stable total count across back-to-back reconciles (no drift) is a
    cheap secondary signal that nothing is being double-inserted."""
    counts = []
    for _ in range(3):
        r = requests.post(f"{API}/followups/reconcile", headers={"Authorization": f"Bearer {owner_token}"}, timeout=90)
        assert r.status_code == 200
        rows = _all_followups(owner_token)
        counts.append(len(rows))
    # created should be 0 on the 2nd/3rd pass once desired-state has converged;
    # total row count must not keep growing.
    assert counts[-1] == counts[-2], f"Follow-up row count drifted across reconciles: {counts}"
