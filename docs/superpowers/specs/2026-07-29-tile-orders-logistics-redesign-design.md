# Ground Floor Tiles — Tile Orders Logistics Redesign

Date: 2026-07-29
Status: approved by user, pending implementation plan

## Background

The Ground Floor → Tiles → Tile Orders module already has a working
dispatch/chalan system, shipped 2026-07-22
(`docs/superpowers/specs/2026-07-22-ground-floor-tiles-purchase-workflow-design.md`):
`PurchaseOrder` already splits one quotation into one PO per brand
(`_handle_order_placed` in `backend/services/domain_outbox.py`), `Supplier`
is brand-scoped, a full `Chalan` model is embedded on `PurchaseOrder` with
PDF generation, atomic numbering, and audit logging, and
`/purchases/orders/customer-view` / `/company-view` already exist.

This is **not a rebuild**. It's a targeted redesign of the stage model and
views to match Buildcon House's real operational workflow, keeping the
mature parts (Mongo transactions, CAS concurrency, RBAC, floor scoping,
activity log, PDF machinery, brand-split PO creation) and replacing/adding:

- brand/supplier grouping not surfaced on order cards (the "mixing brands"
  complaint)
- no unified "one card = one customer order" view aggregating across brands
- no distinct "Ready For Pickup" stage before dispatch/chalan
- no standing Dispatch List register (only per-order chalan breakdown exists)
- no explicit per-line box counters (derived by summing chalan quantities,
  not stored)
- terminology mismatch: old model's "released"=leaves factory,
  "dispatched"=reaches customer; new model's "Dispatch"=leaves supplier,
  "Delivered"=reaches customer (future)

**Explicit decision**: keep `CustomerOrder`/`PurchaseOrder`/`Supplier`/`Brand`
as the business/data layer exactly as they are; replace the Chalan-derived
stage machine and views with a new model where box counts and stored
per-line fields are the source of truth.

## Data model

### `customer_orders` (new collection)

The customer-facing aggregation root. One per "Place Order" event —
decoupled from `quotation_id` so future re-orders/amendments don't need to
be shoehorned onto the original quotation.

```python
class CustomerOrderBrand(BaseModel):
    brand_id: str
    brand_name: str
    supplier_id: str
    supplier_name: str
    purchase_order_id: str
    status: str  # kept in sync with that PO's overall_status

class CustomerOrderDashboardSummary(BaseModel):
    # Cached read-model for the Customer tab, refreshed transactionally on
    # every child write — avoids recomputing completion/status live on every
    # dashboard load. `waiting_days` is deliberately NOT part of this cache
    # (see Ageing below) since it depends on "today," not on order state.
    completion_percentage: float
    overall_status: str
    supplier_statuses: list[dict]   # [{supplier_name, status}], mirrors brands[]

class CustomerOrder(BaseModel):
    id: str
    number: str                    # "TORD-2026-0001", via services/sequence.py
                                    # ("T" prefix keeps Tile Orders distinct from
                                    # any future non-tile CustomerOrder module)
    version: int = 0                # optimistic-locking counter, incremented on
                                     # every aggregation update — guards against
                                     # concurrent writes from sibling POs updating
                                     # the same CustomerOrder simultaneously
    quotation_id: str
    quotation_number: str
    customer_id: str
    customer_name: str
    customer_phone: str
    # Immutable delivery snapshot captured at placement time — never re-read
    # from the live customer record afterwards, so an old Chalan/order never
    # shows an address the customer later changed to.
    delivery_name: str
    delivery_phone: str
    delivery_address: str
    delivery_city: str
    delivery_pincode: str
    delivery_state: str
    floor_id: str
    created_at: str
    created_by: str
    created_by_name: str
    brands: list[CustomerOrderBrand]
    # Cached rollups, recomputed transactionally on every child write
    total_products: int
    total_boxes: int
    total_value: float
    overall_status: str             # furthest-progress across child POs
    completion_percentage: float    # boxes_dispatched / boxes_ordered * 100
    dashboard_summary: CustomerOrderDashboardSummary
    last_activity: str               # short label, e.g. "Dispatch created"
    last_activity_at: str
    # waiting_days computed live at read time (today - created_at), never stored
    is_deleted: bool = False
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None
```

### `purchase_orders` (existing, extended)

Unchanged brand-split model. Adds:

- `customer_order_id: str` — backref. New orders always set this; existing
  orders remain unlinked until the backfill migration runs (see Migration).
- Rollup fields (cached, recomputed transactionally): `ready_boxes`,
  `pending_boxes`, `dispatched_boxes`, `latest_ready_date`,
  `latest_dispatch_date`, `overall_status`, `completion_percentage`,
  `last_supplier_activity_at` (bumped by every `ready_batch.created`,
  `dispatch.created`, `chalan.generated`, `dispatch.godown_received`,
  `dispatch.delivered` event on this PO — drives `supplier_silent_days` on
  the Company/Supplier dashboards, decoupled from plain order age).
- `chalans: []` embedded array is **retired** from active use — Chalan
  becomes its own top-level collection (below). The field stays on old
  documents (dead, unread by new code) rather than being dropped.

### `PurchaseOrderItem` (existing, extended)

Denormalized tile fields copied from the quotation line item at
order-placement time: `series`, `finish`, `sku`, `tile_size`,
`pieces_per_box` (sourced from `QuotationLineItem.size`/`pcs_per_box`,
already present on that model).

Box counters — real stored fields, invariant held at all times:
`boxes_ordered = boxes_ready + boxes_dispatched + boxes_pending`.

- `boxes_ordered` — fixed at PO creation (= existing `qty`)
- `boxes_ready` — sum of *remaining* qty across this item's active
  `ReadyBatch` rows (shrinks as Dispatches consume them)
- `boxes_dispatched` — cumulative qty across all Dispatches against this item
- `boxes_pending` — `boxes_ordered − boxes_ready − boxes_dispatched`
  (never touched yet)

Status fields:

- `current_location: Pending|Ready|Dispatched|Godown|Delivered` — cached,
  derived by furthest-progress precedence (`Delivered > Godown > Dispatched
  > Ready > Pending`), recomputed transactionally on every Ready/Dispatch/
  Godown/Delivered write to this item. Decoupled from `overall_status`: a
  fully-dispatched item can have `current_location = Buildcon Godown` while
  its `overall_status` is `Dispatched`, because Godown is a location, not a
  milestone.
- `overall_status: Pending|Ready|Partially Dispatched|Dispatched|Delivered`
  — the milestone ladder (see Status derivation below).

### `ready_batches` (new collection)

One immutable record per "Mark Ready" event (bulk or single-line).

```python
class ReadyBatch(BaseModel):
    id: str
    batch_number: str          # "RB-2026-0001", via services/sequence.py
    purchase_order_id: str
    po_item_id: str
    customer_order_id: str
    supplier_id: str
    supplier_name: str
    customer_id: str
    customer_name: str
    tile_name: str
    series: Optional[str]
    finish: Optional[str]
    size: Optional[str]
    sku: Optional[str]
    qty: float
    remaining_qty: float       # decrements as Dispatches consume it
    created_at: str
    created_by: str
    created_by_name: str
    auto_created: bool         # true for behind-the-scenes batches from direct dispatch
    is_deleted: bool = False
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None
```

### `dispatches` (new collection)

One record per Dispatch action.

```python
class DispatchLineConsumed(BaseModel):
    ready_batch_id: str
    po_item_id: str
    qty: float

class DispatchAttachment(BaseModel):
    # No UI this pass — field exists so LR copies / transport receipts /
    # vehicle photos / POD can attach later without a migration.
    type: str
    url: str
    uploaded_by: str
    uploaded_at: str

class Dispatch(BaseModel):
    id: str
    dispatch_number: str        # "DSP-2026-0001", via services/sequence.py
    purchase_order_id: str
    customer_order_id: str
    supplier_id: str
    supplier_name: str
    customer_id: str
    customer_name: str
    ready_batches_consumed: list[DispatchLineConsumed]
    destination_type: Literal["Customer", "Godown"]
    destination_name: str
    destination_address: str
    destination_city: str
    dispatch_date: str
    dispatch_time: str
    created_by: str
    created_by_name: str
    chalan_id: str              # 1:1, always set (Chalan generated in the same transaction)
    godown_received_at: Optional[str] = None
    godown_received_by: Optional[str] = None
    delivered_at: Optional[str] = None    # future — modeled now, no action/UI this pass
    delivered_by: Optional[str] = None
    attachments: list[DispatchAttachment] = []
    inventory_transaction_id: Optional[str] = None   # unused today — future
                                                      # inventory-module hook,
                                                      # no migration needed later
    is_deleted: bool = False
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None
```

### `chalans` (promoted out of the embedded array into its own collection)

**Immutable** — no update endpoint exists, ever. A correction always means a
new Dispatch + new Chalan; `CH-001` is never edited. Enforced at the route
layer (no PATCH route wired), not just by convention.

```python
class ChalanItem(BaseModel):
    po_item_id: str
    tile_name: str
    series: Optional[str]
    finish: Optional[str]
    size: Optional[str]
    sku: Optional[str]
    boxes: float
    pieces_per_box: Optional[int]
    quantity: float

class Chalan(BaseModel):
    id: str
    number: str                 # "CH-0001", same services/sequence.py pattern as today
    dispatch_id: str            # 1:1
    purchase_order_id: str
    customer_order_id: str
    supplier_name: str
    supplier_contact: Optional[str]
    supplier_address: Optional[str]
    customer_name: str
    customer_phone: str
    # delivery snapshot copied from the Dispatch/CustomerOrder at generation
    # time — never re-reads the live customer record
    delivery_address: str
    delivery_city: str
    reference_number: Optional[str]
    items: list[ChalanItem]      # only this dispatch's quantities, never the whole order
    receiver_name: Optional[str]
    sender_name: Optional[str]
    vehicle_number: Optional[str] = None   # future-ready, optional
    driver_name: Optional[str] = None      # future-ready, optional
    created_at: str
    created_by: str
    created_by_name: str
    # immutable generation metadata, printed on the PDF for audit purposes
    generated_at: str
    generated_by_name: str
    system_version: str          # e.g. "BuildCon ERP v2"
    is_deleted: bool = False
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None
```

## Status derivation, ageing, completion

### `overall_status` (milestone ladder — item / PO / CustomerOrder)

Furthest-progress rollup, same philosophy as the proven 2026-07-22 rollup,
now driven by stored box counters instead of embedded chalan state:

- `Pending` — `boxes_ready == 0 and boxes_dispatched == 0`
- `Ready` — `boxes_ready > 0 and boxes_dispatched == 0`
- `Partially Dispatched` — `0 < boxes_dispatched < boxes_ordered`
  (regardless of how the remainder splits between ready/pending — e.g. 20
  ordered / 12 marked ready / 8 dispatched → status `Partially Dispatched`,
  with `boxes_ready=4`, `boxes_dispatched=8`, `boxes_pending=8` shown
  alongside so "partially ready" vs. "partially dispatched" is never lost)
- `Dispatched` — `boxes_dispatched == boxes_ordered`
- `Delivered` — every Dispatch against this item is Delivered

PO- and CustomerOrder-level `overall_status` roll up their children the same
way (furthest progress across items / across POs). `CustomerOrder.brands[]`
entries mirror their PO's `overall_status`.

### `current_location` (separate axis, decoupled from the ladder)

`Pending|Ready|Dispatched|Godown|Delivered` — physical location, not
milestone. Godown is explicitly *not* part of the status ladder: a shipment
can be `overall_status=Dispatched` + `current_location=Buildcon Godown`
simultaneously, since the material has already left the supplier and is
simply waiting at Buildcon's own warehouse before final delivery.

### Ageing

`waiting_days = today − customer_orders.created_at`, computed live, never
stored. Bands: 0–7 green, 8–14 amber, 15+ red — applied identically on
Customer cards, Company landing counts, and Supplier dashboard rows (sorted
oldest-first).

`supplier_silent_days = today − purchase_orders.last_supplier_activity_at`
(falls back to `created_at` if no supplier activity yet) — surfaced on
Company/Supplier dashboards to distinguish "old but the supplier worked on
it yesterday" from "old and silent."

### Completion

`completion_percentage = boxes_dispatched / boxes_ordered × 100`, box-weighted
(not count-weighted), computed at item / PO / CustomerOrder level.

### Timeline (activity log)

Extends the existing `backend/services/activity_log.py` (`log_event`/
`timeline_for`) — no new infrastructure. New event types: `customer_order.created`,
`supplier.assigned` (fired immediately alongside each child PO's creation —
supplier resolution is automatic per brand, not a separate manual step),
`ready_batch.created`, `dispatch.created`, `chalan.generated`,
`dispatch.godown_received`, `dispatch.delivered`, `status.changed`
(`{from, to}`, fired whenever the ladder value moves). Every `log_event`
call for a `customer_order`-scoped event also updates
`customer_orders.last_activity`/`last_activity_at`.

## Backend endpoints

New router, `backend/routes/tile_orders.py` (mounted at `/tile-orders`),
reusing existing dependencies (`floor_query`, `require_min_role`, `log_event`,
`services/sequence.py`, the CAS/transaction patterns from
`purchases_tracker.py`).

**Order placement** — extends existing `place_order_confirm` /
`_handle_order_placed` (`backend/services/domain_outbox.py`): creates one
`CustomerOrder` (snapshotting delivery info from the customer record at that
moment) before the existing per-brand `PurchaseOrder` fan-out; each new PO
gets `customer_order_id` and fires `supplier.assigned`.

- `GET /tile-orders/suppliers` — one row per supplier: name, active-order
  count, `max(supplier_silent_days)` across that supplier's active orders
  (sorted most-stalled first)
- `GET /tile-orders/suppliers/{supplier_id}/orders?page=&page_size=&sort=&status=&search=`
  — that supplier's POs only, sorted oldest-waiting-first by default;
  includes a KPI summary (orders / pending / ready / partially dispatched /
  completed / oldest-pending-days / boxes pending / boxes ready / boxes
  dispatched — tile businesses think in boxes as much as order counts) for
  the dashboard's KPI bar
- `GET /tile-orders/suppliers/{id}/analytics` — orders, waiting, oldest
  pending, completion %, and supplier-scorecard timing metrics: average
  ready time (order → first Ready), average dispatch time (Ready → Dispatch),
  average total fulfilment time (order → fully Dispatched)
- `GET /tile-orders/purchase-orders/{po_id}` — item box breakdown + `current_location`
- `POST /tile-orders/purchase-orders/{po_id}/ready` — body `{items:
  [{po_item_id, qty}, ...]}`, bulk, one transaction: creates one `ReadyBatch`
  per line, bumps `boxes_ready`/`boxes_pending`, recomputes
  `current_location`/`overall_status`, logs `ready_batch.created` +
  `status.changed` where applicable
- `POST /tile-orders/purchase-orders/{po_id}/dispatch/preview` — body:
  list of `{po_item_id, ready_batch_id | null, qty}` (`null` batch = direct
  from pending) + `destination_type/name/address/city`. Non-mutating;
  returns the would-be creation chain (`Dispatch DSP-2026-0004 → Chalan
  CH-2026-0032 → Dispatch List entry`), product/box breakdown, and any
  warnings (e.g. over-consuming a batch), plus remaining-pending after the
  action — so staff see exactly what gets created before confirming
- `POST /tile-orders/purchase-orders/{po_id}/dispatch` — same body, commits:
  auto-creates a `ReadyBatch` (`auto_created=true`) for any line dispatched
  directly from pending, consumes the referenced batches, creates the
  `Dispatch` and its immutable `Chalan` in the same transaction, bumps
  counters, logs `dispatch.created` + `chalan.generated` + `status.changed`
- `POST /tile-orders/dispatches/{dispatch_id}/godown-received`
- `POST /tile-orders/dispatches/{dispatch_id}/delivered` (future — modeled
  now, no UI/action wired this pass)
- `GET /tile-orders/chalans/{chalan_id}/pdf` — streams PDF from the
  immutable `Chalan` doc; pure read, no regeneration-drift risk
- `GET /tile-orders/customer-orders?page=&page_size=&sort=&status=&search=`
  — Customer tab card list
- `GET /tile-orders/customer-orders/{id}` — detail: summary card (order #,
  customer, date, brand count, products, boxes, `completion_percentage`,
  `waiting_days`, `overall_status`) followed by supplier-grouped product
  lines via `brands[]`
- `GET /tile-orders/customer-orders/{id}/timeline` — full logistics history
  for that order
- `GET /tile-orders/items/{item_id}/history` — one tile line's full
  lifecycle (ordered → ready → dispatch → godown → delivered)
- `GET /tile-orders/dispatches?supplier=&customer=&brand=&status=&from=&to=&destination=&search=&page=&page_size=&sort=`
  — Dispatch List register: flattened line-item rows from `dispatches` +
  `chalans`, columns: Dispatch #, Chalan #, Customer, Supplier, Tile Name,
  Size, Boxes, Dispatch Date, Destination, delivery-progress status
  (Dispatched / at Godown / Delivered) + current location
- `GET /tile-orders/dashboard` — one consolidated payload: customer orders,
  supplier orders, dispatched today, pending, ready, waiting >15 days,
  delivered today, boxes ordered/pending, revenue

All list endpoints support `page`/`page_size`/`sort`/`status`/`search` as
first-class parameters from the start. `search` is one universal field per
endpoint, matched against whichever of these are relevant to that list:
customer name, mobile, supplier name, brand name, tile name, SKU, Chalan
number, Dispatch number, Customer Order number.

## Chalan PDF

Reuses `backend/pdf_chalan.py`'s existing layout/logo/₹-font machinery,
extended per spec:

- Header: logo, Chalan #, dispatch date/time, plus a small immutable
  generation-metadata block (Generated On, Generated By, System Version —
  audit aid, not a legal document field)
- Customer block: name, mobile, delivery snapshot address/city (from
  `Chalan.delivery_address/city`, never the live customer record), reference,
  `customer_orders.number`
- Supplier block: name, contact, address
- Product table: tile name, series, finish, size, SKU, boxes, pieces/box,
  quantity — only this dispatch's items, from the immutable `Chalan.items` snapshot
- Footer: receiver/sender name + blank signature lines, transport fields
  (vehicle #, driver — blank unless supplied), Buildcon footer
- Filename unchanged: `CH-000123 Nileshbhai Pokiya 29-07-2026.pdf`

## Frontend

Reuses the existing `tiles/orders` route structure and
`TileOrderCard`/`TilesDocBuilder` component patterns.

- **Customer tab**: card list (customer, phone, order #, date, waiting days
  w/ color band, per-brand status chips, totals, `overall_status`). Detail
  page opens with a summary card (order #, customer, date, brand count,
  products, boxes, completion %, waiting days, status) before the
  supplier-grouped product lines; each line shows the 4 box counters +
  `current_location` + latest activity + timeline.
- **Company landing**: one card per supplier (name, active-order count,
  `supplier_silent_days`) — no customer orders shown here.
- **Supplier dashboard**: KPI bar (orders / pending / ready / partially
  dispatched / completed / oldest-pending-days / boxes pending / boxes
  ready / boxes dispatched) above a table of that supplier's orders only,
  sorted oldest-waiting-first.
- **Supplier order detail**: per-product box breakdown, bulk "Mark Ready"
  (multi-select), "Dispatch" opens the preview endpoint first, then commits
  on confirm.
- **New "Dispatch List" tab** under Quotation Tiles nav: filterable,
  sortable, paginated table from `GET /dispatches`, with delivery-progress
  status and current location per row so it stays useful after dispatch.

## Permissions / audit / migration / performance / testing

**RBAC** — reuses `backend/auth.py` as-is: Ready/Dispatch/Godown/Delivered
actions require `require_min_role("purchase")`; viewing the Customer tab,
Company dashboards, and Dispatch List require `require_min_role("sales")`
(read-only, matching today's pattern). Floor scoping applied on
`customer_orders.floor_id`, inherited by child POs via the existing
`floor_inherit()`.

**Audit** — all new writes call `log_event` with the event types above;
registry addition is advisory-only, matching the existing pattern.

**Migration** — feature is ~1 week old with little real data, so a one-time
best-effort backfill script (not a zero-downtime dual-write migration):
group existing `purchase_orders` lacking `customer_order_id` by
`quotation_id`, synthesize one `CustomerOrder` per group (snapshotting
whatever customer address is on file today, since no earlier snapshot
exists), copy each PO's currently-embedded `chalans[]` into the new
top-level `chalans` collection with a reconstructed `Dispatch` per chalan
(old chalans have no `ready_batches_consumed`, so each gets one synthetic
fully-consumed `ReadyBatch` marked `auto_created=true`). The old embedded
`chalans` field is left in place on old documents (dead, unread by new
code) rather than dropped.

**Rollout** — build the new backend + frontend fully, run the backfill
script against a staging copy first, verify against the six scenarios below,
then cut the frontend nav over from `/purchases/orders/customer-view` +
`/company-view` to the new pages in one deploy during a low-traffic window.
Old endpoints stay live but unlinked for a rollback window, removed in a
follow-up cleanup pass.

**Indexes**:
- `customer_orders`: `{customer_id}`, `{created_at}`, `{quotation_id}`
- `purchase_orders`: `{customer_order_id}`, `{supplier_id, overall_status}`, `{last_supplier_activity_at}`
- `ready_batches` / `dispatches`: `{purchase_order_id, po_item_id}`, `{supplier_id}`, `{customer_id}`, `{dispatch_date}`
- `chalans`: unique `{dispatch_id}`, unique `{number}`

All list/read queries filter `is_deleted: false` by default (soft delete
only — logistics records are never physically removed). `CustomerOrder`
writes go through a `version`-guarded update (read version, write with
`{version: current}` filter, retry on mismatch), the same optimistic-CAS
shape already used elsewhere in `purchases_tracker.py`, guarding against two
sibling POs updating the same `CustomerOrder` rollup concurrently.

**Test plan** (existing `backend/tests/unit` pattern — call route-wired
dependencies directly, no live server needed):
- box-counter invariant under bulk-ready + partial/direct dispatch
- the exact 20-ordered/12-ready/8-dispatched simultaneity case →
  `overall_status=Partially Dispatched`, `boxes_ready=4`,
  `boxes_dispatched=8`, `boxes_pending=8`
- multi-supplier placement → 1 `CustomerOrder` + N `PurchaseOrder`s + N
  `supplier.assigned` events
- dispatch preview never mutates state
- Chalan immutability (no PATCH route wired; a hypothetical edit attempt 404s)
- Dispatch List filter/pagination correctness
- floor-scoping regression on the new endpoints
- RBAC enforcement on all write actions
- PDF field-presence check (generation metadata block, delivery snapshot,
  dispatched-items-only)
- `CustomerOrder.version` CAS retry under two concurrent sibling-PO rollup
  updates
- soft-deleted records excluded from all list/read endpoints by default

Validated end-to-end against these six scenarios before considering the
feature complete: single-supplier order, multi-supplier order, partial
dispatch, multiple dispatches for one order, direct dispatch (skip Ready),
supplier dashboard filtering.

## Out of scope for this pass

- Delivered action/UI — data modeled (`delivered_at`, `Delivered` ladder
  value, `current_location=Delivered`) but no button/route wired to trigger
  it yet, per the original brief's "Delivered (future)."
- Digital signature capture on the Chalan — physical pen signatures on the
  printed PDF, same as today.
- SMS/WhatsApp/push notifications to the customer — in-app to staff only,
  matching the existing notification system.
- Dropping the old embedded `chalans` field or the old
  `/purchases/orders/customer-view`/`company-view` endpoints — left in
  place, unlinked, for a follow-up cleanup pass after rollout stabilizes.
