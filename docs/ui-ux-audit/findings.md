# Finding register

All items are deduplicated by root cause. “Confirmed” means source or tooling evidence; it does not claim unperformed visual/assistive-technology runtime behavior.

## UX-001 — Catalog pagination retains the previous floor

- **Category / severity / priority:** states, S1 critical, P0 immediate
- **Route / flow:** `/(admin)/catalog`; switch floor, then load more catalog results.
- **Component / reference:** `app/(admin)/catalog/index.tsx:249-287`.
- **Viewport / state:** all; loaded list with more results after a floor switch.
- **Observed:** `loadMore` reads `selectedFloorId` into its request but omits it from `useCallback` dependencies. Lint reports this exact missing dependency.
- **Expected / impact:** pagination must use the active floor; otherwise prior-floor products can appear in the current business unit and undermine trust/data isolation.
- **Evidence / reproduction:** choose a floor, load catalog, switch floor, trigger end-reached; inspect the next request/cards. `npm run lint` reports line 287.
- **Root cause / direction:** stale callback closure. Include `selectedFloorId` and reset pagination on floor changes.
- **Acceptance:** after each floor switch, initial and pagination requests use the same floor id and cards contain only that floor. **Confidence:** confirmed.

## UX-002 — Shared sheets do not establish an accessible modal lifecycle

- **Category / severity / priority:** accessibility, S1 critical, P0 immediate
- **Route / flow:** phone More; filters; payments; customer, follow-up, and quotation sheets.
- **Component / reference:** `src/design/components.tsx:444-542`, `src/components/BottomSheet.tsx:26-50`, and `src/components/ui.tsx:1151-1185`.
- **Viewport / state:** all; open overlay.
- **Observed:** overlay wrappers lack labelled dialog semantics, focus trap/initial focus, and opener-focus restoration; legacy close control is unnamed.
- **Expected / impact:** keyboard and screen-reader users must stay oriented within the open dialog and return to its trigger on close. Current behavior can expose hidden background controls or lose place.
- **Evidence / reproduction:** static inspection; verify with Tab/Shift+Tab, Escape, and VoiceOver/NVDA after runtime setup.
- **Root cause / direction:** parallel overlay implementations. Upgrade one shared primitive/adapter with labelled modal semantics, 44px named close, focus lifecycle, safe-area, and keyboard behavior.
- **Acceptance:** focus remains in each open panel, Escape/backdrop behavior is predictable, and close restores trigger focus. **Confidence:** confirmed structure; runtime behavior unverified.

## UX-003 — Tile workflows contain unnamed, undersized, and semantically incomplete controls

- **Category / severity / priority:** accessibility/interaction, S1 critical, P0 immediate
- **Route / flow:** `/(admin)/tiles/orders`, dispatch/movement, `tiles/selection`, and `tiles/quotation` document editing.
- **Component / reference:** `src/components/tiles/TileLayout.tsx:130-280`; `TileMovementSheets.tsx:27-50,112-270`; `TilesDocBuilder.tsx:805-859`.
- **Viewport / state:** all, especially phone; filter, dispatch/release, add/remove row.
- **Observed:** key `Pressable` controls lack names/roles/selected state; document row actions are 20–30px icons and the local modal has incomplete close/focus/safe-area handling.
- **Expected / impact:** every core inventory action needs a discoverable accessible name and ≥44px target. Staff can otherwise misoperate or be blocked from dispatch/document workflows.
- **Evidence / reproduction:** source inspection; navigate Tile Orders with screen reader/keyboard and tap row actions at 320px after setup.
- **Root cause / direction:** bespoke primitives bypass shared accessible controls. Adopt shared button/tab/search and shared Sheet, retaining visual styling.
- **Acceptance:** accessible tree exposes named buttons/tabs/search state; all core targets measure at least 44px; modal has UX-002 behavior. **Confidence:** confirmed.

## UX-004 — Shared form labels and errors are not programmatically associated

- **Category / severity / priority:** forms/accessibility, S2 major, P1 next sprint
- **Route / flow:** login, customers, team, settings, catalog editor, follow-ups, sales filters.
- **Component / reference:** `src/components/ui.tsx:620-678`; `src/design/components.tsx:204`.
- **Viewport / state:** all; normal and validation-error states.
- **Observed:** visual label/helper/error are separate from `TextInput`; no accessible name/description/invalid state is provided by the wrapper.
- **Expected / impact:** assistive technology must announce field purpose, error, and correction guidance.
- **Evidence / reproduction:** inspect AX tree for a required/error field. **Root cause / direction:** shared primitives; generate web ids/relationships and native labels/state centrally.
- **Acceptance:** AX inspection exposes label, required/invalid state, and error description for every primitive consumer. **Confidence:** confirmed.

## UX-005 — Quotation product cards/modal expose ambiguous nested and icon-only actions

- **Category / severity / priority:** accessibility/interaction, S2 major, P1 next sprint
- **Route / flow:** `/(admin)/quotations/new` and builder product picker/detail.
- **Component / reference:** `ProductExplorer.tsx:333-367`, `PickerCard.tsx:50`, `ProductModal.tsx:130,139,158,242`, `QuickAddButton.tsx:61`.
- **Viewport / state:** phone/tablet/desktop; browse product, favorite/add, change quantity.
- **Observed:** clickable cards contain child interactive actions; close, zoom, thumbnails, and quantity buttons lack names.
- **Expected / impact:** controls need independent keyboard/pointer behavior and meaningful names; nesting causes ambiguous activation/focus.
- **Evidence / direction:** static references above. Make card noninteractive with sibling named actions; name every icon button.
- **Acceptance:** no nested interactive descendants; keyboard order is logical; AX names include action and context. **Confidence:** confirmed.

## UX-006 — Route navigation is represented as incomplete ARIA tabs

- **Category / severity / priority:** navigation/accessibility, S2 major, P1 next sprint
- **Route / flow:** phone admin shell at widths below 768px.
- **Component / reference:** `app/(admin)/_layout.tsx:493-542`.
- **Observed:** each route-changing control has `role=tab`, but there is no tablist/panel or arrow-key model; More opens a sheet.
- **Expected / impact:** route navigation should be navigation/list links (or a fully implemented tab pattern). Incorrect semantics misleads web assistive technology.
- **Direction / acceptance:** use links in a navigation landmark and keep selected/current state; verify keyboard and screen reader announcement. **Confidence:** confirmed.

## UX-007 — Status feedback and page titles are not available to web assistive technology

- **Category / severity / priority:** accessibility/states, S2 major, P1 next sprint
- **Route / flow:** all web routes; save/create/error actions.
- **Component / reference:** `app/+html.tsx:5`; `src/components/Toast.tsx:31,50-61`.
- **Observed:** no route-specific document title mechanism; Toast has no live status/alert semantics and dismisses in 2.6 seconds.
- **Expected / impact:** route change and outcome feedback must be perceivable non-visually.
- **Direction / acceptance:** set title by route; use polite status/assertive error announcements and retain important errors inline. Verify AX/live announcement. **Confidence:** confirmed structure; announcement runtime-unverified.

## UX-008 — Payment date inputs remove visible web focus

- **Category / severity / priority:** accessibility, S2 major, P1 next sprint
- **Route / flow:** `/(admin)/payments`; filter history and record a payment.
- **Component / reference:** `app/(admin)/payments.tsx:593-602,849-859`.
- **Observed:** browser outline is disabled without a replacement focus-visible style.
- **Expected / impact:** keyboard user must locate focus reliably.
- **Direction / acceptance:** apply design-system focus ring with ≥3:1 contrast; tab through both fields at desktop and 200% zoom. **Confidence:** confirmed.

## UX-009 — Catalog filtering controls omit state/name and fall below the preferred target size

- **Category / severity / priority:** accessibility/interaction, S2 major, P1 next sprint
- **Route / flow:** `/(admin)/catalog` category and active-filter management.
- **Component / reference:** `catalog/index.tsx:551-598`.
- **Observed:** category/family Pressables lack semantics; active-chip removal is unnamed; CategoryPill is 40px.
- **Expected / impact:** selected filters and removal actions must be announced and comfortably tappable.
- **Direction / acceptance:** named buttons with selected state; 44px target/hit slop; test 320px. **Confidence:** confirmed.

## UX-010 — Hidden dashboard queue actions remain keyboard-focusable

- **Category / severity / priority:** accessibility/interaction, S2 major, P1 next sprint
- **Route / flow:** dashboard queue action (Call, WhatsApp, Mark done).
- **Component / reference:** `app/(admin)/dashboard.tsx:89-94`.
- **Observed:** action buttons are hidden by opacity until hover, not removed/hidden from focus order.
- **Expected / impact:** focused action must be visually revealed; otherwise tabbing reaches invisible controls and risks unintended follow-up changes.
- **Direction / acceptance:** reveal on focus-within or render an always-visible action affordance. Keyboard traversal must always show focused action. **Confidence:** confirmed.

## UX-011 — Breakpoint and component systems conflict in tablet widths

- **Category / severity / priority:** responsive/component consistency, S2 major, P1 next sprint
- **Route / flow:** admin routes using shell plus `ui` Sheet; 900–1023px and 1024×768.
- **Component / reference:** `src/design/responsive.ts:10-19`, `src/design/tokens.ts:153-164`, `src/components/ui.tsx:1114-1119`, `src/hooks/use-breakpoint.ts:12-24`.
- **Observed:** shell becomes desktop at 1024, legacy Sheet at 900, and a third hook labels 1024–1439 tablet landscape.
- **Expected / impact:** one documented responsive contract. Current combinations can mix rail/sheet/grid behavior.
- **Direction / acceptance:** derive behavior from one shared breakpoint authority and capture visual evidence at 768, 900, 1024. **Confidence:** confirmed code; visual result unverified.

## UX-012 — Tile header/toolbar constraints risk phone and zoom overflow

- **Category / severity / priority:** responsive, S2 major, P1 next sprint
- **Route / flow:** Tile Orders and document header/toolbars.
- **Component / reference:** `TileLayout.tsx:357-365,413-424,464-480`.
- **Observed:** 260px header and 240px search minimum widths sit inside a 280px available area at 320px (20px gutters) before actions/gaps.
- **Expected / impact:** toolbar should deliberately stack/reflow rather than clip or force accidental horizontal overflow.
- **Direction / acceptance:** phone override removes min widths and stacks actions/search; test 320px, landscape, and 200% zoom. **Confidence:** confirmed geometry; clipping unverified.

## UX-013 — Mobile purchase/PO action controls are repeatedly below target and some lack names

- **Category / severity / priority:** accessibility/interaction, S2 major, P1 next sprint
- **Route / flow:** Purchases, purchase order, customer workspace movement/history/transfer actions.
- **Component / reference:** `purchases.tsx:1058-1061,1116-1126`; `purchase-orders/[id].tsx:628-635`; `customers/[id].tsx:897-903`.
- **Observed:** compact icon Pressables use small glyphs/`hitSlop={6}` and some have no accessible label.
- **Expected / impact:** key stock operations require named ≥44px targets.
- **Direction / acceptance:** use shared IconButton or equivalent 44px frame and contextual labels; verify at 320px. **Confidence:** confirmed.
