"""GET /api/roles — single source of truth for the role list.

Every frontend screen that needs a list of assignable roles (Team's
"Assign role" picker, Settings > Roles & permissions) fetches this instead
of hardcoding role strings. If a role is ever renamed or a new one added,
it happens in one place (auth.ROLE_HIERARCHY / ROLE_LABELS / ROLE_CAPABILITIES)
and every screen picks it up automatically.
"""
from fastapi import APIRouter, Depends

from auth import ROLE_CAPABILITIES, ROLE_HIERARCHY, ROLE_LABELS, get_current_user
from models import UserPublic

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("")
async def list_roles(_: UserPublic = Depends(get_current_user)):
    """Any authenticated staff member can read the role list (needed just to
    render their own role's label) — only Team's mutating endpoints are
    admin-gated, this is read-only reference data."""
    return [
        {
            "role": role,
            "label": ROLE_LABELS.get(role, role.title()),
            "level": level,
            "capabilities": ROLE_CAPABILITIES.get(role, []),
        }
        for role, level in sorted(ROLE_HIERARCHY.items(), key=lambda kv: -kv[1])
    ]
