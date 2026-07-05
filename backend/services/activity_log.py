"""Activity log — the single write path for every domain event.

Timelines (per-quotation, per-purchase, per-customer, global) are read models
over the `activity_events` collection. Never write events from the client —
routes call `log_event` to record them.

Events are best-effort: a logging failure MUST NOT block the business op.
"""
from __future__ import annotations
import logging
from typing import Optional

from db import db
from models import ActivityEvent, ActivityEntity, UserPublic

logger = logging.getLogger("forge.activity")


# Canonical event type registry. Kept as strings (not an enum) so tests and
# clients can be lax; the frontend renders any unknown type by "titleising"
# it. Adding a new event just requires calling log_event with a new string.
QUOTATION_EVENTS = {
    "quotation.created",
    "quotation.customer_updated",
    "quotation.product_added",
    "quotation.product_removed",
    "quotation.product_reordered",
    "quotation.variant_changed",
    "quotation.room_created",
    "quotation.room_renamed",
    "quotation.room_deleted",
    "quotation.discount_changed",
    "quotation.saved",
    "quotation.revision_created",
    "quotation.pdf_generated",
    "quotation.status_changed",
    "quotation.order_placed",
    "quotation.duplicated",
}

PURCHASE_EVENTS = {
    "purchase.created",
    "purchase.status_changed",
    "purchase.received",
    "purchase.note_updated",
    "purchase.attachment_added",
    "purchase.assigned",
    "purchase.supplier_changed",
    "purchase.items_updated",
    "purchase.dispatched",
}

CUSTOMER_EVENTS = {"customer.created", "customer.updated"}


async def log_event(
    *,
    event_type: str,
    entity_type: ActivityEntity,
    entity_id: str,
    actor: Optional[UserPublic] = None,
    actor_id: Optional[str] = None,
    actor_name: Optional[str] = None,
    customer_id: Optional[str] = None,
    quotation_id: Optional[str] = None,
    purchase_id: Optional[str] = None,
    payload: Optional[dict] = None,
    summary: Optional[str] = None,
) -> Optional[ActivityEvent]:
    """Best-effort insert into activity_events. Returns the event or None."""
    try:
        ev = ActivityEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=(actor.id if actor else actor_id),
            actor_name=(actor.full_name if actor else actor_name),
            customer_id=customer_id,
            quotation_id=quotation_id,
            purchase_id=purchase_id,
            payload=payload or {},
            summary=summary,
        )
        await db.activity_events.insert_one(ev.dict())
        return ev
    except Exception as e:  # noqa: BLE001
        logger.warning("activity log failed (%s / %s): %s", event_type, entity_id, e)
        return None


async def timeline_for(
    *,
    entity_type: Optional[ActivityEntity] = None,
    entity_id: Optional[str] = None,
    quotation_id: Optional[str] = None,
    purchase_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """Fetch chronologically-descending audit events under any grouping key."""
    q: dict = {}
    ors: list[dict] = []
    if entity_type and entity_id:
        q["entity_type"] = entity_type
        q["entity_id"] = entity_id
    if quotation_id:
        ors.append({"quotation_id": quotation_id})
        ors.append({"entity_type": "quotation", "entity_id": quotation_id})
    if purchase_id:
        ors.append({"purchase_id": purchase_id})
        ors.append({"entity_type": "purchase", "entity_id": purchase_id})
    if customer_id:
        ors.append({"customer_id": customer_id})
        ors.append({"entity_type": "customer", "entity_id": customer_id})
    if ors:
        q["$or"] = ors
    docs = await db.activity_events.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return docs
