"""The Executive Activity Feed (spec §13.1).

An ALLOWLIST, not a noise filter. `activity_events` is mostly operational
exhaust — `product.image_uploaded` (890 rows) and `user.login` (497) are 57% of
the collection — so the feed renders only events that carry executive meaning.
A new event type is opt-in: instrumentation added anywhere else in the app can
never flood the owner's view.

Two constraints this collection imposes, both handled by joining rather than by
changing the write path:

  * **No `floor_id` on `activity_events`** (stamping it per event needs 30+
    call sites updated and was deferred in July). Floor is derived by joining
    the referenced entity, and an event whose entity no longer resolves is
    OMITTED rather than shown unscoped — showing it anyway would be the same
    class of leak the 2026-07-31 floor-isolation work closed.
  * **No money in `payload`.** It carries small diffs like
    `{from: "draft", to: "approved"}`. Every value shown is joined from the
    referenced record at read time, never read out of the payload — a figure
    stored twice is a figure that drifts from the books.

The allowlist uses the REAL `event_type` values in the live database, which
differ from the spec's prose in three places: dispatch completion is
`purchase.chalan_dispatched` / `dispatch.created` / `dispatch.delivered`,
godown receipt is `purchase.chalan_godown_received` / `item.moved_to_godown`,
and the walk-in conversion event is `walkin.quotation_created` (there is no
`walkin.selection_completed`).
"""
from __future__ import annotations

from datetime import datetime, timedelta

# event_type -> the line rendered in the feed.
EXECUTIVE_EVENTS: dict[str, str] = {
    "quotation.order_placed": "Order closed",
    "quotation.created": "New quotation",
    "quotation.status_changed": "Quotation status changed",
    "payment.recorded": "Payment received",
    "ready_batch.created": "Material released",
    "dispatch.created": "Dispatch created",
    "dispatch.delivered": "Dispatch delivered",
    "purchase.chalan_dispatched": "Dispatch completed",
    "purchase.chalan_godown_received": "Godown receipt",
    "item.moved_to_godown": "Moved to godown",
    "walkin.created": "New walk-in",
    "walkin.quotation_created": "Walk-in quoted",
    "followup.call_logged": "Customer contacted",
    "supplier.assigned": "Supplier assigned",
}

# Only these transitions are executive news; a draft->draft save is not.
MEANINGFUL_STATUS_CHANGES = ("approved", "rejected")

# The completion-shaped subset Today's Priorities renders as "Done today".
COMPLETION_EVENTS = (
    "quotation.order_placed",
    "payment.recorded",
    "purchase.chalan_dispatched",
    "dispatch.delivered",
    "followup.call_logged",
)


def _parse(stamp: str | None, now: datetime) -> datetime | None:
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=now.tzinfo) if parsed.tzinfo is None else parsed


def group_of(created_at: str | None, now: datetime) -> str:
    """Today / Yesterday / This week / Older, on calendar days rather than
    rolling 24-hour windows — "yesterday" must mean yesterday's date."""
    parsed = _parse(created_at, now)
    if parsed is None:
        return "older"
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if parsed >= today:
        return "today"
    if parsed >= today - timedelta(days=1):
        return "yesterday"
    if parsed >= today - timedelta(days=today.weekday()):
        return "this_week"
    return "older"


def _entity_ref(event: dict) -> tuple[str, str] | None:
    """Which record this event happened to, in drill-down priority order."""
    if event.get("quotation_id"):
        return "quotation", event["quotation_id"]
    if event.get("customer_id"):
        return "customer", event["customer_id"]
    if event.get("purchase_id"):
        return "purchase", event["purchase_id"]
    return None


_DESTINATIONS = {
    "quotation": "/(admin)/quotations/{id}",
    "customer": "/(admin)/customers/{id}",
    "purchase": "/(admin)/purchases",
}


def feed_rows(
    events: list[dict],
    entity_floors: dict[str, str],
    values: dict[str, float],
    now: datetime,
    accessible_floors: list[str] | None = None,
) -> list[dict]:
    """Filter, floor-scope, value-join and group. Pure — the caller resolves
    `entity_floors` (entity id -> floor) and `values` (entity id -> ₹) with
    real queries and passes them in."""
    rows: list[dict] = []
    for event in events:
        event_type = event.get("event_type")
        if event_type not in EXECUTIVE_EVENTS:
            continue
        if event_type == "quotation.status_changed":
            to_status = (event.get("payload") or {}).get("to")
            if to_status not in MEANINGFUL_STATUS_CHANGES:
                continue

        ref = _entity_ref(event)
        if ref is None:
            continue
        entity_type, entity_id = ref

        floor = entity_floors.get(entity_id)
        if floor is None:
            # Entity gone: the floor cannot be derived, so the event cannot be
            # shown without risking a cross-floor leak.
            continue
        if accessible_floors is not None and floor not in accessible_floors:
            continue

        parsed = _parse(event.get("created_at"), now)
        rows.append({
            "id": event.get("id"),
            "event_type": event_type,
            "label": EXECUTIVE_EVENTS[event_type],
            "summary": event.get("summary") or "",
            "actor_name": event.get("actor_name") or "",
            "created_at": event.get("created_at"),
            "group": group_of(event.get("created_at"), now),
            "floor_id": floor,
            "value": values.get(entity_id),
            "destination": _DESTINATIONS[entity_type].format(id=entity_id),
            "entity": {f"{entity_type}_id": entity_id},
            "is_completion": event_type in COMPLETION_EVENTS,
            "_sort": parsed.timestamp() if parsed else 0.0,
        })

    rows.sort(key=lambda r: r["_sort"], reverse=True)
    for row in rows:
        row.pop("_sort", None)
    return rows
