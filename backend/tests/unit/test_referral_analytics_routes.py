"""Route-level tests for Referral Analytics. Mirrors test_sales_performance_routes.py."""
from __future__ import annotations

from routes.referral_analytics_routes import router


def test_router_is_registered_under_the_analytics_prefix():
    assert router.prefix == "/analytics"


def test_every_route_has_an_auth_dependency():
    for route in router.routes:
        assert route.dependant.dependencies, f"{route.path} has no auth dependency"


def test_the_referrer_list_route_and_the_detail_route_both_exist():
    paths = {r.path for r in router.routes}
    assert "/analytics/referrers" in paths
    assert "/analytics/referrers/{referrer_id}" in paths
