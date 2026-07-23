# backend/tests/unit/test_catalog_import_no_category_pollution.py
"""orchestrator.import_accepted() used to eagerly pre-seed all 12
sanitary-only ALLOWED_CATEGORIES onto whichever floor_id it was given
(catalog_pipeline/orchestrator.py, pre-fix lines 152-158) — harmless on
first-floor (all 12 already exist there from real imports) but would litter
a brand-new floor like ground-floor with 11 empty, irrelevant categories
(Faucets, Bidets, Urinals, ...) the moment the first tile import runs. The
per-row auto-create path a few lines below already creates whatever
category a row's own data specifies, generically, for any floor — the
eager pre-seed loop is redundant and actively harmful, so it's removed."""
from __future__ import annotations

import asyncio

import pytest

import catalog_pipeline.orchestrator as orchestrator


class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    async def to_list(self, _n):
        return list(self._docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs: dict[str, dict] = {d["id"]: d for d in (docs or [])}

    async def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs.values():
            if all(doc.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                return dict(doc)
        return None

    def find(self, query=None, *_args, **_kwargs):
        query = query or {}
        matched = [d for d in self.docs.values() if all(d.get(k) == v for k, v in query.items() if not isinstance(v, dict))]
        return _FakeCursor(matched)

    async def insert_one(self, doc):
        self.docs[doc["id"]] = dict(doc)

    async def insert_many(self, docs):
        for d in docs:
            d.setdefault("id", f"snap-{len(self.docs)}")
            self.docs[d["id"]] = dict(d)

    async def update_one(self, query, update):
        for doc in self.docs.values():
            if all(doc.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                doc.update(update.get("$set", {}))
                return


class _FakeDb:
    def __init__(self):
        self.brands = _FakeCollection()
        self.categories = _FakeCollection()
        self.products = _FakeCollection()
        self.catalog_import_snapshots = _FakeCollection()


@pytest.fixture(autouse=True)
def _patch_db_and_uploads(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(orchestrator, "db", fake_db)

    async def _noop_upload(*_args, **_kwargs):
        return None

    monkeypatch.setattr(orchestrator, "_upload_supplier_images", _noop_upload)
    return fake_db


def test_importing_a_tiles_row_creates_only_the_tiles_category_on_ground_floor(_patch_db_and_uploads):
    job = {
        "id": "job-cat-1", "supplier_name": "Qutone", "floor_id": "ground-floor",
        "rows": [{
            "row_id": "r1", "status": "accepted", "sku": "SKU-TILE-1", "mrp": 225.0,
            "category": "Tiles", "name": "Test Tile",
        }],
    }
    asyncio.run(orchestrator.import_accepted(job, user_id="user-1", floor_id="ground-floor"))
    fake_db = orchestrator.db
    category_names = {c["name"] for c in fake_db.categories.docs.values()}
    assert category_names == {"Tiles"}  # NOT the 12 sanitary categories too


def test_sanitary_row_still_auto_creates_its_own_category_generically(_patch_db_and_uploads):
    job = {
        "id": "job-cat-2", "supplier_name": "Grohe", "floor_id": "first-floor",
        "rows": [{
            "row_id": "r1", "status": "accepted", "sku": "SKU-FCT-1", "mrp": 1500.0,
            "category": "Faucets", "name": "Test Faucet",
        }],
    }
    asyncio.run(orchestrator.import_accepted(job, user_id="user-1", floor_id="first-floor"))
    fake_db = orchestrator.db
    category_names = {c["name"] for c in fake_db.categories.docs.values()}
    assert category_names == {"Faucets"}  # only what the row actually needed, not all 12
