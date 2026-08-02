"""Structural tests for the Sales Data launch breakdown routes.

Follows the dependency-injection pattern from test_sales_performance_routes.py
— assert the contract the module exists to hold, not a live HTTP round-trip.
"""
from __future__ import annotations

from routes.sales_breakdown_routes import CACHED_SURFACES, router


def test_router_is_registered_under_the_analytics_prefix():
    assert router.prefix == "/analytics"


def test_every_route_carries_an_auth_dependency():
    for route in router.routes:
        assert route.dependant.dependencies, f"{route.path} has no auth dependency"


def test_all_four_launch_breakdowns_are_exposed():
    paths = {route.path for route in router.routes}
    assert paths == {
        "/analytics/revenue-by-brand",
        "/analytics/revenue-by-customer",
        "/analytics/best-selling-products",
        "/analytics/recent-orders",
    }


def test_every_cached_metric_declares_the_collections_it_reads():
    """cache.cached keys on these; a surface that reads a collection it did
    not declare would serve stale rows after that collection is written."""
    for metric, collections in CACHED_SURFACES.items():
        assert collections, f"{metric} declares no source collections"
        assert "quotations" in collections, f"{metric} reads revenue but does not declare quotations"


def test_recent_orders_declares_payments_because_outstanding_depends_on_them():
    assert "payments" in CACHED_SURFACES["recent_orders"]


def test_brand_and_product_surfaces_declare_the_catalog_they_resolve_names_from():
    for metric in ("revenue_by_brand", "best_selling_products"):
        assert {"products", "brands"} <= set(CACHED_SURFACES[metric])


def test_revenue_by_customer_reads_only_quotations():
    """It folds in Python over the confirmed orders — no catalog, no payments
    — so declaring more would invalidate its cache for no reason."""
    assert CACHED_SURFACES["revenue_by_customer"] == ["quotations"]


def test_every_registered_metric_id_matches_a_route():
    """Guards the drift where a cache entry is declared for a surface that
    was renamed or removed."""
    assert set(CACHED_SURFACES) == {
        "revenue_by_brand", "revenue_by_customer", "best_selling_products", "recent_orders",
    }
