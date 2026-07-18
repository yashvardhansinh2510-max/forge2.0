"""Regression test: the in-memory catalog engine must respect floor
scoping. Root cause: _matches_filters (and every function built on it) had
no concept of floor_id at all, so switching floors never changed which
products/brands/categories the catalog returned."""
from __future__ import annotations

from services.catalog_service import _matches_filters


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
