# Ground Floor Tiles Purchase Workflow — design

Date: 2026-07-22
Status: approved by user, pending implementation plan

## Background

Buildcon House's Ground Floor → Tiles module (added 2026-07-22, see
`buildcon-house-project` memory) has quotation/selection document builders,
but no dedicated tracking for how a tile order physically moves from supplier
to customer. The general Purchases module already tracks purchase orders
(`PurchaseOrder`/`PurchaseOrderItem`) through a 6-stage warehouse-handling
pipeline (`order_in_company → company_billing → in_box → dispatched →
in_transit → delivered`), but that pipeline models physical handling steps
generic to any floor's purchases — it has no concept of a Chalan (factory
release proof document), no optional Godown routing, and no per-batch partial
release. This spec adds a **new, coarser stage workflow specific to the
tile-order delivery lifecycle**, layered on top of the existing
`PurchaseOrder` record (no new order documents, no changes to the existing
6-stage tracker).

**Explicit non-goal:** do not redesign or modify the existing Purchases
module (`purchases_tracker.py`'s Material Tracker, PO status state machine in
`purchase_routes.py`, or the `_handle_order_placed` automation). This is a
new, additive layer.

## Scope decision

The new stage/chalan fields live directly on `PurchaseOrder` (generic, not
tiles-specific in the data model), but the new UI entry points (Customer-wise
/ Company-wise order views) are surfaced only under Ground Floor → Tiles for
now. This keeps the implementation focused on tiles per the user's brief,
while leaving the door open to reuse the same fields for sanitary/marble/
granite purchase workflows later without a schema change.

## Data model

### `Chalan` (new, embedded — not a separate collection)

A tile order's material can be released from the factory in multiple
batches, each producing its own Chalan. Embedding on `PurchaseOrder` (rather
than a `chalans` collection) keeps "one order = one document, no duplicate
order records" true — there is nothing to keep in sync because there is only
one document.

```python
class ChalanLineItem(BaseModel):
    po_item_id: str          # references PurchaseOrderItem.id this batch covers
    name: str
    size: Optional[str] = None
    qty: float
    unit: str = "Box"        # "Box" | "PCS" — free text, printed as-is

class Chalan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    number: str                              # "CH-1052", atomic via services/sequence.py (kind="chalan", prefix="CH")
    created_at: str = Field(default_factory=now_iso)
    created_by: str
    created_by_name: str
    items: list[ChalanLineItem]
    reference_number: Optional[str] = None
    receiver_name: Optional[str] = None      # printed on PDF; signature is a blank line for physical pen-signing
    sender_name: Optional[str] = None        # "Supplier Representative"
    stage: Literal["released", "at_godown", "dispatched"] = "released"
    godown_received_at: Optional[str] = None
    godown_received_by: Optional[str] = None
    godown_received_by_name: Optional[str] = None
    dispatched_at: Optional[str] = None
    dispatched_by: Optional[str] = None
    dispatched_by_name: Optional[str] = None
    dispatch_note: Optional[str] = None
    pdf_storage_key: Optional[str] = None    # Supabase private bucket, same pattern as PurchaseAttachment.storage_key
```

### `PurchaseOrder` gains one field

```python
chalans: list[Chalan] = []
```

No new top-level stage field is stored. The order's customer-facing stage is
**computed** from `chalans` + existing `items`, every time it's read:

- `order` — no chalans yet, or cumulative released qty (across all
  non-cancelled chalans, per `po_item_id`) doesn't yet cover every
  `PurchaseOrderItem.qty` on the order.
- `material_released` — every item's qty is fully covered by chalans, but the
  weakest-link chalan (see below) is still `released`.
- `godown` — the weakest-link chalan is `at_godown`.
- `dispatch` — the weakest-link chalan is `dispatched`, but not every chalan
  is `dispatched` yet.
- `completed` — every chalan is `dispatched`.

"Weakest-link chalan" = the chalan with the least-advanced `stage`, ranked
`released < at_godown < dispatched`. This is what drives the single 4-node
progress bar shown in both Customer-wise and Company-wise views, alongside a
supporting per-chalan breakdown (e.g. "2 of 3 batches dispatched") in the
order detail view — since Godown/Dispatch are tracked per batch (per your
explicit choice), a single order can have batches at different points
simultaneously; the rollup above is what collapses that into one customer-
facing indicator without losing the per-batch detail underneath.

**Visibility**: an order appears in the Customer-wise/Company-wise views the
instant it's placed — while `PurchaseOrder.status` is still `draft`, before
staff review — showing stage `Order`. This is unchanged from, and relies
entirely on, the existing `_handle_order_placed` automation already writing
the `PurchaseOrder` synchronously when a quotation's status becomes
`ordered`. The new views query `db.purchase_orders` live, with no cache or
projection in between, so nothing needs a separate sync step for an order to
show up or for one view to reflect the other view's changes.

**Godown is skippable, not a pre-selected route**: no upfront "Route A vs
Route B" field. A chalan simply progresses `released → dispatched` directly,
or `released → at_godown → dispatched`, depending on which action staff
actually take. The route is a fact recorded after it happens, not a decision
made in advance.

## Backend endpoints

Added to `backend/routes/purchases_tracker.py` (same file as the existing
Material Tracker, since this is the natural home for order-lifecycle
actions), reusing existing patterns already in that file (`floor_query`,
`log_event`, `_sync_po_status_with_stages`-style helpers):

- `POST /purchases/{po_id}/chalans` — body: list of `{po_item_id, qty}` to
  release this batch (form pre-fills each item's remaining unreleased qty as
  the default) + reference_number/receiver_name/sender_name. Allocates a
  `CH-` number via `services/sequence.py::next_number(kind="chalan",
  prefix="CH", collection="purchase_orders", width=4)`, generates the PDF,
  uploads to the private Supabase bucket, logs `chalan.generated` via
  `log_event`, notifies (see below).
- `POST /purchases/{po_id}/chalans/{chalan_id}/godown-received`
- `POST /purchases/{po_id}/chalans/{chalan_id}/dispatch` — body: optional
  `dispatch_note`. If this is the last outstanding chalan, notifies "Your
  tile order has been dispatched."
- `GET /purchases/{po_id}/chalans/{chalan_id}/pdf` — streams the generated
  PDF (or regenerates from stored data if not yet persisted — mirrors the
  existing quotation-PDF pattern).
- `GET /purchases/orders/customer-view` — order-card-shaped rows grouped by
  customer, floor-scoped, joined against `customers` for phone number
  (not denormalized on `PurchaseOrder` today).
- `GET /purchases/orders/company-view` — order-card-shaped rows grouped by
  `supplier_id`/`supplier_name`.

## Chalan PDF

New `backend/pdf_chalan.py`, modeled directly on the existing
`backend/pdf_tiles.py` — reuses the Buildcon logo asset and the already-
solved ₹-glyph font fallback (Georgia on macOS / DejaVuSans on Linux, though
a delivery chalan has no currency figures, so this mostly matters if line
notes ever include pricing).

Layout, per spec:
- Centered Buildcon House logo header.
- Header block: Chalan Number, Date, Customer Name, Supplier Name, Phone
  (optional), Reference Number.
- Product table: Sr No, Tile Name, Tile Size, Quantity, Unit.
- Footer: Receiver Name + blank signature line; Sender/Supplier
  Representative + blank signature line (physical pen-signature lines on the
  printed page, matching how paper chalans are actually signed in person —
  not a digital capture flow).
- Buildcon House footer details.
- A4 print-optimized layout, matching the existing tiles PDFs.
- Filename: `CH-1052 Nileshbhai Pokiya 22-07-2026.pdf` (chalan number +
  customer name + date), delivered via the existing `openApiFile`/blob-URL
  helper (`src/utils/downloadFile.ts`) already used for quotation PDFs —
  avoids the `data:`-URL Chrome navigation block fixed 2026-07-20.

## Frontend

One new page, not two separate modules — reinforces "two views of the same
order." New tiles-nav entry ("Tile Orders") in `frontend/app/(admin)/
_layout.tsx`'s `tilesNav` array, linking to a new `/(admin)/tiles/orders`
route with a Customer-wise / Company-wise toggle at the top (same tab
pattern already used in `purchases.tsx`'s view selector).

- **Customer-wise tab**: order cards — Customer Name, Mobile, Order Number,
  Supplier, Current Stage, 4-dot progress indicator (Order / Material
  Released / Godown / Dispatch, with Godown shown but visually skipped if
  unused), Total Products, Total Value.
- **Company-wise tab**: grouped by supplier with a count header (e.g.
  "Kajaria — 12 Orders"), each order row showing its stage plus an inline
  "Generate Chalan" action when the order still has unreleased quantity,
  matching the example layout in the original brief.
- Both cards open a shared order detail view: full per-chalan breakdown
  (each chalan's items/stage/PDF link), the "Release Material" action (opens
  the Generate Chalan form), Godown/Dispatch action buttons per chalan, and
  the timeline.

## Timeline

Reuses `backend/services/activity_log.py` (`log_event`/`timeline_for`),
already used across the app for quotations/POs — no new logging
infrastructure. New event types: `chalan.generated`, `chalan.godown_received`,
`chalan.dispatched`. Order-placed is already logged today by the existing
automation; no change needed there.

## Notifications

Uses the existing in-app-only `notify()`/`notify_many()`
(`backend/services/notifications.py`) — no new channel. Recipients: the
order's `created_by` and `assigned_to` (the staff actually handling that
customer relationship), not a floor-wide broadcast.

- On chalan generation: "Material has been released by the supplier."
- On the last outstanding chalan reaching `dispatched` (i.e. the whole order
  is now `completed`): "Your tile order has been dispatched."

## Testing

Mirrors the existing pattern (`backend/tests/unit/` — call route-wired
dependencies directly, no live server needed, per
`test_purchases_move_permissions.py`):

- Stage-rollup computation: unit tests covering every combination of chalan
  states (no chalans / partially released / fully released single chalan /
  multiple chalans at different stages / all dispatched) against the
  `order/material_released/godown/dispatch/completed` derivation.
- Partial-release math: cumulative qty-per-item across multiple chalans
  correctly determines "fully released."
- Floor scoping: a regression test confirming `customer-view`/`company-view`
  respect floor scoping the same way the rest of the Purchases module does.

## Out of scope for this pass

- No changes to the existing 6-stage Material Tracker, PO status state
  machine, or `_handle_order_placed` automation.
- No digital signature capture — Chalan signatures are physical pen
  signatures on the printed PDF.
- No SMS/WhatsApp/push notifications to the actual customer — notifications
  are in-app, to staff only, matching the existing notification system.
- No upfront route selection (direct vs. via-godown) — always recorded after
  the fact via the skippable Godown action.
- Extending this workflow to sanitary/marble/granite categories — the data
  model is generic enough to support it later, but no other floor's UI is
  touched in this pass.
