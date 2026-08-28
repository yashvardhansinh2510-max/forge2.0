# Mobile Performance & Reliability Review — 2026-08-28

## Release recommendation: **Block**

Scope was source-level performance/reliability review plus the safe, existing frontend checks. No application source was changed. Runtime route, slow-network, memory, frame-rate, screen-reader, and visual measurements remain unexecuted because this workspace has no configured browser/E2E runner or authenticated test session. Therefore the release brief's measured targets (interactive render under 2 s, navigation under 100 ms, approximately 60 fps, and repeated-navigation memory) are **not verified**.

## Commands and results

| Command | Result |
|---|---|
| `cd frontend && yarn test:mobile-ux` | Pass — 26 static assertions for shell/safe-area/list ownership contracts. |
| `cd frontend && yarn test:mobile-budget` | Pass — login 497 KiB gzip and dashboard 505 KiB gzip, both within the 512 KiB initial-JS cap. Dashboard has only 7 KiB (1.4%) remaining. |
| `cd frontend && yarn lint` | Pass — no lint findings. |

The budget command measures only the pre-existing `dist/client` assets for login and dashboard; it does not build the current source or cover the operational routes.

## Blocking defect

### P0 — Catalog-import review defeats virtualization and creates an unbounded write burst

**Evidence:** `frontend/app/(admin)/catalog/import.tsx:221` places `current.rows` in a `FlatList` with `scrollEnabled={false}` inside `AdminPage`, whose default outer container is a vertical `ScrollView` (`frontend/src/components/AdminPage.tsx:31`). With the inner list unable to own scrolling, React Native must lay out all rows. The import review row is itself a multi-control card. The release fixture of 1,000+ products therefore creates the exact high-volume, whole-list render prohibited by the release brief.

The same screen's `acceptAll` (`catalog/import.tsx:109-114`) synchronously sets every row accepted and launches `Promise.all` over every row PATCH without `await`, a concurrency cap, error handling, cancellation, retry summary, or a busy/disabled state. A 1,000-row import immediately creates 1,000 concurrent writes. The user may then press **Import** while those status writes remain in flight (`catalog/import.tsx:158-167`), producing a race between row persistence and approval.

**Reproduction:** upload or open an import containing 1,000 rows; choose **Accept all**; inspect the network panel. Expect one `PATCH /api/catalog/imports/{job}/rows/{row}` per row concurrently, then press **Import** before the requests settle. On a throttled or failed connection, the UI has already shown all rows accepted while an unknown subset is persisted.

**Impact:** severe interaction and memory pressure, possible rate-limit/backend overload, and import approval with partial/unpersisted selection state. This violates the high-volume-list, failed-request/retry, and accidental duplicate/request acceptance gates.

**Required remediation before release:** make this a server-side bulk endpoint (or bounded, awaited worker with per-row failure accounting); disable **Accept all** and **Import** while it runs; show completed/failed counts and retry only failed rows. Give the review screen one scroll owner and keep a virtualized `FlatList` as that owner, or page the server results.

## Important non-blocking findings

### P1 — Stale responses can overwrite current state on several core/detail routes

The shared API client supports caller-provided `AbortSignal` and has a 30-second timeout (`frontend/src/api/client.ts:58-123`; equivalent web client exists). Some high-churn screens use it correctly: catalog uses a request id, purchases aborts previous requests, and tile index routes invalidate stale requests. In contrast, several detail and dashboard routes invoke `load()` from an effect with neither an abort signal nor request-id guard, including:

- Dashboard: `frontend/app/(admin)/dashboard.tsx:126-151`
- Purchase-order detail: `frontend/app/(admin)/purchase-orders/[id].tsx:243-265`
- Walk-in detail: `frontend/app/(admin)/walkins/[id].tsx:43-53`
- Tile customer and brand PO details: `frontend/app/(admin)/tiles/orders/[id].tsx:83-103`, `frontend/app/(admin)/tiles/orders/po/[poId].tsx:61-81`
- Follow-ups bootstrap and detail selection: `frontend/app/(admin)/followups.tsx:287-367`

**Reproduction:** under delayed API responses, refresh/re-enter a route or choose follow-up A then B before A resolves. The earlier request may set loading/data/error after the later interaction. In dashboard specifically, an initial load and pull-to-refresh can finish out of order.

**Required follow-up:** standardize an abort/request-sequence helper and use it for route fetches, especially detail/selection screens. Ensure the `finally` branch is also sequence-checked so stale requests cannot clear a newer loading state.

### P1 — Import editing writes on every keystroke and has no recovery state

Each `TextInput` in an import row calls `editField`, which immediately PATCHes that field (`frontend/app/(admin)/catalog/import.tsx:125-129, 231-271`). There is no debounce, abort, ordering token, save indicator, retry state, or rollback. Slow responses can persist values out of order; a temporary failure leaves optimistic local data visually successful. This compounds the P0 high-volume issue.

**Required follow-up:** debounce/commit on blur, serialize by row+field, and expose save/retry/error status before approval.

### P2 — Budget coverage is narrow and too close to its cap

The sole budget check enumerates `login.html` and `dashboard.html` (`frontend/scripts/check-web-budget.mjs:7`) and reports dashboard at 505/512 KiB gzip. Catalog, quotation builder, purchase/dispatch, and customer-portal bundles are unmeasured. The command also consumes a prior export instead of producing one, so it cannot prove the current commit stays within budget.

**Required follow-up:** make the budget job build first; cover all primary operational entry points; preserve per-route historical output and fail at a lower warning threshold (for example 90%) before the hard cap.

## Positive controls observed

- Shared API clients deduplicate concurrent identical GETs, cache only explicit short-lived reads, clear cache after mutations, support 30-second timeouts, and propagate cancellation.
- Catalog, purchases, customer workspace, customer portal, and tile listing pages contain pagination and/or request-sequence protections. This is a useful pattern to extend rather than replace.
- Action buttons based on the shared design Button disable while `loading`; the inspected create/release/place-order flows use a busy state, reducing ordinary double submissions.
- The existing mobile contract check passes its safe-area, sheet, and selected list-ownership assertions.

## Coverage and remaining risk

No automated viewport regression, visual comparison, accessibility scan, delayed-network scenario, offline/reconnect test, React profile, navigation timing, FPS trace, or memory soak was runnable from the declared frontend scripts. The repository also has no Playwright/Vitest configuration in `frontend/`. The release brief requires these tests across all listed routes and eight viewports; passing three static/build checks is not a substitute.

Before reconsidering release, run authenticated production-like tests at 320×568, 390×844, 768×1024, and 1366×768 at minimum, then complete the remaining specified viewports. Capture network waterfalls, duplicate request counts, JS heap after repeated navigation, and scroll/frame traces for 1,000+ product and 500+ order fixtures. Add explicit delayed/failed request tests for import approval, dispatch creation, POD capture, form submission, and sheet/detail selection.

## Files changed

- `docs/qa/2026-08-28-performance-reliability-review.md` — this review report only.
