"""Regression test: product-by-ID endpoints must authorize by the product's
own floor, not the caller's ambient active-floor header, and alternates/
complete-the-set must scope their candidate pool to the SOURCE product's
floor rather than the caller's ambient state."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.exceptions import HTTPException

import routes.catalog_routes as catalog_routes
from models import UserPublic


def _user(active_floor_id: str = "first-floor", floor_ids: list[str] | None = None) -> UserPublic:
    if floor_ids is None:
        floor_ids = ["ground-floor", "first-floor"]
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=floor_ids, active_floor_id=active_floor_id,
    )


class _FakeProducts:
    def __init__(self, doc: dict):
        self._doc = doc

    async def find_one(self, query, projection=None, session=None):
        return self._doc if query.get("id") == self._doc["id"] else None


class _FakeDb:
    def __init__(self, doc: dict):
        self.products = _FakeProducts(doc)


def test_get_product_ignores_ambient_floor_mismatch(monkeypatch):
    doc = {"id": "p1", "floor_id": "ground-floor"}
    monkeypatch.setattr(catalog_routes, "db", _FakeDb(doc))
    fake = AsyncMock(return_value={"id": "p1"})
    monkeypatch.setattr(catalog_routes.catalog_service, "product_by_id", fake)

    result = asyncio.run(catalog_routes.get_product("p1", user=_user(active_floor_id="first-floor")))

    assert result == {"id": "p1"}
    fake.assert_awaited_once_with("p1", floor_ids=None)


def test_alternates_scope_pool_to_source_floor_not_ambient(monkeypatch):
    doc = {"id": "p1", "floor_id": "ground-floor"}
    monkeypatch.setattr(catalog_routes, "db", _FakeDb(doc))
    fake = AsyncMock(return_value={"source_product_id": "p1", "items": []})
    monkeypatch.setattr(catalog_routes.catalog_service, "alternate_products", fake)

    asyncio.run(catalog_routes.product_alternates("p1", user=_user(active_floor_id="first-floor")))

    _, kwargs = fake.await_args
    assert kwargs["floor_ids"] == ["ground-floor"]


def test_get_product_denies_access_when_user_lacks_floor_access(monkeypatch):
    """Regression: Verify that get_product denies access when the user doesn't
    have access to the product's floor. This catches the bug where a missing
    floor_id in the projection falls back to hardcoded "first-floor" and
    incorrectly allows access."""
    doc = {"id": "p1", "floor_id": "ground-floor"}
    monkeypatch.setattr(catalog_routes, "db", _FakeDb(doc))

    # User only has first-floor access, product is on ground-floor
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(catalog_routes.get_product(
            "p1",
            user=_user(active_floor_id="first-floor", floor_ids=["first-floor"]),
        ))

    assert exc_info.value.status_code == 403


def test_complete_the_set_scopes_pool_to_source_floor_not_ambient(monkeypatch):
    """Verify that complete-the-set scopes its candidate pool to the SOURCE
    product's floor, not the caller's ambient state."""
    doc = {"id": "p1", "floor_id": "ground-floor"}
    monkeypatch.setattr(catalog_routes, "db", _FakeDb(doc))
    fake = AsyncMock(return_value={"source_product_id": "p1", "items": []})
    monkeypatch.setattr(catalog_routes.catalog_service, "complete_set_products", fake)

    asyncio.run(catalog_routes.complete_the_set("p1", user=_user(active_floor_id="first-floor")))

    _, kwargs = fake.await_args
    assert kwargs["floor_ids"] == ["ground-floor"]
