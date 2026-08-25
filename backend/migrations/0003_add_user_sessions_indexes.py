"""Create the `user_sessions` indexes `bootstrap.py`'s own startup preflight
has always required (see REQUIRED_INDEXES in bootstrap.py) but that no
script in the repository ever actually created (BACKEND_AUDIT_2026-07-17.md
Critical #5 / High findings) — a fresh environment had no scripted path to
satisfy its own startup gate for this collection.

BUG FOUND while verifying this migration against a real database (2026-07-17):
the claim that "create_index is idempotent" is only true when name AND key
both match an existing index. This database already had both required
indexes present under MongoDB's auto-generated default names (`id_1`,
`user_type_1_user_id_1` — created by hand before this migration existed).
Naming them explicitly here then hits `OperationFailure` code 85
(IndexOptionsConflict: "Index already exists with a different name") —
which is NOT caught anywhere in `run_migrations()`, so it crashed
`uvicorn`'s startup outright on every boot against this database. Fixed by
tolerating that specific, harmless case: the key pattern already has an
index either way, so the requirement this migration exists to satisfy is
already met.
"""
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
    await _create_index_tolerant(db.user_sessions, "id", unique=True, name="user_sessions_id_unique")
    await _create_index_tolerant(
        db.user_sessions, [("user_type", 1), ("user_id", 1)], name="user_sessions_type_user",
    )
