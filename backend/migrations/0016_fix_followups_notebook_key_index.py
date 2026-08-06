"""Make the notebook-key uniqueness index ignore non-notebook follow-ups.

Automated quotation/order follow-ups intentionally have ``notebook_key=None``.
The original sparse unique index still indexed an explicitly stored null, so
the second such follow-up could fail with DuplicateKeyError. Only real string
notebook keys participate in the uniqueness contract.
"""
from __future__ import annotations

from pymongo.errors import OperationFailure


INDEX_NAME = "followups_notebook_key_unique"


async def up(db) -> None:
    try:
        await db.followups.drop_index(INDEX_NAME)
    except OperationFailure as exc:
        # A fresh database may not have the pre-0016 index. Mongo uses code 27
        # for IndexNotFound; tolerate that one case only.
        if getattr(exc, "code", None) != 27:
            raise

    await db.followups.create_index(
        [("notebook_key", 1)],
        unique=True,
        partialFilterExpression={"notebook_key": {"$type": "string"}},
        name=INDEX_NAME,
    )
