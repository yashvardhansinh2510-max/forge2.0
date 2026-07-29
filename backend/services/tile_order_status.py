"""Pure status/ageing/completion derivation for Tile Orders logistics — no
DB access, mirrors the discipline of services/chalan_stage.py. Every write
endpoint in routes/tile_orders.py calls these after mutating box counters,
so the stored overall_status/current_location/completion_percentage never
drift from the counters that produced them.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

_STATUS_RANK = {"Pending": 0, "Ready": 1, "Partially Dispatched": 2, "Dispatched": 3, "Delivered": 4}
_LOCATION_RANK = {"Pending": 0, "Ready": 1, "Dispatched": 2, "Godown": 3, "Delivered": 4}


def derive_item_status(
    boxes_ordered: float, boxes_ready: float, boxes_dispatched: float, *, all_delivered: bool = False,
) -> str:
    """Furthest-progress milestone ladder: Pending → Ready → Partially
    Dispatched → Dispatched → Delivered. Deliberately ignores how the
    untouched remainder splits between ready/pending — a caller showing
    boxes_ready=4/boxes_dispatched=8/boxes_pending=8 alongside this status
    is what keeps "partially ready" and "partially dispatched" from being
    conflated, not the status string itself."""
    if boxes_ordered <= 0:
        return "Pending"
    if boxes_dispatched >= boxes_ordered:
        return "Delivered" if all_delivered else "Dispatched"
    if boxes_dispatched > 0:
        return "Partially Dispatched"
    if boxes_ready > 0:
        return "Ready"
    return "Pending"


def derive_current_location(
    boxes_ordered: float, boxes_ready: float, boxes_dispatched: float, *,
    any_at_godown: bool = False, all_delivered: bool = False,
) -> str:
    """Physical location — a separate axis from overall_status. Godown is
    explicitly NOT part of the status ladder: a fully-dispatched item can be
    current_location=Godown while its overall_status is still Dispatched,
    because the material already left the supplier and is simply waiting at
    Buildcon's own warehouse before final delivery."""
    if boxes_ordered <= 0:
        return "Pending"
    if all_delivered and boxes_dispatched >= boxes_ordered:
        return "Delivered"
    if any_at_godown:
        return "Godown"
    if boxes_dispatched > 0:
        return "Dispatched"
    if boxes_ready > 0:
        return "Ready"
    return "Pending"


def completion_percentage(boxes_ordered: float, boxes_dispatched: float) -> float:
    if boxes_ordered <= 0:
        return 0.0
    return round(100 * boxes_dispatched / boxes_ordered, 1)


def rollup_status(statuses: list[str]) -> str:
    """Furthest-progress rollup across a list of child statuses (items →
    PO, POs → CustomerOrder). Empty input rolls up to Pending — an order
    with no items yet has nothing further than Pending to report."""
    if not statuses:
        return "Pending"
    return max(statuses, key=lambda s: _STATUS_RANK.get(s, 0))


def waiting_days(created_at: str, *, today: Optional[datetime] = None) -> int:
    now = today or datetime.now(timezone.utc)
    created = datetime.fromisoformat(created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (now - created).days


def ageing_band(days: int) -> str:
    if days <= 7:
        return "green"
    if days <= 14:
        return "amber"
    return "red"


def supplier_silent_days(
    last_supplier_activity_at: Optional[str], created_at: str, *, today: Optional[datetime] = None,
) -> int:
    """Falls back to order creation time when the supplier has never had
    any logged activity yet — distinguishes 'old and the supplier worked on
    it yesterday' from 'old and silent' on the Company/Supplier dashboards."""
    return waiting_days(last_supplier_activity_at or created_at, today=today)
