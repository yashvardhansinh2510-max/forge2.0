import asyncio
import importlib


migration = importlib.import_module("migrations.0016_fix_followups_notebook_key_index")


class _FakeFollowups:
    def __init__(self):
        self.dropped = []
        self.created = []

    async def drop_index(self, name):
        self.dropped.append(name)

    async def create_index(self, keys, **options):
        self.created.append((keys, options))


class _FakeDb:
    def __init__(self):
        self.followups = _FakeFollowups()


def test_notebook_key_index_ignores_explicit_null_automated_followups():
    db = _FakeDb()
    asyncio.run(migration.up(db))

    assert db.followups.dropped == ["followups_notebook_key_unique"]
    keys, options = db.followups.created[0]
    assert keys == [("notebook_key", 1)]
    assert options["unique"] is True
    assert options["partialFilterExpression"] == {"notebook_key": {"$type": "string"}}
