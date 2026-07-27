# Quotation Tiles: unified selection → quotation → confirmation → order workflow

Date: 2026-07-27
Status: approved by user, pending implementation plan
Sub-project: B of 3 (Floor isolation → **Tiles workflow revamp** → Sales Data page), per `2026-07-26-builder-floor-hard-lock-design.md`.

## Background

Ground Floor Tiles today has three separate sidebar entries — **Tiles
Selection**, **Tiles Quotation**, **Tile Orders** — each a standalone screen.
Selection and Quotation are two unrelated documents a rep creates from
scratch every time (no list, no link between them); Place Order only exists
on the Quotation builder and jumps straight to the shared
place-order/preview → confirm flow.

Two real defects in that place-order automation were found and fixed
earlier in this session (see memory `order-placement-payment-idempotency-bug`
for full detail — not repeated here):

1. Every order placed after the very first one ever recorded crashed with a
   Mongo `DuplicateKeyError` on `payments.payment_idempotency_key`, rolling
   back the Purchase Order(s) too. Fixed in `_handle_order_placed`,
   `handle_purchase_transferred`, and `create_payment`.
2. Placing an order on a ₹0 quotation crashed on `Payment.amount`'s
   `Field(gt=0)` constraint. Fixed by skipping Payment creation entirely
   when the order total is ≤0.

Both fixes are live; 3 real quotations that were permanently stuck
(`dead_letter`) from these bugs have been recovered (FQ-2026-0080/0082/0084 —
all now have their real Purchase Orders, and Payments where the total is
non-zero). This spec is the follow-up feature work those fixes unblocked.

## Decision: one document, two doc_types, no new fields

A Selection and its eventual Quotation are **the same underlying
`Quotation` document** — same `id`, same document number, from creation
through order placement. No new schema field, no migration, no separate
collection.

```
doc_type=tiles_selection          doc_type=tiles_quotation
  draft                             draft            (pricing gets filled in)
  → pending_approval                → pending_approval
  → approved  ──[Move to Quotation]──┘
                                    → approved         (= "Confirmation")
                                    → ordered           (existing automation)
```

- **Selection stage**: rep picks products, optionally fills `rate_sqft` per
  item (the only price field the Selection paper collects). Submits for
  approval (`pending_approval`); a manager/owner approves it
  (`status=approved`, `approved_by` stamped) — the exact same mechanic the
  standard quotation flow already has, same role gate
  (`require_min_role("sales")`, i.e. anyone who could edit the document to
  begin with — no new permission tier).
- **"Move to Quotation" button**: appears only once `doc_type=tiles_selection`
  and `status=approved`. Calls a new dedicated endpoint,
  `POST /quotations/{id}/move-to-quotation` — `QuotationUpdate` (the generic
  PATCH body) has no `doc_type` field today and never has (create-only,
  immutable via PATCH), and a purpose-built endpoint can enforce the
  `tiles_selection`+`approved` precondition server-side in one atomic call,
  matching the existing pattern of dedicated action endpoints
  (`/place-order/confirm` is the same shape). It flips
  `doc_type → "tiles_quotation"` and resets `status → "draft"`. **This is a
  metadata-only change** — `items` (which
  products, qty, area, size, and any `rate_sqft` already entered) is not
  touched, so everything already filled in at Selection carries over
  automatically; every field the Selection stage never collects
  (`rate_box`/`unit_price`, `total_box` qty, `pcs_per_box`) is simply absent
  from those line items already and stays open for the rep to fill in during
  the Quotation stage. No transform/copy step, because there's nothing to
  copy — it's the same array.
- **Quotation stage — "Confirmation"**: rep finishes pricing, submits for
  approval again (`pending_approval → approved`). Reaching `approved` while
  `doc_type=tiles_quotation` **is** the Confirmation stage the user asked
  for — an internal recheck before committing to Purchase Orders, no
  customer involved. "Place Order" (already built, already fixed) only
  renders once `approved`.
- **Order stage**: unchanged — existing `/place-order/preview` +
  `/place-order/confirm` flow, `status → "ordered"`.

**Why not a dedicated `stage` field instead of deriving it from
`(doc_type, status)`?** Considered and rejected: it would need a migration,
and — more importantly — this exact codebase has repeatedly been bitten by
denormalized fields drifting out of sync with their source of truth (floor_id
mistagging, the tiles image-dedup guard, both fixed in the last two weeks).
A single shared helper, `stageOf(doc_type, status)`, used by both the
frontend and backend, is the only place this mapping lives — it returns the
label (`"Selection — Awaiting approval"`, `"Quotation — Confirmed"`, etc.)
and which actions are currently available. Zero new failure mode.

**Selections structurally never reach Payments.** Already true today —
"Place Order" only renders for `doc_type=tiles_quotation` (see
`TilesDocBuilder.tsx`'s topbar), so a Selection can never call
`place-order/confirm`, the only thing that ever creates a Payment. Nothing to
change here; just don't regress it while rebuilding the topbar/nav.

## Nav & list: one "Quotation Tiles" tab

Replaces the **Tiles Selection** and **Tiles Quotation** sidebar links with a
single **Quotation Tiles** entry. **Tile Orders stays exactly as-is, its own
separate nav item** — untouched, not absorbed.

The new tab is a list screen (new — neither existing tiles route has one
today; each is just a bare builder). Backed by the existing
`GET /quotations` (already returns these documents, floor-scoped, just never
had a filtered view) filtered client-side (or via a new `doc_type` query
param, whichever the plan finds cleaner) to `tiles_selection` /
`tiles_quotation`. Each row shows customer, number, stage badge (via
`stageOf`), total, updated date. Two buttons at the top:

- **Create new selection** — opens a blank Selection builder (today's
  behavior, just reached from here instead of the old sidebar link).
- **Create new quotation** — opens a blank Quotation builder directly. This
  stays independent of promotion — a rep can still start a Quotation from
  scratch without ever creating a Selection first.

Clicking an existing row opens the same `TilesDocBuilder` component that
exists today, in whichever mode (`SelectionPaper`/`QuotationPaper`) matches
its current `doc_type` — no new builder UI, just a new way to reach a
specific saved document.

## Customer + product history (both surfaces)

- **Customer detail page**: new "Tile history" section listing every
  Selection/Quotation for that customer (any stage), clickable to reopen in
  the builder. `GET /quotations` today has no `customer_id` filter (it
  returns everything the caller's floor scope allows) — needs a new query
  param, restricted server-side to the two tiles doc_types.
- **Product picker inline hint**: when a rep picks a product for a customer
  who's had that exact product on a past Selection/Quotation, show what was
  used last time (rate, size) with a one-tap "use previous" fill. New small
  backend lookup: given `customer_id` + `product_id`, most recent matching
  line item across that customer's tiles documents, any stage.

## Tile images: horizontal everywhere

Standardize the image frame to a landscape aspect ratio in the 2 places that
actually need it (verified against the real code, not assumed): Catalog
cards and the on-screen builder's photo cell (`TileRow.image`). **The PDF
needs no change** — `pdf_tiles.py`'s photo cell already uses a landscape
bounding box (41×24mm on the Quotation table, 24×16mm on the Selection
table, both via the shared `_img()` helper in `pdf_generator.py`) that
proportionally fits the source photo inside it without stretching; that's
the correct behavior already. **Not** the product picker —
`TilesProductPicker.tsx` is deliberately text-only, no thumbnails, by
existing design (its own header comment: kept fast/scannable since the
printed document already carries the photo) — nothing to change there.

Catalog's image container (`imageWrap`, `aspectRatio: 1`) is one shared
style used by every product card regardless of floor — sanitaryware and
tiles alike. Changing it outright would also reshape sanitaryware cards,
which nobody asked for. `Product.floor_id` is already present on every
catalog API response (projection only excludes `_id`) even though the
frontend `Product` type doesn't declare it yet — the fix is per-card:
add `floor_id` to the type, and apply the landscape frame only when a
card's own product has `floor_id === "ground-floor"`. This also makes the
fix correct in owners'/managers' "All floors" merged view, not just when
Ground Floor is the sole active floor.

Purely a container/aspect-ratio fix — no image re-processing, no dependency
on the new tile designs the user will provide later (explicitly out of
scope until then).

## Explicitly not changing

- Tile Orders (Chalan/material-release tracking) — separate feature, own
  nav item, own screens. Not touched.
- The order-placement automation's internals beyond the two bug fixes
  already shipped this session.
- Any new tile product designs — user will provide these separately; this
  spec only fixes existing image *layout*, not image *content*.
- No new permission tier for "approve" — reuses the existing
  `require_min_role("sales")` gate already on quotation writes.

## Testing

- `stageOf(doc_type, status)` helper: table-test every combination, both
  frontend (TS) and backend (Python) implementations agree.
- Backend: promoting a Selection to Quotation only ever changes `doc_type`
  and `status` — items array byte-for-byte identical before/after (guards
  against an accidental copy/transform creeping in later).
- Backend: "Move to Quotation" rejected (400) unless
  `doc_type=tiles_selection` and `status=approved`.
- Backend: customer+product history lookup returns the most recent match
  only, scoped to that customer, across both tiles doc_types.
- Frontend: new Quotation Tiles list renders both doc_types with correct
  stage badges; Create new selection / Create new quotation both land on a
  blank builder; clicking a row reopens the right paper.
- Live verification: full round-trip — create selection, approve, move to
  quotation, fill pricing, confirm, place order — confirm PO+payment appear
  exactly as today's (already-fixed) automation produces them.

## Rollout

No schema change, no data migration, no change to any endpoint's contract
for existing standard (non-tiles) quotations. Existing Selection/Quotation
documents already in the live DB (`floor_id=ground-floor`,
`doc_type` already `tiles_selection`/`tiles_quotation`) work with the new
list/history views immediately — nothing needs backfilling.
