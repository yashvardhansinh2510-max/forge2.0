"""Shared quotation discount-resolution logic.

Moved out of routes/quotation_routes.py so it can also be used by
services/domain_outbox.py (the OrderPlaced handler that turns a quotation
into supplier Purchase Orders) WITHOUT a circular import — quotation_routes
already imports from domain_outbox, so domain_outbox can never import back
from quotation_routes.

Mirrors frontend/src/components/quotation/helpers/pricing.ts effectivePct
EXACTLY — these implementations must never drift, or the builder's live
totals would disagree with what the server persists / what a Purchase
Order is generated at.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from models import QuotationLineItem, RoomDiscountCfg


def effective_discount_pct(
    line: QuotationLineItem,
    room_discounts: dict[str, RoomDiscountCfg],
    category_discounts: dict[str, float],
    project_discount_pct: float,
) -> tuple[float, str]:
    """Return (pct, source) — Product override > Room > Category > Project.
    A room with an "amount" (flat ₹) discount has no single per-line pct —
    it's resolved by recalc_quotation_totals's second pass — so we return
    pct=0 with source "room_amount" here to signal "blocked from
    category/project, pending room-level allocation".
    """
    if line.discount_pct is not None:
        return float(line.discount_pct), "product"
    rd = room_discounts.get(line.room) if line.room else None
    if rd and rd.value > 0:
        if rd.type == "percent":
            return float(rd.value), "room"
        return 0.0, "room_amount"
    if line.category_id and line.category_id in category_discounts:
        return float(category_discounts[line.category_id]), "category"
    if project_discount_pct:
        return float(project_discount_pct), "project"
    return 0.0, "none"


def recalc_quotation_totals(
    items: list[QuotationLineItem],
    project_discount_pct: float = 0.0,
    category_discounts: dict[str, float] | None = None,
    room_discounts: dict[str, RoomDiscountCfg] | None = None,
) -> dict:
    category_discounts = category_discounts or {}
    room_discounts = room_discounts or {}
    subtotal = 0.0
    discount_total = 0.0

    rows = []
    for it in items:
        gross = it.qty * it.unit_price
        pct, source = effective_discount_pct(it, room_discounts, category_discounts, project_discount_pct)
        disc = gross * pct / 100
        rows.append({"gross": gross, "disc": disc, "source": source, "room": it.room})

    by_room: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["source"] == "room_amount":
            by_room[row["room"] or ""].append(row)
    for room, room_rows in by_room.items():
        cfg = room_discounts.get(room)
        if not cfg or cfg.type != "amount" or cfg.value <= 0:
            continue
        room_gross = sum(r["gross"] for r in room_rows)
        flat = min(cfg.value, room_gross)
        if room_gross <= 0 or flat <= 0:
            continue
        for row in room_rows:
            row["disc"] = flat * (row["gross"] / room_gross)

    for row in rows:
        subtotal += row["gross"]
        discount_total += row["disc"]

    grand_total = subtotal - discount_total
    return {
        "subtotal": round(subtotal, 2),
        "discount_total": round(discount_total, 2),
        "grand_total": round(grand_total, 2),
    }


def per_line_net_amounts(doc: dict[str, Any]) -> dict[str, float]:
    """Resolve every line's EFFECTIVE (post-discount) total, honouring
    product/room/category/project discounts exactly like the customer-facing
    /breakdown endpoint and the builder's live totals.

    Used by the OrderPlaced automation so a Purchase Order's unit_cost keeps
    whatever discount was actually applied to the quotation instead of
    silently falling back to the full undiscounted unit_price whenever the
    discount came from a room/category/project rule rather than being
    stamped directly on the line item.

    Returns {line_id: net_total} — divide by qty for a per-unit cost.
    """
    project_pct = doc.get("project_discount_pct", 0) or 0
    cat_discs = doc.get("category_discounts", {}) or {}
    room_discs = {k: RoomDiscountCfg(**v) for k, v in (doc.get("room_discounts") or {}).items()}

    rows = []
    for raw in doc.get("items", []):
        it = QuotationLineItem(**raw)
        gross = it.qty * it.unit_price
        pct, source = effective_discount_pct(it, room_discs, cat_discs, project_pct)
        rows.append({"line_id": it.id, "gross": gross, "pct": pct, "source": source, "room": it.room, "disc": gross * pct / 100})

    by_room: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["source"] == "room_amount":
            by_room[row["room"] or ""].append(row)
    for room, room_rows in by_room.items():
        cfg = room_discs.get(room)
        if not cfg or cfg.type != "amount" or cfg.value <= 0:
            continue
        room_gross = sum(r["gross"] for r in room_rows)
        flat = min(cfg.value, room_gross)
        if room_gross <= 0 or flat <= 0:
            continue
        for row in room_rows:
            row["disc"] = flat * (row["gross"] / room_gross)

    return {row["line_id"]: round(row["gross"] - row["disc"], 2) for row in rows}
