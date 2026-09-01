from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from grohe_xlsx_extract import family_key_from_sku
from rekey_grohe_sku_variants import sku_prefix
import asyncio

import services.catalog_service as catalog_service
from services.catalog_service import _build_snapshot, hydrate_product, search_catalog


def test_grohe_skus_that_only_differ_in_final_three_characters_share_a_family():
    assert family_key_from_sku("Shower", "12345000", "Different description") == "grohe:sku:12345"
    assert family_key_from_sku("Plate", "12345AL0", "Another description") == "grohe:sku:12345"
    assert sku_prefix("12345000") == sku_prefix("12345AL0") == "12345"


def test_grohe_family_key_preserves_description_fallback_for_invalid_sku():
    assert family_key_from_sku("Shower", "--", "Rainshower Chrome") == "grohe:shower:rainshower"
    assert sku_prefix("--") is None


def test_grouped_search_and_hydration_expose_all_grohe_colour_variants(monkeypatch):
    family_key = family_key_from_sku("Plate", "37601000", "Nova plate")
    products = [
        {
            "id": f"p{index}", "sku": sku, "name": "Nova plate", "family_name": "Nova plate",
            "family_key": family_key, "brand_id": "grohe", "category_id": "plate",
            "floor_id": "first-floor", "colour": colour, "finish": colour,
            "variant_label": colour, "price": 100 + index, "mrp": 100 + index,
            "active": True,
        }
        for index, (sku, colour) in enumerate((
            ("37601000", "Chrome"), ("37601AL0", "Code AL0"),
            ("37601DL0", "Code DL0"), ("37601GN0", "Code GN0"),
        ))
    ]
    snapshot = _build_snapshot(products, [], [], [], [])

    async def fake_snapshot():
        return snapshot

    monkeypatch.setattr(catalog_service, "get_catalog_snapshot", fake_snapshot)
    result = asyncio.run(search_catalog(
        q="37601", brand_id="grohe", category_id=None, subcategory=None,
        series=None, limit=20, group=True, floor_ids=["first-floor"],
    ))

    assert result["total"] == 1
    assert {variant["sku"] for variant in result["items"][0]["variants"]} == {product["sku"] for product in products}
    hydrated = hydrate_product(products[0], snapshot)
    assert {variant["colour"] for variant in hydrated["variants"]} == {"Code AL0", "Code DL0", "Code GN0"}


def test_hydration_never_leaks_a_same_family_variant_from_another_floor():
    products = [
        {"id": "first", "sku": "37601000", "family_key": "grohe:sku:37601", "floor_id": "first-floor"},
        {"id": "ground", "sku": "37601AL0", "family_key": "grohe:sku:37601", "floor_id": "ground-floor"},
    ]
    snapshot = _build_snapshot(products, [], [], [], [])
    assert hydrate_product(products[0], snapshot).get("variants") is None
