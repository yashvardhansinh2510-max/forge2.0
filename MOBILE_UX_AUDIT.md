# Forge 2.0 — Mobile UX/UI Handoff for Emergence

## Technical verdict

Mobile UX is **functional but not release-polished**. The dominant issue is not one isolated margin; it is inconsistent responsive composition across pages. Emergence should complete one mobile design-system pass before adding more UI:

1. Make `src/design/tokens.ts` the only spacing/type source. `src/theme/tokens.ts` and `src/design/tokens.ts` currently coexist, and screens mix both systems.
2. Make the shared page frame phone-aware. `src/components/AdminPage.tsx:45-66` always applies `layout.screenPadding.tablet`, so every settings/admin page inherits tablet padding on a phone.
3. Enforce 44×44 minimum touch targets. `src/design/components.tsx:112-195` and `src/components/ui.tsx:75-178` still expose 34–40px controls; small icon actions are visually compact and hard to hit.
4. Remove destructive one-line truncation from business data. Customer names, email/SKU/project metadata, prices, and pipeline labels need wrapping or a two-line layout, not `numberOfLines={1}` everywhere.
5. Use one breakpoint authority. Current code mixes `768/900/1024` and local width checks, which causes tablet/phone layouts to change at different points.

The live mobile login capture at 390×844 is stable and readable, but the full authenticated app could not be visually captured because the local backend is not running. The page-level findings below are therefore based on current source/layout evidence, with runtime verification limits called out.

![Mobile login capture](/Users/yashvardhansinhjhala/buildcon%20house/forge2.0/audit-evidence/01-login-mobile.png)

## Shared system fixes — highest priority

| Priority | Exact location | Finding | Required change |
|---|---|---|---|
| P0 | `frontend/src/components/AdminPage.tsx:45-66` | Phone pages receive tablet horizontal padding and the same top/bottom rhythm. | Use `useBp()` or a shared `useResponsiveSpacing()`; phone content padding 16–20, tablet 24–28, desktop 32–40. Add bottom safe-area padding to every scroll container. |
| P0 | `frontend/src/design/tokens.ts:96-119` and `frontend/src/theme/tokens.ts:276+` | Two typography systems define different display/body/caption sizes and families. | Consolidate to one `Text`, `Heading`, `Body`, `Caption`, `Money`, `Label` scale. Remove ad-hoc `fontSize: 10/11/12/13` from screen files except for approved metadata tokens. |
| P0 | `frontend/src/design/components.tsx:112-195`; `frontend/src/components/ui.tsx:75-178` | Button sizes include 34px and icon buttons commonly use 30–40px. | Keep visual icon at 16–20px but make hit area 44×44; make small buttons at least 44px high on native mobile. |
| P0 | `frontend/src/components/BottomSheet.tsx:28-41` | Sheet body has `paddingBottom: 0`; fixed footer can cover the final field/action when the keyboard or short viewport is present. | Add footer-height + safe-area bottom inset to sheet scroll content; verify keyboard open, error text, and long-form states. |
| P1 | `frontend/src/design/responsive.ts:8-21`; local checks in `followups.tsx:227-229`, `payments.tsx:87`, `purchases.tsx:115` | Breakpoints vary by screen: 640, 768, 900, 1024. | Define one phone/tablet/desktop contract and use it everywhere. Test 320, 375, 390, 430, 768, 1024. |
| P1 | `frontend/src/components/ui.tsx:451-473`, `frontend/src/design/components.tsx:775-825` | Shared headers force title/subtitle into one line in multiple places. | Allow title/subtitle to wrap to two lines; action cluster should move below or collapse to an overflow menu on narrow widths. |
| P1 | Screen-wide `numberOfLines={1}` usage | Long names, email, SKU, status, quotation number and metadata are clipped without a reveal affordance. | Use two-line clamp for primary data; allow horizontal scroll only for codes; expose full text in accessible label/press detail. |
| P1 | `frontend/src/components/quotation/*` and `frontend/src/components/ui.tsx` | Quotation screens and legacy screens use a separate visual language from newer showroom primitives. | Migrate remaining screens to the same surface, border, radius, button, field, and text primitives before further feature work. |

## Page-by-page review

### Authentication

| Page | Exact location | Required improvement |
|---|---|---|
| Staff/customer login | `frontend/app/(auth)/login.tsx:95-161` | Footer actions are 13px text links with only visual text affordance. Make them full-width/44px hit areas or stack them on phones. Keep the primary CTA full width. Error text currently occupies the password field's helper position; reserve stable error space so the form does not jump. |
| Login mobile hero | `login.tsx:166-181` | Fixed 216px hero + 32px top/24px side form padding is acceptable at 390×844 but consumes too much height on 320px or when the keyboard opens. Use a shorter 160–184px hero on compact-height devices and keep the logo/action above the fold. |
| Login | `login.tsx:89-92` | “Use demo account” and a known password are exposed in the production UI. Remove from production builds; keep behind a development flag. |
| Set new password | `frontend/app/(auth)/set-new-password.tsx:45-46` | Uses centered content with generic `spacing.xl`; verify with keyboard and validation errors. Make the form top-anchored on short phones, keep password rules visible, and keep submit CTA above the keyboard. |

### Admin shell/navigation

| Page/component | Exact location | Required improvement |
|---|---|---|
| Mobile bottom navigation | `frontend/app/(admin)/_layout.tsx:388-408` | Tabs use 10.5px labels and a 52px floating action button with a negative top margin. Add bottom safe-area inset, ensure each tab is ≥44px high, and make the FAB label/meaning explicit for screen readers. Test scroll content against the bar. |
| Sidebar/rail | `_layout.tsx:321-347` | Phone, tablet, and desktop switch between different navigation models. Preserve the current route label and a consistent “More” destination; do not hide secondary navigation without a discoverable replacement. |

### Dashboard

| Page | Exact location | Required improvement |
|---|---|---|
| Dashboard KPI grid | `frontend/app/(admin)/dashboard.tsx:198-216` | Phone tiles use `width: "46%"` plus `gap: space.x6` (24px). On 320–375px widths this creates cramped cards and uneven wrapping. Use a two-column grid with calculated width `((100%-gap)/2)` and a minimum card height. |
| Dashboard greeting/header | `dashboard.tsx:352-377` | Header/action spacing changes sharply by breakpoint. Allow greeting copy to wrap and move the action to a full-width row on narrow phones. |
| Up-next/business panels | `dashboard.tsx:386-390` | These are desktop-only; mobile users need a deliberate stacked order, not omission. Render the highest-value panel first and expose the second through a clear section/link. |
| Follow-up/quotation rows | `dashboard.tsx:69-86,281-294` | Customer/action text is one line and hover-only actions are hidden on touch. Provide explicit touch actions or a detail route; do not depend on hover. |

### Catalog

| Page | Exact location | Required improvement |
|---|---|---|
| Catalog index filter header | `frontend/app/(admin)/catalog/index.tsx:330-390` | Two horizontal pill rows plus active-filter chips and segmented mode control consume vertical space and create competing scroll axes. Collapse brands/categories behind a filter sheet on phones; retain only search + one active filter summary in the header. |
| Catalog cards | `catalog/index.tsx:729-764` | Card title is 14px with fixed `minHeight: 36`; overlines/pills are 9–10px. Increase title to 15–16px, allow two lines, and keep price/variant information from colliding with image overlays. |
| Catalog list/grid | `catalog/index.tsx:397-415` | `initialNumToRender={120}` on web and multi-column behavior are not phone-safe defaults. Use a phone-specific render count and verify scroll performance on low-memory Android. |
| Product detail | `frontend/app/(admin)/catalog/[id].tsx:266-350` | Long breadcrumb/brand metadata wraps, but pipeline rows at `394-418` reserve three small icon actions and one-line labels. Stack action buttons or use a single “More” action on phones; let customer/supplier names wrap. |
| Product specifications | `catalog/[id].tsx:353-378` | Two-column spec rows use `flex: 1` and `1.4`, right-aligning long values into a narrow column. On phones use label above value or a 40/60 grid with value left-aligned and wrapping. |

### Customers

| Page | Exact location | Required improvement |
|---|---|---|
| Customer list | `frontend/app/(admin)/customers/index.tsx:80-142` | Four stat tiles wrap on non-desktop, while search and filters follow immediately. Reduce stats to a horizontally scrollable compact strip or two intentional rows; do not let the first customer card start far below the fold. |
| Customer list card | `customers/index.tsx:191-207` | Company/name, email, city, tier and chevron compete in one row; email/city are `numberOfLines={1}`. Use name + secondary line, move tier into the trailing column, and put chevron in a 44px hit area. |
| Customer detail | `frontend/app/(admin)/customers/[id].tsx:194-240,380-388` | Stats and detail sections switch only at 900px and use horizontal content on smaller widths. Stack summary metrics, make tabs horizontally scrollable with visible selected state, and preserve section spacing after long customer names. |
| New/edit customer | `frontend/app/(admin)/customers/new.tsx:67-73`; `customers/[id]/edit.tsx` | Keyboard form should use the same phone padding, field gap, validation reserve space, and sticky submit action. Verify keyboard scroll to every field and error state. |

### Quotations

| Page | Exact location | Required improvement |
|---|---|---|
| Quotations list | `frontend/app/(admin)/quotations/index.tsx:61-162` | Ensure list rows wrap project/customer metadata and keep status/amount visible. Add empty/loading/error states with the same vertical rhythm as Customers and Payments. |
| Quotation builder | `frontend/app/(admin)/quotations/new.tsx`; `frontend/src/components/quotation/layout/BuilderShell.tsx`; `MobileControls.tsx` | This is the highest-risk mobile flow: product catalog, room lines, discounts, variant selection, description, swap, assistant, and finalization are all sheet-driven. Use one persistent mobile control bar; ensure it never overlaps the last line, keyboard, or safe-area inset. Reduce modal nesting and show a clear step title in every sheet. |
| Builder line rows | `frontend/src/components/quotation/canvas/LineRow.tsx`, `RoomHeaderRow.tsx` | Prevent SKU/name/finish/quantity/price from compressing into one row. On phones use a two-row line item: name + price, then finish/qty/actions. Make edit/delete/swap actions 44px. |
| Builder sheets | `frontend/src/components/quotation/sheets/*.tsx` | All sheets need consistent header, close affordance, scroll padding, keyboard behavior, primary CTA placement, and unsaved-change handling. Long descriptions and discount forms must not be clipped by fixed-height sheets. |

### Purchases and purchase orders

| Page | Exact location | Required improvement |
|---|---|---|
| Purchases tracker | `frontend/app/(admin)/purchases.tsx:248-319` | Header actions wrap into multiple rows, while the rail becomes full width. On phones convert search/export/shortage/move/settings into a single toolbar + overflow sheet; use compact horizontal stage filters instead of a long rail. |
| Purchases tracker rows | `purchases.tsx:1033-1093` | 10–12px labels, 18px checkboxes and 30px move buttons are too small for touch and dense with metadata. Use 44px controls and a two-line item layout; keep blocked state text readable without relying only on color. |
| Purchase order detail | `frontend/app/(admin)/purchase-orders/[id].tsx:265-617` | Multiple long forms and nested scroll regions need a single vertical scroll owner. Add sticky bottom action bar with safe-area padding, and verify attachments/status/receive dialogs above the keyboard. |
| Legacy purchase-orders index | `frontend/app/(admin)/purchase-orders/index.tsx:5` | This route is a legacy scaffold. Redirect it to the supported purchase flow or remove it from navigation; do not leave a dead/duplicate destination. |

### Follow-ups

| Page | Exact location | Required improvement |
|---|---|---|
| Follow-ups mobile header | `frontend/app/(admin)/followups.tsx:627-653` | Good intent: phone uses icon actions. Add visible labels/tooltips in the overflow/help surface and keep 44px targets. |
| KPI strip | `followups.tsx:655-682` | Six KPI tiles are horizontally scrollable. Make the first two task metrics visible by default, add a “More metrics” affordance, and avoid requiring horizontal discovery for critical overdue state. |
| Search/filter panel | `followups.tsx:687-756` | On phone the search becomes full width and actions wrap; this is likely where controls feel crowded. Put saved views/help in an overflow button, keep search full width, and make filter rows vertically grouped with 12–16px section spacing. |
| Follow-up detail sheet | `followups.tsx:849-856,1671-1725` | Verify nested context/detail and new-follow-up sheets with keyboard, long notes, validation errors, and bottom CTA. Add explicit “Close”/“Save” hierarchy and reserve 120px + safe-area bottom padding. |

### Payments

| Page | Exact location | Required improvement |
|---|---|---|
| Payments page | `frontend/app/(admin)/payments.tsx:192-396` | The page uses `spacing.xl` padding and desktop-only width logic; on phones this can make the content feel narrow while cards remain dense. Use phone padding 16–20 and stack summary, order detail, and actions with clear section labels. |
| Payment rows | `payments.tsx:287-311,428-450` | Titles/status/amount/actions compete horizontally. Keep customer/order number in the first line, amount/status in the second, and move reminder/download actions into a 44px action cluster. |
| Record payment sheet | `payments.tsx:483-570,576-596` | Inputs/buttons are 40px in places. Increase to 44–48px, keep outstanding balance visible while typing, and ensure error text does not move the confirm action off-screen. |

### Reports, notifications, and settings

| Page | Exact location | Required improvement |
|---|---|---|
| Reports | `frontend/app/(admin)/reports.tsx:7` | This is a minimal route compared with the rest of the product. Provide a deliberate mobile empty/coming-soon state or remove the route from navigation; avoid a page that appears unfinished. |
| Notifications | `frontend/app/(admin)/notifications.tsx:39-86` | Notification title is one line and metadata is compact. Allow title to wrap to two lines, add unread/read contrast that does not rely only on a small dot, and provide empty/error states. |
| Settings hub | `frontend/app/(admin)/settings.tsx:102-235` | Settings groups are card-heavy and rely on shared `AdminPage` tablet padding. Use grouped list rows with 56px minimum height, stronger section separation, and a consistent trailing chevron/value. |
| Company/PDF/notifications/password/catalog/system | `settings-company.tsx:66-67`, `settings-pdf.tsx:56-57`, `settings-notifications.tsx:49-50`, `settings-password.tsx:39`, `settings-catalog.tsx:26-27`, `settings-system.tsx:41-42` | These pages all inherit the same frame but contain different forms/data densities. Add a shared phone form template: label → field → helper/error, 16px section gap, sticky save CTA, and safe-area keyboard handling. System diagnostics should use wrapped key/value rows rather than narrow right-aligned values. |
| Permissions/team | `settings-permissions.tsx:73-98`; `team.tsx:154-238` | Tables/role matrices and member forms need mobile row cards. Avoid horizontal table scrolling for primary permissions; use role selector + permission groups with expandable rows. |

### Customer portal

| Page | Exact location | Required improvement |
|---|---|---|
| Portal home | `frontend/app/(customer)/home.tsx:39-70` | Fixed 240px hero plus 30px single-line company name can clip long company names. Allow two lines and reduce hero height on compact phones. The sign-out pill is visually small; use a 44px hit area. |
| Portal account card | `home.tsx:70-90` | Email and phone rows should wrap rather than overflow on narrow phones. Keep icons in a fixed 24px column and give text `minWidth: 0`. |
| Latest quotation card | `home.tsx:110-126` | Date/item count, status, total, and View action are dense. Stack the status under the quotation number on phones and keep total/action in a separate row. |
| Quotation list | `frontend/app/(customer)/quotes/index.tsx:43-82` | Amount/status/chevron fit in one row but long dates/revision/validity metadata become cramped. Use a two-line metadata block and a full-card 44px touch target. |
| Quotation detail | `frontend/app/(customer)/quotes/[id].tsx:64-140` | Line items use two columns with a right-aligned price. For long item names/SKUs, use name + metadata above and price below/right; preserve PDF CTA as a sticky or repeated bottom action after long quotations. |

## Accessibility and interaction gates

- Test Dynamic Type / large text: no essential label may disappear because of `numberOfLines={1}`.
- Test VoiceOver/TalkBack: every icon-only action must have an accessible label and state; every segmented/filter control must announce selection.
- Test 44px hit targets, keyboard focus order, and keyboard dismissal on every sheet/form.
- Test 320px width, 390px width, landscape phone, iPad/tablet, and long localized strings.
- Test loading, empty, error, offline, disabled, selected, validation, and success states for every data page.
- Test bottom navigation, FABs, sheets, and sticky footers with safe-area insets.
- Test no hover-only action exists on touch (`dashboard.tsx:86` is a concrete example).

## Evidence limits

- Captured and inspected live: login at 390×844 (`audit-evidence/01-login-mobile.png`).
- Not visually verified in this run: authenticated staff/customer routes, because the local frontend was available but its backend API was not running.
- Static evidence is current source code, not a substitute for device testing. Emergence should implement the shared fixes, then run the device matrix above before calling the mobile UX work complete.

## Final handoff verdict

**Necessary work: one shared responsive-system pass, followed by targeted fixes to the quotation builder, catalog filters/cards, purchases tracker, payments, settings forms, and customer portal.** Do not treat this as isolated padding cleanup; the current inconsistencies come from duplicate design systems, inconsistent breakpoints, fixed one-line data rows, and undersized touch controls.
