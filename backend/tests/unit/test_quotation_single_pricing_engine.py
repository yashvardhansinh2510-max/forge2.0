"""The discount cascade has exactly one implementation.

It used to have four — recalc_quotation_totals, per_line_net_amounts, the
/breakdown route, and the PDF item enricher — and the last two had already
drifted apart on how they round a room-amount line's back-derived percent.
Every revenue number in the Executive Operating System is built on these
rows, so a fifth copy must not appear.
"""
from __future__ import annotations

from pathlib import Path

from models import QuotationLineItem, RoomDiscountCfg
from routes.quotation_routes import _breakdown_lines, _enriched_items_for_pdf
from services.pricing import recalc_quotation_totals

_ROOM_AMOUNT_DOC = {
    # 40,000 gross across one room, discounted by a flat 10,000 rupees, split
    # pro rata: 8,000 to the 32,000 line and 2,000 to the 8,000 line.
    "items": [
        {"id": "a", "product_id": "p1", "sku": "S1", "name": "A", "qty": 2, "unit_price": 16000.0, "room": "Bath"},
        {"id": "b", "product_id": "p2", "sku": "S2", "name": "B", "qty": 1, "unit_price": 8000.0, "room": "Bath"},
    ],
    "room_discounts": {"Bath": {"type": "amount", "value": 10000.0}},
}


def test_breakdown_lines_reconcile_to_the_totals():
    lines = _breakdown_lines(_ROOM_AMOUNT_DOC)
    totals = recalc_quotation_totals(
        [QuotationLineItem(**raw) for raw in _ROOM_AMOUNT_DOC["items"]],
        _ROOM_AMOUNT_DOC.get("project_discount_pct", 0),
        _ROOM_AMOUNT_DOC.get("category_discounts", {}),
        {k: RoomDiscountCfg(**v) for k, v in _ROOM_AMOUNT_DOC["room_discounts"].items()},
    )
    net = 0.0
    for line in lines:
        net += line["net"]
    assert round(net, 2) == totals["grand_total"] == 30000.0
    assert [line["discount_amount"] for line in lines] == [8000.0, 2000.0]


def test_room_amount_pct_is_back_derived_per_line():
    """Both lines get the same 25% here because the allocation is pro rata,
    but the percent is derived from the allocated rupees, never assumed."""
    lines = _breakdown_lines(_ROOM_AMOUNT_DOC)
    assert [line["discount_pct"] for line in lines] == [25.0, 25.0]
    assert [line["discount_source"] for line in lines] == ["room", "room"]


def test_pdf_enricher_reports_the_same_effective_pct():
    items = _enriched_items_for_pdf(_ROOM_AMOUNT_DOC)
    assert [i["discount_pct"] for i in items] == [25.0, 25.0]
    # every other field survives untouched
    assert [i["sku"] for i in items] == ["S1", "S2"]


def test_precedence_product_over_room_over_category_over_project():
    doc = {
        "items": [
            {"id": "p", "product_id": "x", "sku": "S", "name": "prod", "qty": 1, "unit_price": 1000.0, "discount_pct": 5, "room": "Bath", "category_id": "c1"},
            {"id": "r", "product_id": "x", "sku": "S", "name": "room", "qty": 1, "unit_price": 1000.0, "room": "Bath", "category_id": "c1"},
            {"id": "c", "product_id": "x", "sku": "S", "name": "cat", "qty": 1, "unit_price": 1000.0, "category_id": "c1"},
            {"id": "j", "product_id": "x", "sku": "S", "name": "proj", "qty": 1, "unit_price": 1000.0},
        ],
        "project_discount_pct": 40,
        "category_discounts": {"c1": 30},
        "room_discounts": {"Bath": {"type": "percent", "value": 20}},
    }
    lines = _breakdown_lines(doc)
    assert [line["discount_pct"] for line in lines] == [5.0, 20.0, 30.0, 40.0]
    assert [line["discount_source"] for line in lines] == ["product", "room", "category", "project"]


def test_the_cascade_is_not_reimplemented_in_the_routes_layer():
    """Structural guard. The room-amount pro-rata allocation is identifiable
    by its `room_gross` accumulator; it belongs to services/pricing.py only."""
    routes = Path(__file__).resolve().parents[2] / "routes" / "quotation_routes.py"
    assert "room_gross" not in routes.read_text(encoding="utf-8")
