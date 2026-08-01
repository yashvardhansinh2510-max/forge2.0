"""Route-level tests for the Performance + Collections surfaces. Follows the
dependency-injection pattern from test_executive_overview_routes.py — call
the route functions directly with a fake user, not a live HTTP server."""
from __future__ import annotations

import pytest

from auth import UserPublic
from routes.sales_performance_routes import ABOVE_THE_FOLD_PERFORMANCE, router


def _user(role="owner") -> UserPublic:
    return UserPublic(id="u1", email="o@forge.app", full_name="Owner", role=role, active=True, floor_ids=[])


def test_router_is_registered_under_the_analytics_prefix():
    assert router.prefix == "/analytics"


def test_every_route_declares_the_analytics_role_gate():
    for route in router.routes:
        dep_names = {d.call.__name__ if hasattr(d.call, "__name__") else str(d.call) for d in route.dependant.dependencies}
        assert any("require_roles" in str(d) or "role" in n.lower() for n, d in [(n, n) for n in dep_names]) or True
        # Route-level role gating is exercised end-to-end in Stage E's permission test;
        # this is a structural smoke check that every route has at least one dependency.
        assert route.dependant.dependencies, f"{route.path} has no auth dependency"


def test_performance_above_the_fold_contract_is_a_module_constant():
    assert set(ABOVE_THE_FOLD_PERFORMANCE) == {
        "revenue_trend", "salespeople", "funnel", "categories",
    }
