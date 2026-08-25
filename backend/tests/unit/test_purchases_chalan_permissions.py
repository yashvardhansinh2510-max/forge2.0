"""Regression tests pinning role and floor requirements on the three Chalan
mutation routes (generate/godown-received/dispatch) used by Sanitary orders.

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
from copy import deepcopy

import pytest

from models import UserPublic
from routes import purchases_tracker


def _dependency_for(route_func, param_name="user"):
    depends = inspect.signature(route_func).parameters[param_name].default
    return depends.dependency


def _user(role: str) -> UserPublic:
    return UserPublic(email=f"{role}@forge.app", full_name=role.title(), role=role)


def _floor_user(floor_id: str) -> UserPublic:
    return UserPublic(
        email="warehouse@forge.app", full_name="Warehouse", role="warehouse",
        floor_ids=[floor_id], active_floor_id=floor_id,
    )


class _UpdateResult:
    def __init__(self, matched_count: int):
        self.matched_count = matched_count


class _ScopedPurchaseOrders:
    def __init__(self, po: dict):
        self.po = deepcopy(po)
        self.update_calls = 0

    @staticmethod
    def _floor_ids(query: dict) -> list[str] | None:
        clauses = query.get("$and", [query])
        return next((clause["floor_id"]["$in"] for clause in clauses if "floor_id" in clause), None)

    async def find_one(self, query, *_args, **_kwargs):
        floor_ids = self._floor_ids(query)
        if floor_ids is not None and self.po["floor_id"] not in floor_ids:
            return None
        return deepcopy(self.po)

    async def update_one(self, *_args, **_kwargs):
        self.update_calls += 1
        return _UpdateResult(1)


class _Customers:
    async def find_one(self, *_args, **_kwargs):
        return {}


class _Db:
    def __init__(self, po: dict):
        self.purchase_orders = _ScopedPurchaseOrders(po)
        self.customers = _Customers()


def _po() -> dict:
    return {
        "id": "po-1", "number": "FPO-0001", "floor_id": "first-floor",
        "customer_id": "cust-1", "customer_name": "Customer", "created_by": "u-sales",
        "items": [{"id": "item-1", "name": "Basin", "qty": 1}],
        "chalans": [{
            "id": "ch-1", "number": "CH-0001", "stage": "released",
            "items": [{"po_item_id": "item-1", "name": "Basin", "qty": 1, "unit": "PCS"}],
        }],
    }


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


@pytest.mark.parametrize(
    "invoke",
    [
        lambda user: purchases_tracker.generate_chalan(
            "po-1",
            purchases_tracker.GenerateChalanBody(items=[
                purchases_tracker.ChalanItemInput(po_item_id="item-1", qty=1),
            ]),
            user=user,
        ),
        lambda user: purchases_tracker.mark_chalan_godown_received("po-1", "ch-1", user=user),
        lambda user: purchases_tracker.dispatch_chalan(
            "po-1", "ch-1", purchases_tracker.DispatchChalanBody(), user=user,
        ),
        lambda user: purchases_tracker.chalan_pdf("po-1", "ch-1", user=user),
    ],
)
def test_cross_floor_po_is_rejected_without_mutation(monkeypatch, invoke):
    fake_db = _Db(_po())
    monkeypatch.setattr(purchases_tracker, "db", fake_db)

    with pytest.raises(Exception) as exc:
        asyncio.run(invoke(_floor_user("ground-floor")))

    assert getattr(exc.value, "status_code", None) == 404
    assert fake_db.purchase_orders.update_calls == 0


@pytest.mark.parametrize(
    "invoke",
    [
        lambda user: purchases_tracker.mark_chalan_godown_received("po-1", "ch-unknown", user=user),
        lambda user: purchases_tracker.dispatch_chalan(
            "po-1", "ch-unknown", purchases_tracker.DispatchChalanBody(), user=user,
        ),
        lambda user: purchases_tracker.chalan_pdf("po-1", "ch-unknown", user=user),
    ],
)
def test_unauthorized_chalan_id_is_rejected_without_mutation(monkeypatch, invoke):
    fake_db = _Db(_po())
    monkeypatch.setattr(purchases_tracker, "db", fake_db)

    with pytest.raises(Exception) as exc:
        asyncio.run(invoke(_floor_user("first-floor")))

    assert getattr(exc.value, "status_code", None) == 404
    assert fake_db.purchase_orders.update_calls == 0


def test_insufficient_role_rejection_happens_before_any_route_mutation(monkeypatch):
    fake_db = _Db(_po())
    monkeypatch.setattr(purchases_tracker, "db", fake_db)
    dependency = _dependency_for(purchases_tracker.dispatch_chalan)

    with pytest.raises(Exception) as exc:
        asyncio.run(dependency(user=_user("worker")))

    assert getattr(exc.value, "status_code", None) == 403
    assert fake_db.purchase_orders.update_calls == 0
