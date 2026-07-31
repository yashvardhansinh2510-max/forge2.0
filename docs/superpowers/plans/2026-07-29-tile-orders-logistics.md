# Tile Orders Logistics Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Ground Floor → Tiles → Tile Orders module's chalan-derived stage machine with a box-counter-driven logistics system: a `CustomerOrder` aggregation layer, first-class `ReadyBatch`/`Dispatch`/`Chalan` collections, a supplier-grouped Company view, and a permanent Dispatch List register — while keeping `PurchaseOrder`/`Supplier`/`Brand` and all Mongo transaction/CAS/audit/RBAC infrastructure exactly as they are today.

**Architecture:** New Pydantic models in `backend/models_tile_orders.py`; a pure status-derivation module (`backend/services/tile_order_status.py`); a new FastAPI router (`backend/routes/tile_orders.py`) mounted alongside the existing routers; four new top-level Mongo collections (`customer_orders`, `ready_batches`, `dispatches`, `chalans`); a one-time backfill script; new frontend screens reusing the existing `tiles/orders` route tree and design tokens.

**Tech Stack:** FastAPI + Motor (async MongoDB driver), Pydantic v1-style models (see `TimestampedModel` pattern), pytest with hand-rolled fake-DB unit tests (no live DB in `tests/unit`), Expo/React Native frontend with a thin `fetch` API client (`@/src/api/client`).

**Reference spec:** `docs/superpowers/specs/2026-07-29-tile-orders-logistics-redesign-design.md` (frozen — implement exactly this; do not introduce further domain-model changes without flagging it explicitly first).

## Global Constraints

- Reuse the existing Purchases architecture (`PurchaseOrder`/`Supplier`/`Brand`) — do not duplicate order documents.
- All state-changing writes are transactional or CAS-guarded and recorded via `log_event` (`backend/services/activity_log.py`) — no silent writes.
- `TileChalan` is immutable: no PATCH/PUT route may ever be wired for it. A correction always means a new `TileDispatch` + new `TileChalan`.
- Box-counter invariant holds at all times: `boxes_ordered == boxes_ready + boxes_dispatched + boxes_pending` (where `boxes_ordered` is the existing `PurchaseOrderItem.qty` field — not renamed, just documented as the "ordered" count).
- Soft delete only on `TileCustomerOrder`, `TileReadyBatch`, `TileDispatch`, `TileChalan` (`is_deleted`/`deleted_at`/`deleted_by`) — logistics records are never physically removed. Every list/read query filters `is_deleted: False`.
- `TileCustomerOrder` writes go through its `version` field (optimistic CAS: read version, write with `{version: current}` filter, retry on `matched_count == 0`), mirroring the `$elemMatch` CAS pattern already used in `purchases_tracker.py`.
- **Critical gating**: `_handle_order_placed` (`backend/services/domain_outbox.py`) runs for BOTH tiles and standard (sanitaryware) quotations — `can_place_order()` in `backend/services/tiles_stage.py` returns `True` unconditionally for `doc_type == "standard"`. All new `TileCustomerOrder`/box-counter logic MUST be gated behind `quotation.get("doc_type") in ("tiles_selection", "tiles_quotation")`, otherwise standard orders wrongly get tile-specific records.
- RBAC: Ready/Dispatch/Godown-received write actions require `require_min_role("warehouse")` — this matches the existing precedent for chalan generation/dispatch in `purchases_tracker.py` (NOT `"purchase"` as an earlier draft of the design doc assumed; verified against the actual route decorators). Read endpoints (Company/Supplier dashboards, Customer tab, Dispatch List) require `require_min_role("sales")`.
- Floor scoping via `floor_query(user, ...)` / `floor_inherit(source)` exactly as existing code — every new collection carries `floor_id`.
- New collections are **top-level**, not embedded on `PurchaseOrder` — `customer_orders`, `ready_batches`, `dispatches`, `chalans`. The existing embedded `PurchaseOrder.chalans` array is left in place on old documents, untouched and unread by any new code.
- Numbering via the existing `services/sequence.py::next_number(kind, prefix, *, collection, width=4, session=None, array_field=None)` — new prefixes are year-scoped exactly like `FPO-{year}-` (see `_next_po_number` in `domain_outbox.py:111-113`): `TORD-{year}-`, `RB-{year}-`, `DSP-{year}-`. The existing `"chalan"`/`"CH-"` counter key is reused for the new top-level `chalans` collection (`next_number("chalan", "CH-", collection="chalans", width=4)`, no `array_field` this time) — this continues the same visible CH- sequence across old and new systems without a manual counter reset.
- No frontend automated test harness exists in this codebase (confirmed: no `*.test.ts(x)` files outside `node_modules`) — frontend tasks are verified manually via the dev server/browser preview, backend tasks are verified via `pytest`.

---

## File Structure

**New backend files:**
- `backend/models_tile_orders.py` — all new Pydantic models (`TileCustomerOrder`, `TileReadyBatch`, `TileDispatch`, `TileChalan`, and their nested types). Kept separate from the already-large `backend/models.py` and named with a `Tile` prefix specifically to avoid colliding with the existing `Chalan`/`ChalanLineItem` classes that the old embedded system still uses.
- `backend/services/tile_order_status.py` — pure functions (no DB access) deriving `overall_status`, `current_location`, `completion_percentage`, ageing bands, and `supplier_silent_days`. Mirrors the existing `backend/services/chalan_stage.py` "pure functions" pattern.
- `backend/services/tile_order_indexes.py` — `ensure_tile_order_indexes()`, called from `server.py` startup alongside `ensure_outbox_indexes()`.
- `backend/routes/tile_orders.py` — the new `/tile-orders` router: order-placement hook is in `domain_outbox.py` (existing file), everything else (Ready/Dispatch/Chalan actions, Company/Supplier/Customer/Dispatch-List reads) lives here.
- `backend/scripts/backfill_tile_customer_orders.py` — one-time migration script.

**Modified backend files:**
- `backend/models.py` — `PurchaseOrderItem` and `PurchaseOrder` gain the new fields listed in the design doc (additive, all with defaults).
- `backend/services/domain_outbox.py` — `_brand_groups` denormalizes `series`/`size`/`pieces_per_box`; `_handle_order_placed` creates the `TileCustomerOrder` and sets item-level box counters, gated to tiles doc types.
- `backend/pdf_chalan.py` — adds `build_tile_chalan_pdf()` / `tile_chalan_pdf_filename()` alongside (not replacing) the existing `build_chalan_pdf()`/`chalan_pdf_filename()`.
- `backend/server.py` — mounts the new router, calls `ensure_tile_order_indexes()` at startup.

**New frontend files:**
- `frontend/src/api/tileOrders.ts` — typed API client functions for every new endpoint.
- `frontend/src/components/tiles/TileOrderStatusUI.tsx` — shared status pill, ageing badge, and box-counter row components used across all new screens.
- `frontend/src/components/tiles/ReadyDispatchSheets.tsx` — the bulk "Mark Ready" and "Dispatch" (preview → commit) bottom-sheet forms.
- `frontend/app/(admin)/tiles/orders/company/[supplierId].tsx` — Supplier dashboard (KPI bar + order table).
- `frontend/app/(admin)/tiles/orders/po/[poId].tsx` — Supplier order detail (per-product box actions).

**Modified frontend files:**
- `frontend/app/(admin)/tiles/orders/index.tsx` — rewritten: three tabs (Customer / Company / Dispatch List) instead of two; Customer tab keeps the card-grid pattern against the new endpoint, Company tab becomes the supplier-landing card list, new Dispatch List tab is a filterable table.
- `frontend/app/(admin)/tiles/orders/[id].tsx` — rewritten from "PurchaseOrder detail" to "CustomerOrder detail" (summary card + supplier-grouped product lines, read-only — actions live on the new supplier order-detail page).
- `frontend/src/components/tiles/TileOrderCard.tsx` — extended with a `CustomerOrderCard`/`SupplierOrderCard` export alongside the existing `OrderCard`/`TileOrderCard` (old exports untouched — old `/purchases/orders/*` screens, if ever re-linked during rollback, keep working).

No change needed to `frontend/app/(admin)/_layout.tsx` — Dispatch List is a new tab inside the existing single "Tile Orders" nav entry, not a new nav item.

---

## Task 1: New Tile Orders models module

**Files:**
- Create: `backend/models_tile_orders.py`
- Test: `backend/tests/unit/test_models_tile_orders.py`

**Interfaces:**
- Produces: `TileOverallStatus`, `TileLocation` (Literal type aliases); `TileCustomerOrderBrand`, `TileCustomerOrderDashboardSummary`, `TileCustomerOrder`, `TileReadyBatch`, `TileDispatchLineConsumed`, `TileDispatchAttachment`, `TileDispatch`, `TileChalanItem`, `TileChalan` (Pydantic models) — every later task imports from this module.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_models_tile_orders.py
"""Defaults/shape for the new Tile Orders collections. Real DB writes are
covered by the route tests in later tasks — this just locks the schema."""
from __future__ import annotations

from models_tile_orders import (
    TileChalan, TileChalanItem, TileCustomerOrder, TileCustomerOrderBrand,
    TileCustomerOrderDashboardSummary, TileDispatch, TileReadyBatch,
)


def _customer_order(**overrides) -> TileCustomerOrder:
    base = dict(
        number="TORD-2026-0001", quotation_id="q-1", quotation_number="FQ-2026-0001",
        customer_id="cust-1", customer_name="Nileshbhai Pokiya", customer_phone="9909900000",
        delivery_name="Nileshbhai Pokiya", delivery_phone="9909900000",
        delivery_address="123 Ring Road", delivery_city="Rajkot", delivery_pincode="360005",
        delivery_state="Gujarat", floor_id="ground-floor",
        created_by="u-1", created_by_name="Sales Rep",
        dashboard_summary=TileCustomerOrderDashboardSummary(
            completion_percentage=0, overall_status="Pending", supplier_statuses=[],
        ),
    )
    base.update(overrides)
    return TileCustomerOrder(**base)


def test_customer_order_defaults():
    order = _customer_order()
    assert order.version == 0
    assert order.is_deleted is False
    assert order.overall_status == "Pending"
    assert order.brands == []
    assert order.total_boxes == 0


def test_customer_order_brand_carries_status():
    brand = TileCustomerOrderBrand(
        brand_id="b-1", brand_name="Qutone", supplier_id="s-1", supplier_name="Qutone Rajkot",
        purchase_order_id="po-1", status="Ready",
    )
    order = _customer_order(brands=[brand])
    assert order.brands[0].status == "Ready"


def test_ready_batch_defaults():
    batch = TileReadyBatch(
        batch_number="RB-2026-0001", purchase_order_id="po-1", po_item_id="item-1",
        customer_order_id="co-1", supplier_id="s-1", supplier_name="Qutone Rajkot",
        customer_id="cust-1", customer_name="Nileshbhai Pokiya", tile_name="Glossy Ivory 600x600",
        qty=8, remaining_qty=8, created_by="u-1", created_by_name="Warehouse Rep",
    )
    assert batch.auto_created is False
    assert batch.is_deleted is False


def test_dispatch_defaults_and_chalan_link():
    dispatch = TileDispatch(
        dispatch_number="DSP-2026-0001", purchase_order_id="po-1", customer_order_id="co-1",
        supplier_id="s-1", supplier_name="Qutone Rajkot", customer_id="cust-1",
        customer_name="Nileshbhai Pokiya", ready_batches_consumed=[],
        destination_type="Customer", destination_name="Nileshbhai Pokiya",
        destination_address="123 Ring Road", destination_city="Rajkot",
        dispatch_date="2026-07-29", dispatch_time="14:23",
        created_by="u-1", created_by_name="Warehouse Rep", chalan_id="ch-1",
    )
    assert dispatch.attachments == []
    assert dispatch.inventory_transaction_id is None
    assert dispatch.godown_received_at is None


def test_chalan_is_a_plain_dict_after_serialization_and_has_no_update_hook():
    chalan = TileChalan(
        number="CH-0001", dispatch_id="d-1", purchase_order_id="po-1", customer_order_id="co-1",
        supplier_name="Qutone Rajkot", customer_name="Nileshbhai Pokiya", customer_phone="9909900000",
        delivery_address="123 Ring Road", delivery_city="Rajkot",
        items=[TileChalanItem(po_item_id="item-1", tile_name="Glossy Ivory 600x600", boxes=8, quantity=8)],
        created_by="u-1", created_by_name="Warehouse Rep",
        generated_at="2026-07-29T14:23:00+00:00", generated_by_name="Warehouse Rep",
    )
    data = chalan.dict()
    assert "update" not in data  # no mutable-state field snuck in
    assert data["system_version"] == "BuildCon ERP v2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_models_tile_orders.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'models_tile_orders'`

- [ ] **Step 3: Write the models module**

```python
# backend/models_tile_orders.py
"""Tile Orders logistics — CustomerOrder aggregation + ReadyBatch/Dispatch/
Chalan as first-class collections. Kept separate from models.py (already
740+ lines) and prefixed `Tile` to avoid colliding with the existing
Chalan/ChalanLineItem classes still used by the old embedded system on
PurchaseOrder.chalans (left in place, unread by any code in this module —
see the design doc's Migration section).

TileChalan is immutable once created: no route in routes/tile_orders.py
ever issues a PATCH/PUT against the chalans collection. A correction always
means a new TileDispatch + new TileChalan, never editing an existing one.
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from models import TimestampedModel, now_iso

TileOverallStatus = Literal["Pending", "Ready", "Partially Dispatched", "Dispatched", "Delivered"]
TileLocation = Literal["Pending", "Ready", "Dispatched", "Godown", "Delivered"]


class TileCustomerOrderBrand(BaseModel):
    brand_id: Optional[str] = None
    brand_name: str
    supplier_id: Optional[str] = None
    supplier_name: str
    purchase_order_id: str
    status: TileOverallStatus = "Pending"


class TileCustomerOrderDashboardSummary(BaseModel):
    """Cached read-model for the Customer tab, refreshed transactionally on
    every child write. `waiting_days` is deliberately NOT part of this cache
    — it depends on "today," not on stored order state, so it is always
    computed live by tile_order_status.waiting_days()."""
    completion_percentage: float = 0
    overall_status: TileOverallStatus = "Pending"
    supplier_statuses: list[dict] = []  # [{supplier_name, status}]


class TileCustomerOrder(TimestampedModel):
    number: str                    # "TORD-2026-0001"
    version: int = 0                # optimistic-locking counter — incremented
                                     # on every aggregation update; guards
                                     # against two sibling POs racing to
                                     # update the same rollup
    quotation_id: str
    quotation_number: str
    customer_id: str
    customer_name: str
    customer_phone: str
    # Immutable delivery snapshot captured at placement time.
    delivery_name: str
    delivery_phone: str
    delivery_address: str
    delivery_city: str
    delivery_pincode: str
    delivery_state: str
    floor_id: str = "first-floor"
    created_by: str
    created_by_name: str
    brands: list[TileCustomerOrderBrand] = []
    total_products: int = 0
    total_boxes: float = 0
    total_value: float = 0
    overall_status: TileOverallStatus = "Pending"
    completion_percentage: float = 0
    dashboard_summary: TileCustomerOrderDashboardSummary
    last_activity: Optional[str] = None
    last_activity_at: Optional[str] = None
    is_deleted: bool = False
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None


class TileReadyBatch(TimestampedModel):
    batch_number: str          # "RB-2026-0001"
    purchase_order_id: str
    po_item_id: str
    customer_order_id: str
    floor_id: str = "first-floor"
    supplier_id: Optional[str] = None
    supplier_name: str
    customer_id: str
    customer_name: str
    tile_name: str
    series: Optional[str] = None
    finish: Optional[str] = None
    size: Optional[str] = None
    sku: Optional[str] = None
    qty: float
    remaining_qty: float       # decrements as Dispatches consume it
    created_by: str
    created_by_name: str
    auto_created: bool = False  # true for behind-the-scenes batches from direct dispatch
    is_deleted: bool = False
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None


class TileDispatchLineConsumed(BaseModel):
    ready_batch_id: str
    po_item_id: str
    qty: float


class TileDispatchAttachment(BaseModel):
    # No UI this pass — LR copies / transport receipts / vehicle photos /
    # POD can attach later without a migration.
    type: str
    url: str
    uploaded_by: str
    uploaded_at: str = Field(default_factory=now_iso)


class TileDispatch(TimestampedModel):
    dispatch_number: str        # "DSP-2026-0001"
    purchase_order_id: str
    customer_order_id: str
    floor_id: str = "first-floor"
    supplier_id: Optional[str] = None
    supplier_name: str
    customer_id: str
    customer_name: str
    ready_batches_consumed: list[TileDispatchLineConsumed]
    destination_type: Literal["Customer", "Godown"]
    destination_name: str
    destination_address: str
    destination_city: str
    dispatch_date: str
    dispatch_time: str
    created_by: str
    created_by_name: str
    chalan_id: str              # 1:1, always set — Chalan is generated in the same transaction
    godown_received_at: Optional[str] = None
    godown_received_by: Optional[str] = None
    godown_received_by_name: Optional[str] = None
    delivered_at: Optional[str] = None    # future — modeled now, no action/UI this pass
    delivered_by: Optional[str] = None
    delivered_by_name: Optional[str] = None
    attachments: list[TileDispatchAttachment] = []
    inventory_transaction_id: Optional[str] = None   # unused today — future inventory-module hook
    is_deleted: bool = False
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None


class TileChalanItem(BaseModel):
    po_item_id: str
    tile_name: str
    series: Optional[str] = None
    finish: Optional[str] = None
    size: Optional[str] = None
    sku: Optional[str] = None
    boxes: float
    pieces_per_box: Optional[str] = None
    quantity: float


class TileChalan(TimestampedModel):
    number: str                 # "CH-0001" — same counter key as the old embedded system
    dispatch_id: str            # 1:1
    purchase_order_id: str
    customer_order_id: str
    floor_id: str = "first-floor"
    supplier_name: str
    supplier_contact: Optional[str] = None
    supplier_address: Optional[str] = None
    customer_name: str
    customer_phone: str
    delivery_address: str
    delivery_city: str
    reference_number: Optional[str] = None
    items: list[TileChalanItem]      # only this dispatch's quantities
    receiver_name: Optional[str] = None
    sender_name: Optional[str] = None
    vehicle_number: Optional[str] = None
    driver_name: Optional[str] = None
    created_by: str
    created_by_name: str
    generated_at: str
    generated_by_name: str
    system_version: str = "BuildCon ERP v2"
    is_deleted: bool = False
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_models_tile_orders.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/models_tile_orders.py backend/tests/unit/test_models_tile_orders.py
git commit -m "feat: add Tile Orders logistics models (CustomerOrder, ReadyBatch, Dispatch, Chalan)"
```

---

## Task 2: Extend `PurchaseOrderItem` / `PurchaseOrder` with tile logistics fields

**Files:**
- Modify: `backend/models.py:628-663` (`PurchaseOrderItem`), `backend/models.py:733-759` (`PurchaseOrder`)
- Test: `backend/tests/unit/test_models_purchase_order_tile_fields.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `PurchaseOrderItem.series/size/pieces_per_box/boxes_ready/boxes_dispatched/boxes_pending/current_location/overall_status` and `PurchaseOrder.customer_order_id/ready_boxes/pending_boxes/dispatched_boxes/latest_ready_date/latest_dispatch_date/overall_status/completion_percentage/last_supplier_activity_at`, plus `ActivityEntity` gaining `"tile_customer_order"` — every later backend task reads/writes these exact field names.

`qty` is **not** renamed — it already means "boxes ordered" and every existing route (`purchase_routes.py`, `purchases_tracker.py`, `domain_outbox.py`) reads it. The invariant is `item.qty == item.boxes_ready + item.boxes_dispatched + item.boxes_pending`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_models_purchase_order_tile_fields.py
from __future__ import annotations

from models import PurchaseOrder, PurchaseOrderItem


def test_purchase_order_item_tile_fields_default():
    item = PurchaseOrderItem(product_id="p-1", sku="SKU-1", name="Glossy Ivory 600x600", qty=20)
    assert item.series is None
    assert item.size is None
    assert item.pieces_per_box is None
    assert item.boxes_ready == 0
    assert item.boxes_dispatched == 0
    assert item.boxes_pending == 0
    assert item.current_location == "Pending"
    assert item.overall_status == "Pending"


def test_purchase_order_tile_rollup_fields_default():
    po = PurchaseOrder(
        number="FPO-2026-0001", customer_id="cust-1", customer_name="Nileshbhai Pokiya",
        created_by="u-1", created_by_name="Sales Rep",
    )
    assert po.customer_order_id is None
    assert po.ready_boxes == 0
    assert po.pending_boxes == 0
    assert po.dispatched_boxes == 0
    assert po.overall_status == "Pending"
    assert po.completion_percentage == 0
    assert po.last_supplier_activity_at is None


def test_activity_entity_accepts_tile_customer_order():
    from models import ActivityEvent

    event = ActivityEvent(
        event_type="customer_order.created", entity_type="tile_customer_order", entity_id="co-1",
    )
    assert event.entity_type == "tile_customer_order"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_models_purchase_order_tile_fields.py -v`
Expected: FAIL — `AttributeError: 'PurchaseOrderItem' object has no attribute 'series'`

- [ ] **Step 3: Add the fields**

In `backend/models.py`, inside `class PurchaseOrderItem(BaseModel):` (currently ending at line 663 with `split_into_item_id`), add immediately after `split_into_item_id: Optional[str] = None`:

```python
    # ---- Tile Orders logistics fields (Ground Floor → Tiles) ----
    # Denormalized from the Product/QuotationLineItem at order-placement
    # time by domain_outbox.py::_handle_order_placed — see Task 5.
    series: Optional[str] = None
    size: Optional[str] = None
    pieces_per_box: Optional[str] = None   # free text, printed as-is — mirrors ChalanLineItem.unit convention
    # Box-counter invariant: qty == boxes_ready + boxes_dispatched + boxes_pending
    boxes_ready: float = 0
    boxes_dispatched: float = 0
    boxes_pending: float = 0
    current_location: str = "Pending"   # TileLocation — Pending|Ready|Dispatched|Godown|Delivered
    overall_status: str = "Pending"     # TileOverallStatus — furthest-progress ladder
```

Also in `backend/models.py`, extend the shared `ActivityEntity` Literal (line 821) to accept CustomerOrder-scoped timeline events — `log_event`/`_upsert_activity` construct a real `ActivityEvent`, whose `entity_type` field is validated against this Literal at runtime (not just a type-checker hint), so `tile_customer_order` must be added here before Task 5 can log against it:

```python
ActivityEntity = Literal["quotation", "purchase", "customer", "project", "payment", "followup", "user", "product", "tile_customer_order"]
```

Inside `class PurchaseOrder(TimestampedModel):` (currently ending at line 759 with `chalans: list[Chalan] = []`), add immediately after that line:

```python
    # ---- Tile Orders logistics fields (Ground Floor → Tiles) ----
    customer_order_id: Optional[str] = None
    ready_boxes: float = 0
    pending_boxes: float = 0
    dispatched_boxes: float = 0
    latest_ready_date: Optional[str] = None
    latest_dispatch_date: Optional[str] = None
    overall_status: str = "Pending"
    completion_percentage: float = 0
    last_supplier_activity_at: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_models_purchase_order_tile_fields.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full existing suite to confirm nothing else broke**

Run: `cd backend && python -m pytest tests/unit -q`
Expected: PASS, same count as before plus 7 new (5 from Task 1, 2 from this task)

- [ ] **Step 6: Commit**

```bash
git add backend/models.py backend/tests/unit/test_models_purchase_order_tile_fields.py
git commit -m "feat: add tile logistics fields to PurchaseOrder/PurchaseOrderItem"
```

---

## Task 3: Status/ageing/completion pure functions

This is the core business logic of the whole feature — every write endpoint in Tasks 8-11 calls into this module, so it gets the heaviest test coverage, including the exact simultaneity example from the design doc.

**Files:**
- Create: `backend/services/tile_order_status.py`
- Test: `backend/tests/unit/test_tile_order_status.py`

**Interfaces:**
- Consumes: nothing (pure functions, no DB access — same discipline as `backend/services/chalan_stage.py`).
- Produces: `derive_item_status(boxes_ordered, boxes_ready, boxes_dispatched, *, all_delivered=False) -> str`, `derive_current_location(boxes_ordered, boxes_ready, boxes_dispatched, *, any_at_godown=False, all_delivered=False) -> str`, `completion_percentage(boxes_ordered, boxes_dispatched) -> float`, `rollup_status(statuses: list[str]) -> str`, `waiting_days(created_at: str, *, today: Optional[datetime] = None) -> int`, `ageing_band(days: int) -> str`, `supplier_silent_days(last_supplier_activity_at: Optional[str], created_at: str, *, today: Optional[datetime] = None) -> int` — imported by name in Tasks 5, 8-14.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_tile_order_status.py
"""Status ladder / location / ageing derivation — pure functions, no DB.
The 20/12/8 case is the exact simultaneity example from the design doc:
20 ordered, 12 marked ready, 8 of those dispatched → 4 still ready, 8
dispatched, 8 never touched — status must be Partially Dispatched, not a
single "Ready" or "Dispatched" label that would hide the split."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.tile_order_status import (
    ageing_band, completion_percentage, derive_current_location, derive_item_status,
    rollup_status, supplier_silent_days, waiting_days,
)


def test_pending_when_nothing_ready_or_dispatched():
    assert derive_item_status(20, 0, 0) == "Pending"


def test_ready_when_some_ready_none_dispatched():
    assert derive_item_status(20, 12, 0) == "Ready"


def test_partially_dispatched_simultaneity_case():
    # 20 ordered / 12 marked ready / 8 of those dispatched → boxes_ready=4 remaining
    assert derive_item_status(20, 4, 8) == "Partially Dispatched"


def test_dispatched_when_fully_dispatched():
    assert derive_item_status(20, 0, 20) == "Dispatched"


def test_delivered_only_when_flagged_and_fully_dispatched():
    assert derive_item_status(20, 0, 20, all_delivered=True) == "Delivered"
    assert derive_item_status(20, 0, 15, all_delivered=True) == "Partially Dispatched"


def test_zero_ordered_is_pending_not_a_division_error():
    assert derive_item_status(0, 0, 0) == "Pending"


def test_current_location_decoupled_from_status():
    # Fully dispatched but still sitting at Buildcon's own godown — status
    # is Dispatched, location is Godown, simultaneously.
    assert derive_current_location(20, 0, 20, any_at_godown=True) == "Godown"
    assert derive_item_status(20, 0, 20) == "Dispatched"


def test_current_location_ladder():
    assert derive_current_location(20, 0, 0) == "Pending"
    assert derive_current_location(20, 12, 0) == "Ready"
    assert derive_current_location(20, 4, 8) == "Dispatched"
    assert derive_current_location(20, 0, 20, all_delivered=True) == "Delivered"


def test_completion_percentage():
    assert completion_percentage(20, 8) == 40.0
    assert completion_percentage(0, 0) == 0.0


def test_rollup_status_is_furthest_progress():
    assert rollup_status(["Pending", "Ready", "Dispatched"]) == "Dispatched"
    assert rollup_status(["Delivered", "Pending"]) == "Delivered"
    assert rollup_status([]) == "Pending"
    assert rollup_status(["Partially Dispatched", "Ready"]) == "Partially Dispatched"


def test_waiting_days():
    created = (datetime.now(timezone.utc) - timedelta(days=11)).isoformat()
    assert waiting_days(created) == 11


def test_ageing_band_boundaries():
    assert ageing_band(0) == "green"
    assert ageing_band(7) == "green"
    assert ageing_band(8) == "amber"
    assert ageing_band(14) == "amber"
    assert ageing_band(15) == "red"
    assert ageing_band(40) == "red"


def test_supplier_silent_days_falls_back_to_created_at():
    created = (datetime.now(timezone.utc) - timedelta(days=18)).isoformat()
    assert supplier_silent_days(None, created) == 18


def test_supplier_silent_days_uses_last_activity_when_present():
    created = (datetime.now(timezone.utc) - timedelta(days=18)).isoformat()
    last_activity = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert supplier_silent_days(last_activity, created) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/unit/test_tile_order_status.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.tile_order_status'`

- [ ] **Step 3: Write the module**

```python
# backend/services/tile_order_status.py
"""Pure status/ageing/completion derivation for Tile Orders logistics — no
DB access, mirrors the discipline of services/chalan_stage.py. Every write
endpoint in routes/tile_orders.py calls these after mutating box counters,
so the stored overall_status/current_location/completion_percentage never
drift from the counters that produced them.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

_STATUS_RANK = {"Pending": 0, "Ready": 1, "Partially Dispatched": 2, "Dispatched": 3, "Delivered": 4}
_LOCATION_RANK = {"Pending": 0, "Ready": 1, "Dispatched": 2, "Godown": 3, "Delivered": 4}


def derive_item_status(
    boxes_ordered: float, boxes_ready: float, boxes_dispatched: float, *, all_delivered: bool = False,
) -> str:
    """Furthest-progress milestone ladder: Pending → Ready → Partially
    Dispatched → Dispatched → Delivered. Deliberately ignores how the
    untouched remainder splits between ready/pending — a caller showing
    boxes_ready=4/boxes_dispatched=8/boxes_pending=8 alongside this status
    is what keeps "partially ready" and "partially dispatched" from being
    conflated, not the status string itself."""
    if boxes_ordered <= 0:
        return "Pending"
    if boxes_dispatched >= boxes_ordered:
        return "Delivered" if all_delivered else "Dispatched"
    if boxes_dispatched > 0:
        return "Partially Dispatched"
    if boxes_ready > 0:
        return "Ready"
    return "Pending"


def derive_current_location(
    boxes_ordered: float, boxes_ready: float, boxes_dispatched: float, *,
    any_at_godown: bool = False, all_delivered: bool = False,
) -> str:
    """Physical location — a separate axis from overall_status. Godown is
    explicitly NOT part of the status ladder: a fully-dispatched item can be
    current_location=Godown while its overall_status is still Dispatched,
    because the material already left the supplier and is simply waiting at
    Buildcon's own warehouse before final delivery."""
    if boxes_ordered <= 0:
        return "Pending"
    if all_delivered and boxes_dispatched >= boxes_ordered:
        return "Delivered"
    if any_at_godown:
        return "Godown"
    if boxes_dispatched > 0:
        return "Dispatched"
    if boxes_ready > 0:
        return "Ready"
    return "Pending"


def completion_percentage(boxes_ordered: float, boxes_dispatched: float) -> float:
    if boxes_ordered <= 0:
        return 0.0
    return round(100 * boxes_dispatched / boxes_ordered, 1)


def rollup_status(statuses: list[str]) -> str:
    """Furthest-progress rollup across a list of child statuses (items →
    PO, POs → CustomerOrder). Empty input rolls up to Pending — an order
    with no items yet has nothing further than Pending to report."""
    if not statuses:
        return "Pending"
    return max(statuses, key=lambda s: _STATUS_RANK.get(s, 0))


def waiting_days(created_at: str, *, today: Optional[datetime] = None) -> int:
    now = today or datetime.now(timezone.utc)
    created = datetime.fromisoformat(created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (now - created).days


def ageing_band(days: int) -> str:
    if days <= 7:
        return "green"
    if days <= 14:
        return "amber"
    return "red"


def supplier_silent_days(
    last_supplier_activity_at: Optional[str], created_at: str, *, today: Optional[datetime] = None,
) -> int:
    """Falls back to order creation time when the supplier has never had
    any logged activity yet — distinguishes 'old and the supplier worked on
    it yesterday' from 'old and silent' on the Company/Supplier dashboards."""
    return waiting_days(last_supplier_activity_at or created_at, today=today)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/test_tile_order_status.py -v`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/tile_order_status.py backend/tests/unit/test_tile_order_status.py
git commit -m "feat: add pure status/ageing/completion derivation for Tile Orders"
```

---

## Task 4: Indexes + startup wiring

**Files:**
- Create: `backend/services/tile_order_indexes.py`
- Modify: `backend/server.py` (startup event handler)
- Test: `backend/tests/unit/test_tile_order_indexes.py`

**Interfaces:**
- Produces: `async def ensure_tile_order_indexes() -> None` — called once from `server.py` startup, same as the existing `ensure_outbox_indexes()`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_tile_order_indexes.py
"""Index creation has no live DB in tests/unit, so this records what WOULD
be created against a fake db rather than hitting real Mongo — same
constraint every other index-setup function in this codebase has."""
from __future__ import annotations

import asyncio

from services import tile_order_indexes


class _RecordingCollection:
    def __init__(self):
        self.calls: list[tuple] = []

    async def create_index(self, keys, **kwargs):
        self.calls.append((keys, kwargs))


class _FakeDb:
    def __init__(self):
        self.customer_orders = _RecordingCollection()
        self.purchase_orders = _RecordingCollection()
        self.ready_batches = _RecordingCollection()
        self.dispatches = _RecordingCollection()
        self.chalans = _RecordingCollection()


def test_ensure_tile_order_indexes_creates_expected_indexes(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(tile_order_indexes, "db", fake_db)

    asyncio.run(tile_order_indexes.ensure_tile_order_indexes())

    assert len(fake_db.customer_orders.calls) == 4
    assert len(fake_db.purchase_orders.calls) == 3
    assert len(fake_db.ready_batches.calls) == 4
    assert len(fake_db.dispatches.calls) == 4
    assert len(fake_db.chalans.calls) == 2
    unique_names = {kwargs.get("name") for _, kwargs in fake_db.chalans.calls}
    assert "chalan_dispatch_unique" in unique_names
    assert "chalan_number_unique" in unique_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_tile_order_indexes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.tile_order_indexes'`

- [ ] **Step 3: Write the module**

```python
# backend/services/tile_order_indexes.py
"""Mongo indexes for the four new Tile Orders logistics collections.
Called once at app startup (server.py), alongside the existing
ensure_outbox_indexes()."""
from __future__ import annotations

from db import db


async def ensure_tile_order_indexes() -> None:
    await db.customer_orders.create_index("customer_id", name="customer_order_customer_id")
    await db.customer_orders.create_index("created_at", name="customer_order_created_at")
    await db.customer_orders.create_index("quotation_id", name="customer_order_quotation_id")
    await db.customer_orders.create_index("number", unique=True, name="customer_order_number_unique")

    await db.purchase_orders.create_index("customer_order_id", name="po_customer_order_id")
    await db.purchase_orders.create_index([("supplier_id", 1), ("overall_status", 1)], name="po_supplier_status")
    await db.purchase_orders.create_index("last_supplier_activity_at", name="po_last_supplier_activity")

    await db.ready_batches.create_index([("purchase_order_id", 1), ("po_item_id", 1)], name="ready_batch_po_item")
    await db.ready_batches.create_index("supplier_id", name="ready_batch_supplier")
    await db.ready_batches.create_index("customer_id", name="ready_batch_customer")
    await db.ready_batches.create_index("batch_number", unique=True, name="ready_batch_number_unique")

    await db.dispatches.create_index([("purchase_order_id", 1), ("dispatch_date", 1)], name="dispatch_po_date")
    await db.dispatches.create_index("supplier_id", name="dispatch_supplier")
    await db.dispatches.create_index("customer_id", name="dispatch_customer")
    await db.dispatches.create_index("dispatch_number", unique=True, name="dispatch_number_unique")

    await db.chalans.create_index("dispatch_id", unique=True, name="chalan_dispatch_unique")
    await db.chalans.create_index("number", unique=True, name="chalan_number_unique")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_tile_order_indexes.py -v`
Expected: PASS

- [ ] **Step 5: Wire into server.py startup**

In `backend/server.py`, add the import near the other index-setup imports (alongside wherever `ensure_outbox_indexes` is imported from `services.domain_outbox`):

```python
from services.tile_order_indexes import ensure_tile_order_indexes
```

Inside the `@app.on_event("startup")` handler, immediately after the existing `await ensure_outbox_indexes()` call, add:

```python
    await ensure_tile_order_indexes()
```

- [ ] **Step 6: Manually verify the app still boots**

Run: `cd backend && python -c "import server"` (import-only smoke check — confirms no syntax/import errors without needing a live Mongo connection for this step)
Expected: no exception

- [ ] **Step 7: Commit**

```bash
git add backend/services/tile_order_indexes.py backend/tests/unit/test_tile_order_indexes.py backend/server.py
git commit -m "feat: create indexes for Tile Orders logistics collections at startup"
```

---

## Task 5: Order placement — create `TileCustomerOrder`, denormalize tile fields

Extends the existing brand-split order-placement automation (`backend/services/domain_outbox.py`) rather than adding a parallel path — per the design doc's explicit reuse decision. **Must be gated to tiles doc types**: `_handle_order_placed` runs for both tiles AND standard (sanitaryware) quotations, and standard orders must never get a `TileCustomerOrder`.

**Files:**
- Modify: `backend/services/domain_outbox.py` (`_brand_groups` at line 116, `_handle_order_placed` at line 158)
- Test: `backend/tests/unit/test_domain_outbox_tile_customer_order.py`

**Interfaces:**
- Consumes: `TileCustomerOrder`, `TileCustomerOrderBrand`, `TileCustomerOrderDashboardSummary` (Task 1); `rollup_status` (Task 3); `PurchaseOrderItem.series/size/pieces_per_box` (Task 2).
- Produces: every `PurchaseOrder` created from a tiles quotation now has `customer_order_id` set; one `TileCustomerOrder` per "Place Order" click on a tiles quotation, `automation_key = f"order-placed:{quotation_id}:customer_order"`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_domain_outbox_tile_customer_order.py
"""_handle_order_placed must create exactly one TileCustomerOrder for a
tiles quotation (regardless of brand count), link every created
PurchaseOrder to it via customer_order_id, and must NOT create one for a
standard (sanitaryware) quotation — can_place_order() in tiles_stage.py
returns True unconditionally for doc_type=="standard", so this handler
runs for both and the tiles-only behavior must be explicitly gated."""
from __future__ import annotations

import asyncio

import pytest

import services.domain_outbox as outbox


class _FakeFind:
    def __init__(self, items):
        self._items = items

    async def to_list(self, n=None):
        return list(self._items)


class _FakeCollection:
    def __init__(self, seed=None):
        self.docs = list(seed or [])
        self.inserted: list[dict] = []

    def find(self, query=None, projection=None, session=None):
        return _FakeFind(self.docs)

    async def find_one(self, query=None, projection=None, session=None):
        query = query or {}
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None

    async def insert_one(self, doc, session=None):
        self.inserted.append(doc)
        self.docs.append(doc)

    async def update_one(self, query, update, upsert=False, session=None):
        existing = None
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                existing = doc
                break
        if existing is None and upsert:
            new_doc = dict(update.get("$setOnInsert") or update.get("$set") or {})
            self.docs.append(new_doc)
            self.inserted.append(new_doc)
        elif existing is not None and "$set" in update:
            existing.update(update["$set"])


class _FakeCounters:
    def __init__(self):
        self.docs: dict = {}

    async def find_one(self, query, *_a, **_kw):
        return self.docs.get(query.get("_id"))

    async def find_one_and_update(self, query, update, **_kw):
        key = query["_id"]
        doc = self.docs.setdefault(key, {"_id": key, "seq": 0})
        doc["seq"] += update["$inc"]["seq"]
        return dict(doc)


class _FakeDb:
    def __init__(self, quotation: dict):
        self.quotations = _FakeCollection([quotation])
        self.products = _FakeCollection([
            {"id": "p-1", "brand_id": "b-qutone", "series": "Metropole"},
            {"id": "p-2", "brand_id": "b-dimore", "series": "Zentrum"},
        ])
        self.brands = _FakeCollection([
            {"id": "b-qutone", "name": "Qutone"}, {"id": "b-dimore", "name": "Dimore"},
        ])
        self.suppliers = _FakeCollection([
            {"id": "s-1", "brand_id": "b-qutone", "name": "Qutone Rajkot", "active": True},
            {"id": "s-2", "brand_id": "b-dimore", "name": "Dimore Rajkot", "active": True},
        ])
        self.customers = _FakeCollection([
            {"id": "cust-1", "name": "Nileshbhai Pokiya", "phone": "9909900000", "address": "123 Ring Road", "city": "Rajkot"},
        ])
        self.purchase_orders = _FakeCollection()
        self.customer_orders = _FakeCollection()
        self.payments = _FakeCollection()
        self.activity_events = _FakeCollection()
        self.followups = _FakeCollection()
        self.counters = _FakeCounters()


def _tiles_quotation(**overrides) -> dict:
    base = {
        "id": "q-1", "number": "FQ-2026-0001", "doc_type": "tiles_quotation",
        "customer_id": "cust-1", "customer_name": "Nileshbhai Pokiya",
        "phone_snapshot": "9909900000", "address_snapshot": "123 Ring Road",
        "grand_total": 50000, "floor_id": "ground-floor",
        "items": [
            {"id": "li-1", "product_id": "p-1", "sku": "SKU-1", "name": "Glossy Ivory 600x600", "qty": 20, "unit_price": 1000, "size": "600X600", "pcs_per_box": "4"},
            {"id": "li-2", "product_id": "p-2", "sku": "SKU-2", "name": "Matte Grey 800x800", "qty": 10, "unit_price": 1500, "size": "800X800", "pcs_per_box": "2"},
        ],
    }
    base.update(overrides)
    return base


def _event(quotation_id: str) -> dict:
    return {
        "idempotency_key": f"order-placed:{quotation_id}", "actor_id": "u-sales", "actor_name": "Sales Rep",
        "payload": {"quotation_id": quotation_id},
    }


def test_tiles_quotation_creates_one_customer_order_linking_both_pos(monkeypatch):
    fake_db = _FakeDb(_tiles_quotation())
    monkeypatch.setattr(outbox, "db", fake_db)

    result = asyncio.run(outbox._handle_order_placed(_event("q-1"), session=None))

    assert len(fake_db.customer_orders.docs) == 1
    customer_order = fake_db.customer_orders.docs[0]
    assert customer_order["number"].startswith("TORD-")
    assert len(customer_order["brands"]) == 2
    po_ids = {b["purchase_order_id"] for b in customer_order["brands"]}
    assert po_ids == set(result["purchase_order_ids"])
    for po in fake_db.purchase_orders.docs:
        assert po["customer_order_id"] == customer_order["id"]
        assert po["items"][0]["series"] in {"Metropole", "Zentrum"}
        assert po["items"][0]["boxes_pending"] == po["items"][0]["qty"]


def test_standard_quotation_never_creates_customer_order(monkeypatch):
    fake_db = _FakeDb(_tiles_quotation(doc_type="standard"))
    monkeypatch.setattr(outbox, "db", fake_db)

    asyncio.run(outbox._handle_order_placed(_event("q-1"), session=None))

    assert fake_db.customer_orders.docs == []
    for po in fake_db.purchase_orders.docs:
        assert po["customer_order_id"] is None


def test_retry_is_idempotent_and_does_not_duplicate_customer_order(monkeypatch):
    fake_db = _FakeDb(_tiles_quotation())
    monkeypatch.setattr(outbox, "db", fake_db)

    event = _event("q-1")
    asyncio.run(outbox._handle_order_placed(event, session=None))
    asyncio.run(outbox._handle_order_placed(event, session=None))

    assert len(fake_db.customer_orders.docs) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_domain_outbox_tile_customer_order.py -v`
Expected: FAIL — `AssertionError` (no `customer_orders` writes happen yet) or `KeyError: 'customer_order_id'`

- [ ] **Step 3: Modify `_brand_groups` to denormalize `series`**

Replace the whole function (`backend/services/domain_outbox.py:116-139`):

```python
async def _brand_groups(quotation: dict, session: Any) -> list[dict]:
    product_ids = list({item["product_id"] for item in quotation.get("items", [])})
    products = await db.products.find(
        {"id": {"$in": product_ids}}, {"_id": 0, "id": 1, "brand_id": 1, "series": 1}, session=session,
    ).to_list(len(product_ids) + 5)
    product_by_id = {product["id"]: product for product in products}
    brand_ids = list({p.get("brand_id") for p in products if p.get("brand_id")})
    brands = await db.brands.find({"id": {"$in": brand_ids}}, {"_id": 0}, session=session).to_list(len(brand_ids) + 5)
    brand_by_id = {brand["id"]: brand for brand in brands}
    suppliers = await db.suppliers.find({"brand_id": {"$in": brand_ids}, "active": True}, {"_id": 0}, session=session).to_list(200)
    supplier_by_brand: dict[str, dict] = {}
    for supplier in suppliers:
        supplier_by_brand.setdefault(supplier.get("brand_id"), supplier)

    groups: dict[str, dict] = {}
    for item in quotation.get("items", []):
        product = product_by_id.get(item["product_id"], {})
        brand_id = product.get("brand_id") or "__unassigned__"
        group = groups.setdefault(brand_id, {
            "brand_id": None if brand_id == "__unassigned__" else brand_id,
            "brand_name": brand_by_id.get(brand_id, {}).get("name", "Unassigned"),
            "supplier": supplier_by_brand.get(brand_id),
            "items": [],
        })
        # Tile Orders logistics (Task 5): series lives on Product, not on
        # the quotation line item — attach it here so _handle_order_placed
        # can copy it onto PurchaseOrderItem without a second product fetch.
        group["items"].append({**item, "series": product.get("series")})
    return list(groups.values())
```

- [ ] **Step 4: Modify `_handle_order_placed`**

Replace the whole function (`backend/services/domain_outbox.py:158-235`):

```python
async def _handle_order_placed(event: dict, session: Any) -> dict:
    quotation_id = event["payload"]["quotation_id"]
    quotation = await db.quotations.find_one({"id": quotation_id}, {"_id": 0}, session=session)
    if not quotation:
        raise RuntimeError(f"Quotation {quotation_id} no longer exists")
    key = event["idempotency_key"]
    groups = await _brand_groups(quotation, session)
    net_by_line = per_line_net_amounts(quotation)

    # Tile Orders logistics (Task 5): _handle_order_placed runs for BOTH
    # tiles and standard (sanitaryware) quotations — tiles_stage.py's
    # can_place_order() returns True unconditionally for doc_type ==
    # "standard". A TileCustomerOrder must only ever be created for a
    # tiles quotation.
    is_tiles = quotation.get("doc_type") in ("tiles_selection", "tiles_quotation")
    customer_order: Optional[TileCustomerOrder] = None
    customer_order_key = f"{key}:customer_order"
    tile_total_products = 0
    tile_total_boxes = 0.0
    tile_total_value = 0.0

    if is_tiles:
        existing_co = await db.customer_orders.find_one({"automation_key": customer_order_key}, {"_id": 0}, session=session)
        if existing_co:
            customer_order = TileCustomerOrder(**{k: v for k, v in existing_co.items() if k != "automation_key"})
        else:
            customer = await db.customers.find_one({"id": quotation["customer_id"]}, {"_id": 0}, session=session) or {}
            customer_order = TileCustomerOrder(
                number=await next_number(
                    "customer_order", f"TORD-{datetime.now(timezone.utc).year}-",
                    collection="customer_orders", session=session,
                ),
                quotation_id=quotation_id, quotation_number=quotation.get("number"),
                customer_id=quotation["customer_id"], customer_name=quotation.get("customer_name", ""),
                customer_phone=quotation.get("phone_snapshot") or customer.get("phone") or "",
                # Immutable delivery snapshot — prefer the quotation's own
                # address/phone lines (tiles-quotation-specific, may differ
                # from the customer's default) over the live customer record.
                delivery_name=quotation.get("customer_name") or customer.get("name") or "",
                delivery_phone=quotation.get("phone_snapshot") or customer.get("phone") or "",
                delivery_address=quotation.get("address_snapshot") or customer.get("address") or "",
                delivery_city=customer.get("city") or "",
                # KNOWN GAP: the Customer model has no pincode/state fields
                # today (models.py:85-99) — left blank until that model
                # gains them; out of scope for this pass per the frozen
                # design doc (Customer model changes are not part of it).
                delivery_pincode="",
                delivery_state="",
                floor_id=floor_inherit(quotation),
                created_by=event["actor_id"], created_by_name=event["actor_name"],
                dashboard_summary=TileCustomerOrderDashboardSummary(
                    completion_percentage=0, overall_status="Pending", supplier_statuses=[],
                ),
            )

    created_po_ids: list[str] = []
    for group in groups:
        brand_key = group["brand_id"] or "unassigned"
        po_key = f"{key}:po:{brand_key}"
        existing = await db.purchase_orders.find_one({"automation_key": po_key}, {"_id": 0, "id": 1}, session=session)
        if existing:
            created_po_ids.append(existing["id"])
            continue
        now = now_iso()
        po_items = []
        for raw in group["items"]:
            qty = float(raw.get("qty") or 0)
            net_total = net_by_line.get(raw.get("id"))
            if net_total is None:
                unit_cost = round(float(raw.get("unit_price") or 0) * (1 - float(raw.get("discount_pct") or 0) / 100), 2)
            else:
                unit_cost = round(net_total / qty, 2) if qty else 0.0
            po_items.append(PurchaseOrderItem(
                product_id=raw["product_id"], sku=raw["sku"], name=raw["name"], image=raw.get("image"),
                finish=raw.get("finish"), category_id=raw.get("category_id"), room=raw.get("room"),
                qty=qty, unit_cost=unit_cost, quotation_line_id=raw.get("id"), stage="order_in_company",
                customer_id=quotation["customer_id"], customer_name=quotation.get("customer_name", ""),
                brand_id=group["brand_id"], brand_name=group["brand_name"],
                last_moved_at=now, last_moved_by=event["actor_id"], last_moved_by_name=event["actor_name"],
                stage_history=[PurchaseStageEvent(from_stage=None, to_stage="order_in_company", by_user_id=event["actor_id"], by_user_name=event["actor_name"], note=f"Created from {quotation.get('number')}", action="create")],
                # Tile Orders logistics (Task 5) — harmless no-op defaults
                # on non-tile orders, real data on tiles orders.
                series=raw.get("series"), size=raw.get("size"), pieces_per_box=raw.get("pcs_per_box"),
                boxes_ready=0, boxes_dispatched=0, boxes_pending=qty,
                current_location="Pending", overall_status="Pending",
            ))
        supplier = group.get("supplier") or {}
        po = PurchaseOrder(
            number=await _next_po_number(session), quotation_id=quotation_id, quotation_number=quotation.get("number"),
            customer_id=quotation["customer_id"], customer_name=quotation.get("customer_name", ""), project_name=quotation.get("project_name"),
            brand_id=group["brand_id"], brand_name=group["brand_name"], supplier_id=supplier.get("id"), supplier_name=supplier.get("name"),
            status="draft", items=po_items, subtotal=round(sum(item.qty * item.unit_cost for item in po_items), 2),
            grand_total=round(sum(item.qty * item.unit_cost for item in po_items), 2), created_by=event["actor_id"], created_by_name=event["actor_name"],
            floor_id=floor_inherit(quotation),
            status_history=[PurchaseStatusEvent(from_status=None, to_status="draft", by_user_id=event["actor_id"], by_user_name=event["actor_name"], note=f"Created from {quotation.get('number')}")],
            customer_order_id=(customer_order.id if customer_order else None),
        ).dict()
        po["automation_key"] = po_key
        await db.purchase_orders.insert_one(po, session=session)
        created_po_ids.append(po["id"])

        if is_tiles and customer_order is not None:
            tile_total_products += len(po_items)
            tile_total_boxes += sum(item.qty for item in po_items)
            tile_total_value += po["grand_total"]
            customer_order.brands.append(TileCustomerOrderBrand(
                brand_id=group["brand_id"], brand_name=group["brand_name"],
                supplier_id=supplier.get("id"), supplier_name=supplier.get("name") or "Unassigned",
                purchase_order_id=po["id"], status="Pending",
            ))
            await _upsert_activity(
                key=f"{key}:supplier-assigned:{brand_key}", event_type="supplier.assigned",
                entity_type="purchase", entity_id=po["id"],
                actor_id=event["actor_id"], actor_name=event["actor_name"],
                customer_id=quotation.get("customer_id"), quotation_id=quotation_id, purchase_id=po["id"],
                summary=f"Supplier {supplier.get('name') or 'Unassigned'} assigned for {group['brand_name']}",
                payload={"supplier_id": supplier.get("id"), "brand_id": group["brand_id"]}, session=session,
            )

    if is_tiles and customer_order is not None:
        customer_order.total_products = tile_total_products
        customer_order.total_boxes = tile_total_boxes
        customer_order.total_value = round(tile_total_value, 2)
        customer_order.overall_status = rollup_status([b.status for b in customer_order.brands])
        customer_order.completion_percentage = 0.0
        customer_order.dashboard_summary = TileCustomerOrderDashboardSummary(
            completion_percentage=0.0, overall_status=customer_order.overall_status,
            supplier_statuses=[{"supplier_name": b.supplier_name, "status": b.status} for b in customer_order.brands],
        )
        customer_order.last_activity = "Order created"
        customer_order.last_activity_at = now_iso()
        co_doc = customer_order.dict()
        co_doc["automation_key"] = customer_order_key
        await db.customer_orders.update_one(
            {"automation_key": customer_order_key}, {"$setOnInsert": co_doc}, upsert=True, session=session,
        )
        await _upsert_activity(
            key=f"{key}:customer_order_created", event_type="customer_order.created",
            entity_type="tile_customer_order", entity_id=customer_order.id,
            actor_id=event["actor_id"], actor_name=event["actor_name"],
            customer_id=quotation.get("customer_id"), quotation_id=quotation_id, purchase_id=None,
            summary=f"Customer order {customer_order.number} created — {len(customer_order.brands)} supplier(s)",
            payload={"customer_order_id": customer_order.id, "brand_count": len(customer_order.brands)}, session=session,
        )

    payment_key = f"{key}:payment"
    payment_amount = round(float(quotation.get("grand_total") or 0), 2)
    if payment_amount > 0:
        payment = Payment(
            quotation_id=quotation_id, quotation_number=quotation.get("number"), customer_id=quotation["customer_id"], customer_name=quotation.get("customer_name"),
            amount=payment_amount, mode="bank", status="pending", note="Outstanding balance created by OrderPlaced automation.",
            recorded_by=event["actor_id"], recorded_by_name=event["actor_name"],
            floor_id=floor_inherit(quotation),
        ).dict()
        payment.pop("idempotency_key", None)
        payment["automation_key"] = payment_key
        await db.payments.update_one({"automation_key": payment_key}, {"$setOnInsert": payment}, upsert=True, session=session)
    await _upsert_activity(
        key=f"{key}:timeline", event_type="quotation.order_placed", entity_type="quotation", entity_id=quotation_id,
        actor_id=event["actor_id"], actor_name=event["actor_name"], customer_id=quotation.get("customer_id"), quotation_id=quotation_id, purchase_id=None,
        summary=f"Order placed — {len(created_po_ids)} purchase order(s) created",
        payload={"event": EVENT_ORDER_PLACED, "purchase_order_ids": created_po_ids, "outstanding": payment_amount}, session=session,
    )
    await _upsert_followup(key=f"{key}:followup", quotation=quotation, reason=f"Order {quotation.get('number')} placed — confirm payment and delivery plan.", category="payment", session=session)
    return {
        "quotation_id": quotation_id,
        "purchase_order_ids": created_po_ids,
        "payment_amount": payment_amount,
        "count": len(created_po_ids),
        "customer_order_id": customer_order.id if customer_order else None,
        "post_commit_notification": {
            "user_id": quotation.get("created_by"),
            "title": f"Order confirmed · {quotation.get('number')}",
            "body": f"{len(created_po_ids)} purchase order(s) created for {quotation.get('customer_name')} — outstanding ₹{payment_amount:,.0f}",
            "kind": "success",
            "link": f"/quotations/{quotation_id}",
        },
    }
```

Add the two new imports at the top of `backend/services/domain_outbox.py` (alongside the existing `from models import ...` line):

```python
from models_tile_orders import TileCustomerOrder, TileCustomerOrderBrand, TileCustomerOrderDashboardSummary
from services.tile_order_status import rollup_status
```

And add `Optional` to the existing `from typing import Any` import line if not already present:

```python
from typing import Any, Optional
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_domain_outbox_tile_customer_order.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Run the full existing domain_outbox suite to confirm no regression**

Run: `cd backend && python -m pytest tests/unit -k domain_outbox -v`
Expected: PASS, including the pre-existing `test_domain_outbox_zero_amount_order.py`, `test_domain_outbox_floor_inheritance.py`, `test_domain_outbox_claim.py`, `test_domain_outbox_payment_idempotency_key.py`

- [ ] **Step 7: Commit**

```bash
git add backend/services/domain_outbox.py backend/tests/unit/test_domain_outbox_tile_customer_order.py
git commit -m "feat: create TileCustomerOrder on tiles order placement, denormalize series/size/pieces_per_box"
```

---

## Task 6: Router setup + bulk "Mark Ready" endpoint

**A note on transaction strategy for this and every write task below**: `purchases_tracker.py`'s single-document CAS pattern (`$elemMatch` pre-condition + retry) exists specifically for code that does **plain, non-transactional** `update_one` calls. `domain_outbox.py::_handle_order_placed` and `quotation_routes.py::place_order_confirm` instead wrap multi-step writes in a real `client.start_session()` / `session.start_transaction()` block and do **not** additionally hand-roll CAS inside it — MongoDB's own transaction conflict detection aborts (and the caller retries) on a genuine concurrent write to the same document. Every write route in this task and Tasks 7-8 follows the transaction pattern, not the CAS pattern, since each of them touches 2+ documents (a `PurchaseOrder` plus one or more of `ready_batches`/`dispatches`/`chalans`/`customer_orders`) that must commit together. `TileCustomerOrder.version` is still incremented on every write as the defense-in-depth guard the design doc calls for (useful for any future caller that updates it outside a transaction), even though the transaction itself is the primary safety net.

**Files:**
- Create: `backend/routes/tile_orders.py`
- Modify: `backend/server.py` (mount the router)
- Test: `backend/tests/unit/test_tile_orders_ready.py`

**Interfaces:**
- Consumes: `TileReadyBatch` (Task 1), `derive_item_status`/`derive_current_location`/`rollup_status` (Task 3), `PurchaseOrderItem` tile fields (Task 2).
- Produces: `router` (FastAPI `APIRouter`, mounted at `/tile-orders`) — every later route task adds handlers to this same `router` object; `POST /tile-orders/purchase-orders/{po_id}/ready`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_tile_orders_ready.py
"""Bulk 'Mark Ready' — creates one ReadyBatch per line in one transaction,
bumps boxes_ready/boxes_pending, recomputes status/location. Uses the same
hand-rolled-fake-db + monkeypatch pattern as test_purchases_chalan_generation.py."""
from __future__ import annotations

import asyncio

import pytest

from models import UserPublic
from routes import tile_orders as router_module


def _user() -> UserPublic:
    return UserPublic(email="wh@forge.app", full_name="Warehouse Rep", role="warehouse", floor_ids=["ground-floor"], active_floor_id="ground-floor")


def _po(**overrides) -> dict:
    base = {
        "id": "po-1", "number": "FPO-2026-0001", "customer_id": "cust-1", "customer_name": "Nileshbhai Pokiya",
        "customer_order_id": "co-1", "supplier_id": "s-1", "supplier_name": "Qutone Rajkot",
        "items": [{
            "id": "item-1", "name": "Glossy Ivory 600x600", "series": "Metropole", "finish": None,
            "size": "600X600", "sku": "SKU-1", "qty": 20, "boxes_ready": 0, "boxes_dispatched": 0,
            "boxes_pending": 20, "overall_status": "Pending", "current_location": "Pending",
        }],
    }
    base.update(overrides)
    return base


class _FakeSession:
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False
    def start_transaction(self): return self


class _FakeClient:
    async def start_session(self): return _FakeSession()


class _FakePOs:
    def __init__(self, po):
        self.po = po
        self.set_calls: list[dict] = []

    async def find_one(self, query, *_a, session=None, **_kw):
        return dict(self.po) if self.po else None

    async def update_one(self, query, update, session=None, **_kw):
        self.set_calls.append(update["$set"])
        self.po.update(update["$set"])
        class _Result:
            matched_count = 1
        return _Result()


class _FakeReadyBatches:
    def __init__(self):
        self.inserted: list[dict] = []

    async def insert_one(self, doc, session=None):
        self.inserted.append(doc)


class _FakeCustomerOrders:
    def __init__(self, co):
        self.co = co

    async def find_one(self, query, *_a, session=None, **_kw):
        return dict(self.co) if self.co else None

    async def update_one(self, query, update, session=None, **_kw):
        self.co.update(update["$set"])
        class _Result:
            matched_count = 1
        return _Result()


class _FakeDb:
    def __init__(self, po, co):
        self.purchase_orders = _FakePOs(po)
        self.ready_batches = _FakeReadyBatches()
        self.customer_orders = _FakeCustomerOrders(co)


async def _fake_next_number(*_a, **_kw):
    return "RB-2026-0001"


async def _noop_log_event(**_kwargs):
    return None


def _customer_order():
    return {
        "id": "co-1", "version": 0, "brands": [{
            "brand_id": "b-1", "brand_name": "Qutone", "supplier_id": "s-1", "supplier_name": "Qutone Rajkot",
            "purchase_order_id": "po-1", "status": "Pending",
        }],
    }


def test_mark_ready_creates_batch_and_updates_counters(monkeypatch):
    fake_db = _FakeDb(_po(), _customer_order())
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "client", _FakeClient())
    monkeypatch.setattr(router_module, "next_number", _fake_next_number)
    monkeypatch.setattr(router_module, "log_event", _noop_log_event)

    body = router_module.BulkReadyBody(items=[router_module.ReadyItemInput(po_item_id="item-1", qty=8)])
    result = asyncio.run(router_module.mark_items_ready("po-1", body, user=_user()))

    assert result["ready_batches"][0]["batch_number"] == "RB-2026-0001"
    updated_item = fake_db.purchase_orders.po["items"][0]
    assert updated_item["boxes_ready"] == 8
    assert updated_item["boxes_pending"] == 12
    assert updated_item["overall_status"] == "Ready"
    assert fake_db.ready_batches.inserted[0]["remaining_qty"] == 8


def test_mark_ready_rejects_over_pending(monkeypatch):
    fake_db = _FakeDb(_po(), _customer_order())
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "client", _FakeClient())
    monkeypatch.setattr(router_module, "next_number", _fake_next_number)

    body = router_module.BulkReadyBody(items=[router_module.ReadyItemInput(po_item_id="item-1", qty=999)])
    with pytest.raises(Exception) as exc:
        asyncio.run(router_module.mark_items_ready("po-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_tile_orders_ready.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'routes.tile_orders'`

- [ ] **Step 3: Write the router file**

```python
# backend/routes/tile_orders.py
"""Tile Orders logistics — Ready/Dispatch/Chalan actions and the Company/
Supplier/Customer/Dispatch-List read endpoints. Order placement (creating
the TileCustomerOrder itself) lives in services/domain_outbox.py, not here
— see that file's _handle_order_placed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import floor_query, require_min_role
from db import client, db
from models import UserPublic, now_iso
from models_tile_orders import TileReadyBatch
from services.activity_log import log_event
from services.sequence import next_number
from services.tile_order_status import (
    completion_percentage, derive_current_location, derive_item_status, rollup_status,
)

router = APIRouter(prefix="/tile-orders", tags=["tile-orders"])


class ReadyItemInput(BaseModel):
    po_item_id: str
    qty: float = Field(gt=0)


class BulkReadyBody(BaseModel):
    items: list[ReadyItemInput] = Field(min_length=1)


async def _sync_customer_order_brand_status(co_id: Optional[str], po_id: str, new_status: str, session) -> None:
    """Updates this PO's entry in TileCustomerOrder.brands[], then rolls the
    CustomerOrder's own overall_status/dashboard_summary up from all
    brands. Increments `version` as the defense-in-depth CAS guard the
    design doc calls for — the enclosing transaction is the primary safety
    net (see Task 6's transaction-strategy note)."""
    if not co_id:
        return
    co = await db.customer_orders.find_one({"id": co_id}, {"_id": 0}, session=session)
    if not co:
        return
    brands = co.get("brands", [])
    for brand in brands:
        if brand.get("purchase_order_id") == po_id:
            brand["status"] = new_status
    overall = rollup_status([b.get("status", "Pending") for b in brands])
    summary = {
        "completion_percentage": co.get("completion_percentage", 0),
        "overall_status": overall,
        "supplier_statuses": [{"supplier_name": b.get("supplier_name"), "status": b.get("status")} for b in brands],
    }
    await db.customer_orders.update_one(
        {"id": co_id, "version": co.get("version", 0)},
        {"$set": {
            "brands": brands, "overall_status": overall, "dashboard_summary": summary,
            "last_activity": "Status changed", "last_activity_at": now_iso(),
            "version": co.get("version", 0) + 1, "updated_at": now_iso(),
        }},
        session=session,
    )


@router.post("/purchase-orders/{po_id}/ready")
async def mark_items_ready(
    po_id: str, body: BulkReadyBody, user: UserPublic = Depends(require_min_role("warehouse")),
):
    """'Mark Ready For Pickup' — bulk, one transaction. Never creates a
    Chalan (see Task 8's Dispatch endpoint for that)."""
    session = await client.start_session()
    async with session:
        async with session.start_transaction():
            po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0}, session=session)
            if not po:
                raise HTTPException(status_code=404, detail="Purchase order not found")
            items_by_id = {item["id"]: item for item in po.get("items", [])}
            created_batches: list[dict] = []
            year = datetime.now(timezone.utc).year
            new_status: Optional[str] = None
            for entry in body.items:
                item = items_by_id.get(entry.po_item_id)
                if not item:
                    raise HTTPException(status_code=400, detail=f"Unknown item {entry.po_item_id}")
                pending = float(item.get("boxes_pending") or 0)
                if entry.qty > pending + 1e-6:
                    raise HTTPException(status_code=400, detail=f"Only {pending:g} boxes of '{item.get('name')}' are pending")

                batch_number = await next_number("ready_batch", f"RB-{year}-", collection="ready_batches", session=session)
                batch = TileReadyBatch(
                    batch_number=batch_number, purchase_order_id=po_id, po_item_id=entry.po_item_id,
                    customer_order_id=po.get("customer_order_id") or "", floor_id=po.get("floor_id", "first-floor"),
                    supplier_id=po.get("supplier_id"),
                    supplier_name=po.get("supplier_name") or "Unassigned", customer_id=po.get("customer_id"),
                    customer_name=po.get("customer_name") or "", tile_name=item.get("name", ""),
                    series=item.get("series"), finish=item.get("finish"), size=item.get("size"), sku=item.get("sku"),
                    qty=entry.qty, remaining_qty=entry.qty, created_by=user.id, created_by_name=user.full_name,
                )
                await db.ready_batches.insert_one(batch.dict(), session=session)
                created_batches.append(batch.dict())

                item["boxes_ready"] = float(item.get("boxes_ready") or 0) + entry.qty
                item["boxes_pending"] = pending - entry.qty
                item["overall_status"] = derive_item_status(item["qty"], item["boxes_ready"], float(item.get("boxes_dispatched") or 0))
                item["current_location"] = derive_current_location(item["qty"], item["boxes_ready"], float(item.get("boxes_dispatched") or 0))

            items = list(items_by_id.values())
            ready_boxes = sum(float(i.get("boxes_ready") or 0) for i in items)
            pending_boxes = sum(float(i.get("boxes_pending") or 0) for i in items)
            dispatched_boxes = sum(float(i.get("boxes_dispatched") or 0) for i in items)
            ordered_boxes = sum(float(i.get("qty") or 0) for i in items)
            new_status = rollup_status([i["overall_status"] for i in items])
            now = now_iso()
            await db.purchase_orders.update_one(
                {"id": po_id}, {"$set": {
                    "items": items, "ready_boxes": ready_boxes, "pending_boxes": pending_boxes,
                    "dispatched_boxes": dispatched_boxes, "overall_status": new_status,
                    "completion_percentage": completion_percentage(ordered_boxes, dispatched_boxes),
                    "latest_ready_date": now, "last_supplier_activity_at": now, "updated_at": now,
                }}, session=session,
            )
            await _sync_customer_order_brand_status(po.get("customer_order_id"), po_id, new_status, session)

    for batch in created_batches:
        await log_event(
            event_type="ready_batch.created", entity_type="purchase", entity_id=po_id, actor=user,
            customer_id=po.get("customer_id"), purchase_id=po_id,
            summary=f"Marked {batch['qty']:g} boxes of '{batch['tile_name']}' ready ({batch['batch_number']})",
            payload={"ready_batch_id": batch["id"], "batch_number": batch["batch_number"], "po_item_id": batch["po_item_id"], "qty": batch["qty"]},
        )
    if new_status:
        await log_event(
            event_type="status.changed", entity_type="purchase", entity_id=po_id, actor=user,
            customer_id=po.get("customer_id"), purchase_id=po_id,
            summary=f"Status changed to {new_status}", payload={"to": new_status},
        )
    return {"po_id": po_id, "ready_batches": created_batches, "overall_status": new_status}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_tile_orders_ready.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Mount the router in server.py**

In `backend/server.py`, add the import alongside the other route imports:

```python
from routes.tile_orders import router as tile_orders_router
```

Add the mount call alongside the other `api.include_router(...)` calls:

```python
api.include_router(tile_orders_router)
```

- [ ] **Step 6: Commit**

```bash
git add backend/routes/tile_orders.py backend/tests/unit/test_tile_orders_ready.py backend/server.py
git commit -m "feat: add tile_orders router with bulk Mark Ready endpoint"
```

---

## Task 7: Dispatch preview + commit (creates Dispatch + immutable Chalan)

The most complex endpoint in the feature: consumes one or more `ReadyBatch` rows (or dispatches straight from Pending, auto-creating a fully-consumed batch behind the scenes so every dispatched box still traces to a batch record), creates one `TileDispatch` and its immutable `TileChalan` in the same transaction, and updates both item- and PO-level rollups.

**A note on Preview and numbering**: `services/sequence.py::next_number` has no "peek" mode — every call atomically increments a real counter. If `/dispatch/preview` called it, a staff member opening and abandoning the preview sheet twice would burn two real `DSP-`/`CH-` numbers before ever confirming. So preview does **not** mint numbers at all; it returns the product/box breakdown and warnings with the numbers shown as `"assigned on confirm"` rather than a fabricated exact value. This is a refinement of the design doc's wording ("Dispatch DSP-2026-0004 → Chalan CH-2026-0032") discovered while implementing it — the creation *chain* (Dispatch → Chalan → Dispatch List entry) is still shown, just without pre-assigning real numbers.

**Files:**
- Modify: `backend/routes/tile_orders.py`
- Test: `backend/tests/unit/test_tile_orders_dispatch.py`

**Interfaces:**
- Consumes: `TileReadyBatch`, `TileDispatch`, `TileDispatchLineConsumed`, `TileChalan`, `TileChalanItem` (Task 1); `_sync_customer_order_brand_status` (Task 6).
- Produces: `POST /tile-orders/purchase-orders/{po_id}/dispatch/preview`, `POST /tile-orders/purchase-orders/{po_id}/dispatch`; `DispatchLineInput`, `DispatchBody` — reused by the frontend dispatch sheet (Task 18).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_tile_orders_dispatch.py
from __future__ import annotations

import asyncio

import pytest

from models import UserPublic
from routes import tile_orders as router_module


def _user() -> UserPublic:
    return UserPublic(email="wh@forge.app", full_name="Warehouse Rep", role="warehouse", floor_ids=["ground-floor"], active_floor_id="ground-floor")


def _po(**overrides) -> dict:
    base = {
        "id": "po-1", "number": "FPO-2026-0001", "customer_id": "cust-1", "customer_name": "Nileshbhai Pokiya",
        "customer_order_id": "co-1", "supplier_id": "s-1", "supplier_name": "Qutone Rajkot",
        "items": [{
            "id": "item-1", "name": "Glossy Ivory 600x600", "series": "Metropole", "finish": None,
            "size": "600X600", "sku": "SKU-1", "pieces_per_box": "4", "qty": 20,
            "boxes_ready": 12, "boxes_dispatched": 0, "boxes_pending": 8,
            "overall_status": "Ready", "current_location": "Ready",
        }],
    }
    base.update(overrides)
    return base


def _ready_batch(**overrides) -> dict:
    base = {
        "id": "rb-1", "batch_number": "RB-2026-0001", "purchase_order_id": "po-1", "po_item_id": "item-1",
        "qty": 12, "remaining_qty": 12, "auto_created": False,
    }
    base.update(overrides)
    return base


class _FakeSession:
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False
    def start_transaction(self): return self


class _FakeClient:
    async def start_session(self): return _FakeSession()


class _FakePOs:
    def __init__(self, po):
        self.po = po

    async def find_one(self, query, *_a, session=None, **_kw):
        return dict(self.po) if self.po else None

    async def update_one(self, query, update, session=None, **_kw):
        self.po.update(update["$set"])
        class _R: matched_count = 1
        return _R()


class _FakeReadyBatches:
    def __init__(self, batches):
        self.docs = {b["id"]: dict(b) for b in batches}
        self.inserted: list[dict] = []

    async def find_one(self, query, *_a, session=None, **_kw):
        for doc in self.docs.values():
            if doc.get("id") == query.get("id"):
                return dict(doc)
        return None

    async def insert_one(self, doc, session=None):
        self.docs[doc["id"]] = doc
        self.inserted.append(doc)

    async def update_one(self, query, update, session=None, **_kw):
        doc = self.docs[query["id"]]
        doc.update(update["$set"])
        class _R: matched_count = 1
        return _R()


class _FakeDispatches:
    def __init__(self):
        self.inserted: list[dict] = []

    async def insert_one(self, doc, session=None):
        self.inserted.append(doc)


class _FakeChalans:
    def __init__(self):
        self.inserted: list[dict] = []

    async def insert_one(self, doc, session=None):
        self.inserted.append(doc)


class _FakeCustomerOrders:
    def __init__(self, co):
        self.co = co

    async def find_one(self, query, *_a, session=None, **_kw):
        return dict(self.co) if self.co else None

    async def update_one(self, query, update, session=None, **_kw):
        self.co.update(update["$set"])
        class _R: matched_count = 1
        return _R()


class _FakeDb:
    def __init__(self, po, ready_batches, co):
        self.purchase_orders = _FakePOs(po)
        self.ready_batches = _FakeReadyBatches(ready_batches)
        self.dispatches = _FakeDispatches()
        self.chalans = _FakeChalans()
        self.customer_orders = _FakeCustomerOrders(co)


def _customer_order():
    return {"id": "co-1", "version": 0, "brands": [{
        "brand_id": "b-1", "brand_name": "Qutone", "supplier_id": "s-1", "supplier_name": "Qutone Rajkot",
        "purchase_order_id": "po-1", "status": "Ready",
    }]}


_DESTINATION = dict(destination_type="Customer", destination_name="Nileshbhai Pokiya", destination_address="123 Ring Road", destination_city="Rajkot")


async def _fake_next_number(kind, *_a, **_kw):
    return "DSP-2026-0001" if kind == "dispatch" else ("RB-2026-0002" if kind == "ready_batch" else "CH-0001")


async def _noop_log_event(**_kwargs):
    return None


def test_preview_never_mutates_state(monkeypatch):
    fake_db = _FakeDb(_po(), [_ready_batch()], _customer_order())
    monkeypatch.setattr(router_module, "db", fake_db)

    body = router_module.DispatchBody(
        items=[router_module.DispatchLineInput(po_item_id="item-1", ready_batch_id="rb-1", qty=5)], **_DESTINATION,
    )
    result = asyncio.run(router_module.preview_dispatch("po-1", body, user=_user()))

    assert result["items"][0]["qty"] == 5
    assert fake_db.dispatches.inserted == []
    assert fake_db.chalans.inserted == []
    assert fake_db.ready_batches.docs["rb-1"]["remaining_qty"] == 12  # untouched


def test_dispatch_from_existing_ready_batch(monkeypatch):
    fake_db = _FakeDb(_po(), [_ready_batch()], _customer_order())
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "client", _FakeClient())
    monkeypatch.setattr(router_module, "next_number", _fake_next_number)
    monkeypatch.setattr(router_module, "log_event", _noop_log_event)

    body = router_module.DispatchBody(
        items=[router_module.DispatchLineInput(po_item_id="item-1", ready_batch_id="rb-1", qty=5)], **_DESTINATION,
    )
    result = asyncio.run(router_module.commit_dispatch("po-1", body, user=_user()))

    assert result["dispatch"]["dispatch_number"] == "DSP-2026-0001"
    assert result["chalan"]["number"] == "CH-0001"
    assert result["chalan"]["items"][0]["quantity"] == 5   # only the dispatched qty, not the whole order
    assert fake_db.ready_batches.docs["rb-1"]["remaining_qty"] == 7
    item = fake_db.purchase_orders.po["items"][0]
    assert item["boxes_ready"] == 7
    assert item["boxes_dispatched"] == 5
    assert item["boxes_pending"] == 8
    assert item["overall_status"] == "Partially Dispatched"


def test_direct_dispatch_from_pending_auto_creates_ready_batch(monkeypatch):
    fake_db = _FakeDb(_po(), [], _customer_order())
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "client", _FakeClient())
    monkeypatch.setattr(router_module, "next_number", _fake_next_number)
    monkeypatch.setattr(router_module, "log_event", _noop_log_event)

    body = router_module.DispatchBody(
        items=[router_module.DispatchLineInput(po_item_id="item-1", ready_batch_id=None, qty=3)], **_DESTINATION,
    )
    result = asyncio.run(router_module.commit_dispatch("po-1", body, user=_user()))

    auto_batch = [b for b in fake_db.ready_batches.inserted if b["auto_created"]][0]
    assert auto_batch["qty"] == 3
    assert auto_batch["remaining_qty"] == 0
    item = fake_db.purchase_orders.po["items"][0]
    assert item["boxes_pending"] == 5      # 8 - 3
    assert item["boxes_dispatched"] == 3
    assert item["boxes_ready"] == 12       # untouched — this dispatch came from pending, not from the existing batch
    assert result["dispatch"]["ready_batches_consumed"][0]["ready_batch_id"] == auto_batch["id"]


def test_dispatch_rejects_over_consuming_a_batch(monkeypatch):
    fake_db = _FakeDb(_po(), [_ready_batch(remaining_qty=2)], _customer_order())
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "client", _FakeClient())

    body = router_module.DispatchBody(
        items=[router_module.DispatchLineInput(po_item_id="item-1", ready_batch_id="rb-1", qty=5)], **_DESTINATION,
    )
    with pytest.raises(Exception) as exc:
        asyncio.run(router_module.commit_dispatch("po-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/unit/test_tile_orders_dispatch.py -v`
Expected: FAIL — `AttributeError: module 'routes.tile_orders' has no attribute 'preview_dispatch'`

- [ ] **Step 3: Add the dispatch models, preview, and commit handlers**

Append to `backend/routes/tile_orders.py` (after the `mark_items_ready` function):

```python
from typing import Literal
from uuid import uuid4

from models_tile_orders import TileChalan, TileChalanItem, TileDispatch, TileDispatchLineConsumed


class DispatchLineInput(BaseModel):
    po_item_id: str
    ready_batch_id: Optional[str] = None   # None = dispatch straight from Pending
    qty: float = Field(gt=0)


class DispatchBody(BaseModel):
    items: list[DispatchLineInput] = Field(min_length=1)
    destination_type: Literal["Customer", "Godown"]
    destination_name: str
    destination_address: str
    destination_city: str
    reference_number: Optional[str] = None
    receiver_name: Optional[str] = None
    sender_name: Optional[str] = None


async def _resolve_dispatch_lines(po: dict, body: DispatchBody, session=None) -> tuple[list[dict], list[dict], list[str]]:
    """Shared by preview and commit. Returns (resolved_lines, warnings,
    errors) — resolved_lines carries per-line {po_item_id, qty, source
    ('existing'|'pending'), item, batch_or_none}. Raises 400 on any error
    that would make the dispatch invalid (unknown item, over-consuming a
    batch, more than what's Pending)."""
    items_by_id = {item["id"]: item for item in po.get("items", [])}
    resolved: list[dict] = []
    warnings: list[str] = []
    for entry in body.items:
        item = items_by_id.get(entry.po_item_id)
        if not item:
            raise HTTPException(status_code=400, detail=f"Unknown item {entry.po_item_id}")
        if entry.ready_batch_id:
            batch = await db.ready_batches.find_one({"id": entry.ready_batch_id}, {"_id": 0}, session=session)
            if not batch or batch.get("po_item_id") != entry.po_item_id:
                raise HTTPException(status_code=400, detail=f"Ready batch {entry.ready_batch_id} not found for this item")
            if entry.qty > float(batch.get("remaining_qty") or 0) + 1e-6:
                raise HTTPException(status_code=400, detail=f"Only {batch['remaining_qty']:g} boxes remain in batch {batch['batch_number']}")
            resolved.append({"po_item_id": entry.po_item_id, "qty": entry.qty, "source": "existing", "item": item, "batch": batch})
        else:
            pending = float(item.get("boxes_pending") or 0)
            if entry.qty > pending + 1e-6:
                raise HTTPException(status_code=400, detail=f"Only {pending:g} boxes of '{item.get('name')}' are pending")
            warnings.append(f"'{item.get('name')}' will be dispatched directly from Pending — a Ready Batch is created automatically for the audit trail.")
            resolved.append({"po_item_id": entry.po_item_id, "qty": entry.qty, "source": "pending", "item": item, "batch": None})
    return resolved, warnings


@router.post("/purchase-orders/{po_id}/dispatch/preview")
async def preview_dispatch(po_id: str, body: DispatchBody, user: UserPublic = Depends(require_min_role("warehouse"))):
    po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    resolved, warnings = await _resolve_dispatch_lines(po, body)
    lines = [{
        "po_item_id": r["po_item_id"], "tile_name": r["item"].get("name"), "qty": r["qty"],
        "source": r["source"], "remaining_pending_after": float(r["item"].get("boxes_pending") or 0) - (r["qty"] if r["source"] == "pending" else 0),
    } for r in resolved]
    return {
        "po_id": po_id, "items": lines, "warnings": warnings,
        "will_create": {"dispatch_number": "assigned on confirm", "chalan_number": "assigned on confirm", "creates_dispatch_list_entry": True},
    }


@router.post("/purchase-orders/{po_id}/dispatch")
async def commit_dispatch(po_id: str, body: DispatchBody, user: UserPublic = Depends(require_min_role("warehouse"))):
    session = await client.start_session()
    async with session:
        async with session.start_transaction():
            po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0}, session=session)
            if not po:
                raise HTTPException(status_code=404, detail="Purchase order not found")
            resolved, _warnings = await _resolve_dispatch_lines(po, body, session=session)
            items_by_id = {item["id"]: item for item in po.get("items", [])}
            year = datetime.now(timezone.utc).year
            consumed: list[TileDispatchLineConsumed] = []
            chalan_items: list[TileChalanItem] = []

            for r in resolved:
                item = items_by_id[r["po_item_id"]]
                qty = r["qty"]
                if r["source"] == "existing":
                    batch = r["batch"]
                    new_remaining = float(batch["remaining_qty"]) - qty
                    await db.ready_batches.update_one({"id": batch["id"]}, {"$set": {"remaining_qty": new_remaining}}, session=session)
                    item["boxes_ready"] = float(item.get("boxes_ready") or 0) - qty
                    ready_batch_id = batch["id"]
                else:
                    batch_number = await next_number("ready_batch", f"RB-{year}-", collection="ready_batches", session=session)
                    auto_batch = TileReadyBatch(
                        batch_number=batch_number, purchase_order_id=po_id, po_item_id=r["po_item_id"],
                        customer_order_id=po.get("customer_order_id") or "", floor_id=po.get("floor_id", "first-floor"),
                        supplier_id=po.get("supplier_id"),
                        supplier_name=po.get("supplier_name") or "Unassigned", customer_id=po.get("customer_id"),
                        customer_name=po.get("customer_name") or "", tile_name=item.get("name", ""),
                        series=item.get("series"), finish=item.get("finish"), size=item.get("size"), sku=item.get("sku"),
                        qty=qty, remaining_qty=0, created_by=user.id, created_by_name=user.full_name, auto_created=True,
                    )
                    await db.ready_batches.insert_one(auto_batch.dict(), session=session)
                    ready_batch_id = auto_batch.id
                    item["boxes_pending"] = float(item.get("boxes_pending") or 0) - qty

                item["boxes_dispatched"] = float(item.get("boxes_dispatched") or 0) + qty
                item["overall_status"] = derive_item_status(item["qty"], item["boxes_ready"], item["boxes_dispatched"])
                item["current_location"] = derive_current_location(item["qty"], item["boxes_ready"], item["boxes_dispatched"])
                consumed.append(TileDispatchLineConsumed(ready_batch_id=ready_batch_id, po_item_id=r["po_item_id"], qty=qty))
                chalan_items.append(TileChalanItem(
                    po_item_id=r["po_item_id"], tile_name=item.get("name", ""), series=item.get("series"),
                    finish=item.get("finish"), size=item.get("size"), sku=item.get("sku"),
                    # boxes == quantity here: pieces_per_box is free text (e.g. "4" or
                    # "BOX", same convention as the old ChalanLineItem.unit field) so it
                    # cannot be reliably multiplied into a separate numeric piece count.
                    boxes=qty, pieces_per_box=item.get("pieces_per_box"), quantity=qty,
                ))

            now = now_iso()
            dispatch_number = await next_number("dispatch", f"DSP-{year}-", collection="dispatches", session=session)
            chalan_number = await next_number("chalan", "CH-", collection="chalans", width=4, session=session)

            chalan = TileChalan(
                number=chalan_number, dispatch_id="", purchase_order_id=po_id, customer_order_id=po.get("customer_order_id") or "",
                floor_id=po.get("floor_id", "first-floor"),
                supplier_name=po.get("supplier_name") or "Unassigned", customer_name=po.get("customer_name") or "",
                customer_phone=body.destination_name and po.get("customer_phone") or "",
                delivery_address=body.destination_address, delivery_city=body.destination_city,
                reference_number=body.reference_number, items=chalan_items,
                receiver_name=body.receiver_name, sender_name=body.sender_name,
                created_by=user.id, created_by_name=user.full_name,
                generated_at=now, generated_by_name=user.full_name,
            )
            dispatch = TileDispatch(
                dispatch_number=dispatch_number, purchase_order_id=po_id, customer_order_id=po.get("customer_order_id") or "",
                floor_id=po.get("floor_id", "first-floor"),
                supplier_id=po.get("supplier_id"), supplier_name=po.get("supplier_name") or "Unassigned",
                customer_id=po.get("customer_id"), customer_name=po.get("customer_name") or "",
                ready_batches_consumed=consumed, destination_type=body.destination_type,
                destination_name=body.destination_name, destination_address=body.destination_address,
                destination_city=body.destination_city, dispatch_date=now[:10], dispatch_time=now[11:16],
                created_by=user.id, created_by_name=user.full_name, chalan_id=chalan.id,
            )
            chalan.dispatch_id = dispatch.id
            await db.chalans.insert_one(chalan.dict(), session=session)
            await db.dispatches.insert_one(dispatch.dict(), session=session)

            items = list(items_by_id.values())
            ordered_boxes = sum(float(i.get("qty") or 0) for i in items)
            dispatched_boxes = sum(float(i.get("boxes_dispatched") or 0) for i in items)
            new_status = rollup_status([i["overall_status"] for i in items])
            await db.purchase_orders.update_one(
                {"id": po_id}, {"$set": {
                    "items": items,
                    "ready_boxes": sum(float(i.get("boxes_ready") or 0) for i in items),
                    "pending_boxes": sum(float(i.get("boxes_pending") or 0) for i in items),
                    "dispatched_boxes": dispatched_boxes, "overall_status": new_status,
                    "completion_percentage": completion_percentage(ordered_boxes, dispatched_boxes),
                    "latest_dispatch_date": now, "last_supplier_activity_at": now, "updated_at": now,
                }}, session=session,
            )
            await _sync_customer_order_brand_status(po.get("customer_order_id"), po_id, new_status, session)

    await log_event(
        event_type="dispatch.created", entity_type="purchase", entity_id=po_id, actor=user,
        customer_id=po.get("customer_id"), purchase_id=po_id,
        summary=f"Dispatch {dispatch.dispatch_number} created — {len(chalan_items)} line(s)",
        payload={"dispatch_id": dispatch.id, "dispatch_number": dispatch.dispatch_number},
    )
    await log_event(
        event_type="chalan.generated", entity_type="purchase", entity_id=po_id, actor=user,
        customer_id=po.get("customer_id"), purchase_id=po_id,
        summary=f"Chalan {chalan.number} generated for Dispatch {dispatch.dispatch_number}",
        payload={"chalan_id": chalan.id, "chalan_number": chalan.number, "dispatch_id": dispatch.id},
    )
    await log_event(
        event_type="status.changed", entity_type="purchase", entity_id=po_id, actor=user,
        customer_id=po.get("customer_id"), purchase_id=po_id,
        summary=f"Status changed to {new_status}", payload={"to": new_status},
    )
    return {"po_id": po_id, "dispatch": dispatch.dict(), "chalan": chalan.dict(), "overall_status": new_status}
```

Note the `id`/`dispatch_id`/`chalan_id` linking trick: `TileChalan(dispatch_id="", ...)` is constructed first so its `.id` (from `TimestampedModel`'s `default_factory=uuid4`) exists before `TileDispatch` is built with `chalan_id=chalan.id`; then `chalan.dispatch_id = dispatch.id` is back-filled once `dispatch` exists — same "construct first, backfill the reverse reference, insert last" trick used for `TileCustomerOrder`/`PurchaseOrder` linkage in Task 5.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/test_tile_orders_dispatch.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/routes/tile_orders.py backend/tests/unit/test_tile_orders_dispatch.py
git commit -m "feat: add Dispatch preview/commit — creates immutable Chalan, consumes Ready Batches"
```

---

## Task 8: Godown-received action

Marks a `TileDispatch` as having arrived at Buildcon's own warehouse en route to final delivery — updates `current_location` (not `overall_status`, per Task 3's decoupled axes) on the items that dispatch covers. A plain CAS-guarded update (not a transaction) is enough here — unlike Ready/Dispatch, this never mutates a box counter, only a location marker, so the existing single-document `$elemMatch`-style precondition guard (not a multi-step transaction) is the right tool, matching Task 6's transaction-strategy note.

**Files:**
- Modify: `backend/routes/tile_orders.py`
- Test: `backend/tests/unit/test_tile_orders_godown.py`

**Interfaces:**
- Consumes: `derive_current_location` (Task 3).
- Produces: `POST /tile-orders/dispatches/{dispatch_id}/godown-received`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_tile_orders_godown.py
from __future__ import annotations

import asyncio

from models import UserPublic
from routes import tile_orders as router_module


def _user() -> UserPublic:
    return UserPublic(email="wh@forge.app", full_name="Warehouse Rep", role="warehouse", floor_ids=["ground-floor"], active_floor_id="ground-floor")


class _FakeDispatches:
    def __init__(self, dispatch):
        self.doc = dispatch
        self.update_calls: list[dict] = []

    async def find_one(self, query, *_a, **_kw):
        return dict(self.doc) if self.doc else None

    async def update_one(self, query, update, **_kw):
        self.update_calls.append(query)
        if query.get("godown_received_at", "MISSING") != self.doc.get("godown_received_at"):
            class _R: matched_count = 0
            return _R()
        self.doc.update(update["$set"])
        class _R: matched_count = 1
        return _R()


class _FakePOs:
    def __init__(self, po):
        self.po = po

    async def find_one(self, query, *_a, **_kw):
        return dict(self.po) if self.po else None

    async def update_one(self, query, update, **_kw):
        self.po.update(update["$set"])


class _FakeDb:
    def __init__(self, dispatch, po):
        self.dispatches = _FakeDispatches(dispatch)
        self.purchase_orders = _FakePOs(po)


async def _noop_log_event(**_kwargs):
    return None


def _dispatch():
    return {
        "id": "d-1", "dispatch_number": "DSP-2026-0001", "purchase_order_id": "po-1", "customer_id": "cust-1",
        "godown_received_at": None, "ready_batches_consumed": [{"po_item_id": "item-1", "ready_batch_id": "rb-1", "qty": 5}],
    }


def _po():
    return {"id": "po-1", "items": [{"id": "item-1", "qty": 20, "boxes_ready": 7, "boxes_dispatched": 5, "current_location": "Dispatched"}]}


def test_mark_godown_received_updates_location(monkeypatch):
    fake_db = _FakeDb(_dispatch(), _po())
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "log_event", _noop_log_event)

    body = router_module.GodownReceivedBody(note=None)
    result = asyncio.run(router_module.mark_dispatch_godown_received("d-1", body, user=_user()))

    assert result["godown_received_at"] is not None
    assert fake_db.purchase_orders.po["items"][0]["current_location"] == "Godown"


def test_mark_godown_received_rejects_double_call(monkeypatch):
    fake_db = _FakeDb(_dispatch(), _po())
    monkeypatch.setattr(router_module, "db", fake_db)
    monkeypatch.setattr(router_module, "log_event", _noop_log_event)

    body = router_module.GodownReceivedBody(note=None)
    asyncio.run(router_module.mark_dispatch_godown_received("d-1", body, user=_user()))
    import pytest
    with pytest.raises(Exception) as exc:
        asyncio.run(router_module.mark_dispatch_godown_received("d-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_tile_orders_godown.py -v`
Expected: FAIL — `AttributeError: module 'routes.tile_orders' has no attribute 'mark_dispatch_godown_received'`

- [ ] **Step 3: Add the handler**

Append to `backend/routes/tile_orders.py`:

```python
class GodownReceivedBody(BaseModel):
    note: Optional[str] = None


@router.post("/dispatches/{dispatch_id}/godown-received")
async def mark_dispatch_godown_received(
    dispatch_id: str, body: GodownReceivedBody, user: UserPublic = Depends(require_min_role("warehouse")),
):
    dispatch = await db.dispatches.find_one({"id": dispatch_id}, {"_id": 0})
    if not dispatch:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if dispatch.get("godown_received_at"):
        raise HTTPException(status_code=400, detail="Already marked received at Godown")

    now = now_iso()
    cas_result = await db.dispatches.update_one(
        {"id": dispatch_id, "godown_received_at": None},
        {"$set": {
            "godown_received_at": now, "godown_received_by": user.id,
            "godown_received_by_name": user.full_name, "updated_at": now,
        }},
    )
    if cas_result.matched_count == 0:
        raise HTTPException(status_code=409, detail={"error": "concurrent_modification", "message": "This dispatch was just updated — refresh and try again"})

    po = await db.purchase_orders.find_one({"id": dispatch["purchase_order_id"]}, {"_id": 0})
    if po:
        touched_item_ids = {c["po_item_id"] for c in dispatch.get("ready_batches_consumed", [])}
        items = po.get("items", [])
        for item in items:
            if item["id"] in touched_item_ids:
                item["current_location"] = derive_current_location(
                    item["qty"], float(item.get("boxes_ready") or 0), float(item.get("boxes_dispatched") or 0), any_at_godown=True,
                )
        await db.purchase_orders.update_one({"id": po["id"]}, {"$set": {"items": items, "updated_at": now}})

    await log_event(
        event_type="dispatch.godown_received", entity_type="purchase", entity_id=dispatch["purchase_order_id"], actor=user,
        customer_id=dispatch.get("customer_id"), purchase_id=dispatch["purchase_order_id"],
        summary=f"Dispatch {dispatch['dispatch_number']} received at Buildcon Godown" + (f" · {body.note}" if body.note else ""),
        payload={"dispatch_id": dispatch_id},
    )
    return {"dispatch_id": dispatch_id, "godown_received_at": now}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_tile_orders_godown.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full backend suite so far**

Run: `cd backend && python -m pytest tests/unit -q`
Expected: PASS, no regressions in any pre-existing test

- [ ] **Step 6: Commit**

```bash
git add backend/routes/tile_orders.py backend/tests/unit/test_tile_orders_godown.py
git commit -m "feat: add godown-received action for Dispatch"
```

---

## Task 9: Company landing, Supplier dashboard, Supplier analytics

Three read-only endpoints answering "which supplier is delaying orders" and "how is this supplier performing." All query `purchase_orders` directly (already floor/supplier/status/date indexed from Task 4) — no new collection needed since every field these read (`overall_status`, `ready_boxes`, `pending_boxes`, `dispatched_boxes`, `last_supplier_activity_at`) already lives on `PurchaseOrder` from Task 2/6/7's writes.

**Files:**
- Modify: `backend/routes/tile_orders.py`
- Test: `backend/tests/unit/test_tile_orders_supplier_views.py`

**Interfaces:**
- Consumes: `waiting_days`, `ageing_band`, `supplier_silent_days` (Task 3).
- Produces: `GET /tile-orders/suppliers`, `GET /tile-orders/suppliers/{supplier_id}/orders`, `GET /tile-orders/suppliers/{id}/analytics`, `GET /tile-orders/purchase-orders/{po_id}` (the Supplier order-detail read Task 18's page and Task 14's `purchaseOrderDetail` client function both depend on).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_tile_orders_supplier_views.py
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from models import UserPublic
from routes import tile_orders as router_module


def _user() -> UserPublic:
    return UserPublic(email="sales@forge.app", full_name="Sales Rep", role="sales", floor_ids=["ground-floor"], active_floor_id="ground-floor")


def _iso_days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def _po(**overrides) -> dict:
    base = {
        "id": "po-1", "number": "FPO-2026-0001", "supplier_id": "s-1", "supplier_name": "Qutone Rajkot",
        "customer_id": "cust-1", "customer_name": "Nileshbhai Pokiya", "created_at": _iso_days_ago(18),
        "items": [{"id": "item-1", "qty": 20}], "overall_status": "Pending",
        "ready_boxes": 0, "pending_boxes": 20, "dispatched_boxes": 0,
        "completion_percentage": 0, "last_supplier_activity_at": None,
    }
    base.update(overrides)
    return base


class _FakeFind:
    def __init__(self, items): self._items = items
    async def to_list(self, n=None): return list(self._items)


class _FakePOs:
    def __init__(self, docs): self.docs = docs
    def find(self, query=None, projection=None, session=None): return _FakeFind(self.docs)
    async def find_one(self, query=None, projection=None, session=None):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in (query or {}).items() if not k.startswith("$")):
                return dict(doc)
        return None


class _FakeDb:
    def __init__(self, docs): self.purchase_orders = _FakePOs(docs)


def test_list_suppliers_sorts_by_most_stalled_first(monkeypatch):
    fake_db = _FakeDb([
        _po(id="po-1", supplier_id="s-1", supplier_name="Qutone Rajkot", created_at=_iso_days_ago(3)),
        _po(id="po-2", supplier_id="s-2", supplier_name="Dimore Rajkot", created_at=_iso_days_ago(18)),
    ])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.list_suppliers(user=_user()))

    assert result["suppliers"][0]["supplier_name"] == "Dimore Rajkot"
    assert result["suppliers"][0]["max_supplier_silent_days"] == 18
    assert result["suppliers"][1]["supplier_name"] == "Qutone Rajkot"


def test_supplier_orders_kpi_bar_and_sort(monkeypatch):
    fake_db = _FakeDb([
        _po(id="po-1", created_at=_iso_days_ago(3), overall_status="Pending"),
        _po(id="po-2", created_at=_iso_days_ago(18), overall_status="Ready", ready_boxes=10, pending_boxes=10),
        _po(id="po-3", created_at=_iso_days_ago(9), overall_status="Dispatched", dispatched_boxes=20, pending_boxes=0),
    ])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.supplier_orders("s-1", user=_user()))

    assert result["kpi"]["orders"] == 3
    assert result["kpi"]["pending"] == 1
    assert result["kpi"]["ready"] == 1
    assert result["kpi"]["completed"] == 1
    assert result["kpi"]["oldest_pending_days"] == 3
    assert [row["po_id"] for row in result["orders"]] == ["po-2", "po-3", "po-1"]  # oldest waiting first


def test_purchase_order_detail_returns_item_box_breakdown(monkeypatch):
    fake_db = _FakeDb([_po(items=[{
        "id": "item-1", "name": "Glossy Ivory 600x600", "series": "Metropole", "finish": None, "size": "600X600",
        "sku": "SKU-1", "qty": 20, "boxes_ready": 4, "boxes_dispatched": 8, "boxes_pending": 8,
        "current_location": "Dispatched", "overall_status": "Partially Dispatched",
    }])])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.purchase_order_detail("po-1", user=_user()))

    assert result["id"] == "po-1"
    assert result["items"][0]["boxes_ready"] == 4
    assert result["items"][0]["boxes_dispatched"] == 8


def test_supplier_analytics_averages(monkeypatch):
    fake_db = _FakeDb([
        _po(id="po-1", overall_status="Dispatched", dispatched_boxes=20, pending_boxes=0,
            latest_ready_date=_iso_days_ago(5), latest_dispatch_date=_iso_days_ago(1), created_at=_iso_days_ago(10)),
    ])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.supplier_analytics("s-1", user=_user()))

    assert result["orders"] == 1
    assert result["completion_percentage_avg"] == 100.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/unit/test_tile_orders_supplier_views.py -v`
Expected: FAIL — `AttributeError: module 'routes.tile_orders' has no attribute 'list_suppliers'`

- [ ] **Step 3: Update imports and add the three handlers**

Update the `from services.tile_order_status import (...)` line near the top of `backend/routes/tile_orders.py` to also pull in the ageing helpers:

```python
from services.tile_order_status import (
    ageing_band, completion_percentage, derive_current_location, derive_item_status,
    rollup_status, supplier_silent_days, waiting_days,
)
```

Append to `backend/routes/tile_orders.py`:

```python
_STATUS_TO_KPI_KEY = {
    "Pending": "pending", "Ready": "ready", "Partially Dispatched": "partially_dispatched",
    "Dispatched": "completed", "Delivered": "completed",
}


@router.get("/suppliers")
async def list_suppliers(user: UserPublic = Depends(require_min_role("sales"))):
    pos = await db.purchase_orders.find(floor_query(user, {"customer_order_id": {"$ne": None}}), {"_id": 0}).to_list(5000)
    grouped: dict[str, dict] = {}
    for po in pos:
        key = po.get("supplier_id") or "unassigned"
        bucket = grouped.setdefault(key, {
            "supplier_id": po.get("supplier_id"), "supplier_name": po.get("supplier_name") or "Unassigned",
            "active_orders": 0, "max_supplier_silent_days": 0,
        })
        if po.get("overall_status") != "Delivered":
            bucket["active_orders"] += 1
        silent = supplier_silent_days(po.get("last_supplier_activity_at"), po["created_at"])
        bucket["max_supplier_silent_days"] = max(bucket["max_supplier_silent_days"], silent)
    suppliers = sorted(grouped.values(), key=lambda g: -g["max_supplier_silent_days"])
    return {"suppliers": suppliers}


@router.get("/purchase-orders/{po_id}")
async def purchase_order_detail(po_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return {
        "id": po["id"], "number": po.get("number"), "customer_name": po.get("customer_name"),
        "supplier_name": po.get("supplier_name"), "overall_status": po.get("overall_status"),
        "items": [{
            "id": item["id"], "name": item.get("name"), "series": item.get("series"), "finish": item.get("finish"),
            "size": item.get("size"), "sku": item.get("sku"), "qty": item.get("qty"),
            "boxes_ready": item.get("boxes_ready"), "boxes_dispatched": item.get("boxes_dispatched"),
            "boxes_pending": item.get("boxes_pending"), "current_location": item.get("current_location"),
            "overall_status": item.get("overall_status"),
        } for item in po.get("items", [])],
    }


@router.get("/suppliers/{supplier_id}/orders")
async def supplier_orders(
    supplier_id: str, page: int = 1, page_size: int = 20, sort: str = "waiting_desc",
    status: Optional[str] = None, search: Optional[str] = None,
    user: UserPublic = Depends(require_min_role("sales")),
):
    filters: dict = {"supplier_id": supplier_id}
    if status:
        filters["overall_status"] = status
    if search:
        filters["$or"] = [
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"number": {"$regex": search, "$options": "i"}},
        ]
    all_pos = await db.purchase_orders.find(floor_query(user, filters), {"_id": 0}).to_list(5000)

    kpi = {"orders": len(all_pos), "pending": 0, "ready": 0, "partially_dispatched": 0, "completed": 0,
           "boxes_pending": 0.0, "boxes_ready": 0.0, "boxes_dispatched": 0.0, "oldest_pending_days": 0}
    for po in all_pos:
        kpi[_STATUS_TO_KPI_KEY.get(po.get("overall_status"), "pending")] += 1
        kpi["boxes_pending"] += float(po.get("pending_boxes") or 0)
        kpi["boxes_ready"] += float(po.get("ready_boxes") or 0)
        kpi["boxes_dispatched"] += float(po.get("dispatched_boxes") or 0)
        if po.get("overall_status") == "Pending":
            kpi["oldest_pending_days"] = max(kpi["oldest_pending_days"], waiting_days(po["created_at"]))

    rows = []
    for po in all_pos:
        days = waiting_days(po["created_at"])
        rows.append({
            "po_id": po["id"], "po_number": po.get("number"), "customer_id": po.get("customer_id"),
            "customer_name": po.get("customer_name"), "order_date": po.get("created_at"),
            "waiting_days": days, "ageing_band": ageing_band(days),
            "total_products": len(po.get("items", [])), "total_boxes": sum(float(i.get("qty") or 0) for i in po.get("items", [])),
            "overall_status": po.get("overall_status"), "completion_percentage": po.get("completion_percentage"),
        })
    rows.sort(key=lambda r: r["waiting_days"], reverse=(sort != "waiting_asc"))
    start = (page - 1) * page_size
    return {"kpi": kpi, "orders": rows[start:start + page_size], "page": page, "page_size": page_size, "total": len(rows)}


@router.get("/suppliers/{supplier_id}/analytics")
async def supplier_analytics(supplier_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    pos = await db.purchase_orders.find(floor_query(user, {"supplier_id": supplier_id}), {"_id": 0}).to_list(5000)
    if not pos:
        return {"orders": 0, "waiting_avg_days": 0, "ready_time_avg_days": 0, "dispatch_time_avg_days": 0, "fulfilment_time_avg_days": 0, "oldest_pending_days": 0, "completion_percentage_avg": 0}

    ready_times, dispatch_times, fulfilment_times = [], [], []
    oldest_pending = 0
    for po in pos:
        created = po["created_at"]
        if po.get("overall_status") == "Pending":
            oldest_pending = max(oldest_pending, waiting_days(created))
        if po.get("latest_ready_date"):
            ready_times.append(waiting_days(created) - waiting_days(po["latest_ready_date"]))
        if po.get("latest_ready_date") and po.get("latest_dispatch_date"):
            dispatch_times.append(waiting_days(po["latest_ready_date"]) - waiting_days(po["latest_dispatch_date"]))
        if po.get("overall_status") in ("Dispatched", "Delivered"):
            fulfilment_times.append(waiting_days(created) - waiting_days(po.get("latest_dispatch_date") or created))

    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 1) if values else 0.0

    return {
        "orders": len(pos),
        "waiting_avg_days": _avg([waiting_days(po["created_at"]) for po in pos]),
        "ready_time_avg_days": _avg(ready_times),
        "dispatch_time_avg_days": _avg(dispatch_times),
        "fulfilment_time_avg_days": _avg(fulfilment_times),
        "oldest_pending_days": oldest_pending,
        "completion_percentage_avg": _avg([float(po.get("completion_percentage") or 0) for po in pos]),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/test_tile_orders_supplier_views.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/routes/tile_orders.py backend/tests/unit/test_tile_orders_supplier_views.py
git commit -m "feat: add Company landing, Supplier dashboard, Supplier analytics endpoints"
```

---

## Task 10: Customer tab — list, detail, timeline

**Files:**
- Modify: `backend/routes/tile_orders.py`
- Test: `backend/tests/unit/test_tile_orders_customer_views.py`

**Interfaces:**
- Consumes: `waiting_days`, `ageing_band` (Task 3).
- Produces: `GET /tile-orders/customer-orders`, `GET /tile-orders/customer-orders/{id}`, `GET /tile-orders/customer-orders/{id}/timeline`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_tile_orders_customer_views.py
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from models import UserPublic
from routes import tile_orders as router_module


def _user() -> UserPublic:
    return UserPublic(email="sales@forge.app", full_name="Sales Rep", role="sales", floor_ids=["ground-floor"], active_floor_id="ground-floor")


def _iso_days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


class _FakeFind:
    def __init__(self, items): self._items = items
    async def to_list(self, n=None): return list(self._items)


class _FakeCollection:
    def __init__(self, docs): self.docs = docs
    def find(self, query=None, projection=None, session=None): return _FakeFind(self.docs)
    async def find_one(self, query=None, projection=None, session=None):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in (query or {}).items() if not k.startswith("$")):
                return dict(doc)
        return None


class _FakeDb:
    def __init__(self, customer_orders, purchase_orders, activity_events=None):
        self.customer_orders = _FakeCollection(customer_orders)
        self.purchase_orders = _FakeCollection(purchase_orders)
        self.activity_events = _FakeCollection(activity_events or [])


def test_list_customer_orders_sorted_oldest_first(monkeypatch):
    fake_db = _FakeDb([
        {"id": "co-1", "number": "TORD-2026-0001", "customer_name": "A", "created_at": _iso_days_ago(2), "is_deleted": False, "brands": [], "overall_status": "Pending"},
        {"id": "co-2", "number": "TORD-2026-0002", "customer_name": "B", "created_at": _iso_days_ago(16), "is_deleted": False, "brands": [], "overall_status": "Ready"},
    ], [])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.list_customer_orders(user=_user()))

    assert [o["number"] for o in result["orders"]] == ["TORD-2026-0002", "TORD-2026-0001"]
    assert result["orders"][0]["ageing_band"] == "red"


def test_customer_order_detail_groups_by_supplier(monkeypatch):
    co = {"id": "co-1", "number": "TORD-2026-0001", "customer_name": "Nileshbhai", "created_at": _iso_days_ago(5), "brands": [{"purchase_order_id": "po-1"}, {"purchase_order_id": "po-2"}], "total_products": 2, "total_boxes": 30, "completion_percentage": 0, "overall_status": "Pending"}
    pos = [
        {"id": "po-1", "supplier_name": "Qutone Rajkot", "overall_status": "Pending", "items": [{"id": "i-1", "name": "Tile A", "qty": 20, "boxes_ready": 0, "boxes_dispatched": 0, "boxes_pending": 20, "current_location": "Pending", "overall_status": "Pending"}]},
        {"id": "po-2", "supplier_name": "Dimore Rajkot", "overall_status": "Pending", "items": [{"id": "i-2", "name": "Tile B", "qty": 10, "boxes_ready": 0, "boxes_dispatched": 0, "boxes_pending": 10, "current_location": "Pending", "overall_status": "Pending"}]},
    ]
    fake_db = _FakeDb([co], pos)
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.customer_order_detail("co-1", user=_user()))

    assert result["summary"]["brand_count"] == 2
    supplier_names = {s["supplier_name"] for s in result["suppliers"]}
    assert supplier_names == {"Qutone Rajkot", "Dimore Rajkot"}


def test_timeline_merges_events_across_pos(monkeypatch):
    co = {"id": "co-1"}
    pos = [{"id": "po-1"}, {"id": "po-2"}]
    events = [
        {"id": "e-1", "event_type": "customer_order.created", "entity_type": "tile_customer_order", "entity_id": "co-1", "created_at": "2026-07-27T10:00:00+00:00"},
        {"id": "e-2", "event_type": "dispatch.created", "entity_type": "purchase", "purchase_id": "po-1", "created_at": "2026-07-28T10:00:00+00:00"},
        {"id": "e-3", "event_type": "dispatch.created", "entity_type": "purchase", "purchase_id": "po-2", "created_at": "2026-07-29T10:00:00+00:00"},
    ]
    fake_db = _FakeDb([co], pos, events)
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.customer_order_timeline("co-1", user=_user()))

    assert len(result["events"]) == 3
    assert result["events"][0]["id"] == "e-3"  # newest first
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/unit/test_tile_orders_customer_views.py -v`
Expected: FAIL — `AttributeError: module 'routes.tile_orders' has no attribute 'list_customer_orders'`

- [ ] **Step 3: Add the three handlers**

Append to `backend/routes/tile_orders.py`:

```python
@router.get("/customer-orders")
async def list_customer_orders(
    page: int = 1, page_size: int = 20, sort: str = "waiting_desc",
    status: Optional[str] = None, search: Optional[str] = None,
    user: UserPublic = Depends(require_min_role("sales")),
):
    filters: dict = {"is_deleted": False}
    if status:
        filters["overall_status"] = status
    if search:
        filters["$or"] = [
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"customer_phone": {"$regex": search, "$options": "i"}},
            {"number": {"$regex": search, "$options": "i"}},
        ]
    docs = await db.customer_orders.find(floor_query(user, filters), {"_id": 0}).to_list(5000)
    rows = []
    for co in docs:
        days = waiting_days(co["created_at"])
        rows.append({
            "id": co["id"], "number": co.get("number"), "customer_name": co.get("customer_name"),
            "customer_phone": co.get("customer_phone"), "order_date": co.get("created_at"),
            "waiting_days": days, "ageing_band": ageing_band(days), "brands": co.get("brands", []),
            "total_products": co.get("total_products"), "total_boxes": co.get("total_boxes"),
            "total_value": co.get("total_value"), "overall_status": co.get("overall_status"),
            "completion_percentage": co.get("completion_percentage"),
        })
    rows.sort(key=lambda r: r["waiting_days"], reverse=(sort != "waiting_asc"))
    start = (page - 1) * page_size
    return {"orders": rows[start:start + page_size], "page": page, "page_size": page_size, "total": len(rows)}


@router.get("/customer-orders/{co_id}")
async def customer_order_detail(co_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    co = await db.customer_orders.find_one(floor_query(user, {"id": co_id}), {"_id": 0})
    if not co:
        raise HTTPException(status_code=404, detail="Customer order not found")
    pos = await db.purchase_orders.find({"customer_order_id": co_id}, {"_id": 0}).to_list(50)
    suppliers = [{
        "purchase_order_id": po["id"], "supplier_name": po.get("supplier_name") or "Unassigned",
        "overall_status": po.get("overall_status"),
        "items": [{
            "po_item_id": item["id"], "tile_name": item.get("name"), "series": item.get("series"),
            "finish": item.get("finish"), "size": item.get("size"),
            "boxes_ordered": item.get("qty"), "boxes_ready": item.get("boxes_ready"),
            "boxes_dispatched": item.get("boxes_dispatched"), "boxes_pending": item.get("boxes_pending"),
            "current_location": item.get("current_location"), "overall_status": item.get("overall_status"),
        } for item in po.get("items", [])],
    } for po in pos]
    days = waiting_days(co["created_at"])
    return {
        "summary": {
            "id": co["id"], "number": co.get("number"), "customer_name": co.get("customer_name"),
            "order_date": co.get("created_at"), "brand_count": len(co.get("brands", [])),
            "total_products": co.get("total_products"), "total_boxes": co.get("total_boxes"),
            "completion_percentage": co.get("completion_percentage"), "waiting_days": days,
            "ageing_band": ageing_band(days), "overall_status": co.get("overall_status"),
        },
        "suppliers": suppliers,
    }


@router.get("/customer-orders/{co_id}/timeline")
async def customer_order_timeline(co_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    co = await db.customer_orders.find_one(floor_query(user, {"id": co_id}), {"_id": 0, "id": 1})
    if not co:
        raise HTTPException(status_code=404, detail="Customer order not found")
    pos = await db.purchase_orders.find({"customer_order_id": co_id}, {"_id": 0, "id": 1}).to_list(50)
    po_ids = [po["id"] for po in pos]
    events = await db.activity_events.find(
        {"$or": [{"entity_type": "tile_customer_order", "entity_id": co_id}, {"purchase_id": {"$in": po_ids}}]}, {"_id": 0},
    ).to_list(500)
    events.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return {"events": events}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/test_tile_orders_customer_views.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/routes/tile_orders.py backend/tests/unit/test_tile_orders_customer_views.py
git commit -m "feat: add Customer tab list/detail/timeline endpoints"
```

---

## Task 11: Dispatch List register, item history, dashboard summary

**Files:**
- Modify: `backend/routes/tile_orders.py`
- Test: `backend/tests/unit/test_tile_orders_dispatch_list.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `GET /tile-orders/dispatches` (filterable/paginated register), `GET /tile-orders/items/{item_id}/history`, `GET /tile-orders/dashboard`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_tile_orders_dispatch_list.py
from __future__ import annotations

import asyncio

from models import UserPublic
from routes import tile_orders as router_module


def _user() -> UserPublic:
    return UserPublic(email="sales@forge.app", full_name="Sales Rep", role="sales", floor_ids=["ground-floor"], active_floor_id="ground-floor")


class _FakeFind:
    def __init__(self, items): self._items = items
    async def to_list(self, n=None): return list(self._items)


class _FakeCollection:
    def __init__(self, docs): self.docs = docs
    def find(self, query=None, projection=None, session=None): return _FakeFind(self.docs)
    async def find_one(self, query=None, projection=None, session=None):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in (query or {}).items() if not k.startswith("$")):
                return dict(doc)
        return None


class _FakeDb:
    def __init__(self, dispatches=None, chalans=None, ready_batches=None, purchase_orders=None):
        self.dispatches = _FakeCollection(dispatches or [])
        self.chalans = _FakeCollection(chalans or [])
        self.ready_batches = _FakeCollection(ready_batches or [])
        self.purchase_orders = _FakeCollection(purchase_orders or [])


def _dispatch(**overrides):
    base = {
        "id": "d-1", "dispatch_number": "DSP-2026-0001", "chalan_id": "ch-1", "customer_name": "Nileshbhai Pokiya",
        "supplier_name": "Qutone Rajkot", "supplier_id": "s-1", "customer_id": "cust-1", "dispatch_date": "2026-07-29",
        "destination_type": "Customer", "destination_name": "Nileshbhai Pokiya", "godown_received_at": None,
        "delivered_at": None, "is_deleted": False,
    }
    base.update(overrides)
    return base


def _chalan(**overrides):
    base = {
        "id": "ch-1", "number": "CH-0001", "dispatch_id": "d-1",
        "items": [{"po_item_id": "item-1", "tile_name": "Glossy Ivory 600x600", "size": "600X600", "boxes": 5, "quantity": 5}],
    }
    base.update(overrides)
    return base


def test_dispatch_list_flattens_chalan_lines(monkeypatch):
    fake_db = _FakeDb(dispatches=[_dispatch()], chalans=[_chalan()])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.list_dispatches(user=_user()))

    assert result["total"] == 1
    row = result["rows"][0]
    assert row["dispatch_number"] == "DSP-2026-0001"
    assert row["chalan_number"] == "CH-0001"
    assert row["tile_name"] == "Glossy Ivory 600x600"
    assert row["boxes"] == 5
    assert row["status"] == "Dispatched"


def test_dispatch_list_filters_by_supplier(monkeypatch):
    fake_db = _FakeDb(
        dispatches=[_dispatch(id="d-1", supplier_id="s-1"), _dispatch(id="d-2", supplier_id="s-2", chalan_id="ch-2")],
        chalans=[_chalan(id="ch-1", dispatch_id="d-1"), _chalan(id="ch-2", dispatch_id="d-2")],
    )
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.list_dispatches(supplier="s-1", user=_user()))

    assert result["total"] == 1
    assert result["rows"][0]["supplier_name"] == "Qutone Rajkot"


def test_item_history_merges_ready_and_dispatch_events(monkeypatch):
    fake_db = _FakeDb(
        ready_batches=[{"id": "rb-1", "po_item_id": "item-1", "batch_number": "RB-2026-0001", "qty": 8, "created_at": "2026-07-27T10:00:00+00:00"}],
        dispatches=[_dispatch(ready_batches_consumed=[{"po_item_id": "item-1", "ready_batch_id": "rb-1", "qty": 5}], created_at="2026-07-28T10:00:00+00:00")],
    )
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.item_history("item-1", user=_user()))

    kinds = [e["kind"] for e in result["events"]]
    assert kinds == ["dispatch", "ready_batch"]  # newest first
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/unit/test_tile_orders_dispatch_list.py -v`
Expected: FAIL — `AttributeError: module 'routes.tile_orders' has no attribute 'list_dispatches'`

- [ ] **Step 3: Add `Query` import and the three handlers**

Update the `from fastapi import ...` line near the top of `backend/routes/tile_orders.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
```

Append to `backend/routes/tile_orders.py`:

```python
def _dispatch_status(dispatch: dict) -> str:
    if dispatch.get("delivered_at"):
        return "Delivered"
    if dispatch.get("godown_received_at"):
        return "At Godown"
    return "Dispatched"


@router.get("/dispatches")
async def list_dispatches(
    supplier: Optional[str] = None, customer: Optional[str] = None, brand: Optional[str] = None,
    status: Optional[str] = None, from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
    destination: Optional[str] = None, search: Optional[str] = None,
    page: int = 1, page_size: int = 50, sort: str = "date_desc",
    user: UserPublic = Depends(require_min_role("sales")),
):
    filters: dict = {"is_deleted": False}
    if supplier:
        filters["supplier_id"] = supplier
    if customer:
        filters["customer_id"] = customer
    if destination:
        filters["destination_type"] = destination
    if from_ or to:
        date_filter: dict = {}
        if from_:
            date_filter["$gte"] = from_
        if to:
            date_filter["$lte"] = to
        filters["dispatch_date"] = date_filter
    if search:
        filters["$or"] = [
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"supplier_name": {"$regex": search, "$options": "i"}},
            {"dispatch_number": {"$regex": search, "$options": "i"}},
        ]
    dispatches = await db.dispatches.find(floor_query(user, filters), {"_id": 0}).to_list(5000)
    chalan_ids = [d["chalan_id"] for d in dispatches]
    chalans = await db.chalans.find({"id": {"$in": chalan_ids}}, {"_id": 0}).to_list(len(chalan_ids) + 5)
    chalan_by_id = {c["id"]: c for c in chalans}

    rows = []
    for dispatch in dispatches:
        dispatch_status = _dispatch_status(dispatch)
        if status and status != dispatch_status:
            continue
        chalan = chalan_by_id.get(dispatch["chalan_id"], {})
        for line in chalan.get("items", []):
            if brand and dispatch.get("brand_id") != brand:
                continue
            rows.append({
                "dispatch_number": dispatch.get("dispatch_number"), "chalan_number": chalan.get("number"),
                "customer_name": dispatch.get("customer_name"), "supplier_name": dispatch.get("supplier_name"),
                "tile_name": line.get("tile_name"), "tile_size": line.get("size"), "boxes": line.get("boxes"),
                "dispatch_date": dispatch.get("dispatch_date"), "destination": dispatch.get("destination_name"),
                "status": dispatch_status,
            })
    rows.sort(key=lambda r: r["dispatch_date"] or "", reverse=(sort != "date_asc"))
    start = (page - 1) * page_size
    return {"rows": rows[start:start + page_size], "page": page, "page_size": page_size, "total": len(rows)}


@router.get("/items/{item_id}/history")
async def item_history(item_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    ready_batches = await db.ready_batches.find({"po_item_id": item_id}, {"_id": 0}).to_list(200)
    dispatches = await db.dispatches.find({"ready_batches_consumed.po_item_id": item_id}, {"_id": 0}).to_list(200)
    events = [{"kind": "ready_batch", "at": rb.get("created_at"), "detail": rb} for rb in ready_batches]
    events += [{"kind": "dispatch", "at": d.get("created_at"), "detail": d} for d in dispatches]
    events.sort(key=lambda e: e["at"] or "", reverse=True)
    return {"item_id": item_id, "events": events}


@router.get("/dashboard")
async def tile_orders_dashboard(user: UserPublic = Depends(require_min_role("sales"))):
    pos = await db.purchase_orders.find(floor_query(user, {"customer_order_id": {"$ne": None}}), {"_id": 0}).to_list(5000)
    today = now_iso()[:10]
    dispatched_today = await db.dispatches.find(floor_query(user, {"dispatch_date": today, "is_deleted": False}), {"_id": 0}).to_list(2000)
    delivered_today = [d for d in dispatched_today if (d.get("delivered_at") or "")[:10] == today]
    customer_orders = await db.customer_orders.find(floor_query(user, {"is_deleted": False}), {"_id": 0}).to_list(5000)

    pending = sum(1 for po in pos if po.get("overall_status") == "Pending")
    ready = sum(1 for po in pos if po.get("overall_status") == "Ready")
    waiting_over_15 = sum(1 for co in customer_orders if waiting_days(co["created_at"]) > 15)
    boxes_ordered = sum(float(i.get("qty") or 0) for po in pos for i in po.get("items", []))
    boxes_pending = sum(float(po.get("pending_boxes") or 0) for po in pos)
    revenue = sum(float(co.get("total_value") or 0) for co in customer_orders)

    return {
        "customer_orders": len(customer_orders), "supplier_orders": len(pos),
        "dispatched_today": len(dispatched_today), "delivered_today": len(delivered_today),
        "pending": pending, "ready": ready, "waiting_over_15_days": waiting_over_15,
        "boxes_ordered": boxes_ordered, "boxes_pending": boxes_pending, "revenue": round(revenue, 2),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/test_tile_orders_dispatch_list.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && python -m pytest tests/unit -q`
Expected: PASS, no regressions

- [ ] **Step 6: Commit**

```bash
git add backend/routes/tile_orders.py backend/tests/unit/test_tile_orders_dispatch_list.py
git commit -m "feat: add Dispatch List register, item history, dashboard summary endpoints"
```

---

## Task 12: Tile Chalan PDF

Adds `build_tile_chalan_pdf()`/`tile_chalan_pdf_filename()` **alongside** (not replacing) the existing `build_chalan_pdf()`/`chalan_pdf_filename()` in `backend/pdf_chalan.py` — the old functions keep serving the old embedded-chalan route unchanged (rollback safety, per the design doc's migration section). Only the primitives already confirmed present in this codebase are used (`_logo_flowable`, `_escape`, `LOGO_PATH`, reportlab platypus/A4) — no invented helper signatures.

**Files:**
- Modify: `backend/pdf_chalan.py`
- Modify: `backend/routes/tile_orders.py` (PDF route)
- Test: `backend/tests/unit/test_pdf_tile_chalan.py`

**Interfaces:**
- Consumes: `TileChalan` shape (Task 1).
- Produces: `tile_chalan_pdf_filename(chalan: dict) -> str`, `build_tile_chalan_pdf(chalan: dict, branding: dict | None = None) -> bytes`; `GET /tile-orders/chalans/{chalan_id}/pdf`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_pdf_tile_chalan.py
"""Field-presence check, not pixel-perfect layout — extracts PDF text via
reportlab's own byte stream markers is fragile, so this asserts the
function runs and produces non-trivial PDF bytes with the right filename
convention, matching the existing test_pdf_chalan.py's level of rigor."""
from __future__ import annotations

from pdf_chalan import build_tile_chalan_pdf, tile_chalan_pdf_filename


def _chalan() -> dict:
    return {
        "number": "CH-000123", "dispatch_id": "d-1", "supplier_name": "Qutone Rajkot",
        "supplier_contact": "9909900001", "supplier_address": "Morbi, Gujarat",
        "customer_name": "Nileshbhai Pokiya", "customer_phone": "9909900000",
        "delivery_address": "123 Ring Road", "delivery_city": "Rajkot",
        "reference_number": "TORD-2026-0001",
        "items": [{"po_item_id": "item-1", "tile_name": "Glossy Ivory 600x600", "series": "Metropole", "finish": None, "size": "600X600", "sku": "SKU-1", "boxes": 5, "pieces_per_box": "4", "quantity": 5}],
        "receiver_name": "Nileshbhai Pokiya", "sender_name": "Qutone Rep",
        "vehicle_number": None, "driver_name": None,
        "generated_at": "2026-07-29T14:23:00+00:00", "generated_by_name": "Aarav Kapoor", "system_version": "BuildCon ERP v2",
    }


def test_filename_matches_convention():
    filename = tile_chalan_pdf_filename(_chalan(), "Nileshbhai Pokiya")
    assert filename.startswith("CH-000123 Nileshbhai Pokiya ")
    assert filename.endswith(".pdf")


def test_build_tile_chalan_pdf_produces_bytes():
    pdf_bytes = build_tile_chalan_pdf(_chalan())
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_pdf_tile_chalan.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_tile_chalan_pdf' from 'pdf_chalan'`

- [ ] **Step 3: Add the functions to `pdf_chalan.py`**

Append to `backend/pdf_chalan.py` (below the existing `build_chalan_pdf`):

```python
def tile_chalan_pdf_filename(chalan: dict, customer_name: str) -> str:
    stamp = datetime.now(timezone.utc)
    return f"{chalan['number']} {customer_name} {stamp.strftime('%d-%m-%Y')}.pdf"


def build_tile_chalan_pdf(chalan: dict, branding: dict | None = None) -> bytes:
    """Renders the immutable TileChalan document — only ever called with a
    fully-formed, never-edited chalan dict (see models_tile_orders.TileChalan)."""
    branding = branding or {}
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=14 * mm, bottomMargin=14 * mm, leftMargin=16 * mm, rightMargin=16 * mm)
    styles = getSampleStyleSheet()
    body = ParagraphStyle("tcBody", parent=styles["Normal"], fontSize=9, leading=13)
    heading = ParagraphStyle("tcHeading", parent=styles["Normal"], fontSize=11, leading=14, fontName="Helvetica-Bold")
    small = ParagraphStyle("tcSmall", parent=styles["Normal"], fontSize=7.5, leading=10, textColor=colors.grey)

    flow: list = [_logo_flowable(45), Spacer(1, 6 * mm)]
    flow.append(Paragraph(f"<b>Chalan No:</b> {_escape(chalan['number'])} &nbsp;&nbsp; <b>Date:</b> {chalan['generated_at'][:10]} &nbsp;&nbsp; <b>Time:</b> {chalan['generated_at'][11:16]}", body))
    flow.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceBefore=4, spaceAfter=6))

    flow.append(Paragraph("<b>Customer</b>", heading))
    flow.append(Paragraph(
        f"{_escape(chalan.get('customer_name', ''))} &nbsp;·&nbsp; {_escape(chalan.get('customer_phone') or '')}<br/>"
        f"{_escape(chalan.get('delivery_address', ''))}, {_escape(chalan.get('delivery_city', ''))}<br/>"
        f"Reference: {_escape(chalan.get('reference_number') or '—')}", body,
    ))
    flow.append(Spacer(1, 4 * mm))

    flow.append(Paragraph("<b>Supplier</b>", heading))
    flow.append(Paragraph(
        f"{_escape(chalan.get('supplier_name', ''))} &nbsp;·&nbsp; {_escape(chalan.get('supplier_contact') or '—')}<br/>"
        f"{_escape(chalan.get('supplier_address') or '—')}", body,
    ))
    flow.append(Spacer(1, 5 * mm))

    header_row = ["Sr", "Tile Name", "Series", "Finish", "Size", "SKU", "Boxes", "Pcs/Box", "Qty"]
    table_data = [header_row]
    for i, item in enumerate(chalan.get("items", []), start=1):
        table_data.append([
            str(i), _escape(item.get("tile_name", "")), _escape(item.get("series") or "—"),
            _escape(item.get("finish") or "—"), _escape(item.get("size") or "—"), _escape(item.get("sku") or "—"),
            f"{item.get('boxes', 0):g}", _escape(item.get("pieces_per_box") or "—"), f"{item.get('quantity', 0):g}",
        ])
    product_table = Table(table_data, colWidths=[8 * mm, 40 * mm, 22 * mm, 18 * mm, 20 * mm, 20 * mm, 14 * mm, 16 * mm, 14 * mm])
    product_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    flow.append(product_table)
    flow.append(Spacer(1, 8 * mm))

    signature_table = Table([
        ["Receiver", "Sender"],
        [_escape(chalan.get("receiver_name") or ""), _escape(chalan.get("sender_name") or "")],
        ["Signature: ____________________", "Signature: ____________________"],
    ], colWidths=[85 * mm, 85 * mm])
    signature_table.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
    flow.append(signature_table)
    flow.append(Spacer(1, 5 * mm))

    vehicle = chalan.get("vehicle_number") or "—"
    driver = chalan.get("driver_name") or "—"
    flow.append(Paragraph(f"<b>Transport:</b> Vehicle {_escape(vehicle)} &nbsp;·&nbsp; Driver {_escape(driver)}", small))
    flow.append(Spacer(1, 3 * mm))
    flow.append(Paragraph(
        f"Generated on {chalan['generated_at'][:16].replace('T', ' ')} by {_escape(chalan.get('generated_by_name', ''))} "
        f"&nbsp;·&nbsp; {_escape(chalan.get('system_version', 'BuildCon ERP'))}", small,
    ))
    flow.append(Paragraph(
        branding.get("footer_company_name", "Buildcon House") + " · " + branding.get("footer_phone", DEFAULT_MOBILE), small,
    ))

    doc.build(flow)
    return buffer.getvalue()
```

Add the missing `datetime`/`timezone` import at the top of `backend/pdf_chalan.py` if not already present (the existing file already imports from `reportlab`/`pdf_generator`/`pdf_tiles` per Task research — only add what's missing):

```python
from datetime import datetime, timezone
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_pdf_tile_chalan.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Add the PDF route**

Append to `backend/routes/tile_orders.py`:

```python
from fastapi.responses import StreamingResponse

from pdf_chalan import build_tile_chalan_pdf, tile_chalan_pdf_filename


@router.get("/chalans/{chalan_id}/pdf")
async def chalan_pdf(chalan_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    chalan = await db.chalans.find_one(floor_query(user, {"id": chalan_id}), {"_id": 0})
    if not chalan:
        raise HTTPException(status_code=404, detail="Chalan not found")
    company = await db.settings.find_one({"key": "company"}, {"_id": 0}) or {}
    pdf_settings = await db.settings.find_one({"key": "pdf"}, {"_id": 0}) or {}
    branding = {
        "footer_company_name": pdf_settings.get("footer_company_name") or company.get("name") or "Buildcon House",
        "footer_phone": pdf_settings.get("footer_phone") or company.get("phone") or "",
    }
    pdf_bytes = build_tile_chalan_pdf(chalan, branding)
    filename = tile_chalan_pdf_filename(chalan, chalan.get("customer_name", "Customer"))
    return StreamingResponse(
        iter([pdf_bytes]), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
```

- [ ] **Step 6: Commit**

```bash
git add backend/pdf_chalan.py backend/routes/tile_orders.py backend/tests/unit/test_pdf_tile_chalan.py
git commit -m "feat: add Tile Chalan PDF generation and download route"
```

---

## Task 13: One-time backfill migration script

Per the design doc's Migration section ("restructure freely" — the feature is ~1 week old with little real data): a standalone script, not a zero-downtime dual-write migration. For every pre-existing tiles `PurchaseOrder` missing `customer_order_id`, this creates its `TileCustomerOrder` (grouped by `quotation_id`) and converts each embedded old `Chalan` into a new `TileDispatch` + immutable `TileChalan` + one synthetic fully-consumed `TileReadyBatch`.

**Old-stage → new-location mapping** (matches the design doc's Background section, which already established these are the same underlying milestone under different names): old `Chalan.stage == "released"` → new `current_location = "Dispatched"` (old "released" meant material left the factory — that's what "Dispatch" means in the new model); old `"at_godown"` → new `"Godown"`; old `"dispatched"` (old system's *final*, reached-the-customer state) → new `"Delivered"`. Every old chalan, regardless of stage, already means the material left the supplier, so its full quantity always counts toward the new `boxes_dispatched` counter — only quantity that was **never** chalan'd under the old system becomes new `boxes_pending`. `boxes_ready` is always `0` for backfilled items, since the old system had no separate Ready stage.

**Files:**
- Create: `backend/scripts/backfill_tile_customer_orders.py`
- Test: `backend/tests/unit/test_backfill_tile_customer_orders.py`

**Interfaces:**
- Consumes: `TileCustomerOrder`, `TileCustomerOrderBrand`, `TileDispatch`, `TileChalan`, `TileReadyBatch` (Task 1).
- Produces: `async def backfill(*, dry_run: bool) -> dict` — the script's `main()` calls this; the test calls it directly.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_backfill_tile_customer_orders.py
from __future__ import annotations

import asyncio

from scripts import backfill_tile_customer_orders as backfill_module


class _FakeFind:
    def __init__(self, items): self._items = items
    async def to_list(self, n=None): return list(self._items)


class _FakeCollection:
    def __init__(self, docs): self.docs = docs
    def find(self, query=None, projection=None, session=None): return _FakeFind(self.docs)
    async def find_one(self, query=None, projection=None, session=None):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in (query or {}).items() if not k.startswith("$")):
                return dict(doc)
        return None
    async def insert_one(self, doc, session=None): self.docs.append(doc)
    async def update_one(self, query, update, session=None, **_kw):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                doc.update(update.get("$set", {}))


class _FakeCounters:
    def __init__(self): self.docs: dict = {}
    async def find_one(self, query, *_a, **_kw): return self.docs.get(query.get("_id"))
    async def find_one_and_update(self, query, update, **_kw):
        key = query["_id"]
        doc = self.docs.setdefault(key, {"_id": key, "seq": 0})
        doc["seq"] += update["$inc"]["seq"]
        return dict(doc)


def _old_tiles_po():
    return {
        "id": "po-1", "number": "FPO-2026-0001", "quotation_id": "q-1", "quotation_number": "FQ-2026-0001",
        "customer_id": "cust-1", "customer_name": "Nileshbhai Pokiya", "supplier_id": "s-1", "supplier_name": "Qutone Rajkot",
        "brand_id": "b-1", "brand_name": "Qutone", "floor_id": "ground-floor", "created_at": "2026-07-22T10:00:00+00:00",
        "items": [{"id": "item-1", "name": "Glossy Ivory 600x600", "qty": 20, "finish": None, "series": None, "size": None, "sku": "SKU-1"}],
        "chalans": [{"id": "old-ch-1", "number": "CH-0001", "stage": "released", "items": [{"po_item_id": "item-1", "name": "Glossy Ivory 600x600", "qty": 8, "unit": "Box"}], "created_at": "2026-07-23T10:00:00+00:00", "created_by": "u-1", "created_by_name": "Warehouse Rep"}],
    }


def test_backfill_creates_customer_order_and_migrates_chalans(monkeypatch):
    db = type("Db", (), {})()
    db.purchase_orders = _FakeCollection([_old_tiles_po()])
    db.quotations = _FakeCollection([{"id": "q-1", "doc_type": "tiles_quotation"}])
    db.customer_orders = _FakeCollection([])
    db.dispatches = _FakeCollection([])
    db.chalans = _FakeCollection([])
    db.ready_batches = _FakeCollection([])
    db.counters = _FakeCounters()
    monkeypatch.setattr(backfill_module, "db", db)

    result = asyncio.run(backfill_module.backfill(dry_run=False))

    assert result["customer_orders_created"] == 1
    assert result["chalans_migrated"] == 1
    assert len(db.customer_orders.docs) == 1
    po = db.purchase_orders.docs[0]
    assert po["customer_order_id"] == db.customer_orders.docs[0]["id"]
    item = po["items"][0]
    assert item["boxes_dispatched"] == 8
    assert item["boxes_pending"] == 12
    assert item["current_location"] == "Dispatched"  # old stage "released"
    assert len(db.chalans.docs) == 1
    assert len(db.dispatches.docs) == 1
    assert db.ready_batches.docs[0]["auto_created"] is True


def test_backfill_skips_standard_quotation_pos(monkeypatch):
    po = _old_tiles_po()
    db = type("Db", (), {})()
    db.purchase_orders = _FakeCollection([po])
    db.quotations = _FakeCollection([{"id": "q-1", "doc_type": "standard"}])
    db.customer_orders = _FakeCollection([])
    db.dispatches = _FakeCollection([])
    db.chalans = _FakeCollection([])
    db.ready_batches = _FakeCollection([])
    db.counters = _FakeCounters()
    monkeypatch.setattr(backfill_module, "db", db)

    result = asyncio.run(backfill_module.backfill(dry_run=False))

    assert result["customer_orders_created"] == 0
    assert db.customer_orders.docs == []


def test_backfill_is_idempotent(monkeypatch):
    po = _old_tiles_po()
    db = type("Db", (), {})()
    db.purchase_orders = _FakeCollection([po])
    db.quotations = _FakeCollection([{"id": "q-1", "doc_type": "tiles_quotation"}])
    db.customer_orders = _FakeCollection([])
    db.dispatches = _FakeCollection([])
    db.chalans = _FakeCollection([])
    db.ready_batches = _FakeCollection([])
    db.counters = _FakeCounters()
    monkeypatch.setattr(backfill_module, "db", db)

    asyncio.run(backfill_module.backfill(dry_run=False))
    result_second_run = asyncio.run(backfill_module.backfill(dry_run=False))

    assert result_second_run["customer_orders_created"] == 0  # already has customer_order_id, skipped
    assert len(db.customer_orders.docs) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_backfill_tile_customer_orders.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.backfill_tile_customer_orders'`

- [ ] **Step 3: Write the script**

```python
# backend/scripts/backfill_tile_customer_orders.py
#!/usr/bin/env python3
"""One-time backfill for the Tile Orders logistics redesign (see
docs/superpowers/specs/2026-07-29-tile-orders-logistics-redesign-design.md
§Migration). Creates a TileCustomerOrder for every pre-existing tiles
PurchaseOrder missing customer_order_id (grouped by quotation_id), and
converts each embedded old Chalan into a new TileDispatch + immutable
TileChalan + one synthetic fully-consumed TileReadyBatch.

Idempotent — a PurchaseOrder with customer_order_id already set is
skipped entirely, so re-running after a partial failure is safe.

Usage:
    cd backend && python scripts/backfill_tile_customer_orders.py           # apply
    cd backend && python scripts/backfill_tile_customer_orders.py --dry-run # report only, no writes
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from db import db
from models_tile_orders import (
    TileChalan, TileChalanItem, TileCustomerOrder, TileCustomerOrderBrand,
    TileCustomerOrderDashboardSummary, TileDispatch, TileDispatchLineConsumed, TileReadyBatch,
)
from services.sequence import next_number
from services.tile_order_status import rollup_status

_OLD_STAGE_TO_LOCATION = {"released": "Dispatched", "at_godown": "Godown", "dispatched": "Delivered"}


async def backfill(*, dry_run: bool) -> dict:
    customer_orders_created = 0
    chalans_migrated = 0

    pos = await db.purchase_orders.find(
        {"$or": [{"customer_order_id": {"$exists": False}}, {"customer_order_id": None}]}, {"_id": 0},
    ).to_list(50000)

    by_quotation: dict[str, list[dict]] = {}
    for po in pos:
        quotation_id = po.get("quotation_id")
        if not quotation_id:
            continue
        by_quotation.setdefault(quotation_id, []).append(po)

    for quotation_id, group_pos in by_quotation.items():
        quotation = await db.quotations.find_one({"id": quotation_id}, {"_id": 0, "doc_type": 1})
        if not quotation or quotation.get("doc_type") not in ("tiles_selection", "tiles_quotation"):
            continue  # standard (sanitaryware) orders never get a TileCustomerOrder

        first_po = group_pos[0]
        year_str = first_po.get("created_at", "")[:4] or str(datetime.now(timezone.utc).year)
        number = await next_number("customer_order", f"TORD-{year_str}-", collection="customer_orders")
        customer_order = TileCustomerOrder(
            number=number, quotation_id=quotation_id, quotation_number=first_po.get("quotation_number", ""),
            customer_id=first_po.get("customer_id", ""), customer_name=first_po.get("customer_name", ""),
            customer_phone="", delivery_name=first_po.get("customer_name", ""), delivery_phone="",
            delivery_address="", delivery_city="", delivery_pincode="", delivery_state="",
            floor_id=first_po.get("floor_id", "first-floor"), created_by="system-backfill",
            created_by_name="Backfill script", dashboard_summary=TileCustomerOrderDashboardSummary(),
        )

        total_products, total_boxes = 0, 0.0
        brands: list[TileCustomerOrderBrand] = []

        for po in group_pos:
            items = po.get("items", [])
            total_products += len(items)
            total_boxes += sum(float(i.get("qty") or 0) for i in items)

            for item in items:
                boxes_dispatched = 0.0
                location = "Pending"
                for old_chalan in po.get("chalans", []):
                    for line in old_chalan.get("items", []):
                        if line.get("po_item_id") != item["id"]:
                            continue
                        qty = float(line.get("qty") or 0)
                        boxes_dispatched += qty
                        location = _OLD_STAGE_TO_LOCATION.get(old_chalan.get("stage"), "Dispatched")

                        if not dry_run:
                            batch_number = await next_number("ready_batch", f"RB-{year_str}-", collection="ready_batches")
                            batch = TileReadyBatch(
                                batch_number=batch_number, purchase_order_id=po["id"], po_item_id=item["id"],
                                customer_order_id=customer_order.id, floor_id=po.get("floor_id", "first-floor"),
                                supplier_id=po.get("supplier_id"), supplier_name=po.get("supplier_name") or "Unassigned",
                                customer_id=po.get("customer_id"), customer_name=po.get("customer_name") or "",
                                tile_name=item.get("name", ""), qty=qty, remaining_qty=0,
                                created_by="system-backfill", created_by_name="Backfill script", auto_created=True,
                            )
                            await db.ready_batches.insert_one(batch.dict())

                            chalan = TileChalan(
                                number=old_chalan.get("number", ""), dispatch_id="", purchase_order_id=po["id"],
                                customer_order_id=customer_order.id, floor_id=po.get("floor_id", "first-floor"),
                                supplier_name=po.get("supplier_name") or "Unassigned", customer_name=po.get("customer_name") or "",
                                customer_phone="", delivery_address="", delivery_city="",
                                items=[TileChalanItem(po_item_id=item["id"], tile_name=item.get("name", ""), boxes=qty, quantity=qty)],
                                created_by=old_chalan.get("created_by", "system-backfill"),
                                created_by_name=old_chalan.get("created_by_name", "Backfill script"),
                                generated_at=old_chalan.get("created_at", datetime.now(timezone.utc).isoformat()),
                                generated_by_name=old_chalan.get("created_by_name", "Backfill script"),
                            )
                            dispatch = TileDispatch(
                                dispatch_number=await next_number("dispatch", f"DSP-{year_str}-", collection="dispatches"),
                                purchase_order_id=po["id"], customer_order_id=customer_order.id,
                                floor_id=po.get("floor_id", "first-floor"), supplier_id=po.get("supplier_id"),
                                supplier_name=po.get("supplier_name") or "Unassigned", customer_id=po.get("customer_id"),
                                customer_name=po.get("customer_name") or "",
                                ready_batches_consumed=[TileDispatchLineConsumed(ready_batch_id=batch.id, po_item_id=item["id"], qty=qty)],
                                destination_type="Customer", destination_name=po.get("customer_name") or "",
                                destination_address="", destination_city="",
                                dispatch_date=old_chalan.get("created_at", "")[:10], dispatch_time=old_chalan.get("created_at", "")[11:16],
                                created_by="system-backfill", created_by_name="Backfill script", chalan_id=chalan.id,
                            )
                            chalan.dispatch_id = dispatch.id
                            if old_chalan.get("stage") == "at_godown":
                                dispatch.godown_received_at = old_chalan.get("created_at")
                            await db.chalans.insert_one(chalan.dict())
                            await db.dispatches.insert_one(dispatch.dict())
                        chalans_migrated += 1

                item["boxes_ready"] = 0
                item["boxes_dispatched"] = boxes_dispatched
                item["boxes_pending"] = float(item.get("qty") or 0) - boxes_dispatched
                item["current_location"] = location
                item["overall_status"] = "Dispatched" if boxes_dispatched >= float(item.get("qty") or 0) and boxes_dispatched > 0 else ("Partially Dispatched" if boxes_dispatched > 0 else "Pending")

            po_status = rollup_status([i["overall_status"] for i in items])
            brands.append(TileCustomerOrderBrand(
                brand_id=po.get("brand_id"), brand_name=po.get("brand_name") or "Unassigned",
                supplier_id=po.get("supplier_id"), supplier_name=po.get("supplier_name") or "Unassigned",
                purchase_order_id=po["id"], status=po_status,
            ))
            if not dry_run:
                await db.purchase_orders.update_one({"id": po["id"]}, {"$set": {
                    "items": items, "customer_order_id": customer_order.id, "overall_status": po_status,
                    "dispatched_boxes": sum(i["boxes_dispatched"] for i in items),
                    "pending_boxes": sum(i["boxes_pending"] for i in items), "ready_boxes": 0,
                }})

        customer_order.brands = brands
        customer_order.total_products = total_products
        customer_order.total_boxes = total_boxes
        customer_order.overall_status = rollup_status([b.status for b in brands])
        customer_order.dashboard_summary = TileCustomerOrderDashboardSummary(
            completion_percentage=0, overall_status=customer_order.overall_status,
            supplier_statuses=[{"supplier_name": b.supplier_name, "status": b.status} for b in brands],
        )
        if not dry_run:
            await db.customer_orders.insert_one(customer_order.dict())
        customer_orders_created += 1

    return {"customer_orders_created": customer_orders_created, "chalans_migrated": chalans_migrated}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args()
    result = await backfill(dry_run=args.dry_run)
    mode = "DRY RUN — " if args.dry_run else ""
    print(f"{mode}Created {result['customer_orders_created']} TileCustomerOrder(s), migrated {result['chalans_migrated']} old Chalan(s).")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/test_backfill_tile_customer_orders.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full backend suite one final time**

Run: `cd backend && python -m pytest tests/unit -q`
Expected: PASS — every test from Tasks 1-13, no regressions in the pre-existing suite

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/backfill_tile_customer_orders.py backend/tests/unit/test_backfill_tile_customer_orders.py
git commit -m "feat: add one-time backfill script for pre-existing tiles PurchaseOrders"
```

**Do not run this script against the real database as part of this task.** Running it is an operational step for the Rollout phase (see Task 20), after a staging-copy dry run and explicit user confirmation — this task only makes the script exist and pass its own tests.

---

## Task 14: Frontend API client

No automated frontend test harness exists in this codebase (confirmed: no `*.test.ts(x)` outside `node_modules`) — this and every remaining frontend task are verified manually against the running dev server, per the Global Constraints note. TypeScript's own compiler is still the correctness check for this task.

**Files:**
- Create: `frontend/src/api/tileOrders.ts`

**Interfaces:**
- Produces: every type and function below — imported by every remaining frontend task.

- [ ] **Step 1: Write the client**

```typescript
// frontend/src/api/tileOrders.ts
// Typed client for the /tile-orders backend router (see
// backend/routes/tile_orders.py). Mirrors the thin api.get/post pattern
// already used throughout the app (@/src/api/client) — no separate fetch
// layer, just typed wrappers around it.
import { api } from "@/src/api/client";

export type TileOverallStatus = "Pending" | "Ready" | "Partially Dispatched" | "Dispatched" | "Delivered";
export type TileLocation = "Pending" | "Ready" | "Dispatched" | "Godown" | "Delivered";
export type AgeingBand = "green" | "amber" | "red";

export type CustomerOrderBrand = { brand_id: string | null; brand_name: string; supplier_id: string | null; supplier_name: string; purchase_order_id: string; status: TileOverallStatus };

export type CustomerOrderCard = {
  id: string; number: string; customer_name: string; customer_phone: string | null;
  order_date: string; waiting_days: number; ageing_band: AgeingBand;
  brands: CustomerOrderBrand[]; total_products: number; total_boxes: number; total_value: number;
  overall_status: TileOverallStatus; completion_percentage: number;
};

export type CustomerOrderItem = {
  po_item_id: string; tile_name: string; series: string | null; finish: string | null; size: string | null;
  boxes_ordered: number; boxes_ready: number; boxes_dispatched: number; boxes_pending: number;
  current_location: TileLocation; overall_status: TileOverallStatus;
};

export type CustomerOrderSupplierGroup = { purchase_order_id: string; supplier_name: string; overall_status: TileOverallStatus; items: CustomerOrderItem[] };

export type CustomerOrderDetail = {
  summary: {
    id: string; number: string; customer_name: string; order_date: string; brand_count: number;
    total_products: number; total_boxes: number; completion_percentage: number;
    waiting_days: number; ageing_band: AgeingBand; overall_status: TileOverallStatus;
  };
  suppliers: CustomerOrderSupplierGroup[];
};

export type SupplierLandingCard = { supplier_id: string | null; supplier_name: string; active_orders: number; max_supplier_silent_days: number };

export type SupplierOrderRow = {
  po_id: string; po_number: string; customer_id: string; customer_name: string; order_date: string;
  waiting_days: number; ageing_band: AgeingBand; total_products: number; total_boxes: number;
  overall_status: TileOverallStatus; completion_percentage: number;
};

export type SupplierOrdersKpi = {
  orders: number; pending: number; ready: number; partially_dispatched: number; completed: number;
  boxes_pending: number; boxes_ready: number; boxes_dispatched: number; oldest_pending_days: number;
};

export type SupplierAnalytics = {
  orders: number; waiting_avg_days: number; ready_time_avg_days: number; dispatch_time_avg_days: number;
  fulfilment_time_avg_days: number; oldest_pending_days: number; completion_percentage_avg: number;
};

export type PurchaseOrderItemDetail = {
  id: string; name: string; series: string | null; finish: string | null; size: string | null; sku: string | null;
  qty: number; boxes_ready: number; boxes_dispatched: number; boxes_pending: number;
  current_location: TileLocation; overall_status: TileOverallStatus;
};

export type PurchaseOrderDetail = {
  id: string; number: string; customer_name: string; supplier_name: string | null;
  overall_status: TileOverallStatus; items: PurchaseOrderItemDetail[];
};

export type ReadyBatch = { id: string; batch_number: string; po_item_id: string; qty: number; remaining_qty: number; created_at: string };

export type DispatchPreviewLine = { po_item_id: string; tile_name: string; qty: number; source: "existing" | "pending"; remaining_pending_after: number };
export type DispatchPreview = { po_id: string; items: DispatchPreviewLine[]; warnings: string[]; will_create: { dispatch_number: string; chalan_number: string; creates_dispatch_list_entry: boolean } };

export type DispatchLineInput = { po_item_id: string; ready_batch_id: string | null; qty: number };
export type DispatchDestination = { destination_type: "Customer" | "Godown"; destination_name: string; destination_address: string; destination_city: string; reference_number?: string; receiver_name?: string; sender_name?: string };

export type DispatchListRow = { dispatch_number: string; chalan_number: string; customer_name: string; supplier_name: string; tile_name: string; tile_size: string | null; boxes: number; dispatch_date: string; destination: string; status: "Dispatched" | "At Godown" | "Delivered" };

export type TileOrdersDashboard = {
  customer_orders: number; supplier_orders: number; dispatched_today: number; delivered_today: number;
  pending: number; ready: number; waiting_over_15_days: number; boxes_ordered: number; boxes_pending: number; revenue: number;
};

const FLOOR = { floorId: "ground-floor" };

export const tileOrdersApi = {
  listCustomerOrders: (params?: { page?: number; page_size?: number; sort?: string; status?: string; search?: string }) =>
    api.get<{ orders: CustomerOrderCard[]; page: number; page_size: number; total: number }>(
      `/tile-orders/customer-orders${toQuery(params)}`, FLOOR,
    ),
  customerOrderDetail: (id: string) => api.get<CustomerOrderDetail>(`/tile-orders/customer-orders/${id}`, FLOOR),
  customerOrderTimeline: (id: string) => api.get<{ events: Record<string, any>[] }>(`/tile-orders/customer-orders/${id}/timeline`, FLOOR),

  listSuppliers: () => api.get<{ suppliers: SupplierLandingCard[] }>("/tile-orders/suppliers", FLOOR),
  supplierOrders: (supplierId: string, params?: { page?: number; page_size?: number; sort?: string; status?: string; search?: string }) =>
    api.get<{ kpi: SupplierOrdersKpi; orders: SupplierOrderRow[]; page: number; page_size: number; total: number }>(
      `/tile-orders/suppliers/${supplierId}/orders${toQuery(params)}`, FLOOR,
    ),
  supplierAnalytics: (supplierId: string) => api.get<SupplierAnalytics>(`/tile-orders/suppliers/${supplierId}/analytics`, FLOOR),

  purchaseOrderDetail: (poId: string) => api.get<PurchaseOrderDetail>(`/tile-orders/purchase-orders/${poId}`, FLOOR),
  markItemsReady: (poId: string, items: { po_item_id: string; qty: number }[]) =>
    api.post<{ po_id: string; ready_batches: ReadyBatch[]; overall_status: TileOverallStatus }>(
      `/tile-orders/purchase-orders/${poId}/ready`, { items }, FLOOR,
    ),
  previewDispatch: (poId: string, items: DispatchLineInput[], destination: DispatchDestination) =>
    api.post<DispatchPreview>(`/tile-orders/purchase-orders/${poId}/dispatch/preview`, { items, ...destination }, FLOOR),
  commitDispatch: (poId: string, items: DispatchLineInput[], destination: DispatchDestination) =>
    api.post<{ po_id: string; dispatch: Record<string, any>; chalan: Record<string, any>; overall_status: TileOverallStatus }>(
      `/tile-orders/purchase-orders/${poId}/dispatch`, { items, ...destination }, FLOOR,
    ),
  markGodownReceived: (dispatchId: string, note?: string) =>
    api.post<{ dispatch_id: string; godown_received_at: string }>(`/tile-orders/dispatches/${dispatchId}/godown-received`, { note }, FLOOR),

  listDispatches: (params?: Record<string, string | number | undefined>) =>
    api.get<{ rows: DispatchListRow[]; page: number; page_size: number; total: number }>(`/tile-orders/dispatches${toQuery(params)}`, FLOOR),
  itemHistory: (itemId: string) => api.get<{ item_id: string; events: Record<string, any>[] }>(`/tile-orders/items/${itemId}/history`, FLOOR),
  dashboard: () => api.get<TileOrdersDashboard>("/tile-orders/dashboard", FLOOR),
};

function toQuery(params?: Record<string, string | number | undefined>): string {
  if (!params) return "";
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (entries.length === 0) return "";
  return "?" + entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&");
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors attributable to `src/api/tileOrders.ts`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/tileOrders.ts
git commit -m "feat: add typed frontend client for the /tile-orders API"
```

---

## Task 15: Shared status/ageing/box-counter UI components

**Files:**
- Create: `frontend/src/components/tiles/TileOrderStatusUI.tsx`

**Interfaces:**
- Consumes: `TileOverallStatus`, `AgeingBand`, `CustomerOrderBrand`, `PurchaseOrderItemDetail` (Task 14).
- Produces: `StatusPill`, `AgeingBadge`, `BoxCounterRow`, `BrandStatusChips` — used by every remaining frontend task.

- [ ] **Step 1: Write the components**

```tsx
// frontend/src/components/tiles/TileOrderStatusUI.tsx
// Shared building blocks for every Tile Orders logistics screen: the
// overall_status pill, the waiting-days ageing badge (green/amber/red per
// the design doc's 0-7/8-14/15+ bands), and the per-line box-counter row.
import { Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/src/theme/tokens";
import type { AgeingBand, CustomerOrderBrand, TileOverallStatus } from "@/src/api/tileOrders";

const STATUS_COLORS: Record<TileOverallStatus, { fg: string; bg: string; border: string }> = {
  Pending: { fg: colors.onSurfaceMuted, bg: colors.surfaceSecondary, border: colors.border },
  Ready: { fg: colors.infoFg, bg: colors.infoBg, border: colors.infoBorder },
  "Partially Dispatched": { fg: colors.warningFg, bg: colors.warningBg, border: colors.warningBorder },
  Dispatched: { fg: colors.successFg, bg: colors.successBg, border: colors.successBorder },
  Delivered: { fg: colors.successFg, bg: colors.successBg, border: colors.successBorder },
};

export function StatusPill({ status }: { status: TileOverallStatus }) {
  const palette = STATUS_COLORS[status] || STATUS_COLORS.Pending;
  return (
    <View style={{
      alignSelf: "flex-start", paddingVertical: 3, paddingHorizontal: spacing.sm,
      borderRadius: radius.pill, backgroundColor: palette.bg, borderWidth: 1, borderColor: palette.border,
    }}>
      <Text style={[type.captionStrong, { color: palette.fg }]}>{status}</Text>
    </View>
  );
}

const AGEING_COLORS: Record<AgeingBand, { fg: string; bg: string; border: string }> = {
  green: { fg: colors.successFg, bg: colors.successBg, border: colors.successBorder },
  amber: { fg: colors.warningFg, bg: colors.warningBg, border: colors.warningBorder },
  red: { fg: colors.errorFg, bg: colors.errorBg, border: colors.errorBorder },
};

export function AgeingBadge({ days, band }: { days: number; band: AgeingBand }) {
  const palette = AGEING_COLORS[band];
  return (
    <View style={{
      alignSelf: "flex-start", paddingVertical: 3, paddingHorizontal: spacing.sm,
      borderRadius: radius.pill, backgroundColor: palette.bg, borderWidth: 1, borderColor: palette.border,
    }}>
      <Text style={[type.captionStrong, { color: palette.fg }]}>{days} day{days === 1 ? "" : "s"} waiting</Text>
    </View>
  );
}

export function BoxCounterRow({ ordered, ready, dispatched, pending }: { ordered: number; ready: number; dispatched: number; pending: number }) {
  const cell = (label: string, value: number) => (
    <View style={{ alignItems: "center", flex: 1 }}>
      <Text style={type.numeric}>{value}</Text>
      <Text style={[type.bodyMuted, { fontSize: 11 }]}>{label}</Text>
    </View>
  );
  return (
    <View style={{ flexDirection: "row", paddingVertical: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider }}>
      {cell("Ordered", ordered)}
      {cell("Ready", ready)}
      {cell("Dispatched", dispatched)}
      {cell("Pending", pending)}
    </View>
  );
}

export function BrandStatusChips({ brands }: { brands: CustomerOrderBrand[] }) {
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
      {brands.map((brand) => (
        <View key={brand.purchase_order_id} style={{
          flexDirection: "row", alignItems: "center", gap: 4, paddingVertical: 2, paddingHorizontal: spacing.sm,
          borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
        }}>
          <Text style={type.bodySm}>{brand.brand_name}</Text>
          <StatusPill status={brand.status} />
        </View>
      ))}
    </View>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors attributable to `TileOrderStatusUI.tsx`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/tiles/TileOrderStatusUI.tsx
git commit -m "feat: add shared status/ageing/box-counter UI components"
```

---

## Task 16: Rewrite Tile Orders index (3 tabs) + Customer Order detail page

Replaces the old Customer-wise/Company-wise 2-tab screen with three tabs (Customer / Company / Dispatch List) against the new endpoints, and replaces the old PurchaseOrder-detail `[id].tsx` with a read-only CustomerOrder detail (summary card + supplier-grouped product lines — actions live on the Supplier order-detail page from Task 18, per the design doc's clean separation between customer-facing and supplier-facing surfaces). The old `frontend/src/components/tiles/TileOrderCard.tsx` exports are left in place, unused, as the design doc's rollback safety net — nothing deletes them in this task.

**Files:**
- Modify: `frontend/app/(admin)/tiles/orders/index.tsx` (full rewrite)
- Modify: `frontend/app/(admin)/tiles/orders/[id].tsx` (full rewrite)

**Interfaces:**
- Consumes: `tileOrdersApi` (Task 14), `StatusPill`/`AgeingBadge`/`BoxCounterRow`/`BrandStatusChips` (Task 15).
- Produces: nothing new consumed by later tasks — Task 17/18 add sibling routes, not imports from this file.

- [ ] **Step 1: Rewrite `index.tsx`**

```tsx
// frontend/app/(admin)/tiles/orders/index.tsx
// Ground Floor → Tiles → Orders — three tabs over the same underlying
// CustomerOrder/PurchaseOrder data: Customer (one card per CustomerOrder),
// Company (one card per supplier, landing only — never customer orders
// directly), and Dispatch List (the permanent dispatch register).
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { tileOrdersApi, type CustomerOrderCard, type DispatchListRow, type SupplierLandingCard } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { AgeingBadge, BrandStatusChips, StatusPill } from "@/src/components/tiles/TileOrderStatusUI";
import { useBp } from "@/src/design/responsive";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

type TabKey = "customer" | "company" | "dispatch-list";
const TABS: [TabKey, string][] = [["customer", "Customer"], ["company", "Company"], ["dispatch-list", "Dispatch List"]];

export default function TileOrdersScreen() {
  useRequireFloorAccess("ground-floor");
  const router = useRouter();
  const { isPhone, isTablet } = useBp();
  const cols = isPhone ? 1 : isTablet ? 2 : 3;
  const cardSlotStyle = { width: `${100 / cols}%` as const, padding: spacing.sm };
  const [tab, setTab] = useState<TabKey>("customer");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [customerOrders, setCustomerOrders] = useState<CustomerOrderCard[]>([]);
  const [suppliers, setSuppliers] = useState<SupplierLandingCard[]>([]);
  const [dispatchRows, setDispatchRows] = useState<DispatchListRow[]>([]);
  const [dispatchSearch, setDispatchSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      if (tab === "customer") {
        setCustomerOrders((await tileOrdersApi.listCustomerOrders()).orders);
      } else if (tab === "company") {
        setSuppliers((await tileOrdersApi.listSuppliers()).suppliers);
      } else {
        setDispatchRows((await tileOrdersApi.listDispatches({ search: dispatchSearch || undefined })).rows);
      }
    } catch (e: any) {
      const message = e?.detail || "Could not load orders";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [tab, dispatchSearch]);

  useEffect(() => { load(); }, [load]);

  const openCustomerOrder = (id: string) => router.push(`/(admin)/tiles/orders/${id}` as any);
  const openSupplier = (supplierId: string | null) => router.push(`/(admin)/tiles/orders/company/${supplierId || "unassigned"}` as any);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={type.overline}>GROUND FLOOR · TILES</Text>
        <Text style={type.displayMd}>Tile Orders</Text>
        <Text style={type.bodyMuted}>Track every tile order from placement to delivery.</Text>

        <View style={styles.tabRow}>
          {TABS.map(([key, label]) => (
            <Pressable key={key} onPress={() => setTab(key)} style={[styles.tab, tab === key ? styles.tabActive : null]}>
              <Text style={[type.bodyStrong, tab === key ? { color: colors.brandHover } : null]}>{label}</Text>
            </Pressable>
          ))}
        </View>

        {loading ? (
          <ActivityIndicator style={{ marginTop: spacing.xl }} color={colors.brand} />
        ) : loadError ? (
          <View style={{ marginTop: spacing.xl, alignItems: "flex-start", gap: spacing.md }}>
            <Text style={type.bodyStrong}>{loadError}</Text>
            <Pressable style={styles.retryButton} onPress={() => load()}>
              <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Retry</Text>
            </Pressable>
          </View>
        ) : tab === "customer" ? (
          customerOrders.length === 0 ? (
            <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No tile orders yet.</Text>
          ) : (
            <View style={styles.cardGrid}>
              {customerOrders.map((order) => (
                <View key={order.id} style={cardSlotStyle}>
                  <Pressable onPress={() => openCustomerOrder(order.id)} style={styles.customerCard}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                      <View style={{ flex: 1, minWidth: 0 }}>
                        <Text numberOfLines={1} style={type.titleSm}>{order.customer_name}</Text>
                        <Text numberOfLines={1} style={type.bodyMuted}>{order.customer_phone || "No phone on file"}</Text>
                      </View>
                      <Text style={type.captionStrong}>{order.number}</Text>
                    </View>
                    <AgeingBadge days={order.waiting_days} band={order.ageing_band} />
                    <BrandStatusChips brands={order.brands} />
                    <View style={styles.customerCardFooter}>
                      <Text style={type.bodyMuted}>{order.total_products} products · {order.total_boxes} boxes</Text>
                      <StatusPill status={order.overall_status} />
                    </View>
                  </Pressable>
                </View>
              ))}
            </View>
          )
        ) : tab === "company" ? (
          suppliers.length === 0 ? (
            <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No suppliers with active orders yet.</Text>
          ) : (
            <View style={styles.cardGrid}>
              {suppliers.map((supplier) => (
                <View key={supplier.supplier_id || "unassigned"} style={cardSlotStyle}>
                  <Pressable onPress={() => openSupplier(supplier.supplier_id)} style={styles.supplierCard}>
                    <Feather name="briefcase" size={18} color={colors.onSurfaceMuted} />
                    <Text style={type.titleMd}>{supplier.supplier_name}</Text>
                    <Text style={type.bodyMuted}>{supplier.active_orders} active order{supplier.active_orders === 1 ? "" : "s"}</Text>
                    {supplier.max_supplier_silent_days > 0 ? (
                      <Text style={[type.captionStrong, { color: colors.warningFg }]}>Supplier silent {supplier.max_supplier_silent_days}d</Text>
                    ) : null}
                  </Pressable>
                </View>
              ))}
            </View>
          )
        ) : (
          <View style={{ marginTop: spacing.md }}>
            <TextInput
              placeholder="Search customer, supplier, dispatch, chalan…" value={dispatchSearch}
              onChangeText={setDispatchSearch} onSubmitEditing={() => load()} style={styles.searchInput}
            />
            {dispatchRows.length === 0 ? (
              <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No dispatches yet.</Text>
            ) : (
              dispatchRows.map((row, i) => (
                <View key={`${row.dispatch_number}-${i}`} style={styles.dispatchRow}>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={type.bodyStrong}>{row.dispatch_number} · {row.chalan_number}</Text>
                    <Text style={type.bodySm}>{row.tile_name} {row.tile_size ? `· ${row.tile_size}` : ""} · {row.boxes} boxes</Text>
                    <Text style={type.bodyMuted}>{row.customer_name} · {row.supplier_name} · {row.destination}</Text>
                  </View>
                  <View style={{ alignItems: "flex-end", gap: spacing.xs }}>
                    <Text style={type.bodyMuted}>{row.dispatch_date}</Text>
                    <Text style={[type.captionStrong, { color: colors.brandHover }]}>{row.status}</Text>
                  </View>
                </View>
              ))
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.xl, width: "100%", maxWidth: 1120, alignSelf: "center" },
  tabRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg, marginBottom: spacing.md },
  tab: { paddingVertical: spacing.sm, paddingHorizontal: spacing.lg, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  tabActive: { backgroundColor: colors.brandTint, borderColor: colors.brandBorder },
  retryButton: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.xl },
  cardGrid: { flexDirection: "row", flexWrap: "wrap", marginHorizontal: -spacing.sm, marginTop: spacing.sm },
  customerCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, gap: spacing.sm },
  customerCardFooter: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider },
  supplierCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, gap: spacing.xs },
  searchInput: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingVertical: spacing.sm, paddingHorizontal: spacing.md, marginBottom: spacing.md },
  dispatchRow: { flexDirection: "row", justifyContent: "space-between", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md, marginBottom: spacing.sm },
});
```

- [ ] **Step 2: Rewrite `[id].tsx`**

```tsx
// frontend/app/(admin)/tiles/orders/[id].tsx
// Ground Floor → Tiles → Orders → Customer detail — read-only summary +
// supplier-grouped product lines. Ready/Dispatch actions live on the
// Supplier order-detail page (Task 18), not here — this is the customer-
// facing view, staff use it to see the whole order's status at a glance.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { tileOrdersApi, type CustomerOrderDetail } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { AgeingBadge, BoxCounterRow, StatusPill } from "@/src/components/tiles/TileOrderStatusUI";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

export default function CustomerOrderDetailScreen() {
  useRequireFloorAccess("ground-floor");
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [order, setOrder] = useState<CustomerOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setLoadError(null);
    try {
      setOrder(await tileOrdersApi.customerOrderDetail(id));
    } catch (e: any) {
      const message = e?.detail || "Could not load order";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface, justifyContent: "center" }}>
        <ActivityIndicator color={colors.brand} />
      </SafeAreaView>
    );
  }

  if (loadError || !order) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface, justifyContent: "center", alignItems: "center", gap: spacing.md, padding: spacing.xl }}>
        <Text style={type.bodyStrong}>{loadError || "Order not found"}</Text>
        <Pressable style={styles.primaryButton} onPress={() => load()}>
          <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Retry</Text>
        </Pressable>
        <Pressable onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back to Tile Orders</Text>
        </Pressable>
      </SafeAreaView>
    );
  }

  const { summary, suppliers } = order;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Pressable onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back to Tile Orders</Text>
        </Pressable>

        <View style={styles.summaryCard}>
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <Text style={type.overline}>{summary.number}</Text>
            <StatusPill status={summary.overall_status} />
          </View>
          <Text style={type.displayMd}>{summary.customer_name}</Text>
          <Text style={type.bodyMuted}>{summary.order_date.slice(0, 10)} · {summary.brand_count} brand{summary.brand_count === 1 ? "" : "s"}</Text>
          <View style={{ flexDirection: "row", gap: spacing.lg, marginTop: spacing.sm }}>
            <View><Text style={type.numeric}>{summary.total_products}</Text><Text style={type.bodyMuted}>Products</Text></View>
            <View><Text style={type.numeric}>{summary.total_boxes}</Text><Text style={type.bodyMuted}>Boxes</Text></View>
            <View><Text style={type.numeric}>{summary.completion_percentage}%</Text><Text style={type.bodyMuted}>Complete</Text></View>
          </View>
          <AgeingBadge days={summary.waiting_days} band={summary.ageing_band} />
        </View>

        {suppliers.map((group) => (
          <View key={group.purchase_order_id} style={{ marginTop: spacing.xl }}>
            <View style={styles.supplierHeader}>
              <Text style={type.titleMd}>{group.supplier_name}</Text>
              <StatusPill status={group.overall_status} />
            </View>
            {group.items.map((item) => (
              <View key={item.po_item_id} style={styles.itemCard}>
                <Text style={type.bodyStrong}>{item.tile_name}</Text>
                <Text style={type.bodyMuted}>{[item.series, item.finish, item.size].filter(Boolean).join(" · ") || "—"}</Text>
                <BoxCounterRow ordered={item.boxes_ordered} ready={item.boxes_ready} dispatched={item.boxes_dispatched} pending={item.boxes_pending} />
                <Text style={type.bodyMuted}>Currently: {item.current_location}</Text>
              </View>
            ))}
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.xl, width: "100%", maxWidth: 760, alignSelf: "center" },
  backRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.md },
  primaryButton: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.xl },
  summaryCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, gap: spacing.xs },
  supplierHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm },
  itemCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, marginTop: spacing.sm, gap: spacing.xs },
});
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors attributable to either rewritten file

- [ ] **Step 4: Manually verify in the browser preview**

Start the dev server (`preview_start` with the project's configured frontend launch entry, or `npm run web`/equivalent per `frontend/package.json`), sign in as staff, navigate to Tile Orders. Confirm: the three tabs (Customer/Company/Dispatch List) switch without errors; each shows its correct empty state on a fresh/empty DB ("No tile orders yet." / "No suppliers with active orders yet." / "No dispatches yet."); no red-screen errors in the console. If any tiles orders already exist from earlier testing, open one Customer card and confirm the detail page renders the summary + supplier groups without crashing.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/\(admin\)/tiles/orders/index.tsx frontend/app/\(admin\)/tiles/orders/\[id\].tsx
git commit -m "feat: rewrite Tile Orders index (3 tabs) and Customer Order detail page"
```

---

## Task 17: Supplier dashboard page

**Files:**
- Create: `frontend/app/(admin)/tiles/orders/company/[supplierId].tsx`

**Interfaces:**
- Consumes: `tileOrdersApi.supplierOrders` (Task 14), `AgeingBadge`/`StatusPill` (Task 15).
- Produces: nothing consumed elsewhere — Task 18's page is reached by tapping a row here.

- [ ] **Step 1: Write the page**

```tsx
// frontend/app/(admin)/tiles/orders/company/[supplierId].tsx
// Ground Floor → Tiles → Orders → Company → Supplier dashboard. Shows
// ONLY this supplier's orders — never mixes in another supplier's, per
// the design doc's "supplier dashboards must never mix brands" rule.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { tileOrdersApi, type SupplierOrderRow, type SupplierOrdersKpi } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { AgeingBadge, StatusPill } from "@/src/components/tiles/TileOrderStatusUI";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

export default function SupplierDashboardScreen() {
  useRequireFloorAccess("ground-floor");
  const { supplierId } = useLocalSearchParams<{ supplierId: string }>();
  const router = useRouter();
  const [kpi, setKpi] = useState<SupplierOrdersKpi | null>(null);
  const [orders, setOrders] = useState<SupplierOrderRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!supplierId) return;
    setLoading(true);
    setLoadError(null);
    try {
      const r = await tileOrdersApi.supplierOrders(supplierId);
      setKpi(r.kpi);
      setOrders(r.orders);
    } catch (e: any) {
      const message = e?.detail || "Could not load supplier orders";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [supplierId]);

  useEffect(() => { load(); }, [load]);

  const openOrder = (poId: string) => router.push(`/(admin)/tiles/orders/po/${poId}` as any);

  if (loading) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface, justifyContent: "center" }}>
        <ActivityIndicator color={colors.brand} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Pressable onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back to Company</Text>
        </Pressable>
        <Text style={type.displayMd}>Supplier orders</Text>

        {loadError ? (
          <View style={{ marginTop: spacing.xl, gap: spacing.md, alignItems: "flex-start" }}>
            <Text style={type.bodyStrong}>{loadError}</Text>
            <Pressable style={styles.retryButton} onPress={() => load()}>
              <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Retry</Text>
            </Pressable>
          </View>
        ) : (
          <>
            {kpi ? (
              <View style={styles.kpiBar}>
                {([
                  ["Orders", kpi.orders], ["Pending", kpi.pending], ["Ready", kpi.ready],
                  ["Partial", kpi.partially_dispatched], ["Completed", kpi.completed],
                  ["Oldest Pending", `${kpi.oldest_pending_days}d`],
                ] as [string, number | string][]).map(([label, value]) => (
                  <View key={label} style={styles.kpiCell}>
                    <Text style={type.numeric}>{value}</Text>
                    <Text style={type.bodyMuted}>{label}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            {orders.length === 0 ? (
              <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No orders for this supplier yet.</Text>
            ) : (
              orders.map((order) => (
                <Pressable key={order.po_id} onPress={() => openOrder(order.po_id)} style={styles.orderRow}>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={type.bodyStrong}>{order.customer_name}</Text>
                    <Text style={type.bodyMuted}>{order.po_number} · {order.total_products} products · {order.total_boxes} boxes</Text>
                  </View>
                  <View style={{ alignItems: "flex-end", gap: spacing.xs }}>
                    <AgeingBadge days={order.waiting_days} band={order.ageing_band} />
                    <StatusPill status={order.overall_status} />
                  </View>
                </Pressable>
              ))
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.xl, width: "100%", maxWidth: 900, alignSelf: "center" },
  backRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.md },
  retryButton: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.xl },
  kpiBar: { flexDirection: "row", flexWrap: "wrap", gap: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, marginVertical: spacing.lg },
  kpiCell: { minWidth: 80 },
  orderRow: { flexDirection: "row", justifyContent: "space-between", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md, marginBottom: spacing.sm },
});
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors

- [ ] **Step 3: Manually verify in the browser preview**

From the Tile Orders → Company tab, tap a supplier card and confirm the dashboard loads with the KPI bar and order rows (or the empty state on a fresh DB), and that tapping "Back to Company" returns correctly.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/\(admin\)/tiles/orders/company/\[supplierId\].tsx
git commit -m "feat: add Supplier dashboard page"
```

---

## Task 18: Supplier order detail — bulk Ready + Dispatch (preview → commit)

**A small backend gap found while designing this screen**: Task 7's `POST .../dispatch` takes a specific `ready_batch_id` per line (or `null` for direct-from-pending) — correct for the API, but staff shouldn't have to know internal batch IDs. They think "dispatch 3 boxes of this tile," not "dispatch 3 boxes from batch RB-2026-0001." So this task adds one small new read endpoint the frontend uses to **greedily auto-allocate** a plain "dispatch N boxes of item X" request across that item's existing Ready Batches (oldest first) before calling the Task 7 endpoints — Task 7's contract itself is unchanged.

**Files:**
- Modify: `backend/routes/tile_orders.py` (new small read endpoint)
- Modify: `frontend/src/api/tileOrders.ts` (add `itemReadyBatches`)
- Create: `backend/tests/unit/test_tile_orders_item_ready_batches.py`
- Create: `frontend/src/components/tiles/ReadyDispatchSheets.tsx`
- Create: `frontend/app/(admin)/tiles/orders/po/[poId].tsx`

**Interfaces:**
- Consumes: `tileOrdersApi` (Task 14, extended here), `StatusPill`/`BoxCounterRow` (Task 15).
- Produces: `MarkReadySheet`, `DispatchSheet` — used only by `po/[poId].tsx` in this task.

- [ ] **Step 1: Write the failing backend test**

```python
# backend/tests/unit/test_tile_orders_item_ready_batches.py
from __future__ import annotations

import asyncio

from models import UserPublic
from routes import tile_orders as router_module


def _user() -> UserPublic:
    return UserPublic(email="wh@forge.app", full_name="Warehouse Rep", role="warehouse", floor_ids=["ground-floor"], active_floor_id="ground-floor")


class _FakeFind:
    def __init__(self, items): self._items = items
    async def to_list(self, n=None): return list(self._items)


class _FakeReadyBatches:
    def __init__(self, docs): self.docs = docs
    def find(self, query=None, projection=None, session=None):
        matched = [d for d in self.docs if d.get("po_item_id") == query.get("po_item_id") and d.get("remaining_qty", 0) > 0]
        return _FakeFind(matched)


class _FakeDb:
    def __init__(self, docs): self.ready_batches = _FakeReadyBatches(docs)


def test_item_ready_batches_excludes_fully_consumed(monkeypatch):
    fake_db = _FakeDb([
        {"id": "rb-1", "po_item_id": "item-1", "remaining_qty": 4, "created_at": "2026-07-27T10:00:00+00:00"},
        {"id": "rb-2", "po_item_id": "item-1", "remaining_qty": 0, "created_at": "2026-07-28T10:00:00+00:00"},
    ])
    monkeypatch.setattr(router_module, "db", fake_db)

    result = asyncio.run(router_module.item_ready_batches("po-1", "item-1", user=_user()))

    assert [b["id"] for b in result["batches"]] == ["rb-1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_tile_orders_item_ready_batches.py -v`
Expected: FAIL — `AttributeError: module 'routes.tile_orders' has no attribute 'item_ready_batches'`

- [ ] **Step 3: Add the endpoint**

Append to `backend/routes/tile_orders.py`:

```python
@router.get("/purchase-orders/{po_id}/items/{item_id}/ready-batches")
async def item_ready_batches(po_id: str, item_id: str, user: UserPublic = Depends(require_min_role("warehouse"))):
    batches = await db.ready_batches.find(
        {"purchase_order_id": po_id, "po_item_id": item_id, "remaining_qty": {"$gt": 0}}, {"_id": 0},
    ).to_list(200)
    batches.sort(key=lambda b: b.get("created_at", ""))
    return {"batches": batches}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_tile_orders_item_ready_batches.py -v`
Expected: PASS

- [ ] **Step 5: Add the client function**

Add to `frontend/src/api/tileOrders.ts`'s `tileOrdersApi` object (alongside `previewDispatch`/`commitDispatch`):

```typescript
  itemReadyBatches: (poId: string, itemId: string) => api.get<{ batches: ReadyBatch[] }>(`/tile-orders/purchase-orders/${poId}/items/${itemId}/ready-batches`, FLOOR),
```

- [ ] **Step 6: Write the Ready/Dispatch sheet components**

```tsx
// frontend/src/components/tiles/ReadyDispatchSheets.tsx
// Bottom-sheet forms for the two Supplier order-detail actions. DispatchSheet
// does client-side allocation across existing Ready Batches (oldest first)
// before calling preview/commit, so staff enter a plain "dispatch N boxes"
// number per item instead of picking an internal batch ID — see Task 18.
import { useState } from "react";
import { Modal, Pressable, ScrollView, Text, TextInput, View } from "react-native";

import { tileOrdersApi, type DispatchLineInput, type DispatchPreview, type PurchaseOrderItemDetail } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

async function allocateDispatchLines(poId: string, entries: { po_item_id: string; qty: number }[]): Promise<DispatchLineInput[]> {
  const lines: DispatchLineInput[] = [];
  for (const entry of entries) {
    let remaining = entry.qty;
    const { batches } = await tileOrdersApi.itemReadyBatches(poId, entry.po_item_id);
    for (const batch of batches) {
      if (remaining <= 0) break;
      const take = Math.min(remaining, batch.remaining_qty);
      lines.push({ po_item_id: entry.po_item_id, ready_batch_id: batch.id, qty: take });
      remaining -= take;
    }
    if (remaining > 0) {
      lines.push({ po_item_id: entry.po_item_id, ready_batch_id: null, qty: remaining });
    }
  }
  return lines;
}

export function MarkReadySheet({ poId, items, onClose, onDone }: { poId: string; items: PurchaseOrderItemDetail[]; onClose: () => void; onDone: () => void }) {
  const [qtyByItem, setQtyByItem] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const entries = items
      .map((item) => ({ po_item_id: item.id, qty: Number(qtyByItem[item.id] || 0) }))
      .filter((e) => e.qty > 0);
    if (entries.length === 0) {
      toast.error("Enter at least one quantity");
      return;
    }
    setBusy(true);
    try {
      await tileOrdersApi.markItemsReady(poId, entries);
      toast.success("Marked ready");
      onDone();
    } catch (e: any) {
      toast.error(e?.detail || "Could not mark items ready");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: "flex-end" }}>
        <View style={{ backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.xl, maxHeight: "80%" }}>
          <Text style={type.titleMd}>Mark Ready For Pickup</Text>
          <ScrollView style={{ marginVertical: spacing.md }}>
            {items.filter((item) => item.boxes_pending > 0).map((item) => (
              <View key={item.id} style={{ marginBottom: spacing.md }}>
                <Text style={type.bodyStrong}>{item.name}</Text>
                <Text style={type.bodyMuted}>{item.boxes_pending} boxes pending</Text>
                <TextInput
                  keyboardType="numeric" placeholder="Qty ready"
                  value={qtyByItem[item.id] || ""} onChangeText={(v) => setQtyByItem((s) => ({ ...s, [item.id]: v }))}
                  style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.sm, marginTop: spacing.xs }}
                />
              </View>
            ))}
          </ScrollView>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Pressable onPress={onClose} style={{ flex: 1, padding: spacing.md, alignItems: "center", borderRadius: radius.md, borderWidth: 1, borderColor: colors.border }}>
              <Text style={type.bodyStrong}>Cancel</Text>
            </Pressable>
            <Pressable disabled={busy} onPress={submit} style={{ flex: 1, padding: spacing.md, alignItems: "center", borderRadius: radius.md, backgroundColor: colors.brand }}>
              <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Mark Ready</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

export function DispatchSheet({ poId, items, customerName, customerAddress, customerCity, onClose, onDone }: {
  poId: string; items: PurchaseOrderItemDetail[]; customerName: string; customerAddress: string; customerCity: string;
  onClose: () => void; onDone: () => void;
}) {
  const [qtyByItem, setQtyByItem] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<DispatchPreview | null>(null);
  const [busy, setBusy] = useState(false);

  const entries = () => items
    .map((item) => ({ po_item_id: item.id, qty: Number(qtyByItem[item.id] || 0) }))
    .filter((e) => e.qty > 0);

  const runPreview = async () => {
    const built = entries();
    if (built.length === 0) {
      toast.error("Enter at least one quantity to dispatch");
      return;
    }
    setBusy(true);
    try {
      const lines = await allocateDispatchLines(poId, built);
      const result = await tileOrdersApi.previewDispatch(poId, lines, {
        destination_type: "Customer", destination_name: customerName, destination_address: customerAddress, destination_city: customerCity,
      });
      setPreview(result);
    } catch (e: any) {
      toast.error(e?.detail || "Could not preview dispatch");
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    setBusy(true);
    try {
      const lines = await allocateDispatchLines(poId, entries());
      await tileOrdersApi.commitDispatch(poId, lines, {
        destination_type: "Customer", destination_name: customerName, destination_address: customerAddress, destination_city: customerCity,
      });
      toast.success("Dispatched — Chalan generated");
      onDone();
    } catch (e: any) {
      toast.error(e?.detail || "Could not dispatch");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: "flex-end" }}>
        <View style={{ backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.xl, maxHeight: "85%" }}>
          <Text style={type.titleMd}>Dispatch</Text>
          <ScrollView style={{ marginVertical: spacing.md }}>
            {!preview ? items.filter((item) => item.boxes_ready + item.boxes_pending > 0).map((item) => (
              <View key={item.id} style={{ marginBottom: spacing.md }}>
                <Text style={type.bodyStrong}>{item.name}</Text>
                <Text style={type.bodyMuted}>Ready {item.boxes_ready} · Pending {item.boxes_pending}</Text>
                <TextInput
                  keyboardType="numeric" placeholder="Dispatch today"
                  value={qtyByItem[item.id] || ""} onChangeText={(v) => setQtyByItem((s) => ({ ...s, [item.id]: v }))}
                  style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.sm, marginTop: spacing.xs }}
                />
              </View>
            )) : (
              <View>
                <Text style={type.bodyStrong}>Will create: Dispatch → Chalan → Dispatch List entry</Text>
                {preview.warnings.map((w, i) => <Text key={i} style={[type.bodyMuted, { color: colors.warningFg }]}>{w}</Text>)}
                {preview.items.map((line) => (
                  <Text key={line.po_item_id} style={type.bodySm}>{line.tile_name} · {line.qty} boxes · {line.remaining_pending_after} pending after</Text>
                ))}
              </View>
            )}
          </ScrollView>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Pressable onPress={onClose} style={{ flex: 1, padding: spacing.md, alignItems: "center", borderRadius: radius.md, borderWidth: 1, borderColor: colors.border }}>
              <Text style={type.bodyStrong}>Cancel</Text>
            </Pressable>
            {!preview ? (
              <Pressable disabled={busy} onPress={runPreview} style={{ flex: 1, padding: spacing.md, alignItems: "center", borderRadius: radius.md, backgroundColor: colors.brand }}>
                <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Preview</Text>
              </Pressable>
            ) : (
              <Pressable disabled={busy} onPress={confirm} style={{ flex: 1, padding: spacing.md, alignItems: "center", borderRadius: radius.md, backgroundColor: colors.brand }}>
                <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Confirm Dispatch</Text>
              </Pressable>
            )}
          </View>
        </View>
      </View>
    </Modal>
  );
}
```

- [ ] **Step 7: Write the Supplier order detail page**

```tsx
// frontend/app/(admin)/tiles/orders/po/[poId].tsx
// Ground Floor → Tiles → Orders → Company → Supplier → Order detail — the
// only screen with Ready/Dispatch actions, per the design doc's clean
// separation between customer-facing (read-only) and supplier-facing
// (actionable) surfaces.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { tileOrdersApi, type PurchaseOrderDetail } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { DispatchSheet, MarkReadySheet } from "@/src/components/tiles/ReadyDispatchSheets";
import { BoxCounterRow, StatusPill } from "@/src/components/tiles/TileOrderStatusUI";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

export default function SupplierOrderDetailScreen() {
  useRequireFloorAccess("ground-floor");
  const { poId } = useLocalSearchParams<{ poId: string }>();
  const router = useRouter();
  const [order, setOrder] = useState<PurchaseOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sheet, setSheet] = useState<"ready" | "dispatch" | null>(null);

  const load = useCallback(async () => {
    if (!poId) return;
    setLoading(true);
    setLoadError(null);
    try {
      setOrder(await tileOrdersApi.purchaseOrderDetail(poId));
    } catch (e: any) {
      const message = e?.detail || "Could not load order";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [poId]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface, justifyContent: "center" }}>
        <ActivityIndicator color={colors.brand} />
      </SafeAreaView>
    );
  }

  if (loadError || !order) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface, justifyContent: "center", alignItems: "center", gap: spacing.md, padding: spacing.xl }}>
        <Text style={type.bodyStrong}>{loadError || "Order not found"}</Text>
        <Pressable onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back</Text>
        </Pressable>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Pressable onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back to Supplier</Text>
        </Pressable>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <Text style={type.displayMd}>{order.customer_name}</Text>
          <StatusPill status={order.overall_status} />
        </View>
        <Text style={type.bodyMuted}>{order.number} · {order.supplier_name || "No supplier"}</Text>

        <View style={{ flexDirection: "row", gap: spacing.sm, marginVertical: spacing.lg }}>
          <Pressable style={styles.actionButton} onPress={() => setSheet("ready")}>
            <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Mark Ready For Pickup</Text>
          </Pressable>
          <Pressable style={styles.actionButton} onPress={() => setSheet("dispatch")}>
            <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Dispatch</Text>
          </Pressable>
        </View>

        {order.items.map((item) => (
          <View key={item.id} style={styles.itemCard}>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <Text style={type.bodyStrong}>{item.name}</Text>
              <StatusPill status={item.overall_status} />
            </View>
            <Text style={type.bodyMuted}>{[item.series, item.finish, item.size].filter(Boolean).join(" · ") || "—"}</Text>
            <BoxCounterRow ordered={item.qty} ready={item.boxes_ready} dispatched={item.boxes_dispatched} pending={item.boxes_pending} />
            <Text style={type.bodyMuted}>Currently: {item.current_location}</Text>
          </View>
        ))}
      </ScrollView>

      {sheet === "ready" ? (
        <MarkReadySheet poId={order.id} items={order.items} onClose={() => setSheet(null)} onDone={async () => { setSheet(null); await load(); }} />
      ) : null}
      {sheet === "dispatch" ? (
        <DispatchSheet
          poId={order.id} items={order.items} customerName={order.customer_name} customerAddress="" customerCity=""
          onClose={() => setSheet(null)} onDone={async () => { setSheet(null); await load(); }}
        />
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.xl, width: "100%", maxWidth: 760, alignSelf: "center" },
  backRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.md },
  actionButton: { flex: 1, backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md, alignItems: "center" },
  itemCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, marginBottom: spacing.sm, gap: spacing.xs },
});
```

Note `customerAddress`/`customerCity` are passed as empty strings here — `PurchaseOrderDetail` (Task 14's type) doesn't carry the customer's delivery snapshot today. Acceptable for this pass since the backend's `commit_dispatch` (Task 7) already stores whatever `destination_address/city` the request supplies verbatim on the `TileDispatch`/`TileChalan`, and the Chalan PDF's real source of truth is that stored snapshot — if this gap matters operationally, extending `GET /tile-orders/purchase-orders/{po_id}` to also return `customer_order_id`'s `delivery_address/city` (a one-line addition to Task 9's handler) is a natural, low-risk follow-up, not a blocker for this pass.

- [ ] **Step 8: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors

- [ ] **Step 9: Manually verify in the browser preview**

Place a real test tiles order (per Task 19's scenarios) so there's a live `PurchaseOrder` to open. From Company → a supplier → an order row, confirm: item cards show box counters; "Mark Ready For Pickup" opens the sheet, entering a quantity and submitting updates the counters on reload; "Dispatch" opens the sheet, "Preview" shows the will-create chain and warnings without changing any numbers yet, "Confirm Dispatch" commits and the item's `boxes_dispatched`/`current_location` update on reload.

- [ ] **Step 10: Commit**

```bash
git add backend/routes/tile_orders.py backend/tests/unit/test_tile_orders_item_ready_batches.py frontend/src/api/tileOrders.ts frontend/src/components/tiles/ReadyDispatchSheets.tsx frontend/app/\(admin\)/tiles/orders/po/\[poId\].tsx
git commit -m "feat: add Supplier order detail with Ready/Dispatch actions"
```

---

## Task 19: End-to-end verification against the six scenarios

Runs the full backend test suite one more time, then walks the six real-world scenarios from the design doc's Test Plan section through the actual running app (not mocks) — this is the "fix any inconsistencies before considering the feature complete" step from the original brief's Loop Engineering. No code changes are expected here; if a scenario surfaces a bug, fix it in the relevant task's file and re-run the affected task's tests before continuing.

**Files:** none new — this task exercises everything from Tasks 1-18.

- [ ] **Step 1: Full backend suite**

Run: `cd backend && python -m pytest tests/unit -q`
Expected: PASS — every test from every task, zero regressions in the pre-existing suite (69 pre-existing files + the new ones from this plan)

- [ ] **Step 2: Full frontend typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Start the app and place a real multi-supplier tiles order**

Start the dev server (backend `uvicorn` + frontend, per the project's normal local-dev instructions). As a sales-role user: build a Tiles Quotation with line items from at least 2 different brands (e.g. Qutone + Dimore), confirm it, and Place Order. Verify: `GET /tile-orders/customer-orders` shows exactly one card for this order with both brands listed; `GET /tile-orders/suppliers` shows both suppliers with an incremented active-order count; opening the customer card shows both suppliers' product lines grouped separately.

- [ ] **Step 4: Single-supplier order**

Repeat with a quotation containing only one brand. Verify: still exactly one `CustomerOrder`, with `brands` containing a single entry, and the Company tab's supplier card count increments by exactly one for that one supplier only.

- [ ] **Step 5: Partial dispatch**

On the multi-supplier order from Step 3, open one supplier's order detail. Mark a partial quantity of one item Ready (e.g. 12 of 20 boxes), then Dispatch a partial quantity of what's Ready (e.g. 8 of the 12). Verify the item shows `boxes_ready=4`, `boxes_dispatched=8`, `boxes_pending=8`, `overall_status="Partially Dispatched"` — the exact 20/12/8 case from the design doc.

- [ ] **Step 6: Multiple dispatches for one order**

Continuing Step 5's item, Dispatch the remaining 4 ready boxes in a second, separate Dispatch action. Verify two distinct `Chalan` documents now exist for this PO (two entries in the Dispatch List, two downloadable PDFs, each containing only its own dispatch's line item — never the whole order), and the item's `boxes_dispatched` is now 12 with `boxes_pending` still 8 (never touched).

- [ ] **Step 7: Direct dispatch (skip Ready)**

On a different item that has never been marked Ready, Dispatch directly from Pending. Verify: a `ReadyBatch` was still created behind the scenes (`auto_created: true`, `remaining_qty: 0`) — check via `GET /tile-orders/items/{item_id}/history` — and the item's `boxes_pending` decreased by exactly the dispatched quantity with `boxes_ready` unchanged.

- [ ] **Step 8: Supplier dashboard filtering**

Open the Company tab and confirm the two suppliers' dashboards never show each other's orders — the Qutone dashboard shows only Qutone's `PurchaseOrder`s, Dimore's only Dimore's, even though both originated from the same `CustomerOrder`/quotation.

- [ ] **Step 9: Fix anything found, then re-run Steps 1-2**

If any scenario above surfaced a bug, fix it in the owning task's file (not a new ad-hoc patch), re-run that task's own test file, then re-run the full Step 1/Step 2 checks before considering this task done.

- [ ] **Step 10: Note the migration script as a deployment step, not a code step**

Confirm with the user before running `backend/scripts/backfill_tile_customer_orders.py --dry-run` against a real (staging or production) database — this plan's Task 13 only builds and unit-tests the script; actually invoking it against real data is an operational action outside the scope of "writing code," matching this project's Actions with care guidance on destructive/hard-to-reverse operations. Run `--dry-run` first, review its output with the user, then run it for real only with explicit approval.

- [ ] **Step 11: Final commit (if Step 9 produced any fixes)**

```bash
git add -A
git commit -m "fix: address issues found during six-scenario end-to-end verification"
```

If Step 9 found nothing to fix, skip this step — there is nothing to commit.
