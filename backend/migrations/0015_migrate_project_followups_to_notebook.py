"""Migrate the Kitchen/Furniture prototype rows into the shared followups set.

The source collection is intentionally left untouched. The migration is
idempotent by floor-scoped ``notebook_key`` and a legacy source marker, and it
also creates the indexes required by the notebook list and optimistic writes.
"""
from __future__ import annotations

from uuid import uuid4

from pymongo.errors import OperationFailure

from models import ActivityEvent, now_iso
from services.followup_notebook import normalize_mobile, resolve_or_create_customer

FLOORS = {"second-floor", "third-floor"}
STATUS_VALUES = {"new", "pending", "won", "lost"}


async def _create_index_tolerant(collection, keys, **kwargs) -> None:
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as error:
        if error.code != 85:
            raise


def migration_key(legacy: dict) -> str:
    return f"project_followup:{legacy.get('id')}"


def legacy_to_notebook_document(legacy: dict, *, customer: dict, floor_id: str) -> dict:
    raw_status = legacy.get("status") or "new"
    status = raw_status if raw_status in STATUS_VALUES else "new"
    is_converted = bool(legacy.get("is_quotation_followup") or raw_status == "quotation_created")
    notes = legacy.get("notes") or ""
    if status == "lost" and not notes.strip():
        notes = legacy.get("lost_reason") or "Legacy lost record"
    now = now_iso()
    return {
        "id": str(uuid4()),
        "floor_id": floor_id,
        "notebook_key": f"{floor_id}:{customer['id']}",
        "notebook_migration_key": migration_key(legacy),
        "source_key": migration_key(legacy),
        "rule_type": "manual",
        "category": "sales",
        "customer_id": customer["id"],
        "customer_name": legacy.get("customer_name") or customer.get("name") or "",
        "customer_phone": normalize_mobile(legacy.get("mobile_number") or customer.get("phone") or ""),
        "customer_tier": customer.get("tier", "retail"),
        "reason": "Migrated Kitchen/Furniture notebook row",
        "next_action": "Call customer",
        "next_action_reason": "Migrated from the previous notebook prototype.",
        "suggested_channel": "call",
        "priority_score": 0,
        "priority_level": "medium",
        "due_at": legacy.get("next_followup") or now,
        "status": "open",
        "is_automated": False,
        "notes": notes,
        "address": legacy.get("address") or customer.get("address"),
        "kitchen_type": legacy.get("business_type") if legacy.get("business_type") in {"GI", "SS"} else "GI",
        "referred_by": legacy.get("referred_by"),
        "architect_interior_designer": legacy.get("architect_interior_designer"),
        "notebook_status": status,
        "is_converted": is_converted,
        "quotation_price": legacy.get("quotation_amount") if is_converted else None,
        "estimated_value": legacy.get("estimated_budget") if is_converted else None,
        "quotation_date": legacy.get("quotation_date") or legacy.get("followup_date") if is_converted else None,
        "created_at": legacy.get("created_at") or now,
        "updated_at": legacy.get("updated_at") or now,
    }


async def _backfill_customer_phone_keys(db) -> None:
    cursor = db.customers.find({"phone_normalized": {"$exists": False}}, {"_id": 0, "id": 1, "phone": 1})
    async for customer in cursor:
        normalized = normalize_mobile(customer.get("phone") or "")
        if normalized:
            await db.customers.update_one({"id": customer["id"]}, {"$set": {"phone_normalized": normalized}})


async def _customer_for_legacy(db, legacy: dict, floor_id: str) -> dict | None:
    customer_id = legacy.get("customer_id")
    if customer_id:
        found = await db.customers.find_one({"id": customer_id, "floor_id": floor_id}, {"_id": 0})
        if found:
            return found
    phone = legacy.get("mobile_number") or ""
    if not normalize_mobile(phone):
        return None
    return await resolve_or_create_customer(
        db, user=None, floor_id=floor_id,
        name=legacy.get("customer_name") or "Unknown customer",
        phone=phone, address=legacy.get("address"),
    )


async def up(db) -> None:
    await _backfill_customer_phone_keys(db)
    await _create_index_tolerant(
        db.followups, [("notebook_key", 1)], unique=True, sparse=True,
        name="followups_notebook_key_unique",
    )
    await _create_index_tolerant(
        db.followups, [("floor_id", 1), ("updated_at", -1), ("id", 1)],
        name="followups_notebook_list",
    )
    await _create_index_tolerant(
        db.customers, [("floor_id", 1), ("phone_normalized", 1)],
        name="customers_floor_phone_normalized",
    )

    cursor = db.project_followups.find({}, {"_id": 0})
    async for legacy in cursor:
        floor_id = legacy.get("floor_id")
        if floor_id not in FLOORS:
            continue
        customer = await _customer_for_legacy(db, legacy, floor_id)
        if not customer:
            continue
        key = f"{floor_id}:{customer['id']}"
        existing = await db.followups.find_one({"notebook_key": key}, {"_id": 0, "id": 1})
        if existing:
            continue
        document = legacy_to_notebook_document(legacy, customer=customer, floor_id=floor_id)
        await db.followups.insert_one(document)
        event = ActivityEvent(
            event_type="project_followup.created",
            entity_type="followup",
            entity_id=document["id"],
            actor_id="migration",
            actor_name="Migration",
            customer_id=customer["id"],
            payload={"source": "project_followups", "source_id": legacy.get("id")},
            summary="Migrated from Kitchen/Furniture notebook prototype",
            floor_id=floor_id,
        )
        await db.activity_events.insert_one(event.model_dump())
