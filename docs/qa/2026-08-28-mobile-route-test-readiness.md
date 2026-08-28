# Mobile Route and Test-Readiness Review

**Date:** 2026-08-28  
**Scope:** Route inventory and automated-testing readiness for the mobile release brief. No application source was changed.

## Executive result

**Release recommendation: Block.**

The Expo Router inventory is largely present, and the existing static mobile UX contract, web budget check, and lint command pass. However, the required viewport, interaction, accessibility, visual-regression, device-navigation, and realistic-fixture suites do not exist or cannot be executed from the repository. No route has current evidence for the requested eight viewports or runtime conditions. A verified Notifications request failure is also presented to the user as an empty inbox.

## Executed evidence

| Check | Result | Evidence |
| --- | --- | --- |
| `npm run lint` | Pass | `expo lint` exited 0. |
| `npm run test:mobile-ux` | Pass | 26 static source assertions. The script checks a limited safe-area route list, selected follow-up/list ownership patterns, a sheet migration, catalog breakpoint use, TileTable ownership, and System Settings only. |
| `npm run test:mobile-budget` | Pass with low dashboard headroom | Login: 497 KiB gzip; Dashboard: 505 KiB gzip; limit: 512 KiB. |
| Browser/device/visual test discovery | Not available | `package.json` contains no Playwright, Jest, Detox, Maestro, Appium, visual-snapshot, accessibility, or performance-profiler runner/configuration. Existing `test:*` scripts are source-level contract scripts. |

The bundle guard itself only evaluates `login.html` and `dashboard.html` (`frontend/scripts/check-web-budget.mjs:8`), so its successful result is not evidence for the other primary routes.

## Primary route matrix

Status meanings: **Mapped** = route/source located; **Redirect** = route exists but is not a standalone screen; **Unmapped** = no dedicated Expo Router path; **Not executed** = no current automated runtime evidence for the requested mobile conditions.

| Release-brief screen | Expo Router path / implementation | Preliminary status |
| --- | --- | --- |
| Login | `/login` — `app/(auth)/login.tsx`; `/` redirects unauthenticated users here | Mapped; not executed |
| Dashboard | `/dashboard` — `app/(admin)/dashboard.tsx` | Mapped; budget checked only; not executed |
| Orders | No `app/(admin)/orders*` route exists. Operational purchase tracker is `/purchases`. | **Unmapped** — product owner must confirm replacement/rename |
| Purchase Orders | `/purchase-orders` redirects to `/purchases`; detail remains `/purchase-orders/[id]` | Redirect; not executed |
| Tile Orders | `/tiles/orders` — `app/(admin)/tiles/orders/index.tsx` | Mapped; not executed |
| Dispatch | No direct `/dispatch` route. It is the **Dispatch List** tab within `/tiles/orders`. | Mapped as in-screen tab; not independently deep-linkable; not executed |
| Product Catalog | `/catalog` — `app/(admin)/catalog/index.tsx` | Mapped; not executed |
| Product Detail | `/catalog/[id]` — `app/(admin)/catalog/[id].tsx` | Parameterized route mapped; not executed |
| Quotations | `/quotations` — `app/(admin)/quotations/index.tsx` | Mapped; not executed |
| Quotation Builder | `/quotations/new` — `app/(admin)/quotations/new.tsx` | Mapped; not executed |
| Payments | `/payments` — `app/(admin)/payments.tsx` | Mapped; limited static safe-area check only; not executed |
| Follow-ups | `/followups` — `app/(admin)/followups.tsx` | Mapped; limited static list-ownership check only; not executed |
| Customers | `/customers` — `app/(admin)/customers/index.tsx` | Mapped; limited static safe-area check only; not executed |
| Notifications | `/notifications` — `app/(admin)/notifications.tsx` | Mapped; verified failed-request defect (QA-001) |
| Settings | `/settings` — `app/(admin)/settings.tsx` | Mapped; not executed |
| Customer portal | `/home`, `/quotes`, `/quotes/[id]` under `app/(customer)`; `/` redirects customer users to `/home` | Mapped; not executed |

Expo Router group names are omitted in user-facing URL paths. References above identify the exact source file where needed.

## Viewport and condition matrix

No browser/device test runner is configured; every cell is **NE** (not evidenced), rather than a pass/fail result.

| Route group | 320×568 | 375×667 | 390×844 | 430×932 | 768×1024 | 820×1180 | 1024×768 | 1366×768 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Login, Dashboard, Purchases/POs | NE | NE | NE | NE | NE | NE | NE | NE |
| Tile Orders/Dispatch | NE | NE | NE | NE | NE | NE | NE | NE |
| Catalog/Product detail | NE | NE | NE | NE | NE | NE | NE | NE |
| Quotations/Builder, Payments | NE | NE | NE | NE | NE | NE | NE | NE |
| Follow-ups, Customers, Notifications, Settings, Customer portal | NE | NE | NE | NE | NE | NE | NE | NE |

Portrait/landscape, keyboard, home-indicator safe area, long text, empty/large datasets, delay/failure/retry, offline/reconnect, dark mode, large text, VoiceOver/TalkBack, Android back, and iOS swipe-back are likewise not currently evidenced by an executable suite.

## Verified findings

### High

#### QA-001 — Notifications converts an API failure into a successful empty state

**Location:** `frontend/app/(admin)/notifications.tsx:27-51`  
**Evidence:** The sole request calls `.catch(() => setItems([]))`; the following UI renders “You're all caught up” for every empty list. A network/auth/server failure is therefore indistinguishable from an empty inbox and provides no retry path.  
**Impact:** Violates the brief's failed-request/retry/recovery requirements and can suppress actionable alerts.  
**Reproduction:** Disable/intercept `GET /notifications`, open `/notifications`, wait for the request to settle; the empty-success UI appears instead of an error state.

#### QA-002 — Required runtime regression coverage is absent

**Evidence:** `frontend/package.json:5-18` exposes only lint, source-contract, and bundle scripts. Dependency discovery found no E2E/device/visual/accessibility runner. The current mobile contract is static text matching (`scripts/test-mobile-ux-contract.mjs:1-50`) and does not launch a route or set a viewport.  
**Impact:** Every acceptance rule that depends on rendered layout, interaction, focus, touch geometry, scroll physics, device back behavior, or network state is unverified. The release brief expressly requires these suites.

### Medium

#### QA-003 — “Orders” is not a routable primary screen; Purchase Orders is a redirect

**Evidence:** No `app/(admin)/orders*` file exists. `app/(admin)/purchase-orders/index.tsx:1-6` documents and implements a redirect to `/purchases`.  
**Impact:** The requested primary-route inventory cannot be tested one-for-one, and direct navigation/analytics expectations for Orders and Purchase Orders need product confirmation.

#### QA-004 — Dispatch is not independently addressable

**Evidence:** The only dispatch operational entry is the `Dispatch List` tab in `/tiles/orders` (`app/(admin)/tiles/orders/index.tsx:49-61`); there is no `app/(admin)/dispatch*` route.  
**Impact:** An operational workflow can be tested through Tile Orders, but cannot be tested or linked as a first-class Dispatch route from the release inventory.

#### QA-005 — Dashboard's web payload has only 7 KiB budget headroom

**Evidence:** Current `test:mobile-budget` output is 505 KiB gzip against a 512 KiB limit. The guard rounds reported values, so the exact headroom should be re-measured before treating it as a hard 7 KiB margin.  
**Impact:** A small shared-shell or dashboard dependency increase can turn the release check red. This is a budget risk, not a measured first-interactive-render result.

## Performance and accessibility result

No timing, navigation-latency, interaction-response, FPS, memory, React profiling, or duplicate-request measurement is presently executable from the frontend tooling. The two bundle measurements above are static production-output sizes only; they cannot demonstrate the brief's under-2-second interactive target or 100 ms interaction targets.

Accessibility labels and test IDs exist in some route source (for example, tile and follow-up controls), but no automated role/name/focus/announcement audit or VoiceOver/TalkBack session is configured. This is implementation evidence only, not an accessibility pass.

## Required follow-up before a release decision can change

1. Add an executable viewport/interaction suite that boots the app with deterministic auth and fixtures, covering all matrix entries and required failure/retry/back flows.
2. Add screenshot baselines for the main operational flows and an accessibility audit that checks labels, roles, focus management, and sheet dismissal.
3. Add realistic 1,000+ product / 500+ order fixtures plus image, delayed-response, partial-failure, offline, and reconnect cases; measure runtime/FPS/memory/profiling against the stated targets.
4. Fix QA-001 and add a regression test for the failure and retry UI.
5. Confirm whether `/purchases` is the intended replacement for the release brief's **Orders** and **Purchase Orders**, and whether the Dispatch tab needs a direct URL.

## Files changed

- `docs/qa/2026-08-28-mobile-route-test-readiness.md` — this review report only.
