"""Contract tests for the tile-only quotation defaults and totals."""

from models import QuotationLineItem
from routes.quotation_routes import _normalize_tile_items, _tile_totals


def _item(**kwargs) -> QuotationLineItem:
    return QuotationLineItem(
        id="line-1",
        product_id="tile-1",
        sku="T-1",
        name="Tile",
        qty=2,
        unit_price=125,
        **kwargs,
    )


def test_tile_offer_rate_defaults_to_product_rate_but_standard_does_not_mutate():
    tile = _item()
    standard = _item()

    _normalize_tile_items([tile], "tiles_quotation")
    _normalize_tile_items([standard], "standard")

    assert tile.offer_rate == 125
    assert standard.offer_rate is None


def test_tile_offer_rate_defaults_to_rate_per_sqft_not_derived_box_rate():
    tile = _item(rate_sqft=70, box_sqft=31)

    _normalize_tile_items([tile], "tiles_quotation")

    assert tile.unit_price == 2170
    assert tile.offer_rate == 70


def test_tile_transportation_fee_is_separate_from_subtotal_and_in_grand_total():
    totals = _tile_totals({"subtotal": 250, "grand_total": 225, "discount_total": 25}, 75, "tiles_quotation")

    assert totals["subtotal"] == 250
    assert totals["grand_total"] == 300
    assert totals["discount_total"] == 25


def test_transportation_fee_does_not_change_standard_quotation_totals():
    totals = {"subtotal": 250, "grand_total": 225, "discount_total": 25}

    assert _tile_totals(totals, 75, "standard") == totals
