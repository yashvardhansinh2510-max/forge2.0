"""The dashboard index migration must stay additive and query-shaped."""
from __future__ import annotations

import asyncio
import importlib


class _Collection:
    def __init__(self):
        self.calls: list[tuple[object, dict]] = []

    async def create_index(self, keys, **kwargs):
        self.calls.append((keys, kwargs))


class _Db:
    def __init__(self):
        self.quotations = _Collection()
        self.followups = _Collection()


def test_dashboard_indexes_cover_floor_scoped_sorts_and_due_work():
    migration = importlib.import_module("migrations.0018_add_dashboard_hot_read_indexes")
    db = _Db()
    asyncio.run(migration.up(db))

    assert [(keys, options["name"]) for keys, options in db.quotations.calls] == [
        ([("floor_id", 1), ("updated_at", -1)], "dashboard_quotations_floor_updated"),
        ([("floor_id", 1), ("created_at", -1)], "dashboard_quotations_floor_created"),
    ]
    keys, options = db.followups.calls[0]
    assert keys == [("floor_id", 1), ("assigned_to", 1), ("status", 1), ("due_at", 1)]
    assert options["name"] == "dashboard_followups_due"
