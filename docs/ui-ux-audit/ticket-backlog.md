# Ticket backlog

## [States][P0][S1] Catalog must not append results from another floor

**Tags:** buildcon-house, ui-ux-audit, states, P0, S1  
**Affected routes:** `/(admin)/catalog`  
**Problem:** after a floor switch, `loadMore` may issue a request with a captured prior floor id.  
**Steps:** load catalog; switch business floor; cause pagination.  
**Expected / actual:** only active-floor products / previous-floor products may append.  
**Evidence:** `app/(admin)/catalog/index.tsx:249-287`; lint warning at 287.  
**Suggested non-breaking fix:** add `selectedFloorId` dependency and reset pagination when it changes.  
**Acceptance / regression:** inspect initial and page-two requests/cards across each floor; retain existing pagination behavior.

## [Accessibility][P0][S1] Modal sheets must keep keyboard and screen-reader users oriented

**Tags:** buildcon-house, ui-ux-audit, accessibility, P0, S1  
**Affected routes:** phone More, catalog, customers, payments, follow-ups, quotations, purchases, Tiles.  
**Problem:** shared overlays lack labelled dialog/focus lifecycle.  
**Steps:** open a Sheet/BottomSheet, Tab/Shift+Tab, close with Escape/backdrop.  
**Expected / actual:** focus stays in named dialog and returns to trigger / behavior is not centrally implemented.  
**Evidence:** `src/design/components.tsx:444-542`, `src/components/BottomSheet.tsx:26-50`, `src/components/ui.tsx:1151-1185`.  
**Suggested non-breaking fix:** central adapter with modal semantics, named 44px close, initial focus, focus trap, and focus restoration.  
**Acceptance / regression:** keyboard and VO/NVDA verification at 320 and 1280; preserve all existing visual variants.

## [Accessibility][P0][S1] Warehouse actions must be discoverable and tappable

**Tags:** buildcon-house, ui-ux-audit, accessibility, interaction, P0, S1, responsive  
**Affected routes:** Tile Orders, dispatch/movement, Tile selection/quotation.  
**Problem:** core Tile action/filter/document controls lack semantics and some targets are 20–30px.  
**Steps:** use screen reader/keyboard to filter, dispatch, add, or remove a row.  
**Expected / actual:** named ≥44px controls / visual-only or undersized controls.  
**Evidence:** `TileLayout.tsx:130-280`, `TileMovementSheets.tsx:27-50`, `TilesDocBuilder.tsx:805-859`.  
**Suggested non-breaking fix:** use shared controls and Sheet while retaining styles.  
**Acceptance / regression:** AX tree exposes roles/names/state; all actions measure ≥44px at 320px.

## P1 grouped tickets

1. **[Forms][P1][S2] Associate shared input labels, errors, and invalid state** — `ui.tsx:620-678`, `design/components.tsx:204` (UX-004).
2. **[Accessibility][P1][S2] Make quotation product actions independently named and non-nested** — ProductExplorer/PickerCard/ProductModal (UX-005).
3. **[Navigation][P1][S2] Represent phone route navigation as navigation links** — `_layout.tsx:493-542` (UX-006).
4. **[Accessibility][P1][S2] Announce toast outcomes and set route-specific web titles** — `Toast.tsx`, `+html.tsx` (UX-007).
5. **[Accessibility][P1][S2] Restore visible keyboard focus to payment date fields** — `payments.tsx:593-602,849-859` (UX-008).
6. **[Interaction][P1][S2] Add catalog filter state, labels, and 44px targets** — `catalog/index.tsx:551-598` (UX-009).
7. **[Interaction][P1][S2] Reveal dashboard queue actions on keyboard focus** — `dashboard.tsx:89-94` (UX-010).
8. **[Responsive][P1][S2] Consolidate 900/1024 breakpoint contracts** — responsive/tokens/legacy Sheet (UX-011).
9. **[Responsive][P1][S2] Stack Tile headers and toolbar at constrained widths** — `TileLayout.tsx` (UX-012).
10. **[Accessibility][P1][S2] Standardize 44px named purchase/PO operations** — purchase components (UX-013).
