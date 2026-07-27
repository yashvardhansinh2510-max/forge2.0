"""Sales Data dashboard (owner/admin only) — revenue by floor, by
architect/interior-designer referrer, and by brand. Reads only `won`
quotations, matching the revenue definition already used by
/dashboard/stats. Aggregation happens in Python over an in-memory list —
matches the existing dashboard_routes.py convention — rather than a Mongo
pipeline, since won-quotation volume stays small and this is far easier to
unit-test against the codebase's existing fake-db pattern. See
docs/superpowers/specs/2026-07-27-sales-data-dashboard-design.md."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import accessible_floor_ids, require_roles
from db import db
from models import UserPublic

router = APIRouter(prefix="/sales-data", tags=["sales-data"])

Granularity = Literal["day", "month", "quarter", "year"]


def _bucket_label(iso_ts: str, granularity: Granularity) -> str:
    dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    if granularity == "day":
        return dt.strftime("%Y-%m-%d")
    if granularity == "month":
        return dt.strftime("%Y-%m")
    if granularity == "year":
        return dt.strftime("%Y")
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{q}"


def _resolve_floor_ids(user: UserPublic, floor_id: Optional[str]) -> Optional[list[str]]:
    """Combines the caller's own floor access with the Floor filter the
    frontend sent. None means "no floor restriction" (query every floor
    the caller can see)."""
    allowed = accessible_floor_ids(user)
    if floor_id and floor_id != "both":
        if allowed is not None and floor_id not in allowed:
            raise HTTPException(status_code=403, detail="You do not have access to this floor")
        return [floor_id]
    return allowed


async def _won_quotations(
    floor_ids: Optional[list[str]], date_from: Optional[str], date_to: Optional[str],
) -> list[dict]:
    query: dict = {"status": "won"}
    if floor_ids is not None:
        query["floor_id"] = {"$in": floor_ids}
    if date_from or date_to:
        rng: dict = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        query["updated_at"] = rng
    return await db.quotations.find(query, {"_id": 0}).to_list(10000)


@router.get("/overview")
async def sales_overview(
    floor_id: Optional[str] = Query(None),
    referrer_type: Optional[Literal["architect", "interior_designer"]] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    granularity: Granularity = Query("month"),
    user: UserPublic = Depends(require_roles("owner", "admin")),
):
    floor_ids = _resolve_floor_ids(user, floor_id)
    quotations = await _won_quotations(floor_ids, date_from, date_to)

    if referrer_type:
        quotations = [q for q in quotations if q.get("referrer_type") == referrer_type]

    total_revenue = round(sum(q.get("grand_total", 0) for q in quotations), 2)

    by_floor: dict[str, float] = defaultdict(float)
    for q in quotations:
        by_floor[q.get("floor_id", "unknown")] += q.get("grand_total", 0)
    revenue_by_floor = [{"floor_id": fid, "revenue": round(rev, 2)} for fid, rev in by_floor.items()]

    trend_map: dict[str, float] = defaultdict(float)
    for q in quotations:
        ts = q.get("updated_at") or q.get("created_at")
        if ts:
            trend_map[_bucket_label(ts, granularity)] += q.get("grand_total", 0)
    trend = [{"bucket": k, "revenue": round(v, 2)} for k, v in sorted(trend_map.items())]

    referrers = None
    if referrer_type:
        by_referrer: dict[str, dict] = {}
        for q in quotations:
            rid = q.get("referrer_id")
            if not rid:
                continue
            entry = by_referrer.setdefault(
                rid, {"referrer_id": rid, "name": q.get("referrer_name") or "Unknown", "revenue": 0.0},
            )
            entry["revenue"] += q.get("grand_total", 0)
        referrers = sorted(
            ({**e, "revenue": round(e["revenue"], 2)} for e in by_referrer.values()),
            key=lambda e: e["revenue"], reverse=True,
        )

    return {
        "total_revenue": total_revenue,
        "quotation_count": len(quotations),
        "revenue_by_floor": revenue_by_floor,
        "trend": trend,
        "referrers": referrers,
    }


@router.get("/referrers/{referrer_id}")
async def referrer_detail(
    referrer_id: str,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    granularity: Granularity = Query("month"),
    user: UserPublic = Depends(require_roles("owner", "admin")),
):
    referrer = await db.referrers.find_one({"id": referrer_id}, {"_id": 0})
    if not referrer:
        raise HTTPException(status_code=404, detail="Referrer not found")

    floor_ids = _resolve_floor_ids(user, None)
    quotations = await _won_quotations(floor_ids, date_from, date_to)
    quotations = [q for q in quotations if q.get("referrer_id") == referrer_id]

    trend_map: dict[str, float] = defaultdict(float)
    for q in quotations:
        ts = q.get("updated_at") or q.get("created_at")
        if ts:
            trend_map[_bucket_label(ts, granularity)] += q.get("grand_total", 0)
    trend = [{"bucket": k, "revenue": round(v, 2)} for k, v in sorted(trend_map.items())]

    quotes = sorted(
        (
            {
                "id": q["id"], "number": q["number"], "customer_name": q["customer_name"],
                "grand_total": q.get("grand_total", 0), "updated_at": q.get("updated_at"),
            }
            for q in quotations
        ),
        key=lambda q: q["updated_at"] or "", reverse=True,
    )

    return {
        "referrer": referrer,
        "total_revenue": round(sum(q.get("grand_total", 0) for q in quotations), 2),
        "trend": trend,
        "quotations": quotes,
    }
