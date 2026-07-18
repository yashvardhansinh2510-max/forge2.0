"""Migration 0007 must create a unique index on brands.slug — the same index
scripts/ensure_indexes.py has always created manually, now given a versioned
migration path (matching 0005's treatment of categories.slug) so a fresh
database gets it without relying on someone running that script."""
from __future__ import annotations

import asyncio
import importlib

migration = importlib.import_module("migrations.0007_add_brands_slug_unique_index")


class _FakeBrands:
    def __init__(self):
        self.create_index_calls: list[tuple[object, dict]] = []

    async def create_index(self, keys, **kwargs):
        self.create_index_calls.append((keys, kwargs))


class _FakeDb:
    def __init__(self):
        self.brands = _FakeBrands()


def test_migration_creates_unique_index_on_brands_slug():
    fake_db = _FakeDb()
    asyncio.run(migration.up(fake_db))

    assert len(fake_db.brands.create_index_calls) == 1
    keys, kwargs = fake_db.brands.create_index_calls[0]
    assert keys == "slug"
    assert kwargs["unique"] is True
    assert kwargs["name"] == "brands_slug"
