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
