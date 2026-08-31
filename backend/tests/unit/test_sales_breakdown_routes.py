"""Structural tests for the Sales Data launch breakdown routes.

Follows the dependency-injection pattern from test_sales_performance_routes.py
— assert the contract the module exists to hold, not a live HTTP round-trip.
"""
from __future__ import annotations

import asyncio
import io

import openpyxl

from models import UserPublic
from routes import sales_breakdown_routes as breakdowns
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


def test_sales_records_export_is_available_from_the_filtered_recent_orders_endpoint():
    """The dashboard's Export Excel control uses the same secured endpoint
    and filter contract as the on-screen recent-orders table.  The route's
    `format` query parameter is intentionally optional so normal reads keep
    their JSON response while `format=xlsx` produces the workbook."""
    route = next(route for route in router.routes if route.path == "/analytics/recent-orders")
    assert "format" in {param.name for param in route.dependant.query_params}


def test_sales_records_xlsx_export_contains_every_filtered_row_not_the_screen_limit(monkeypatch):
    async def rows(*_args):
        return [
            {"number": "SO-1", "customer_name": "Amit", "grand_total": 1000},
            {"number": "SO-2", "customer_name": "Priya", "grand_total": 2000},
        ]

    async def collect(response):
        return b"".join([chunk async for chunk in response.body_iterator])

    monkeypatch.setattr(breakdowns, "_recent_order_rows", rows)
    response = asyncio.run(breakdowns.recent_orders(
        floor_id="ground-floor", preset="all", date_from=None, date_to=None,
        limit=1, format="xlsx",
        user=UserPublic(id="owner", email="owner@example.com", full_name="Owner", role="owner"),
    ))
    workbook = openpyxl.load_workbook(io.BytesIO(asyncio.run(collect(response))))
    sheet = workbook.active

    assert response.headers["content-disposition"] == 'attachment; filename="sales-data.xlsx"'
    assert [sheet.cell(row=row, column=1).value for row in (2, 3)] == ["SO-1", "SO-2"]


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
