# Sales Data Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an owner/admin-only "Sales Data" dashboard showing revenue by floor, by architect/interior-designer referrer, and by brand, backed by a new lightweight referrer directory.

**Architecture:** Backend adds one new collection (`referrers`) and three denormalized fields on `Quotation` (`referrer_type`, `referrer_id`, `referrer_name`), plus a new read-only `sales_data_routes.py` that aggregates already-`won` quotations in Python (matching the existing `dashboard_routes.py` convention — no Mongo aggregation pipeline). Frontend adds a referrer picker to the quotation builder (mirrors the existing `CustomerSwitcherSheet` pattern) and a new `(admin)/sales-data` route tree gated through the existing configurable permission-matrix system.

**Tech Stack:** FastAPI + Motor (Mongo) backend, Expo/React Native frontend, existing `components/ui.tsx` design system. No new dependencies — the trend chart is a small custom bar-chart component (the codebase has no charting library anywhere).

## Global Constraints

- Revenue = `sum(grand_total)` over quotations where `status == "won"` — exactly the definition already used by `GET /dashboard/stats` (`backend/routes/dashboard_routes.py`). Never introduce a second definition of "sale."
- Every new `sales-data` endpoint is gated with `require_roles("owner", "admin")` from `backend/auth.py` — no new auth mechanism.
- `Quotation.reference_source` (free-text "Walk-in"/"Instagram"/etc.) is never modified or removed — the new `referrer_*` fields are additive and independent of it.
- No historical backfill — old quotations keep `referrer_id: None`; referrer tracking starts from the first quotation created after this ships.
- No new npm/pip dependencies. No new charting library.
- Date range for v1 is implemented as **presets** (Today / This Month / This Quarter / This Year / All Time), computed client-side — not a calendar picker (none exists in this codebase and building one is out of scope for this feature; flagged here so it's visible at review time).
- Frontend has no test runner configured (`frontend/package.json` has no `test` script and no `.test.tsx` files exist anywhere in the repo) — frontend tasks are verified manually via `expo start --web` + `expo lint`, not automated tests. Backend tasks follow strict TDD with `pytest`.

---

## File Structure

**Backend — new files:**
- `backend/routes/referrer_routes.py` — referrer directory CRUD (list, create)
- `backend/routes/sales_data_routes.py` — read-only aggregation endpoints
- `backend/tests/unit/test_referrer_routes.py`
- `backend/tests/unit/test_quotation_referrer_fields.py`
- `backend/tests/unit/test_sales_data_routes.py`

**Backend — modified files:**
- `backend/models.py` — add `Referrer`, `ReferrerCreate`, `ReferrerType`; add 3 fields to `Quotation`, `QuotationCreate`, `QuotationUpdate`
- `backend/routes/quotation_routes.py` — resolve + denormalize referrer on create/update
- `backend/routes/permissions_routes.py` — register the `sales-data` module
- `backend/server.py` — register the two new routers

**Frontend — new files:**
- `frontend/src/components/quotation/sheets/ReferrerSwitcherSheet.tsx`
- `frontend/src/components/salesData/TrendChart.tsx`
- `frontend/src/components/salesData/salesDataApi.ts` (shared fetch types/helpers used by all 3 screens)
- `frontend/app/(admin)/sales-data/index.tsx`
- `frontend/app/(admin)/sales-data/referrer/[id].tsx`
- `frontend/app/(admin)/sales-data/brand/[id].tsx`

**Frontend — modified files:**
- `frontend/src/components/quotation/helpers/types.ts` — add `Referrer` type, extend `QuotationHeader`/`INITIAL_BUILDER_STATE`
- `frontend/src/components/quotation/context/BuilderContext.tsx` — referrer state + mutations + persist/restore wiring
- `frontend/src/components/quotation/layout/BuilderTopbar.tsx` — "Referred By" pill
- `frontend/src/components/quotation/layout/BuilderShell.tsx` — mount `<ReferrerSwitcherSheet />`
- `frontend/app/(admin)/_layout.tsx` — nav entry

---

## Task 1: Referrer data model + directory CRUD

**Files:**
- Modify: `backend/models.py`
- Create: `backend/routes/referrer_routes.py`
- Modify: `backend/server.py`
- Test: `backend/tests/unit/test_referrer_routes.py`

**Interfaces:**
- Produces: `Referrer(TimestampedModel)` with fields `name: str, type: ReferrerType, phone: Optional[str], company: Optional[str], created_by: str`; `ReferrerCreate(BaseModel)` with `name, type, phone, company`; `ReferrerType = Literal["architect", "interior_designer"]`. Route functions `list_referrers(type, user)` and `create_referrer(body, user)` in `routes.referrer_routes`, mounted at `GET/POST /referrers`.

- [ ] **Step 1: Add the model classes**

In `backend/models.py`, insert this immediately above `class Quotation(TimestampedModel):` (currently around line 438, right after `class RoomDiscountCfg`):

```python
# ---------- Referrers (Sales Data > Referred By) ----------
# Architects and interior designers who send business our way. Deliberately
# minimal — just enough to attribute revenue to a specific person. Existing
# free-text Quotation.reference_source ("Walk-in", "Instagram", etc.) is
# untouched; these fields are only used when a quotation's referrer_type is
# architect/interior_designer. See
# docs/superpowers/specs/2026-07-27-sales-data-dashboard-design.md.
ReferrerType = Literal["architect", "interior_designer"]


class Referrer(TimestampedModel):
    name: str
    type: ReferrerType
    phone: Optional[str] = None
    company: Optional[str] = None
    created_by: str


class ReferrerCreate(BaseModel):
    name: str
    type: ReferrerType
    phone: Optional[str] = None
    company: Optional[str] = None
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/unit/test_referrer_routes.py`:

```python
"""Referrer directory (list + create) — the quotation builder's picker and
the Sales Data dashboard both depend on this being correct."""
from __future__ import annotations

import asyncio

from models import ReferrerCreate, UserPublic
from routes import referrer_routes


def _user(role="sales"):
    return UserPublic(id="user-1", email="s@forge.app", full_name="Sales", role=role)


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_a, **_kw):
        return self

    async def to_list(self, _n):
        return self._docs


class _Collection:
    def __init__(self, docs):
        self._docs = docs
        self.inserted = None

    def find(self, query, *_a, **_kw):
        matched = [d for d in self._docs if all(d.get(k) == v for k, v in query.items())]
        return _Cursor(matched)

    async def insert_one(self, doc):
        self.inserted = doc


class _FakeDb:
    def __init__(self, docs):
        self.referrers = _Collection(docs)


def test_list_referrers_filters_by_type(monkeypatch):
    fake_db = _FakeDb([
        {"id": "r1", "name": "Rakesh Sharma", "type": "architect", "created_at": "t", "updated_at": "t", "created_by": "u"},
        {"id": "r2", "name": "Nikita Shah", "type": "interior_designer", "created_at": "t", "updated_at": "t", "created_by": "u"},
    ])
    monkeypatch.setattr(referrer_routes, "db", fake_db)

    result = asyncio.run(referrer_routes.list_referrers(type="architect", user=_user()))

    assert [r.id for r in result] == ["r1"]


def test_list_referrers_no_filter_returns_all(monkeypatch):
    fake_db = _FakeDb([
        {"id": "r1", "name": "Rakesh Sharma", "type": "architect", "created_at": "t", "updated_at": "t", "created_by": "u"},
        {"id": "r2", "name": "Nikita Shah", "type": "interior_designer", "created_at": "t", "updated_at": "t", "created_by": "u"},
    ])
    monkeypatch.setattr(referrer_routes, "db", fake_db)

    result = asyncio.run(referrer_routes.list_referrers(type=None, user=_user()))

    assert len(result) == 2


def test_create_referrer_stamps_created_by(monkeypatch):
    fake_db = _FakeDb([])
    monkeypatch.setattr(referrer_routes, "db", fake_db)

    body = ReferrerCreate(name="Studio Verve", type="interior_designer")
    result = asyncio.run(referrer_routes.create_referrer(body, user=_user()))

    assert result.created_by == "user-1"
    assert result.name == "Studio Verve"
    assert fake_db.referrers.inserted["name"] == "Studio Verve"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_referrer_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'routes.referrer_routes'`

- [ ] **Step 4: Create the route file**

Create `backend/routes/referrer_routes.py`:

```python
"""Referrer directory — architects & interior designers who refer business.
Minimal CRUD: list (used by the quotation builder's picker and the Sales
Data dashboard) and create (inline quick-add from that same picker). No
update/delete for v1 — see
docs/superpowers/specs/2026-07-27-sales-data-dashboard-design.md."""
from fastapi import APIRouter, Depends, Query

from auth import require_min_role
from db import db
from models import Referrer, ReferrerCreate, ReferrerType, UserPublic

router = APIRouter(tags=["referrers"])


@router.get("/referrers", response_model=list[Referrer])
async def list_referrers(
    type: ReferrerType | None = Query(None),
    user: UserPublic = Depends(require_min_role("sales")),
):
    query: dict = {}
    if type:
        query["type"] = type
    docs = await db.referrers.find(query, {"_id": 0}).sort("name", 1).to_list(2000)
    return [Referrer(**d) for d in docs]


@router.post("/referrers", response_model=Referrer)
async def create_referrer(
    body: ReferrerCreate,
    user: UserPublic = Depends(require_min_role("sales")),
):
    referrer = Referrer(**body.dict(), created_by=user.id)
    await db.referrers.insert_one(referrer.dict())
    return referrer
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_referrer_routes.py -v`
Expected: 3 passed

- [ ] **Step 6: Register the router**

In `backend/server.py`, add the import next to the other route imports (after the `roles_routes`/`permissions_routes` imports):

```python
from routes.referrer_routes import router as referrer_router  # noqa: E402
```

And add `api.include_router(referrer_router)` next to the other `api.include_router(...)` calls (after `api.include_router(permissions_router)`).

- [ ] **Step 7: Commit**

```bash
git add backend/models.py backend/routes/referrer_routes.py backend/server.py backend/tests/unit/test_referrer_routes.py
git commit -m "feat: add referrer directory (architects/interior designers)"
```

---

## Task 2: Quotation gets referrer fields

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/routes/quotation_routes.py`
- Test: `backend/tests/unit/test_quotation_referrer_fields.py`

**Interfaces:**
- Consumes: `Referrer` model from Task 1, `db.referrers` collection.
- Produces: `Quotation.referrer_type: Optional[ReferrerType]`, `Quotation.referrer_id: Optional[str]`, `Quotation.referrer_name: Optional[str]`. Pure helper `_referrer_fields(referrer_type: Optional[str], referrer_doc: Optional[dict]) -> dict` in `routes.quotation_routes`, consumed by later Sales Data tasks indirectly (they read `referrer_type`/`referrer_id`/`referrer_name` straight off `db.quotations` documents).

- [ ] **Step 1: Add fields to the Pydantic models**

In `backend/models.py`, add to `class Quotation(TimestampedModel):` — insert right after the `reference_source: Optional[str] = None` line (around line 457):

```python
    referrer_type: Optional[ReferrerType] = None   # set only when reference_source-style
    referrer_id: Optional[str] = None               # tracking is via a structured Referrer
    referrer_name: Optional[str] = None              # denormalized at write time — see Referrer
```

Add to `class QuotationCreate(BaseModel):` — insert right after `reference_source: Optional[str] = None` (around line 494):

```python
    referrer_type: Optional[ReferrerType] = None
    referrer_id: Optional[str] = None
```

Add to `class QuotationUpdate(BaseModel):` — insert right after `reference_source: Optional[str] = None` (around line 516):

```python
    referrer_type: Optional[ReferrerType] = None
    referrer_id: Optional[str] = None
```

Note: neither `QuotationCreate` nor `QuotationUpdate` accepts `referrer_name` from the client — it's always resolved server-side from `db.referrers`, exactly like `customer_name` is resolved from the fetched customer doc rather than trusted from the client elsewhere on this same router.

- [ ] **Step 2: Write the failing test for the pure helper**

Create `backend/tests/unit/test_quotation_referrer_fields.py`:

```python
"""_referrer_fields denormalizes a referrer's name at write time from an
already-fetched Referrer doc — mirrors how customer_name is resolved from
the fetched customer doc elsewhere on this router, never trusted from the
client directly."""
from routes.quotation_routes import _referrer_fields


def test_no_referrer_doc_clears_all_three_fields():
    assert _referrer_fields("architect", None) == {
        "referrer_type": None, "referrer_id": None, "referrer_name": None,
    }


def test_referrer_doc_present_denormalizes_name():
    doc = {"id": "r1", "name": "Rakesh Sharma Architects"}
    assert _referrer_fields("architect", doc) == {
        "referrer_type": "architect", "referrer_id": "r1", "referrer_name": "Rakesh Sharma Architects",
    }


def test_referrer_doc_present_but_type_missing_still_denormalizes():
    # Defensive: even if the caller forgot to send referrer_type, a resolved
    # doc still means "there IS a referrer" — better to keep the name/id
    # than silently drop them.
    doc = {"id": "r2", "name": "Studio Verve"}
    result = _referrer_fields(None, doc)
    assert result["referrer_id"] == "r2"
    assert result["referrer_name"] == "Studio Verve"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_quotation_referrer_fields.py -v`
Expected: FAIL — `ImportError: cannot import name '_referrer_fields'`

- [ ] **Step 4: Add the helper and wire it into create/update**

In `backend/routes/quotation_routes.py`, add this near the other module-level helpers (e.g. right above `async def create_quotation`):

```python
def _referrer_fields(referrer_type: str | None, referrer_doc: dict | None) -> dict:
    """Denormalizes a referrer's name at write time from an already-fetched
    Referrer doc, mirroring how customer_name is resolved from the fetched
    customer doc rather than trusted from the client. Returns the three
    Quotation fields to merge; all None when there is no referrer."""
    if not referrer_doc:
        return {"referrer_type": None, "referrer_id": None, "referrer_name": None}
    return {
        "referrer_type": referrer_type,
        "referrer_id": referrer_doc["id"],
        "referrer_name": referrer_doc["name"],
    }
```

In `create_quotation`, right before the `totals = _recalc(...)` line, add:

```python
    referrer_doc = None
    if body.referrer_id:
        referrer_doc = await db.referrers.find_one({"id": body.referrer_id}, {"_id": 0, "id": 1, "name": 1})
        if not referrer_doc:
            raise HTTPException(status_code=404, detail="Referrer not found")
```

Then in the `Quotation(...)` constructor call, add `**_referrer_fields(body.referrer_type, referrer_doc),` right next to the existing `reference_source=body.reference_source,` line.

In `update_quotation`, right after the existing block:
```python
    if body.reference_source is not None:
        update["reference_source"] = body.reference_source
```
add:

```python
    if body.referrer_id is not None:
        referrer_doc = None
        if body.referrer_id:
            referrer_doc = await db.referrers.find_one({"id": body.referrer_id}, {"_id": 0, "id": 1, "name": 1})
            if not referrer_doc:
                raise HTTPException(status_code=404, detail="Referrer not found")
        update.update(_referrer_fields(body.referrer_type, referrer_doc))
```

(Sending `referrer_id: ""` or `null` clears the referrer entirely — `_referrer_fields(_, None)` sets all three fields back to `None`.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_quotation_referrer_fields.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/models.py backend/routes/quotation_routes.py backend/tests/unit/test_quotation_referrer_fields.py
git commit -m "feat: quotations denormalize a structured referrer at write time"
```

---

## Task 3: Sales Data backend — overview endpoint

**Files:**
- Create: `backend/routes/sales_data_routes.py`
- Test: `backend/tests/unit/test_sales_data_routes.py`

**Interfaces:**
- Consumes: `db.quotations` docs with `status`, `floor_id`, `grand_total`, `updated_at`/`created_at`, `referrer_type`, `referrer_id`, `referrer_name` (from Task 2). `auth.accessible_floor_ids`, `auth.require_roles`.
- Produces: `_bucket_label(iso_ts: str, granularity: str) -> str`, `_resolve_floor_ids(user, floor_id: str | None) -> list[str] | None`, `_won_quotations(floor_ids, date_from, date_to) -> list[dict]` — all consumed by Tasks 4 and 5 in the same file. Route `GET /sales-data/overview`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_sales_data_routes.py`:

```python
"""Sales Data dashboard aggregation — computed in Python over already-`won`
quotations, matching the existing dashboard_routes.py convention. These
tests exercise the computation directly against a fake db, same pattern as
test_dashboard_floor_scoping.py."""
from __future__ import annotations

import asyncio

from auth import accessible_floor_ids
from models import UserPublic
from routes import sales_data_routes as sd


def _owner():
    return UserPublic(id="u-owner", email="o@forge.app", full_name="Owner", role="owner")


def _admin_ground_only():
    return UserPublic(id="u-admin", email="a@forge.app", full_name="Admin", role="admin", floor_ids=["ground-floor"])


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, _n):
        return self._docs


class _Collection:
    def __init__(self, docs):
        self._docs = docs
        self.last_query = None

    def find(self, query, *_a, **_kw):
        self.last_query = query
        return _Cursor(self._docs)


class _FakeDb:
    def __init__(self, docs):
        self.quotations = _Collection(docs)


def test_bucket_label_day():
    assert sd._bucket_label("2026-07-15T10:00:00+00:00", "day") == "2026-07-15"


def test_bucket_label_month():
    assert sd._bucket_label("2026-07-15T10:00:00+00:00", "month") == "2026-07"


def test_bucket_label_quarter():
    assert sd._bucket_label("2026-08-01T00:00:00+00:00", "quarter") == "2026-Q3"


def test_bucket_label_year():
    assert sd._bucket_label("2026-01-05T00:00:00+00:00", "year") == "2026"


def test_resolve_floor_ids_owner_both_means_no_restriction():
    assert sd._resolve_floor_ids(_owner(), "both") is None
    assert sd._resolve_floor_ids(_owner(), None) is None


def test_resolve_floor_ids_owner_picks_one_floor():
    assert sd._resolve_floor_ids(_owner(), "ground-floor") == ["ground-floor"]


def test_resolve_floor_ids_admin_cannot_request_a_floor_outside_their_access():
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        sd._resolve_floor_ids(_admin_ground_only(), "first-floor")
    assert exc.value.status_code == 403


def test_overview_totals_revenue_and_splits_by_floor(monkeypatch):
    fake_db = _FakeDb([
        {"status": "won", "floor_id": "ground-floor", "grand_total": 100000, "updated_at": "2026-07-01T00:00:00+00:00"},
        {"status": "won", "floor_id": "first-floor", "grand_total": 50000, "updated_at": "2026-07-02T00:00:00+00:00"},
    ])
    monkeypatch.setattr(sd, "db", fake_db)

    result = asyncio.run(sd.sales_overview(
        floor_id=None, referrer_type=None, date_from=None, date_to=None,
        granularity="month", user=_owner(),
    ))

    assert result["total_revenue"] == 150000
    by_floor = {r["floor_id"]: r["revenue"] for r in result["revenue_by_floor"]}
    assert by_floor == {"ground-floor": 100000, "first-floor": 50000}
    assert result["trend"] == [{"bucket": "2026-07", "revenue": 150000}]
    assert result["referrers"] is None


def test_overview_referrer_type_filters_and_ranks(monkeypatch):
    fake_db = _FakeDb([
        {
            "status": "won", "floor_id": "first-floor", "grand_total": 80000,
            "updated_at": "2026-07-01T00:00:00+00:00",
            "referrer_type": "architect", "referrer_id": "r1", "referrer_name": "Rakesh Sharma",
        },
        {
            "status": "won", "floor_id": "first-floor", "grand_total": 40000,
            "updated_at": "2026-07-02T00:00:00+00:00",
            "referrer_type": "architect", "referrer_id": "r1", "referrer_name": "Rakesh Sharma",
        },
        {
            "status": "won", "floor_id": "first-floor", "grand_total": 20000,
            "updated_at": "2026-07-02T00:00:00+00:00",
            "referrer_type": "interior_designer", "referrer_id": "r2", "referrer_name": "Nikita Shah",
        },
    ])
    monkeypatch.setattr(sd, "db", fake_db)

    result = asyncio.run(sd.sales_overview(
        floor_id=None, referrer_type="architect", date_from=None, date_to=None,
        granularity="month", user=_owner(),
    ))

    assert result["total_revenue"] == 120000
    assert result["referrers"] == [{"referrer_id": "r1", "name": "Rakesh Sharma", "revenue": 120000}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_sales_data_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'routes.sales_data_routes'`

- [ ] **Step 3: Create the route file (overview only)**

Create `backend/routes/sales_data_routes.py`:

```python
"""Sales Data dashboard (owner/admin only) — revenue by floor, by
architect/interior-designer referrer, and by brand. Reads only `won`
quotations, matching the revenue definition already used by
/dashboard/stats. Aggregation happens in Python over an in-memory list —
matches the existing dashboard_routes.py convention — rather than a Mongo
pipeline, since won-quotation volume stays small and this is far easier to
unit-test against the codebase's existing fake-db pattern. See
docs/superpowers/specs/2026-07-27-sales-data-dashboard-design.md."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import accessible_floor_ids, require_roles
from db import db
from models import UserPublic

router = APIRouter(prefix="/sales-data", tags=["sales-data"])

Granularity = Literal["day", "month", "quarter", "year"]


def _bucket_label(iso_ts: str, granularity: Granularity) -> str:
    dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    if granularity == "day":
        return dt.strftime("%Y-%m-%d")
    if granularity == "month":
        return dt.strftime("%Y-%m")
    if granularity == "year":
        return dt.strftime("%Y")
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{q}"


def _resolve_floor_ids(user: UserPublic, floor_id: Optional[str]) -> Optional[list[str]]:
    """Combines the caller's own floor access with the Floor filter the
    frontend sent. None means "no floor restriction" (query every floor
    the caller can see)."""
    allowed = accessible_floor_ids(user)
    if floor_id and floor_id != "both":
        if allowed is not None and floor_id not in allowed:
            raise HTTPException(status_code=403, detail="You do not have access to this floor")
        return [floor_id]
    return allowed


async def _won_quotations(
    floor_ids: Optional[list[str]], date_from: Optional[str], date_to: Optional[str],
) -> list[dict]:
    query: dict = {"status": "won"}
    if floor_ids is not None:
        query["floor_id"] = {"$in": floor_ids}
    if date_from or date_to:
        rng: dict = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        query["updated_at"] = rng
    return await db.quotations.find(query, {"_id": 0}).to_list(10000)


@router.get("/overview")
async def sales_overview(
    floor_id: Optional[str] = Query(None),
    referrer_type: Optional[Literal["architect", "interior_designer"]] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    granularity: Granularity = Query("month"),
    user: UserPublic = Depends(require_roles("owner", "admin")),
):
    floor_ids = _resolve_floor_ids(user, floor_id)
    quotations = await _won_quotations(floor_ids, date_from, date_to)

    if referrer_type:
        quotations = [q for q in quotations if q.get("referrer_type") == referrer_type]

    total_revenue = round(sum(q.get("grand_total", 0) for q in quotations), 2)

    by_floor: dict[str, float] = defaultdict(float)
    for q in quotations:
        by_floor[q.get("floor_id", "unknown")] += q.get("grand_total", 0)
    revenue_by_floor = [{"floor_id": fid, "revenue": round(rev, 2)} for fid, rev in by_floor.items()]

    trend_map: dict[str, float] = defaultdict(float)
    for q in quotations:
        ts = q.get("updated_at") or q.get("created_at")
        if ts:
            trend_map[_bucket_label(ts, granularity)] += q.get("grand_total", 0)
    trend = [{"bucket": k, "revenue": round(v, 2)} for k, v in sorted(trend_map.items())]

    referrers = None
    if referrer_type:
        by_referrer: dict[str, dict] = {}
        for q in quotations:
            rid = q.get("referrer_id")
            if not rid:
                continue
            entry = by_referrer.setdefault(
                rid, {"referrer_id": rid, "name": q.get("referrer_name") or "Unknown", "revenue": 0.0},
            )
            entry["revenue"] += q.get("grand_total", 0)
        referrers = sorted(
            ({**e, "revenue": round(e["revenue"], 2)} for e in by_referrer.values()),
            key=lambda e: e["revenue"], reverse=True,
        )

    return {
        "total_revenue": total_revenue,
        "quotation_count": len(quotations),
        "revenue_by_floor": revenue_by_floor,
        "trend": trend,
        "referrers": referrers,
    }
```

`quotation_count` is the count of the same already-filtered `quotations` list `total_revenue` was computed from — when `referrer_type` is set, both numbers are already architect/interior-designer-only. The frontend (Task 9) uses this to show "Avg Deal Size" and "# Active" when a referrer type is selected, without a second request.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_sales_data_routes.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add backend/routes/sales_data_routes.py backend/tests/unit/test_sales_data_routes.py
git commit -m "feat: add Sales Data overview endpoint (revenue by floor + referrer type)"
```

---

## Task 4: Sales Data backend — referrer detail endpoint

**Files:**
- Modify: `backend/routes/sales_data_routes.py`
- Test: `backend/tests/unit/test_sales_data_routes.py`

**Interfaces:**
- Consumes: `_bucket_label`, `_resolve_floor_ids`, `_won_quotations` from Task 3; `db.referrers` from Task 1.
- Produces: `GET /sales-data/referrers/{referrer_id}`.

- [ ] **Step 1: Add the failing test**

Append to `backend/tests/unit/test_sales_data_routes.py`:

```python
class _CollectionWithFindOne(_Collection):
    def __init__(self, docs, referrer_doc):
        super().__init__(docs)
        self._referrer_doc = referrer_doc

    async def find_one(self, query, *_a, **_kw):
        if self._referrer_doc and self._referrer_doc.get("id") == query.get("id"):
            return self._referrer_doc
        return None


class _FakeDbWithReferrer:
    def __init__(self, quotation_docs, referrer_doc):
        self.quotations = _Collection(quotation_docs)
        self.referrers = _CollectionWithFindOne([], referrer_doc)


def test_referrer_detail_returns_trend_and_quotations(monkeypatch):
    fake_db = _FakeDbWithReferrer(
        quotation_docs=[
            {
                "id": "q1", "number": "FQ-1", "customer_name": "Amit", "status": "won",
                "floor_id": "first-floor", "grand_total": 80000, "updated_at": "2026-07-01T00:00:00+00:00",
                "referrer_id": "r1",
            },
            {
                "id": "q2", "number": "FQ-2", "customer_name": "Priya", "status": "won",
                "floor_id": "first-floor", "grand_total": 40000, "updated_at": "2026-08-01T00:00:00+00:00",
                "referrer_id": "r1",
            },
            {
                "id": "q3", "number": "FQ-3", "customer_name": "Other", "status": "won",
                "floor_id": "first-floor", "grand_total": 99999, "updated_at": "2026-07-01T00:00:00+00:00",
                "referrer_id": "r-someone-else",
            },
        ],
        referrer_doc={"id": "r1", "name": "Rakesh Sharma Architects", "type": "architect"},
    )
    monkeypatch.setattr(sd, "db", fake_db)

    result = asyncio.run(sd.referrer_detail(
        "r1", date_from=None, date_to=None, granularity="month", user=_owner(),
    ))

    assert result["referrer"]["name"] == "Rakesh Sharma Architects"
    assert result["total_revenue"] == 120000
    assert result["trend"] == [
        {"bucket": "2026-07", "revenue": 80000},
        {"bucket": "2026-08", "revenue": 40000},
    ]
    assert [q["number"] for q in result["quotations"]] == ["FQ-2", "FQ-1"]  # newest first


def test_referrer_detail_404s_for_unknown_referrer(monkeypatch):
    import pytest
    from fastapi import HTTPException

    fake_db = _FakeDbWithReferrer(quotation_docs=[], referrer_doc=None)
    monkeypatch.setattr(sd, "db", fake_db)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(sd.referrer_detail("missing", date_from=None, date_to=None, granularity="month", user=_owner()))
    assert exc.value.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_sales_data_routes.py -v -k referrer_detail`
Expected: FAIL — `AttributeError: module 'routes.sales_data_routes' has no attribute 'referrer_detail'`

- [ ] **Step 3: Add the endpoint**

In `backend/routes/sales_data_routes.py`, append:

```python
@router.get("/referrers/{referrer_id}")
async def referrer_detail(
    referrer_id: str,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    granularity: Granularity = Query("month"),
    user: UserPublic = Depends(require_roles("owner", "admin")),
):
    referrer = await db.referrers.find_one({"id": referrer_id}, {"_id": 0})
    if not referrer:
        raise HTTPException(status_code=404, detail="Referrer not found")

    floor_ids = _resolve_floor_ids(user, None)
    quotations = await _won_quotations(floor_ids, date_from, date_to)
    quotations = [q for q in quotations if q.get("referrer_id") == referrer_id]

    trend_map: dict[str, float] = defaultdict(float)
    for q in quotations:
        ts = q.get("updated_at") or q.get("created_at")
        if ts:
            trend_map[_bucket_label(ts, granularity)] += q.get("grand_total", 0)
    trend = [{"bucket": k, "revenue": round(v, 2)} for k, v in sorted(trend_map.items())]

    quotes = sorted(
        (
            {
                "id": q["id"], "number": q["number"], "customer_name": q["customer_name"],
                "grand_total": q.get("grand_total", 0), "updated_at": q.get("updated_at"),
            }
            for q in quotations
        ),
        key=lambda q: q["updated_at"] or "", reverse=True,
    )

    return {
        "referrer": referrer,
        "total_revenue": round(sum(q.get("grand_total", 0) for q in quotations), 2),
        "trend": trend,
        "quotations": quotes,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_sales_data_routes.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add backend/routes/sales_data_routes.py backend/tests/unit/test_sales_data_routes.py
git commit -m "feat: add Sales Data referrer detail endpoint"
```

---

## Task 5: Sales Data backend — brand endpoints

**Files:**
- Modify: `backend/routes/sales_data_routes.py`
- Test: `backend/tests/unit/test_sales_data_routes.py`

**Interfaces:**
- Consumes: `_resolve_floor_ids`, `_won_quotations`, `_bucket_label` from Task 3. `db.products` (`id`, `brand_id`), `db.brands` (`id`, `name`).
- Produces: `GET /sales-data/brands`, `GET /sales-data/brands/{brand_id}`.

- [ ] **Step 1: Add the failing test**

Append to `backend/tests/unit/test_sales_data_routes.py`:

```python
class _FakeDbForBrands:
    def __init__(self, quotation_docs, product_docs, brand_docs):
        self.quotations = _Collection(quotation_docs)
        self.products = _Collection(product_docs)
        self.brands = _CollectionWithFindOne(brand_docs, brand_docs[0] if brand_docs else None)


_QUOTATIONS_TWO_BRANDS = [
    {
        "status": "won", "floor_id": "first-floor", "grand_total": 0, "updated_at": "2026-07-01T00:00:00+00:00",
        "items": [
            {"product_id": "p1", "name": "Basin A", "sku": "SKU-A", "qty": 2, "unit_price": 5000, "discount_pct": 10},
        ],
    },
    {
        "status": "won", "floor_id": "first-floor", "grand_total": 0, "updated_at": "2026-07-02T00:00:00+00:00",
        "items": [
            {"product_id": "p2", "name": "Tap B", "sku": "SKU-B", "qty": 1, "unit_price": 3000, "discount_pct": 0},
        ],
    },
]
_PRODUCTS = [{"id": "p1", "brand_id": "b-kohler"}, {"id": "p2", "brand_id": "b-jaguar"}]
_BRANDS = [{"id": "b-kohler", "name": "Kohler"}, {"id": "b-jaguar", "name": "Jaguar"}]


def test_brands_ranked_joins_items_to_products_to_brands(monkeypatch):
    fake_db = _FakeDbForBrands(_QUOTATIONS_TWO_BRANDS, _PRODUCTS, _BRANDS)
    monkeypatch.setattr(sd, "db", fake_db)

    result = asyncio.run(sd.brands_ranked(date_from=None, date_to=None, user=_owner()))

    # Basin A: 2 * 5000 * 0.9 = 9000. Tap B: 1 * 3000 = 3000.
    assert result["brands"][0] == {"brand_id": "b-kohler", "brand_name": "Kohler", "revenue": 9000.0}
    assert result["brands"][1] == {"brand_id": "b-jaguar", "brand_name": "Jaguar", "revenue": 3000.0}


def test_brand_detail_returns_trend_and_top_products(monkeypatch):
    fake_db = _FakeDbForBrands(
        _QUOTATIONS_TWO_BRANDS, _PRODUCTS, [{"id": "b-kohler", "name": "Kohler"}],
    )
    monkeypatch.setattr(sd, "db", fake_db)

    result = asyncio.run(sd.brand_detail("b-kohler", date_from=None, date_to=None, granularity="month", user=_owner()))

    assert result["brand"]["name"] == "Kohler"
    assert result["total_revenue"] == 9000.0
    assert result["top_products"] == [{"product_id": "p1", "name": "Basin A", "sku": "SKU-A", "revenue": 9000.0}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_sales_data_routes.py -v -k brand`
Expected: FAIL — `AttributeError: module 'routes.sales_data_routes' has no attribute 'brands_ranked'`

- [ ] **Step 3: Add the endpoints**

In `backend/routes/sales_data_routes.py`, append:

```python
def _line_net(item: dict) -> float:
    """Mirrors QuotationLineItem.net — recomputed here because these
    aggregations work over raw Mongo dicts, not model instances."""
    gross = item.get("qty", 0) * item.get("unit_price", 0)
    disc_pct = item.get("discount_pct") or 0
    return gross - (gross * disc_pct / 100)


async def _product_brand_map(product_ids: set[str]) -> dict[str, str]:
    if not product_ids:
        return {}
    products = await db.products.find(
        {"id": {"$in": list(product_ids)}}, {"_id": 0, "id": 1, "brand_id": 1},
    ).to_list(len(product_ids))
    return {p["id"]: p.get("brand_id") for p in products if p.get("brand_id")}


@router.get("/brands")
async def brands_ranked(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    user: UserPublic = Depends(require_roles("owner", "admin")),
):
    floor_ids = _resolve_floor_ids(user, None)
    quotations = await _won_quotations(floor_ids, date_from, date_to)

    product_ids = {it["product_id"] for q in quotations for it in q.get("items", [])}
    product_brand = await _product_brand_map(product_ids)

    brand_ids = set(product_brand.values())
    brands = await db.brands.find(
        {"id": {"$in": list(brand_ids)}}, {"_id": 0, "id": 1, "name": 1},
    ).to_list(len(brand_ids) or 1)
    brand_name = {b["id"]: b["name"] for b in brands}

    by_brand: dict[str, float] = defaultdict(float)
    for q in quotations:
        for it in q.get("items", []):
            bid = product_brand.get(it["product_id"])
            if bid:
                by_brand[bid] += _line_net(it)

    ranked = sorted(
        (
            {"brand_id": bid, "brand_name": brand_name.get(bid, "Unknown"), "revenue": round(rev, 2)}
            for bid, rev in by_brand.items()
        ),
        key=lambda e: e["revenue"], reverse=True,
    )
    return {"brands": ranked}


@router.get("/brands/{brand_id}")
async def brand_detail(
    brand_id: str,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    granularity: Granularity = Query("month"),
    user: UserPublic = Depends(require_roles("owner", "admin")),
):
    brand = await db.brands.find_one({"id": brand_id}, {"_id": 0})
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    floor_ids = _resolve_floor_ids(user, None)
    quotations = await _won_quotations(floor_ids, date_from, date_to)

    product_ids = {it["product_id"] for q in quotations for it in q.get("items", [])}
    product_brand = await _product_brand_map(product_ids)
    ids_for_brand = {pid for pid, bid in product_brand.items() if bid == brand_id}

    trend_map: dict[str, float] = defaultdict(float)
    product_revenue: dict[str, dict] = {}
    total = 0.0
    for q in quotations:
        ts = q.get("updated_at") or q.get("created_at")
        for it in q.get("items", []):
            if it["product_id"] not in ids_for_brand:
                continue
            net = _line_net(it)
            total += net
            if ts:
                trend_map[_bucket_label(ts, granularity)] += net
            entry = product_revenue.setdefault(
                it["product_id"], {"product_id": it["product_id"], "name": it["name"], "sku": it["sku"], "revenue": 0.0},
            )
            entry["revenue"] += net

    trend = [{"bucket": k, "revenue": round(v, 2)} for k, v in sorted(trend_map.items())]
    top_products = sorted(
        ({**e, "revenue": round(e["revenue"], 2)} for e in product_revenue.values()),
        key=lambda e: e["revenue"], reverse=True,
    )[:10]

    return {"brand": brand, "total_revenue": round(total, 2), "trend": trend, "top_products": top_products}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_sales_data_routes.py -v`
Expected: 13 passed

- [ ] **Step 5: Run the full unit test suite to check for regressions**

Run: `cd backend && python -m pytest tests/unit -v`
Expected: all passing (no pre-existing failures introduced)

- [ ] **Step 6: Commit**

```bash
git add backend/routes/sales_data_routes.py backend/tests/unit/test_sales_data_routes.py
git commit -m "feat: add Sales Data brand ranking and brand detail endpoints"
```

---

## Task 6: Wire up router, permission module, and role-gate test

**Files:**
- Modify: `backend/server.py`
- Modify: `backend/routes/permissions_routes.py`
- Test: `backend/tests/unit/test_sales_data_role_gate.py`

**Interfaces:**
- Consumes: `sales_data_router` from Task 5's file, `auth.require_roles`.
- Produces: `GET /api/sales-data/*` live and gated; `"sales-data"` module key in the permission matrix consumed by the frontend nav in Task 8.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_sales_data_role_gate.py`:

```python
"""Every Sales Data endpoint depends on require_roles("owner", "admin") —
this is the actual dependency FastAPI wires into each route in
sales_data_routes.py, not a separate policy, so testing it here covers all
four endpoints at once."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from auth import require_roles
from models import UserPublic


def _user(role: str) -> UserPublic:
    return UserPublic(id="u1", email="u@forge.app", full_name="U", role=role)


@pytest.mark.parametrize("role", ["sales", "manager", "accounts", "purchase", "warehouse", "worker"])
def test_non_owner_admin_roles_rejected(role):
    dep = require_roles("owner", "admin")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(user=_user(role)))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["owner", "admin"])
def test_owner_and_admin_allowed(role):
    dep = require_roles("owner", "admin")
    result = asyncio.run(dep(user=_user(role)))
    assert result.role == role
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_sales_data_role_gate.py -v`
Expected: 8 passed. `require_roles` already exists in `auth.py` (used elsewhere in the codebase) — this test doesn't drive new production code, it's a regression guard documenting the exact gate every `sales-data` route in Tasks 3-5 depends on, so it fails loudly if that dependency is ever swapped for something weaker on this feature.

- [ ] **Step 3: Register the sales-data router**

In `backend/server.py`, add the import next to the other route imports:

```python
from routes.sales_data_routes import router as sales_data_router  # noqa: E402
```

Add `api.include_router(sales_data_router)` next to the other `api.include_router(...)` calls.

- [ ] **Step 4: Register the permission-matrix module**

In `backend/routes/permissions_routes.py`, add to the `MODULES` list (after the `"settings"` entry):

```python
    {"key": "sales-data", "label": "Sales Data"},
```

Add to `DEFAULT_MIN_ROLE` (currently `{"team": "manager"}`):

```python
DEFAULT_MIN_ROLE: dict[str, str] = {"team": "manager", "sales-data": "admin"}
```

`ROLE_HIERARCHY` has `admin: 90`, `manager: 70` — a `DEFAULT_MIN_ROLE` of `"admin"` means only `owner` (100) and `admin` (90) default to visible, exactly matching the "Owner + Admin" decision. This is a UI-visibility default only; the real enforcement is `require_roles("owner", "admin")` on every `sales-data` endpoint from Task 3-5, which this matrix can never override (see the docstring at the top of `permissions_routes.py`).

- [ ] **Step 5: Start the backend and manually verify the role gate end-to-end**

Run: `cd backend && uvicorn server:app --reload --port 8000` (or however this project normally starts the backend locally — check `README.md`/`STARTUP_CHECK.md` if unsure)

With a valid `sales` (or any non-owner/admin) role token:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/sales-data/overview -H "Authorization: Bearer <sales-role-token>"
```
Expected: `403`

With an `owner` or `admin` token:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/sales-data/overview -H "Authorization: Bearer <owner-role-token>"
```
Expected: `200`

- [ ] **Step 6: Commit**

```bash
git add backend/server.py backend/routes/permissions_routes.py backend/tests/unit/test_sales_data_role_gate.py
git commit -m "feat: register Sales Data routes and permission-matrix module"
```

---

## Task 7: Referrer picker in the quotation builder

**Files:**
- Modify: `frontend/src/components/quotation/helpers/types.ts`
- Modify: `frontend/src/components/quotation/context/BuilderContext.tsx`
- Modify: `frontend/src/components/quotation/layout/BuilderTopbar.tsx`
- Modify: `frontend/src/components/quotation/layout/BuilderShell.tsx`
- Create: `frontend/src/components/quotation/sheets/ReferrerSwitcherSheet.tsx`

**Interfaces:**
- Consumes: `GET/POST /referrers` from Task 1; `PATCH /quotations/{id}` with `referrer_type`/`referrer_id` from Task 2.
- Produces: `useBuilder().referrers: Referrer[]`, `setReferrer(type, id, name)`, `clearReferrer()`, `createReferrer(data)`, `referrerSwitcherOpen`/`setReferrerSwitcherOpen`, consumed only within the quotation builder — no other task depends on these.

- [ ] **Step 1: Add the `Referrer` type and extend `QuotationHeader`**

In `frontend/src/components/quotation/helpers/types.ts`, add near `export type Customer`:

```typescript
export type Referrer = {
  id: string; name: string; type: "architect" | "interior_designer";
  phone?: string | null; company?: string | null;
};
```

Change `QuotationHeader`:

```typescript
export type QuotationHeader = {
  projectName: string;
  phone: string;
  referenceSource: string;
  referrerType: "architect" | "interior_designer" | null;
  referrerId: string | null;
  referrerName: string;
};
```

Change `INITIAL_BUILDER_STATE.header`:

```typescript
  header: { projectName: "", phone: "", referenceSource: "", referrerType: null, referrerId: null, referrerName: "" },
```

- [ ] **Step 2: Add referrer state + fetch to `BuilderContext.tsx`**

Add `Referrer` to the import from `../helpers/types` (same import statement that already lists `Customer`, `Brand`, etc.).

Add state near `const [customerSwitcherOpen, setCustomerSwitcherOpen] = useState(false);`:

```typescript
  const [referrers, setReferrers] = useState<Referrer[]>([]);
  const [referrerSwitcherOpen, setReferrerSwitcherOpen] = useState(false);
```

In the `useEffect` that loads reference data, add `api.get<Referrer[]>("/referrers")` to the `Promise.all([...])` array (as a 7th entry) and destructure it as `refs`, then add `setReferrers(refs);` next to `setCustomers(cs);`.

- [ ] **Step 3: Add `setReferrer`/`clearReferrer`/`createReferrer` mutations**

Add right after the existing `createCustomer` function:

```typescript
  const setReferrer = useCallback((type: "architect" | "interior_designer", id: string, name: string) => {
    history.apply((cur) => ({ ...cur, header: { ...cur.header, referrerType: type, referrerId: id, referrerName: name } }));
    if (quotationId) {
      api.patch(`/quotations/${quotationId}`, { referrer_type: type, referrer_id: id })
        .then(() => { setSaveState("saved"); setSavedAt(new Date()); })
        .catch((e: any) => toast.error(e?.detail || "Could not set referrer"));
    }
  }, [history, quotationId]);

  const clearReferrer = useCallback(() => {
    history.apply((cur) => ({ ...cur, header: { ...cur.header, referrerType: null, referrerId: null, referrerName: "" } }));
    if (quotationId) {
      api.patch(`/quotations/${quotationId}`, { referrer_type: null, referrer_id: null })
        .then(() => { setSaveState("saved"); setSavedAt(new Date()); })
        .catch((e: any) => toast.error(e?.detail || "Could not clear referrer"));
    }
  }, [history, quotationId]);

  const createReferrer = useCallback(async (data: { name: string; type: "architect" | "interior_designer" }) => {
    try {
      const created = await api.post<Referrer>("/referrers", data);
      setReferrers((cur) => [...cur, created].sort((a, b) => a.name.localeCompare(b.name)));
      setReferrer(created.type, created.id, created.name);
      toast.success(`${created.name} added`);
      return created.id;
    } catch (e: any) {
      toast.error(e?.detail || "Could not create referrer");
      return null;
    }
  }, [setReferrer]);
```

- [ ] **Step 4: Wire referrer fields into persist + restore**

In the `persist` callback's `payload` object, add right after `reference_source: s.header.referenceSource || null,`:

```typescript
      referrer_type: s.header.referrerType,
      referrer_id: s.header.referrerId,
```

In `restoreQuotation`, in the `restored.header` object, add right after `referenceSource: doc.reference_source || "",`:

```typescript
          referrerType: doc.referrer_type || null,
          referrerId: doc.referrer_id || null,
          referrerName: doc.referrer_name || "",
```

- [ ] **Step 5: Expose the new state on the context type + provider value**

In the `BuilderContextValue` interface (or equivalent — the block starting `customers: Customer[];` etc.), add near `customers: Customer[];`:

```typescript
  referrers: Referrer[];
```

And near `setCustomer: (id: string) => void;` / `customerSwitcherOpen: boolean; setCustomerSwitcherOpen: (v: boolean) => void;`:

```typescript
  setReferrer: (type: "architect" | "interior_designer", id: string, name: string) => void;
  clearReferrer: () => void;
  createReferrer: (data: { name: string; type: "architect" | "interior_designer" }) => Promise<string | null>;
  referrerSwitcherOpen: boolean; setReferrerSwitcherOpen: (v: boolean) => void;
```

Find the context provider's `value={{ ... }}` object (the same one that lists `customers, categories, categoryById, ... setCustomer, createCustomer, customerSwitcherOpen, setCustomerSwitcherOpen,` twice — once in the memo deps array, once in the value itself) and add `referrers,` next to `customers,`, and `setReferrer, clearReferrer, createReferrer, referrerSwitcherOpen, setReferrerSwitcherOpen,` next to the `setCustomer, createCustomer, ...` group, in both places.

- [ ] **Step 6: Create `ReferrerSwitcherSheet.tsx`**

Create `frontend/src/components/quotation/sheets/ReferrerSwitcherSheet.tsx`, modeled directly on `CustomerSwitcherSheet.tsx`:

```typescript
// Referrer switcher — searchable list of architects/interior designers +
// inline "create new" form. Opens from the topbar's "Referred By" field.
import { useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { BottomSheet } from "@/src/components/BottomSheet";
import { Button } from "@/src/components/ui";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

import { useBuilder } from "../context/BuilderContext";

type ReferrerType = "architect" | "interior_designer";

export function ReferrerSwitcherSheet() {
  const b = useBuilder();
  const [tab, setTab] = useState<ReferrerType>("architect");
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  const close = () => {
    b.setReferrerSwitcherOpen(false);
    setCreating(false);
    setQ(""); setName("");
  };

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    const byType = b.referrers.filter((r) => r.type === tab);
    if (!term) return byType;
    return byType.filter((r) => r.name.toLowerCase().includes(term));
  }, [b.referrers, tab, q]);

  const pick = (id: string, refName: string) => {
    b.setReferrer(tab, id, refName);
    close();
  };

  const save = async () => {
    if (!name.trim()) return;
    setSaving(true);
    const id = await b.createReferrer({ name: name.trim(), type: tab });
    setSaving(false);
    if (id) close();
  };

  return (
    <BottomSheet
      visible={b.referrerSwitcherOpen}
      onClose={close}
      title={creating ? "New referrer" : "Referred by"}
      testID="referrer-switcher-sheet"
      footer={
        creating ? (
          <View style={{ flexDirection: "row", gap: 8, justifyContent: "flex-end" }}>
            <Button label="Cancel" variant="secondary" onPress={() => setCreating(false)} />
            <Button label={saving ? "Saving…" : "Create & select"} onPress={save} disabled={!name.trim() || saving} testID="save-new-referrer" />
          </View>
        ) : undefined
      }
    >
      {creating ? (
        <View style={{ gap: spacing.md }}>
          <View style={{ gap: 6 }}>
            <Text style={type.overline}>Name *</Text>
            <TextInput
              testID="new-referrer-name"
              value={name}
              onChangeText={setName}
              placeholder={tab === "architect" ? "Architect or firm name" : "Interior designer or studio name"}
              style={styles.input}
              autoFocus
            />
          </View>
        </View>
      ) : (
        <View style={{ gap: spacing.md }}>
          <View style={{ flexDirection: "row", gap: 8 }}>
            <Pressable
              testID="referrer-tab-architect"
              onPress={() => setTab("architect")}
              style={[styles.typeTab, tab === "architect" && styles.typeTabActive]}
            >
              <Text style={[styles.typeTabText, tab === "architect" && styles.typeTabTextActive]}>Architect</Text>
            </Pressable>
            <Pressable
              testID="referrer-tab-interior_designer"
              onPress={() => setTab("interior_designer")}
              style={[styles.typeTab, tab === "interior_designer" && styles.typeTabActive]}
            >
              <Text style={[styles.typeTabText, tab === "interior_designer" && styles.typeTabTextActive]}>Interior Designer</Text>
            </Pressable>
          </View>
          <TextInput
            testID="referrer-search"
            value={q}
            onChangeText={setQ}
            placeholder="Search…"
            style={styles.input}
          />
          <Pressable onPress={() => b.clearReferrer()} style={styles.row}>
            <Text style={type.body}>None</Text>
          </Pressable>
          {filtered.map((r) => (
            <Pressable key={r.id} testID={`referrer-row-${r.id}`} onPress={() => pick(r.id, r.name)} style={styles.row}>
              <Text style={type.body}>{r.name}</Text>
            </Pressable>
          ))}
          <Button label="+ Add new" variant="secondary" onPress={() => setCreating(true)} testID="referrer-add-new" />
        </View>
      )}
    </BottomSheet>
  );
}

const styles = StyleSheet.create({
  input: {
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm, fontSize: 15,
  },
  row: { paddingVertical: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  typeTab: {
    flex: 1, paddingVertical: spacing.sm, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, alignItems: "center",
  },
  typeTabActive: { backgroundColor: colors.brandTint, borderColor: colors.brand },
  typeTabText: { fontSize: 13, fontWeight: "500", color: colors.onSurfaceMuted },
  typeTabTextActive: { color: colors.brand, fontWeight: "600" },
});
```

- [ ] **Step 7: Add the "Referred By" pill to `BuilderTopbar.tsx`**

Right after the existing `<FieldPill label="Ref" ... testID="hdr-ref" />` block, add:

```typescript
          <Pressable
            testID="hdr-referrer"
            onPress={() => b.setReferrerSwitcherOpen(true)}
            style={({ pressed }) => [styles.field, styles.fieldPressable, pressed && styles.fieldPressed]}
          >
            <Text style={styles.fieldLabel}>Referred By</Text>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
              <Text style={styles.fieldValue} numberOfLines={1}>
                {b.s.header.referrerName || "None"}
              </Text>
              <Feather name="chevron-down" size={11} color={colors.onSurfaceMuted} />
            </View>
          </Pressable>
```

- [ ] **Step 8: Mount the sheet in `BuilderShell.tsx`**

Add the import next to `import { CustomerSwitcherSheet } from "../sheets/CustomerSwitcherSheet";`:

```typescript
import { ReferrerSwitcherSheet } from "../sheets/ReferrerSwitcherSheet";
```

Add `<ReferrerSwitcherSheet />` right after `<CustomerSwitcherSheet />` in the "Universal sheets" block.

- [ ] **Step 9: Lint**

Run: `cd frontend && npx expo lint`
Expected: no new errors in the files touched this task

- [ ] **Step 10: Manual verification**

Start the app (`cd frontend && npx expo start --web`), open the quotation builder, click the new "Referred By" pill, switch between Architect/Interior Designer tabs, add a new referrer via "+ Add new", confirm it's selected and shown in the pill, reload the builder for that same quotation and confirm the referrer is restored.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/components/quotation
git commit -m "feat: add structured architect/interior-designer picker to quotation builder"
```

---

## Task 8: Sales Data nav entry + page shell

**Files:**
- Modify: `frontend/app/(admin)/_layout.tsx`
- Create: `frontend/src/components/salesData/salesDataApi.ts`
- Create: `frontend/app/(admin)/sales-data/index.tsx`

**Interfaces:**
- Consumes: `GET /sales-data/overview` from Task 3, `GET /settings/floors` (existing), `useModuleAccess()` from `@/src/hooks/use-permissions` (existing), `useAuth()` from `@/src/state/auth` (existing).
- Produces: `salesDataApi.ts` exports `Granularity`, `ReferredByFilter`, `DatePreset`, `presetToRange(preset: DatePreset) -> {date_from, date_to}` — consumed by Tasks 9-11.

- [ ] **Step 1: Add the nav entry**

In `frontend/app/(admin)/_layout.tsx`, add to the `SECONDARY` array, right before the `team` entry:

```typescript
  { href: "/(admin)/sales-data", label: "Sales Data", icon: "trending-up", match: "sales-data" },
```

(No `roles:` array — that field isn't actually consulted for filtering anywhere in this file; visibility is driven entirely by `hasAccess(item.match)`, which reads the permission matrix registered in Task 6. Confirmed by grepping this file: `roles` only appears in the type definition and two dead array literals.)

- [ ] **Step 2: Create the shared API helper**

Create `frontend/src/components/salesData/salesDataApi.ts`:

```typescript
import dayjs from "dayjs";

export type Granularity = "day" | "month" | "quarter" | "year";
export type ReferredByFilter = "all" | "architect" | "interior_designer";
export type DatePreset = "today" | "this_month" | "this_quarter" | "this_year" | "all_time";

export type TrendPoint = { bucket: string; revenue: number };
export type OverviewResponse = {
  total_revenue: number;
  quotation_count: number;
  revenue_by_floor: { floor_id: string; revenue: number }[];
  trend: TrendPoint[];
  referrers: { referrer_id: string; name: string; revenue: number }[] | null;
};

export function presetToRange(preset: DatePreset): { date_from: string | null; date_to: string | null } {
  const now = dayjs();
  if (preset === "today") return { date_from: now.startOf("day").toISOString(), date_to: now.endOf("day").toISOString() };
  if (preset === "this_month") return { date_from: now.startOf("month").toISOString(), date_to: now.endOf("month").toISOString() };
  if (preset === "this_quarter") {
    const qStartMonth = Math.floor(now.month() / 3) * 3;
    const start = now.month(qStartMonth).startOf("month");
    return { date_from: start.toISOString(), date_to: start.add(3, "month").endOf("month").subtract(1, "month").endOf("month").toISOString() };
  }
  if (preset === "this_year") return { date_from: now.startOf("year").toISOString(), date_to: now.endOf("year").toISOString() };
  return { date_from: null, date_to: null }; // all_time
}

export const DATE_PRESET_LABEL: Record<DatePreset, string> = {
  today: "Today", this_month: "This Month", this_quarter: "This Quarter",
  this_year: "This Year", all_time: "All Time",
};
```

- [ ] **Step 3: Create the page shell**

Create `frontend/app/(admin)/sales-data/index.tsx`:

```typescript
import { Redirect } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { api } from "@/src/api/client";
import {
  EmptyState, ErrorState, LoadingState, PillTabs, SegmentedControl, Tabs,
} from "@/src/components/ui";
import { spacing } from "@/src/theme/tokens";
import { useAuth } from "@/src/state/auth";
import {
  DATE_PRESET_LABEL, DatePreset, Granularity, OverviewResponse, ReferredByFilter, presetToRange,
} from "@/src/components/salesData/salesDataApi";

type Floor = { id: string; name: string; slug: string };
type PageTab = "overview" | "brand";

export default function SalesData() {
  const { staff } = useAuth();

  // All hooks are declared unconditionally, in the same order every render —
  // the role check below is a plain `if` AFTER every hook call, never a
  // conditional `return` before one. An early return before a hook would
  // violate the Rules of Hooks: this component would call a different
  // number of hooks depending on `staff.role`, and React throws "Rendered
  // fewer hooks than expected" the next time it re-renders with a
  // different hook count.
  const [floors, setFloors] = useState<Floor[]>([]);
  const [floorId, setFloorId] = useState<string>("both");
  const [referredBy, setReferredBy] = useState<ReferredByFilter>("all");
  const [preset, setPreset] = useState<DatePreset>("this_month");
  const [granularity, setGranularity] = useState<Granularity>("month");
  const [tab, setTab] = useState<PageTab>("overview");

  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.get<Floor[]>("/settings/floors").then(setFloors).catch(() => setFloors([])); }, []);

  const load = useCallback(() => {
    setError(null);
    setOverview(null);
    const { date_from, date_to } = presetToRange(preset);
    const params = new URLSearchParams();
    if (floorId !== "both") params.set("floor_id", floorId);
    if (referredBy !== "all") params.set("referrer_type", referredBy);
    if (date_from) params.set("date_from", date_from);
    if (date_to) params.set("date_to", date_to);
    params.set("granularity", granularity);
    api.get<OverviewResponse>(`/sales-data/overview?${params.toString()}`)
      .then(setOverview)
      .catch((e: any) => setError(e?.detail || "Could not load sales data"));
  }, [floorId, referredBy, preset, granularity]);

  useEffect(() => { load(); }, [load]);

  if (staff && staff.role !== "owner" && staff.role !== "admin") {
    return <Redirect href="/(admin)/dashboard" />;
  }

  return (
    <AdminPage title="Sales Data" subtitle="Every sale, filtered by floor, referrer, and brand">
      <View style={{ gap: spacing.md }}>
        <SegmentedControl
          testID="sales-data-floor"
          value={floorId}
          onChange={setFloorId}
          options={[
            { value: "both", label: "Both" },
            ...floors.map((f) => ({ value: f.id, label: f.name })),
          ]}
        />
        <PillTabs
          testID="sales-data-referred-by"
          value={referredBy}
          onChange={setReferredBy}
          options={[
            { value: "all", label: "All" },
            { value: "architect", label: "Architect" },
            { value: "interior_designer", label: "Interior Designer" },
          ]}
        />
        <PillTabs
          testID="sales-data-preset"
          value={preset}
          onChange={setPreset}
          options={(Object.keys(DATE_PRESET_LABEL) as DatePreset[]).map((p) => ({ value: p, label: DATE_PRESET_LABEL[p] }))}
        />
        <SegmentedControl
          testID="sales-data-granularity"
          value={granularity}
          onChange={setGranularity}
          options={[
            { value: "day", label: "Day" }, { value: "month", label: "Month" },
            { value: "quarter", label: "Quarter" }, { value: "year", label: "Year" },
          ]}
        />
      </View>

      <Tabs
        testID="sales-data-tabs"
        value={tab}
        onChange={setTab}
        options={[{ value: "overview", label: "Overview" }, { value: "brand", label: "By Brand" }]}
      />

      {error ? <ErrorState subtitle={error} onRetry={load} /> : null}
      {!error && !overview ? <LoadingState label="Loading sales data…" /> : null}
      {!error && overview && overview.total_revenue === 0 ? (
        <EmptyState title="No sales in this range" subtitle="Try a wider date range or different filters." />
      ) : null}
      {/* Overview KPI cards, trend chart, and referrer list are added in Task 9-10.
          By Brand tab content is added in Task 11. */}
    </AdminPage>
  );
}
```

- [ ] **Step 4: Lint**

Run: `cd frontend && npx expo lint`
Expected: no new errors

- [ ] **Step 5: Manual verification**

As an owner/admin user, confirm "Sales Data" appears in the nav and the page loads with filters + tabs + an empty-state or loading state (no KPIs yet — that's Task 9). As a `sales`-role user, confirm the nav item is hidden and direct navigation to `/(admin)/sales-data` redirects to the dashboard.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/\(admin\)/_layout.tsx frontend/src/components/salesData frontend/app/\(admin\)/sales-data
git commit -m "feat: add Sales Data page shell with filters and role gate"
```

---

## Task 9: Overview tab — KPIs, trend chart, referrer ranking

**Files:**
- Create: `frontend/src/components/salesData/TrendChart.tsx`
- Modify: `frontend/app/(admin)/sales-data/index.tsx`

**Interfaces:**
- Consumes: `OverviewResponse` from Task 8's `salesDataApi.ts`.
- Produces: `<TrendChart points={TrendPoint[]} />` — reused by Tasks 10 and 11.

- [ ] **Step 1: Create `TrendChart.tsx`**

Create `frontend/src/components/salesData/TrendChart.tsx`:

```typescript
// Minimal bar-chart — no charting library exists anywhere in this codebase
// (grep confirms it), so this stays a plain View-based bar row rather than
// adding a new dependency for one chart.
import { Text, View } from "react-native";

import { fmtMoneyCompact } from "@/src/design/tokens";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

export function TrendChart({ points }: { points: { bucket: string; revenue: number }[] }) {
  if (points.length === 0) {
    return <Text style={[type.bodyMuted, { padding: spacing.lg, textAlign: "center" }]}>No data in this range</Text>;
  }
  const max = Math.max(...points.map((p) => p.revenue), 1);
  return (
    <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 6, height: 140, paddingHorizontal: spacing.md }}>
      {points.map((p) => (
        <View key={p.bucket} style={{ flex: 1, alignItems: "center", gap: 4 }}>
          <Text style={{ fontSize: 10, color: colors.onSurfaceMuted }} numberOfLines={1}>
            {fmtMoneyCompact(p.revenue)}
          </Text>
          <View
            style={{
              width: "100%",
              height: Math.max(4, (p.revenue / max) * 90),
              backgroundColor: colors.brand,
              borderRadius: radius.sm,
            }}
          />
          <Text style={{ fontSize: 9, color: colors.onSurfaceMuted }} numberOfLines={1}>{p.bucket}</Text>
        </View>
      ))}
    </View>
  );
}
```

- [ ] **Step 2: Render KPIs + chart + referrer list in the Overview tab**

In `frontend/app/(admin)/sales-data/index.tsx`:

Change the `expo-router` import from `import { Redirect } from "expo-router";` to:
```typescript
import { Redirect, useRouter } from "expo-router";
```

Extend the existing `@/src/components/ui` import (from Task 8) to also include `KpiCard, Table, TableHeader, TableRow, TableCell`:
```typescript
import {
  EmptyState, ErrorState, KpiCard, LoadingState, PillTabs, SegmentedControl, Table, TableCell,
  TableHeader, TableRow, Tabs,
} from "@/src/components/ui";
```

Add two new import lines:
```typescript
import { fmtMoney } from "@/src/design/tokens";
import { TrendChart } from "@/src/components/salesData/TrendChart";
```

Add `const router = useRouter();` alongside the other hooks at the top of the component.

Replace the closing comment block:
```typescript
      {/* Overview KPI cards, trend chart, and referrer list are added in Task 9-10.
          By Brand tab content is added in Task 11. */}
```
with:

```typescript
      {!error && overview && overview.total_revenue > 0 && tab === "overview" ? (
        <View style={{ gap: spacing.lg }}>
          <View style={{ flexDirection: "row", gap: spacing.md, flexWrap: "wrap" }}>
            {referredBy === "all" ? (
              <>
                <KpiCard label="Total Revenue" value={`₹${fmtMoney(overview.total_revenue)}`} style={{ flex: 1, minWidth: 160 }} />
                {overview.revenue_by_floor.map((f) => {
                  const floor = floors.find((fl) => fl.id === f.floor_id);
                  return (
                    <KpiCard
                      key={f.floor_id}
                      label={floor?.name || f.floor_id}
                      value={`₹${fmtMoney(f.revenue)}`}
                      style={{ flex: 1, minWidth: 160 }}
                    />
                  );
                })}
              </>
            ) : (
              // Referrer type selected — KPIs re-scope IN PLACE (same row,
              // same position) rather than the page restructuring, per the
              // approved design: Architect/Interior Designer Revenue, how
              // many people contributed, and the average deal size.
              <>
                <KpiCard
                  label={referredBy === "architect" ? "Architect Revenue" : "Interior Designer Revenue"}
                  value={`₹${fmtMoney(overview.total_revenue)}`}
                  style={{ flex: 1, minWidth: 160 }}
                />
                <KpiCard
                  label="# Active"
                  value={String(overview.referrers?.length || 0)}
                  style={{ flex: 1, minWidth: 160 }}
                />
                <KpiCard
                  label="Avg Deal Size"
                  value={`₹${fmtMoney(overview.quotation_count ? overview.total_revenue / overview.quotation_count : 0)}`}
                  style={{ flex: 1, minWidth: 160 }}
                />
              </>
            )}
          </View>
          <TrendChart points={overview.trend} />
          {overview.referrers ? (
            <Table>
              <TableHeader columns={[{ label: "Name", flex: 2 }, { label: "Revenue", align: "right" }]} />
              {overview.referrers.map((r, i) => (
                <TableRow
                  key={r.referrer_id}
                  isLast={i === overview.referrers!.length - 1}
                  onPress={() => router.push(`/(admin)/sales-data/referrer/${r.referrer_id}`)}
                  testID={`referrer-rank-row-${r.referrer_id}`}
                >
                  <TableCell flex={2}>{r.name}</TableCell>
                  <TableCell align="right">₹{fmtMoney(r.revenue)}</TableCell>
                </TableRow>
              ))}
            </Table>
          ) : null}
        </View>
      ) : null}
```

- [ ] **Step 3: Lint**

Run: `cd frontend && npx expo lint`
Expected: no new errors

- [ ] **Step 4: Manual verification**

Create a test quotation, set it to a Ground/First floor, mark it `won` (via the existing quotation status flow), and set a referrer on it via the picker from Task 7. Reload Sales Data with "This Month"/matching floor — confirm the KPI cards show the right totals, the trend chart renders a bar, and switching Referred By to Architect/Interior Designer shows the ranked list with the test referrer.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/salesData/TrendChart.tsx frontend/app/\(admin\)/sales-data/index.tsx
git commit -m "feat: render Sales Data Overview KPIs, trend chart, and referrer ranking"
```

---

## Task 10: Referrer detail screen

**Files:**
- Create: `frontend/app/(admin)/sales-data/referrer/[id].tsx`

**Interfaces:**
- Consumes: `GET /sales-data/referrers/{id}` from Task 4, `<TrendChart>` from Task 9.

- [ ] **Step 1: Create the screen**

Create `frontend/app/(admin)/sales-data/referrer/[id].tsx`:

```typescript
import { useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { api } from "@/src/api/client";
import {
  EmptyState, ErrorState, LoadingState, PillTabs, Table, TableCell, TableHeader, TableRow,
} from "@/src/components/ui";
import { fmtMoney } from "@/src/design/tokens";
import { spacing } from "@/src/theme/tokens";
import { TrendChart } from "@/src/components/salesData/TrendChart";
import { Granularity } from "@/src/components/salesData/salesDataApi";

type ReferrerDetail = {
  referrer: { id: string; name: string; type: string; phone?: string | null; company?: string | null };
  total_revenue: number;
  trend: { bucket: string; revenue: number }[];
  quotations: { id: string; number: string; customer_name: string; grand_total: number; updated_at: string | null }[];
};

export default function ReferrerDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [granularity, setGranularity] = useState<Granularity>("month");
  const [data, setData] = useState<ReferrerDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    setData(null);
    api.get<ReferrerDetail>(`/sales-data/referrers/${id}?granularity=${granularity}`)
      .then(setData)
      .catch((e: any) => setError(e?.detail || "Could not load referrer"));
  }, [id, granularity]);

  useEffect(() => { load(); }, [load]);

  return (
    <AdminPage title={data?.referrer.name || "Referrer"} subtitle={data ? `₹${fmtMoney(data.total_revenue)} total revenue` : undefined}>
      <PillTabs
        testID="referrer-detail-granularity"
        value={granularity}
        onChange={setGranularity}
        options={[
          { value: "day", label: "Day" }, { value: "month", label: "Month" },
          { value: "quarter", label: "Quarter" }, { value: "year", label: "Year" },
        ]}
      />
      {error ? <ErrorState subtitle={error} onRetry={load} /> : null}
      {!error && !data ? <LoadingState label="Loading…" /> : null}
      {data ? (
        <View style={{ gap: spacing.lg }}>
          <TrendChart points={data.trend} />
          {data.quotations.length === 0 ? (
            <EmptyState title="No won quotations in this range" />
          ) : (
            <Table>
              <TableHeader columns={[
                { label: "Number", flex: 1 }, { label: "Customer", flex: 2 }, { label: "Amount", align: "right" },
              ]} />
              {data.quotations.map((q, i) => (
                <TableRow key={q.id} isLast={i === data.quotations.length - 1} testID={`referrer-quote-row-${q.id}`}>
                  <TableCell flex={1}>{q.number}</TableCell>
                  <TableCell flex={2}>{q.customer_name}</TableCell>
                  <TableCell align="right">₹{fmtMoney(q.grand_total)}</TableCell>
                </TableRow>
              ))}
            </Table>
          )}
        </View>
      ) : null}
    </AdminPage>
  );
}
```

- [ ] **Step 2: Lint**

Run: `cd frontend && npx expo lint`
Expected: no new errors

- [ ] **Step 3: Manual verification**

From the Overview tab's ranked referrer list (Task 9), tap a person and confirm this screen loads their trend chart and quotations table, and that changing the granularity pills reloads the trend.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/\(admin\)/sales-data/referrer
git commit -m "feat: add referrer detail screen to Sales Data"
```

---

## Task 11: By Brand tab + brand detail screen

**Files:**
- Modify: `frontend/app/(admin)/sales-data/index.tsx`
- Create: `frontend/app/(admin)/sales-data/brand/[id].tsx`

**Interfaces:**
- Consumes: `GET /sales-data/brands` from Task 5, `GET /sales-data/brands/{id}` from Task 5, `<TrendChart>` from Task 9.

- [ ] **Step 1: Add brand list state + fetch to `index.tsx`**

Add the type:

```typescript
type BrandRow = { brand_id: string; brand_name: string; revenue: number };
```

Add state near the other `useState` calls:

```typescript
  const [brands, setBrands] = useState<BrandRow[] | null>(null);
  const [brandsError, setBrandsError] = useState<string | null>(null);
```

Add a load effect — brands respect the date range only, per the design spec, so this depends only on `preset`:

```typescript
  useEffect(() => {
    if (tab !== "brand") return;
    setBrandsError(null);
    setBrands(null);
    const { date_from, date_to } = presetToRange(preset);
    const params = new URLSearchParams();
    if (date_from) params.set("date_from", date_from);
    if (date_to) params.set("date_to", date_to);
    api.get<{ brands: BrandRow[] }>(`/sales-data/brands?${params.toString()}`)
      .then((res) => setBrands(res.brands))
      .catch((e: any) => setBrandsError(e?.detail || "Could not load brand revenue"));
  }, [tab, preset]);
```

- [ ] **Step 2: Render the By Brand tab**

Add right after the Overview tab's closing `) : null}` block (from Task 9, Step 2):

```typescript
      {tab === "brand" ? (
        <View style={{ gap: spacing.lg }}>
          {brandsError ? <ErrorState subtitle={brandsError} /> : null}
          {!brandsError && !brands ? <LoadingState label="Loading brand revenue…" /> : null}
          {brands && brands.length === 0 ? <EmptyState title="No brand revenue in this range" /> : null}
          {brands && brands.length > 0 ? (
            <Table>
              <TableHeader columns={[{ label: "Brand", flex: 2 }, { label: "Revenue", align: "right" }]} />
              {brands.map((b, i) => (
                <TableRow
                  key={b.brand_id}
                  isLast={i === brands.length - 1}
                  onPress={() => router.push(`/(admin)/sales-data/brand/${b.brand_id}`)}
                  testID={`brand-rank-row-${b.brand_id}`}
                >
                  <TableCell flex={2}>{b.brand_name}</TableCell>
                  <TableCell align="right">₹{fmtMoney(b.revenue)}</TableCell>
                </TableRow>
              ))}
            </Table>
          ) : null}
        </View>
      ) : null}
```

- [ ] **Step 3: Create the brand detail screen**

Create `frontend/app/(admin)/sales-data/brand/[id].tsx`:

```typescript
import { useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { api } from "@/src/api/client";
import {
  EmptyState, ErrorState, LoadingState, PillTabs, Table, TableCell, TableHeader, TableRow,
} from "@/src/components/ui";
import { fmtMoney } from "@/src/design/tokens";
import { spacing } from "@/src/theme/tokens";
import { TrendChart } from "@/src/components/salesData/TrendChart";
import { Granularity } from "@/src/components/salesData/salesDataApi";

type BrandDetail = {
  brand: { id: string; name: string };
  total_revenue: number;
  trend: { bucket: string; revenue: number }[];
  top_products: { product_id: string; name: string; sku: string; revenue: number }[];
};

export default function BrandDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [granularity, setGranularity] = useState<Granularity>("month");
  const [data, setData] = useState<BrandDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    setData(null);
    api.get<BrandDetail>(`/sales-data/brands/${id}?granularity=${granularity}`)
      .then(setData)
      .catch((e: any) => setError(e?.detail || "Could not load brand"));
  }, [id, granularity]);

  useEffect(() => { load(); }, [load]);

  return (
    <AdminPage title={data?.brand.name || "Brand"} subtitle={data ? `₹${fmtMoney(data.total_revenue)} total revenue` : undefined}>
      <PillTabs
        testID="brand-detail-granularity"
        value={granularity}
        onChange={setGranularity}
        options={[
          { value: "day", label: "Day" }, { value: "month", label: "Month" },
          { value: "quarter", label: "Quarter" }, { value: "year", label: "Year" },
        ]}
      />
      {error ? <ErrorState subtitle={error} onRetry={load} /> : null}
      {!error && !data ? <LoadingState label="Loading…" /> : null}
      {data ? (
        <View style={{ gap: spacing.lg }}>
          <TrendChart points={data.trend} />
          {data.top_products.length === 0 ? (
            <EmptyState title="No product revenue in this range" />
          ) : (
            <Table>
              <TableHeader columns={[
                { label: "Product", flex: 2 }, { label: "SKU", flex: 1 }, { label: "Revenue", align: "right" },
              ]} />
              {data.top_products.map((p, i) => (
                <TableRow key={p.product_id} isLast={i === data.top_products.length - 1} testID={`brand-product-row-${p.product_id}`}>
                  <TableCell flex={2}>{p.name}</TableCell>
                  <TableCell flex={1}>{p.sku}</TableCell>
                  <TableCell align="right">₹{fmtMoney(p.revenue)}</TableCell>
                </TableRow>
              ))}
            </Table>
          )}
        </View>
      ) : null}
    </AdminPage>
  );
}
```

- [ ] **Step 4: Lint**

Run: `cd frontend && npx expo lint`
Expected: no new errors

- [ ] **Step 5: Manual verification**

Switch to the By Brand tab, confirm ranked brands load for "This Month", tap a brand and confirm its trend + top products render. Switch the top-level date preset and confirm the By Brand tab's numbers change too (per the design decision that date range — but not Floor/Referred By — carries over to this tab).

- [ ] **Step 6: Commit**

```bash
git add frontend/app/\(admin\)/sales-data
git commit -m "feat: add By Brand tab and brand detail screen to Sales Data"
```

---

## Final check

- [ ] Run the full backend suite once more: `cd backend && python -m pytest tests/unit -v` — expect all green.
- [ ] Run `cd frontend && npx expo lint` from the repo root of `frontend/` — expect no new errors.
- [ ] Walk through the whole flow once end-to-end as an owner: create a quotation, set floor + a new architect referrer, mark it won, open Sales Data, confirm it shows up in Overview (Both floors, then filtered to that floor, then filtered to Architect), open that architect's detail screen, then check By Brand shows the products' brand(s).
- [ ] Confirm a `sales`-role login cannot see the nav item and gets redirected on direct navigation, and that a raw `curl` to `/api/sales-data/overview` with that role's token returns 403.
