"""SKU uniqueness is now scoped per (floor_id, brand_id) rather than
globally or per-brand-only — the ground-floor tile catalog and the
first-floor sanitary catalog are separate businesses that may legitimately
reuse a supplier SKU code across floors.

PREREQUISITE (manual, human decision — do not automate): as of 2026-07-17
there is one known live duplicate SKU (26456000) under Hansgrohe, both rows
on floor_id="first-floor" — this migration's index will fail to build
against that data until it's resolved (rename one SKU or merge the two
products). See migrations/0003's docstring for the exact failure mode
(OperationFailure code 85) this class of problem produces if left
unresolved and the collision happens to also match on index name; a
brand-new index name here means a genuine duplicate-key error instead,
which is the correct, loud failure for real duplicate data — don't catch or
suppress it.

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
