"""Regression test: Catalog read routes must pass the caller's floor scope
into the catalog engine instead of discarding the user entirely."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import routes.catalog_routes as catalog_routes
from models import UserPublic


def _user(floor_id: str) -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=floor_id,
    )


def test_list_brands_passes_floor_scope_ids(monkeypatch):
    fake = AsyncMock(return_value=[])
    monkeypatch.setattr(catalog_routes.catalog_service, "list_brands_with_counts", fake)

    asyncio.run(catalog_routes.list_brands(user=_user("ground-floor")))

    fake.assert_awaited_once_with(floor_ids=["ground-floor"])


def test_catalog_search_passes_floor_scope_ids(monkeypatch):
    fake = AsyncMock(return_value={"query": "", "total": 0, "grouped": False, "items": []})
    monkeypatch.setattr(catalog_routes.catalog_service, "search_catalog", fake)

    asyncio.run(catalog_routes.catalog_search(user=_user("ground-floor")))

    _, kwargs = fake.await_args
    assert kwargs["floor_ids"] == ["ground-floor"]


def test_recent_products_passes_active_floor_scope(monkeypatch):
    fake = AsyncMock(return_value=[])
    monkeypatch.setattr(catalog_routes.catalog_service, "recent_or_frequent_products", fake)
    user = _user("ground-floor")

    asyncio.run(catalog_routes.recent_products(limit=7, user=user))

    fake.assert_awaited_once_with(
        user.id, limit=7, recent=True, floor_ids=["ground-floor"],
    )


def test_frequent_products_passes_active_floor_scope(monkeypatch):
    fake = AsyncMock(return_value=[])
    monkeypatch.setattr(catalog_routes.catalog_service, "recent_or_frequent_products", fake)
    user = _user("first-floor")

    asyncio.run(catalog_routes.frequent_products(limit=9, user=user))

    fake.assert_awaited_once_with(
        user.id, limit=9, recent=False, floor_ids=["first-floor"],
    )


def test_create_brand_stamps_floor_for_write(monkeypatch):
    inserted = {}

    class _FakeBrands:
        async def find_one(self, *_a, **_kw):
            return None

        async def insert_one(self, doc):
            inserted.update(doc)

    class _FakeDb:
        brands = _FakeBrands()

    monkeypatch.setattr(catalog_routes, "db", _FakeDb())
    monkeypatch.setattr(catalog_routes.catalog_service, "schedule_catalog_refresh", lambda: None)

    from models import BrandCreate
    body = BrandCreate(name="CUTE", slug="cute")
    asyncio.run(catalog_routes.create_brand(body, user=_user("ground-floor")))

    assert inserted["floor_id"] == "ground-floor"
    assert inserted["name"] == "CUTE"


def test_create_category_stamps_floor_for_write(monkeypatch):
    inserted = {}

    class _FakeCategories:
        async def find_one(self, *_a, **_kw):
            return None

        async def insert_one(self, doc):
            inserted.update(doc)

    class _FakeDb:
        categories = _FakeCategories()

    monkeypatch.setattr(catalog_routes, "db", _FakeDb())
    monkeypatch.setattr(catalog_routes.catalog_service, "schedule_catalog_refresh", lambda: None)

    from models import CategoryCreate
    body = CategoryCreate(name="Tiles", slug="tiles")
    asyncio.run(catalog_routes.create_category(body, user=_user("ground-floor")))

    assert inserted["floor_id"] == "ground-floor"
    assert inserted["name"] == "Tiles"
