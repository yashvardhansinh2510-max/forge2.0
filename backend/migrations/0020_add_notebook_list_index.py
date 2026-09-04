"""Index the Kitchen/Furniture notebook's floor-scoped list query.

The register filters real notebook rows by floor and conversion state, may
filter their status, then sorts by most-recent update.  Keeping this index
partial prevents the much larger automated follow-up population from growing
the index or being scanned by this hot interaction path.
"""
from __future__ import annotations

from pymongo.errors import OperationFailure


INDEX_NAME = "followups_notebook_floor_view_list"


async def up(db) -> None:
    try:
        await db.followups.create_index(
            [
                ("floor_id", 1),
                ("is_converted", 1),
                ("updated_at", -1),
                ("id", -1),
            ],
            partialFilterExpression={"notebook_key": {"$type": "string"}},
            name=INDEX_NAME,
        )
    except OperationFailure as exc:
        # Repeated deploys may have already created the exact index.  Do not
        # hide a same-key/different-options conflict, which needs an operator
        # decision rather than silently using an unsuitable plan.
        if getattr(exc, "code", None) not in {68}:
            raise
