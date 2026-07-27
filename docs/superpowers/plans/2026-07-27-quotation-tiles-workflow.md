# Quotation Tiles Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge Tiles Selection and Tiles Quotation into one "Quotation Tiles" nav tab driving a 4-stage workflow (Selection → Quotation → Confirmation → Order), plus customer/product history lookups and a tile-image aspect-ratio fix — all on top of the existing `doc_type`+`status` fields, no schema change.

**Architecture:** A Selection and its eventual Quotation are the *same* `Quotation` document throughout. A single pure-function helper (`services/tiles_stage.py` on the backend, `tilesStage.ts` on the frontend — kept in lockstep like `services/pricing.py` already is) derives the user-facing stage and next available action from `(doc_type, status)`, so nothing new is denormalized. A new dedicated endpoint (`POST /quotations/{id}/move-to-quotation`) performs the one stage transition that's more than a plain status edit. Two small read additions (`doc_type`/`customer_id` filters on `GET /quotations`, a customer+product history lookup) back the new list screen and history features. The image fix is a scoped, per-card style change — not a global one, since Catalog's image container is shared with sanitaryware.

**Tech Stack:** FastAPI + MongoDB (Motor) backend, Expo Router / React Native Web frontend, pytest for backend unit tests (no frontend test infra exists in this repo — frontend tasks end with `tsc --noEmit` + a manual browser-verification step instead).

**Design doc:** `docs/superpowers/specs/2026-07-27-quotation-tiles-workflow-design.md`

## Global Constraints

- Do not add a new `stage` field to the `Quotation` model or a new Mongo collection — the design's whole point is deriving stage from `doc_type`+`status` via one shared helper, not a third denormalized field (see spec's "Why not a dedicated `stage` field").
- All new/modified endpoints use the same role gate the rest of `routes/quotation_routes.py` already uses for writes: `Depends(require_min_role("sales"))`. Reads use `Depends(get_current_user)`. No new permission tier.
- The Confirmed-status gate on Place Order applies **only** to `doc_type == "tiles_quotation"` — standard (non-tiles) quotations keep today's behavior (no status gate on place-order) untouched.
- Frontend token imports: `@/src/theme/tokens` (`colors, radius, spacing, type, money`) exclusively, matching every existing file in `src/components/tiles/` and `app/(admin)/tiles/`. Do not import from `@/src/design/tokens`.
- Run backend tests with: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit -v`
- Run frontend typecheck with: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/frontend" && npx tsc --noEmit`
- The shared backend on `:8010` has no `--reload` — restart it (`kill` the `uvicorn` process, relaunch `.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8010`) before live-verifying any backend task, and ask the user first since it's a shared dev process.

---

## Task 1: Backend — tiles stage helper

**Files:**
- Create: `backend/services/tiles_stage.py`
- Test: `backend/tests/unit/test_tiles_stage.py`

**Interfaces:**
- Produces: `tiles_stage(doc_type: str, status: str) -> str`, `TILES_STAGE_LABELS: dict[str, str]`, `tiles_stage_label(doc_type: str, status: str) -> str`, `can_move_to_quotation(doc_type: str, status: str) -> bool`, `can_place_order(doc_type: str, status: str) -> bool`, `NEXT_TILES_STATUS: dict[str, str]`, `next_tiles_action(doc_type: str, status: str) -> dict | None`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_tiles_stage.py`:

```python
"""Pure-function tests for the tiles workflow stage helper — the single
source of truth mapping (doc_type, status) to a user-facing stage and the
next available workflow action. Mirrored in
frontend/src/components/tiles/tilesStage.ts; these two must never drift.
See docs/superpowers/specs/2026-07-27-quotation-tiles-workflow-design.md."""
from __future__ import annotations

import pytest

from services.tiles_stage import (
    can_move_to_quotation, can_place_order, next_tiles_action, tiles_stage, tiles_stage_label,
)


@pytest.mark.parametrize("doc_type,status,expected", [
    ("tiles_selection", "draft", "selection_draft"),
    ("tiles_selection", "pending_approval", "selection_pending_approval"),
    ("tiles_selection", "approved", "selection_approved"),
    ("tiles_quotation", "draft", "quotation_draft"),
    ("tiles_quotation", "pending_approval", "quotation_pending_approval"),
    ("tiles_quotation", "approved", "quotation_confirmed"),
    ("tiles_quotation", "ordered", "ordered"),
])
def test_tiles_stage_mapping(doc_type, status, expected):
    assert tiles_stage(doc_type, status) == expected


def test_tiles_stage_rejects_non_tiles_doc_type():
    with pytest.raises(ValueError):
        tiles_stage("standard", "draft")


def test_tiles_stage_label_is_human_readable():
    assert tiles_stage_label("tiles_selection", "approved") == "Selection — Approved"
    assert tiles_stage_label("tiles_quotation", "approved") == "Quotation — Confirmed"


def test_can_move_to_quotation_only_when_selection_approved():
    assert can_move_to_quotation("tiles_selection", "approved") is True
    assert can_move_to_quotation("tiles_selection", "draft") is False
    assert can_move_to_quotation("tiles_selection", "pending_approval") is False
    assert can_move_to_quotation("tiles_quotation", "approved") is False


def test_can_place_order_gates_tiles_quotation_on_confirmed_status():
    assert can_place_order("tiles_quotation", "approved") is True
    assert can_place_order("tiles_quotation", "draft") is False
    assert can_place_order("tiles_quotation", "pending_approval") is False


def test_can_place_order_never_gates_standard_quotations():
    # Regression guard: the new Confirmed-status gate must not change
    # behavior for the existing sanitaryware quotation flow.
    assert can_place_order("standard", "draft") is True
    assert can_place_order("standard", "pending_approval") is True


def test_next_tiles_action_selection_progression():
    assert next_tiles_action("tiles_selection", "draft") == {
        "label": "Submit for approval", "kind": "patch_status", "next_status": "pending_approval",
    }
    assert next_tiles_action("tiles_selection", "pending_approval") == {
        "label": "Approve", "kind": "patch_status", "next_status": "approved",
    }
    assert next_tiles_action("tiles_selection", "approved") == {
        "label": "Move to Quotation", "kind": "move_to_quotation", "next_status": None,
    }


def test_next_tiles_action_quotation_progression():
    assert next_tiles_action("tiles_quotation", "draft") == {
        "label": "Submit for confirmation", "kind": "patch_status", "next_status": "pending_approval",
    }
    assert next_tiles_action("tiles_quotation", "pending_approval") == {
        "label": "Confirm", "kind": "patch_status", "next_status": "approved",
    }


def test_next_tiles_action_none_when_nothing_left_to_do():
    assert next_tiles_action("tiles_quotation", "approved") is None
    assert next_tiles_action("tiles_quotation", "ordered") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_tiles_stage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.tiles_stage'`

- [ ] **Step 3: Write the implementation**

Create `backend/services/tiles_stage.py`:

```python
"""Single source of truth mapping a tiles document's (doc_type, status) to
its user-facing workflow stage and the next available workflow action.
Mirrored exactly in frontend/src/components/tiles/tilesStage.ts — these two
implementations must never drift, same discipline as services/pricing.py's
docstring for effective_discount_pct.

Deriving the stage from these two existing Quotation fields (instead of a
new denormalized field) means there is nothing that can drift out of sync
with the source of truth — see the design doc's "Why not a dedicated
`stage` field?" section.
"""
from __future__ import annotations


def tiles_stage(doc_type: str, status: str) -> str:
    if doc_type == "tiles_selection":
        if status == "approved":
            return "selection_approved"
        if status == "pending_approval":
            return "selection_pending_approval"
        return "selection_draft"
    if doc_type == "tiles_quotation":
        if status == "ordered":
            return "ordered"
        if status == "approved":
            return "quotation_confirmed"
        if status == "pending_approval":
            return "quotation_pending_approval"
        return "quotation_draft"
    raise ValueError(f"tiles_stage() called with non-tiles doc_type {doc_type!r}")


TILES_STAGE_LABELS: dict[str, str] = {
    "selection_draft": "Selection — Draft",
    "selection_pending_approval": "Selection — Awaiting approval",
    "selection_approved": "Selection — Approved",
    "quotation_draft": "Quotation — Draft",
    "quotation_pending_approval": "Quotation — Awaiting confirmation",
    "quotation_confirmed": "Quotation — Confirmed",
    "ordered": "Order placed",
}


def tiles_stage_label(doc_type: str, status: str) -> str:
    return TILES_STAGE_LABELS[tiles_stage(doc_type, status)]


def can_move_to_quotation(doc_type: str, status: str) -> bool:
    return doc_type == "tiles_selection" and status == "approved"


def can_place_order(doc_type: str, status: str) -> bool:
    """A tiles quotation must be Confirmed (status=="approved") before
    Place Order is allowed — the workflow's "Confirmation" stage. Standard
    (non-tiles) quotations are untouched by this gate."""
    if doc_type != "tiles_quotation":
        return True
    return status == "approved"


NEXT_TILES_STATUS: dict[str, str] = {
    "draft": "pending_approval",
    "pending_approval": "approved",
}


def next_tiles_action(doc_type: str, status: str) -> dict | None:
    """What the single workflow-action button in the builder topbar should
    do next, or None once there's nothing left (approved quotation —
    Place Order takes over — or an already-ordered document).
    Returns {"label": str, "kind": "patch_status" | "move_to_quotation",
    "next_status": str | None}."""
    if doc_type == "tiles_selection":
        if status == "draft":
            return {"label": "Submit for approval", "kind": "patch_status", "next_status": "pending_approval"}
        if status == "pending_approval":
            return {"label": "Approve", "kind": "patch_status", "next_status": "approved"}
        if status == "approved":
            return {"label": "Move to Quotation", "kind": "move_to_quotation", "next_status": None}
        return None
    if doc_type == "tiles_quotation":
        if status == "draft":
            return {"label": "Submit for confirmation", "kind": "patch_status", "next_status": "pending_approval"}
        if status == "pending_approval":
            return {"label": "Confirm", "kind": "patch_status", "next_status": "approved"}
        return None
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_tiles_stage.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/services/tiles_stage.py backend/tests/unit/test_tiles_stage.py && git commit -m "feat: add tiles workflow stage helper (doc_type+status -> stage/next action)"
```

---

## Task 2: Backend — Move to Quotation endpoint + Confirmed-status gate on Place Order

**Files:**
- Modify: `backend/routes/quotation_routes.py` (imports at line 10-19; new endpoint after `duplicate_quotation`, currently ending line 432; `place_order_preview` at line 719-724; `place_order_confirm` at line 727-763)
- Test: `backend/tests/unit/test_tiles_move_to_quotation.py`

**Interfaces:**
- Consumes: `can_move_to_quotation`, `can_place_order` (Task 1)
- Produces: `POST /quotations/{quotation_id}/move-to-quotation`, route function `move_to_quotation`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_tiles_move_to_quotation.py`:

```python
"""Move to Quotation: promotes an approved Tiles Selection into the
Quotation stage. Metadata-only — doc_type flips, status resets to draft,
`items` untouched (everything already filled in at Selection carries over
automatically; fields Selection never collects stay absent/open). Also
covers the new Confirmed-status gate on place_order_preview — the same gate
in place_order_confirm runs inside a real Mongo transaction
(client.start_session()), which isn't worth faking here; it's verified live
in Task 12 instead, since it's the exact same can_place_order() call on the
exact same doc shape."""
from __future__ import annotations

import asyncio

import pytest

from fastapi import HTTPException
from models import UserPublic
import routes.quotation_routes as quotation_routes


def _user() -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales Rep", role="sales",
        floor_ids=["ground-floor"], active_floor_id="ground-floor",
    )


class _Recorder:
    def __init__(self, doc: dict | None):
        self._doc = doc
        self.updates: list[dict] = []

    async def find_one(self, query, *_args, **_kwargs):
        if self._doc is None:
            return None
        # Support both {"id": ...} lookups (get_floor_scoped_or_404) and the
        # post-update re-fetch in the same shape this codebase uses elsewhere.
        return dict(self._doc)

    async def update_one(self, _query, update, **_kwargs):
        self.updates.append(update)
        if "$set" in update:
            self._doc.update(update["$set"])


class _FakeDb:
    def __init__(self, doc: dict | None):
        self.quotations = _Recorder(doc)


def _selection_doc(status: str = "approved") -> dict:
    return {
        "id": "q-1", "number": "FQ-2026-0100", "doc_type": "tiles_selection",
        "status": status, "floor_id": "ground-floor", "customer_id": "cust-1",
        "items": [{"id": "line-1", "product_id": "prod-1", "sku": "SKU-1", "name": "Tile A", "room": "Living", "qty": 1, "unit_price": 0}],
    }


def test_move_to_quotation_flips_doc_type_and_resets_status(monkeypatch):
    fake_db = _FakeDb(_selection_doc("approved"))
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    result = asyncio.run(quotation_routes.move_to_quotation("q-1", user=_user()))

    assert result["doc_type"] == "tiles_quotation"
    assert result["status"] == "draft"
    # Promotion is metadata-only — items carried over byte-for-byte, nothing transformed.
    assert result["items"] == _selection_doc("approved")["items"]


def test_move_to_quotation_rejects_when_not_a_selection(monkeypatch):
    doc = _selection_doc("approved")
    doc["doc_type"] = "tiles_quotation"
    fake_db = _FakeDb(doc)
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(quotation_routes.move_to_quotation("q-1", user=_user()))
    assert exc.value.status_code == 400


def test_move_to_quotation_rejects_when_not_approved(monkeypatch):
    fake_db = _FakeDb(_selection_doc("draft"))
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(quotation_routes.move_to_quotation("q-1", user=_user()))
    assert exc.value.status_code == 400


def test_place_order_preview_rejects_unconfirmed_tiles_quotation(monkeypatch):
    doc = {
        "id": "q-2", "number": "FQ-2026-0101", "doc_type": "tiles_quotation",
        "status": "draft", "floor_id": "ground-floor", "customer_id": "cust-1",
        "items": [{"id": "line-1", "product_id": "prod-1", "sku": "SKU-1", "name": "Tile A", "qty": 1, "unit_price": 100}],
    }
    fake_db = _FakeDb(doc)
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(quotation_routes.place_order_preview("q-2", user=_user()))
    assert exc.value.status_code == 400
    assert "confirm" in exc.value.detail.lower()


def test_place_order_preview_allows_confirmed_tiles_quotation(monkeypatch):
    doc = {
        "id": "q-3", "number": "FQ-2026-0102", "doc_type": "tiles_quotation",
        "status": "approved", "floor_id": "ground-floor", "customer_id": "cust-1",
        "items": [],
    }
    fake_db = _FakeDb(doc)
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    # Empty items still 400s (pre-existing "no items" guard) — proves we
    # reached PAST the new confirmed-status check, not that everything passes.
    with pytest.raises(HTTPException) as exc:
        asyncio.run(quotation_routes.place_order_preview("q-3", user=_user()))
    assert "no items" in exc.value.detail.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_tiles_move_to_quotation.py -v`
Expected: FAIL with `AttributeError: module 'routes.quotation_routes' has no attribute 'move_to_quotation'`

- [ ] **Step 3: Write the implementation**

In `backend/routes/quotation_routes.py`, update the imports (currently lines 10-19) to add the new module:

```python
from auth import (
    accessible_floor_ids, floor_for_write, floor_query, get_current_customer, get_current_user,
    get_floor_scoped_or_404, require_min_role,
)
from db import db
from models import (
    CustomerPublic, PurchaseOrder, PurchaseOrderItem, PurchaseStatusEvent, PurchaseStageEvent,
    Quotation, QuotationCreate, QuotationLineItem, QuotationRevision,
    QuotationUpdate, RoomDiscountCfg, UserPublic, now_iso,
)
from pdf_generator import build_quotation_pdf
from pdf_tiles import build_tiles_quotation_pdf, build_tiles_selection_pdf, tiles_pdf_filename
from services import catalog_service
from services.activity_log import log_event
from services.domain_outbox import (
    EVENT_ORDER_PLACED,
    EVENT_QUOTATION_GENERATED,
    dispatch_event,
    enqueue_after_primary_commit,
)
from services.followup_engine import reconcile_followups
from services.pricing import effective_discount_pct as _effective_discount_pct
from services.pricing import per_line_net_amounts
from services.pricing import recalc_quotation_totals as _recalc
from services.sequence import next_number
from services.tiles_stage import can_move_to_quotation, can_place_order
```

(Only the last line is new — `from services.tiles_stage import can_move_to_quotation, can_place_order`.)

Then, immediately after `duplicate_quotation` (currently ending at line 432, right before the `# --- Breakdown` comment on line 435), insert:

```python
@router.post("/{quotation_id}/move-to-quotation", response_model=Quotation)
async def move_to_quotation(
    quotation_id: str,
    user: UserPublic = Depends(require_min_role("sales")),
):
    """Promote an approved Tiles Selection into the Quotation stage — see
    docs/superpowers/specs/2026-07-27-quotation-tiles-workflow-design.md.
    Metadata-only: doc_type flips, status resets to draft for a fresh
    pricing pass. `items` (products/area/size/rate_sqft already entered) is
    left completely untouched so everything already filled in at Selection
    carries over automatically — there is nothing to copy, it's the same
    array on the same document."""
    doc = await get_floor_scoped_or_404(
        db.quotations, quotation_id, user, not_found="Quotation not found", projection={"_id": 0},
    )
    if not can_move_to_quotation(doc.get("doc_type", ""), doc.get("status", "")):
        raise HTTPException(
            status_code=400,
            detail="Only an approved Tiles Selection can be moved to the Quotation stage",
        )
    await db.quotations.update_one(
        {"id": quotation_id},
        {"$set": {"doc_type": "tiles_quotation", "status": "draft", "updated_at": now_iso()}},
    )
    fresh = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    return fresh


```

Then modify `place_order_preview` (currently lines 719-724):

```python
@router.get("/{quotation_id}/place-order/preview")
async def place_order_preview(quotation_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    doc = await get_floor_scoped_or_404(db.quotations, quotation_id, user, not_found="Quotation not found", projection={"_id": 0})
    if not can_place_order(doc.get("doc_type", "standard"), doc.get("status", "draft")):
        raise HTTPException(status_code=400, detail="Confirm the quotation before placing the order")
    if not doc.get("items"):
        raise HTTPException(status_code=400, detail="Cannot place order — quotation has no items")
    return await _brand_grouped_preview(doc)
```

Then modify `place_order_confirm` (currently lines 727-742) — add the same check right after the `doc` fetch inside the transaction, before the existing items check:

```python
                    doc = await get_floor_scoped_or_404(
                        db.quotations, quotation_id, user, not_found="Quotation not found",
                        projection={"_id": 0}, session=session,
                    )
                    if not can_place_order(doc.get("doc_type", "standard"), doc.get("status", "draft")):
                        raise HTTPException(status_code=400, detail="Confirm the quotation before placing the order")
                    if not doc.get("items"):
                        raise HTTPException(status_code=400, detail="Cannot place order — quotation has no items")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_tiles_move_to_quotation.py -v`
Expected: PASS (5 tests)

Then run the full unit suite to confirm nothing existing broke (the Confirmed-status gate must not affect standard quotations):
Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/routes/quotation_routes.py backend/tests/unit/test_tiles_move_to_quotation.py && git commit -m "feat: add Move-to-Quotation endpoint and Confirmed-status gate on tiles Place Order"
```

---

## Task 3: Backend — `doc_type` filter on `GET /quotations`

**Files:**
- Modify: `backend/routes/quotation_routes.py` (`list_quotations`, currently lines 76-79)
- Test: `backend/tests/unit/test_quotations_list_filters.py`

**Interfaces:**
- Produces: `list_quotations(doc_type: str | None = None, user: UserPublic = ...)` — same route, same response shape, one new optional query param

Note: no `customer_id` filter — the customer detail page (Task 9) already
fetches all quotations and filters client-side by `customer_id`
(`app/(admin)/customers/[id].tsx` line 98); adding a redundant server-side
filter nothing in this plan would call is unnecessary surface area (YAGNI).
Only `doc_type` is added, which the new Quotation Tiles list (Task 8)
genuinely needs.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_quotations_list_filters.py`:

```python
"""GET /quotations gains an optional doc_type filter — backs the new
Quotation Tiles list screen (doc_type=tiles_selection or tiles_quotation).
Omitting it must keep today's "everything the caller's floor scope allows"
behavior."""
from __future__ import annotations

import asyncio

from models import UserPublic
import routes.quotation_routes as quotation_routes


def _user() -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales Rep", role="sales",
        floor_ids=["ground-floor"], active_floor_id="ground-floor",
    )


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def sort(self, *_a, **_kw):
        return self

    async def to_list(self, _n):
        return self._rows


class _Recorder:
    def __init__(self):
        self.last_query = None

    def find(self, query, *_a, **_kw):
        self.last_query = query
        return _Cursor([])


class _FakeDb:
    def __init__(self):
        self.quotations = _Recorder()


def test_list_quotations_with_no_filter_unchanged(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    asyncio.run(quotation_routes.list_quotations(user=_user()))

    assert "doc_type" not in fake_db.quotations.last_query


def test_list_quotations_filters_by_doc_type(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    asyncio.run(quotation_routes.list_quotations(doc_type="tiles_selection", user=_user()))

    assert fake_db.quotations.last_query["doc_type"] == "tiles_selection"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_quotations_list_filters.py -v`
Expected: FAIL with `TypeError: list_quotations() got an unexpected keyword argument 'doc_type'`

- [ ] **Step 3: Write the implementation**

In `backend/routes/quotation_routes.py`, replace `list_quotations` (currently lines 76-79):

```python
@router.get("")
async def list_quotations(
    doc_type: str | None = None,
    user: UserPublic = Depends(get_current_user),
):
    query: dict = {}
    if doc_type:
        query["doc_type"] = doc_type
    docs = await db.quotations.find(floor_query(user, query), {"_id": 0}).sort("created_at", -1).to_list(500)
    return docs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_quotations_list_filters.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/routes/quotation_routes.py backend/tests/unit/test_quotations_list_filters.py && git commit -m "feat: add doc_type filter to GET /quotations"
```

---

## Task 4: Backend — customer + product tile history lookup

**Files:**
- Modify: `backend/routes/quotation_routes.py` (new endpoint after the `move-to-quotation` endpoint added in Task 2)
- Test: `backend/tests/unit/test_tiles_product_history.py`

**Interfaces:**
- Produces: `GET /quotations/tiles/product-history?customer_id=...&product_id=...`, route function `tiles_product_history`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_tiles_product_history.py`:

```python
"""Customer + product tile history lookup — powers the product picker's
"used last time" hint. Returns the most recent match only, across both
Selection and Quotation documents for that customer, scoped to the exact
product. `GET /quotations/tiles/product-history` has two extra path
segments vs. `GET /quotations/{quotation_id}` (one segment) so there is no
FastAPI routing collision regardless of registration order."""
from __future__ import annotations

import asyncio

from models import UserPublic
import routes.quotation_routes as quotation_routes


def _user() -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales Rep", role="sales",
        floor_ids=["ground-floor"], active_floor_id="ground-floor",
    )


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def sort(self, *_a, **_kw):
        return self

    async def to_list(self, _n):
        return self._rows


class _Recorder:
    def __init__(self, rows):
        self._rows = rows

    def find(self, *_a, **_kw):
        return _Cursor(self._rows)


class _FakeDb:
    def __init__(self, rows):
        self.quotations = _Recorder(rows)


def test_product_history_returns_most_recent_match():
    older = {
        "number": "FQ-2026-0010", "created_at": "2026-01-01T00:00:00+00:00", "doc_date": "01-Jan-26",
        "items": [{"product_id": "prod-1", "size": "600X1200", "rate_sqft": 100, "unit_price": 200, "pcs_per_box": "BOX"}],
    }
    newer = {
        "number": "FQ-2026-0050", "created_at": "2026-06-01T00:00:00+00:00", "doc_date": "01-Jun-26",
        "items": [{"product_id": "prod-1", "size": "1200X1800", "rate_sqft": 135, "unit_price": 220, "pcs_per_box": "BOX"}],
    }
    fake_db = _FakeDb([newer, older])  # find(...).sort(created_at, -1) already returns newest-first

    import routes.quotation_routes as qr
    result = asyncio.run(qr.tiles_product_history(customer_id="cust-1", product_id="prod-1", user=_user()))

    assert result == {
        "found": True, "quotation_number": "FQ-2026-0050", "doc_date": "01-Jun-26",
        "size": "1200X1800", "rate_sqft": 135, "rate_box": 220, "pcs_per_box": "BOX",
    }


def test_product_history_not_found_when_no_match():
    fake_db = _FakeDb([])

    import routes.quotation_routes as qr
    result = asyncio.run(qr.tiles_product_history(customer_id="cust-1", product_id="prod-1", user=_user()))

    assert result == {"found": False}
```

Note: assign `monkeypatch.setattr(quotation_routes, "db", fake_db)` in each test (omitted above for brevity in the fixture description, but required — see Step 3's exact test file for the real version below).

Actually write the real file with `monkeypatch` wired in both tests:

```python
"""Customer + product tile history lookup — powers the product picker's
"used last time" hint. Returns the most recent match only, across both
Selection and Quotation documents for that customer, scoped to the exact
product. GET /quotations/tiles/product-history has two extra path segments
vs. GET /quotations/{quotation_id} (one segment) so there is no FastAPI
routing collision regardless of registration order."""
from __future__ import annotations

import asyncio

from models import UserPublic
import routes.quotation_routes as quotation_routes


def _user() -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales Rep", role="sales",
        floor_ids=["ground-floor"], active_floor_id="ground-floor",
    )


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def sort(self, *_a, **_kw):
        return self

    async def to_list(self, _n):
        return self._rows


class _Recorder:
    def __init__(self, rows):
        self._rows = rows

    def find(self, *_a, **_kw):
        return _Cursor(self._rows)


class _FakeDb:
    def __init__(self, rows):
        self.quotations = _Recorder(rows)


def test_product_history_returns_most_recent_match(monkeypatch):
    newer = {
        "number": "FQ-2026-0050", "created_at": "2026-06-01T00:00:00+00:00", "doc_date": "01-Jun-26",
        "items": [{"product_id": "prod-1", "size": "1200X1800", "rate_sqft": 135, "unit_price": 220, "pcs_per_box": "BOX"}],
    }
    fake_db = _FakeDb([newer])
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    result = asyncio.run(quotation_routes.tiles_product_history(customer_id="cust-1", product_id="prod-1", user=_user()))

    assert result == {
        "found": True, "quotation_number": "FQ-2026-0050", "doc_date": "01-Jun-26",
        "size": "1200X1800", "rate_sqft": 135, "rate_box": 220, "pcs_per_box": "BOX",
    }


def test_product_history_not_found_when_no_match(monkeypatch):
    fake_db = _FakeDb([])
    monkeypatch.setattr(quotation_routes, "db", fake_db)

    result = asyncio.run(quotation_routes.tiles_product_history(customer_id="cust-1", product_id="prod-1", user=_user()))

    assert result == {"found": False}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_tiles_product_history.py -v`
Expected: FAIL with `AttributeError: module 'routes.quotation_routes' has no attribute 'tiles_product_history'`

- [ ] **Step 3: Write the implementation**

In `backend/routes/quotation_routes.py`, immediately after the `move_to_quotation` endpoint added in Task 2, add:

```python
@router.get("/tiles/product-history")
async def tiles_product_history(
    customer_id: str, product_id: str,
    user: UserPublic = Depends(get_current_user),
):
    """Most recent tiles line item this customer had for this exact
    product, across any Selection/Quotation (any stage) — powers the
    product picker's "used last time" hint."""
    docs = await db.quotations.find(
        floor_query(user, {
            "customer_id": customer_id,
            "doc_type": {"$in": ["tiles_selection", "tiles_quotation"]},
            "items.product_id": product_id,
        }),
        {"_id": 0, "number": 1, "doc_date": 1, "created_at": 1, "items": 1},
    ).sort("created_at", -1).to_list(20)
    for doc in docs:
        for item in doc.get("items", []):
            if item.get("product_id") == product_id:
                return {
                    "found": True,
                    "quotation_number": doc.get("number"),
                    "doc_date": doc.get("doc_date") or doc.get("created_at"),
                    "size": item.get("size"),
                    "rate_sqft": item.get("rate_sqft"),
                    "rate_box": item.get("unit_price"),
                    "pcs_per_box": item.get("pcs_per_box"),
                }
    return {"found": False}


```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_tiles_product_history.py -v`
Expected: PASS (2 tests)

Then run the full unit suite:
Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/routes/quotation_routes.py backend/tests/unit/test_tiles_product_history.py && git commit -m "feat: add customer+product tile history lookup endpoint"
```

---

## Task 5: Backend — `floor_id` on family-group catalog aggregation

**Files:**
- Modify: `backend/services/catalog_service.py` (`list_family_groups`, the `groups.setdefault(...)` dict currently at lines 616-629)
- Test: `backend/tests/unit/test_catalog_family_groups_floor_id.py`

**Interfaces:**
- Produces: each dict returned by `list_family_groups()`'s `families` list now includes `floor_id: str | None`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_catalog_family_groups_floor_id.py`:

```python
"""Family-group cards (Catalog's default grouped view) must carry floor_id
so the frontend can tell tile families from sanitaryware ones without a
second request — needed for the per-card landscape image fix (tile photos
only), since "All floors" merges both kinds of product in one list."""
from __future__ import annotations

import asyncio

import services.catalog_service as catalog_service


class _FakeSnapshot:
    products = [
        {
            "id": "p1", "sku": "SKU-1", "name": "Tile A", "family_key": "fam-1",
            "family_name": "Tile A Family", "brand_id": "b1", "category_id": "c1",
            "price": 100, "mrp": 120, "images": [], "floor_id": "ground-floor",
        },
    ]
    # list_family_groups also reads these two unconditionally (the media
    # lookup pass after pagination) — required or the real function raises
    # AttributeError on this fake.
    media_rows_by_product = {}
    media_rows_by_family = {}


def test_family_groups_include_floor_id(monkeypatch):
    async def _fake_snapshot():
        return _FakeSnapshot()

    monkeypatch.setattr(catalog_service, "get_catalog_snapshot", _fake_snapshot)

    result = asyncio.run(catalog_service.list_family_groups(
        brand_id=None, category_id=None, subcategory=None, series=None, q=None,
        limit=60, skip=0, floor_ids=None,
    ))

    # list_family_groups returns {"total": ..., "items": [...]} — not "families".
    assert result["items"][0]["floor_id"] == "ground-floor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_catalog_family_groups_floor_id.py -v`
Expected: FAIL with `KeyError: 'floor_id'`

- [ ] **Step 3: Write the implementation**

In `backend/services/catalog_service.py`, inside `list_family_groups`, find the `groups.setdefault(key, {...})` call (currently lines 616-629) and add one line:

```python
        group = groups.setdefault(key, {
            "family_key": key,
            "family_name": product.get("family_name"),
            "brand_id": product.get("brand_id"),
            "category_id": product.get("category_id"),
            "subcategory": product.get("subcategory"),
            "series": product.get("series"),
            "floor_id": product.get("floor_id"),
            "min_price": float(product.get("price") or 0),
            "max_price": float(product.get("price") or 0),
            "product_count": 0,
            "sample_image": (product.get("images") or [None])[0],
            "sample_image_quality": product.get("image_quality"),
            "variants": [],
        })
```

(Only the `"floor_id": product.get("floor_id"),` line is new.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_catalog_family_groups_floor_id.py -v`
Expected: PASS (1 test)

Then run the full unit suite:
Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/services/catalog_service.py backend/tests/unit/test_catalog_family_groups_floor_id.py && git commit -m "feat: include floor_id on catalog family-group cards"
```

---

## Task 6: Frontend — `tilesStage.ts` (TS mirror)

**Files:**
- Create: `frontend/src/components/tiles/tilesStage.ts`

**Interfaces:**
- Consumes: nothing (pure functions, no imports)
- Produces: `TilesStage` (type), `tilesStage(docType: string, status: string): TilesStage`, `TILES_STAGE_LABELS: Record<TilesStage, string>`, `tilesStageLabel(docType: string, status: string): string`, `canMoveToQuotation(docType: string, status: string): boolean`, `canPlaceOrder(docType: string, status: string): boolean`, `NextTilesAction` (type), `nextTilesAction(docType: string, status: string): NextTilesAction | null`

No automated test — this repo has no frontend test infrastructure (confirmed: no jest/testing-library anywhere). Correctness is verified by `tsc --noEmit` (Step 2) and by Task 7/8 actually using every exported function.

- [ ] **Step 1: Write the implementation**

Create `frontend/src/components/tiles/tilesStage.ts`:

```typescript
// Single source of truth mapping a tiles document's (doc_type, status) to
// its user-facing workflow stage and next available action. Mirrored
// exactly in backend/services/tiles_stage.py — these two implementations
// must never drift. See
// docs/superpowers/specs/2026-07-27-quotation-tiles-workflow-design.md.

export type TilesStage =
  | "selection_draft" | "selection_pending_approval" | "selection_approved"
  | "quotation_draft" | "quotation_pending_approval" | "quotation_confirmed"
  | "ordered";

export function tilesStage(docType: string, status: string): TilesStage {
  if (docType === "tiles_selection") {
    if (status === "approved") return "selection_approved";
    if (status === "pending_approval") return "selection_pending_approval";
    return "selection_draft";
  }
  if (status === "ordered") return "ordered";
  if (status === "approved") return "quotation_confirmed";
  if (status === "pending_approval") return "quotation_pending_approval";
  return "quotation_draft";
}

export const TILES_STAGE_LABELS: Record<TilesStage, string> = {
  selection_draft: "Selection — Draft",
  selection_pending_approval: "Selection — Awaiting approval",
  selection_approved: "Selection — Approved",
  quotation_draft: "Quotation — Draft",
  quotation_pending_approval: "Quotation — Awaiting confirmation",
  quotation_confirmed: "Quotation — Confirmed",
  ordered: "Order placed",
};

export function tilesStageLabel(docType: string, status: string): string {
  return TILES_STAGE_LABELS[tilesStage(docType, status)];
}

export function canMoveToQuotation(docType: string, status: string): boolean {
  return docType === "tiles_selection" && status === "approved";
}

export function canPlaceOrder(docType: string, status: string): boolean {
  if (docType !== "tiles_quotation") return true;
  return status === "approved";
}

export type NextTilesAction = {
  label: string;
  kind: "patch_status" | "move_to_quotation";
  nextStatus: string | null;
};

export function nextTilesAction(docType: string, status: string): NextTilesAction | null {
  if (docType === "tiles_selection") {
    if (status === "draft") return { label: "Submit for approval", kind: "patch_status", nextStatus: "pending_approval" };
    if (status === "pending_approval") return { label: "Approve", kind: "patch_status", nextStatus: "approved" };
    if (status === "approved") return { label: "Move to Quotation", kind: "move_to_quotation", nextStatus: null };
    return null;
  }
  if (docType === "tiles_quotation") {
    if (status === "draft") return { label: "Submit for confirmation", kind: "patch_status", nextStatus: "pending_approval" };
    if (status === "pending_approval") return { label: "Confirm", kind: "patch_status", nextStatus: "approved" };
    return null;
  }
  return null;
}
```

- [ ] **Step 2: Run typecheck to verify it compiles**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/frontend" && npx tsc --noEmit`
Expected: no new errors (pre-existing unrelated `TileOrderCard.tsx:107` error may still be present — that predates this work, see memory)

- [ ] **Step 3: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add frontend/src/components/tiles/tilesStage.ts && git commit -m "feat: add frontend tiles workflow stage helper (mirrors backend)"
```

---

## Task 7: Frontend — workflow-action button + Confirmed-gated Place Order in the builder

**Files:**
- Modify: `frontend/src/components/tiles/TilesDocBuilder.tsx` (`useTilesDoc`'s state block at lines 139-153; the restore-effect at lines 160-207; new callback after `placeOrder` at line 413; topbar render in `TilesDocBuilder` component, lines 1048-1113)

**Interfaces:**
- Consumes: `tilesStage`, `nextTilesAction`, `canPlaceOrder` (Task 6)
- Produces: `useTilesDoc()` return value gains `status: string`, `stage: TilesStage`, `workflowAction: NextTilesAction | null`, `runWorkflowAction: () => Promise<void>`

- [ ] **Step 1: Add `status` state and load it from the fetched document**

In `frontend/src/components/tiles/TilesDocBuilder.tsx`, add the import (near the top with the other local imports, after the `TilesProductPicker` import):

```typescript
import { canPlaceOrder, nextTilesAction, tilesStage } from "./tilesStage";
```

In `useTilesDoc` (currently starting line 136), add one line of state right after `docNumberServer` (currently line 140):

```typescript
  const [docNumberServer, setDocNumberServer] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("draft");
```

In the restore-effect (currently lines 160-207), set `status` from the fetched doc — add right after `setDocNumberServer(doc.number || null);` (currently line 168):

```typescript
        setDocNumberServer(doc.number || null);
        setStatus(doc.status || "draft");
```

- [ ] **Step 2: Add the workflow-action runner**

Immediately after `placeOrder` (currently ending line 413, right before `pickCustomer`), add:

```typescript
  const workflowAction = nextTilesAction(docType, status);

  const runWorkflowAction = useCallback(async () => {
    const action = nextTilesAction(docType, status);
    if (!action) return;
    setBusy("workflow");
    try {
      if (action.kind === "move_to_quotation") {
        const id = await persist({ silent: true });
        if (!id) return;
        const updated = await api.post<{ id: string; doc_type: string; status: string }>(`/quotations/${id}/move-to-quotation`);
        toast.success("Moved to Quotation");
        // Move-to-Quotation changes doc_type; the route file (selection.tsx
        // vs quotation.tsx) is what picks Selection vs Quotation paper, so
        // navigate to the sibling route for the same id.
        router.replace(`/(admin)/tiles/quotation?id=${updated.id}` as any);
        return;
      }
      const id = await persist({ silent: true });
      if (!id) return;
      const updated = await api.patch<{ status: string }>(`/quotations/${id}`, { status: action.nextStatus });
      setStatus(updated.status);
      toast.success(action.label === "Approve" || action.label === "Confirm" ? `${action.label}d` : "Submitted");
    } catch (e: any) {
      toast.error(e?.detail || "Couldn't update the workflow stage");
    } finally {
      setBusy(null);
    }
  }, [docType, status, persist, router]);
```

- [ ] **Step 3: Gate Place Order on Confirmed status (client-side, matching the new server-side gate from Task 2)**

Still inside `placeOrder` (currently lines 403-413), add the status check right after the existing `buildItems().length` check:

```typescript
  const placeOrder = useCallback(async () => {
    setBusy("order");
    const id = await persist({ silent: true });
    setBusy(null);
    if (!id) return;
    if (!buildItems().length) {
      toast.show("Add at least one product first");
      return;
    }
    if (!canPlaceOrder(docType, status)) {
      toast.show("Confirm the quotation before placing the order");
      return;
    }
    router.push(`/(admin)/quotations/${id}/place-order` as any);
  }, [persist, buildItems, router, docType, status]);
```

- [ ] **Step 4: Expose the new state from `useTilesDoc`'s return value**

Replace `useTilesDoc`'s return statement (currently lines 422-427):

```typescript
  return {
    docId, docNumberServer, loading, header, setHeaderField, rows,
    updateRow, addRow, removeRow, applyProduct,
    customers, customerId, pickCustomer, setCustomerId,
    saveState, busy, save, generatePdf, print, placeOrder,
    status, stage: tilesStage(docType, status), workflowAction, runWorkflowAction,
  };
```

(Only the last line — `status, stage: ..., workflowAction, runWorkflowAction,` — is new; every existing field is kept exactly as-is.)

- [ ] **Step 5: Render the workflow-action button in the topbar**

In the `TilesDocBuilder` component (currently lines 1048-1113), find the `<View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>` block that renders `Save` / `Selection|Quotation` / `Print|Place Order` (currently lines 1072-1093) and add the new button first, before `Save`:

```typescript
        <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
          {doc.workflowAction ? (
            <ActionBtn
              label={doc.workflowAction.label}
              icon={doc.workflowAction.kind === "move_to_quotation" ? "arrow-right-circle" : "check-circle"}
              onPress={doc.runWorkflowAction}
              loading={doc.busy === "workflow"}
              testID="tiles-workflow-action"
            />
          ) : null}
          <ActionBtn
            label={saveLabel}
            icon="save"
            onPress={doc.save}
            loading={doc.busy === "save"}
            testID="tiles-save"
          />
```

(Everything after this — the existing `Save`/`Selection|Quotation`/`Print|Place Order` buttons — stays exactly as it is today.)

- [ ] **Step 6: Run typecheck**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/frontend" && npx tsc --noEmit`
Expected: no new errors

- [ ] **Step 7: Live-verify**

Ask the user before restarting the shared `:8010` backend (per Global Constraints), then in the browser: open Tiles Selection, add a product, confirm "Submit for approval" appears and works, then "Approve", then "Move to Quotation" (confirm it navigates to `/tiles/quotation?id=...` showing the Quotation paper with the same product already there), then "Submit for confirmation" → "Confirm", then confirm "Place Order" now works (it was silently gated before Confirm — try clicking it while still in Draft/Awaiting-confirmation first and confirm the "Confirm the quotation before placing the order" toast appears instead of navigating).

- [ ] **Step 8: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add frontend/src/components/tiles/TilesDocBuilder.tsx && git commit -m "feat: add workflow-action button and Confirmed-status gate to tiles builder"
```

---

## Task 8: Frontend — nav consolidation + new Quotation Tiles list screen

**Files:**
- Modify: `frontend/app/(admin)/_layout.tsx` (`TILES_ITEMS`, currently lines 150-154)
- Create: `frontend/app/(admin)/tiles/index.tsx`

**Interfaces:**
- Consumes: `api.get` (existing client), `tilesStageLabel` (Task 6)
- Produces: route `/(admin)/tiles` (the "Quotation Tiles" tab)

- [ ] **Step 1: Update the sidebar nav**

In `frontend/app/(admin)/_layout.tsx`, replace `TILES_ITEMS` (currently lines 150-154):

```typescript
const TILES_ITEMS: NavItem[] = [
  { href: "/(admin)/tiles", label: "Quotation Tiles", icon: "layers", match: "tiles" },
  { href: "/(admin)/tiles/orders", label: "Tile Orders", icon: "truck", match: "orders" },
];
```

(This drops the separate `selection`/`quotation` entries in favor of one `tiles` entry pointing at the new list screen below; `orders` — Tile Orders — is untouched.)

Note: the existing `match` values `"selection"`/`"quotation"` were used by `Sidebar()`'s active-state check (`segments.includes("tiles") && isActive(n.match)`, currently line 199) to highlight whichever of the two was open. With one consolidated entry, `match: "tiles"` combined with the existing `segments.includes("tiles")` check is sufficient — no further change needed there.

- [ ] **Step 2: Create the list screen**

Create `frontend/app/(admin)/tiles/index.tsx`:

```typescript
// Quotation Tiles — single tab listing every Ground Floor tiles Selection
// and Quotation, any stage, with two entry points to start a new one. See
// docs/superpowers/specs/2026-07-27-quotation-tiles-workflow-design.md.
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Button, EmptyState } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";
import { tilesStageLabel } from "@/src/components/tiles/tilesStage";

type TilesDoc = {
  id: string; number: string; doc_type: "tiles_selection" | "tiles_quotation";
  status: string; customer_name: string; grand_total: number; updated_at: string;
};

export default function QuotationTilesList() {
  useRequireFloorAccess("ground-floor");
  const router = useRouter();
  const [docs, setDocs] = useState<TilesDoc[] | null>(null);

  const load = useCallback(async () => {
    const [selections, quotations] = await Promise.all([
      api.get<TilesDoc[]>("/quotations?doc_type=tiles_selection", { floorId: "ground-floor" }),
      api.get<TilesDoc[]>("/quotations?doc_type=tiles_quotation", { floorId: "ground-floor" }),
    ]);
    const merged = [...selections, ...quotations].sort(
      (a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""),
    );
    setDocs(merged);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const openDoc = (doc: TilesDoc) => {
    const route = doc.doc_type === "tiles_selection" ? "selection" : "quotation";
    router.push(`/(admin)/tiles/${route}?id=${doc.id}` as any);
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <View style={styles.header}>
        <View>
          <Text style={type.overline}>Ground Floor · Tiles</Text>
          <Text style={type.titleMd}>Quotation Tiles</Text>
        </View>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Button
            label="Create new selection"
            variant="ghost"
            icon="grid"
            onPress={() => router.push("/(admin)/tiles/selection" as any)}
            testID="tiles-create-selection"
          />
          <Button
            label="Create new quotation"
            icon="layout"
            onPress={() => router.push("/(admin)/tiles/quotation" as any)}
            testID="tiles-create-quotation"
          />
        </View>
      </View>

      {docs === null ? null : docs.length === 0 ? (
        <EmptyState icon="layers" title="No selections or quotations yet" subtitle="Create one to get started." />
      ) : (
        <FlatList
          data={docs}
          keyExtractor={(d) => d.id}
          contentContainerStyle={{ padding: spacing.lg, gap: 8 }}
          renderItem={({ item }) => (
            <Pressable style={styles.row} onPress={() => openDoc(item)} testID={`tiles-doc-${item.id}`}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>
                  {item.customer_name || "Unnamed customer"}
                </Text>
                <Text style={type.caption} numberOfLines={1}>{item.number} · {tilesStageLabel(item.doc_type, item.status)}</Text>
              </View>
              <Text style={[type.mono, { fontSize: 13, fontWeight: "600" }]}>{money(item.grand_total || 0)}</Text>
              <Feather name="chevron-right" size={16} color={colors.onSurfaceMuted} />
            </Pressable>
          )}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  row: {
    flexDirection: "row", alignItems: "center", gap: 10,
    padding: spacing.md, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
});
```

- [ ] **Step 3: Run typecheck**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/frontend" && npx tsc --noEmit`
Expected: no new errors (verified against `src/components/ui.tsx`'s actual `Button`/`EmptyState` signatures — `label/onPress/variant/icon/testID` and `icon/title/subtitle` respectively — the code in Step 2 already matches them exactly).

- [ ] **Step 4: Live-verify**

In the browser: sidebar now shows one "Quotation Tiles" entry (not two); clicking it lists every ground-floor tiles doc with correct stage label and total; "Create new selection"/"Create new quotation" both open a blank builder; clicking an existing row reopens it in the right paper.

- [ ] **Step 5: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add "frontend/app/(admin)/_layout.tsx" "frontend/app/(admin)/tiles/index.tsx" && git commit -m "feat: consolidate Tiles Selection/Quotation into one Quotation Tiles list tab"
```

---

## Task 9: Frontend — Customer detail "Tile history" section

**Files:**
- Modify: `frontend/app/(admin)/customers/[id].tsx` (`Quotation` type at line 31; new `useMemo` alongside the existing one at line 151; new `<Card>` in the `tab === "overview"` branch, lines 268-274)

**Interfaces:**
- Consumes: `tilesStageLabel` (Task 6)

This page already fetches **all** of this customer's quotations and filters
client-side (`api.get<Quotation[]>(\`/quotations\`).then((all) =>
all.filter((q: any) => q.customer_id === id))`, line 98) into the existing
`quotations` state — so this task adds **zero new network calls**, just a
`useMemo` filtering that same array to the two tiles `doc_type`s, and a new
`<Card>` rendering the result. (This is also why Task 3's `doc_type` filter
isn't needed here — it's for the new Quotation Tiles list in Task 8, which
has no per-customer scope to reuse.)

- [ ] **Step 1: Add `doc_type` to the local `Quotation` type**

In `frontend/app/(admin)/customers/[id].tsx`, update the type (currently line 31):

```typescript
type Quotation = { id: string; number: string; status: string; doc_type?: string; grand_total: number; created_at: string; items: any[] };
```

(Only `doc_type?: string;` is new — the API already returns this field on every quotation, per `backend/routes/quotation_routes.py::list_quotations`'s `{"_id": 0}` projection, which excludes nothing but `_id`.)

- [ ] **Step 2: Add the import and the derived list**

Add the import alongside the existing ones (near `import { api } from "@/src/api/client";`, line 18):

```typescript
import { tilesStageLabel } from "@/src/components/tiles/tilesStage";
```

Add a `useMemo` right after the existing `lifetimeRevenue`-style memo (currently line 151, `() => quotations.filter(...)`):

```typescript
  const tilesHistory = useMemo(
    () => quotations.filter((q) => q.doc_type === "tiles_selection" || q.doc_type === "tiles_quotation"),
    [quotations],
  );
```

- [ ] **Step 3: Render the section**

In the `tab === "overview"` branch (currently lines 268-274), add a second `<Card>` right after the existing "Latest activity" one:

```tsx
        {tab === "overview" ? (
          <>
            <Card>
              <Text style={[type.overline, { marginBottom: spacing.md }]}>Latest activity</Text>
              <ActivityTimeline events={timeline.slice(0, 8)} dense emptyLabel="No activity yet" />
            </Card>
            {tilesHistory.length > 0 ? (
              <Card>
                <Text style={[type.overline, { marginBottom: spacing.md }]}>Tile history</Text>
                {tilesHistory.map((doc, i) => (
                  <Pressable
                    key={doc.id}
                    onPress={() => router.push(`/(admin)/tiles/${doc.doc_type === "tiles_selection" ? "selection" : "quotation"}?id=${doc.id}` as any)}
                    style={({ pressed, hovered }: any) => [
                      styles.listRow,
                      {
                        borderTopWidth: i > 0 ? StyleSheet.hairlineWidth : 0,
                        borderTopColor: colors.divider,
                        backgroundColor: pressed ? colors.surfaceTertiary : hovered ? colors.surfaceSubtle : "transparent",
                      },
                    ]}
                  >
                    <Text style={[type.mono, { width: 120 }]} numberOfLines={1}>{doc.number}</Text>
                    <Text style={{ flex: 1, minWidth: 0 }} numberOfLines={1}>{tilesStageLabel(doc.doc_type!, doc.status)}</Text>
                    <Text style={[type.mono, { width: 110, textAlign: "right", fontWeight: "700" }]} numberOfLines={1}>
                      {money(doc.grand_total)}
                    </Text>
                  </Pressable>
                ))}
              </Card>
            ) : null}
          </>
        ) : tab === "quotations" ? (
```

(This reuses `styles.listRow`, already defined in this file for the "quotations" tab's own list rows, currently used at line 287.)

- [ ] **Step 4: Run typecheck**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/frontend" && npx tsc --noEmit`
Expected: no new errors

- [ ] **Step 5: Live-verify**

Open a customer who has at least one tiles Selection/Quotation (or create one via the new Quotation Tiles tab first, on the Overview tab) → confirm the "Tile history" card appears and clicking a row reopens the right document. Open a customer with none → confirm the card is simply absent.

- [ ] **Step 6: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add "frontend/app/(admin)/customers/[id].tsx" && git commit -m "feat: add Tile history section to customer detail page"
```

---

## Task 10: Frontend — product picker "used last time" hint

**Files:**
- Modify: `frontend/src/components/tiles/TilesProductPicker.tsx` (`onPick` callback / result-row render)
- Modify: `frontend/src/components/tiles/TilesDocBuilder.tsx` (`applyProduct`, currently lines 244-281 — pass `customerId` through so the picker can look up history)

**Interfaces:**
- Consumes: `GET /quotations/tiles/product-history` (Task 4)
- Produces: `TilesProductPicker` gains an optional `customerId?: string | null` prop; on picking a product, if history is found, a toast/hint offers to apply the previous rate/size

- [ ] **Step 1: Thread `customerId` into `TilesProductPicker`**

In `frontend/src/components/tiles/TilesProductPicker.tsx`, add `customerId` to the props:

```typescript
export function TilesProductPicker({
  open, onClose, onPick, customerId,
}: {
  open: boolean;
  onClose: () => void;
  onPick: (product: Product, history?: { size: string | null; rate_sqft: number | null; rate_box: number | null; pcs_per_box: string | null }) => void;
  customerId?: string | null;
}) {
```

Replace the `pick` callback (currently lines 59-63 — `const pick = useCallback((product: Product | undefined) => { if (!product) return; onPick(product); onClose(); }, [onPick, onClose]);`) with a version that looks up history first:

```typescript
  const pick = useCallback(async (product: Product | undefined) => {
    if (!product) return;
    if (customerId) {
      try {
        const history = await api.get<{ found: boolean; size?: string; rate_sqft?: number; rate_box?: number; pcs_per_box?: string }>(
          `/quotations/tiles/product-history?customer_id=${customerId}&product_id=${product.id}`,
        );
        if (history.found) {
          onPick(product, {
            size: history.size ?? null, rate_sqft: history.rate_sqft ?? null,
            rate_box: history.rate_box ?? null, pcs_per_box: history.pcs_per_box ?? null,
          });
          onClose();
          return;
        }
      } catch {
        // History lookup is a convenience — fall through to the normal pick on any failure.
      }
    }
    onPick(product);
    onClose();
  }, [customerId, onPick, onClose]);
```

The two calls to `pick` (`onSubmitEditing={() => pick(results[highlight])}` at line 93 and `onPress={() => pick(item)}` at line 114) are both fire-and-forget event handlers — making `pick` `async` requires no change at either call site.

- [ ] **Step 2: Use the history hint in `applyProduct`**

In `frontend/src/components/tiles/TilesDocBuilder.tsx`, update `applyProduct` (currently lines 244-281) to accept the optional history and apply it, and show a toast when it's used:

```typescript
  const applyProduct = useCallback((key: string, product: Product, history?: { size: string | null; rate_sqft: number | null; rate_box: number | null; pcs_per_box: string | null }) => {
    const image = productImageList(product)[0] || null;
    const specs = product.specs || {};
    const specNum = (...keys: string[]): string => {
      for (const k of keys) {
        const v = (specs as any)[k];
        if (v != null && v !== "" && Number.isFinite(parseFloat(String(v)))) return String(v);
      }
      return "";
    };
    const specText = (...keys: string[]): string => {
      for (const k of keys) {
        const v = (specs as any)[k];
        if (v != null && String(v).trim()) return String(v);
      }
      return "";
    };
    setRows((cur) => cur.map((row) => {
      if (row.key !== key) return row;
      const next: TileRow = {
        ...row,
        productId: product.id,
        sku: product.sku,
        categoryId: product.category_id || null,
        name: product.name,
        image,
        mrp: product.mrp ?? null,
        size: history?.size || product.size || product.dimensions || row.size,
        rateSqft: history?.rate_sqft != null ? String(history.rate_sqft) : (product.price ? String(product.price) : row.rateSqft),
        rateBox: history?.rate_box != null ? String(history.rate_box) : (specNum("rate_per_box", "rate_box", "box_rate") || row.rateBox),
        pcsBox: history?.pcs_per_box || specText("pcs_per_box", "pcs_box", "pcs") || row.pcsBox,
        totalEdited: false,
      };
      next.total = computedTotal(next);
      return next;
    }));
    if (history) toast.show(`Used ${customerId ? "this customer's" : ""} last rate for ${product.name}`.replace("  ", " "));
    markDirty();
  }, [markDirty, customerId]);
```

Then pass `customerId` to the `TilesProductPicker` element (both usages, currently lines 773-777 and 1006-1010):

```typescript
      <TilesProductPicker
        open={pickerRow !== null}
        onClose={() => setPickerRow(null)}
        onPick={(product, history) => { if (pickerRow) doc.applyProduct(pickerRow, product, history); }}
        customerId={doc.customerId}
      />
```

Note: `customerId` is already in `useTilesDoc`'s return value (see the return statement replaced in Task 7 Step 4 — `customers, customerId, pickCustomer, setCustomerId` — unchanged by that edit), so `doc.customerId` works with no further change.

- [ ] **Step 3: Run typecheck**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/frontend" && npx tsc --noEmit`
Expected: no new errors

- [ ] **Step 4: Live-verify**

Create a Tiles Quotation for a customer, pick a product, fill rate/size, save. Start a second, new Tiles Quotation for the *same* customer, pick the *same* product → confirm the rate/size auto-fill and the "Used ... last rate" toast appear. Pick a product that customer has never had → confirm normal (empty) row behavior, no toast.

- [ ] **Step 5: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add frontend/src/components/tiles/TilesProductPicker.tsx frontend/src/components/tiles/TilesDocBuilder.tsx && git commit -m "feat: surface customer's previous rate/size when re-picking a tile product"
```

---

## Task 11: Frontend — tile images horizontal (Catalog cards + builder photo cells)

**Files:**
- Modify: `frontend/app/(admin)/catalog/index.tsx` (`Product`/`Family` local types at lines 30-48; `ProductCard` at line 612-619; `FamilyCard` at line 544-551ish; `styles.imageWrap` at line 750-752)
- Modify: `frontend/src/components/tiles/TilesDocBuilder.tsx` (photo cells at lines 726-728 and 927-928)

**Interfaces:**
- Consumes: `floor_id` on `Product`/`Family` (Task 5 for families; products already carry it per `db.products.find(regular_query, {"_id": 0})`'s projection)

**No PDF change** — `pdf_tiles.py`'s photo cell is already landscape-proportioned (see spec correction); not part of this task.

- [ ] **Step 1: Add `floor_id` to Catalog's local types**

In `frontend/app/(admin)/catalog/index.tsx`, add `floor_id` to both local type definitions (currently lines 30-48):

```typescript
type Family = {
  family_key: string; family_name: string; brand_id: string; category_id: string;
  subcategory?: string | null; series?: string | null;
  min_price: number; max_price: number; product_count: number;
  sample_image?: string | null; sample_image_quality?: string | null;
  floor_id?: string | null;
  variants: {
    id: string; sku: string; variant_label?: string | null; colour?: string | null;
    finish?: string | null; finish_code?: string | null; price: number; mrp: number;
    image?: string | null; image_quality?: string | null;
  }[];
};
type Product = {
  id: string; name: string; sku: string; brand_id: string; category_id: string;
  subcategory?: string | null; series?: string | null;
  price: number; mrp: number; finish?: string | null; images: string[]; stock: number;
  image_quality?: string | null;
  hero_image_url?: string | null;
  colour?: string | null;
  floor_id?: string | null;
};
```

(Only the `floor_id?: string | null;` line is new in each type.)

- [ ] **Step 2: Add a landscape style variant and apply it conditionally**

In the `styles` `StyleSheet.create({...})` block, find `imageWrap` (currently lines 750-752) and add a sibling style right after it:

```typescript
  imageWrap: {
    width: "100%", aspectRatio: 1, backgroundColor: colors.surfaceTertiary, position: "relative",
  },
  imageWrapTile: {
    aspectRatio: 16 / 10,
  },
```

In `ProductCard` (currently lines 612-619), apply it conditionally:

```typescript
function ProductCard({ product: p, brandName, onPress }: { product: Product; brandName: string; onPress: () => void }) {
  return (
    <Pressable
      testID={`product-${p.id}`}
      onPress={onPress}
      style={({ pressed }) => [styles.card, { opacity: pressed ? 0.9 : 1 }]}
    >
      <View style={[styles.imageWrap, p.floor_id === "ground-floor" && styles.imageWrapTile]}>
```

(Leave the rest of `ProductCard` — everything after this opening `<View>` tag — exactly as it is today.)

In `FamilyCard` (`function FamilyCard({ family: f, brandName, onPress }: ...)`, currently line 544), its `<View style={styles.imageWrap}>` (currently line 551) becomes:

```typescript
      <View style={[styles.imageWrap, f.floor_id === "ground-floor" && styles.imageWrapTile]}>
```

- [ ] **Step 3: Run typecheck**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/frontend" && npx tsc --noEmit`
Expected: no new errors

- [ ] **Step 4: Live-verify Catalog**

Browse Catalog on Ground Floor → tile cards render visibly wider/shorter (landscape) than before. Switch to a sanitaryware floor (or "All floors" as owner) → sanitaryware cards are unchanged (still square) while any ground-floor tile cards mixed into an "All floors" view are landscape.

- [ ] **Step 5: Fix the builder's on-screen photo cells**

In `frontend/src/components/tiles/TilesDocBuilder.tsx`, replace the fixed-height `Image` styles with an aspect-ratio-driven landscape frame at both photo-cell locations.

Currently line 727 (`SelectionPaper`):
```typescript
                <Image source={{ uri: row.image }} resizeMode="contain" style={{ width: "100%", height: 88 }} />
```
Change to:
```typescript
                <Image source={{ uri: row.image }} resizeMode="contain" style={{ width: "100%", aspectRatio: 16 / 10 }} />
```

Currently line 928 (`QuotationPaper`):
```typescript
              {row.image ? <Image source={{ uri: row.image }} resizeMode="contain" style={{ width: "100%", height: 68 }} /> : null}
```
Change to:
```typescript
              {row.image ? <Image source={{ uri: row.image }} resizeMode="contain" style={{ width: "100%", aspectRatio: 16 / 10 }} /> : null}
```

- [ ] **Step 6: Run typecheck**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/frontend" && npx tsc --noEmit`
Expected: no new errors

- [ ] **Step 7: Live-verify the builder**

Open Tiles Selection and Tiles Quotation, add a product with a photo to each → confirm the on-screen photo cell now renders as a wide landscape frame in both, matching Catalog's new card shape.

- [ ] **Step 8: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add "frontend/app/(admin)/catalog/index.tsx" frontend/src/components/tiles/TilesDocBuilder.tsx && git commit -m "feat: render tile images in a landscape frame across Catalog and the tiles builder"
```

---

## Task 12: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend unit suite**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit -v`
Expected: PASS (all tests — every task above already checked this individually, this is the final confirmation after all tasks land together)

- [ ] **Step 2: Run frontend typecheck**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/frontend" && npx tsc --noEmit`
Expected: no new errors (the one pre-existing `TileOrderCard.tsx:107` error, if still present, predates this work)

- [ ] **Step 3: Full live round-trip**

Ask the user before restarting the shared `:8010` backend. Then in the browser: create a Selection for a new customer → add 2 products → Submit for approval → Approve → Move to Quotation (confirm it lands on the Quotation paper with both products already there, pricing fields open) → fill rate/box + qty on both → Submit for confirmation → Confirm → Place Order → confirm the Purchase Order(s) and Payment appear exactly as the already-fixed automation produces them (per the earlier bug fixes this session). Confirm the customer's "Tile history" section shows this document, and that re-picking one of the same 2 products for the same customer in a fresh document surfaces the "used last time" hint.

- [ ] **Step 4: Confirm Tile Orders is untouched**

Open Tile Orders — confirm it looks and behaves exactly as before (not absorbed into the new tab, no regressions from the nav change in Task 8).
