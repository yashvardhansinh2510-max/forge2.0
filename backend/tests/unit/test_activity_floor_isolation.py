"""Floor isolation for the Activity feed, timelines and notifications.

Three gaps this locks shut, all of them the same shape — a collection that
never carried `floor_id`, so the only "isolation" available was a client-side
compromise:

  * `GET /api/activity` returned an EMPTY list to floor-restricted staff and a
    merged cross-unit feed to owners/managers. Owners are exactly the accounts
    that work both business units, so in practice the feed always mixed The
    Sanitary Bathroom's quotation edits into Ground Floor's.
  * `GET /api/activity/product/{id}` had no access check of any kind — any
    authenticated staff member could read another unit's catalogue history.
  * the notification bell filtered on `user_id` alone, so the same owner saw
    both units' alerts on whichever floor they happened to be viewing.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import routes.activity_routes as activity_routes
import routes.misc_routes as misc_routes
import services.activity_log as activity_log
import services.notifications as notifications_service
from models import UserPublic


def _user(*, role="owner", floors=None, active=None) -> UserPublic:
    return UserPublic(
        email="user@forge.app", full_name="User", role=role,
        floor_ids=floors if floors is not None else ["ground-floor", "first-floor"],
        active_floor_id=active,
    )


class _RecordingCollection:
    """Captures the Mongo filter it was handed and replays canned rows."""

    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows or []
        self.last_query: dict | None = None
        self.inserted: list[dict] = []

    def find(self, query, projection=None):
        self.last_query = query
        return self

    def sort(self, *_args, **_kwargs):
        return self

    async def to_list(self, _limit):
        return list(self.rows)

    async def find_one(self, query, projection=None, session=None):
        self.last_query = query
        return self.rows[0] if self.rows else None

    async def insert_one(self, doc, session=None):
        self.inserted.append(doc)
        return doc


class _Db:
    def __init__(self, **collections):
        for name, coll in collections.items():
            setattr(self, name, coll)


# ── write path: log_event stamps a floor ────────────────────────────────────
def test_log_event_stamps_the_actors_active_floor(monkeypatch):
    events = _RecordingCollection()
    monkeypatch.setattr(activity_log, "db", _Db(activity_events=events))

    asyncio.run(activity_log.log_event(
        event_type="quotation.saved", entity_type="quotation", entity_id="q1",
        actor=_user(active="ground-floor"),
    ))

    assert events.inserted[0]["floor_id"] == "ground-floor"


def test_explicit_floor_id_beats_the_ambient_active_floor(monkeypatch):
    """The stale-header case. A Tiles document opened by direct URL carries
    whatever floor was last active, but the document itself is Ground Floor —
    the event must follow the document, not the request."""
    events = _RecordingCollection()
    monkeypatch.setattr(activity_log, "db", _Db(activity_events=events))

    asyncio.run(activity_log.log_event(
        event_type="quotation.created", entity_type="quotation", entity_id="q1",
        actor=_user(active="first-floor"), floor_id="ground-floor",
    ))

    assert events.inserted[0]["floor_id"] == "ground-floor"


def test_event_without_any_floor_signal_stays_null(monkeypatch):
    """Null, never a guessed default: the read path filters strictly, so an
    unstamped event is invisible everywhere rather than shown on the wrong
    floor."""
    events = _RecordingCollection()
    monkeypatch.setattr(activity_log, "db", _Db(activity_events=events))

    asyncio.run(activity_log.log_event(
        event_type="user.login", entity_type="user", entity_id="u1", actor_id="u1",
    ))

    assert events.inserted[0]["floor_id"] is None


# ── read path: timeline_for filters in Mongo ────────────────────────────────
def test_timeline_for_filters_on_floor_when_scoped(monkeypatch):
    events = _RecordingCollection()
    monkeypatch.setattr(activity_log, "db", _Db(activity_events=events))

    asyncio.run(activity_log.timeline_for(limit=10, floor_ids=["ground-floor"]))

    assert events.last_query["floor_id"] == {"$in": ["ground-floor"]}


def test_timeline_for_unrestricted_when_floor_ids_is_none(monkeypatch):
    events = _RecordingCollection()
    monkeypatch.setattr(activity_log, "db", _Db(activity_events=events))

    asyncio.run(activity_log.timeline_for(limit=10, floor_ids=None))

    assert "floor_id" not in events.last_query


def test_global_feed_scopes_to_the_active_floor(monkeypatch):
    """Replaces the old behaviour, which returned [] for restricted staff and
    an unfiltered merge for everyone else."""
    captured: dict = {}

    async def fake_timeline_for(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(activity_routes, "timeline_for", fake_timeline_for)

    asyncio.run(activity_routes.global_activity(limit=50, user=_user(active="ground-floor")))

    assert captured["floor_ids"] == ["ground-floor"]


def test_restricted_staff_get_their_own_floors_not_an_empty_feed(monkeypatch):
    captured: dict = {}

    async def fake_timeline_for(**kwargs):
        captured.update(kwargs)
        return [{"id": "e1"}]

    monkeypatch.setattr(activity_routes, "timeline_for", fake_timeline_for)

    rows = asyncio.run(activity_routes.global_activity(
        limit=50, user=_user(role="sales", floors=["first-floor"], active=None),
    ))

    assert captured["floor_ids"] == ["first-floor"]
    assert rows == [{"id": "e1"}]


# ── product timeline access check ───────────────────────────────────────────
def test_product_timeline_rejects_another_floors_product(monkeypatch):
    products = _RecordingCollection([])  # nothing matches the floor-scoped filter
    monkeypatch.setattr(activity_routes, "db", _Db(products=products))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(activity_routes.product_timeline(
            "p-on-ground-floor", limit=10, user=_user(role="sales", floors=["first-floor"], active="first-floor"),
        ))

    assert exc.value.status_code == 404


def test_product_timeline_allows_a_product_on_the_callers_floor(monkeypatch):
    products = _RecordingCollection([{"id": "p1", "floor_id": "first-floor"}])
    monkeypatch.setattr(activity_routes, "db", _Db(products=products))

    async def fake_timeline_for(**_kwargs):
        return [{"id": "e1"}]

    monkeypatch.setattr(activity_routes, "timeline_for", fake_timeline_for)

    rows = asyncio.run(activity_routes.product_timeline(
        "p1", limit=10, user=_user(role="sales", floors=["first-floor"], active="first-floor"),
    ))

    assert rows == [{"id": "e1"}]


# ── notifications ───────────────────────────────────────────────────────────
def test_notify_stores_the_source_records_floor(monkeypatch):
    rows = _RecordingCollection()
    monkeypatch.setattr(notifications_service, "db", _Db(notifications=rows))

    asyncio.run(notifications_service.notify(
        "u1", "Payment received", floor_id="ground-floor",
    ))

    assert rows.inserted[0]["floor_id"] == "ground-floor"


def test_notification_list_filters_by_user_and_floor(monkeypatch):
    rows = _RecordingCollection()
    monkeypatch.setattr(misc_routes, "db", _Db(notifications=rows))

    user = _user(active="ground-floor")

    asyncio.run(misc_routes.list_notifications(user=user))

    assert rows.last_query == {"user_id": user.id, "floor_id": {"$in": ["ground-floor"]}}
