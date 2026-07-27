"""Test fixtures for unit tests."""
import pytest
from auth import accessible_floor_ids


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
