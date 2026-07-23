"""Regression test for the Chalan-numbering collision-recovery bug: the
`_seed_from_existing` safety net (fires when a counter doc is missing/reset)
scanned `purchase_orders.number` — the PO's own FPO- number — instead of the
nested `purchase_orders.chalans[].number` where CH- numbers actually live.
If the counter was ever deleted, re-seeding would silently restart at
CH-0001 even with hundreds of higher-numbered live chalans already issued.

`array_field="chalans"` on `next_number` is the fix; this pins that scanning
the nested array finds the true max instead of missing it entirely.
"""
from __future__ import annotations

import asyncio

from services import sequence as sequence_service


class _FakeCursor:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    async def __aiter__(self):
        for doc in self._docs:
            yield doc


class _FakePOs:
    """Purchase orders whose own `number` is an FPO- number (never CH-), with
    CH- numbers only nested inside `chalans[].number` — the real shape."""

    def __init__(self, docs: list[dict]):
        self._docs = docs

    def find(self, query, _projection):
        prefix = query["chalans.number" if "chalans.number" in query else "number"]["$regex"].lstrip("^")
        matches = [d for d in self._docs if any(
            str(c.get("number") or "").startswith(prefix) for c in d.get("chalans", [])
        )] if "chalans.number" in query else [
            d for d in self._docs if str(d.get("number") or "").startswith(prefix)
        ]
        return _FakeCursor(matches)


class _FakeCounters:
    def __init__(self):
        self.doc = None
        self.seeded_seq = None

    async def find_one(self, query, *_a, **_kw):
        return dict(self.doc) if self.doc and query.get("_id") == self.doc["_id"] else None

    async def update_one(self, query, update, upsert=False):
        self.seeded_seq = update["$max"]["seq"]
        self.doc = {"_id": query["_id"], "seq": update["$max"]["seq"]}

    async def find_one_and_update(self, _query, update, **_kw):
        self.doc["seq"] += update["$inc"]["seq"]
        return dict(self.doc)


class _FakeDb:
    """sequence.py addresses the target collection dynamically via
    `db[collection]` (not attribute access), since the collection name is a
    caller-supplied string."""

    def __init__(self, pos: list[dict]):
        self.purchase_orders = _FakePOs(pos)
        self.counters = _FakeCounters()

    def __getitem__(self, name: str):
        return getattr(self, name)


def test_seeds_from_nested_chalan_numbers_not_top_level_po_number(monkeypatch):
    """The counter doc doesn't exist yet (simulating a deleted/reset
    counter). purchase_orders.number only ever holds FPO- numbers; CH-0007
    is the highest number actually issued, nested three levels down."""
    pos = [
        {"id": "po-1", "number": "FPO-0001", "chalans": [{"number": "CH-0003"}, {"number": "CH-0007"}]},
        {"id": "po-2", "number": "FPO-0002", "chalans": [{"number": "CH-0005"}]},
        {"id": "po-3", "number": "FPO-0003", "chalans": []},
    ]
    fake_db = _FakeDb(pos)
    monkeypatch.setattr(sequence_service, "db", fake_db)

    result = asyncio.run(sequence_service.next_number(
        "chalan", "CH-", collection="purchase_orders", width=4, array_field="chalans",
    ))

    # Highest existing was CH-0007 — next allocation must continue from
    # there (CH-0008), not restart at CH-0001 because the top-level `number`
    # field never matched the "^CH-" prefix.
    assert result == "CH-0008"


def test_top_level_seeding_still_works_for_non_array_kinds(monkeypatch):
    """array_field=None (every other caller: quotations, purchase orders
    themselves) must keep scanning the collection's own top-level `number`
    field exactly as before."""
    pos = [{"id": "po-1", "number": "FPO-2026-0001"}, {"id": "po-2", "number": "FPO-2026-0009"}]
    fake_db = _FakeDb(pos)
    monkeypatch.setattr(sequence_service, "db", fake_db)

    result = asyncio.run(sequence_service.next_number(
        "purchase_order", "FPO-2026-", collection="purchase_orders", width=4,
    ))

    assert result == "FPO-2026-0010"
