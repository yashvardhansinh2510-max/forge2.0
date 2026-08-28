# Mobile UX remediation inventory

Completed before implementation on 2026-08-28. This document is the source of
truth for the migration; it complements the detailed visual findings in
`MOBILE_UX_AUDIT.md`.

## Route and ownership inventory

| Route family | Current primary vertical owner | Mobile shell/safe-area status | Risk / migration batch |
| --- | --- | --- | --- |
| `/(auth)/*`, `/`, `/privacy`, `/terms` | Route `ScrollView` or form | Outside admin shell | Validate keyboard and compact height separately |
| `/(customer)/*` | Route `ScrollView` | Customer shell owns its own insets | Customer portal batch |
| `/(admin)/dashboard`, `reports`, `notifications`, `team` | Route `ScrollView` / `AdminPage` | Must use no top inset on phone | Shell audit batch |
| `walkins/*`, `customers/*`, `catalog/*` | Route `ScrollView`; catalog lists use `FlatList` | Several legacy routes still request `top` | Catalog/customer batch |
| `quotations/*` | Lists use `FlatList`; builder owns its own canvas/list | Place-order used duplicate phone top inset | Quotation batch |
| `purchases`, `purchase-orders/*`, `payments*`, `followups*` | Mixed `FlatList`, `ScrollView`, and `SectionList` | Payments List used duplicate phone top inset | Operations batch |
| `tiles/*` | `TileLayout` / editor `ScrollView`; picker list is modal-isolated | Mobile tiles editor used duplicate top inset | Tiles/dispatch batch |
| `settings*`, `sales-data/*`, `notebook/*` | Mostly `AdminPage` plus route scroll/form | Settings has nested owners in six routes | Settings then analytics/notebook batch |

The complete route set is under `frontend/app/`, including all sales-data
subroutes. Horizontal chip rails and image galleries are permitted; they are
not vertical scroll owners.

## Defect map

1. **Nested vertical scrolling:** `app/(admin)/followups.tsx` places a
   `SectionList` inside its primary vertical `ScrollView` with scrolling
   disabled. `AdminPage` also wraps an inner vertical scroll in settings
   company, notifications, password, PDF, catalog, and permissions routes.
2. **Duplicate safe areas:** `AppScaffold` owns phone top and bottom safe areas.
   Before this batch, Tile editor, quotation place-order, and Payment List also
   requested `top`; other legacy routes remain in the audit queue.
3. **Sheets:** `design/components.tsx:Sheet`, legacy `BottomSheet`, and local
   modal sheets coexist. The shared `Sheet` is the target primitive; migration
   must preserve callers' business actions and add focus return tests.
4. **Breakpoints:** canonical viewport tiers are 0–767, 768–1023,
   1024–1365, and 1366+. The builder has intentionally centralized
   container-width thresholds. Product image management and tile picker used
   local viewport checks and are migrated in this batch.
5. **List performance:** catalog, purchases, tile orders, and quotation lists
   already use virtualized owners. Follow-ups, customers, payments, and several
   settings/data pages need explicit virtualization review before declaring the
   acceptance gate met.

## Component ownership map

```
AppScaffold (phone only)
  ├─ top/side safe area
  ├─ Slot: exactly one route-owned vertical content surface
  └─ normal-flow bottom navigation + bottom safe area

Route list surface: FlatList / SectionList / ScrollView (one only)
  ├─ ListHeaderComponent: header, filters, summary, banners
  └─ ListFooterComponent: empty/end state and content inset

Sheet (shared primitive)
  ├─ modal/backdrop/back handling
  ├─ close control, safe area, keyboard avoidance
  └─ one internally-owned ScrollView and visible footer actions
```

## Desktop-safe migration order

1. Lock the scaffold insets, responsive contract, and shared-sheet behavior.
2. Remove duplicate scroll and safe-area ownership in settings, follow-ups, and
   tile operations.
3. Migrate list surfaces in small operational batches: catalog/orders,
   quotations, payments/follow-ups, then settings.
4. Run lint, contract checks, viewport checks, and device QA after each batch.

No backend routes, permissions, API contracts, floor rules, or data models are
part of this plan.

## Implemented in Phases 2 and 3

- `AppScaffold` remains the sole phone safe-area and normal-flow bottom-nav
  owner. The admin routes audited in this pass now skip their local `top` edge
  on phones while retaining it for tablet and desktop.
- Legacy `BottomSheet` callers now delegate to the design-system `Sheet`.
  This covers the catalog filter and quotation helper sheets without changing
  their public API.
- The phone Follow-ups inbox now uses a virtualized `SectionList` as its only
  vertical owner, with operational header/filter content in
  `ListHeaderComponent`. Desktop keeps its existing split-pane layout.
- Company, notification, password, PDF, and catalog settings pages now let
  `AdminPage` own their sole vertical scroll surface. Permissions already used
  one vertical owner and a separate horizontal control rail. System diagnostics
  now explicitly make its refreshable route `ScrollView` the sole owner too.
- Parent-owned Tile Orders tables now render their bounded page inside the
  route scroll surface instead of creating a second vertical table scroller.
  Self-owned table surfaces retain their `FlatList` virtualization; desktop
  horizontal table overflow is unchanged.
- `npm run test:mobile-ux` is the source-level regression gate for scaffold
  edges, the shared sheet adapter, the phone Follow-ups list, and responsive
  bypasses addressed here.

## Phase 4 evidence and limits

The web app was built successfully for all static routes with a non-routable
HTTPS API URL, and the unauthenticated login route was checked in a real browser
at 320, 375, 390, 430, 768, 820, 1024, and 1366px without horizontal overflow.
Authenticated, read-only browser QA also covered the mobile catalog filter
sheet, team sheet, More sheet, Follow-ups (256 records), and Payments (20 active
orders), plus Payments at 768×1024 and 1024×768. These checks found no horizontal
overflow; sheets closed with Escape and returned focus to their opener. No
record-mutating control was used.

Physical iOS/Android hardware, system screen readers, slow-network behavior,
and native keyboard/orientation testing still require device-lab evidence; those
checks cannot be truthfully inferred from a desktop web browser.
