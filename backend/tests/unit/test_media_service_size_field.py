"""Regression test: hydrate_variants_batch must forward `size` into the
sibling-variant data it builds for family-grouped tile products. Tile
products are modelled as separate Product documents grouped by
`family_key` (not embedded ProductVariant rows), so this is the actual
code path that populates variant chips for real tile products. Task 20's
`variantDescriptor()` helper joins finish+size+color, so `size` must
survive both the Mongo projection and the constructed variant dict."""
from __future__ import annotations

import asyncio

import services.media_service as media_service
from services.media_service import hydrate_variants_batch


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    async def to_list(self, _n):
        return self.rows


class Products:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, _projection):
        family_keys = set(query.get("family_key", {}).get("$in", []))
        rows = [r for r in self.rows if r.get("family_key") in family_keys]
        return Cursor(rows)


class ProductMedia:
    def find(self, _query, _projection):
        return Cursor([])


class Db:
    def __init__(self, product_rows):
        self.products = Products(product_rows)
        self.product_media = ProductMedia()


def test_hydrate_variants_batch_forwards_size(monkeypatch):
    siblings = [
        {"id": "p1", "sku": "SKU-1", "family_key": "fam-1", "finish": None,
         "colour": None, "color": None, "size": "600x600mm", "price": 100.0,
         "mrp": 120.0, "stock": 5, "name": "Tile A"},
        {"id": "p2", "sku": "SKU-2", "family_key": "fam-1", "finish": None,
         "colour": None, "color": None, "size": "300x600mm", "price": 90.0,
         "mrp": 110.0, "stock": 3, "name": "Tile B"},
    ]
    monkeypatch.setattr(media_service, "db", Db(siblings))

    target = {"id": "p2", "family_key": "fam-1", "variants": []}
    docs = [target]

    asyncio.run(hydrate_variants_batch(docs))

    assert target["variants"], "expected sibling variant to be populated"
    sizes = {v["id"]: v.get("size") for v in target["variants"]}
    assert sizes == {"p1": "600x600mm"}
