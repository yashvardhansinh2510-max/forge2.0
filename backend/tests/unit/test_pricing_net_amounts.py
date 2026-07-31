"""Per-line net_amount must reconcile to grand_total under every discount
source, including the room "amount" (flat rupee) allocation that was
previously implemented twice and could drift."""
from __future__ import annotations

from models import QuotationLineItem, RoomDiscountCfg
from services.pricing import net_amounts, recalc_quotation_totals, stamp_net_amounts


def _line(line_id: str, qty: float, price: float, **kw) -> QuotationLineItem:
    return QuotationLineItem(id=line_id, product_id=f"p-{line_id}", sku=f"S-{line_id}", name=line_id, qty=qty, unit_price=price, **kw)


def _reconciles(items, **cfg) -> None:
    nets = net_amounts(items, **cfg)
    totals = recalc_quotation_totals(items, **cfg)
    # Half a paisa per line (independent rounding) plus half a paisa on the
    # total. 0.01 * N would let a systematic one-paisa-per-line error pass.
    assert abs(sum(nets.values()) - totals["grand_total"]) <= 0.005 * (len(items) + 1)


def test_no_discount_net_equals_gross():
    items = [_line("a", 2, 100.0)]
    assert net_amounts(items) == {"a": 200.0}
    _reconciles(items)


def test_product_level_discount():
    items = [_line("a", 2, 100.0, discount_pct=10)]
    assert net_amounts(items) == {"a": 180.0}
    _reconciles(items, project_discount_pct=50)  # product override wins


def test_project_discount_applies_when_no_override():
    items = [_line("a", 1, 100.0), _line("b", 1, 300.0)]
    assert net_amounts(items, project_discount_pct=10) == {"a": 90.0, "b": 270.0}
    _reconciles(items, project_discount_pct=10)


def test_category_discount_beats_project():
    items = [_line("a", 1, 100.0, category_id="c1")]
    cfg = {"project_discount_pct": 50, "category_discounts": {"c1": 10}}
    assert net_amounts(items, **cfg) == {"a": 90.0}
    _reconciles(items, **cfg)


def test_room_percent_discount_beats_category():
    items = [_line("a", 1, 100.0, room="Kitchen", category_id="c1")]
    cfg = {
        "category_discounts": {"c1": 50},
        "room_discounts": {"Kitchen": RoomDiscountCfg(type="percent", value=10)},
    }
    assert net_amounts(items, **cfg) == {"a": 90.0}
    _reconciles(items, **cfg)


def test_room_flat_amount_allocates_pro_rata_and_reconciles():
    # ₹300 flat off a room whose lines gross ₹100 and ₹300 → 25%/75% split.
    items = [_line("a", 1, 100.0, room="Bath"), _line("b", 1, 300.0, room="Bath")]
    cfg = {"room_discounts": {"Bath": RoomDiscountCfg(type="amount", value=300)}}
    assert net_amounts(items, **cfg) == {"a": 25.0, "b": 75.0}
    _reconciles(items, **cfg)


def test_room_flat_amount_never_exceeds_room_gross():
    items = [_line("a", 1, 100.0, room="Bath")]
    cfg = {"room_discounts": {"Bath": RoomDiscountCfg(type="amount", value=5000)}}
    assert net_amounts(items, **cfg) == {"a": 0.0}


def test_mixed_sources_all_reconcile():
    items = [
        _line("a", 2, 100.0, discount_pct=10),
        _line("b", 1, 300.0, room="Bath"),
        _line("c", 3, 50.0, room="Bath"),
        _line("d", 1, 900.0, category_id="c1"),
        _line("e", 4, 25.0),
    ]
    cfg = {
        "project_discount_pct": 5,
        "category_discounts": {"c1": 12},
        "room_discounts": {"Bath": RoomDiscountCfg(type="amount", value=200)},
    }
    _reconciles(items, **cfg)


def test_stamp_net_amounts_writes_onto_item_dicts():
    raw = [
        {"id": "a", "product_id": "p1", "sku": "S1", "name": "A", "qty": 1, "unit_price": 100.0},
        {"id": "b", "product_id": "p2", "sku": "S2", "name": "B", "qty": 1, "unit_price": 300.0},
    ]
    out = stamp_net_amounts(raw, project_discount_pct=10)
    assert [r["net_amount"] for r in out] == [90.0, 270.0]
    assert out is raw  # mutates in place, returns the same list


def test_stamp_net_amounts_overwrites_a_stale_value():
    raw = [{"id": "a", "product_id": "p1", "sku": "S1", "name": "A", "qty": 1, "unit_price": 100.0, "net_amount": 999.0}]
    assert stamp_net_amounts(raw)[0]["net_amount"] == 100.0


def test_stamp_handles_an_item_dict_with_no_id():
    raw = [{"product_id": "p1", "sku": "S1", "name": "A", "qty": 1, "unit_price": 100.0}]
    assert stamp_net_amounts(raw)[0]["net_amount"] == 100.0


def test_stamp_handles_duplicate_line_ids_independently():
    raw = [
        {"id": "dup", "product_id": "p1", "sku": "S1", "name": "A", "qty": 1, "unit_price": 100.0},
        {"id": "dup", "product_id": "p2", "sku": "S2", "name": "B", "qty": 1, "unit_price": 300.0},
    ]
    assert [r["net_amount"] for r in stamp_net_amounts(raw)] == [100.0, 300.0]


def test_grand_total_matches_the_historical_accumulator_on_a_boundary_case():
    """Pins a case where compensated summation and a plain fold disagree.

    sum() would return 275638.09 here. The value below is what this codebase
    has always produced and what is already persisted for real quotations.
    """
    items = [
        _line("a", 2, 4490.38), _line("b", 14, 7102.56), _line("c", 20, 3162.31),
        _line("d", 14, 6524.09), _line("e", 12, 5106.67),
    ]
    assert recalc_quotation_totals(items, project_discount_pct=15)["grand_total"] == 275638.08


def test_grand_total_boundary_case_with_fractional_quantities():
    """Same class of bug, no discounts involved at all."""
    items = [_line("a", 0.5, 2285.89), _line("b", 0.5, 1445.30), _line("c", 2.75, 2024.64)]
    assert recalc_quotation_totals(items)["grand_total"] == 7433.35
