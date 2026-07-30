"""Configurable automation-rule cadences for the Follow-ups engine.

Redesign requirement: reminder day-thresholds must NOT be hardcoded in
Python — they live in Mongo (`automation_rules`) with sensible seeded
defaults, editable via Settings by owner/admin/manager. Any category key is
allowed (plain string, not a Literal) so a future department can register
its own cadence without touching this file.

see docs/superpowers/specs/2026-07-30-followups-v3-workspaces-design.md
"""
from __future__ import annotations

from typing import Optional

from db import db
from models import AutomationRule, now_iso

# Seeded once at startup (idempotent — see ensure_seeded). Values match the
# BuildCon House Follow-ups 2.0 spec exactly:
#   Tile Selection : Day 2 gentle -> Day 4 waiting/call -> Day 7 high priority
#                     -> Day 10 manager attention
#   Tile Quotation  : Day 2 -> Day 5 -> Day 10 -> Day 15, priority auto-escalates
DEFAULT_RULES: dict[str, dict] = {
    "selection": {"label": "Tile Selection waiting", "reminder_offsets_days": [2, 4, 7, 10]},
    "quotation_tiles": {"label": "Tile Quotation waiting", "reminder_offsets_days": [2, 5, 10, 15]},
}


async def ensure_seeded() -> None:
    """Idempotent — safe to call on every server startup."""
    for category, cfg in DEFAULT_RULES.items():
        existing = await db.automation_rules.find_one({"category": category}, {"_id": 0, "id": 1})
        if existing:
            continue
        rule = AutomationRule(category=category, label=cfg["label"], reminder_offsets_days=cfg["reminder_offsets_days"])
        await db.automation_rules.insert_one(rule.dict())


async def list_rules() -> list[dict]:
    await ensure_seeded()
    return await db.automation_rules.find({}, {"_id": 0}).sort("category", 1).to_list(200)


async def get_offsets(category: str) -> list[int]:
    """Active offsets for `category`, sorted ascending. Falls back to the
    seeded default (never hardcoded twice — DEFAULT_RULES is the single
    source of truth for the fallback) if the DB row is missing or inactive."""
    doc = await db.automation_rules.find_one({"category": category}, {"_id": 0})
    if doc and doc.get("is_active", True) and doc.get("reminder_offsets_days"):
        return sorted(doc["reminder_offsets_days"])
    return sorted(DEFAULT_RULES.get(category, {}).get("reminder_offsets_days", [7]))


async def update_rule(category: str, patch: dict, user_id: Optional[str] = None, user_name: Optional[str] = None) -> dict:
    await ensure_seeded()
    patch = {k: v for k, v in patch.items() if v is not None}
    if patch.get("reminder_offsets_days") is not None:
        patch["reminder_offsets_days"] = sorted(set(int(d) for d in patch["reminder_offsets_days"] if int(d) > 0))
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user_id
    patch["updated_by_name"] = user_name
    await db.automation_rules.update_one({"category": category}, {"$set": patch}, upsert=True)
    return await db.automation_rules.find_one({"category": category}, {"_id": 0})
