"""Migration 0006 creates a compound unique index on products scoped to
(floor_id, brand_id, sku) — SKUs no longer need to be globally unique, only
unique within their own floor+brand, matching the 2026-07-17 decision to
scope uniqueness per floor now that the catalog spans multiple floors."""
from __future__ import annotations

import asyncio
import importlib

migration = importlib.import_module("migrations.0006_products_sku_unique_per_floor_brand")


class _FakeProducts:
    def __init__(self):
        self.create_index_calls: list[tuple] = []

    async def create_index(self, keys, **kwargs):
        self.create_index_calls.append((keys, kwargs))


class _FakeDb:
    def __init__(self):
        self.products = _FakeProducts()


def test_migration_creates_compound_unique_index():
    fake_db = _FakeDb()
    asyncio.run(migration.up(fake_db))

    keys, kwargs = fake_db.products.create_index_calls[0]
    assert keys == [("floor_id", 1), ("brand_id", 1), ("sku", 1)]
    assert kwargs.get("unique") is True
    assert kwargs.get("name") == "products_floor_brand_sku_unique"
