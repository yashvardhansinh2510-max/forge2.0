# Mobile UI and accessibility audit — 2026-08-28

## Scope and method

Static, code-backed review of the Expo phone shell and the release-brief routes, with emphasis on scroll ownership, safe-area/bottom-bar clearance, modal focus, target size, screen-reader names, and non-colour status communication. The review covered the shared `AppScaffold`, `Sheet`, `Screen`, admin phone navigation, Login, Dashboard, Catalog, Customers, Purchases, Payments, Follow-ups, Notifications, Settings, Tile Orders, Quotations, and Customer Portal route/component paths.

Validated checks:

- `npm run test:mobile-ux` — passed (26 assertions).
- `npm run lint` — passed.
- `npx tsc --noEmit` — passed.

These are static checks, not emulator/device or VoiceOver/TalkBack sessions. No screenshots were produced because this audit did not launch an authenticated app session.

## Findings

### Serious — MOB-A11Y-01: Purchases filters is an unnamed icon-only control

- **Route:** Purchases phone workspace (`/(admin)/purchases`).
- **Impact:** A VoiceOver/TalkBack user cannot reliably discover the control that opens the only brand/stage filter workflow. The button exposes only a sliders icon (and, when active, a count), with no accessible name, role, or expanded/active state.
- **Evidence:** `app/(admin)/purchases.tsx:407` renders `purchases-filter-button` with a `Feather` icon but no `accessibilityLabel`, `accessibilityRole`, or `accessibilityState`.
- **Reproduction:** Sign in on a phone-sized viewport; navigate to Purchases; enable VoiceOver/TalkBack; move focus to the control beside search. It is announced without an action-identifying name (or only as the active-filter count), rather than “Filter purchases”.
- **Acceptance rule affected:** Accessible core workflow; screen-reader labels and roles.

### Serious — MOB-A11Y-02: Purchases sheets and dialogs do not create an accessible modal boundary

- **Route:** Purchases phone workspace (`/(admin)/purchases`): item actions, filters, purchase actions, remove confirmation, bulk move, SLA settings, and shortages.
- **Impact:** Screen-reader focus is not constrained to the overlay, no initial focus target is set, and focus restoration on dismissal is absent. A user can traverse and activate controls behind the open sheet/dialog, including underlying operational actions. The shared `Sheet` does set `accessibilityViewIsModal`; these custom overlays bypass it.
- **Evidence:** Custom `<Modal>` implementations at `app/(admin)/purchases.tsx:801, 827, 855, 1203, 1230, 1288, 1345` have no `accessibilityViewIsModal`, dialog role, or focus management. Compare `src/design/components.tsx:532-545`, the shared sheet implementation used elsewhere.
- **Reproduction:** On a phone, open Purchases → Filters or an item’s actions; with VoiceOver/TalkBack enabled, swipe past the sheet’s last control. Focus can continue into the background list/bottom navigation rather than remaining in the modal. Dismiss and note that focus is not restored to the invoking control.
- **Acceptance rule affected:** “No sheet opens without correct focus and dismissal behavior”; critical screen-reader workflow.

### Serious — MOB-UI-03: Purchases confirmation/settings dialogs overflow the 320 px mobile viewport and do not avoid the keyboard

- **Route:** Purchases phone workspace (`/(admin)/purchases`) → item actions → Remove from active purchases; More actions → Tracker settings.
- **Impact:** At the required 320×568 viewport, both dialogs have a fixed 340 px width inside a 20 px-per-side modal inset, leaving only 280 px usable width. The right 60 px is clipped. Both dialogs also contain `TextInput`s but use neither `KeyboardAvoidingView` nor a scrollable dialog body, so the confirmation/save controls can be covered by the software keyboard. This blocks an operational destructive-flow confirmation and a settings update.
- **Evidence:** `styles.settingsCard` is `width: 340` with no `maxWidth` at `app/(admin)/purchases.tsx:1629`; its native backdrop applies `padding: 20` at `app/(admin)/purchases.tsx:1561-1565`. `CancelPurchaseModal` and `SettingsModal` render an input inside this card at `app/(admin)/purchases.tsx:1203-1217` and `1288-1314`, respectively, without `KeyboardAvoidingView`.
- **Reproduction:** Use a 320×568 device/emulator; open either dialog; observe horizontal clipping. Focus the Reason or SLA input and open the keyboard; the dialog is not repositioned/resized and its bottom action row can be obscured.
- **Acceptance rule affected:** No clipped/unreachable actions; keyboard-open behavior; safe interaction for destructive actions.

## Confirmed positive controls

- The admin phone shell delegates top/side safe areas to `AppScaffold` and bottom safe area to its navigation container. The existing mobile UX contract confirms the expected edge configuration.
- Catalog and Purchases use virtualized `FlatList` configurations on phone paths; the audited Purchases list has one vertical owner and a 96 px terminal spacer for the 62 px bottom bar plus a typical home indicator.
- The shared `Sheet` has a backdrop dismiss affordance, Android request-close handler, keyboard avoidance, safe-area padding, and an accessibility modal boundary. Migrating the custom Purchases overlays to this primitive would remove most of MOB-A11Y-02 and MOB-UI-03.
- Status components generally pair colour with words/icons (`StatusBadge`, `StatusPill`, notification icons); no validated colour-only status defect was found in the reviewed paths.

## Release recommendation

**Block** for accessibility and small-phone readiness until the three serious findings are remediated and verified on 320×568 and a safe-area phone with VoiceOver/TalkBack. The passing static contracts are useful regression coverage but do not exercise these custom modal paths or assistive-technology focus behavior.
