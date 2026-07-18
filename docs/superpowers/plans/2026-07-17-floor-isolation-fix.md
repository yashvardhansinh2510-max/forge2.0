# Floor Isolation Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop first-floor (sanitary) data from leaking onto the ground floor (and vice versa) across Purchases, Follow-ups, Reports, and Catalog, on both the read side (queries that never filtered by floor) and the write side (automation that creates new records without stamping their floor), then give Catalog a real floor concept and a `size` field so the ground-floor tile section can exist.

**Architecture:** Every fix reuses the one established pattern already correct elsewhere in this codebase: `floor_query(user, base)` / `floor_for_write(user)` from `backend/auth.py`, driven by the `X-Floor-Id` header the frontend already sends correctly. Reads get `floor_query()` applied to their Mongo filter. Human-initiated writes get `floor_id=floor_for_write(user)`. Automation-created writes (background event handlers with no live user context) inherit `floor_id` from their immediate source document instead.

**Tech Stack:** FastAPI + Motor (async MongoDB) backend, Expo/React Native Web frontend. Tests use the existing pattern in `backend/tests/unit/` — call the route's own async function directly with `asyncio.run(...)` and a `monkeypatch`-installed fake `db` object (see `test_purchases_tracker_concurrency.py` for the reference shape), no live server or live database required.

---

## Milestone A — Read paths that never apply floor scoping

### Task 1: Purchases Tracker main board (`_iter_items` + `GET /items`)

**Files:**
- Modify: `backend/routes/purchases_tracker.py:202-279` (`_iter_items`), `:454-475` (`list_items`)
- Test: `backend/tests/unit/test_purchases_tracker_floor_scoping.py` (new)

Current `_iter_items` signature takes no floor information at all:

```python
async def _iter_items(
    view: str,
    brand: Optional[str],
    customer: Optional[str],
    stage: Optional[str],
    q: Optional[str],
    sla_days: int,
    limit: int = 2000,
    product_id: Optional[str] = None,
) -> list[dict]:
    """Return a flat list of tracker rows across all POs, filtered."""
    match: dict = {"status": {"$ne": "cancelled"}}
```

And `list_items` discards the user:

```python
@router.get("/items")
async def list_items(
    view: str = Query("stock", regex="^(today|stock|customers|dispatch_record)$"),
    brand: Optional[str] = None,
    customer: Optional[str] = None,
    stage: Optional[str] = None,
    q: Optional[str] = None,
    product_id: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    _: UserPublic = Depends(get_current_user),
):
    """Flat tracker rows filtered by view/brand/customer/stage/q/product_id."""
    settings = await _load_settings()
    rows = await _iter_items(view, brand, customer, stage, q, settings.sla_days, limit, product_id)
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_purchases_tracker_floor_scoping.py`:

```python
"""Regression test: the Purchases Tracker read endpoints must never return
rows from a floor the caller isn't currently viewing. Root cause (2026-07-17
floor-isolation investigation): `_iter_items()` built its Mongo `$match`
with no floor filter at all, so every tracker view showed every floor's
purchase orders regardless of the selected floor."""
from __future__ import annotations

import asyncio

import pytest

from models import UserPublic
from routes import purchases_tracker as tracker


def _user(floor_id: str) -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=floor_id,
    )


class _FakeAggregateCursor:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    async def to_list(self, _n):
        return self._rows


class _FakePurchaseOrders:
    """Captures the pipeline passed to aggregate() instead of simulating
    real Mongo aggregation semantics — the thing under test is whether the
    floor filter is present in the $match stage, not Mongo's engine."""

    def __init__(self):
        self.last_pipeline: list[dict] | None = None

    def aggregate(self, pipeline):
        self.last_pipeline = pipeline
        return _FakeAggregateCursor([])


class _FakeDb:
    def __init__(self, purchase_orders: _FakePurchaseOrders):
        self.purchase_orders = purchase_orders


def test_iter_items_scopes_pipeline_to_the_active_floor(monkeypatch):
    fake_pos = _FakePurchaseOrders()
    monkeypatch.setattr(tracker, "db", _FakeDb(fake_pos))

    asyncio.run(tracker._iter_items(
        "stock", None, None, None, None, sla_days=7, limit=500,
        floor_ids=["ground-floor"],
    ))

    match_stage = fake_pos.last_pipeline[0]["$match"]
    assert match_stage.get("floor_id") == {"$in": ["ground-floor"]}


def test_iter_items_unscoped_when_floor_ids_is_none(monkeypatch):
    fake_pos = _FakePurchaseOrders()
    monkeypatch.setattr(tracker, "db", _FakeDb(fake_pos))

    asyncio.run(tracker._iter_items(
        "stock", None, None, None, None, sla_days=7, limit=500,
        floor_ids=None,
    ))

    match_stage = fake_pos.last_pipeline[0]["$match"]
    assert "floor_id" not in match_stage
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_purchases_tracker_floor_scoping.py -v`
Expected: FAIL — `TypeError: _iter_items() got an unexpected keyword argument 'floor_ids'`

- [ ] **Step 3: Write minimal implementation**

In `backend/routes/purchases_tracker.py`, change `_iter_items`'s signature and match-building:

```python
async def _iter_items(
    view: str,
    brand: Optional[str],
    customer: Optional[str],
    stage: Optional[str],
    q: Optional[str],
    sla_days: int,
    limit: int = 2000,
    product_id: Optional[str] = None,
    floor_ids: Optional[list[str]] = None,
) -> list[dict]:
    """Return a flat list of tracker rows across all POs, filtered."""
    match: dict = {"status": {"$ne": "cancelled"}}
    if floor_ids is not None:
        match["floor_id"] = {"$in": floor_ids}
```

Then update `list_items` to capture `user` and pass its floor scope through (using the same `accessible_floor_ids`/`active_floor_id` resolution `floor_query` uses internally, but as a plain list since `_iter_items` builds its own pipeline rather than taking a Mongo filter dict):

```python
@router.get("/items")
async def list_items(
    view: str = Query("stock", regex="^(today|stock|customers|dispatch_record)$"),
    brand: Optional[str] = None,
    customer: Optional[str] = None,
    stage: Optional[str] = None,
    q: Optional[str] = None,
    product_id: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    user: UserPublic = Depends(get_current_user),
):
    """Flat tracker rows filtered by view/brand/customer/stage/q/product_id."""
    settings = await _load_settings()
    rows = await _iter_items(
        view, brand, customer, stage, q, settings.sla_days, limit, product_id,
        floor_ids=floor_scope_ids(user),
    )
```

Add a `floor_scope_ids(user)` helper to `backend/auth.py` itself, alongside
`floor_query`/`floor_for_write`/`accessible_floor_ids` (this is used by both
`purchases_tracker.py` in this milestone and `catalog_routes.py` in
Milestone C, and both build their own pipelines/in-memory filters rather
than taking a Mongo filter dict, so it belongs next to its siblings in
`auth.py` rather than being copy-pasted into each route file separately):

```python
def floor_scope_ids(user: UserPublic) -> Optional[list[str]]:
    """Resolve the caller's floor filter the same way `floor_query()` does
    for Mongo-filter-based queries, but as a plain list — for callers that
    build their own aggregation pipeline or in-memory filter rather than
    taking a Mongo filter dict."""
    if user.active_floor_id:
        return [user.active_floor_id]
    return accessible_floor_ids(user)
```

Add a quick unit test alongside wherever `auth.py`'s existing behavior is
tested (or create `backend/tests/unit/test_auth_floor_scope_ids.py` if none
exists) to pin the two branches:

```python
from auth import floor_scope_ids
from models import UserPublic


def test_floor_scope_ids_returns_single_item_list_when_a_floor_is_active():
    user = UserPublic(email="x@forge.app", full_name="X", role="sales",
                       floor_ids=["ground-floor", "first-floor"], active_floor_id="ground-floor")
    assert floor_scope_ids(user) == ["ground-floor"]


def test_floor_scope_ids_falls_back_to_accessible_floor_ids_when_none_active():
    user = UserPublic(email="x@forge.app", full_name="X", role="owner", active_floor_id=None)
    assert floor_scope_ids(user) is None  # owners/managers: unscoped
```

Then, in `backend/routes/purchases_tracker.py`, import it instead of
redefining it locally:

```python
from auth import accessible_floor_ids, floor_scope_ids, get_current_user, require_min_role
```

(Add `floor_scope_ids` to whatever `from auth import ...` line already
exists in this file — don't create a second import line. `accessible_floor_ids`
only needs to stay in that import list if something else in this file still
calls it directly; otherwise drop it once `floor_scope_ids` is the only
caller.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_purchases_tracker_floor_scoping.py tests/unit/test_auth_floor_scope_ids.py -v`
Expected: PASS (4 tests total — 2 in each file)

- [ ] **Step 5: Commit**

```bash
git add backend/auth.py backend/routes/purchases_tracker.py backend/tests/unit/test_purchases_tracker_floor_scoping.py backend/tests/unit/test_auth_floor_scope_ids.py
git commit -m "fix: scope Purchases Tracker main board to the active floor"
```

### Task 2: Purchases Tracker facet endpoints (`/stages`, `/brands`, `/customers`)

**Files:**
- Modify: `backend/routes/purchases_tracker.py:285-344`
- Test: `backend/tests/unit/test_purchases_tracker_floor_scoping.py` (append)

All three currently discard `user` and build a pipeline with no floor filter:

```python
@router.get("/stages")
async def stage_catalog(_: UserPublic = Depends(get_current_user)):
    """Stage list with counts across ALL non-cancelled items."""
    pipeline = [
        {"$match": {"status": {"$ne": "cancelled"}}},
        {"$unwind": "$items"},
        {"$group": {"_id": {"$ifNull": ["$items.stage", "order_in_company"]}, "count": {"$sum": 1}}},
    ]
    rows = await db.purchase_orders.aggregate(pipeline).to_list(20)
```

```python
@router.get("/brands")
async def brand_facets(_: UserPublic = Depends(get_current_user)):
    """Brand list with counts of tracked items."""
    pipeline = [
        {"$match": {"status": {"$ne": "cancelled"}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": {"id": "$brand_id", "name": "$brand_name"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
    ]
    rows = await db.purchase_orders.aggregate(pipeline).to_list(50)
```

```python
@router.get("/customers")
async def customer_facets(_: UserPublic = Depends(get_current_user)):
    """Customers with open (non-delivered) tracked items."""
    pipeline = [
        {"$match": {"status": {"$ne": "cancelled"}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": {"id": "$customer_id", "name": "$customer_name"},
            "count": {"$sum": 1},
            "open": {"$sum": {"$cond": [{"$in": ["$items.stage", ["delivered"]]}, 0, 1]}},
        }},
        {"$sort": {"open": -1, "count": -1}},
    ]
    rows = await db.purchase_orders.aggregate(pipeline).to_list(500)
```

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_purchases_tracker_floor_scoping.py`:

```python
@pytest.mark.parametrize(
    "route_func",
    [tracker.stage_catalog, tracker.brand_facets, tracker.customer_facets],
)
def test_facet_endpoints_scope_pipeline_to_the_active_floor(monkeypatch, route_func):
    fake_pos = _FakePurchaseOrders()
    monkeypatch.setattr(tracker, "db", _FakeDb(fake_pos))

    asyncio.run(route_func(user=_user("ground-floor")))

    match_stage = fake_pos.last_pipeline[0]["$match"]
    assert match_stage.get("floor_id") == {"$in": ["ground-floor"]}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_purchases_tracker_floor_scoping.py -k facet_endpoints -v`
Expected: FAIL — `TypeError: stage_catalog() got an unexpected keyword argument 'user'` (the params are currently named `_`)

- [ ] **Step 3: Write minimal implementation**

```python
@router.get("/stages")
async def stage_catalog(user: UserPublic = Depends(get_current_user)):
    """Stage list with counts across ALL non-cancelled items on the caller's floor(s)."""
    match: dict = {"status": {"$ne": "cancelled"}}
    floor_ids = floor_scope_ids(user)
    if floor_ids is not None:
        match["floor_id"] = {"$in": floor_ids}
    pipeline = [
        {"$match": match},
        {"$unwind": "$items"},
        {"$group": {"_id": {"$ifNull": ["$items.stage", "order_in_company"]}, "count": {"$sum": 1}}},
    ]
    rows = await db.purchase_orders.aggregate(pipeline).to_list(20)
```

```python
@router.get("/brands")
async def brand_facets(user: UserPublic = Depends(get_current_user)):
    """Brand list with counts of tracked items on the caller's floor(s)."""
    match: dict = {"status": {"$ne": "cancelled"}}
    floor_ids = floor_scope_ids(user)
    if floor_ids is not None:
        match["floor_id"] = {"$in": floor_ids}
    pipeline = [
        {"$match": match},
        {"$unwind": "$items"},
        {"$group": {
            "_id": {"id": "$brand_id", "name": "$brand_name"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
    ]
    rows = await db.purchase_orders.aggregate(pipeline).to_list(50)
```

```python
@router.get("/customers")
async def customer_facets(user: UserPublic = Depends(get_current_user)):
    """Customers with open (non-delivered) tracked items on the caller's floor(s)."""
    match: dict = {"status": {"$ne": "cancelled"}}
    floor_ids = floor_scope_ids(user)
    if floor_ids is not None:
        match["floor_id"] = {"$in": floor_ids}
    pipeline = [
        {"$match": match},
        {"$unwind": "$items"},
        {"$group": {
            "_id": {"id": "$customer_id", "name": "$customer_name"},
            "count": {"$sum": 1},
            "open": {"$sum": {"$cond": [{"$in": ["$items.stage", ["delivered"]]}, 0, 1]}},
        }},
        {"$sort": {"open": -1, "count": -1}},
    ]
    rows = await db.purchase_orders.aggregate(pipeline).to_list(500)
```

The rest of each function body (turning `rows` into the response shape) is unchanged — only the pipeline's first `$match` stage and the `_: UserPublic` → `user: UserPublic` parameter rename change.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_purchases_tracker_floor_scoping.py -v`
Expected: PASS (5 tests total so far)

- [ ] **Step 5: Commit**

```bash
git add backend/routes/purchases_tracker.py backend/tests/unit/test_purchases_tracker_floor_scoping.py
git commit -m "fix: scope Purchases Tracker facet endpoints to the active floor"
```

### Task 3: Purchases Tracker remaining read endpoints

**Files:**
- Modify: `backend/routes/purchases_tracker.py` — `customer_workspace` (~347), `dispatch_record` (~478), `list_shortages` (~1286), `export_xlsx` (~1394), `get_item` (~492), `item_transfer_history` (~1015)
- Test: `backend/tests/unit/test_purchases_tracker_floor_scoping.py` (append)

`dispatch_record` and `export_xlsx` both call `_iter_items(...)` without the new `floor_ids` kwarg added in Task 1 — since it defaults to `None` (unscoped), they currently compile fine but stay unscoped until fixed here. `list_shortages` builds its own unscoped `query` dict. `customer_workspace`, `get_item`, and `item_transfer_history` all discard `user` entirely.

**`customer_workspace` note (self-review catch — this function is listed in Files above but was missing from the original Step 3 draft):** it's a large aggregate-everything-about-a-customer endpoint with SEVEN separate unscoped queries: `db.customers.find_one`, `_iter_items(...)` (missing the `floor_ids` kwarg), `db.purchase_orders.find`, `db.purchase_shortages.find`, `db.quotations.find`, `db.payments.find`, `db.followups.find`. Since these are all plain Mongo-filter `.find()`/`.find_one()` calls (not an aggregation pipeline), use `floor_query(user, base)` for each — add `floor_query` to the `from auth import ...` line alongside `floor_scope_ids`. The one call inside it that isn't touched: `timeline_for(customer_id=customer_id, limit=15)` (the activity feed) — this is a known, already-accepted separate gap (the global activity log's per-event floor tagging is explicitly out of scope everywhere in this codebase, tracked separately, not part of this plan).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_purchases_tracker_floor_scoping.py`:

```python
def test_customer_workspace_scopes_every_query_to_the_active_floor(monkeypatch):
    from auth import floor_query

    class _Recorder:
        def __init__(self, find_one_result=None):
            self._find_one_result = find_one_result
            self.last_query: dict | None = None

        async def find_one(self, query, *_args, **_kwargs):
            self.last_query = query
            return dict(self._find_one_result) if self._find_one_result else None

        def find(self, query, *_args, **_kwargs):
            self.last_query = query
            return self

        def sort(self, *_args, **_kwargs):
            return self

        async def to_list(self, _n):
            return []

    class _Db:
        customers = _Recorder(find_one_result={"id": "cust-1", "name": "Test"})
        purchase_orders = _Recorder()
        purchase_shortages = _Recorder()
        quotations = _Recorder()
        payments = _Recorder()
        followups = _Recorder()

    fake_db = _Db()
    monkeypatch.setattr(tracker, "db", fake_db)

    async def _fake_iter_items(*_args, **kwargs):
        assert kwargs.get("floor_ids") == ["ground-floor"]
        return []

    async def _fake_timeline_for(**_kwargs):
        return []

    monkeypatch.setattr(tracker, "_iter_items", _fake_iter_items)
    monkeypatch.setattr(tracker, "timeline_for", _fake_timeline_for)

    user = _user("ground-floor")
    asyncio.run(tracker.customer_workspace("cust-1", user=user))

    expected = floor_query(user, {}).get("floor_id")
    assert fake_db.customers.last_query.get("floor_id") == expected
    assert fake_db.purchase_orders.last_query.get("floor_id") == expected
    assert fake_db.purchase_shortages.last_query.get("floor_id") == expected
    assert fake_db.quotations.last_query.get("floor_id") == expected
    assert fake_db.payments.last_query.get("floor_id") == expected
    assert fake_db.followups.last_query.get("floor_id") == expected


def test_dispatch_record_scopes_to_the_active_floor(monkeypatch):
    fake_pos = _FakePurchaseOrders()
    monkeypatch.setattr(tracker, "db", _FakeDb(fake_pos))

    asyncio.run(tracker.dispatch_record(user=_user("ground-floor")))

    match_stage = fake_pos.last_pipeline[0]["$match"]
    assert match_stage.get("floor_id") == {"$in": ["ground-floor"]}


def test_export_xlsx_scopes_to_the_active_floor(monkeypatch):
    fake_pos = _FakePurchaseOrders()
    monkeypatch.setattr(tracker, "db", _FakeDb(fake_pos))

    asyncio.run(tracker.export_xlsx(user=_user("ground-floor")))

    match_stage = fake_pos.last_pipeline[0]["$match"]
    assert match_stage.get("floor_id") == {"$in": ["ground-floor"]}


class _FakeShortages:
    def __init__(self):
        self.last_query: dict | None = None

    def find(self, query, *_args, **_kwargs):
        self.last_query = query
        return self

    def sort(self, *_args, **_kwargs):
        return self

    async def to_list(self, _n):
        return []


def test_list_shortages_scopes_to_the_active_floor(monkeypatch):
    fake_shortages = _FakeShortages()

    class _Db:
        purchase_shortages = fake_shortages

    monkeypatch.setattr(tracker, "db", _Db())

    asyncio.run(tracker.list_shortages(user=_user("ground-floor")))

    assert fake_shortages.last_query.get("floor_id") == {"$in": ["ground-floor"]}


class _FakeSinglePo:
    def __init__(self, po: dict | None):
        self._po = po

    async def find_one(self, *_args, **_kwargs):
        return dict(self._po) if self._po else None


def test_get_item_404s_when_item_is_on_a_different_floor(monkeypatch):
    class _Db:
        purchase_orders = _FakeSinglePo({"id": "po-1", "floor_id": "first-floor", "items": []})

    monkeypatch.setattr(tracker, "db", _Db())

    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.get_item("item-1", user=_user("ground-floor")))
    assert getattr(exc.value, "status_code", None) == 404


def test_item_transfer_history_404s_when_item_is_on_a_different_floor(monkeypatch):
    class _Db:
        purchase_orders = _FakeSinglePo({"id": "po-1", "floor_id": "first-floor"})

    monkeypatch.setattr(tracker, "db", _Db())

    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.item_transfer_history("item-1", user=_user("ground-floor")))
    assert getattr(exc.value, "status_code", None) == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_purchases_tracker_floor_scoping.py -k "customer_workspace or dispatch_record or export_xlsx or list_shortages or get_item or item_transfer_history" -v`
Expected: FAIL — `customer_workspace()`/`dispatch_record()`/`export_xlsx()`/`list_shortages()`/`get_item()`/`item_transfer_history()` currently take `_: UserPublic`, not `user=`, so these fail with a `TypeError` on the keyword argument.

- [ ] **Step 3: Write minimal implementation**

`customer_workspace` (currently — showing only the lines that change; the summary-building logic in between, and the final `return {...}` block, are unchanged):

```python
@router.get("/customers/{customer_id}/workspace")
async def customer_workspace(customer_id: str, _: UserPublic = Depends(get_current_user)):
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    settings = await _load_settings()
    rows = await _iter_items("stock", None, customer_id, None, None, settings.sla_days, limit=2000)
    pos = await db.purchase_orders.find({"customer_id": customer_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    ...
    shortages = await db.purchase_shortages.find(
        {"customer_id": customer_id, "status": "awaiting_reorder"}, {"_id": 0},
    ).sort("created_at", -1).to_list(100)

    order_quotes = await db.quotations.find(
        {"customer_id": customer_id, "status": {"$in": ["ordered", "won"]}},
        {"_id": 0, "id": 1, "grand_total": 1},
    ).to_list(500)
    ...
    payments = await db.payments.find({"customer_id": customer_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    followups = await db.followups.find(
        {"customer_id": customer_id, "status": {"$in": ["open", "snoozed"]}}, {"_id": 0},
    ).sort("due_at", 1).to_list(100)
```

becomes:

```python
@router.get("/customers/{customer_id}/workspace")
async def customer_workspace(customer_id: str, user: UserPublic = Depends(get_current_user)):
    customer = await db.customers.find_one(floor_query(user, {"id": customer_id}), {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    settings = await _load_settings()
    rows = await _iter_items(
        "stock", None, customer_id, None, None, settings.sla_days, limit=2000,
        floor_ids=floor_scope_ids(user),
    )
    pos = await db.purchase_orders.find(floor_query(user, {"customer_id": customer_id}), {"_id": 0}).sort("created_at", -1).to_list(200)
    ...
    shortages = await db.purchase_shortages.find(
        floor_query(user, {"customer_id": customer_id, "status": "awaiting_reorder"}), {"_id": 0},
    ).sort("created_at", -1).to_list(100)

    order_quotes = await db.quotations.find(
        floor_query(user, {"customer_id": customer_id, "status": {"$in": ["ordered", "won"]}}),
        {"_id": 0, "id": 1, "grand_total": 1},
    ).to_list(500)
    ...
    payments = await db.payments.find(floor_query(user, {"customer_id": customer_id}), {"_id": 0}).sort("created_at", -1).to_list(100)
    followups = await db.followups.find(
        floor_query(user, {"customer_id": customer_id, "status": {"$in": ["open", "snoozed"]}}), {"_id": 0},
    ).sort("due_at", 1).to_list(100)
```

(The `...` in both blocks marks unchanged lines in between — `total_value`/`outstanding_rows`/`brand_map`/`stage_counts`/`activity = await timeline_for(...)` and everything else stays exactly as it is today.) Add `floor_query` to the `from auth import ...` line alongside `floor_scope_ids` (currently `from auth import floor_scope_ids, get_current_user, require_min_role`).

`dispatch_record` (currently):

```python
@router.get("/dispatch-record")
async def dispatch_record(
    brand: Optional[str] = None,
    customer: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    _: UserPublic = Depends(get_current_user),
):
    settings = await _load_settings()
    rows = await _iter_items("dispatch_record", brand, customer, None, q, settings.sla_days, limit)
    return {"count": len(rows), "items": rows}
```

becomes:

```python
@router.get("/dispatch-record")
async def dispatch_record(
    brand: Optional[str] = None,
    customer: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    user: UserPublic = Depends(get_current_user),
):
    settings = await _load_settings()
    rows = await _iter_items(
        "dispatch_record", brand, customer, None, q, settings.sla_days, limit,
        floor_ids=floor_scope_ids(user),
    )
    return {"count": len(rows), "items": rows}
```

`export_xlsx` (currently):

```python
@router.get("/export.xlsx")
async def export_xlsx(
    view: str = Query("stock", regex="^(today|stock|customers|dispatch_record)$"),
    brand: Optional[str] = None,
    customer: Optional[str] = None,
    stage: Optional[str] = None,
    q: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    settings = await _load_settings()
    rows = await _iter_items(view, brand, customer, stage, q, settings.sla_days, limit=2000)
```

becomes:

```python
@router.get("/export.xlsx")
async def export_xlsx(
    view: str = Query("stock", regex="^(today|stock|customers|dispatch_record)$"),
    brand: Optional[str] = None,
    customer: Optional[str] = None,
    stage: Optional[str] = None,
    q: Optional[str] = None,
    user: UserPublic = Depends(get_current_user),
):
    settings = await _load_settings()
    rows = await _iter_items(
        view, brand, customer, stage, q, settings.sla_days, limit=2000,
        floor_ids=floor_scope_ids(user),
    )
```

`list_shortages` (currently):

```python
@router.get("/shortages")
async def list_shortages(
    customer_id: Optional[str] = None,
    status_filter: str = Query("awaiting_reorder", alias="status"),
    limit: int = Query(200, ge=1, le=1000),
    _: UserPublic = Depends(get_current_user),
):
    query: dict = {}
    if status_filter and status_filter != "all":
        query["status"] = status_filter
    if customer_id:
        query["customer_id"] = customer_id
    docs = await db.purchase_shortages.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"count": len(docs), "items": docs}
```

becomes:

```python
@router.get("/shortages")
async def list_shortages(
    customer_id: Optional[str] = None,
    status_filter: str = Query("awaiting_reorder", alias="status"),
    limit: int = Query(200, ge=1, le=1000),
    user: UserPublic = Depends(get_current_user),
):
    query: dict = {}
    if status_filter and status_filter != "all":
        query["status"] = status_filter
    if customer_id:
        query["customer_id"] = customer_id
    floor_ids = floor_scope_ids(user)
    if floor_ids is not None:
        query["floor_id"] = {"$in": floor_ids}
    docs = await db.purchase_shortages.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"count": len(docs), "items": docs}
```

`get_item` and `item_transfer_history` (currently just discard `user`, no
floor check at all on the item's own PO). `get_item` currently:

```python
@router.get("/items/{item_id}")
async def get_item(item_id: str, _: UserPublic = Depends(get_current_user)):
    po = await db.purchase_orders.find_one({"items.id": item_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Item not found")
    it = next((i for i in po.get("items", []) if i.get("id") == item_id), None)
    if not it:
        raise HTTPException(status_code=404, detail="Item not found")
    settings = await _load_settings()
    row = _flatten_item(po, it, settings.sla_days)
    row["stage_history"] = it.get("stage_history") or []
    row["po_status"] = po.get("status")
    return row
```

becomes:

```python
@router.get("/items/{item_id}")
async def get_item(item_id: str, user: UserPublic = Depends(get_current_user)):
    po = await db.purchase_orders.find_one({"items.id": item_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Item not found")
    floor_ids = floor_scope_ids(user)
    if floor_ids is not None and po.get("floor_id") not in floor_ids:
        raise HTTPException(status_code=404, detail="Item not found")
    it = next((i for i in po.get("items", []) if i.get("id") == item_id), None)
    if not it:
        raise HTTPException(status_code=404, detail="Item not found")
    settings = await _load_settings()
    row = _flatten_item(po, it, settings.sla_days)
    row["stage_history"] = it.get("stage_history") or []
    row["po_status"] = po.get("status")
    return row
```

(The floor check uses the same 404 rather than 403 so a restricted-floor
user can't distinguish "doesn't exist" from "exists on a floor you can't
see".)

`item_transfer_history` currently:

```python
@router.get("/items/{item_id}/transfer-history")
async def item_transfer_history(item_id: str, _: UserPublic = Depends(get_current_user)):
    return {"item_id": item_id, "transfers": await transfer_history(item_id)}
```

`transfer_history(item_id)` (in `services/transfer_workflow.py:276`) queries
the `purchase_transfers` journal directly by item id, with no floor
awareness of its own — so the floor check has to happen in the route, the
same way as `get_item`, by independently resolving the item's own PO first:

```python
@router.get("/items/{item_id}/transfer-history")
async def item_transfer_history(item_id: str, user: UserPublic = Depends(get_current_user)):
    po = await db.purchase_orders.find_one({"items.id": item_id}, {"_id": 0, "floor_id": 1})
    if not po:
        raise HTTPException(status_code=404, detail="Item not found")
    floor_ids = floor_scope_ids(user)
    if floor_ids is not None and po.get("floor_id") not in floor_ids:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"item_id": item_id, "transfers": await transfer_history(item_id)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_purchases_tracker_floor_scoping.py -v`
Expected: PASS (11 tests total so far)

- [ ] **Step 5: Commit**

```bash
git add backend/routes/purchases_tracker.py backend/tests/unit/test_purchases_tracker_floor_scoping.py
git commit -m "fix: scope remaining Purchases Tracker read endpoints to the active floor"
```

### Task 4: Follow-ups `/insights`

**Files:**
- Modify: `backend/routes/followup_routes.py:186-210`
- Test: `backend/tests/unit/test_followups_floor_scoping.py` (new)

Current code (fully unscoped, four raw queries):

```python
@router.get("/insights")
async def insights(_: UserPublic = Depends(get_current_user)):
    start, end = ist_day_bounds_utc(0)
    rng = {"$gte": start.isoformat(), "$lt": end.isoformat()}

    calls = await db.activity_events.count_documents({"event_type": "followup.call_logged", "created_at": rng})
    whatsapps = await db.activity_events.count_documents({
        "event_type": "followup.contacted", "payload.channel": "whatsapp", "created_at": rng,
    })
    pay_docs = await db.payments.find({"paid_at": rng}, {"_id": 0, "amount": 1}).to_list(1000)
    payments_collected = sum(p.get("amount", 0) for p in pay_docs)
    quotations_approved = await db.quotations.count_documents({
        "status": {"$in": ["approved", "won"]}, "updated_at": rng,
    })
    completed_today = await db.followups.count_documents({"completed_at": rng})
    still_open = await db.followups.count_documents({"status": {"$in": ["open", "snoozed"]}})
    response_rate = round(100 * completed_today / max(1, completed_today + still_open))
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_followups_floor_scoping.py`:

```python
"""Regression test: /followups/insights must scope every count to the
caller's active floor. It previously ran four raw, unscoped queries, so the
insights panel always showed global (in practice, 100% first-floor) numbers
regardless of which floor was selected."""
from __future__ import annotations

import asyncio

import pytest

from auth import floor_query
from models import UserPublic
from routes import followup_routes as followups


def _user(floor_id: str) -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=floor_id,
    )


class _Recorder:
    """Generic fake collection: records the filter passed to whichever
    method is called and returns a value shaped for that method."""

    def __init__(self, count_result: int = 0, find_result: list | None = None):
        self.count_result = count_result
        self.find_result = find_result or []
        self.last_count_filter: dict | None = None
        self.last_find_filter: dict | None = None

    async def count_documents(self, query):
        self.last_count_filter = query
        return self.count_result

    def find(self, query, *_args, **_kwargs):
        self.last_find_filter = query
        return self

    async def to_list(self, _n):
        return self.find_result


class _FakeDb:
    def __init__(self):
        self.activity_events = _Recorder()
        self.payments = _Recorder(find_result=[])
        self.quotations = _Recorder()
        self.followups = _Recorder()


def test_insights_scopes_every_query_to_the_active_floor(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(followups, "db", fake_db)

    asyncio.run(followups.insights(user=_user("ground-floor")))

    expected = floor_query(_user("ground-floor"), {}).get("floor_id")
    assert fake_db.activity_events.last_count_filter.get("floor_id") == expected
    assert fake_db.payments.last_find_filter.get("floor_id") == expected
    assert fake_db.quotations.last_count_filter.get("floor_id") == expected
    # followups.count_documents is called twice (completed_today, still_open) —
    # last_count_filter only captures the final call, which is enough to prove
    # the floor filter reaches this collection too.
    assert fake_db.followups.last_count_filter.get("floor_id") == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_followups_floor_scoping.py -v`
Expected: FAIL — `TypeError: insights() got an unexpected keyword argument 'user'`

- [ ] **Step 3: Write minimal implementation**

```python
@router.get("/insights")
async def insights(user: UserPublic = Depends(get_current_user)):
    start, end = ist_day_bounds_utc(0)
    rng = {"$gte": start.isoformat(), "$lt": end.isoformat()}

    calls = await db.activity_events.count_documents(
        floor_query(user, {"event_type": "followup.call_logged", "created_at": rng})
    )
    whatsapps = await db.activity_events.count_documents(floor_query(user, {
        "event_type": "followup.contacted", "payload.channel": "whatsapp", "created_at": rng,
    }))
    pay_docs = await db.payments.find(
        floor_query(user, {"paid_at": rng}), {"_id": 0, "amount": 1},
    ).to_list(1000)
    payments_collected = sum(p.get("amount", 0) for p in pay_docs)
    quotations_approved = await db.quotations.count_documents(floor_query(user, {
        "status": {"$in": ["approved", "won"]}, "updated_at": rng,
    }))
    completed_today = await db.followups.count_documents(floor_query(user, {"completed_at": rng}))
    still_open = await db.followups.count_documents(
        floor_query(user, {"status": {"$in": ["open", "snoozed"]}})
    )
    response_rate = round(100 * completed_today / max(1, completed_today + still_open))
```

`floor_query` is already imported at the top of `followup_routes.py` (it's used by `_all_with_bucket` already) — no new import needed. The rest of the function (building and returning the response dict) is unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_followups_floor_scoping.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routes/followup_routes.py backend/tests/unit/test_followups_floor_scoping.py
git commit -m "fix: scope /followups/insights to the active floor"
```

### Task 5: Reports overview

**Files:**
- Modify: `backend/routes/misc_routes.py:283-293`
- Test: `backend/tests/unit/test_reports_floor_scoping.py` (new)

Current code:

```python
@router.get("/reports/overview")
async def reports_overview(_: UserPublic = Depends(get_current_user)):
    quotations = await db.quotations.find({}, {"_id": 0}).to_list(2000)
    by_status: dict[str, int] = {}
    revenue_by_month: dict[str, float] = {}
    for q in quotations:
        by_status[q.get("status", "draft")] = by_status.get(q.get("status", "draft"), 0) + 1
        if q.get("status") == "won":
            month = (q.get("updated_at") or "")[:7]
            if month:
                revenue_by_month[month] = revenue_by_month.get(month, 0) + q.get("grand_total", 0)
    return {"by_status": by_status, "revenue_by_month": revenue_by_month}
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_reports_floor_scoping.py`:

```python
"""Regression test: /reports/overview must only aggregate the caller's own
floor's quotations. It previously ran `db.quotations.find({}, ...)` with no
filter at all."""
from __future__ import annotations

import asyncio

from auth import floor_query
from models import UserPublic
from routes import misc_routes


def _user(floor_id: str) -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=floor_id,
    )


class _FakeQuotations:
    def __init__(self):
        self.last_query: dict | None = None

    def find(self, query, *_args, **_kwargs):
        self.last_query = query
        return self

    async def to_list(self, _n):
        return []


class _FakeDb:
    def __init__(self):
        self.quotations = _FakeQuotations()


def test_reports_overview_scopes_to_the_active_floor(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(misc_routes, "db", fake_db)

    asyncio.run(misc_routes.reports_overview(user=_user("ground-floor")))

    expected = floor_query(_user("ground-floor"), {}).get("floor_id")
    assert fake_db.quotations.last_query.get("floor_id") == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_reports_floor_scoping.py -v`
Expected: FAIL — `TypeError: reports_overview() got an unexpected keyword argument 'user'`

- [ ] **Step 3: Write minimal implementation**

```python
@router.get("/reports/overview")
async def reports_overview(user: UserPublic = Depends(get_current_user)):
    quotations = await db.quotations.find(floor_query(user, {}), {"_id": 0}).to_list(2000)
    by_status: dict[str, int] = {}
    revenue_by_month: dict[str, float] = {}
    for q in quotations:
        by_status[q.get("status", "draft")] = by_status.get(q.get("status", "draft"), 0) + 1
        if q.get("status") == "won":
            month = (q.get("updated_at") or "")[:7]
            if month:
                revenue_by_month[month] = revenue_by_month.get(month, 0) + q.get("grand_total", 0)
    return {"by_status": by_status, "revenue_by_month": revenue_by_month}
```

Check the top of `backend/routes/misc_routes.py` for `from auth import ...` and add `floor_query` to that existing import line if it isn't already there (it wasn't needed by this file before).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_reports_floor_scoping.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routes/misc_routes.py backend/tests/unit/test_reports_floor_scoping.py
git commit -m "fix: scope /reports/overview to the active floor"
```

### Task 6: Dashboard `followups_due` counter

**Files:**
- Modify: `backend/routes/dashboard_routes.py:59-64`
- Test: `backend/tests/unit/test_dashboard_floor_scoping.py` (new)

Current code:

```python
    # follow-ups due today for the logged-in user
    today_end = (now + timedelta(days=1)).isoformat()
    followups_due = await db.followups.count_documents({
        "status": "open",
        "due_at": {"$lte": today_end},
        "assigned_to": user.id,
    })
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_dashboard_floor_scoping.py`:

```python
"""Regression test: /dashboard/stats' followups_due counter must respect the
active floor, not just assigned_to. (The main quotations/customers queries in
this endpoint were already correctly scoped — this covers the one field that
wasn't.)"""
from __future__ import annotations

import asyncio

from auth import floor_query
from models import UserPublic
from routes import dashboard_routes


def _user(floor_id: str) -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales", id="user-1",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=floor_id,
    )


class _Recorder:
    def __init__(self):
        self.last_find_filter: dict | None = None
        self.last_count_filter: dict | None = None

    def find(self, query, *_args, **_kwargs):
        self.last_find_filter = query
        return self

    async def to_list(self, _n):
        return []

    async def count_documents(self, query):
        self.last_count_filter = query
        return 0


class _FakeDb:
    def __init__(self):
        self.quotations = _Recorder()
        self.customers = _Recorder()
        self.products = _Recorder()
        self.followups = _Recorder()


def test_followups_due_scopes_to_the_active_floor(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(dashboard_routes, "db", fake_db)

    asyncio.run(dashboard_routes.dashboard_stats(user=_user("ground-floor")))

    expected = floor_query(_user("ground-floor"), {}).get("floor_id")
    assert fake_db.followups.last_count_filter.get("floor_id") == expected
    assert fake_db.followups.last_count_filter.get("assigned_to") == "user-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_dashboard_floor_scoping.py -v`
Expected: FAIL — `assert None == {'$in': ['ground-floor']}` (no `floor_id` key present yet)

- [ ] **Step 3: Write minimal implementation**

```python
    # follow-ups due today for the logged-in user
    today_end = (now + timedelta(days=1)).isoformat()
    followups_due = await db.followups.count_documents(floor_query(user, {
        "status": "open",
        "due_at": {"$lte": today_end},
        "assigned_to": user.id,
    }))
```

`floor_query` is already imported at the top of `dashboard_routes.py` (used two lines above for `quotations`/`customers`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_dashboard_floor_scoping.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routes/dashboard_routes.py backend/tests/unit/test_dashboard_floor_scoping.py
git commit -m "fix: scope dashboard's followups_due counter to the active floor"
```

---

## Milestone B — Write paths that never stamp `floor_id` on derived records

Rule used throughout this milestone: **automation/event-handler-created
records inherit `floor_id` from their immediate source document**
(`quotation.get("floor_id", "first-floor")`, `source_po.get("floor_id",
"first-floor")`, etc.) — never `floor_for_write(user)`, since these handlers
often only have an actor id/name string, and semantically a record derived
from a ground-floor source must stay ground-floor regardless of which floor
the triggering user happens to have selected.

### Task 7: `domain_outbox.py::_handle_order_placed` — the quotation→PO+Payment automation

**Files:**
- Modify: `backend/services/domain_outbox.py` (`_handle_order_placed`, the `PurchaseOrder(...)` and `Payment(...)` constructions)
- Test: `backend/tests/unit/test_domain_outbox_floor_inheritance.py` (new)

This is the automation that fires whenever a quotation is placed: it builds
one `PurchaseOrder` per brand group plus a pending `Payment`. Neither
currently sets `floor_id`, so both silently default to `"first-floor"`
regardless of the quotation's real floor.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_domain_outbox_floor_inheritance.py`:

```python
"""Regression test: automated records created by the quotation-placed
automation must inherit floor_id from the source quotation, not silently
default to first-floor. Root cause: `_handle_order_placed` built
PurchaseOrder/Payment without ever reading `quotation.get("floor_id")`."""
from __future__ import annotations

import asyncio

import services.domain_outbox as domain_outbox


class _Recorder:
    def __init__(self, find_one_result=None):
        self._find_one_result = find_one_result
        self.inserted: list[dict] = []
        self.upserts: list[dict] = []

    async def find_one(self, *_args, **_kwargs):
        return self._find_one_result

    def find(self, *_args, **_kwargs):
        return self

    async def to_list(self, _n):
        return []

    async def insert_one(self, doc, **_kwargs):
        self.inserted.append(doc)

    async def update_one(self, _query, update, *, upsert=False, **_kwargs):
        if upsert and "$setOnInsert" in update:
            self.upserts.append(update["$setOnInsert"])


def _quotation(floor_id: str) -> dict:
    return {
        "id": "q-1", "number": "FQ-2026-0001", "customer_id": "cust-1",
        "customer_name": "Test Customer", "project_name": None,
        "grand_total": 1000.0, "floor_id": floor_id,
        "items": [{
            "id": "line-1", "product_id": "prod-1", "sku": "SKU-1", "name": "Tile A",
            "image": None, "finish": None, "category_id": "cat-1", "room": None,
            "qty": 10.0, "unit_price": 100.0, "discount_pct": None,
        }],
    }


def test_order_placed_purchase_order_and_payment_inherit_quotation_floor(monkeypatch):
    quotation = _quotation("ground-floor")

    class _FakeDb:
        quotations = _Recorder(find_one_result=quotation)
        products = _Recorder()
        brands = _Recorder()
        suppliers = _Recorder()
        purchase_orders = _Recorder()
        payments = _Recorder()
        activity_events = _Recorder()

    fake_db = _FakeDb()
    monkeypatch.setattr(domain_outbox, "db", fake_db)

    event = {
        "id": "evt-1", "idempotency_key": "order-placed:q-1",
        "payload": {"quotation_id": "q-1"},
        "actor_id": "user-1", "actor_name": "Sales",
    }
    asyncio.run(domain_outbox._handle_order_placed(event, session=None))

    assert fake_db.purchase_orders.inserted, "expected at least one PurchaseOrder to be inserted"
    for po in fake_db.purchase_orders.inserted:
        assert po["floor_id"] == "ground-floor"
    assert fake_db.payments.upserts, "expected a pending Payment to be upserted"
    assert fake_db.payments.upserts[0]["floor_id"] == "ground-floor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_domain_outbox_floor_inheritance.py -v`
Expected: FAIL — `KeyError: 'floor_id'` (neither the inserted PO dict nor the payment upsert dict has the key yet)

- [ ] **Step 3: Write minimal implementation**

In `_handle_order_placed`, find the `po = PurchaseOrder(...)` construction and add `floor_id=quotation.get("floor_id", "first-floor")`:

```python
        po = PurchaseOrder(
            number=await _next_po_number(session), quotation_id=quotation_id, quotation_number=quotation.get("number"),
            customer_id=quotation["customer_id"], customer_name=quotation.get("customer_name", ""), project_name=quotation.get("project_name"),
            brand_id=group["brand_id"], brand_name=group["brand_name"], supplier_id=supplier.get("id"), supplier_name=supplier.get("name"),
            status="draft", items=po_items, subtotal=round(sum(item.qty * item.unit_cost for item in po_items), 2),
            grand_total=round(sum(item.qty * item.unit_cost for item in po_items), 2), created_by=event["actor_id"], created_by_name=event["actor_name"],
            floor_id=quotation.get("floor_id", "first-floor"),
            status_history=[PurchaseStatusEvent(from_status=None, to_status="draft", by_user_id=event["actor_id"], by_user_name=event["actor_name"], note=f"Created from {quotation.get('number')}")],
        ).dict()
```

And the `payment = Payment(...)` construction immediately below it:

```python
    payment_key = f"{key}:payment"
    payment = Payment(
        quotation_id=quotation_id, quotation_number=quotation.get("number"), customer_id=quotation["customer_id"], customer_name=quotation.get("customer_name"),
        amount=round(float(quotation.get("grand_total") or 0), 2), mode="bank", status="pending", note="Outstanding balance created by OrderPlaced automation.",
        recorded_by=event["actor_id"], recorded_by_name=event["actor_name"],
        floor_id=quotation.get("floor_id", "first-floor"),
    ).dict()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_domain_outbox_floor_inheritance.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/domain_outbox.py backend/tests/unit/test_domain_outbox_floor_inheritance.py
git commit -m "fix: order-placed automation inherits floor_id from the source quotation"
```

### Task 8: `domain_outbox.py::_upsert_followup`

**Files:**
- Modify: `backend/services/domain_outbox.py` (`_upsert_followup`)
- Test: `backend/tests/unit/test_domain_outbox_floor_inheritance.py` (append)

Current code:

```python
async def _upsert_followup(*, key: str, quotation: dict, reason: str, category: str, session: Any) -> None:
    customer = await db.customers.find_one({"id": quotation["customer_id"]}, {"_id": 0}, session=session) or {}
    followup = Followup(
        source_key=key,
        rule_type="manual",
        category=category,  # type: ignore[arg-type]
        customer_id=quotation["customer_id"],
        customer_name=quotation.get("customer_name", ""),
        customer_phone=customer.get("phone"),
        customer_tier=customer.get("tier", "retail"),
        quotation_id=quotation["id"],
        quotation_number=quotation.get("number"),
        project_name=quotation.get("project_name"),
        value=round(float(quotation.get("grand_total") or 0), 2),
        reason=reason,
        next_action="Review with customer",
        next_action_reason="Created by the quotation workflow.",
        suggested_channel="call",
        due_at=now_iso(),
        is_automated=False,
    ).dict()
```

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_domain_outbox_floor_inheritance.py`:

```python
def test_upsert_followup_inherits_quotation_floor(monkeypatch):
    class _FakeDb:
        customers = _Recorder(find_one_result={"phone": "555", "tier": "retail"})
        followups = _Recorder()

    fake_db = _FakeDb()
    monkeypatch.setattr(domain_outbox, "db", fake_db)

    asyncio.run(domain_outbox._upsert_followup(
        key="k1", quotation=_quotation("ground-floor"), reason="test", category="quotation", session=None,
    ))

    assert fake_db.followups.upserts[0]["floor_id"] == "ground-floor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_domain_outbox_floor_inheritance.py -k upsert_followup -v`
Expected: FAIL — `KeyError: 'floor_id'`

- [ ] **Step 3: Write minimal implementation**

```python
async def _upsert_followup(*, key: str, quotation: dict, reason: str, category: str, session: Any) -> None:
    customer = await db.customers.find_one({"id": quotation["customer_id"]}, {"_id": 0}, session=session) or {}
    followup = Followup(
        source_key=key,
        rule_type="manual",
        category=category,  # type: ignore[arg-type]
        customer_id=quotation["customer_id"],
        customer_name=quotation.get("customer_name", ""),
        customer_phone=customer.get("phone"),
        customer_tier=customer.get("tier", "retail"),
        quotation_id=quotation["id"],
        quotation_number=quotation.get("number"),
        project_name=quotation.get("project_name"),
        value=round(float(quotation.get("grand_total") or 0), 2),
        reason=reason,
        next_action="Review with customer",
        next_action_reason="Created by the quotation workflow.",
        suggested_channel="call",
        due_at=now_iso(),
        is_automated=False,
        floor_id=quotation.get("floor_id", "first-floor"),
    ).dict()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_domain_outbox_floor_inheritance.py -v`
Expected: PASS (all tests in this file)

- [ ] **Step 5: Commit**

```bash
git add backend/services/domain_outbox.py backend/tests/unit/test_domain_outbox_floor_inheritance.py
git commit -m "fix: quotation-generated follow-up automation inherits floor_id"
```

### Task 9: `followup_engine.py` rule-based auto-follow-up engine

**Files:**
- Modify: `backend/services/followup_engine.py:229-243` (`upsert` closure inside `reconcile_followups`)
- Test: `backend/tests/unit/test_followup_engine_floor_inheritance.py` (new)

Current `desired[key] = {...}` dict never includes `floor_id`, even though
`quotation`/`purchase` (whichever is passed) are full raw documents that
already carry it.

This function is a nested closure inside `reconcile_followups()`, and that
outer function touches five collections (`followups`, `customers`,
`quotations`, `purchase_orders`, `purchase_shortages`) — faking the whole
orchestrator just to test one dict field would be heavy and brittle.
Instead, extract the floor-inheritance decision into a tiny module-level
helper (mirroring the `_transfer_floor_id` / `_source_floor_id` pattern
already used in Tasks 10 and 12), so it's directly unit-testable without
running the orchestrator at all.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_followup_engine_floor_inheritance.py`:

```python
"""Regression test: the rule-based auto-follow-up engine must inherit
floor_id from whichever source document (quotation or purchase) triggered
the rule, instead of silently defaulting to first-floor on every
automated card."""
from __future__ import annotations

from services.followup_engine import _followup_floor_id


def test_inherits_from_quotation_when_present():
    assert _followup_floor_id(
        quotation={"floor_id": "ground-floor"}, purchase=None,
    ) == "ground-floor"


def test_inherits_from_purchase_when_no_quotation():
    assert _followup_floor_id(
        quotation=None, purchase={"floor_id": "ground-floor"},
    ) == "ground-floor"


def test_defaults_to_first_floor_when_neither_present():
    assert _followup_floor_id(quotation=None, purchase=None) == "first-floor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_followup_engine_floor_inheritance.py -v`
Expected: FAIL — `ImportError: cannot import name '_followup_floor_id'`

- [ ] **Step 3: Write minimal implementation**

Add the helper near the top of `services/followup_engine.py`, alongside the other module-level helpers (e.g. right before `build_whatsapp_message`):

```python
def _followup_floor_id(quotation: Optional[dict], purchase: Optional[dict]) -> str:
    """Automated follow-ups inherit floor_id from whichever source document
    triggered the rule — never a hardcoded default that would silently mix
    floors once ground-floor quotations/purchases exist."""
    return (quotation or purchase or {}).get("floor_id", "first-floor")
```

Then, inside `upsert(...)`'s `desired[key] = {...}` dict, add one line calling it:

```python
        desired[key] = {
            "rule_type": rule_type, "category": category,
            "customer_id": customer["id"],
            "customer_name": customer.get("company") or customer.get("name"),
            "customer_phone": customer.get("phone"), "customer_tier": tier,
            "quotation_id": quotation.get("id") if quotation else None,
            "quotation_number": quotation.get("number") if quotation else None,
            "purchase_id": purchase.get("id") if purchase else None,
            "purchase_number": purchase.get("number") if purchase else None,
            "project_name": (quotation or {}).get("project_name"),
            "value": round(value, 2), "reason": reason, "reason_factors": factors,
            "next_action": next_action, "next_action_reason": next_action_reason,
            "suggested_channel": channel, "priority_score": score, "priority_level": level,
            "tags": tags or [], "due_at": due_at or now_iso(),
            "floor_id": _followup_floor_id(quotation, purchase),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_followup_engine_floor_inheritance.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/followup_engine.py backend/tests/unit/test_followup_engine_floor_inheritance.py
git commit -m "fix: rule-based auto-follow-up engine inherits floor_id from its source record"
```

### Task 10: `transfer_workflow.py::execute_transfer` — Quotation + PurchaseOrder

**Files:**
- Modify: `backend/services/transfer_workflow.py` (`execute_transfer`'s `quote`/`destination_po`/`transfer` constructions, roughly lines 128-186)
- Test: `backend/tests/unit/test_transfer_workflow_floor_inheritance.py` (new)

This is the modern transactional customer-transfer command (`POST
/purchases-tracker/items/{id}/transfer`). It has `source_po` (the original
PO, fetched fresh with no field restriction, so `floor_id` is present)
available directly in scope. Add `floor_id=source_po.get("floor_id",
"first-floor")` to both the `quote` and `destination_po` constructions, and
also stamp it onto the `transfer` journal dict so the later async event
handler (Task 11) can read it back.

- [ ] **Step 1: Write the failing test**

Because `execute_transfer` runs inside a real Mongo transaction
(`client.start_session()` / `session.start_transaction()`), faking it fully
is disproportionate for a unit test. Instead, test the narrower, directly
reachable unit: a small helper this task also introduces,
`_transfer_floor_id(source_po: dict) -> str`, extracted so the inheritance
rule itself is unit-testable without faking a whole transaction.

Create `backend/tests/unit/test_transfer_workflow_floor_inheritance.py`:

```python
"""Regression test: every record created by a customer transfer must inherit
floor_id from the source purchase order, not silently default to
first-floor."""
from __future__ import annotations

from services.transfer_workflow import _transfer_floor_id


def test_transfer_floor_id_inherits_from_source_po():
    assert _transfer_floor_id({"floor_id": "ground-floor"}) == "ground-floor"


def test_transfer_floor_id_defaults_when_source_po_missing_field():
    assert _transfer_floor_id({}) == "first-floor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_transfer_workflow_floor_inheritance.py -v`
Expected: FAIL — `ImportError: cannot import name '_transfer_floor_id'`

- [ ] **Step 3: Write minimal implementation**

Add the helper near the top of `backend/services/transfer_workflow.py`, right after `now_iso()`:

```python
def _transfer_floor_id(source_po: dict) -> str:
    """Every record a transfer creates (destination quotation, destination
    PO, shortage, payment, follow-up) stays on the SOURCE PO's floor — a
    transfer moves stock between customers, not between floors."""
    return source_po.get("floor_id", "first-floor")
```

Then use it in the `quote = Quotation(...)` construction:

```python
            quote = Quotation(
                number=await _next_number("quotations", "FQ", session), customer_id=destination["id"],
                customer_name=destination_name, status="ordered", items=[quote_line], rooms=[source_item.get("room")] if source_item.get("room") else [],
                subtotal=round(quote_line.net, 2), grand_total=round(quote_line.net, 2),
                notes=f"Transfer from {source_name} · {source_po.get('number')}" + (f" — {reason}" if reason else ""),
                created_by=user.id, created_by_name=user.full_name, source="transfer",
                floor_id=_transfer_floor_id(source_po),
            )
```

And in the `destination_po = PurchaseOrder(...)` construction:

```python
            destination_po = PurchaseOrder(
                number=await _next_number("purchase_orders", "FPO", session), quotation_id=quote.id, quotation_number=quote.number,
                customer_id=destination["id"], customer_name=destination_name, brand_id=destination_item.brand_id, brand_name=destination_item.brand_name,
                supplier_id=source_po.get("supplier_id"), supplier_name=source_po.get("supplier_name"), status="draft", items=[destination_item],
                internal_notes=f"Transfer {transfer_id} from {source_po.get('number')} · {source_name}" + (f" — {reason}" if reason else ""),
                subtotal=round(destination_item.qty * destination_item.unit_cost, 2), grand_total=round(destination_item.qty * destination_item.unit_cost, 2),
                created_by=user.id, created_by_name=user.full_name,
                floor_id=_transfer_floor_id(source_po),
                status_history=[PurchaseStatusEvent(from_status=None, to_status="draft", by_user_id=user.id, by_user_name=user.full_name, note="Created by customer transfer")],
            )
```

And add `"floor_id": _transfer_floor_id(source_po),` to the `transfer = {...}` journal dict (so `handle_purchase_transferred` can read it back in Task 11):

```python
            transfer = {
                "id": transfer_id, "idempotency_key": command_key, "source_po_id": source_po["id"], "source_po_number": source_po.get("number"),
                "source_item_id": item_id, "source_customer_id": source_customer_id, "source_customer_name": source_name,
                "source_quotation_id": source_quotation_id, "source_quotation_line_id": source_quotation_line_id,
                "destination_po_id": destination_po.id, "destination_po_number": destination_po.number, "destination_item_id": destination_item_id,
                "destination_customer_id": destination["id"], "destination_customer_name": destination_name, "destination_quotation_id": quote.id,
                "destination_quotation_number": quote.number, "product_id": source_item["product_id"], "sku": source_item["sku"], "name": source_item["name"],
                "image": source_item.get("image"), "brand_id": destination_item.brand_id, "brand_name": destination_item.brand_name, "room": source_item.get("room"),
                "qty": float(qty), "source_qty_before": source_qty, "source_remaining_qty": max(0, source_remaining), "reason": reason,
                "created_customer": created_customer, "actor_id": user.id, "actor_name": user.full_name, "created_at": now, "updated_at": now,
                "floor_id": _transfer_floor_id(source_po),
            }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_transfer_workflow_floor_inheritance.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/transfer_workflow.py backend/tests/unit/test_transfer_workflow_floor_inheritance.py
git commit -m "fix: customer transfer inherits floor_id from the source purchase order"
```

### Task 11: `transfer_workflow.py::handle_purchase_transferred` — Shortage + Payment + Followup

**Files:**
- Modify: `backend/services/transfer_workflow.py` (`handle_purchase_transferred`)
- Test: `backend/tests/unit/test_transfer_workflow_floor_inheritance.py` (append)

This is the async event handler that fires after `execute_transfer`
commits. It only has the persisted `transfer` journal document (now
carrying `floor_id` since Task 10), not a live `user`. Read
`transfer.get("floor_id")` and stamp it onto the `PurchaseShortage`,
`Payment`, and `Followup` it creates.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_transfer_workflow_floor_inheritance.py`:

```python
def test_transfer_floor_id_reads_back_from_transfer_journal():
    # handle_purchase_transferred reads transfer.get("floor_id") the same
    # way execute_transfer writes it via _transfer_floor_id — this pins that
    # contract so the two don't drift apart.
    transfer = {"floor_id": "ground-floor"}
    assert transfer.get("floor_id", "first-floor") == "ground-floor"
```

(This is a thin contract-pinning test rather than a full simulation of
`handle_purchase_transferred`, which needs a real Mongo session; the
meaningful coverage is Step 3's actual code change plus manual verification
in Step 4 of this milestone's rollout — see the Testing note at the end of
this plan.)

- [ ] **Step 2: Run test to verify it fails**

This particular test can't fail against old code (it doesn't call
production code) — skip straight to Step 3. Its purpose is documentation of
intent, not a red/green gate.

- [ ] **Step 3: Write minimal implementation**

In `handle_purchase_transferred`, add `floor_id=transfer.get("floor_id", "first-floor")` to all three constructions:

```python
            if missing > 1e-6:
                shortage = PurchaseShortage(
                    customer_id=transfer["source_customer_id"], customer_name=transfer["source_customer_name"], quotation_id=source_quote_id,
                    quotation_number=(original_quote or {}).get("number"), quotation_line_id=source_line_id, product_id=transfer["product_id"], sku=transfer["sku"], name=transfer["name"], image=transfer.get("image"),
                    committed_qty=committed, allocated_qty=allocated, shortage_qty=missing, status="awaiting_reorder",
                    reason=f"{transfer['qty']:g} unit(s) transferred to {transfer['destination_customer_name']} — {missing:g} unit(s) need re-order.",
                    transferred_to_customer_id=transfer["destination_customer_id"], transferred_to_customer_name=transfer["destination_customer_name"],
                    floor_id=transfer.get("floor_id", "first-floor"),
                ).dict()
```

```python
    payment = Payment(
        quotation_id=transfer["destination_quotation_id"], quotation_number=transfer["destination_quotation_number"], customer_id=transfer["destination_customer_id"], customer_name=transfer["destination_customer_name"],
        amount=round(float(dest_quote.get("grand_total") or 0), 2), mode="bank", status="pending", note=f"Pending balance from transfer {transfer['id']}", recorded_by=event["actor_id"], recorded_by_name=event["actor_name"],
        floor_id=transfer.get("floor_id", "first-floor"),
    ).dict()
```

```python
    followup = Followup(
        source_key=f"{key}:followup", rule_type="manual", category="purchase", customer_id=transfer["destination_customer_id"], customer_name=transfer["destination_customer_name"], customer_phone=destination_customer.get("phone"), customer_tier=destination_customer.get("tier", "retail"),
        quotation_id=transfer["destination_quotation_id"], quotation_number=transfer["destination_quotation_number"], purchase_id=transfer["destination_po_id"], purchase_number=transfer["destination_po_number"],
        value=payment["amount"], reason=f"Transferred {transfer['qty']:g} × {transfer['name']} received from {transfer['source_customer_name']}.", next_action="Confirm transfer and payment plan", next_action_reason="Transfer-specific operational follow-up.", suggested_channel="call", due_at=now_iso(), is_automated=False,
        floor_id=transfer.get("floor_id", "first-floor"),
    ).dict()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_transfer_workflow_floor_inheritance.py -v`
Expected: PASS (3 tests total in this file)

- [ ] **Step 5: Commit**

```bash
git add backend/services/transfer_workflow.py backend/tests/unit/test_transfer_workflow_floor_inheritance.py
git commit -m "fix: transfer-completed automation inherits floor_id from the transfer journal"
```

### Task 12: Legacy inline transfer/reorder code in `purchases_tracker.py`

**Files:**
- Modify: `backend/routes/purchases_tracker.py` — `_reconcile_shortage_for_line` (~912), `transfer_item` legacy route (~1022, its `auto_quotation`/`dest_po`), `create_po_for_shortage` (~1302, its `new_po`)
- Test: `backend/tests/unit/test_purchases_tracker_write_floor_inheritance.py` (new)

Three gaps, same shape as Milestone B so far:

1. `_reconcile_shortage_for_line` builds `PurchaseShortage(**fields)` from a
   `fields` dict with no `floor_id`, even though it already has `q` (the
   source quotation, fetched with no field restriction) in scope.
2. The **legacy** `transfer_item` route (`POST
   /legacy/items/{item_id}/transfer` — kept alongside the modern
   `execute_transfer` path) builds `auto_quotation = Quotation(...)` and
   `dest_po = PurchaseOrder(...)` with no `floor_id`, even though `po` (the
   source PO) is already in scope.
3. `create_po_for_shortage` builds `new_po = PurchaseOrder(...)` with no
   `floor_id`, even though `s` (the shortage doc) is already in scope.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_purchases_tracker_write_floor_inheritance.py`:

```python
"""Regression test: every record the legacy transfer/reorder code paths in
purchases_tracker.py create must inherit floor_id from their source
document, matching the rule applied to the modern transfer_workflow.py path
and the domain_outbox.py automation."""
from __future__ import annotations

from routes.purchases_tracker import _source_floor_id


def test_source_floor_id_inherits_present_value():
    assert _source_floor_id({"floor_id": "ground-floor"}) == "ground-floor"


def test_source_floor_id_defaults_when_missing():
    assert _source_floor_id({}) == "first-floor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_purchases_tracker_write_floor_inheritance.py -v`
Expected: FAIL — `ImportError: cannot import name '_source_floor_id'`

- [ ] **Step 3: Write minimal implementation**

Add the helper near the top of `purchases_tracker.py`, alongside the `floor_scope_ids` import added in Task 1:

```python
def _source_floor_id(source: dict) -> str:
    """Same inheritance rule as transfer_workflow._transfer_floor_id — a
    record derived from an existing PO/quotation/shortage stays on that
    source's floor."""
    return source.get("floor_id", "first-floor")
```

In `_reconcile_shortage_for_line`, add `"floor_id": _source_floor_id(q),` to the `fields` dict:

```python
        fields = {
            "customer_id": customer_id, "customer_name": customer_name,
            "quotation_id": quotation_id, "quotation_number": q.get("number"),
            "quotation_line_id": quotation_line_id,
            "product_id": product_id, "sku": sku, "name": name, "image": image,
            "committed_qty": committed_qty, "allocated_qty": allocated_qty, "shortage_qty": shortage_qty,
            "status": "awaiting_reorder", "reason": reason,
            "transferred_to_customer_id": dest_customer_id, "transferred_to_customer_name": dest_customer_name,
            "updated_at": now,
            "floor_id": _source_floor_id(q),
        }
```

In the legacy `transfer_item`, add `floor_id=_source_floor_id(po),` to both `auto_quotation` and `dest_po`:

```python
    auto_quotation = Quotation(
        number=auto_quotation_number,
        customer_id=body.new_customer_id,
        customer_name=new_cust.get("company") or new_cust.get("name"),
        status="ordered",
        items=[auto_line],
        subtotal=round(auto_line.net, 2),
        grand_total=round(auto_line.net, 2),
        notes=(
            f"Auto-created by transfer — {body.qty:g} × {it['name']} from "
            f"{po.get('customer_name')} ({po.get('number')})"
            + (f" — {body.reason}" if body.reason else "")
        ),
        created_by=user.id, created_by_name=user.full_name,
        source="transfer",
        floor_id=_source_floor_id(po),
    )
```

```python
    dest_po = PurchaseOrder(
        number=number,
        quotation_id=auto_quotation.id,
        quotation_number=auto_quotation.number,
        customer_id=body.new_customer_id,
        customer_name=new_cust.get("company") or new_cust.get("name"),
        brand_id=it.get("brand_id") or po.get("brand_id"),
        brand_name=it.get("brand_name") or po.get("brand_name"),
        supplier_id=po.get("supplier_id"),
        supplier_name=po.get("supplier_name"),
        status="draft",
        items=[dest_item],
        internal_notes=(
            f"Transferred from {po.get('number')} · "
            f"{po.get('customer_name')}" + (f" — {body.reason}" if body.reason else "")
        ),
        subtotal=round(dest_item.qty * dest_item.unit_cost, 2),
        grand_total=round(dest_item.qty * dest_item.unit_cost, 2),
        created_by=user.id,
        created_by_name=user.full_name,
        floor_id=_source_floor_id(po),
        status_history=[
            PurchaseStatusEvent(
                from_status=None, to_status="draft",
                by_user_id=user.id, by_user_name=user.full_name,
                note=f"Customer transfer from {po.get('number')}",
            ).dict()
        ],
    )
```

In `create_po_for_shortage`, add `floor_id=_source_floor_id(s),` to `new_po`:

```python
    new_po = PurchaseOrder(
        number=number,
        quotation_id=s.get("quotation_id"), quotation_number=s.get("quotation_number"),
        customer_id=s["customer_id"], customer_name=s["customer_name"],
        status="draft", items=[item],
        internal_notes=f"Reorder — {s.get('reason')}",
        subtotal=0, grand_total=0,
        created_by=user.id, created_by_name=user.full_name,
        floor_id=_source_floor_id(s),
        status_history=[
            PurchaseStatusEvent(
                from_status=None, to_status="draft",
                by_user_id=user.id, by_user_name=user.full_name,
                note="Created from a shortage recommendation",
            ).dict()
        ],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_purchases_tracker_write_floor_inheritance.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routes/purchases_tracker.py backend/tests/unit/test_purchases_tracker_write_floor_inheritance.py
git commit -m "fix: legacy transfer/reorder code paths inherit floor_id from their source document"
```

### Task 13: Follow-up call-back rescheduling (`POST /{followup_id}/log-call`)

**Files:**
- Modify: `backend/routes/followup_routes.py:601-631` (`log_call`)
- Test: `backend/tests/unit/test_followups_floor_scoping.py` (append)

Current code (the sibling manual-create endpoint earlier in this same file
already does this correctly — this one was missed) — full function:

```python
@router.post("/{followup_id}/log-call")
async def log_call(followup_id: str, body: FollowupCallOutcomePayload, user: UserPublic = Depends(get_current_user)):
    f = await db.followups.find_one({"id": followup_id}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    now_dt = datetime.now(timezone.utc)
    patch: dict = {
        "last_contacted_at": now_dt.isoformat(), "updated_at": now_iso(),
        "notes": body.notes if body.notes is not None else f.get("notes"),
    }
    next_created = None

    if body.outcome in ("interested", "call_back"):
        patch.update({"status": "done", "completed_at": now_iso(), "completed_outcome": body.outcome})
        due = now_dt + timedelta(days=1 if body.outcome == "call_back" else 2)
        nf = Followup(
            rule_type="manual", category=f.get("category", "general"),
            customer_id=f["customer_id"], customer_name=f["customer_name"], customer_phone=f.get("customer_phone"),
            customer_tier=f.get("customer_tier", "retail"), quotation_id=f.get("quotation_id"),
            quotation_number=f.get("quotation_number"), purchase_id=f.get("purchase_id"),
            purchase_number=f.get("purchase_number"), value=f.get("value", 0),
            reason=("Call back requested" if body.outcome == "call_back" else "Customer interested — follow up on their decision"),
            reason_factors=[f.get("reason", "")] if f.get("reason") else [],
            next_action="Call customer", next_action_reason="Scheduled automatically from the previous call outcome.",
            suggested_channel="call", priority_score=f.get("priority_score", 50), priority_level=f.get("priority_level", "medium"),
            due_at=due.isoformat(), is_automated=False,
            assigned_to=f.get("assigned_to") or user.id, assigned_to_name=f.get("assigned_to_name") or user.full_name,
            tags=f.get("tags", []),
        )
        await db.followups.insert_one(nf.dict())
        next_created = nf.id
```

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_followups_floor_scoping.py`:

```python
class _FakeFollowups:
    def __init__(self, existing: dict):
        self._existing = existing
        self.inserted: list[dict] = []

    async def find_one(self, *_args, **_kwargs):
        return dict(self._existing)

    async def insert_one(self, doc):
        self.inserted.append(doc)

    async def update_one(self, *_args, **_kwargs):
        pass


def test_log_call_reschedule_inherits_source_followup_floor(monkeypatch):
    from models import FollowupCallOutcomePayload

    fake_followups = _FakeFollowups({
        "id": "f-1", "customer_id": "cust-1", "customer_name": "Test Customer",
        "floor_id": "ground-floor",
    })

    class _Db:
        followups = fake_followups

    monkeypatch.setattr(followups, "db", _Db())

    asyncio.run(followups.log_call(
        "f-1", FollowupCallOutcomePayload(outcome="call_back"), user=_user("ground-floor"),
    ))

    assert fake_followups.inserted[0]["floor_id"] == "ground-floor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_followups_floor_scoping.py -k log_call -v`
Expected: FAIL — `KeyError: 'floor_id'` (the inserted follow-up dict has no `floor_id` key yet)

- [ ] **Step 3: Write minimal implementation**

```python
        nf = Followup(
            rule_type="manual", category=f.get("category", "general"),
            customer_id=f["customer_id"], customer_name=f["customer_name"], customer_phone=f.get("customer_phone"),
            customer_tier=f.get("customer_tier", "retail"), quotation_id=f.get("quotation_id"),
            quotation_number=f.get("quotation_number"), purchase_id=f.get("purchase_id"),
            purchase_number=f.get("purchase_number"), value=f.get("value", 0),
            reason=("Call back requested" if body.outcome == "call_back" else "Customer interested — follow up on their decision"),
            reason_factors=[f.get("reason", "")] if f.get("reason") else [],
            next_action="Call customer", next_action_reason="Scheduled automatically from the previous call outcome.",
            suggested_channel="call", priority_score=f.get("priority_score", 50), priority_level=f.get("priority_level", "medium"),
            due_at=due.isoformat(), is_automated=False,
            assigned_to=f.get("assigned_to") or user.id, assigned_to_name=f.get("assigned_to_name") or user.full_name,
            tags=f.get("tags", []),
            floor_id=f.get("floor_id", "first-floor"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_followups_floor_scoping.py -v`
Expected: PASS (all tests in this file)

- [ ] **Step 5: Commit**

```bash
git add backend/routes/followup_routes.py backend/tests/unit/test_followups_floor_scoping.py
git commit -m "fix: follow-up call-back rescheduling inherits floor_id from the source follow-up"
```

---

## Milestone C — Catalog floor isolation + tile-ready schema

### Task 14: Add `floor_id` to `Brand`/`Category` + backfill migration

**Files:**
- Modify: `backend/models.py:245-256` (`Brand`, `Category`)
- Create: `backend/migrations/0004_backfill_brand_category_floor_id.py`
- Test: `backend/tests/unit/test_migration_0004.py` (new)

Current models:

```python
class Brand(TimestampedModel):
    name: str
    slug: str
    logo_url: Optional[str] = None
    country: Optional[str] = None


class Category(TimestampedModel):
    name: str
    slug: str
    parent_id: Optional[str] = None
    icon: Optional[str] = None
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_migration_0004.py`:

```python
"""Migration 0004 must backfill floor_id="first-floor" onto every existing
brand/category doc (neither collection has the field at all pre-migration)."""
from __future__ import annotations

import asyncio
import importlib

# Module name starts with a digit (0004_...), which isn't a valid dotted
# `import a.b` target — importlib.import_module() resolves it fine at
# runtime by string, the same way migrations/runner.py's `_discover()`
# loads every numbered migration (`f"migrations.{name}"`).
migration = importlib.import_module("migrations.0004_backfill_brand_category_floor_id")


class _FakeCollection:
    def __init__(self, docs: list[dict]):
        self.docs = docs
        self.update_many_calls: list[tuple[dict, dict]] = []

    async def update_many(self, query, update):
        self.update_many_calls.append((query, update))
        matched = 0
        for doc in self.docs:
            if all(doc.get(k) is None if v == {"$exists": False} else True for k, v in query.items()):
                doc.update(update.get("$set", {}))
                matched += 1
        return type("Result", (), {"modified_count": matched})()


class _FakeDb:
    def __init__(self):
        self.brands = _FakeCollection([{"id": "b1", "name": "Hansgrohe"}])
        self.categories = _FakeCollection([{"id": "c1", "name": "Faucets"}])


def test_migration_backfills_first_floor_on_brands_and_categories():
    fake_db = _FakeDb()
    asyncio.run(migration.up(fake_db))

    assert fake_db.brands.docs[0]["floor_id"] == "first-floor"
    assert fake_db.categories.docs[0]["floor_id"] == "first-floor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_migration_0004.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'migrations.0004_backfill_brand_category_floor_id'` (file doesn't exist yet)

- [ ] **Step 3: Write minimal implementation**

Add to `backend/models.py`:

```python
class Brand(TimestampedModel):
    name: str
    slug: str
    logo_url: Optional[str] = None
    country: Optional[str] = None
    floor_id: str = "first-floor"


class Category(TimestampedModel):
    name: str
    slug: str
    parent_id: Optional[str] = None
    icon: Optional[str] = None
    floor_id: str = "first-floor"
```

Create `backend/migrations/0004_backfill_brand_category_floor_id.py` (following the same docstring-first style as the existing migrations):

```python
"""Brand and Category never had a floor_id field at all (2026-07-17
floor-isolation investigation — this is why the ground-floor tile section
and the first-floor sanitary catalog couldn't be told apart at the
brand/category level). Every existing brand/category belongs to the
first-floor sanitary catalog, so backfill that value explicitly rather than
leaving the field to Pydantic's model default silently covering for it —
an explicit stored value survives a future change to that default."""
from __future__ import annotations


async def up(db) -> None:
    await db.brands.update_many(
        {"floor_id": {"$exists": False}}, {"$set": {"floor_id": "first-floor"}},
    )
    await db.categories.update_many(
        {"floor_id": {"$exists": False}}, {"$set": {"floor_id": "first-floor"}},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_migration_0004.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/migrations/0004_backfill_brand_category_floor_id.py backend/tests/unit/test_migration_0004.py
git commit -m "feat: add floor_id to Brand/Category with a backfill migration"
```

### Task 15: Floor-scope the in-memory catalog engine

**Files:**
- Modify: `backend/services/catalog_service.py` — `_matches_filters` (~377), `list_products_page` (~424), `list_brands_with_counts` (~490), `list_categories_with_counts` (~499), `hierarchy_rows` (~537), `list_family_groups` (~564), `facet_buckets` (~628), `search_catalog` (~662)
- Test: `backend/tests/unit/test_catalog_service_floor_scoping.py` (new)

`_matches_filters` currently has no `floor_ids` parameter at all:

```python
def _matches_filters(product: dict, *, brand_id: Optional[str], category_id: Optional[str],
                     subcategory: Optional[str], series: Optional[str], family_key: Optional[str],
                     finish: Optional[str], colour: Optional[str]) -> bool:
    expected = {
        "brand_id": brand_id,
        "category_id": category_id,
        "subcategory": subcategory,
        "series": series,
        "family_key": family_key,
        "finish": finish,
        "colour": colour,
    }
    return all(value is None or product.get(field) == value for field, value in expected.items())
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_catalog_service_floor_scoping.py`:

```python
"""Regression test: the in-memory catalog engine must respect floor
scoping. Root cause: _matches_filters (and every function built on it) had
no concept of floor_id at all, so switching floors never changed which
products/brands/categories the catalog returned."""
from __future__ import annotations

from services.catalog_service import _matches_filters


def _product(floor_id: str) -> dict:
    return {
        "brand_id": "b1", "category_id": "c1", "subcategory": None, "series": None,
        "family_key": None, "finish": None, "colour": None, "floor_id": floor_id,
    }


def test_matches_filters_scopes_by_floor_ids():
    ground = _product("ground-floor")
    first = _product("first-floor")
    kwargs = dict(brand_id=None, category_id=None, subcategory=None, series=None,
                  family_key=None, finish=None, colour=None)

    assert _matches_filters(ground, floor_ids=["ground-floor"], **kwargs) is True
    assert _matches_filters(first, floor_ids=["ground-floor"], **kwargs) is False


def test_matches_filters_unscoped_when_floor_ids_is_none():
    first = _product("first-floor")
    kwargs = dict(brand_id=None, category_id=None, subcategory=None, series=None,
                  family_key=None, finish=None, colour=None)

    assert _matches_filters(first, floor_ids=None, **kwargs) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_catalog_service_floor_scoping.py -v`
Expected: FAIL — `TypeError: _matches_filters() got an unexpected keyword argument 'floor_ids'`

- [ ] **Step 3: Write minimal implementation**

```python
def _matches_filters(product: dict, *, brand_id: Optional[str], category_id: Optional[str],
                     subcategory: Optional[str], series: Optional[str], family_key: Optional[str],
                     finish: Optional[str], colour: Optional[str],
                     floor_ids: Optional[list[str]] = None) -> bool:
    if floor_ids is not None and product.get("floor_id") not in floor_ids:
        return False
    expected = {
        "brand_id": brand_id,
        "category_id": category_id,
        "subcategory": subcategory,
        "series": series,
        "family_key": family_key,
        "finish": finish,
        "colour": colour,
    }
    return all(value is None or product.get(field) == value for field, value in expected.items())
```

Now thread `floor_ids` through every caller. `list_products_page`:

```python
async def list_products_page(
    *, user_id: str, q: Optional[str], brand_id: Optional[str], category_id: Optional[str],
    subcategory: Optional[str], series: Optional[str], family_key: Optional[str],
    finish: Optional[str], colour: Optional[str], sort: str, limit: int, skip: int,
    floor_ids: Optional[list[str]] = None,
) -> dict:
    snapshot = await get_catalog_snapshot()
    pattern = _compile_search(q)
    matching = [
        product for product in snapshot.products
        if _matches_filters(
            product, brand_id=brand_id, category_id=category_id,
            subcategory=subcategory, series=series, family_key=family_key,
            finish=finish, colour=colour, floor_ids=floor_ids,
        ) and _matches_search(product, pattern)
    ]
```

(The rest of the function body is unchanged — only the signature and the one `_matches_filters(...)` call above change.)

`list_brands_with_counts` — brands themselves now carry `floor_id` (Task 14), so filter the brand list itself, not just product counts:

```python
async def list_brands_with_counts(floor_ids: Optional[list[str]] = None) -> list[dict]:
    snapshot = await get_catalog_snapshot()
    counts = Counter(row.get("brand_id") for row in snapshot.products)
    brands = snapshot.brands if floor_ids is None else [
        b for b in snapshot.brands if b.get("floor_id") in floor_ids
    ]
    out = copy.deepcopy(list(brands))
    for row in out:
        row["product_count"] = counts.get(row.get("id"), 0)
    return out
```

`list_categories_with_counts` — same idea:

```python
async def list_categories_with_counts(brand_id: Optional[str], floor_ids: Optional[list[str]] = None) -> list[dict]:
    snapshot = await get_catalog_snapshot()
    counts = Counter(
        row.get("category_id") for row in snapshot.products
        if not brand_id or row.get("brand_id") == brand_id
    )
    out = []
    categories = snapshot.categories if floor_ids is None else [
        c for c in snapshot.categories if c.get("floor_id") in floor_ids
    ]
    for category in categories:
        count = counts.get(category.get("id"), 0)
        if brand_id and count == 0:
            continue
        row = copy.deepcopy(category)
        row["product_count"] = count
        out.append(row)
    return out
```

`hierarchy_rows` — filter the underlying products before grouping:

```python
async def hierarchy_rows(floor_ids: Optional[list[str]] = None) -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    snapshot = await get_catalog_snapshot()
    groups: dict[tuple, dict] = {}
    products = snapshot.products if floor_ids is None else [
        p for p in snapshot.products if p.get("floor_id") in floor_ids
    ]
    for product in products:
        key = (
            product.get("brand_id"), product.get("category_id"), product.get("subcategory"),
            product.get("series"), product.get("family_key"), product.get("family_name"),
        )
        row = groups.setdefault(key, {
            "_id": {
                "brand_id": key[0], "category_id": key[1], "subcategory": key[2],
                "series": key[3], "family_key": key[4], "family_name": key[5],
            },
            "product_count": 0,
            "min_price": float(product.get("price") or 0),
            "sample_image": (product.get("images") or [None])[0],
            "image_quality": product.get("image_quality"),
        })
        row["product_count"] += 1
        row["min_price"] = min(row["min_price"], float(product.get("price") or 0))
    return (
        list(groups.values()),
        {row["id"]: copy.deepcopy(row) for row in snapshot.brands},
        {row["id"]: copy.deepcopy(row) for row in snapshot.categories},
    )
```

`list_family_groups` — add `floor_ids` to its signature and to the `_matches_filters` call:

```python
async def list_family_groups(
    *, brand_id: Optional[str], category_id: Optional[str], subcategory: Optional[str],
    series: Optional[str], q: Optional[str], limit: int, skip: int,
    floor_ids: Optional[list[str]] = None,
) -> dict:
    snapshot = await get_catalog_snapshot()
    pattern = _compile_search(q)
    products = [
        row for row in snapshot.products
        if row.get("family_key")
        and _matches_filters(
            row, brand_id=brand_id, category_id=category_id, subcategory=subcategory,
            series=series, family_key=None, finish=None, colour=None, floor_ids=floor_ids,
        )
        and (pattern is None or any(pattern.search(str(row.get(field) or "")) for field in (
            "name", "family_name", "series", "subcategory", "finish", "colour", "sku",
        )))
    ]
```

`facet_buckets` — add `floor_ids` to its signature and to the `_matches_filters` call inside:

```python
async def facet_buckets(
    *, brand_id: Optional[str], category_id: Optional[str], subcategory: Optional[str],
    series: Optional[str], floor_ids: Optional[list[str]] = None,
) -> dict:
    snapshot = await get_catalog_snapshot()
    products = [
        row for row in snapshot.products
        if _matches_filters(
            row, brand_id=brand_id, category_id=category_id, subcategory=subcategory,
            series=series, family_key=None, finish=None, colour=None, floor_ids=floor_ids,
        )
    ]
```

`search_catalog` — same pattern:

```python
async def search_catalog(
    *, q: str, brand_id: Optional[str], category_id: Optional[str], subcategory: Optional[str],
    series: Optional[str], limit: int, group: bool, floor_ids: Optional[list[str]] = None,
) -> dict:
    snapshot = await get_catalog_snapshot()
    query = (q or "").strip()
    q_lower = query.lower()
    products = [
        row for row in snapshot.products
        if _matches_filters(
            row, brand_id=brand_id, category_id=category_id, subcategory=subcategory,
            series=series, family_key=None, finish=None, colour=None, floor_ids=floor_ids,
        )
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_catalog_service_floor_scoping.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/catalog_service.py backend/tests/unit/test_catalog_service_floor_scoping.py
git commit -m "feat: thread floor scoping through the in-memory catalog engine"
```

### Task 16: Thread floor scope through Catalog routes; fix product creation defaults

**Files:**
- Modify: `backend/routes/catalog_routes.py` — `list_brands`, `list_categories`, `catalog_hierarchy`, `list_products`, `list_families`, `catalog_search`, `catalog_facets`, `create_product`, `create_custom_product`
- Test: `backend/tests/unit/test_catalog_routes_floor_scoping.py` (new)

Import `floor_scope_ids` and `floor_for_write` at the top of `catalog_routes.py` — this is the same helper added to `backend/auth.py` in Task 1, reused here rather than redefined:

```python
from auth import floor_for_write, floor_scope_ids, get_current_user, require_min_role
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_catalog_routes_floor_scoping.py`:

```python
"""Regression test: Catalog read routes must pass the caller's floor scope
into the catalog engine instead of discarding the user entirely."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import routes.catalog_routes as catalog_routes
from models import UserPublic


def _user(floor_id: str) -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=floor_id,
    )


def test_list_brands_passes_floor_scope_ids(monkeypatch):
    fake = AsyncMock(return_value=[])
    monkeypatch.setattr(catalog_routes.catalog_service, "list_brands_with_counts", fake)

    asyncio.run(catalog_routes.list_brands(user=_user("ground-floor")))

    fake.assert_awaited_once_with(floor_ids=["ground-floor"])


def test_catalog_search_passes_floor_scope_ids(monkeypatch):
    fake = AsyncMock(return_value={"query": "", "total": 0, "grouped": False, "items": []})
    monkeypatch.setattr(catalog_routes.catalog_service, "search_catalog", fake)

    asyncio.run(catalog_routes.catalog_search(user=_user("ground-floor")))

    _, kwargs = fake.await_args
    assert kwargs["floor_ids"] == ["ground-floor"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_catalog_routes_floor_scoping.py -v`
Expected: FAIL — `TypeError: list_brands() got an unexpected keyword argument 'user'` (currently named `_`)

- [ ] **Step 3: Write minimal implementation**

```python
@router.get("/brands")
async def list_brands(user: UserPublic = Depends(get_current_user)):
    """Return every brand + its active product count, scoped to the
    caller's floor(s). Counts drive the left-rail brand badges in the
    Quotation Builder V4."""
    return await catalog_service.list_brands_with_counts(floor_ids=floor_scope_ids(user))
```

```python
@router.get("/categories")
async def list_categories(
    brand_id: Optional[str] = None,
    user: UserPublic = Depends(get_current_user),
):
    """Return categories + per-brand-scoped product counts, scoped to the
    caller's floor(s).

    When `brand_id` is passed, counts reflect ONLY that brand — this is what
    powers the left-rail "Categories under Hansgrohe" list.
    """
    return await catalog_service.list_categories_with_counts(brand_id, floor_ids=floor_scope_ids(user))
```

```python
@router.get("/catalog/hierarchy")
async def catalog_hierarchy(user: UserPublic = Depends(get_current_user)):
    """Return the full Brand → Category → Subcategory → Series → Family tree,
    scoped to the caller's floor(s). Only counts active products.
    """
    rows, brands, cats = await catalog_service.hierarchy_rows(floor_ids=floor_scope_ids(user))
```

(The rest of `catalog_hierarchy`'s body — the tree-building/flattening logic
below the `rows, brands, cats = ...` line — is unchanged; only that one line
and the `_: UserPublic` → `user: UserPublic` parameter change.)

```python
@router.get("/products")
async def list_products(
    q: Optional[str] = Query(None, description="Free text search on name/sku/description/series/family/finish/colour/tags"),
    brand_id: Optional[str] = None,
    category_id: Optional[str] = None,
    subcategory: Optional[str] = None,
    series: Optional[str] = None,
    family_key: Optional[str] = None,
    finish: Optional[str] = None,
    colour: Optional[str] = None,
    sort: str = Query("popular", description="popular | recent | price_asc | price_desc | name"),
    limit: int = 60,
    skip: int = 0,
    user: UserPublic = Depends(get_current_user),
):
    return await catalog_service.list_products_page(
        user_id=user.id,
        q=q,
        brand_id=brand_id,
        category_id=category_id,
        subcategory=subcategory,
        series=series,
        family_key=family_key,
        finish=finish,
        colour=colour,
        sort=sort,
        limit=limit,
        skip=skip,
        floor_ids=floor_scope_ids(user),
    )
```

```python
@router.get("/products/families")
async def list_families(
    brand_id: Optional[str] = None,
    category_id: Optional[str] = None,
    subcategory: Optional[str] = None,
    series: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 60,
    skip: int = 0,
    user: UserPublic = Depends(get_current_user),
):
    """Return products grouped by family_key — one card per family, variants
    collapsed underneath. Ideal for the premium grouped catalog view.
    """
    return await catalog_service.list_family_groups(
        brand_id=brand_id,
        category_id=category_id,
        subcategory=subcategory,
        series=series,
        q=q,
        limit=limit,
        skip=skip,
        floor_ids=floor_scope_ids(user),
    )
```

```python
@router.get("/catalog/search")
async def catalog_search(
    q: str = Query("", description="Free-text query"),
    brand_id: Optional[str] = None,
    category_id: Optional[str] = None,
    subcategory: Optional[str] = None,
    series: Optional[str] = None,
    limit: int = 30,
    group: bool = Query(True, description="Group variants by family_key (Shopify-style)"),
    user: UserPublic = Depends(get_current_user),
):
    """Ranked catalog search, scoped to the caller's floor(s).

    Ranking priority (highest first):
      1. Exact SKU / SKU prefix
      2. Product name / family name (Mongo text score)
      3. Series / subcategory / finish / colour matches
      4. Fallback dimension / description matches

    Results are grouped by `family_key` by default so callers don't see 6
    duplicates of the same product with different finishes.
    """
    return await catalog_service.search_catalog(
        q=q,
        brand_id=brand_id,
        category_id=category_id,
        subcategory=subcategory,
        series=series,
        limit=limit,
        group=group,
        floor_ids=floor_scope_ids(user),
    )
```

```python
@router.get("/catalog/facets")
async def catalog_facets(
    brand_id: Optional[str] = None,
    category_id: Optional[str] = None,
    subcategory: Optional[str] = None,
    series: Optional[str] = None,
    user: UserPublic = Depends(get_current_user),
):
    """Return the facet buckets (brands, categories, finishes, colours,
    price range) for the current selection, scoped to the caller's floor(s).
    """
    return await catalog_service.facet_buckets(
        brand_id=brand_id,
        category_id=category_id,
        subcategory=subcategory,
        series=series,
        floor_ids=floor_scope_ids(user),
    )
```

Finally, fix `create_custom_product`/`create_product` to stop hardcoding the
floor default and use `floor_for_write(user)` instead (add
`floor_for_write` to the `from auth import ...` line):

```python
@router.post("/products/custom", response_model=Product)
async def create_custom_product(
    body: ProductCreate,
    user: UserPublic = Depends(require_min_role("sales")),
):
    """Create a custom / one-off product from the Quotation Builder.

    When body.is_custom=True, the SKU can collide with existing rows (we
    auto-suffix). If False, we behave like /products with duplicate-SKU
    rejection.
    """
    sku = body.sku or f"CUSTOM-{datetime.now(timezone.utc).strftime('%y%m%d%H%M%S')}"
    if body.is_custom:
        # Auto-uniquify — never fail because the user typed the same SKU twice.
        base = sku
        n = 1
        while await db.products.find_one({"sku": sku}):
            n += 1
            sku = f"{base}-{n}"
    elif await db.products.find_one({"sku": sku}):
        raise HTTPException(status_code=409, detail="SKU already exists")

    payload = body.dict()
    payload["sku"] = sku
    payload["tags"] = list(set([*(payload.get("tags") or []), "custom"]))
    payload["floor_id"] = floor_for_write(user)
    prod = Product(**payload)
    await db.products.insert_one(prod.dict())
    catalog_service.schedule_catalog_refresh()
    return prod


@router.post("/products", response_model=Product)
async def create_product(
    body: ProductCreate,
    user: UserPublic = Depends(require_min_role("purchase")),
):
    if await db.products.find_one({"sku": body.sku}):
        raise HTTPException(status_code=409, detail="SKU already exists")
    payload = body.dict()
    payload["floor_id"] = floor_for_write(user)
    prod = Product(**payload)
    await db.products.insert_one(prod.dict())
    catalog_service.schedule_catalog_refresh()
    return prod
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_catalog_routes_floor_scoping.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routes/catalog_routes.py backend/tests/unit/test_catalog_routes_floor_scoping.py
git commit -m "fix: thread floor scope through Catalog routes; fix product-creation floor default"
```

### Task 17: `POST /brands` and `POST /categories`

**Files:**
- Modify: `backend/models.py` (add `BrandCreate`, `CategoryCreate` request models near `Brand`/`Category`)
- Modify: `backend/routes/catalog_routes.py` (add the two new endpoints)
- Test: `backend/tests/unit/test_catalog_routes_floor_scoping.py` (append)

Brands/categories today are only ever seeded — there is no live way to
create one, which blocks creating a ground-floor "CUTE" brand once tile data
arrives.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_catalog_routes_floor_scoping.py`:

```python
def test_create_brand_stamps_floor_for_write(monkeypatch):
    inserted = {}

    class _FakeBrands:
        async def find_one(self, *_a, **_kw):
            return None

        async def insert_one(self, doc):
            inserted.update(doc)

    class _FakeDb:
        brands = _FakeBrands()

    monkeypatch.setattr(catalog_routes, "db", _FakeDb())
    monkeypatch.setattr(catalog_routes.catalog_service, "schedule_catalog_refresh", lambda: None)

    from models import BrandCreate
    body = BrandCreate(name="CUTE", slug="cute")
    asyncio.run(catalog_routes.create_brand(body, user=_user("ground-floor")))

    assert inserted["floor_id"] == "ground-floor"
    assert inserted["name"] == "CUTE"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_catalog_routes_floor_scoping.py -k create_brand -v`
Expected: FAIL — `ImportError: cannot import name 'BrandCreate'`

- [ ] **Step 3: Write minimal implementation**

Add to `backend/models.py`, right after the existing `Category` class:

```python
class BrandCreate(BaseModel):
    name: str
    slug: str
    logo_url: Optional[str] = None
    country: Optional[str] = None


class CategoryCreate(BaseModel):
    name: str
    slug: str
    parent_id: Optional[str] = None
    icon: Optional[str] = None
```

Add to `backend/routes/catalog_routes.py`, right after `list_categories`:

```python
@router.post("/brands", response_model=Brand)
async def create_brand(
    body: BrandCreate,
    user: UserPublic = Depends(require_min_role("purchase")),
):
    if await db.brands.find_one({"slug": body.slug}):
        raise HTTPException(status_code=409, detail="A brand with this slug already exists")
    payload = body.dict()
    payload["floor_id"] = floor_for_write(user)
    brand = Brand(**payload)
    await db.brands.insert_one(brand.dict())
    catalog_service.schedule_catalog_refresh()
    return brand


@router.post("/categories", response_model=Category)
async def create_category(
    body: CategoryCreate,
    user: UserPublic = Depends(require_min_role("purchase")),
):
    if await db.categories.find_one({"slug": body.slug}):
        raise HTTPException(status_code=409, detail="A category with this slug already exists")
    payload = body.dict()
    payload["floor_id"] = floor_for_write(user)
    category = Category(**payload)
    await db.categories.insert_one(category.dict())
    catalog_service.schedule_catalog_refresh()
    return category
```

Add `Brand, BrandCreate, Category, CategoryCreate` to the existing `from models import ...` line at the top of `catalog_routes.py` (currently only imports `Product, ProductCreate, ProductPatch, UserPublic`). `floor_for_write` is already imported as of Task 16 — no change needed to the `from auth import ...` line.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_catalog_routes_floor_scoping.py -v`
Expected: PASS (all tests in this file)

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/routes/catalog_routes.py backend/tests/unit/test_catalog_routes_floor_scoping.py
git commit -m "feat: add POST /brands and POST /categories, floor-scoped"
```

### Task 18: `size` field on `Product` + search/facets

**Files:**
- Modify: `backend/models.py:275-319` (`Product`, `ProductCreate`, `ProductPatch`)
- Modify: `backend/services/catalog_service.py` (`_SEARCH_FIELDS`, `facet_buckets`)
- Test: `backend/tests/unit/test_catalog_service_floor_scoping.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_catalog_service_floor_scoping.py`:

```python
def test_size_is_a_search_field():
    from services.catalog_service import _SEARCH_FIELDS
    assert "size" in _SEARCH_FIELDS


def test_facet_buckets_includes_sizes():
    import asyncio
    from unittest.mock import AsyncMock, patch

    async def _fake_snapshot():
        class _Snap:
            products = ({"size": "600x600mm", "floor_id": "ground-floor"},)
        return _Snap()

    with patch("services.catalog_service.get_catalog_snapshot", _fake_snapshot):
        from services.catalog_service import facet_buckets
        result = asyncio.run(facet_buckets(brand_id=None, category_id=None, subcategory=None, series=None))
        assert result["sizes"] == [{"value": "600x600mm", "count": 1}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_catalog_service_floor_scoping.py -k "search_field or facet_buckets_includes" -v`
Expected: FAIL — `AssertionError: 'size' not in (...)` and `KeyError: 'sizes'`

- [ ] **Step 3: Write minimal implementation**

In `backend/models.py`, add `size` to `Product` right after the existing `finish` field:

```python
    finish: Optional[str] = None            # e.g. "Chrome", "Matt Black", "Brushed Brass"
    size: Optional[str] = None              # e.g. "600x600mm" — tile nominal size
```

Add it to `ProductCreate` too, alongside its existing `finish` field:

```python
class ProductCreate(BaseModel):
    name: str
    sku: str
    brand_id: str
    category_id: str
    description: Optional[str] = None
    finish: Optional[str] = None
    size: Optional[str] = None
    material: Optional[str] = None
```

And to `ProductPatch` alongside its `finish` field — current:

```python
class ProductPatch(BaseModel):
    """Partial edit of an existing catalog product — the "single source of
    truth" editor (Catalog / Quotation Builder / Purchases all write through
    this one shape). Every field is optional; only fields actually present in
    the request body are applied (exclude_unset), so callers never
    accidentally blank out a field they didn't mean to touch."""
    name: Optional[str] = None
    sku: Optional[str] = None
    brand_id: Optional[str] = None
    category_id: Optional[str] = None
    subcategory: Optional[str] = None
    series: Optional[str] = None
    family_key: Optional[str] = None
    family_name: Optional[str] = None
    finish: Optional[str] = None
    colour: Optional[str] = None
    description: Optional[str] = None
    mrp: Optional[float] = None
    price: Optional[float] = None
    specs: Optional[dict] = None
```

becomes (one added line):

```python
class ProductPatch(BaseModel):
    """Partial edit of an existing catalog product — the "single source of
    truth" editor (Catalog / Quotation Builder / Purchases all write through
    this one shape). Every field is optional; only fields actually present in
    the request body are applied (exclude_unset), so callers never
    accidentally blank out a field they didn't mean to touch."""
    name: Optional[str] = None
    sku: Optional[str] = None
    brand_id: Optional[str] = None
    category_id: Optional[str] = None
    subcategory: Optional[str] = None
    series: Optional[str] = None
    family_key: Optional[str] = None
    family_name: Optional[str] = None
    finish: Optional[str] = None
    size: Optional[str] = None
    colour: Optional[str] = None
    description: Optional[str] = None
    mrp: Optional[float] = None
    price: Optional[float] = None
    specs: Optional[dict] = None
```

In `backend/services/catalog_service.py`, add `"size"` to `_SEARCH_FIELDS`:

```python
_SEARCH_FIELDS = (
    "name", "sku", "description", "series", "family_name", "subcategory",
    "collection", "finish", "colour", "dimensions", "size", "tags",
)
```

And add a `"sizes"` bucket to `facet_buckets`, matching the existing `"finishes"` bucket:

```python
    return {
        "brands": bucket("brand_id"),
        "categories": bucket("category_id"),
        "subcategories": bucket("subcategory"),
        "series": bucket("series"),
        "finishes": bucket("finish"),
        "sizes": bucket("size"),
        "colours": bucket("colour"),
        "materials": bucket("material"),
        "price": {"min": min(prices, default=0), "max": max(prices, default=0)},
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_catalog_service_floor_scoping.py -v`
Expected: PASS (all tests in this file)

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/services/catalog_service.py backend/tests/unit/test_catalog_service_floor_scoping.py
git commit -m "feat: add size as a first-class Product field, search field, and facet"
```

### Task 19: SKU uniqueness migration (per floor + brand)

**Files:**
- Create: `backend/migrations/0005_products_sku_unique_per_floor_brand.py`
- Test: `backend/tests/unit/test_migration_0005.py` (new)

**Manual pre-step required before this migration can run cleanly against
the live database** — flag this to the user, don't silently work around it:
the known live duplicate SKU `26456000` under Hansgrohe (two different
product documents, both `floor_id="first-floor"`) will make this index fail
to build, the same way the earlier index-collision gotcha did (see
`migrations/0003`'s docstring). Query for it and resolve it (rename one
SKU, or merge the two products) before this migration runs. The migration
itself should NOT attempt to auto-resolve real product data — that is a
data decision for a human, not a schema migration.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_migration_0005.py`:

```python
"""Migration 0005 creates a compound unique index on products scoped to
(floor_id, brand_id, sku) — SKUs no longer need to be globally unique, only
unique within their own floor+brand, matching the 2026-07-17 decision to
scope uniqueness per floor now that the catalog spans multiple floors."""
from __future__ import annotations

import asyncio
import importlib

migration = importlib.import_module("migrations.0005_products_sku_unique_per_floor_brand")


class _FakeProducts:
    def __init__(self):
        self.create_index_calls: list[tuple] = []

    async def create_index(self, keys, **kwargs):
        self.create_index_calls.append((keys, kwargs))


class _FakeDb:
    def __init__(self):
        self.products = _FakeProducts()


def test_migration_creates_compound_unique_index():
    fake_db = _FakeDb()
    asyncio.run(migration.up(fake_db))

    keys, kwargs = fake_db.products.create_index_calls[0]
    assert keys == [("floor_id", 1), ("brand_id", 1), ("sku", 1)]
    assert kwargs.get("unique") is True
    assert kwargs.get("name") == "products_floor_brand_sku_unique"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_migration_0005.py -v`
Expected: FAIL — `ModuleNotFoundError` (file doesn't exist yet)

- [ ] **Step 3: Write minimal implementation**

Create `backend/migrations/0005_products_sku_unique_per_floor_brand.py`:

```python
"""SKU uniqueness is now scoped per (floor_id, brand_id) rather than
globally or per-brand-only — the ground-floor tile catalog and the
first-floor sanitary catalog are separate businesses that may legitimately
reuse a supplier SKU code across floors.

PREREQUISITE (manual, human decision — do not automate): as of 2026-07-17
there is one known live duplicate SKU (26456000) under Hansgrohe, both rows
on floor_id="first-floor" — this migration's index will fail to build
against that data until it's resolved (rename one SKU or merge the two
products). See migrations/0003's docstring for the exact failure mode
(OperationFailure code 85) this class of problem produces if left
unresolved and the collision happens to also match on index name; a
brand-new index name here means a genuine duplicate-key error instead,
which is the correct, loud failure for real duplicate data — don't catch or
suppress it.
"""
from __future__ import annotations


async def up(db) -> None:
    await db.products.create_index(
        [("floor_id", 1), ("brand_id", 1), ("sku", 1)],
        unique=True,
        name="products_floor_brand_sku_unique",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_migration_0005.py -v`
Expected: PASS

- [ ] **Step 5: Before committing — resolve the live duplicate SKU manually**

Run this read-only check against the real database first (do not skip):

```bash
cd backend && .venv/bin/python -c "
import asyncio
from db import db

async def main():
    dupes = await db.products.aggregate([
        {'\$group': {'_id': {'brand_id': '\$brand_id', 'sku': '\$sku'}, 'ids': {'\$push': '\$id'}, 'n': {'\$sum': 1}}},
        {'\$match': {'n': {'\$gt': 1}}},
    ]).to_list(50)
    print(dupes)

asyncio.run(main())
"
```

If this prints any rows, stop and resolve them (coordinate with the user on
which product to rename/merge) before running the migration against the
live database — this plan's Step 3 code is correct and safe to commit
either way, but do not run `scripts/run_migrations.py` against production
until the query above returns an empty list.

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/0005_products_sku_unique_per_floor_brand.py backend/tests/unit/test_migration_0005.py
git commit -m "feat: scope product SKU uniqueness to (floor_id, brand_id)"
```

### Task 20: Frontend — `variantDescriptor()` helper + display fix

**Files:**
- Modify: `frontend/src/components/quotation/helpers/pricing.ts` (add `variantDescriptor`)
- Modify: `frontend/src/components/quotation/helpers/types.ts:12-39` (add `size` to `Product`)
- Modify: `frontend/src/components/quotation/catalog/PickerCard.tsx:63-66,83`
- Modify: `frontend/src/components/quotation/shared/VariantChip.tsx:31-32`
- Modify: `frontend/src/components/quotation/sheets/SwapSheet.tsx:48`
- Modify: `frontend/src/components/quotation/sheets/ProductModal.tsx:198`

This repo has no frontend test runner configured (no Jest/Vitest, no
existing `.test.ts` files) — introducing one is out of scope for this fix.
Verify this task by running the app in the dev server and checking a
product with both `finish` and `size` set shows both together, per the
verification steps below instead of an automated test.

- [ ] **Step 1: Add the type field**

In `frontend/src/components/quotation/helpers/types.ts`, add `size` to `Product` right after its existing `finish` field:

```typescript
export type Product = {
  id: string; name: string; sku: string; price: number; mrp: number;
  finish?: string | null; size?: string | null; images: string[]; category_id: string; brand_id: string;
  variants?: ProductVariant[];
```

- [ ] **Step 2: Add the shared helper**

In `frontend/src/components/quotation/helpers/pricing.ts`, add (this file
already exports `finishSwatch`, which `VariantChip.tsx` imports from here —
keep the same import path so callers only need one new named import):

```typescript
// Joins whichever of finish/size/color are present into one display
// string, e.g. "Glossy · 600×600mm". A tile has both a finish and a size —
// the old pattern (`finish || color || size || sku`) picked only ONE of
// them, silently dropping the other. Returns "" (never a fallback to sku)
// so callers decide their own sku fallback explicitly.
export function variantDescriptor(v: { finish?: string | null; size?: string | null; color?: string | null }): string {
  return [v.finish, v.size, v.color].filter((part): part is string => !!part).join(" · ");
}
```

- [ ] **Step 3: Replace the fallback chain in `VariantChip.tsx`**

Current:

```typescript
  const delta = (variant.price ?? basePrice) - basePrice;
  const label = variant.finish || variant.color || variant.size || variant.sku;
```

Becomes:

```typescript
  const delta = (variant.price ?? basePrice) - basePrice;
  const label = variantDescriptor(variant) || variant.sku;
```

Add `variantDescriptor` to the existing `import { finishSwatch } from "../helpers/pricing";` line:

```typescript
import { finishSwatch, variantDescriptor } from "../helpers/pricing";
```

- [ ] **Step 4: Replace both call sites in `PickerCard.tsx`**

Current:

```typescript
          <Text style={type.caption} numberOfLines={1}>
            {product.sku}{product.finish ? ` · ${product.finish}` : ""}
          </Text>
```

Becomes:

```typescript
          <Text style={type.caption} numberOfLines={1}>
            {product.sku}{variantDescriptor(product) ? ` · ${variantDescriptor(product)}` : ""}
          </Text>
```

And current:

```typescript
          toast.success(`${product.name} · ${v.finish || v.color || v.size || v.sku} added`);
```

Becomes:

```typescript
          toast.success(`${product.name} · ${variantDescriptor(v) || v.sku} added`);
```

Add the import: `import { variantDescriptor } from "../helpers/pricing";` (new
import line — this file doesn't currently import from `pricing.ts`).

- [ ] **Step 5: Replace the call site in `SwapSheet.tsx`**

Current:

```typescript
                  <Text style={type.caption}>{p.sku}{p.finish ? ` · ${p.finish}` : ""}</Text>
```

Becomes:

```typescript
                  <Text style={type.caption}>{p.sku}{variantDescriptor(p) ? ` · ${variantDescriptor(p)}` : ""}</Text>
```

Add the import: `import { variantDescriptor } from "../helpers/pricing";`
(check the existing import block at the top of `SwapSheet.tsx` first — add
to an existing `from "../helpers/pricing"` line if one is already there,
otherwise add a new line).

- [ ] **Step 6: Replace the call site in `ProductModal.tsx`**

Current:

```typescript
                            <Text style={[styles.variantLabel, on && { color: colors.onBrand }]}>{v.finish || v.color || v.size || v.sku}</Text>
```

Becomes:

```typescript
                            <Text style={[styles.variantLabel, on && { color: colors.onBrand }]}>{variantDescriptor(v) || v.sku}</Text>
```

Add the import: `import { variantDescriptor } from "../helpers/pricing";`
(check `ProductModal.tsx`'s existing import block first, same as Step 5).

- [ ] **Step 7: Verify in the browser**

Start the dev server (`.claude/launch.json`'s existing frontend
configuration, per this repo's established restart recipe — see the
project's dev-run notes if the server isn't already running on its usual
port) and:

1. Open the Catalog or Quotation Builder product picker.
2. Find or temporarily create (via `PATCH /products/{id}` or the product
   editor) a product with both `finish` and `size` set (e.g. finish
   "Glossy", size "600x600mm").
3. Confirm the picker card caption shows `SKU · Glossy · 600x600mm` (both
   values, not just one).
4. Open its variant chips (if it has sibling variants) and confirm each
   chip's label also shows the joined finish+size, not just one field.
5. Confirm a product with only a `finish` (no `size`) still shows correctly
   (no stray " · " separator, no "null" text) — this is the regression case
   the old fallback chain handled correctly and the new helper must too.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/quotation/helpers/pricing.ts \
        frontend/src/components/quotation/helpers/types.ts \
        frontend/src/components/quotation/catalog/PickerCard.tsx \
        frontend/src/components/quotation/shared/VariantChip.tsx \
        frontend/src/components/quotation/sheets/SwapSheet.tsx \
        frontend/src/components/quotation/sheets/ProductModal.tsx
git commit -m "fix: show finish and size together instead of picking only one"
```

---

## Explicitly out of scope for this plan

- No new MongoDB Atlas cluster or new Supabase project — the app already
  runs on cloud infrastructure (confirmed: `MONGO_URL` is a real Atlas
  `mongodb+srv://` connection string, not local; Supabase is already used
  for `forge-products`/`forge-private` storage buckets). Nothing here
  changes that.
- No tile product data import — this plan makes the schema and isolation
  correct; loading the actual 5,000+ tile SKUs is separate, later work once
  the user has that data ready.
- No Cmd+K quick-search brand-scoping — confirmed with the user this
  surface isn't the one that matters; the Catalog page and Quotation
  Builder search (both fixed here) are.
- No `LineRow`/`Line`-type/`QuotationLineItem` changes for `size` — `LineRow`
  only shows a `FinishSwatch` (a colour dot), not a text fallback chain, so
  it isn't affected by this bug. Persisting `size` onto quotation/purchase
  line-item snapshots (so it survives into PDFs, POs, etc.) is a reasonable
  future follow-up but wasn't part of the approved spec — raise it
  separately once real tile data exists to test against.
- Payments' `whatsapp_reminder` endpoint (minor, action-only, not a
  data-display leak) — left as a known small gap, not part of this pass.

## Rollout order

Milestone A, then B, then C, in the order the tasks are numbered — each
milestone is independently deployable and each task within it is a single
commit. Task 19 has a hard manual gate (resolve the live duplicate SKU)
before its migration may be run against the real database; every other task
in this plan is safe to deploy immediately after its tests pass.
