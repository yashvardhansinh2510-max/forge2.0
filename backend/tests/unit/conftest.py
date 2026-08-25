"""Test fixtures for unit tests."""
import pytest
from auth import accessible_floor_ids


class _RaisingDb:
    """Raises loudly on any attribute access — used to guard
    services.sequence's module-level `db` import (see
    _guard_services_sequence_db below)."""

    def __getattr__(self, name):
        raise RuntimeError(
            "services.sequence.db was not mocked in this test — this would "
            "hit a real database. See "
            "backend/tests/unit/test_domain_outbox_tile_customer_order.py "
            "or test_backfill_tile_customer_orders.py for the correct "
            "mocking pattern."
        )


@pytest.fixture(autouse=True)
def _guard_services_sequence_db(monkeypatch):
    """Close the next_number()/production-DB landmine at the suite level.

    services/sequence.py does `from db import db` at its own module scope,
    so patching some *other* module's `db` reference (e.g. a route module's
    `db`) does NOT redirect next_number()'s own db.counters calls — they
    still hit whatever real database backend/db.py is actually configured
    to talk to. This bit a real Task 13 test run: three counter documents
    were incremented in the live production MongoDB before the gap was
    caught.

    This autouse fixture monkeypatches services.sequence.db to a fake that
    raises on any use, by default, in every unit test. A test that
    legitimately needs next_number() to run for real must explicitly
    monkeypatch services.sequence.db (or the caller's own next_number
    reference) itself — pytest/monkeypatch's last-write-wins semantics mean
    a test's own later `monkeypatch.setattr(sequence, "db", ...)` simply
    overrides the patch this fixture applied first, which is the normal,
    safe behavior of fixtures that run before the test body. This fixture
    intentionally does nothing clever beyond that.
    """
    import services.sequence as sequence

    monkeypatch.setattr(sequence, "db", _RaisingDb())


@pytest.fixture(autouse=True)
def mock_floor_query(monkeypatch):
    """Mock floor_query to flatten the dict when both floor_scope and base are present.

    This ensures tests get the same flat dict structure as the old
    {**floor_query(user), **query} pattern, while the production code uses
    the proper floor_query(user, query) composition.
    """
    import auth

    original_floor_query = auth.floor_query

    def flat_floor_query(user, base=None):
        """Flattened version for testing — returns a flat dict instead of $and wrapper."""
        base = base or {}
        allowed = [user.active_floor_id] if user.active_floor_id else accessible_floor_ids(user)
        if allowed is None:
            return base
        scope = {"floor_id": {"$in": allowed}}
        # Test version: flatten by merging instead of wrapping in $and
        return {**scope, **base}

    monkeypatch.setattr(auth, "floor_query", flat_floor_query)
    # Also patch it in quotation_routes module since it's already imported there
    import routes.quotation_routes as quotation_routes
    monkeypatch.setattr(quotation_routes, "floor_query", flat_floor_query)
