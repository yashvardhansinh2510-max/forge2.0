# Builder screens: hard-lock floor scope (Tiles vs sanitary)

Date: 2026-07-26
Status: approved by user, pending implementation plan
Sub-project: A of 3 (Floor isolation → Tiles workflow revamp → Sales Data page). Follow-ups explicitly deferred by user.

## Background

This is a follow-up to `2026-07-17-floor-isolation-and-tile-catalog-design.md`
(status: implemented — verified live in this session: `catalog_routes.py`
threads `floor_scope_ids(user)`/`floor_query(user, ...)` through brand,
category, product, family, and search endpoints; `domain_outbox.py`'s
`_handle_order_placed` now stamps `floor_id=floor_inherit(quotation)` on
generated purchase orders and payments). That pass made floor scoping
**correctly follow the ambient floor context** (`X-Floor-Id` header / active
floor selection). It did not make any screen **independent** of that ambient
context.

The user is hitting exactly that gap:

- Switching floors sometimes shows the wrong floor's items (ambient state
  lagging or unset).
- Selecting "All floors" merges ground-floor tile products into what should
  be a sanitary-only view, and vice versa.
- The Tiles Quotation product picker can effectively fail to add products
  when the ambient floor context isn't `ground-floor` (e.g. reached via
  direct URL/bookmark/refresh rather than through the sidebar's
  `useTilesNav().open()`, which is the only place that currently forces the
  switch).

**Live data confirmed this session (read-only query, no writes):** 2,821
first-floor products, 708 ground-floor (tile) products, 46 first-floor
quotations, 13 first-floor purchase orders, 8 ground-floor tiles documents.
`second-floor` is a dead stub in the `floors` collection — zero records ever,
not a real third floor in practice. Also found: 3 of the 8 ground-floor tiles
quotations are stuck in `status: "ordered"` with **zero** purchase orders
behind them anywhere in the `purchase_orders` collection — evidence the
order-placement automation is crashing for tile-shaped line items after the
quotation's status is already committed as `ordered`. That crash is a
different bug (automation logic, not floor scoping) and is explicitly
**out of scope here** — it belongs to sub-project B (Tiles workflow revamp).
Per user's explicit decision, no existing data is being deleted or modified
as part of this fix; the 3 stuck quotations are left exactly as they are.

## Decision: hard-lock two screens, leave the rest as true "All floors"

Confirmed with user:

- **Tiles Selection / Tiles Quotation / Tile Orders** always operate against
  `floor_id="ground-floor"` product and document data — regardless of the
  global floor switcher, "All floors" selection, or how the screen was
  reached (sidebar nav, direct URL, refresh, bookmark).
- **The sanitary Quotation Builder** always excludes `ground-floor` — same
  treatment, opposite direction.
- Every other screen (Catalog browse, Dashboard, Customers, Purchases
  Tracker/list) keeps today's behavior: "All floors" means a true merged
  view for owners/managers. This is intentionally useful there and is not
  being changed.
- Enforcement is **server-side**, not a frontend convenience: a client
  cannot get ground-floor data out of a sanitary-builder-only endpoint (or
  vice versa) by manipulating request state. The existing
  `require_floor_access(floor_id, user)` guard (`backend/auth.py`, already
  written, currently unused by these paths) is the mechanism — a user
  without ground-floor access gets a 403 from the tiles endpoints, not a
  silently empty result.

## Design

**Backend — new fixed-floor request shape for the two builders.** Rather
than reading `user.active_floor_id` from the ambient header, the specific
endpoints these two builders call (product search/list, family/variant
lookups used by `TilesProductPicker` and the sanitary builder's
`ProductExplorer`/`CatalogPane`) accept an explicit, required floor
parameter that the builder always sends as a constant (`ground-floor` for
Tiles, `first-floor` for sanitary — never derived from the switcher). The
route calls `require_floor_access(floor_id, user)` before querying, then
uses that fixed value in place of `floor_scope_ids(user)`/`floor_query(user,
...)` for that request only. This reuses the same underlying
`catalog_service` functions from the 07-17 pass (`floor_ids=[...]` — they
already accept an explicit list, just weren't being called with anything
except the ambient/ derived value in these two call sites).

**Write path.** Saving/creating a quotation from either builder stamps
`floor_id` from the builder's fixed floor (passed alongside the save
request, validated the same way), not from `floor_for_write(user)`. This
closes the exact class of bug already fixed once for the read side on
2026-07-25 (quotations silently saving under the wrong floor when reached
outside the sidebar's floor-switch flow) — this time at the general
mechanism level instead of a one-off patch.

**Frontend.** `TilesProductPicker` and the sanitary builder's product
pickers stop reading the global floor switcher for their catalog queries —
they pass their screen's constant floor instead. No visible UI change; this
is purely which data comes back.

**Access-control audit (small, bundled in).** Confirm a first-floor-only
staff account genuinely cannot reach `/tiles/selection`,
`/tiles/quotation`, or `/tiles/orders` by direct URL — today the sidebar
just hides the nav links (`useTilesNav`'s `groundAccessible` check), which
is not the same as a server-side guard. Add one if the audit finds it
missing, using the same `require_floor_access` call.

**Explicitly not touched:**
- No data deletion or migration — products, quotations, purchase orders,
  customers, payments all stay exactly as they are.
- The 3 stuck `ordered` tiles quotations — left as-is (user's explicit
  choice), to be addressed when sub-project B fixes the underlying
  place-order automation crash.
- `second-floor` — confirmed unused; no design decision needed for it here.
  If it's genuinely never going to hold data, retiring it is a candidate for
  a later cleanup pass, not this one.

## Testing

Mirror the existing pattern (`backend/tests/unit/`, call the route's wired
dependency directly — see `test_quotation_floor_id_from_items.py` and
`test_purchases_move_permissions.py` for the reference shape):

- Tiles endpoints return only `ground-floor` products/documents even when
  the caller's ambient `active_floor_id` is empty ("All floors") or set to
  `first-floor`.
- Sanitary builder endpoints return only non-`ground-floor` data under the
  same ambient-state variations.
- A user whose `floor_ids` don't include `ground-floor` gets a 403 from the
  tiles endpoints (not an empty list).
- A quotation saved from either builder carries the correct `floor_id`
  regardless of ambient state at save time.
- Catalog browse, Dashboard, Customers, Purchases list: confirm "All
  floors" is unchanged (regression guard, since these share underlying
  `catalog_service` functions with the two builders).

Live verification: open Tiles Quotation directly by URL while set to "All
floors" as an owner → only tile products appear, add-product works; repeat
for the sanitary builder; confirm the untouched screens still merge under
"All floors".

## Rollout

Single milestone — additive/corrective logic only, no schema change, no
data migration. Safe to revert via git if it regresses anything.
