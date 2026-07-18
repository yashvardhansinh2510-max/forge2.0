"""brands.slug is checked by bootstrap.py's REQUIRED_INDEXES startup preflight
but, unlike categories.slug (migrations/0005), was only ever created by the
manually-run scripts/ensure_indexes.py — a fresh database never got it
without someone remembering to run that script. This gives it the same
versioned migration path as 0005."""
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
    await _create_index_tolerant(db.brands, "slug", unique=True, sparse=True, name="brands_slug")
