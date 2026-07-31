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


def _resolve_line_rows(
    items: list[QuotationLineItem],
    project_discount_pct: float,
    category_discounts: dict[str, float],
    room_discounts: dict[str, RoomDiscountCfg],
) -> list[dict]:
    """The one implementation of the discount cascade and the room "amount"
    pro-rata allocation.

    This loop used to exist twice — once in recalc_quotation_totals and once
    in per_line_net_amounts — which is exactly how per-line revenue drifted
    from grand_total. Both now build on this.
    """
    rows = []
    for it in items:
        gross = it.qty * it.unit_price
        pct, source = effective_discount_pct(it, room_discounts, category_discounts, project_discount_pct)
        rows.append({"line_id": it.id, "gross": gross, "source": source, "room": it.room, "disc": gross * pct / 100})

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
    return rows


def recalc_quotation_totals(
    items: list[QuotationLineItem],
    project_discount_pct: float = 0.0,
    category_discounts: dict[str, float] | None = None,
    room_discounts: dict[str, RoomDiscountCfg] | None = None,
) -> dict:
    rows = _resolve_line_rows(items, project_discount_pct, category_discounts or {}, room_discounts or {})
    subtotal = sum(row["gross"] for row in rows)
    discount_total = sum(row["disc"] for row in rows)
    return {
        "subtotal": round(subtotal, 2),
        "discount_total": round(discount_total, 2),
        "grand_total": round(subtotal - discount_total, 2),
    }


def net_amounts(
    items: list[QuotationLineItem],
    project_discount_pct: float = 0.0,
    category_discounts: dict[str, float] | None = None,
    room_discounts: dict[str, RoomDiscountCfg] | None = None,
) -> dict[str, float]:
    """Return {line_id: post-discount line total}.

    Sums to grand_total to within per-line rounding (each line is rounded to
    paise independently, so a quotation with N lines can differ from
    grand_total by at most N x ₹0.01 — assert with that tolerance, not equality.
    """
    rows = _resolve_line_rows(items, project_discount_pct, category_discounts or {}, room_discounts or {})
    return {row["line_id"]: round(row["gross"] - row["disc"], 2) for row in rows}


def per_line_net_amounts(doc: dict[str, Any]) -> dict[str, float]:
    """Doc-shaped wrapper over net_amounts().

    Used by the OrderPlaced automation so a Purchase Order's unit_cost keeps
    whatever discount was actually applied, and by the place-order preview so
    the review screen shows the same number the PO is created at.
    """
    return net_amounts(
        [QuotationLineItem(**raw) for raw in doc.get("items", [])],
        doc.get("project_discount_pct", 0) or 0,
        doc.get("category_discounts", {}) or {},
        {k: RoomDiscountCfg(**v) for k, v in (doc.get("room_discounts") or {}).items()},
    )


def stamp_net_amounts(
    item_dicts: list[dict[str, Any]],
    project_discount_pct: float = 0.0,
    category_discounts: dict[str, float] | None = None,
    room_discounts: dict[str, RoomDiscountCfg] | None = None,
) -> list[dict[str, Any]]:
    """Write each line's post-discount total onto its dict as net_amount.

    Mutates in place and returns the same list, so it can be dropped into a
    persistence path without re-binding. Always overwrites: a discount change
    re-prices every line even when no line itself was edited.
    """
    resolved = net_amounts(
        [QuotationLineItem(**raw) for raw in item_dicts],
        project_discount_pct,
        category_discounts,
        room_discounts,
    )
    for raw in item_dicts:
        raw["net_amount"] = resolved.get(raw.get("id"), 0.0)
    return item_dicts
