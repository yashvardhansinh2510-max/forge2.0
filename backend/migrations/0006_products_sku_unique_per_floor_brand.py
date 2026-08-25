"""SKU uniqueness is now scoped per (floor_id, brand_id) rather than
globally or per-brand-only — the ground-floor tile catalog and the
first-floor sanitary catalog are separate businesses that may legitimately
reuse a supplier SKU code across floors.

The previously reported Hansgrohe collision was verified as already
normalised in production: the two valid products are stored as ``26456000``
and ``26456000-2``. The ``-2`` row is the "With attachment" variant; it is
not a duplicate document. Keep this index strict: any future same-floor,
same-brand SKU collision must use an explicit supplier/variant SKU suffix
rather than silently overwriting a catalog row.

** DEPLOYMENT WARNING — this is not just about avoiding a manual script. **
`migrations/runner.py` auto-applies every pending migration at every backend
startup (see `server.py`'s startup event, which calls `run_migrations(db)`
uncaught — unlike the reconciliation call right below it, this one has no
surrounding try/except). Traced this directly: there is no per-migration
error handling in the runner either. So the moment this file exists in
`backend/migrations/` on any deployment pointed at a database that still has
the Hansgrohe duplicate, the *next process restart* (not a manual
`scripts/run_migrations.py` invocation — any restart) will raise an uncaught
`DuplicateKeyError` out of the FastAPI startup handler, which aborts
application startup entirely. Because the migration never gets recorded as
applied on failure, this repeats on every subsequent restart — a boot crash
loop, not a one-time error. Do not deploy/merge this file to any environment
that shares the live database until the duplicate SKU above is resolved.
"""
from __future__ import annotations


async def up(db) -> None:
    await db.products.create_index(
        [("floor_id", 1), ("brand_id", 1), ("sku", 1)],
        unique=True,
        name="products_floor_brand_sku_unique",
    )
