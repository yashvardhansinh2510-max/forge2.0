"""An allowlist, not a noise filter: 57% of activity_events is
product.image_uploaded and user.login. An event not on the list can never
reach the owner's feed, so instrumentation added elsewhere cannot flood it."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.analytics.feed import EXECUTIVE_EVENTS, feed_rows, group_of

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def _iso(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


def test_the_noisiest_operational_events_are_not_on_the_allowlist():
    for noisy in ("product.image_uploaded", "user.login", "quotation.pdf_generated", "product.updated"):
        assert noisy not in EXECUTIVE_EVENTS


def test_the_executive_events_are_on_the_allowlist_under_their_real_names():
    for real in ("quotation.order_placed", "quotation.created", "payment.recorded",
                 "ready_batch.created", "purchase.chalan_dispatched", "walkin.created",
                 "followup.call_logged", "supplier.assigned"):
        assert real in EXECUTIVE_EVENTS


def test_an_event_off_the_allowlist_is_dropped():
    events = [{"id": "e1", "event_type": "product.image_uploaded", "created_at": _iso(1), "quotation_id": None}]
    assert feed_rows(events, entity_floors={}, values={}, now=NOW) == []


def test_an_allowed_event_renders_with_its_joined_value():
    events = [{"id": "e1", "event_type": "quotation.order_placed", "created_at": _iso(2),
               "quotation_id": "q1", "actor_name": "Rahul", "summary": "FQ-1 · JK"}]
    rows = feed_rows(events, entity_floors={"q1": "first-floor"}, values={"q1": 480000.0}, now=NOW)
    assert len(rows) == 1
    assert rows[0]["value"] == 480000.0
    assert rows[0]["destination"] == "/(admin)/quotations/q1"
    assert rows[0]["group"] == "today"


def test_an_event_whose_entity_no_longer_resolves_is_omitted_not_shown_unscoped():
    # activity_events has no floor_id; an unresolvable entity means the floor
    # cannot be derived, and showing it anyway is a floor leak.
    events = [{"id": "e1", "event_type": "quotation.order_placed", "created_at": _iso(1), "quotation_id": "gone"}]
    assert feed_rows(events, entity_floors={}, values={}, now=NOW) == []


def test_value_is_never_read_from_the_payload():
    """payload carries small diffs, not money. A value shown must come from the
    joined record or not be shown at all."""
    events = [{"id": "e1", "event_type": "quotation.order_placed", "created_at": _iso(1),
               "quotation_id": "q1", "payload": {"grand_total": 999999.0}}]
    rows = feed_rows(events, entity_floors={"q1": "first-floor"}, values={}, now=NOW)
    assert rows[0]["value"] is None


def test_grouping_covers_today_yesterday_and_this_week():
    assert group_of(_iso(1), NOW) == "today"
    assert group_of(_iso(30), NOW) == "yesterday"
    assert group_of(_iso(24 * 4), NOW) == "this_week"
    assert group_of(_iso(24 * 30), NOW) == "older"


def test_rows_are_newest_first():
    events = [
        {"id": "old", "event_type": "quotation.created", "created_at": _iso(5), "quotation_id": "q1"},
        {"id": "new", "event_type": "quotation.created", "created_at": _iso(1), "quotation_id": "q1"},
    ]
    rows = feed_rows(events, entity_floors={"q1": "first-floor"}, values={"q1": 1.0}, now=NOW)
    assert [r["id"] for r in rows] == ["new", "old"]


def test_only_approved_and_rejected_status_changes_reach_the_feed():
    def event(to_status):
        return {"id": to_status, "event_type": "quotation.status_changed", "created_at": _iso(1),
                "quotation_id": "q1", "payload": {"from": "draft", "to": to_status}}
    rows = feed_rows([event("approved"), event("draft"), event("rejected")],
                     entity_floors={"q1": "first-floor"}, values={"q1": 1.0}, now=NOW)
    assert {r["id"] for r in rows} == {"approved", "rejected"}


def test_floor_scoping_drops_events_outside_the_callers_floors():
    events = [
        {"id": "g", "event_type": "quotation.created", "created_at": _iso(1), "quotation_id": "qg"},
        {"id": "f", "event_type": "quotation.created", "created_at": _iso(1), "quotation_id": "qf"},
    ]
    rows = feed_rows(events, entity_floors={"qg": "ground-floor", "qf": "first-floor"},
                     values={}, now=NOW, accessible_floors=["ground-floor"])
    assert [r["id"] for r in rows] == ["g"]


def test_an_unrestricted_caller_sees_every_floor():
    events = [
        {"id": "g", "event_type": "quotation.created", "created_at": _iso(1), "quotation_id": "qg"},
        {"id": "f", "event_type": "quotation.created", "created_at": _iso(2), "quotation_id": "qf"},
    ]
    rows = feed_rows(events, entity_floors={"qg": "ground-floor", "qf": "first-floor"},
                     values={}, now=NOW, accessible_floors=None)
    assert len(rows) == 2


def test_a_customer_only_event_resolves_through_its_customer():
    events = [{"id": "w1", "event_type": "walkin.created", "created_at": _iso(1),
               "customer_id": "c1", "quotation_id": None}]
    rows = feed_rows(events, entity_floors={"c1": "ground-floor"}, values={}, now=NOW)
    assert len(rows) == 1 and rows[0]["destination"] == "/(admin)/customers/c1"


def test_every_allowlisted_event_declares_a_label():
    for event_type, label in EXECUTIVE_EVENTS.items():
        assert label, f"{event_type} has no feed label"
