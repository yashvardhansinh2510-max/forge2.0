# Multi-floor page and workflow audit — 2026-09-02

## Scope and evidence

This review covers the current frontend and backend paths for The Sanitary
Bathroom (`first-floor`), Ground Floor/Tiles (`ground-floor`), Kitchen Floor
(`second-floor`), and the tile quotation/order workflow. It combines route,
state, API-scope, and workflow source review with the current automated checks.
It is not a substitute for a staffed-device session: no authenticated visual,
VoiceOver/TalkBack, or real-network run was available in this workspace.

Verified during this audit:

- `frontend`: lint, TypeScript (`npx tsc --noEmit`), notebook, quotation, and
  mobile UX contracts pass.
- `backend`: `1094 passed` in `tests/unit` after the corrective work below.
- A production frontend build was intentionally not run: its guard correctly
  rejects this environment because it has no configured safe HTTPS backend URL.

## What is working and should be amplified

| Area | Evidence | Why it matters |
| --- | --- | --- |
| Floor-scoped operations | Request floor headers, backend floor-query helpers, and tile-specific client calls are consistently used in core operation paths. | Keeps product, customer, and order data isolated by business unit. |
| Tile order operations | Tile Orders has explicit Ground Floor access, paged/race-safe loads, retry states, and a dedicated movement register. | This is the most operationally mature cross-department workflow. |
| Revenue foundation | `ordered_at` is write-once and the analytics service already treats `ordered` as the current confirmed-order status. | Enables accurate period reporting without edits moving historic revenue. |
| Notebook model | Kitchen/Furniture use the same floor-pinned model and preserve the two-page follow-up/quotation-follow-up workflow. | Avoids a separate, drifting CRM implementation. |
| Shared design system | Shared sheets, loading/error states, safe areas, and virtualized core lists are available and increasingly used. | Reduces repeat mobile and accessibility regressions. |

## Page audit and revisions

### The Sanitary Bathroom

1. **P1 — Direct-route context must remain explicit.** Generic quotation,
   purchase, and purchase-order routes intentionally follow the active floor;
   the shell hides them outside their appropriate workspace. A bookmark or
   direct URL therefore depends on the active-floor lifecycle. Keep the route
   contract documented and add authenticated route tests that open each
   Sanitary URL from Ground Floor, then assert the intended redirect or scoped
   content. Do not blindly pin the generic routes to `first-floor`: doing so
   would reintroduce the old cross-floor data leak.
2. **P2 — Validate Sanitary routes on a real phone.** Purchases uses compact
   operational controls, so its transfer, shortage, and settings sheets need a
   320px keyboard and screen-reader check even though the shared Sheet contract
   and source checks now pass.
3. **Completed in this audit:** Catalog filter controls now announce their
   selected state and have named removal controls with 44px targets.

### Ground Floor / Tiles

1. **Completed in this audit:** Tile quotation/selection list reloads on
   focus, ignores stale responses, and has loading/error/Retry states instead
   of a blank screen.
2. **Completed in this audit:** Tile deletion returns to Tile Quotations,
   not Follow-ups. Tile order review now stays on the Ground Floor request
   context and labels quantities as boxes or pieces (with size/pack metadata).
3. **Completed in this audit:** Tile product-search failures no longer pretend
   that the catalog is empty; existing results remain visible with Retry.
4. **P2 — Runtime layout verification remains needed.** Tile headers and
   document toolbars need 320px/200%-zoom screenshots to prove deliberate
   wrapping rather than clipping.

### Kitchen Floor

1. **Completed in this audit:** Kitchen/Furniture notebook deep links now call
   the floor-access guard, and stale search/filter responses cannot overwrite
   the latest result set.
2. **Completed in this audit:** Notebook table cells and fields expose their
   customer/column editing context to assistive technology.
3. **P2 — Desktop notebook navigation needs a follow-up.** The wide grid still
   relies on horizontal scrolling. Add keyboard movement using the existing
   `nextCell` model, then test focus and save/error behavior with real data.

### Shared Tile workflow

1. **Completed in this audit:** A tile document opened under the wrong
   Selection/Quotation route redirects to its canonical route.
2. **Completed in this audit:** Custom-access Tile staff now receive the
   `tiles` visibility mapping and a Tiles landing path.
3. **P1 — Device test required:** The modal/sheet focus lifecycle must still
   be verified with VoiceOver/TalkBack; static semantics cannot prove focus
   trapping or focus restoration.

## Workflow audit and revisions

| Priority | Workflow finding | Result |
| --- | --- | --- |
| P0 | Dashboard/Sales Data treated legacy `won` as the only completed sale, even though current placement writes `ordered`. | **Fixed.** Current orders are dated by immutable `ordered_at`; historic `won` rows remain visible through a compatibility path. |
| P1 | Dashboard top products included draft/lost lines and used gross quantity × rate. | **Fixed.** Ranking is limited to confirmed orders and sums stamped discounted `net_amount`, with a historic fallback. |
| P1 | A PO could be manually or automatically associated with a supplier from another floor or an unrelated brand. | **Fixed.** Supplier/brand checks now validate PO floor and brand; automated grouping scopes active suppliers to the quotation's floor. |
| P1 | Walk-ins could be assigned to warehouse, inactive, or wrong-floor staff. | **Fixed.** Creation and reassignment require active sales-capable staff assigned to the walk-in floor. |
| P1 | Tile quotation list/search failures could leave staff with a blank or false empty state. | **Fixed.** Error states retain context and offer a retry path. |
| P1 | Custom grants could hide the Tiles navigation path. | **Fixed.** The module/resource map and grant landing route are aligned. |
| P2 | Reporting still mixes current and legacy status schemas. | Keep the temporary `won` compatibility branch until a planned migration/backfill converts historic confirmed revenue to `ordered_at`; then remove the fallback deliberately. |
| P2 | Runtime/device coverage is absent. | Add deterministic authenticated fixtures plus viewport, offline, delayed-response, keyboard, and screen-reader regression coverage. |

## Operational release gates

1. Resolve the known live duplicate SKU before any production process starts
   with migration `0006` present; the migration can otherwise prevent backend
   startup. See `AGENTS.md` for the confirmed record and safe sequence.
2. Configure a non-secret HTTPS backend URL in the production build
   environment, then run the frontend build and route-level smoke suite.
3. Run staff-device checks at 320×568, 390×844, 768×1024, and 1366×768 for:
   Sanitary quotations/purchases, Tile Orders/dispatch, Tile quotation
   builder/place-order, and Kitchen notebook editing.

## Next implementation order

1. Add authenticated route/device regression coverage for the direct URL and
   active-floor contract.
2. Add notebook keyboard cell navigation and a mobile card/editor fallback
   for wide tables.
3. Backfill/migrate historic `won` records to the current confirmed-order
   schema, then retire legacy reporting compatibility.
4. Capture visual and assistive-technology evidence for every release gate.
