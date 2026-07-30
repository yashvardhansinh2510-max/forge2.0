"""Walk-ins business logic — kept out of routes/walkin_routes.py so
routes/quotation_routes.py can call the two status-transition hooks
without a route-to-route import.
"""
from __future__ import annotations

from typing import Optional

from db import db
from models import UserPublic, now_iso
from services.activity_log import log_event


def _digits(phone: Optional[str]) -> str:
    return "".join(c for c in (phone or "") if c.isdigit())


async def find_or_create_customer(
    *, name: str, phone: Optional[str], alternate_phone: Optional[str], email: Optional[str],
    floor_id: str, user: UserPublic,
) -> dict:
    """Duplicate detection per the Walk-ins spec: search existing customers
    by phone OR alternate phone (either direction — a new walk-in's phone
    might match an existing customer's alternate_phone, or vice versa)
    before ever creating a new Customer record. Email match is a stated
    future extension, not implemented yet (no reliable normalization rule
    was specified for it this session)."""
    phone_digits = _digits(phone)
    alt_digits = _digits(alternate_phone)
    candidates = [d for d in (phone_digits, alt_digits) if d]
    existing = None
    if candidates:
        existing = await db.customers.find_one(
            {"$or": [
                {"phone": {"$regex": f"{d}$"}} for d in candidates
            ] + [
                {"alternate_phone": {"$regex": f"{d}$"}} for d in candidates
            ]},
            {"_id": 0},
        )
    if existing:
        return existing

    from models import CustomerPublic
    data: dict = {
        "name": name, "phone": phone, "alternate_phone": alternate_phone,
        "email": email.lower() if email else None, "floor_id": floor_id,
    }
    cust = CustomerPublic(**data)
    to_store = cust.dict()
    if not to_store.get("email"):
        to_store.pop("email", None)  # customers_email_unique is a sparse index — omit the key entirely, not null
    await db.customers.insert_one(to_store)
    await log_event(
        event_type="customer.created", entity_type="customer", entity_id=cust.id,
        customer_id=cust.id, actor=user, summary="Customer Created (via Walk-in)",
    )
    return to_store


async def on_selection_created(customer_id: str, quotation_id: str, quotation_number: str) -> None:
    """Called by routes/quotation_routes.py right after a doc_type=
    "tiles_selection" Quotation is inserted. Advances any of this
    customer's still-open Walk-ins to "selection_completed" and links them
    to the new document — the walk_in_new Follow-up producer excludes this
    status, so the old card auto-closes on the next reconcile (fired by the
    caller), and the Tile Selections producer picks up the new document on
    its own next reconcile pass. No new reminder logic is added here."""
    from models_walkins import WALKIN_OPEN_STATUSES

    now = now_iso()
    await db.walkins.update_many(
        {"customer_id": customer_id, "status": {"$in": WALKIN_OPEN_STATUSES}, "is_deleted": False},
        {"$set": {"status": "selection_completed", "selection_quotation_id": quotation_id, "updated_at": now}},
    )
    walkins = await db.walkins.find(
        {"customer_id": customer_id, "selection_quotation_id": quotation_id}, {"_id": 0, "id": 1},
    ).to_list(10)
    for w in walkins:
        await log_event(
            event_type="walkin.selection_completed", entity_type="walkin", entity_id=w["id"],
            customer_id=customer_id, quotation_id=quotation_id,
            summary=f"Selection {quotation_number} created — Walk-in converted to Selection",
        )


async def on_moved_to_quotation(quotation_id: str, quotation_number: str) -> None:
    """Called right after routes/quotation_routes.py flips a Selection's
    doc_type to "tiles_quotation". Advances the linked Walk-in (if any) to
    "quotation_created"."""
    now = now_iso()
    result = await db.walkins.update_many(
        {"selection_quotation_id": quotation_id, "status": "selection_completed", "is_deleted": False},
        {"$set": {"status": "quotation_created", "updated_at": now}},
    )
    if result.modified_count:
        walkins = await db.walkins.find({"selection_quotation_id": quotation_id}, {"_id": 0, "id": 1, "customer_id": 1}).to_list(10)
        for w in walkins:
            await log_event(
                event_type="walkin.quotation_created", entity_type="walkin", entity_id=w["id"],
                customer_id=w.get("customer_id"), quotation_id=quotation_id,
                summary=f"Quotation {quotation_number} created from Selection",
            )
