"""Configurable workflow-transition follow-ups (2026-08).

Extends the same pattern as services/automation_rules.py — DB-configured,
never hardcoded strings in Python — but for one-time OPERATIONAL handoff
follow-ups fired by a business-event transition (e.g. "Quotation -> Order
Confirmed") rather than a recurring waiting-cadence reminder.

Each transition row defines: trigger label, the Follow-up title/message
template (with {customer_name}/{quotation_number} placeholders), priority,
and is_active — editable via
GET/PUT /followups/config/workflow-transitions (manager+ for PUT).
"""
from __future__ import annotations

from typing import Optional

from db import db
from models import now_iso

DEFAULT_TRANSITIONS: dict[str, dict] = {
    "order_confirmed": {
        "label": "Quotation → Order Confirmed",
        "title": "Order Confirmed",
        "message_template": (
            "{customer_name}'s order {quotation_number} has been confirmed. "
            "Proceed with order processing and hand off to Operations."
        ),
        "priority": "medium",
        "auto_close_note": "Operations began processing this order (material release recorded).",
    },
}


async def ensure_seeded() -> None:
    for key, cfg in DEFAULT_TRANSITIONS.items():
        existing = await db.workflow_transitions.find_one({"key": key}, {"_id": 0, "key": 1})
        if existing:
            continue
        await db.workflow_transitions.insert_one({
            "key": key, "is_active": True, "created_at": now_iso(), "updated_at": now_iso(), **cfg,
        })


async def list_transitions() -> list[dict]:
    await ensure_seeded()
    return await db.workflow_transitions.find({}, {"_id": 0}).sort("key", 1).to_list(100)


async def get_transition(key: str) -> Optional[dict]:
    await ensure_seeded()
    return await db.workflow_transitions.find_one({"key": key}, {"_id": 0})


async def update_transition(key: str, patch: dict, user_id: Optional[str] = None, user_name: Optional[str] = None) -> dict:
    await ensure_seeded()
    patch = {k: v for k, v in patch.items() if v is not None}
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user_id
    patch["updated_by_name"] = user_name
    await db.workflow_transitions.update_one({"key": key}, {"$set": patch}, upsert=True)
    return await db.workflow_transitions.find_one({"key": key}, {"_id": 0})
