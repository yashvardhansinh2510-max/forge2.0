"""Migration 0010 must create a unique index on customers.email — the same
index scripts/ensure_indexes.py has always created manually, now given a
versioned migration path (matching 0005/0007's treatment of
categories.slug/brands.slug) so a fresh database gets it without relying on
someone running that script. Re-verified 2026-07-23 against the live
buildcon_house database (read-only aggregate check): 6 customers, zero
duplicate emails case-insensitive, so this applies cleanly today."""
from __future__ import annotations

import asyncio
import importlib

migration = importlib.import_module("migrations.0010_add_customers_email_unique_index")


class _FakeCustomers:
    def __init__(self):
        self.create_index_calls: list[tuple[object, dict]] = []

    async def create_index(self, keys, **kwargs):
        self.create_index_calls.append((keys, kwargs))


class _FakeDb:
    def __init__(self):
        self.customers = _FakeCustomers()


def test_migration_creates_unique_index_on_customers_email():
    fake_db = _FakeDb()
    asyncio.run(migration.up(fake_db))

    assert len(fake_db.customers.create_index_calls) == 1
    keys, kwargs = fake_db.customers.create_index_calls[0]
    assert keys == "email"
    assert kwargs["unique"] is True
    assert kwargs["sparse"] is True
    assert kwargs["name"] == "customers_email_unique"
