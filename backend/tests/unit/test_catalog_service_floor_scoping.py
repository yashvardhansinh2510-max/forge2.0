"""Regression test: the in-memory catalog engine must respect floor
scoping. Root cause: _matches_filters (and every function built on it) had
no concept of floor_id at all, so switching floors never changed which
products/brands/categories the catalog returned."""
from __future__ import annotations

import asyncio

import services.catalog_service as catalog_service
from services.catalog_service import _build_snapshot, _matches_filters, list_brands_with_counts


def _product(floor_id: str) -> dict:
    return {
        "brand_id": "b1", "category_id": "c1", "subcategory": None, "series": None,
        "family_key": None, "finish": None, "colour": None, "floor_id": floor_id,
    }


def test_matches_filters_scopes_by_floor_ids():
    ground = _product("ground-floor")
    first = _product("first-floor")
    kwargs = dict(brand_id=None, category_id=None, subcategory=None, series=None,
                  family_key=None, finish=None, colour=None)

    assert _matches_filters(ground, floor_ids=["ground-floor"], **kwargs) is True
    assert _matches_filters(first, floor_ids=["ground-floor"], **kwargs) is False


def test_matches_filters_unscoped_when_floor_ids_is_none():
    first = _product("first-floor")
    kwargs = dict(brand_id=None, category_id=None, subcategory=None, series=None,
                  family_key=None, finish=None, colour=None)

    assert _matches_filters(first, floor_ids=None, **kwargs) is True


def test_list_brands_with_counts_does_not_leak_other_floors_products_into_count(monkeypatch):
    """Defense-in-depth regression test: list_brands_with_counts filters the
    BRAND list by floor_ids, but the Counter that computes each brand's
    product_count must ALSO be scoped to the same floor_ids. Today the
    invariant "no brand spans two floors" happens to hold, so building the
    Counter from the full unfiltered product list looks correct — but that
    invariant is not enforced anywhere. This test plants the invariant
    violation directly (the same brand_id appearing on two different
    floors) and asserts the ground-floor-scoped count does NOT include the
    first-floor product that happens to share its brand_id."""
    products = [
        {"id": "p-ground", "brand_id": "b1", "floor_id": "ground-floor"},
        {"id": "p-first", "brand_id": "b1", "floor_id": "first-floor"},
    ]
    brands = [{"id": "b1", "name": "Acme", "floor_id": "ground-floor"}]
    snapshot = _build_snapshot(products, [], brands, [], [])

    async def fake_get_catalog_snapshot():
        return snapshot

    monkeypatch.setattr(catalog_service, "get_catalog_snapshot", fake_get_catalog_snapshot)

    result = asyncio.run(list_brands_with_counts(floor_ids=["ground-floor"]))

    assert len(result) == 1
    assert result[0]["id"] == "b1"
    assert result[0]["product_count"] == 1
