# Floor isolation fix + tile-ready catalog design

Date: 2026-07-17
Status: approved by user, pending implementation plan

## Background

Staff reported that switching from the first floor ("The Sanitary Bathroom")
to the ground floor shows the same purchase, follow-up, and other data
instead of the ground floor's own (currently empty) data. Root-cause
investigation (live DB query + full code trace, not assumptions from prior
session notes, since the repo has a large amount of uncommitted in-flight
work from a concurrent process) found two distinct, compounding bug classes.
Both are fixed with the same established pattern already used correctly
elsewhere in the codebase (`floor_query()` / `floor_for_write()` in
`backend/auth.py`, driven by the `X-Floor-Id` header the frontend already
sends correctly on every request).

**Ground truth confirmed via direct query against the live Atlas DB:** every
one of the 2,601 products, 69 follow-ups, 13 purchase orders, 12 payments, 5
customers, 41 quotations, and 5 suppliers currently in the database carries
`floor_id="first-floor"`. Zero records exist under `ground-floor` or
`second-floor`. Three real floor documents exist (`ground-floor`,
`first-floor`, `second-floor`), and the floor switcher UI works and sends the
right header. So the correct behavior today, before any fix, would be an
**empty state** on Ground floor — not first-floor data. The fact that
first-floor data shows through is entirely explained by the gaps below.

## Bug class 1 — read paths that never apply floor scoping

A specific set of endpoints discard the authenticated user
(`_: UserPublic = Depends(get_current_user)`) and query collections with no
floor filter at all, so they always return every floor's data regardless of
the selected floor.

**Purchases Tracker** (`backend/routes/purchases_tracker.py`) — the
worst-affected module, matches the user's specific complaint:
- `GET /purchases-tracker/items` (`list_items` → `_iter_items`) — the main
  tracker board. `_iter_items()` itself takes no user/floor parameter.
- `GET /purchases-tracker/stages` (`stage_catalog`)
- `GET /purchases-tracker/brands` (`brand_facets`)
- `GET /purchases-tracker/customers` (`customer_facets`)
- `GET /purchases-tracker/customers/{id}/workspace` (`customer_workspace`)
- `GET /purchases-tracker/dispatch-record`
- `GET /purchases-tracker/shortages` (`list_shortages`)
- `GET /purchases-tracker/export.xlsx`
- `GET /purchases-tracker/items/{id}` (`get_item`), `/items/{id}/transfer-history`

**Follow-ups** (`backend/routes/followup_routes.py`):
- `GET /followups/insights` — calls/WhatsApps/payments-collected/quotations-
  approved/response-rate. (Main list, `/stats`, `/mission` are already
  correctly scoped — leave those alone.)

**Reports** (`backend/routes/misc_routes.py`):
- `GET /reports/overview` — revenue by status/month, fully unscoped.

**Dashboard** (`backend/routes/dashboard_routes.py`):
- `followups_due` counter in `/dashboard/stats` scopes by `assigned_to` only,
  not floor. Minor, fix alongside the above (main dashboard query is already
  correctly scoped).

**Catalog** (`backend/routes/catalog_routes.py`,
`backend/services/catalog_service.py`) — different shape of the same root
cause, see the "Catalog" section below; folded into the same fix pass.

**Not touched:** Payments module is correctly scoped everywhere except one
minor action endpoint (`whatsapp_reminder`) that doesn't display data, just
triggers a message for an order the caller already has the ID for — low
priority, fix opportunistically but not a required part of this pass.

### Fix pattern for bug class 1

Thread `user: UserPublic = Depends(get_current_user)` (not `_`) into every
endpoint above, and apply `floor_query(user, ...)` to every query against a
floor-scoped collection. For `_iter_items()`, add a `floor_ids: list[str] |
None` parameter and fold it into the `$match` stage the same way
`purchase_routes.py`'s `/dashboard` endpoint already does it (`scope =
floor_query(user); if scope: pipeline.append({"$match": scope})`).

## Bug class 2 — write paths that never stamp floor_id on derived records

Separate from the read-side gap: several places construct a **new**
floor-scoped document without setting `floor_id` at all, so it silently
takes the Pydantic model default (`"first-floor"`) regardless of which floor
the source data actually belongs to. This matters even more going forward —
once real ground-floor (tile) quotations exist, their automatically-derived
purchase orders/payments/follow-ups would otherwise keep landing back on
first-floor, permanently re-mixing the two floors' data no matter how well
the read side is fixed.

Confirmed gaps (all found by reading every non-`**doc` construction of
`Quotation`, `PurchaseOrder`, `PurchaseShortage`, `Payment`, `Followup`
across `routes/` and `services/`; direct human-initiated creates in
`quotation_routes.py`, `followup_routes.py` manual-create,
`supplier_routes.py`, and `payment_routes.py` were checked and are already
correct):

- `services/domain_outbox.py::_handle_order_placed` — **the primary
  quotation-to-purchase-order automation.** Builds one `PurchaseOrder` per
  brand group plus a pending `Payment` whenever a quotation is placed.
  Neither carries `floor_id`. This is very likely the single biggest source
  of future cross-floor mixing: even a correctly-floor-tagged ground-floor
  quotation would spawn a first-floor purchase order and payment.
- `services/domain_outbox.py::_upsert_followup` — the follow-up created when
  a quotation PDF is generated. No `floor_id`.
- `services/followup_engine.py` — the rule-based auto-follow-up engine
  (payment-overdue, quotation-expiring, etc.). The `desired[key] = {...}`
  fields dict never includes `floor_id`.
- `services/transfer_workflow.py::handle_purchase_transferred` — the
  transactional customer-transfer workflow. Constructs a `Quotation`,
  `PurchaseOrder`, `PurchaseShortage`, `Payment`, and `Followup`, none with
  `floor_id`.
- `routes/purchases_tracker.py` inline transfer/reorder code (lines ~1075
  `auto_quotation`, ~1122 `dest_po`, ~972 shortage, ~1333 `new_po` for
  shortage-reorder) — same gap. (This looks like an older/parallel
  implementation to `transfer_workflow.py` — both need the fix regardless of
  which one is authoritative; leave the question of consolidating them for a
  separate pass, out of scope here.)
- `routes/followup_routes.py` call-back rescheduling (`nf = Followup(...)`
  around line 616) — the manual follow-up create earlier in the same file
  already does this correctly (`floor_id=floor_for_write(user)`); this
  sibling code path was missed.

### Fix pattern for bug class 2

Two different rules depending on who's creating the record:

1. **Direct human-initiated creates** (a live API request) — already correct
   where checked; use `floor_id=floor_for_write(user)`.
2. **Automation/event-handler-derived records** — inherit `floor_id` from the
   immediate source document (e.g. `quotation.get("floor_id", "first-floor")`,
   `source_po.get("floor_id", "first-floor")`), **not** `floor_for_write()`.
   Event handlers often only have an `actor_id`/`actor_name` string, not a
   full `UserPublic`, and semantically a PO derived from a ground-floor
   quotation must be a ground-floor PO regardless of which floor the
   triggering user happens to have selected right now.

## Catalog floor isolation + tile-ready schema

Folds the originally-scoped Catalog design into the same pass, since it's the
same root cause shape (missing floor concept) and blocks the ground-floor
tile section specifically.

**Data model** (`backend/models.py`):
- Add `floor_id: str = "first-floor"` to `Brand` and `Category` (currently
  absent entirely). One floor per brand/category (confirmed with user) — no
  brand spans two floors.
- Add `size: Optional[str] = None` to `Product` (top-level, parallel to the
  existing `finish`). `ProductVariant.size` already exists.

**Catalog engine** (`backend/services/catalog_service.py`) — the whole
product read model is an in-memory snapshot refreshed on writes (Atlas is
~228ms away; not worth a per-request round trip). None of its filtering
functions reference `floor_id` today. Fix:
- `_matches_filters()` gains `floor_ids: Optional[list[str]]` (`None` =
  unscoped, matching `floor_query`'s "All floors" semantics for
  owners/managers).
- Thread it through `list_products_page`, `search_catalog`, `facet_buckets`,
  `list_categories_with_counts`, `catalog_hierarchy`, families, alternates,
  complete-the-set.
- Routes: stop discarding `user` on brand/category/search/facet endpoints;
  resolve floor scope the same way `floor_query` does
  (`[user.active_floor_id]` if set, else `accessible_floor_ids(user)`, else
  unscoped).
- `create_product` / `create_custom_product`: use `floor_for_write(user)`
  instead of the hardcoded `"first-floor"` default.
- Add `POST /brands` and `POST /categories` (don't exist today — brands are
  currently only ever seeded) scoped to `floor_for_write(user)`, so a
  ground-floor "CUTE" brand can actually be created once tile data arrives.
- Add `"size"` to `_SEARCH_FIELDS` and a `"sizes"` facet bucket.

**Indexes & migration** (`backend/migrations/`):
- Backfill `floor_id="first-floor"` onto all existing `brands`/`categories`
  docs (none have the field yet).
- New compound unique index on `products`: `(floor_id, brand_id, sku)` — SKU
  uniqueness scoped per floor+brand (confirmed with user).
- **Prerequisite blocker:** the known live duplicate SKU (`26456000`, two
  different Hansgrohe products, both first-floor) will still block this
  index — same floor, same brand. Must be resolved (rename one SKU or merge
  the products) before the index migration runs, or the migration will
  crash the same way the earlier index-collision gotcha did. Surface this to
  the user as an explicit manual step, don't silently skip the index.
- Compound index on `(floor_id, brand_id)` for query performance.

**Quotation builder display** (frontend) — `PickerCard`, `VariantChip`, and
`LineRow` currently pick **one** differentiator via a fallback chain
(`finish || color || size || sku`), so a tile with both a finish and size
only shows the finish. Add one shared `variantDescriptor()` helper that joins
whichever of finish/size/color are present (e.g. "Glossy · 600×600mm"),
replacing the fallback chain at all call sites.

**Explicitly out of scope for this pass** (per user's earlier answers):
- No new infrastructure — staying on the existing Atlas cluster + Supabase
  project.
- No tile product data import — schema/isolation only, data entry later.
- Cmd+K quick-search brand-scoping — not required; Catalog page + Quotation
  Builder search (already brand-scoped) is what matters.

## Testing strategy

Mirror the existing pattern (`backend/tests/test_purchases_move_permissions.py`
— call the route's wired dependency directly, no live server needed):

- One regression test per fixed read-path module confirming a second-floor-
  scoped user gets an empty/disjoint result from a first-floor-scoped user
  against the same underlying data.
- One test per fixed write-path automation confirming the derived record
  inherits the source document's `floor_id` rather than defaulting to
  `"first-floor"`.
- Catalog: a test confirming `search_catalog`/`list_products_page`/
  `facet_buckets` respect floor scoping, and that SKU uniqueness is enforced
  per (floor_id, brand_id) not globally.

## Rollout sequencing

1. Bug class 1 (read-path scoping) — highest confidence, most visible to the
   user right now, no schema changes required.
2. Bug class 2 (write-path floor inheritance) — same pattern family, still no
   schema changes, prevents future re-mixing once ground-floor quotations
   start flowing through automation.
3. Catalog floor isolation + tile schema — schema changes + migration +
   frontend display fix. Requires resolving the duplicate-SKU blocker first.
