"""A discount-only edit re-prices every line, so items must be re-stamped
even when the request body carried no items at all."""
from __future__ import annotations

from routes.quotation_routes import _stamped_items_for_update


def _raw(line_id: str, qty: float, price: float, **kw) -> dict:
    return {"id": line_id, "product_id": f"p-{line_id}", "sku": f"S-{line_id}", "name": line_id, "qty": qty, "unit_price": price, **kw}


def test_items_supplied_in_the_update_are_stamped():
    doc = {"items": [], "project_discount_pct": 0, "category_discounts": {}, "room_discounts": {}}
    update = {"items": [_raw("a", 1, 100.0)], "project_discount_pct": 10}
    assert [i["net_amount"] for i in _stamped_items_for_update(update, doc)] == [90.0]


def test_discount_only_edit_restamps_the_existing_items():
    doc = {
        "items": [_raw("a", 1, 100.0, net_amount=100.0), _raw("b", 1, 200.0, net_amount=200.0)],
        "project_discount_pct": 0,
        "category_discounts": {},
        "room_discounts": {},
    }
    update = {"project_discount_pct": 25}  # no items in the body at all
    assert [i["net_amount"] for i in _stamped_items_for_update(update, doc)] == [75.0, 150.0]


def test_falls_back_to_stored_discount_config_for_keys_not_being_updated():
    doc = {
        "items": [_raw("a", 1, 100.0)],
        "project_discount_pct": 10,
        "category_discounts": {},
        "room_discounts": {},
    }
    update = {"items": [_raw("a", 1, 100.0)]}  # discounts unchanged
    assert _stamped_items_for_update(update, doc)[0]["net_amount"] == 90.0


def test_empty_quotation_returns_empty_list():
    doc = {"items": [], "project_discount_pct": 0, "category_discounts": {}, "room_discounts": {}}
    assert _stamped_items_for_update({"project_discount_pct": 5}, doc) == []
