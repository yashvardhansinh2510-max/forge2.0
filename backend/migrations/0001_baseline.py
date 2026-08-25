"""Baseline marker — no schema change.

Records the point at which versioned migrations started being tracked. Every
migration written after this one can assume the schema described in
models.py as of 2026-07-17 (floor_id backfilled everywhere via
services/floor_scope.py's ensure_floor_scope(), payment idempotency keys,
atomic FQ-/FPO- sequence counters). This migration is intentionally a no-op —
it exists purely to seed the `schema_migrations` collection so `run_migrations.py`
has a starting point.
"""
from __future__ import annotations


async def up(db) -> None:
    return None
