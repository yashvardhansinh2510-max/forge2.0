"""Pure shaping for the Performance workspace (spec §7 Workspace 2).

No Mongo access in this file — see gather_performance.py, the only module
that reads the database for this workspace. Every function here takes
already-fetched rows and returns typed, JSON-serializable dataclasses.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from services.analytics.periods import compare


@dataclass(frozen=True)
class SalespersonRow:
    salesperson_id: str
    name: str
    revenue: float
    orders: int
    aov: float
    walkins_handled: int
    conversion_pct: float | None
    last_activity_at: str | None
    rank: int
    previous_rank: int | None
    rank_movement: int | None
    comparison: dict


def salesperson_rows(
    current: list[dict],
    previous_revenue_by_id: dict[str, float],
    previous_rank_by_id: dict[str, int],
) -> list[SalespersonRow]:
    ordered = sorted(current, key=lambda p: (-float(p.get("revenue") or 0), p.get("name") or ""))
    result: list[SalespersonRow] = []
    for rank, person in enumerate(ordered, start=1):
        sid = person["salesperson_id"]
        revenue = float(person.get("revenue") or 0)
        orders = int(person.get("orders") or 0)
        walkins = int(person.get("walkins_handled") or 0)
        prior_revenue = previous_revenue_by_id.get(sid)
        prior_rank = previous_rank_by_id.get(sid)
        result.append(SalespersonRow(
            salesperson_id=sid,
            name=person.get("name") or "Unknown",
            revenue=revenue,
            orders=orders,
            aov=round(revenue / orders, 2) if orders else 0.0,
            walkins_handled=walkins,
            conversion_pct=round(orders / walkins * 100, 1) if walkins else None,
            last_activity_at=person.get("last_activity_at"),
            rank=rank,
            previous_rank=prior_rank,
            rank_movement=(prior_rank - rank) if prior_rank is not None else None,
            comparison=compare(revenue, prior_revenue or 0.0, prior_window_exists=True),
        ))
    return result


def row_dict(row: SalespersonRow) -> dict:
    return asdict(row)


from statistics import median

STAGE_ORDER: tuple[str, ...] = (
    "walkins", "selections", "quotations", "approved",
    "confirmed_orders", "release", "dispatch", "payments",
)
STAGE_LABELS: dict[str, str] = {
    "walkins": "Walk-ins", "selections": "Selections", "quotations": "Quotations",
    "approved": "Approved", "confirmed_orders": "Confirmed Orders",
    "release": "Release", "dispatch": "Dispatch", "payments": "Payments",
}


@dataclass(frozen=True)
class FunnelStage:
    key: str
    label: str
    count: int
    conversion_from_start_pct: float | None
    dropoff_from_previous_pct: float | None
    median_days_in_stage: float | None
    revenue_lost_at_drop: float


def funnel_stages(
    counts: dict[str, int],
    stage_durations: dict[str, list[float] | None],
    avg_order_value: float,
) -> list[FunnelStage]:
    start_count = counts.get(STAGE_ORDER[0], 0)
    result: list[FunnelStage] = []
    previous_count: int | None = None
    for key in STAGE_ORDER:
        count = counts.get(key, 0)
        conversion = round(count / start_count * 100, 1) if start_count else None
        if previous_count is None:
            dropoff = None
            lost = 0.0
        else:
            dropped = max(previous_count - count, 0)
            dropoff = round(dropped / previous_count * 100, 1) if previous_count else None
            lost = round(dropped * avg_order_value, 2)
        durations = stage_durations.get(key)
        median_days = round(median(durations), 2) if durations else None
        result.append(FunnelStage(
            key=key, label=STAGE_LABELS[key], count=count,
            conversion_from_start_pct=conversion, dropoff_from_previous_pct=dropoff,
            median_days_in_stage=median_days, revenue_lost_at_drop=lost,
        ))
        previous_count = count
    return result


@dataclass(frozen=True)
class CategoryRow:
    category_id: str
    name: str
    revenue: float
    qty: float


def category_rows(raw: list[dict], category_names: dict[str, str]) -> list[CategoryRow]:
    rows = []
    for entry in raw:
        cid = entry.get("category_id") or "uncategorized"
        name = category_names.get(cid, "Uncategorized") if cid != "uncategorized" else "Uncategorized"
        rows.append(CategoryRow(category_id=cid, name=name, revenue=round(float(entry.get("revenue") or 0), 2), qty=float(entry.get("qty") or 0)))
    return sorted(rows, key=lambda r: -r.revenue)
