# Remediation plan

## Phase 0 — release blockers

1. Fix Catalog’s stale floor pagination closure and add a focused regression test.
2. Make one accessible overlay primitive the compatibility layer for all existing sheets.
3. Replace Tile workflow’s bespoke action/modal controls with that primitive and shared accessible controls.

## Phase 1 — shared foundations

1. Consolidate responsive decisions onto `src/design/responsive.ts` and documented design tokens.
2. Add accessible form-field linkage and invalid/error semantics to both existing input systems, then migrate by adapter rather than screen rewrite.
3. Define a shared web focus-visible ring and apply it to custom/native date inputs.
4. Upgrade status announcements and route titles.

## Phase 2 — critical-flow composition

1. Recompose quotation product cards into sibling actions; name every icon action.
2. Make phone navigation use truthful navigation semantics.
3. Give catalog, purchase, and PO compact actions contextual names and 44px hit areas.
4. Add mobile Tile toolbar stacking without changing desktop layout.

## Phase 3 — verification and polish

Run 320/375/390/414 phone, 568 landscape, 768/820 tablet, 1024/1280/1440 desktop, plus 200% zoom. Exercise Catalog floor switch/pagination, quotation add/save, Tile dispatch/document edit, payment, More navigation, form validation, dialog lifecycle, loading/empty/error cases. Capture screenshots and AX/keyboard evidence before claiming release readiness.
