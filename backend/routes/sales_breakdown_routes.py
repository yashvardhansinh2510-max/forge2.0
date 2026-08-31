"""The Sales Data launch breakdowns — Revenue by Brand, Revenue by Customer,
Best Selling Products, and Recent Orders (Milestone 4).

Mirrors `sales_performance_routes.py`'s shape exactly: `_filter_from_query` /
`_floor_error_to_http` are imported from `executive_overview_routes.py` rather
than redefined, every non-export read goes through `cache.cached`, and exports
check `format` before any caching and bypass it entirely.

These four are the surfaces Phase 0 built the foundation for but never
exposed a route to. They are deliberately shaped as four independent,
filterable, exportable resource endpoints rather than one page-shaped blob:
the Products, Brands and Customers workspaces on the roadmap are exactly
these lists with more columns, so a later milestone adds capability to an
existing endpoint instead of replacing it.

Two invariants worth stating, because they are the reason this module exists
rather than the page reusing `/executive-analytics/dashboard`:

  * **Every breakdown reconciles to the Total Revenue KPI.** Line revenue
    sums `items.net_amount` through the canonical `line_revenue_pipeline`.
    `/executive-analytics/dashboard` computes `qty x unit_price`, which
    ignores the discount cascade — putting both on one page would show the
    owner two different totals for the same book.
  * **No revenue is dropped to make a table tidy.** A product that no longer
    resolves to a catalog doc still sold something; it folds into an explicit
    "Unlinked products" brand bucket.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, Query

from auth import UserPublic, accessible_floor_ids, require_roles
from db import db
from routes.executive_overview_routes import _filter_from_query, _floor_error_to_http
from services import export
from services.analytics import cache
from services.analytics.breakdowns import brand_rows, customer_rows, order_rows, product_rows
from services.analytics.filters import AnalyticsFilter, FloorAccessError
from services.analytics.gather_breakdowns import (
    gather_confirmed_orders,
    gather_line_labels,
    gather_order_collections,
    gather_product_brands,
    gather_product_line_revenue,
)
from services.analytics.metrics import filter_signature
from services.analytics.periods import Period, resolve

router = APIRouter(prefix="/analytics", tags=["analytics"])

_ANALYTICS_ROLES = ("owner", "admin", "manager")
_CACHE_TTL = 60

ExportFormat = Literal["csv", "xlsx"]

# Source collections each cached metric reads — same discipline as
# sales_performance_routes.CACHED_SURFACES, so a write to any of them
# invalidates the entry automatically.
CACHED_SURFACES: dict[str, list[str]] = {
    "revenue_by_brand": ["quotations", "products", "brands"],
    "revenue_by_customer": ["quotations"],
    "best_selling_products": ["quotations", "products", "brands"],
    "recent_orders": ["quotations", "payments"],
}

_BRAND_COLUMNS: list[tuple[str, str]] = [
    ("name", "Brand"), ("revenue", "Revenue"), ("quantity", "Qty"), ("orders", "Order Lines"),
]
_CUSTOMER_COLUMNS: list[tuple[str, str]] = [
    ("name", "Customer"), ("revenue", "Revenue"), ("orders", "Orders"),
    ("aov", "AOV"), ("last_order_at", "Last Order"),
]
_PRODUCT_COLUMNS: list[tuple[str, str]] = [
    ("name", "Product"), ("sku", "SKU"), ("brand_name", "Brand"),
    ("revenue", "Revenue"), ("quantity", "Qty"), ("orders", "Orders"), ("customers", "Customers"),
]
_ORDER_COLUMNS: list[tuple[str, str]] = [
    ("number", "Order"), ("ordered_at", "Confirmed At"), ("customer_name", "Customer"),
    ("floor_id", "Floor"), ("salesperson_name", "Salesperson"),
    ("grand_total", "Order Value"), ("collected", "Collected"), ("outstanding", "Outstanding"),
]


def _period_of(f: AnalyticsFilter) -> Period:
    return resolve(f.preset, f.date_from, f.date_to)


# ---------------------------------------------------------------------------
# Revenue by Brand
# ---------------------------------------------------------------------------

async def _brand_revenue_rows(f: AnalyticsFilter, floors, period: Period) -> list[dict]:
    window = (period.start, period.end)
    line_revenue = await gather_product_line_revenue(db, f, floors, window)
    product_ids = [row["key"] for row in line_revenue if row.get("key")]
    product_brand, brand_names = await gather_product_brands(db, product_ids)
    return [asdict(row) for row in brand_rows(line_revenue, product_brand, brand_names)]


@router.get("/revenue-by-brand")
async def revenue_by_brand(
    floor_id: str | None = Query(None),
    preset: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    format: ExportFormat | None = Query(None),
    user: UserPublic = Depends(require_roles(*_ANALYTICS_ROLES)),
):
    f = _filter_from_query(floor_id, preset, date_from, date_to)
    floors = accessible_floor_ids(user)
    period = _period_of(f)
    try:
        if format:
            rows = await _brand_revenue_rows(f, floors, period)
            return export.export_response(rows, _BRAND_COLUMNS, "revenue-by-brand", format)
        rows = await cache.cached(
            "revenue_by_brand", CACHED_SURFACES["revenue_by_brand"], filter_signature(f), floors,
            lambda: _brand_revenue_rows(f, floors, period), ttl=_CACHE_TTL,
        )
    except FloorAccessError as exc:
        raise _floor_error_to_http(exc) from exc
    return {"rows": rows}


# ---------------------------------------------------------------------------
# Revenue by Customer
# ---------------------------------------------------------------------------

async def _customer_revenue_rows(f: AnalyticsFilter, floors, period: Period) -> list[dict]:
    orders = await gather_confirmed_orders(db, f, floors, (period.start, period.end))
    return [asdict(row) for row in customer_rows(orders)]


@router.get("/revenue-by-customer")
async def revenue_by_customer(
    floor_id: str | None = Query(None),
    preset: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    format: ExportFormat | None = Query(None),
    user: UserPublic = Depends(require_roles(*_ANALYTICS_ROLES)),
):
    f = _filter_from_query(floor_id, preset, date_from, date_to)
    floors = accessible_floor_ids(user)
    period = _period_of(f)
    try:
        if format:
            rows = await _customer_revenue_rows(f, floors, period)
            return export.export_response(rows, _CUSTOMER_COLUMNS, "revenue-by-customer", format)
        rows = await cache.cached(
            "revenue_by_customer", CACHED_SURFACES["revenue_by_customer"], filter_signature(f), floors,
            lambda: _customer_revenue_rows(f, floors, period), ttl=_CACHE_TTL,
        )
    except FloorAccessError as exc:
        raise _floor_error_to_http(exc) from exc
    return {"rows": rows}


# ---------------------------------------------------------------------------
# Best Selling Products
# ---------------------------------------------------------------------------

async def _product_revenue_rows(f: AnalyticsFilter, floors, period: Period) -> list[dict]:
    window = (period.start, period.end)
    line_revenue = await gather_product_line_revenue(db, f, floors, window)
    names, skus = await gather_line_labels(db, f, floors, window)
    product_ids = [row["key"] for row in line_revenue if row.get("key")]
    product_brand, brand_names = await gather_product_brands(db, product_ids)
    return [asdict(row) for row in product_rows(line_revenue, names, skus, product_brand, brand_names)]


@router.get("/best-selling-products")
async def best_selling_products(
    floor_id: str | None = Query(None),
    preset: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(10, ge=1, le=200),
    format: ExportFormat | None = Query(None),
    user: UserPublic = Depends(require_roles(*_ANALYTICS_ROLES)),
):
    f = _filter_from_query(floor_id, preset, date_from, date_to)
    floors = accessible_floor_ids(user)
    period = _period_of(f)
    try:
        if format:
            # An export is the whole ranked list, never the screen's top N —
            # the caller asked for the data, not the card.
            rows = await _product_revenue_rows(f, floors, period)
            return export.export_response(rows, _PRODUCT_COLUMNS, "best-selling-products", format)
        # `limit` is NOT part of filter_signature (it is a plain function
        # argument, not a field on AnalyticsFilter), so it must be appended
        # by hand or a limit=10 and a limit=50 request would collide on one
        # entry — the same treatment referral_analytics_routes gives `type`.
        rows = await cache.cached(
            "best_selling_products", CACHED_SURFACES["best_selling_products"],
            f"{filter_signature(f)}:{limit}", floors,
            lambda: _product_revenue_rows(f, floors, period), ttl=_CACHE_TTL,
        )
    except FloorAccessError as exc:
        raise _floor_error_to_http(exc) from exc
    return {"rows": rows[:limit], "total": len(rows)}


# ---------------------------------------------------------------------------
# Recent Orders
# ---------------------------------------------------------------------------

async def _recent_order_rows(f: AnalyticsFilter, floors, period: Period) -> list[dict]:
    orders = await gather_confirmed_orders(db, f, floors, (period.start, period.end))
    collected = await gather_order_collections(db, orders)
    return [asdict(row) for row in order_rows(orders, collected)]


@router.get("/recent-orders")
async def recent_orders(
    floor_id: str | None = Query(None),
    preset: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(10, ge=1, le=200),
    format: ExportFormat | None = Query(None),
    user: UserPublic = Depends(require_roles(*_ANALYTICS_ROLES)),
):
    f = _filter_from_query(floor_id, preset, date_from, date_to)
    floors = accessible_floor_ids(user)
    period = _period_of(f)
    try:
        if format:
            # The Sales Data screen uses this as its single, complete sales
            # export.  `_recent_order_rows` intentionally returns the whole
            # filtered result set (the `limit` below is presentation-only),
            # so an exported workbook never silently contains just the ten
            # rows visible in the dashboard.
            rows = await _recent_order_rows(f, floors, period)
            return export.export_response(rows, _ORDER_COLUMNS, "sales-data", format)
        rows = await cache.cached(
            "recent_orders", CACHED_SURFACES["recent_orders"],
            f"{filter_signature(f)}:{limit}", floors,
            lambda: _recent_order_rows(f, floors, period), ttl=_CACHE_TTL,
        )
    except FloorAccessError as exc:
        raise _floor_error_to_http(exc) from exc
    return {"rows": rows[:limit], "total": len(rows)}
