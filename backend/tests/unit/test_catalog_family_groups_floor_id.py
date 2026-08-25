"""Family-group cards (Catalog's default grouped view) must carry floor_id
so the frontend can tell tile families from sanitaryware ones without a
second request — needed for the per-card landscape image fix (tile photos
only), since "All floors" merges both kinds of product in one list."""
from __future__ import annotations

import asyncio

import services.catalog_service as catalog_service


class _FakeSnapshot:
    products = [
        {
            "id": "p1", "sku": "SKU-1", "name": "Tile A", "family_key": "fam-1",
            "family_name": "Tile A Family", "brand_id": "b1", "category_id": "c1",
            "price": 100, "mrp": 120, "images": [], "floor_id": "ground-floor",
            "size": "600x1200", "finish": "Matt",
        },
    ]
    media_rows_by_product = {}
    media_rows_by_family = {}


def test_family_groups_include_floor_id(monkeypatch):
    async def _fake_snapshot():
        return _FakeSnapshot()

    monkeypatch.setattr(catalog_service, "get_catalog_snapshot", _fake_snapshot)

    result = asyncio.run(catalog_service.list_family_groups(
        brand_id=None, category_id=None, subcategory=None, series=None, q=None,
        limit=60, skip=0, floor_ids=None,
    ))

    assert result["items"][0]["floor_id"] == "ground-floor"
    assert result["items"][0]["variants"][0]["sku"] == "SKU-1"
    assert result["items"][0]["variants"][0]["size"] == "600x1200"
    assert result["items"][0]["variants"][0]["finish"] == "Matt"
