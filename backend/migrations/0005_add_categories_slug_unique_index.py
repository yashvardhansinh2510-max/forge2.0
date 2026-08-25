"""categories never had a unique index on slug, unlike brands (which has one
via scripts/ensure_indexes.py). This closes the same class of check-then-act
race in POST /categories (routes/catalog_routes.py::create_category) that
brands.slug's existing index closes for POST /brands."""
from __future__ import annotations

from pymongo.errors import OperationFailure

_INDEX_CONFLICT_CODE = 85


async def _create_index_tolerant(collection, keys, **kwargs) -> None:
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as e:
        if e.code != _INDEX_CONFLICT_CODE:
            raise


async def up(db) -> None:
    await _create_index_tolerant(db.categories, "slug", unique=True, sparse=True, name="categories_slug")
