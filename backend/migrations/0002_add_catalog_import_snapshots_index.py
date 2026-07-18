"""Index the collection `catalog_pipeline.orchestrator.rollback_job` queries.

`rollback_job` does `db.catalog_import_snapshots.find({"job_id": job_id})` —
without an index that's a full collection scan on every rollback, and the
collection grows one document per created/updated product across every
catalog import ever run.

`scripts/ensure_indexes.py` no longer creates a competing index here — the
two mechanisms briefly picked different default names for the same (key)
index, and one differently-named index already existing crashed this
migration outright with OperationFailure code 85 (IndexOptionsConflict),
un-caught, on every startup (found 2026-07-17 while verifying the full
change set boots cleanly). This migration is now the sole owner of this
index, and tolerates the same conflict class defensively in case a
differently-named index is ever created here again by hand.
"""
from __future__ import annotations

from pymongo.errors import OperationFailure

_INDEX_CONFLICT_CODE = 85


async def up(db) -> None:
    try:
        await db.catalog_import_snapshots.create_index("job_id", name="snapshots_job_id")
    except OperationFailure as e:
        if e.code != _INDEX_CONFLICT_CODE:
            raise
