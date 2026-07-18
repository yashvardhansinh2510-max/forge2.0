"""Numbered migration runner.

Forge previously had no versioned migration history — schema changes on live
data happened as ad-hoc one-off scripts in backend/scripts/, with no record
of what had already run against a given database (see
PRODUCTION_FIXES_2026-07-16.md item 4). This gives every future schema
change a single, auditable path:

    backend/migrations/0002_something.py:

        async def up(db):
            await db.some_collection.update_many({"field": {"$exists": False}}, {"$set": {"field": None}})

Rules for writing a migration:
  * Filename: `NNNN_snake_case_description.py`, NNNN zero-padded and strictly
    increasing — the runner applies them in filename order.
  * Must define an async `up(db)`. No `down()` — Forge migrations are
    forward-only (matches the rest of the codebase's style: additive,
    backward-compatible changes rather than destructive rollbacks).
  * Must be idempotent (safe to run twice) — the runner records success in
    `schema_migrations` and will not re-run an applied migration, but idempotency
    is still the safety net if that record is ever lost or hand-edited.
  * Never `DROP`/`delete_many` on a live collection without a reviewed,
    explicit reason in the migration's own docstring.

Usage:
    ./.venv/bin/python scripts/run_migrations.py            # apply all pending
    ./.venv/bin/python scripts/run_migrations.py --dry-run  # list pending only
"""
from __future__ import annotations

import importlib
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("forge.migrations")

MIGRATIONS_DIR = Path(__file__).resolve().parent


def _discover() -> list[tuple[str, str]]:
    """Returns [(name, module_path), ...] sorted by filename."""
    found = []
    for path in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.py")):
        name = path.stem
        found.append((name, f"migrations.{name}"))
    return found


async def ensure_migrations_index(db) -> None:
    await db.schema_migrations.create_index("name", unique=True, name="migration_name_unique")


async def pending_migrations(db) -> list[str]:
    applied = {d["name"] async for d in db.schema_migrations.find({}, {"name": 1, "_id": 0})}
    return [name for name, _ in _discover() if name not in applied]


async def run_migrations(db, *, dry_run: bool = False) -> list[str]:
    """Applies every not-yet-recorded migration in order. Returns the list of
    migration names that were (or, in dry-run, would be) applied."""
    await ensure_migrations_index(db)
    applied = {d["name"] async for d in db.schema_migrations.find({}, {"name": 1, "_id": 0})}
    ran: list[str] = []
    for name, module_path in _discover():
        if name in applied:
            continue
        if dry_run:
            ran.append(name)
            continue
        module = importlib.import_module(module_path)
        if not hasattr(module, "up"):
            raise RuntimeError(f"Migration {name} has no async up(db) function.")
        logger.info("Applying migration %s ...", name)
        await module.up(db)
        await db.schema_migrations.insert_one({"name": name, "applied_at": datetime.now(timezone.utc).isoformat()})
        logger.info("Applied %s.", name)
        ran.append(name)
    return ran
