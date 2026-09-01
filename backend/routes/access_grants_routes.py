"""Owner/admin management API for custom staff access grants.

The router is intentionally isolated until it is registered in ``server.py``.
It does not alter existing role checks; a later integration adds grant-aware
dependencies to individual business endpoints.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user, invalidate_principal_cache, require_min_role, revoke_all_sessions
from db import db
from models import UserPublic
from services.access_grants import (
    ACTIONS, RESOURCE_REGISTRY, build_grant, grants_for_user, is_expired,
    is_valid_resource, normalized_actions, utc_now_iso,
)

router = APIRouter(prefix="/settings/access-grants", tags=["settings", "access grants"])


class AccessGrantInput(BaseModel):
    resource: str
    actions: list[Literal["view", "create", "update", "delete", "export"]] = Field(min_length=1)
    floor_id: str | None = None
    expires_at: str | None = None


def _validate_input(body: AccessGrantInput) -> list[str]:
    actions = normalized_actions(body.actions)
    if not is_valid_resource(body.resource) or actions is None:
        raise HTTPException(status_code=422, detail="Invalid access-grant resource or actions")
    if body.floor_id is not None and not body.floor_id.strip():
        raise HTTPException(status_code=422, detail="floor_id must be a non-empty string or null")
    if body.expires_at is not None and is_expired(body.expires_at):
        raise HTTPException(status_code=422, detail="expires_at must be a valid future ISO-8601 timestamp")
    return actions


async def _target_user_or_404(user_id: str) -> dict:
    target = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Team member not found")
    return target


async def _assert_can_manage_target(actor: UserPublic, target: dict) -> None:
    # Admins can manage staff grants, but no admin may change an owner's
    # scope. This mirrors the existing Team-management owner protection.
    if target.get("role") == "owner" and actor.role != "owner":
        raise HTTPException(status_code=403, detail="Only an owner can manage an owner's access grants")


async def _validate_floor(floor_id: str | None) -> None:
    if floor_id is None:
        return
    if not await db.floors.find_one({"id": floor_id, "active": {"$ne": False}}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=422, detail="floor_id must refer to an active floor")


async def _revoke_grant_subject(user_id: str) -> None:
    # Grant state is authorization state. Revoke every active device so stale
    # sessions cannot continue after an owner removes or narrows a grant.
    invalidate_principal_cache("staff", user_id)
    await revoke_all_sessions("staff", user_id)


@router.get("/resources")
async def list_grant_resources(_: UserPublic = Depends(require_min_role("admin"))):
    return {
        "resources": [
            {"key": key, "label": value["label"], "actions": sorted(ACTIONS)}
            for key, value in RESOURCE_REGISTRY.items()
        ],
    }


@router.get("/me")
async def my_access_grants(user: UserPublic = Depends(get_current_user)):
    """The caller's grants, for an honest client shell; API enforcement remains server-side."""
    return {"user_id": user.id, "grants": await grants_for_user(db, user.id)}


@router.get("/{user_id}")
async def list_access_grants(user_id: str, actor: UserPublic = Depends(require_min_role("admin"))):
    target = await _target_user_or_404(user_id)
    await _assert_can_manage_target(actor, target)
    return {"user_id": user_id, "grants": await grants_for_user(db, user_id)}


@router.post("/{user_id}", status_code=201)
async def create_access_grant(
    user_id: str, body: AccessGrantInput, actor: UserPublic = Depends(require_min_role("admin")),
):
    target = await _target_user_or_404(user_id)
    await _assert_can_manage_target(actor, target)
    actions = _validate_input(body)
    await _validate_floor(body.floor_id)
    grant = build_grant(
        user_id=user_id, resource=body.resource, actions=actions, floor_id=body.floor_id,
        expires_at=body.expires_at, actor_id=actor.id, actor_name=actor.full_name,
    )
    try:
        await db.access_grants.insert_one(grant)
    except Exception as exc:
        # The unique index is an operational invariant. Avoid leaking driver
        # details and make duplicate grants an actionable client error.
        if "duplicate" in str(exc).lower() or "e11000" in str(exc).lower():
            raise HTTPException(status_code=409, detail="A grant already exists for this resource and floor") from exc
        raise
    # A user with one or more grants is deliberately in custom-access mode.
    # Their next sign-in token carries this state and the server middleware
    # applies the grants as a default-deny allow-list.
    await db.users.update_one({"id": user_id}, {"$set": {"custom_access": True, "updated_at": utc_now_iso()}})
    await _revoke_grant_subject(user_id)
    grant.pop("_id", None)
    return grant


@router.delete("/{user_id}/{grant_id}")
async def delete_access_grant(
    user_id: str, grant_id: str, actor: UserPublic = Depends(require_min_role("admin")),
):
    target = await _target_user_or_404(user_id)
    await _assert_can_manage_target(actor, target)
    result = await db.access_grants.delete_one({"id": grant_id, "user_id": user_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Access grant not found")
    remaining = await db.access_grants.count_documents({"user_id": user_id})
    if remaining == 0:
        await db.users.update_one({"id": user_id}, {"$set": {"custom_access": False, "updated_at": utc_now_iso()}})
    await _revoke_grant_subject(user_id)
    return {"deleted": True, "id": grant_id}
