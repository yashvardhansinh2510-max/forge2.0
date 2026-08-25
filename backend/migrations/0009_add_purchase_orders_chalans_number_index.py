"""Production readiness audit (2026-07-23), Low: purchase_orders.chalans[]
(Ground Floor Tiles) shipped with no index entry, consistent with this
collection's pre-existing gap on items.id — not a regression, but worth
closing now that something actually scans across it. services/sequence.py's
collision-recovery path (`_seed_from_existing`) runs a `^CH-` prefix-
anchored regex over `chalans.number` across the whole collection whenever
the CH- counter is missing or reset; an index lets Mongo use an
index-prefix scan for that instead of a full collection scan. Same
versioned migration path as 0007's brands.slug index, for a fresh database
that never gets scripts/ensure_indexes.py run against it by hand."""
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
    await _create_index_tolerant(db.purchase_orders, "chalans.number", name="purchase_orders_chalans_number")
