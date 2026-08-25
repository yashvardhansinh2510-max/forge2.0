"""Owner-declared analytics targets.

Stored as a single key-addressed document in the existing `settings`
collection (key "analytics_targets"), which the Phase 8 Goals & Targets
workspace will read and write unchanged — targets are stored once.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import require_roles
from db import db
from models import AnalyticsTargets, UserPublic, now_iso

router = APIRouter(prefix="/analytics", tags=["analytics"])

SETTINGS_KEY = "analytics_targets"


def available_target_signals(targets: AnalyticsTargets) -> list[str]:
    """Which Health Score components have a target to measure against.

    A zero target is treated as unset — dividing by it would make attainment
    infinite rather than meaningful.
    """
    signals = []
    if targets.monthly_revenue_target:
        signals.append("revenue_attainment")
    if targets.target_conversion_pct:
        signals.append("conversion_health")
    return signals


async def load_targets() -> AnalyticsTargets:
    doc = await db.settings.find_one({"key": SETTINGS_KEY}, {"_id": 0})
    return AnalyticsTargets(**{k: v for k, v in (doc or {}).items() if k in AnalyticsTargets.model_fields})


@router.get("/targets")
async def get_targets(user: UserPublic = Depends(require_roles("owner", "admin", "manager"))):
    targets = await load_targets()
    return {"targets": targets.model_dump(), "available_signals": available_target_signals(targets)}


@router.put("/targets")
async def put_targets(body: AnalyticsTargets, user: UserPublic = Depends(require_roles("owner", "admin"))):
    await db.settings.update_one(
        {"key": SETTINGS_KEY},
        {"$set": {**body.model_dump(), "key": SETTINGS_KEY, "updated_at": now_iso(), "updated_by": user.id, "updated_by_name": user.full_name}},
        upsert=True,
    )
    return {"targets": body.model_dump(), "available_signals": available_target_signals(body)}
