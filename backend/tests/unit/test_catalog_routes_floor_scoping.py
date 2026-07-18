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
