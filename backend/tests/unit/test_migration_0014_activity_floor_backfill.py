"""The backfill must derive the same floor the write path now stamps, and must
leave a row null rather than guessing when nothing resolves.

A guessed default is the failure mode worth guarding: `floor_id` defaults to
`"first-floor"` in several models, and applying that here would have filed
every underivable Ground Floor event under The Sanitary Bathroom.
"""
from __future__ import annotations

import asyncio
import importlib

migration = importlib.import_module("migrations.0014_backfill_activity_notification_floor_id")


class _Collection:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows or []

    def find(self, query, projection=None):
        matched = [r for r in self.rows if self._matches(r, query)]
        return _Cursor(matched)

    @staticmethod
    def _matches(row: dict, query: dict) -> bool:
        for key, want in query.items():
            have = row.get(key)
            if isinstance(want, dict) and "$in" in want:
                if have not in want["$in"]:
                    return False
            elif have != want:
                return False
        return True

    async def update_one(self, query, update):
        for row in self.rows:
            if self._matches(row, query):
                row.update(update["$set"])
                return
        raise AssertionError(f"no row matched {query}")

    async def bulk_write(self, ops, ordered=True):
        assert ops, "bulk_write must never be called with an empty op list"
        for op in ops:
            await self.update_one(op._filter, op._doc)

    async def create_index(self, *_args, **_kwargs):
        return None


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    async def to_list(self, _limit):
        return list(self._rows)

    def __aiter__(self):
        async def gen():
            for row in list(self._rows):
                yield row
        return gen()


class _Db:
    def __init__(self, **collections):
        self._collections = collections
        for name, coll in collections.items():
            setattr(self, name, coll)

    def __getitem__(self, name):
        return self._collections[name]


def _run(db):
    asyncio.run(migration.up(db))


def _db(*, activity_events, notifications=None, quotations=None,
        purchase_orders=None, customers=None, products=None, followups=None,
        payments=None, walkins=None):
    return _Db(
        activity_events=_Collection(activity_events),
        notifications=_Collection(notifications or []),
        quotations=_Collection(quotations or []),
        purchase_orders=_Collection(purchase_orders or []),
        customers=_Collection(customers or []),
        products=_Collection(products or []),
        followups=_Collection(followups or []),
        payments=_Collection(payments or []),
        walkins=_Collection(walkins or []),
    )


def test_quotation_reference_resolves_the_floor():
    db = _db(
        activity_events=[{"id": "e1", "quotation_id": "q1", "entity_type": "quotation", "entity_id": "q1"}],
        quotations=[{"id": "q1", "floor_id": "ground-floor"}],
    )
    _run(db)
    assert db.activity_events.rows[0]["floor_id"] == "ground-floor"


def test_purchase_reference_resolves_when_there_is_no_quotation():
    db = _db(
        activity_events=[{"id": "e1", "purchase_id": "po1", "entity_type": "purchase", "entity_id": "po1"}],
        purchase_orders=[{"id": "po1", "floor_id": "ground-floor"}],
    )
    _run(db)
    assert db.activity_events.rows[0]["floor_id"] == "ground-floor"


def test_entity_reference_resolves_for_a_product_event():
    db = _db(
        activity_events=[{"id": "e1", "entity_type": "product", "entity_id": "p1"}],
        products=[{"id": "p1", "floor_id": "ground-floor"}],
    )
    _run(db)
    assert db.activity_events.rows[0]["floor_id"] == "ground-floor"


def test_customer_reference_is_the_last_resort():
    db = _db(
        activity_events=[{"id": "e1", "customer_id": "c1", "entity_type": "customer", "entity_id": "c-missing"}],
        customers=[{"id": "c1", "floor_id": "first-floor"}],
    )
    _run(db)
    assert db.activity_events.rows[0]["floor_id"] == "first-floor"


def test_unresolvable_event_stays_null_rather_than_defaulting():
    db = _db(activity_events=[{"id": "e1", "entity_type": "user", "entity_id": "u1"}])
    _run(db)
    assert db.activity_events.rows[0].get("floor_id") is None


def test_already_stamped_events_are_not_revisited():
    db = _db(
        activity_events=[{"id": "e1", "quotation_id": "q1", "floor_id": "ground-floor"}],
        quotations=[{"id": "q1", "floor_id": "first-floor"}],
    )
    _run(db)
    assert db.activity_events.rows[0]["floor_id"] == "ground-floor"


def test_rerunning_is_idempotent():
    db = _db(
        activity_events=[{"id": "e1", "quotation_id": "q1"}],
        quotations=[{"id": "q1", "floor_id": "ground-floor"}],
    )
    _run(db)
    _run(db)
    assert db.activity_events.rows[0]["floor_id"] == "ground-floor"


# ── notification links ──────────────────────────────────────────────────────
def test_tile_order_link_resolves_before_a_shorter_prefix_could_shadow_it():
    db = _db(
        activity_events=[],
        notifications=[{"id": "n1", "link": "/tiles/orders/po1"}],
        purchase_orders=[{"id": "po1", "floor_id": "ground-floor"}],
    )
    _run(db)
    assert db.notifications.rows[0]["floor_id"] == "ground-floor"


def test_quotation_link_resolves():
    db = _db(
        activity_events=[],
        notifications=[{"id": "n1", "link": "/quotations/q1"}],
        quotations=[{"id": "q1", "floor_id": "first-floor"}],
    )
    _run(db)
    assert db.notifications.rows[0]["floor_id"] == "first-floor"


def test_link_query_string_is_not_part_of_the_id():
    db = _db(
        activity_events=[],
        notifications=[{"id": "n1", "link": "/quotations/q1?tab=timeline"}],
        quotations=[{"id": "q1", "floor_id": "first-floor"}],
    )
    _run(db)
    assert db.notifications.rows[0]["floor_id"] == "first-floor"


def test_notification_without_a_usable_link_stays_null():
    db = _db(activity_events=[], notifications=[{"id": "n1", "link": None}])
    _run(db)
    assert db.notifications.rows[0].get("floor_id") is None
