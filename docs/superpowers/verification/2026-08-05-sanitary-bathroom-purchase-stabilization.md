# Sanitary Bathroom Purchase Stabilization Verification

Date: 2026-08-05
Scope: Task 7 of `docs/superpowers/plans/2026-08-05-sanitary-bathroom-purchase-stabilization.md`

## Outcome

At the isolated `751658c` snapshot, the focused sanitary regression gate, configured backend unit suite, and frontend lint completed without test/lint errors: `82 passed, 51 warnings`, `876 passed, 274 warnings`, and `10 warnings`, respectively. TypeScript also passed in the review environment, but only with locally generated, ignored `.expo/types` present; a clean snapshot requires that generation prerequisite before the TypeScript result is reproducible.

The Expo web workflow rendered the Sanitary Purchases and Customer Purchases surfaces at desktop, tablet, and 375 px widths without horizontal document overflow. This was not a strictly read-only verification: backend startup may run migrations and reconciliation, and demo authentication may write session and activity records. No deliberate purchase, dispatch, or Chalan mutation was performed through the UI, and no frontend regression requiring a code fix was demonstrated, so this verification changes only this report.

Release is not ready without resolving the critical default-password preflight finding. Mutating UI acceptance, the browser PDF/history/empty/error matrix, native simulator proof, and EAS/store readiness remain explicitly unverified as detailed below.

## Automated evidence

### Isolated-commit focused backend suites — passed

Command (repository root):

```text
backend/.venv/bin/pytest backend/tests/unit/test_purchases_tracker_bulk_move.py backend/tests/unit/test_customer_purchase_workspace_filters.py backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_purchases_chalan_lifecycle.py backend/tests/unit/test_pdf_chalan.py backend/tests/unit/test_purchases_chalan_permissions.py backend/tests/unit/test_purchases_tracker_floor_scoping.py backend/tests/unit/test_customer_routes_floor_scoped_lookups.py backend/tests/unit/test_purchases_move_permissions.py backend/tests/unit/test_purchases_tracker_concurrency.py -q
```

Result at the isolated commit: exit 0; `82 passed, 51 warnings`. The warnings are FastAPI `Query(regex=...)` and Pydantic v2 deprecations; no focused failure occurred.

This gate covers bulk 1/5/20 and partial-result behavior, mixed selections, empty selection and move permissions, composable workspace filters and the 300-row query-count regression, Chalan lifecycle/idempotency/concurrency, PDF generation, Chalan permissions, and floor scoping. Existing committed tests specifically cover rejection of an invalid Chalan movement/stage without mutation or event emission, and Chalan quantity safety through over-release rejection, partial-then-complete cumulative limits, concurrent release, and concurrent item-quantity replacement.

### Complete backend suite

Required literal command from the repository root:

```text
backend/.venv/bin/pytest -q
```

Result: exit 3 during collection. The tracked root-level `test_failfast.py` is a standalone executable check that calls `sys.exit(0)` at import time after intentionally verifying that `MONGO_URL` is missing when local fallback loading is disabled. Collection also reaches `pdf_image_test.py`, which imports unavailable `PyPDF2`, as well as other root-level executable/network scripts matching pytest's filename patterns. Running from the repository root bypasses `backend/pytest.ini`'s `testpaths = tests/unit` boundary. This is a repository test-discovery/layout blocker, not evidence that the sanitary assertions failed.

Configured complete backend suite:

```text
cd backend && .venv/bin/pytest -q
```

Result at the isolated commit: exit 0; `876 passed, 274 warnings`. Warnings are existing FastAPI/Starlette/Pydantic deprecations.

### Frontend checks

```text
cd frontend && npx tsc --noEmit
```

Result: exit 0; no output.

This pass depended on locally generated, gitignored `frontend/.expo/types` declarations. Because `frontend/tsconfig.json` includes `.expo/types/**/*.ts`, a clean snapshot needs the Expo type-generation prerequisite before `npx tsc --noEmit`; the result is not standalone clean-checkout proof without that step.

```text
cd frontend && npm run lint
```

Result at the isolated commit: exit 0; `10 problems (0 errors, 10 warnings)`. No warning is in either allowed Task 7 screen. Existing warnings include `react-hooks/exhaustive-deps` findings in `src/components/purchases/MovementEngine.tsx` plus unrelated unused/import/dependency warnings. No automatic fix was run.

## Web workflow evidence and write caveat

Commands:

```text
cd backend && .venv/bin/uvicorn server:app --host 127.0.0.1 --port 8010
cd frontend && EXPO_PUBLIC_ENABLE_DEMO_AUTH=true npm run web -- --port 8081
```

The first API launch on port 8000 was stopped after the checked-in `frontend/.env` was found to target `http://localhost:8010`; the configured 8010 launch then reached `Application startup complete`. Both development servers and the browser task were stopped after verification, and no listeners remained on ports 8010 or 8081.

These actions were not strictly read-only. Backend startup can execute migrations and reconciliation work, while demo sign-in can create or update session and activity records. The UI inspection avoided intentional purchase, movement, dispatch, Chalan, notification, and fixture mutations, but the startup/auth side effects mean it must not be described as a read-only database session.

Observed browser evidence:

- Signed in through the development-only demo affordance, switched from Ground Floor to The Sanitary Bathroom, and opened `/purchases`.
- Purchases rendered 35 floor-scoped items and its Today, Stock, Customers, and Dispatch Record navigation, brand/stage facets, disabled empty-selection bulk action, blocked-order rows, movement actions, and history actions.
- Captured real frames at 1440×900, 1024×768, and 375×812. At each size `document.documentElement.scrollWidth === clientWidth` (1440, 1024, and 375 respectively), so no document-level horizontal overflow was observed.
- At 375 px the loading state (`Preparing today’s operations…`) appeared during the request and settled to the populated control tower. The mobile bottom navigation remained visible.
- Opened the Customer Purchases view and Malhotra Interiors' purchase tab at 375 px. Search, brand, stage, All/Outstanding/Delayed controls, seven existing product cards, seven POs, and recent activity rendered in the preserved card layout.
- Backend request logs showed one purchase-items request plus the three facet requests on initial Purchases load, and one workspace request on initial customer workspace load. No polling loop or per-row request pattern appeared.

Unavailable or intentionally limited web checks:

- The user requested that any hanging browser/download attempt be stopped. The browser session was finalized immediately; no download remained active.
- Search/brand/stage interaction automation did not produce reliable controlled-input values before the stop request. Filter combinations and clearing therefore have automated backend proof, but not complete live browser proof in this run.
- Bulk 1/5/20 moves, mixed supplier/brand mutations, retry/partial-error actions, single/multi/partial/complete dispatch, repeated/conflicting Chalan actions, and notification creation were not executed against the connected shared database. These mutating UI acceptance cases remain a verification limitation/blocker; the passing focused suites are committed regression evidence but do not replace browser acceptance.
- Chalan detail, Purchase Detail, movement History sheet, browser PDF download, explicit empty/error states, and end-to-end activity/notification synchronization were not completed before shutdown. These remain verification limitations/blockers. Customer timeline/recent activity and the relevant navigation/actions did render.
- The reviewer checked generated Chalan PDF text extraction and a one-page render. This is useful renderer evidence, but the visual browser PDF download flow was not exercised and remains unverified.

## Performance and history audit

Direct code/test evidence:

- `customer_workspace` performs one `_iter_items` aggregation and one bounded query for each related collection; the 300-item regression asserts one aggregate and no per-item database queries.
- `_iter_items` returns at most 2,000 rows (default endpoint limit 500); customer POs are capped at 200; workspace activity at 15; shortages, payments, and follow-ups at 100 each; ordered quotations at 500; activity endpoints default to 200 with maximum 500; notifications cap at 100; transfer history caps at 200.
- Purchase filters debounce by 220 ms and invalidate stale requests. Purchases initial loading issues one item request and batched facet requests. Mutation refreshes are explicit rather than polling.
- Customer `loadCore` and workspace are intentionally separate, but `loadCore` fetches the bounded global quotation list and filters it client-side, and mutation `reloadAll` refreshes both core and workspace data. This is redundant payload/work at scale, though not an N+1 pattern.

Residual scale risks:

- `GET /purchases/items/{item_id}` returns the embedded `stage_history` without a server-side cap; the History sheet reverses and renders the whole array. Activity and transfer histories are bounded, but item stage history is not.
- Checked-in index creation includes activity customer timeline, payment quotation/status, follow-up floor/status/due date, PO number, and Chalan number indexes. No checked-in compound purchase-order index directly matches the workspace's leading `floor_id`/`customer_id`/status access. Query volume is bounded, but production index coverage for this workspace should be verified with `explain()` before large-scale rollout.

## Native and deployment readiness

Simulator probe:

```text
xcrun simctl list devices available
```

Result: exit 72; `xcrun: error: unable to find utility "simctl", not a developer tool or in PATH`. iOS simulator launch, real simulator frame proof, tablet-native proof, and native PDF/share behavior are unavailable in this environment. No simulator mirror or helper was started.

Only `frontend/eas.json` and `frontend/app.json` were inspected. No EAS build, submit, deploy, TestFlight, App Store, Play Store, or hosting command was run.

Observed configuration:

- EAS uses remote app-version source; development and preview are internal distributions; production enables auto-increment; production submit is otherwise empty.
- App version is `1.0.0`; iOS bundle identifier and Android package are both `com.buildconhouse.app`; iOS tablet support is enabled; non-exempt encryption is declared false.
- The inspected files do not contain an EAS project ID or unattended submit identifiers/credential references, so project linkage and store submission readiness cannot be proven from the permitted files alone.
- Expo startup warned that installed `expo@54.0.35` should be `~54.0.36` and that Sentry organization/project config was absent. These were not modified in verification.

## Blockers and disposition

1. **Critical release blocker:** backend startup reports that `owner@forge.app` still uses the historical known default password. Rotate it through the established credential-rotation process before deployment; no rotation was performed here.
2. **Verification blocker:** the exact repo-root full-suite command exits 3 because pytest collects root executable/network scripts, including `test_failfast.py` (import-time exit) and `pdf_image_test.py` (missing `PyPDF2`). The configured backend suite itself passes 876 tests at the isolated commit.
3. **Reproducibility blocker:** TypeScript passed only after ignored `.expo/types` had been generated locally; a clean snapshot needs that explicit prerequisite.
4. **Acceptance blocker:** the mutating bulk movement, dispatch, retry/conflict, Chalan, activity, and notification UI matrix was not run against shared business data. Committed tests cover invalid movement/stage rejection and Chalan quantity constraints where applicable, but they are not live UI evidence.
5. **Browser coverage blocker:** visual browser PDF download, detail/history, explicit empty/error, and end-to-end synchronization checks were not completed. Reviewer PDF text extraction and one-page rendering do not prove the browser download flow.
6. **Environment blocker:** iOS Simulator tooling (`simctl`) is unavailable.
7. **Scale follow-up:** verify/add appropriate purchase workspace indexes and bound embedded stage history before materially larger histories.

No deliberate production fixture mutation or cleanup, deployment, store action, frontend change, or unrelated dirty-worktree modification was made. Startup and demo-auth write-capable side effects are disclosed above.
