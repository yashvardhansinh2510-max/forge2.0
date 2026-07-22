"""Pure functions computing a tile order's customer-facing delivery stage
from its embedded chalans. No DB access — the caller passes the raw
PurchaseOrder dict (as read from Mongo) and gets a stage string back. See
docs/superpowers/specs/2026-07-22-ground-floor-tiles-purchase-workflow-design.md
for the stage semantics.

Stages: "order" -> "material_released" -> "godown" -> "dispatch" -> "completed".
Godown is optional — a chalan can go released -> dispatched directly, or
released -> at_godown -> dispatched. The order-level stage reflects the
FURTHEST progress reached by any chalan (not the weakest), except that
"completed" requires every chalan to be dispatched.
"""
from __future__ import annotations


def remaining_qty_by_item(po: dict) -> dict[str, float]:
    """{po_item_id: qty not yet covered by any chalan}, one entry per item
    on the order."""
    totals = {item["id"]: float(item.get("qty") or 0) for item in po.get("items", [])}
    released: dict[str, float] = {}
    for chalan in po.get("chalans", []):
        for line in chalan.get("items", []):
            item_id = line["po_item_id"]
            released[item_id] = released.get(item_id, 0.0) + float(line.get("qty") or 0)
    return {
        item_id: round(max(0.0, total - released.get(item_id, 0.0)), 4)
        for item_id, total in totals.items()
    }


def is_fully_released(po: dict) -> bool:
    """True once every item's quantity is covered by cumulative chalans."""
    remaining = remaining_qty_by_item(po)
    return all(qty <= 1e-6 for qty in remaining.values())


def compute_order_stage(po: dict) -> str:
    chalans = po.get("chalans") or []
    if not chalans or not is_fully_released(po):
        return "order"
    if all(c.get("stage") == "dispatched" for c in chalans):
        return "completed"
    if any(c.get("stage") == "dispatched" for c in chalans):
        return "dispatch"
    if any(c.get("stage") == "at_godown" for c in chalans):
        return "godown"
    return "material_released"
