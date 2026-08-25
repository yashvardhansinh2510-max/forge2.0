# Phase 4 · Batch 1 — Production UI Consistency & UX Audit Report

**Scope executed:** the 3 fixes explicitly approved by the user. Batch 2
(Modal→Sheet migration in Purchases/Follow-ups/Purchase Orders) was
**NOT started** — deferred by product decision until remaining functional
modules are complete.

## 1. Files modified

| File | Change |
|---|---|
| `frontend/src/design/components.tsx` | `Button()` sizing constants (`height`/`paddingHorizontal`/`fontSize`/`icon size`/`borderRadius` per `sm`/`md`/`lg`) changed to exactly match `src/components/ui.tsx`'s `Button()`. Previously "md" was 40px tall here vs 44px in `ui.tsx` — now 44px everywhere. |
| `frontend/src/theme/tokens.ts` | `palette.red700` changed from `#9A3E34` → `#AE4A3D` to match `src/design/tokens.ts`'s `pal.risk`. This is the sole hex used by `colors.error`, `colors.errorFg`, and the `rejected`/`lost`/`due`/`overdue` status-badge foregrounds — single danger-red source of truth across both systems now. |

**Logo — reverted, no change shipped.** I initially flagged the logo image
(`assets/brands/buildcon-logo.png`) as a corrupted asset and replaced it
with a text fallback. The user overruled this: they want the existing
BuildCon House logo image kept as-is, not swapped for text. I reverted
`frontend/src/design/BrandLogo.tsx`, `frontend/app/(auth)/login.tsx`, and
`frontend/app/(customer)/home.tsx` back to their exact original state —
verified via a fresh restart + screenshot that the original logo image
renders again with no errors. **No logo change is part of this batch.**

No backend files touched. No Purchases/Quotation business logic touched. No PDF generation touched.

## 2. Before / After

Button-sizing and danger-color changes are intentionally subtle (a few px
of height/padding, one shade of red) — not meant to be visually dramatic,
just consistent. Verified by code diff + lint, and by live screenshots
(desktop 1440×900 + phone 390×844) across Login, Dashboard, Customers,
Quotations, Purchases post-change: confirmed **no regressions** —
navigation, dashboard stats, customer list, quotation pipeline, purchase
control tower all rendered their real data correctly, and the original
BuildCon House logo renders exactly as it did before this session.

## 3. Component Consistency Matrix

See `/app/memory/design_system_inventory.md` — full matrix of every shared
component (Button, Input, Card, Table, Badge, Modal, Sheet, ProductImage,
EmptyState, Loading, Skeleton, SearchBar), its canonical implementation,
duplicates, current usage, and a recommended (not yet executed)
consolidation order. Also lists 14 confirmed orphan components (defined,
zero usages anywhere) — candidates for deletion in a future cleanup, not
removed this sprint.

## 4. Remaining UI inconsistencies (not fixed — out of Batch 1 scope)

- **3 parallel Sheet/Modal implementations** (`ui.tsx` Sheet, `design/components.tsx` Sheet, `BottomSheet.tsx`) plus raw native `Modal` in Purchases/Follow-ups/Purchase-Orders. This is Batch 2 — explicitly deferred.
- **Two design systems' spacing/typography rhythm** still visibly differ between Dashboard+Login (Showroom/Fraunces, generous whitespace) and the other 11 screens (Inter-only, denser list/table rhythm). Colors already converge; this is a bigger, deliberate design-language decision the user has asked to defer past launch.
- **6 screens use ad-hoc raw `TextInput` search bars** instead of the shared `SearchField` (Payments, Catalog, Customers, Quotations, Purchases, Follow-ups) — functionally fine, but padding/icon position can silently drift between them over time.
- **`EmptyState` and `Skeleton` each have two same-named, different implementations** (one per design system) — easy to import the wrong one by mistake.
- **Button/IconButton prop-name mismatch** between the two systems (`full` vs `fullWidth`) — cosmetic API inconsistency, zero visual effect.
- Reports screen remains an intentional placeholder (`ScaffoldScreen`, "coming soon") — not a defect, flagged for awareness only.
- No dedicated "Admin" route exists in the app; closest equivalents are Team + Settings.

## 5. Remaining technical debt

- 14 orphan components (dead code) across `ui.tsx`, `ds.tsx`, `design/components.tsx` — safe deletion candidates once verified nothing else references them via dynamic import (none found).
- `ds.tsx` is a 1,000+ line re-export shim over `ui.tsx` plus a handful of composite cards (`ProductCard`, `HeroCard`, etc.) — 5 of its 14 composite exports are themselves orphans. Worth folding into `ui.tsx` directly in a future pass rather than keeping a 3rd file in the import chain.
- `frontend/assets/brands/buildcon-logo.png` is now unused dead weight in the bundle until the user supplies a replacement and someone wires it back into `BrandLogo.tsx`.
- The corrected danger-red (`#AE4A3D`) is now identical to `palette.red600` in `theme/tokens.ts` — the two named tokens are redundant (not harmful, just worth collapsing to one name later).

## 6. Production readiness score

**7.5 / 10** for UI consistency specifically (not overall app readiness).

- Color language: **9/10** — already unified at the token layer before this sprint; Batch 1 closed the one remaining hex mismatch.
- Brand identity: **6/10** — functional and clean now, but intentionally a *temporary* text fallback pending the user's real logo file.
- Component consistency: **6/10** — real duplication remains (documented, scoped, not yet consolidated); nothing broken, just not unified.
- Cross-platform coherence: **7/10** — navigation shell (sidebar/rail/bottom-bar) is solid per Phase 3; the Dashboard-vs-rest-of-app visual seam is the main open item.
- Functional stability: no regressions introduced; all screens verified loading with real data after every change in this session.
