# backend/tests/unit/test_orchestrator_size_field.py
"""Product.size already exists in the schema (models.py: "e.g. '600x600mm' —
tile nominal size") but no adapter or orchestrator code ever populated it —
this is the generic wiring, not Qutone-specific."""
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


def test_size_field_flows_from_row_to_persisted_product(_patch_db_and_uploads):
    job = {
        "id": "job-size-1", "supplier_name": "TestBrand", "floor_id": "first-floor",
        "rows": [{
            "row_id": "r1", "status": "accepted", "sku": "SKU-1", "mrp": 100.0,
            "category": "Tiles", "name": "Test Tile", "size": "600X600",
        }],
    }
    asyncio.run(orchestrator.import_accepted(job, user_id="user-1", floor_id="first-floor"))
    fake_db = orchestrator.db
    product = next(iter(fake_db.products.docs.values()))
    assert product["size"] == "600X600"


def test_missing_size_stays_null_not_fabricated(_patch_db_and_uploads):
    job = {
        "id": "job-size-2", "supplier_name": "TestBrand", "floor_id": "first-floor",
        "rows": [{
            "row_id": "r1", "status": "accepted", "sku": "SKU-2", "mrp": 100.0,
            "category": "Faucets", "name": "Test Faucet",
        }],
    }
    asyncio.run(orchestrator.import_accepted(job, user_id="user-1", floor_id="first-floor"))
    fake_db = orchestrator.db
    product = next(iter(fake_db.products.docs.values()))
    assert product["size"] is None
