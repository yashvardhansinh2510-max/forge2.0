"""customers.email had a check-then-insert race with nothing backing it at
the DB layer (BACKEND_AUDIT_2026-07-17.md High #14). scripts/ensure_indexes.py
has created this index manually since 07-17, but "manual" means it only
exists on a database someone remembered to run that script against — a
fresh environment gets nothing. Same treatment as 0005/0007
(categories.slug/brands.slug): move it into the auto-run migration path.
Re-verified 2026-07-23 against the live buildcon_house database: 6
customers, zero duplicate emails (case-insensitive), so a unique index
applies cleanly today."""
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
    await _create_index_tolerant(db.customers, "email", unique=True, sparse=True, name="customers_email_unique")
