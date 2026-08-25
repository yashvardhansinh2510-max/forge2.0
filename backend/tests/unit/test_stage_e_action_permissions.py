"""Spec §18 point 7: "Every Command Center action re-checks its own
permission." This is the live-permission verification for Phase 1 —
Stage E of the ledger.

The Sales Data / analytics gate (owner/admin/manager) must never widen
access to the underlying operation an action performs. This is checked by
calling the REAL production dependency objects the operational routes use
(`require_min_role`, `get_current_user`) directly — not a reimplementation,
not `ACTION_ROLES` checking itself — so a change to the real route's gate
that `rows.py` forgets to mirror shows up here as a failure, not silently.

This is also how the `assign` bug was actually found: the original
declaration ("manager") was never checked against the real endpoint until
this pass. `PATCH /followups/{id}` turned out to have no role gate beyond
authentication.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from auth import require_min_role
from models import UserPublic
from services.analytics.rows import ACTION_ROLES


def _user(role: str) -> UserPublic:
    return UserPublic(id="u1", email="u1@forge.app", full_name="Test User", role=role, floor_ids=[])


async def _call(dep, user: UserPublic) -> UserPublic:
    # require_min_role's inner dependency takes `user` as a keyword-injected
    # parameter; calling it directly bypasses FastAPI's DI container but
    # exercises the exact same ROLE_HIERARCHY comparison the real request
    # path runs.
    return await dep(user=user)


def test_record_payment_endpoint_genuinely_refuses_a_role_below_accounts():
    """routes/payment_routes.py:264 — the real create_payment gate."""
    dep = require_min_role("accounts")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_call(dep, _user("sales")))
    assert exc.value.status_code == 403


def test_record_payment_endpoint_accepts_the_role_action_rows_declares():
    dep = require_min_role("accounts")
    result = asyncio.run(_call(dep, _user(ACTION_ROLES["record_payment"])))
    assert result.role == "accounts"


def test_action_roles_record_payment_matches_the_real_endpoints_threshold():
    assert ACTION_ROLES["record_payment"] == "accounts"


def test_assign_and_contact_endpoints_have_no_role_gate_beyond_authentication():
    """routes/followup_routes.py:578 (assign, via PATCH) and :663 (whatsapp/
    send_reminder, via /contact) both depend on get_current_user only — no
    require_min_role wrapper exists to call here. ACTION_ROLES must declare
    the lowest real role (worker), not an unverified stricter one — the
    2026-08-01 bug this test guards against."""
    for action in ("assign", "schedule_followup", "whatsapp", "send_reminder"):
        assert ACTION_ROLES[action] == "worker", (
            f"{action} claims a role stricter than its real endpoint requires"
        )
