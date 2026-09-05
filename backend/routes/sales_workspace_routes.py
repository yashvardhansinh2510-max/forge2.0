"""Owner-only data resources for the Sales Data workspaces.

These routes deliberately sit beside, rather than inside, the launch Sales
Data dashboard.  The dashboard's response shapes are a stable contract; the
new workspaces consume this small, paginated read model instead.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import UserPublic, accessible_floor_ids, require_roles
from db import db
from routes.executive_overview_routes import _floor_error_to_http
from services.analytics.filters import AnalyticsFilter, FloorAccessError, build_match
from services.analytics.gather_breakdowns import gather_order_collections, gather_product_brands, gather_product_line_revenue
from services.analytics.breakdowns import brand_rows, customer_rows, order_rows, product_rows
from services.analytics.gather_breakdowns import gather_line_labels
from services.analytics.periods import resolve

router = APIRouter(prefix="/analytics/workspaces", tags=["analytics"])

Workspace = Literal["revenue", "collections", "forecasting", "customers", "architects", "interior-designers", "relationships", "products", "brands", "suppliers", "operations"]


def _filter(
    floor_id: str | None, preset: str | None, date_from: str | None, date_to: str | None,
    brand_id: str | None, customer_id: str | None, salesperson_id: str | None, referrer_id: str | None,
) -> AnalyticsFilter:
    return AnalyticsFilter(
        floor_id=floor_id or "all", preset=preset or "this_month", date_from=date_from, date_to=date_to,
        brand_id=brand_id, customer_id=customer_id, salesperson_id=salesperson_id, referrer_id=referrer_id,
    )


async def _brand_product_ids(brand_id: str | None) -> list[str] | None:
    if not brand_id:
        return None
    return [p["id"] for p in await db.products.find({"brand_id": brand_id}, {"_id": 0, "id": 1}).to_list(10000)]


async def _orders(f: AnalyticsFilter, floors: list[str] | None) -> tuple[list[dict], dict[str, float]]:
    period = resolve(f.preset, f.date_from, f.date_to)
    product_ids = await _brand_product_ids(f.brand_id)
    match = build_match(f, floors, (period.start, period.end), product_ids)
    docs = await db.quotations.find(match, {"_id": 0}).to_list(10000)
    # Brand filters apply to order inclusion. Line-level aggregates below still
    # use the canonical net amount pipeline, so no dashboard total is changed.
    collected = await gather_order_collections(db, docs)
    return docs, collected


def _money(value: float | int | None) -> float:
    return round(float(value or 0), 2)


async def _forecast(f: AnalyticsFilter, floors, now: datetime | None = None) -> dict:
    """A baseline requires observed orders in three complete calendar months.

    Empty months alone cannot establish history: a new installation with no
    orders must not claim a measured zero forecast. The baseline always uses
    the three prior complete months and preserves the report's entity scope.
    """
    now = now or datetime.now(timezone.utc)
    end_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly: list[float] = []
    months_with_orders = 0
    product_ids = await _brand_product_ids(f.brand_id)
    for i in range(3, 0, -1):
        month_index = end_month.month - 1 - i
        start = end_month.replace(year=end_month.year + month_index // 12, month=month_index % 12 + 1)
        end = start.replace(month=start.month % 12 + 1, year=start.year + (start.month == 12))
        match = build_match(replace(f, status="ordered"), floors, (start.isoformat(), end.isoformat()), product_ids)
        rows = await db.quotations.find(match, {"_id": 0, "grand_total": 1}).to_list(None)
        months_with_orders += bool(rows)
        monthly.append(sum(float(row.get("grand_total") or 0) for row in rows))
    available = months_with_orders == 3
    return {
        "months_used": months_with_orders,
        "history_state": "ok" if available else "insufficient_history",
        "monthly_history": [_money(value) for value in monthly],
        "forecast": _money(sum(monthly) / 3) if available else None,
        "method": "Mean revenue over the previous three complete calendar months; requires orders in each month",
    }


@router.get("/sales-records")
async def sales_records(
    floor_id: str | None = None, preset: str | None = None, date_from: str | None = None, date_to: str | None = None,
    brand_id: str | None = None, customer_id: str | None = None, salesperson_id: str | None = None, referrer_id: str | None = None,
    offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
    user: UserPublic = Depends(require_roles("owner")),
):
    f = _filter(floor_id, preset, date_from, date_to, brand_id, customer_id, salesperson_id, referrer_id)
    try:
        docs, collected = await _orders(f, accessible_floor_ids(user))
    except FloorAccessError as exc:
        raise _floor_error_to_http(exc) from exc
    rows = order_rows(docs, collected)
    return {"rows": [r.__dict__ for r in rows[offset:offset + limit]], "total": len(rows), "offset": offset, "limit": limit}


@router.get("/facets")
async def facets(user: UserPublic = Depends(require_roles("owner"))):
    """Small option lists for filters; owner floor access is applied to brands."""
    floors = accessible_floor_ids(user)
    brand_query = {} if floors is None else {"floor_id": {"$in": floors}}
    brands = await db.brands.find(brand_query, {"_id": 0, "id": 1, "name": 1}).sort("name", 1).to_list(2000)
    customers = await db.customers.find({}, {"_id": 0, "id": 1, "name": 1}).sort("name", 1).to_list(2000)
    people = await db.users.find({"role": {"$in": ["owner", "admin", "manager", "sales"]}}, {"_id": 0, "id": 1, "full_name": 1}).sort("full_name", 1).to_list(500)
    referrers = await db.referrers.find(brand_query, {"_id": 0, "id": 1, "name": 1, "type": 1}).sort("name", 1).to_list(2000)
    return {"brands": brands, "customers": customers, "salespeople": people, "referrers": referrers}


@router.get("/{workspace}")
async def workspace(
    workspace: Workspace,
    floor_id: str | None = None, preset: str | None = None, date_from: str | None = None, date_to: str | None = None,
    brand_id: str | None = None, customer_id: str | None = None, salesperson_id: str | None = None, referrer_id: str | None = None,
    user: UserPublic = Depends(require_roles("owner")),
):
    f = _filter(floor_id, preset, date_from, date_to, brand_id, customer_id, salesperson_id, referrer_id)
    floors = accessible_floor_ids(user)
    try:
        docs, collected = await _orders(f, floors)
    except FloorAccessError as exc:
        raise _floor_error_to_http(exc) from exc
    total = sum(float(d.get("grand_total") or 0) for d in docs)
    outstanding = sum(max(0, float(d.get("grand_total") or 0) - float(collected.get(d.get("id"), 0))) for d in docs)
    period = resolve(f.preset, f.date_from, f.date_to)
    # The line pipeline remains the source of truth for product/brand numbers.
    line = await gather_product_line_revenue(db, f, floors, (period.start, period.end))
    product_ids = [r.get("key") for r in line if r.get("key")]
    product_brand, brand_names = await gather_product_brands(db, product_ids)
    names, skus = await gather_line_labels(db, f, floors, (period.start, period.end))
    brands = [r.__dict__ for r in brand_rows(line, product_brand, brand_names)]
    products = [r.__dict__ for r in product_rows(line, names, skus, product_brand, brand_names)]
    customers = [r.__dict__ for r in customer_rows(docs)]
    hansgrohe = next((r["revenue"] for r in brands if r["name"].strip().lower() == "hansgrohe"), 0.0)
    by_floor: dict[str, dict] = {}
    for d in docs:
        key = d.get("floor_id") or "unassigned"
        b = by_floor.setdefault(key, {"floor_id": key, "revenue": 0.0, "orders": 0})
        b["revenue"] += float(d.get("grand_total") or 0); b["orders"] += 1
    payload: dict = {
        "workspace": workspace, "period": period.label,
        "kpis": {"revenue": _money(total), "orders": len(docs), "outstanding": _money(outstanding), "hansgrohe_revenue": _money(hansgrohe)},
        "brands": brands[:100], "products": products[:100], "customers": customers[:100],
        "floors": sorted(({**row, "revenue": _money(row["revenue"])} for row in by_floor.values()), key=lambda row: -row["revenue"]),
    }
    if workspace in ("architects", "interior-designers", "relationships"):
        kind = "architect" if workspace == "architects" else "interior_designer" if workspace == "interior-designers" else None
        grouped: dict[tuple[str, str], dict] = {}
        for d in docs:
            if kind and d.get("referrer_type") != kind: continue
            rid, name = d.get("referrer_id"), d.get("referrer_name")
            if not rid or not name: continue
            row = grouped.setdefault((rid, name), {"id": rid, "name": name, "type": d.get("referrer_type"), "revenue": 0.0, "orders": 0, "customers": set(), "last_order_at": None})
            row["revenue"] += float(d.get("grand_total") or 0); row["orders"] += 1; row["customers"].add(d.get("customer_id"))
            row["last_order_at"] = max(row["last_order_at"] or "", d.get("ordered_at") or "") or None
        payload["relationships"] = sorted(({**r, "revenue": _money(r["revenue"]), "customers": len(r["customers"])} for r in grouped.values()), key=lambda r: -r["revenue"])
    if workspace == "forecasting":
        payload["forecast"] = await _forecast(f, floors)
    return payload
