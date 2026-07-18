"""Migration 0004 must backfill floor_id="first-floor" onto every existing
brand/category doc (neither collection has the field at all pre-migration)."""
from __future__ import annotations

import asyncio
import importlib

# Module name starts with a digit (0004_...), which isn't a valid dotted
# `import a.b` target — importlib.import_module() resolves it fine at
# runtime by string, the same way migrations/runner.py's `_discover()`
# loads every numbered migration (`f"migrations.{name}"`).
migration = importlib.import_module("migrations.0004_backfill_brand_category_floor_id")


class _FakeCollection:
    def __init__(self, docs: list[dict]):
        self.docs = docs
        self.update_many_calls: list[tuple[dict, dict]] = []

    async def update_many(self, query, update):
        self.update_many_calls.append((query, update))
        matched = 0
        for doc in self.docs:
            if all(doc.get(k) is None if v == {"$exists": False} else True for k, v in query.items()):
                doc.update(update.get("$set", {}))
                matched += 1
        return type("Result", (), {"modified_count": matched})()


class _FakeDb:
    def __init__(self):
        self.brands = _FakeCollection([{"id": "b1", "name": "Hansgrohe"}])
        self.categories = _FakeCollection([{"id": "c1", "name": "Faucets"}])


def test_migration_backfills_first_floor_on_brands_and_categories():
    fake_db = _FakeDb()
    asyncio.run(migration.up(fake_db))

    assert fake_db.brands.docs[0]["floor_id"] == "first-floor"
    assert fake_db.categories.docs[0]["floor_id"] == "first-floor"
