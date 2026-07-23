"""Regression test pinning the role requirement on the three Chalan mutation
routes (generate/godown-received/dispatch) added for Ground Floor Tiles.

The role choice itself (`require_min_role("warehouse")`) already matches
`ROLE_CAPABILITIES["warehouse"]`, but nothing pinned it — same gap this
codebase already closed once for move/transfer in
test_purchases_move_permissions.py, extended here to the new routes so it
can't quietly regress to the wrong threshold.

Mirrors that file's approach: call each route function's own wired-in
`Depends(...)` dependency directly, so a regression that re-tightens or
loosens the threshold in `purchases_tracker.py` fails here even if
`require_min_role` itself is untouched.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from models import UserPublic
from routes import purchases_tracker


def _dependency_for(route_func, param_name="user"):
    depends = inspect.signature(route_func).parameters[param_name].default
    return depends.dependency


def _user(role: str) -> UserPublic:
    return UserPublic(email=f"{role}@forge.app", full_name=role.title(), role=role)


@pytest.mark.parametrize(
    "route_func",
    [
        purchases_tracker.generate_chalan,
        purchases_tracker.mark_chalan_godown_received,
        purchases_tracker.dispatch_chalan,
    ],
)
def test_warehouse_role_is_allowed_on_chalan_routes(route_func):
    dep = _dependency_for(route_func)
    warehouse_user = _user("warehouse")

    result = asyncio.run(dep(user=warehouse_user))

    assert result is warehouse_user


@pytest.mark.parametrize(
    "route_func",
    [
        purchases_tracker.generate_chalan,
        purchases_tracker.mark_chalan_godown_received,
        purchases_tracker.dispatch_chalan,
    ],
)
def test_worker_role_is_blocked_from_chalan_routes(route_func):
    dep = _dependency_for(route_func)
    worker_user = _user("worker")

    with pytest.raises(Exception) as exc:
        asyncio.run(dep(user=worker_user))

    assert getattr(exc.value, "status_code", None) == 403
