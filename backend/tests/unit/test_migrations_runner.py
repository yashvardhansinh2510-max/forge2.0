"""Migration runner (backend/migrations/runner.py) — addresses the
"no versioned migration history, ad-hoc if-field-missing checks instead"
gap flagged in BACKEND_AUDIT_2026-07-17.md. Applies each migration exactly
once, in filename order, and is safe to call repeatedly."""
from __future__ import annotations

import asyncio

from migrations.runner import run_migrations


class _FakeCursor:
    def __init__(self, docs: list[dict]):
        self._iter = iter(docs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class _FakeMigrationsCollection:
    def __init__(self):
        self.docs: list[dict] = []

    def find(self, *_args, **_kwargs):
        return _FakeCursor(list(self.docs))

    async def create_index(self, *_args, **_kwargs):
        return None

    async def insert_one(self, doc):
        self.docs.append(doc)


class _GenericFakeCollection:
    """Accepts any create_index/insert_one/etc. call as a no-op — the real
    migration files each touch a different collection name, and this test
    only cares that the runner discovers/orders/tracks them correctly, not
    that each migration's own index-creation logic is re-verified here."""

    def __getattr__(self, _name):
        async def _noop(*_args, **_kwargs):
            return None
        return _noop


class _FakeDb:
    def __init__(self):
        self.schema_migrations = _FakeMigrationsCollection()

    def __getattr__(self, _name):
        # Only reached for attributes NOT already set in __init__ (i.e. any
        # collection name other than `schema_migrations`), so this never shadows it.
        return _GenericFakeCollection()


def test_run_migrations_discovers_and_applies_real_migrations_in_order():
    """Uses the real migrations/ directory (0001_baseline, 0002_..., 0003_...)
    against a fake db — confirms discovery + ordering + idempotency without
    needing a real Mongo connection."""
    fake_db = _FakeDb()

    ran_first = asyncio.run(run_migrations(fake_db))
    assert ran_first == sorted(ran_first)  # applied in filename order
    assert "0001_baseline" in ran_first
    assert len(ran_first) >= 3  # 0001, 0002, 0003 at minimum

    ran_second = asyncio.run(run_migrations(fake_db))
    assert ran_second == []  # nothing pending — already recorded as applied


def test_run_migrations_dry_run_reports_without_recording():
    fake_db = _FakeDb()

    pending = asyncio.run(run_migrations(fake_db, dry_run=True))
    assert "0001_baseline" in pending
    assert fake_db.schema_migrations.docs == []  # dry run must not write anything

    # A real (non-dry) run afterwards still sees everything as pending.
    ran = asyncio.run(run_migrations(fake_db))
    assert ran == pending
