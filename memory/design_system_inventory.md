# BuildCon House — Design System Inventory & Component Consistency Matrix

**Purpose:** roadmap for a future consolidation sprint. This is a read-only audit
document — nothing here was consolidated in Phase 4 · Batch 1 per explicit
product decision ("stability over architectural perfection before launch").

**Last updated:** Phase 4 · Batch 1 — Production UI Consistency & UX Audit (2026-08).

## The two systems, in one sentence each

- **`src/design/*`** ("Showroom") — Fraunces serif + warm-gallery spacing.
  Used by exactly 2 screens: **Dashboard** (`app/(admin)/dashboard.tsx`) and
  **Login** (`app/(auth)/login.tsx`), plus the app shell (`_layout.tsx`,
  `CommandPalette.tsx`).
- **`src/components/ui.tsx`** ("Design System V1") + its re-export shim
  **`src/components/ds.tsx`** — Inter-only, denser list/table rhythm. Used by
  the other **11** screens: Customers, Quotations, Catalog, Purchases,
  Payments, Follow-ups, Settings, Team, Notifications, Customer Portal Home,
  Add Customer.

Both systems' raw **color values** already converge on the same brass/ink
palette (verified — see Phase 4 audit report), so the seam is about
**spacing/typography rhythm and component API shape**, not color.

## Component Consistency Matrix

| Component | Canonical (recommend) | Duplicate implementation(s) | Current usage | Notes |
|---|---|---|---|---|
| **Button** | `ui.tsx` (11 screens) | `design/components.tsx` (Dashboard, Login, shell) | Both now render identical height/padding/icon-size per size name (fixed in Batch 1) | API differs: `fullWidth` (ui.tsx) vs `full` (design). Prop-name unification deferred. |
| **IconButton** | `ui.tsx` | `design/components.tsx` | Both actively used | Not yet compared pixel-for-pixel; not in Batch 1 scope. |
| **Sheet** (bottom/center) | `ui.tsx` `Sheet()` | `design/components.tsx` `Sheet()`; **`BottomSheet.tsx`** (3rd impl) | ui.tsx Sheet: 0 direct screen usages found (available, unused so far); design Sheet: `_layout.tsx`, `MovementEngine.tsx`; `BottomSheet.tsx`: Catalog + 5 Quotation Builder sheets (Swap/Room/Discount/Description/CustomerSwitcher) | **3 parallel sheet implementations.** Highest-value future consolidation target. |
| **Modal (raw native)** | — none canonical | Raw `Modal` from `react-native` used directly in `purchases.tsx`, `followups.tsx`, `purchase-orders/[id].tsx` | 3 screens | Flagged in Phase 4 report as Batch 2 (not started — explicitly deferred by product decision). |
| **Card / Surface / Panel** | `ui.tsx` `Card()` | `design/components.tsx` `Surface()`; `ds.tsx` `Panel()` | Card: most V1 screens; Surface: Dashboard/Login; Panel: 2 files | 3 names for the same concept. |
| **TextField / Input / Field** | `ui.tsx` `TextField()` | `design/components.tsx` `Field()` + `Input`; `ui.tsx` `FormField()` (variant) | TextField: most V1 screens; Field/Input: Login only | Different focus-ring/label layout between systems. |
| **Badge / Chip / StatusBadge** | `ui.tsx` (`Badge`, `Chip`, `StatusBadge`) | `design/components.tsx` `StatusWord()` (dot+word variant) | Badge/Chip: everywhere in V1 screens; StatusWord: Dashboard only | Same semantic purpose (status pill), different visual treatment (filled pill vs dot+word). |
| **Table** | `ui.tsx` `Table/TableHeader/TableRow/TableCell` | none found | Purchases, Purchase Orders | Single implementation — **no duplication found here.** |
| **SearchField** | `ui.tsx` `SearchField()` | none — but 6 screens (`payments`, `catalog`, `customers`, `quotations`, `purchases`, `followups`) use a **raw `TextInput`** styled ad-hoc instead of importing `SearchField` | Mixed | Not a duplicate *component*, but a duplicate *pattern* — every screen re-styles its own search bar instead of reusing the shared one. Real inconsistency risk (padding/icon position can drift screen-to-screen). |
| **EmptyState** | `ui.tsx` `EmptyState()` | `design/components.tsx` `EmptyState()` (separate impl, same name) | ui.tsx version: 11 screens; design version: Dashboard only | Same name, two implementations — easy to accidentally import the wrong one. |
| **ErrorState** | `ui.tsx` `ErrorState()` | none | All V1 screens | Single implementation. Showroom system has no dedicated ErrorState (Dashboard doesn't currently need one). |
| **LoadingState** | `ui.tsx` `LoadingState()` | none (Showroom screens use `Skeleton` directly, no dedicated loading-state wrapper) | Sparse usage — most screens prefer `Skeleton` over `LoadingState` | Low usage; consider deprecating in favor of Skeleton everywhere. |
| **Skeleton** | `ui.tsx` `Skeleton()` | `design/components.tsx` `Skeleton()` (separate impl, same name/props shape) | Both actively used in their respective screens | Nearly identical props (`w`/`h`/`radius` vs `w`/`h`/`r`) — cheapest future merge candidate. |
| **ProductImage** | `src/components/ProductImage.tsx` | **none found** | Catalog, Catalog detail, Customer detail, Purchases, Quotation Builder (LineRow, ProductExplorer, PickerCard, ProductModal, SwapSheet, AssistantPane) | ✅ **Fully consolidated already** — every product photo in the app goes through this one component. No action needed. |
| **PageHeader** | `ui.tsx` `PageHeader()` | none | Most V1 screens | Single implementation. |
| **BrandLogo / wordmark** | `src/design/BrandLogo.tsx` | none (previously an `AdminPage`-adjacent ad-hoc "B" monogram existed in `_layout.tsx` for the compact/tablet rail — kept, not a duplicate, it's an intentional compact variant) | Sidebar, Login, Customer Portal | Single component, renders `assets/brands/buildcon-logo.png` — **unchanged this sprint** (a text-fallback fix was tried and explicitly reverted by the user, who wants the existing logo image kept as-is). |
| **AdminPage** (screen scaffold) | `src/components/AdminPage.tsx` | `src/components/ScaffoldScreen.tsx` (different purpose — "coming soon" placeholder, not a true duplicate) | AdminPage: Catalog Import, Quotations, Team, Settings, Notifications; ScaffoldScreen: Reports only | Not a real duplicate — different jobs (page chrome vs. placeholder). Naming could be clearer. |

## Orphan components (defined, zero usages found anywhere)

These are dead code — safe to delete in a future cleanup, **not removed now**
per "don't touch what isn't part of Batch 1":

- `ds.tsx`: `QuotationCard`, `CustomerCard`, `PurchaseCard`, `RoomCard`, `Stepper`, `ConfirmDialog`
- `ui.tsx`: `KpiCard`, `ListRow`, `BrandMark`, `PillTabs`, `SkeletonGrid`, `SkeletonRow`, `SectionHeader`
- `design/components.tsx`: `Dialog`

## Recommended consolidation order (future sprint — NOT this sprint)

1. **Sheet/BottomSheet (3 implementations → 1)** — highest visual-consistency payoff, matches the Batch 2 item already deferred by product decision. Do this together with the Modal→Sheet migration.
2. **Skeleton (2 implementations → 1)** — near-identical already, cheapest merge.
3. **EmptyState (2 implementations, same name)** — rename or merge to remove import ambiguity.
4. **SearchField adoption** — migrate the 6 screens with ad-hoc `TextInput` search bars onto the shared `SearchField`.
5. **Card / Surface / Panel (3 names → 1)** — bigger visual-risk item, needs design sign-off on final padding/radius rhythm.
6. **Button/IconButton prop-name unification** (`full` vs `fullWidth`) — cosmetic API cleanup, no visual change.

## Non-goals for this document

This inventory does **not** recommend merging the two design *systems*
(`src/design/*` vs `src/theme/tokens.ts` + `ui.tsx`) themselves — that is a
much larger decision (which typography/spacing rhythm wins for the whole
app) that belongs to a dedicated design-language sprint after the remaining
functional modules are complete, per explicit product direction.
