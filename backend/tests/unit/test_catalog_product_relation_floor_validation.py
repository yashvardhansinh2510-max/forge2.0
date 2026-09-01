"""Products may only reference a brand and category on their own floor."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import routes.catalog_routes as catalog_routes
from models import ProductCreate, ProductPatch, UserPublic


class _Collection:
    def __init__(self, docs):
        self.docs = list(docs)
        self.inserted = []
        self.updated = None

    async def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs:
            if self._matches(doc, query):
                return doc
        return None

    @staticmethod
    def _matches(doc, query):
        if "$and" in query:
            return all(_Collection._matches(doc, clause) for clause in query["$and"])
        for key, value in query.items():
            if isinstance(value, dict) and "$in" in value:
                if doc.get(key) not in value["$in"]:
                    return False
            elif doc.get(key) != value:
                return False
        return True

    async def insert_one(self, doc):
        self.inserted.append(doc)

    async def update_one(self, query, update):
        self.updated = (query, update)


class _Db:
    def __init__(self, product, brands, categories):
        self.products = _Collection([product] if product else [])
        self.brands = _Collection(brands)
        self.categories = _Collection(categories)


def _user() -> UserPublic:
    return UserPublic(email="purchase@forge.app", full_name="Purchase", role="purchase",
                      floor_ids=["ground-floor"], active_floor_id="ground-floor")


def _body(**overrides) -> ProductCreate:
    values = {"name": "Tile", "sku": "T-1", "brand_id": "brand-ground",
              "category_id": "category-ground", "mrp": 100, "price": 90}
    values.update(overrides)
    return ProductCreate(**values)


def _patch_common(monkeypatch, fake_db):
    monkeypatch.setattr(catalog_routes, "db", fake_db)
    monkeypatch.setattr(catalog_routes.catalog_service, "schedule_catalog_refresh", lambda: None)
    monkeypatch.setattr(catalog_routes.catalog_service, "patch_product_in_snapshot", lambda *_a: None)
    monkeypatch.setattr(catalog_routes, "log_event", lambda **_kw: None)


@pytest.mark.parametrize("field,foreign_id", [("brand_id", "brand-first"), ("category_id", "category-first")])
def test_create_product_rejects_relation_from_another_floor(monkeypatch, field, foreign_id):
    fake_db = _Db(None,
                  [{"id": "brand-ground", "floor_id": "ground-floor"}, {"id": "brand-first", "floor_id": "first-floor"}],
                  [{"id": "category-ground", "floor_id": "ground-floor"}, {"id": "category-first", "floor_id": "first-floor"}])
    _patch_common(monkeypatch, fake_db)

    with pytest.raises(HTTPException, match="same floor") as exc:
        asyncio.run(catalog_routes.create_product(_body(**{field: foreign_id}), user=_user()))

    assert exc.value.status_code == 400
    assert not fake_db.products.inserted


@pytest.mark.parametrize("field,foreign_id", [("brand_id", "brand-first"), ("category_id", "category-first")])
def test_update_product_rejects_relation_from_another_floor(monkeypatch, field, foreign_id):
    product = {"id": "product-1", "floor_id": "ground-floor", "brand_id": "brand-ground",
               "category_id": "category-ground", "name": "Tile", "sku": "T-1", "mrp": 100, "price": 90}
    fake_db = _Db(product,
                  [{"id": "brand-ground", "floor_id": "ground-floor"}, {"id": "brand-first", "floor_id": "first-floor"}],
                  [{"id": "category-ground", "floor_id": "ground-floor"}, {"id": "category-first", "floor_id": "first-floor"}])
    _patch_common(monkeypatch, fake_db)

    with pytest.raises(HTTPException, match="same floor") as exc:
        asyncio.run(catalog_routes.update_product("product-1", ProductPatch(**{field: foreign_id}), user=_user()))

    assert exc.value.status_code == 400
    assert fake_db.products.updated is None
