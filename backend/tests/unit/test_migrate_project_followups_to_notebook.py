import importlib

import pytest


migration = importlib.import_module("migrations.0015_migrate_project_followups_to_notebook")


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self.rows):
            raise StopAsyncIteration
        value = self.rows[self._index]
        self._index += 1
        return dict(value)

    async def to_list(self, _limit):
        return [dict(row) for row in self.rows]


class _Collection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.indexes = []

    @staticmethod
    def matches(row, query):
        for key, value in query.items():
            if isinstance(value, dict) and "$exists" in value:
                if (key in row) != value["$exists"]:
                    return False
            elif row.get(key) != value:
                return False
        return True

    def find(self, query, _projection=None):
        return _Cursor([row for row in self.rows if self.matches(row, query)])

    async def find_one(self, query, _projection=None):
        for row in self.rows:
            if self.matches(row, query):
                return dict(row)
        return None

    async def insert_one(self, row):
        self.rows.append(dict(row))

    async def update_one(self, query, update):
        for row in self.rows:
            if self.matches(row, query):
                row.update(update.get("$set", {}))
                return

    async def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))


class _Db:
    def __init__(self, legacy):
        self.project_followups = _Collection(legacy)
        self.customers = _Collection()
        self.followups = _Collection()
        self.activity_events = _Collection()


def test_legacy_mapping_preserves_allowed_fields_and_conversion():
    row = migration.legacy_to_notebook_document(
        {
            "id": "legacy-1", "customer_name": "A", "mobile_number": "+91 99099 06652",
            "business_type": "SS", "status": "quotation_created", "is_quotation_followup": True,
            "quotation_amount": 125000, "estimated_budget": 140000, "followup_date": "2026-08-06",
        },
        customer={"id": "c1", "name": "A", "tier": "retail"}, floor_id="second-floor",
    )
    assert row["notebook_key"] == "second-floor:c1"
    assert row["customer_phone"] == "9909906652"
    assert row["is_converted"] is True
    assert row["quotation_price"] == 125000
    assert row["estimated_value"] == 140000
    assert row["quotation_date"] == "2026-08-06"
    assert "current_stage" not in row


@pytest.mark.asyncio
async def test_migration_is_idempotent_and_preserves_source(monkeypatch):
    legacy = {
        "id": "legacy-1", "floor_id": "second-floor", "customer_name": "A",
        "mobile_number": "+91 99099 06652", "business_type": "GI", "status": "new",
        "notes": "Call back",
    }
    db = _Db([legacy])
    await migration.up(db)
    await migration.up(db)
    assert len(db.project_followups.rows) == 1
    assert len(db.followups.rows) == 1
    assert len(db.activity_events.rows) == 1
    assert db.followups.rows[0]["floor_id"] == "second-floor"
    assert db.followups.rows[0]["customer_id"] == db.customers.rows[0]["id"]
