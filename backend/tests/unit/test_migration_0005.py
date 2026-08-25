"""Migration 0005 must create a unique index on categories.slug — closing the
same check-then-act race in POST /categories that brands.slug's existing
index (scripts/ensure_indexes.py) already closes for POST /brands."""
from __future__ import annotations

import asyncio
import importlib

# Module name starts with a digit (0005_...), which isn't a valid dotted
# `import a.b` target — importlib.import_module() resolves it fine at
# runtime by string, the same way migrations/runner.py's `_discover()`
# loads every numbered migration (`f"migrations.{name}"`).
migration = importlib.import_module("migrations.0005_add_categories_slug_unique_index")


class _FakeCategories:
    def __init__(self):
        self.create_index_calls: list[tuple[object, dict]] = []

    async def create_index(self, keys, **kwargs):
        self.create_index_calls.append((keys, kwargs))


class _FakeDb:
    def __init__(self):
        self.categories = _FakeCategories()


def test_migration_creates_unique_index_on_categories_slug():
    fake_db = _FakeDb()
    asyncio.run(migration.up(fake_db))

    assert len(fake_db.categories.create_index_calls) == 1
    keys, kwargs = fake_db.categories.create_index_calls[0]
    assert keys == "slug"
    assert kwargs["unique"] is True
    assert kwargs["name"] == "categories_slug"
