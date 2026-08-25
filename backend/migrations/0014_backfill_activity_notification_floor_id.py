"""Backfill `floor_id` onto `activity_events` and `notifications`.

Both collections were written without a floor for their whole history, which
is why the global Activity feed and the notification bell were the last two
surfaces that could not be floor-filtered in Mongo. `routes/activity_routes.py`
used to compensate by returning an EMPTY feed to floor-restricted staff while
still showing owners/managers a merged cross-unit feed; the bell had no floor
logic at all.

`services/activity_log.log_event` and `services/notifications.notify` now stamp
the field going forward. This migration derives it for the rows already stored,
in decreasing order of reliability:

  1. `quotation_id`  → that quotation's floor_id
  2. `purchase_id`   → that purchase order's floor_id
  3. `entity_type`/`entity_id` → the referenced document's floor_id
  4. `customer_id`   → that customer's floor_id

Notifications carry no entity reference, only a `link` (`/quotations/<id>`,
`/tiles/orders/<id>`, `/customers/<id>`), so their floor is derived from the
id embedded in that link using the same lookups.

Rows that resolve to nothing keep a null floor_id deliberately: the read paths
filter strictly on `{"floor_id": {"$in": [...]}}`, so an underivable row stays
invisible to every business unit rather than appearing on the wrong one. The
alternatives — guessing "first-floor", or matching nulls into every floor — are
both a silent leak. `user.login`/`user.created`/`user.role_changed` events are
genuinely floor-less account-administration rows and fall in this bucket by
design; they are read through the Team screens, not the activity feed.

Idempotent: only ever touches documents where `floor_id` is missing or null,
and re-running after a partial run simply resolves the remainder.
"""
from __future__ import annotations

import re

from pymongo import UpdateOne
from pymongo.errors import OperationFailure

_INDEX_CONFLICT_CODE = 85
# One round trip per row is minutes of latency against Atlas even at a few
# thousand events, and this collection only grows.
_BATCH_SIZE = 500

# entity_type value -> collection name holding that entity.
_ENTITY_COLLECTIONS = {
    "quotation": "quotations",
    "purchase": "purchase_orders",
    "customer": "customers",
    "product": "products",
    "followup": "followups",
    "payment": "payments",
    "walkin": "walkins",
    "tile_customer_order": "customer_orders",
}

# Notification link prefix -> collection. Ordered longest-first so
# "/tiles/orders/" is tested before any shorter prefix could shadow it.
_LINK_COLLECTIONS = (
    ("/tiles/orders/", "purchase_orders"),
    ("/quotations/", "quotations"),
    ("/customers/", "customers"),
    ("/purchases/", "purchase_orders"),
)

_MISSING = {"floor_id": {"$in": [None]}}  # matches both an absent key and an explicit null


async def _create_index_tolerant(collection, keys, **kwargs) -> None:
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as e:
        if e.code != _INDEX_CONFLICT_CODE:
            raise


class _FloorResolver:
    """Batched id -> floor_id lookups with a per-run cache.

    A single collection scan per referenced collection, not one query per
    event: these collections have tens of thousands of rows in production.
    """

    def __init__(self, db):
        self._db = db
        self._cache: dict[str, dict[str, str]] = {}

    async def floors_for(self, collection_name: str) -> dict[str, str]:
        if collection_name not in self._cache:
            rows = await self._db[collection_name].find(
                {}, {"_id": 0, "id": 1, "floor_id": 1},
            ).to_list(200000)
            self._cache[collection_name] = {
                r["id"]: r["floor_id"] for r in rows if r.get("id") and r.get("floor_id")
            }
        return self._cache[collection_name]

    async def resolve(self, collection_name: str, doc_id: str | None) -> str | None:
        if not doc_id:
            return None
        return (await self.floors_for(collection_name)).get(doc_id)


async def _flush(collection, ops: list) -> int:
    if not ops:
        return 0
    await collection.bulk_write(ops, ordered=False)
    count = len(ops)
    ops.clear()
    return count


async def _backfill_activity_events(db, resolver: _FloorResolver) -> int:
    updated = 0
    ops: list = []
    cursor = db.activity_events.find(
        _MISSING,
        {"_id": 0, "id": 1, "quotation_id": 1, "purchase_id": 1, "customer_id": 1,
         "entity_type": 1, "entity_id": 1},
    )
    async for ev in cursor:
        floor_id = (
            await resolver.resolve("quotations", ev.get("quotation_id"))
            or await resolver.resolve("purchase_orders", ev.get("purchase_id"))
            or await resolver.resolve(
                _ENTITY_COLLECTIONS.get(ev.get("entity_type") or "", "quotations"),
                ev.get("entity_id") if ev.get("entity_type") in _ENTITY_COLLECTIONS else None,
            )
            or await resolver.resolve("customers", ev.get("customer_id"))
        )
        if not floor_id:
            continue
        ops.append(UpdateOne({"id": ev["id"]}, {"$set": {"floor_id": floor_id}}))
        if len(ops) >= _BATCH_SIZE:
            updated += await _flush(db.activity_events, ops)
    updated += await _flush(db.activity_events, ops)
    return updated


def _link_target(link: str | None) -> tuple[str, str] | None:
    if not link:
        return None
    for prefix, collection in _LINK_COLLECTIONS:
        if link.startswith(prefix):
            tail = link[len(prefix):]
            doc_id = re.split(r"[/?#]", tail, maxsplit=1)[0]
            if doc_id:
                return collection, doc_id
    return None


async def _backfill_notifications(db, resolver: _FloorResolver) -> int:
    updated = 0
    ops: list = []
    cursor = db.notifications.find(_MISSING, {"_id": 0, "id": 1, "link": 1})
    async for n in cursor:
        target = _link_target(n.get("link"))
        if not target:
            continue
        floor_id = await resolver.resolve(*target)
        if not floor_id:
            continue
        ops.append(UpdateOne({"id": n["id"]}, {"$set": {"floor_id": floor_id}}))
        if len(ops) >= _BATCH_SIZE:
            updated += await _flush(db.notifications, ops)
    updated += await _flush(db.notifications, ops)
    return updated


async def up(db) -> None:
    resolver = _FloorResolver(db)
    await _backfill_activity_events(db, resolver)
    await _backfill_notifications(db, resolver)

    # The global feed's exact access pattern: filter on floor, sort by recency.
    await _create_index_tolerant(
        db.activity_events, [("floor_id", 1), ("created_at", -1)],
        name="activity_events_floor_created",
    )
    await _create_index_tolerant(
        db.notifications, [("user_id", 1), ("floor_id", 1), ("created_at", -1)],
        name="notifications_user_floor_created",
    )
