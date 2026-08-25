"""Tile pricing normalization stays in the backend pricing boundary."""

from models import QuotationLineItem
from services.pricing import normalize_tile_line_item


def _line(**overrides):
    return QuotationLineItem(
        id="line-1", product_id="tile-1", sku="T-1", name="Tile",
        qty=2, unit_price=999, **overrides,
    )


def test_rate_per_sqft_conversion_is_backend_owned():
    line = normalize_tile_line_item(_line(rate_sqft=360, box_sqft=31))

    assert line.unit_price == 11160
    assert line.offer_rate == 360


def test_existing_offer_rate_is_preserved():
    line = normalize_tile_line_item(_line(rate_sqft=360, box_sqft=31, offer_rate=10800))

    assert line.unit_price == 334800
    assert line.offer_rate == 10800


def test_offer_rate_drives_box_and_line_price_over_rate_per_sqft():
    line = normalize_tile_line_item(_line(rate_sqft=130, box_sqft=35, offer_rate=80, rate_box=4550))

    assert line.rate_box == 2800
    assert line.unit_price == 2800


def test_missing_box_coverage_does_not_invent_a_conversion():
    line = normalize_tile_line_item(_line(rate_sqft=360, box_sqft=None))

    assert line.unit_price == 999
    assert line.offer_rate == 360


def test_quantity_unit_toggle_never_changes_the_quoted_price():
    box = normalize_tile_line_item(_line(rate_sqft=100, box_sqft=10, pcs_per_box="5", quantity_unit="Box"))
    piece = normalize_tile_line_item(_line(rate_sqft=100, box_sqft=10, pcs_per_box="5", quantity_unit="Pieces"))

    assert box.rate_box == piece.rate_box == 1000
    assert box.unit_price == piece.unit_price == 1000
