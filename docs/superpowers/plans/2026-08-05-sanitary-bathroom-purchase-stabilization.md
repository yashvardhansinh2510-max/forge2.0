# Sanitary Bathroom Purchase Workflow Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the existing Sanitary Bathroom purchase workflow across bulk movement, customer filtering, dispatch/Chalan/PDF, synchronized history, UI states, performance, and regression coverage.

**Architecture:** Keep `purchase_orders.items[]` and embedded `purchase_orders.chalans[]` as the source of truth. Extend the existing floor-scoped tracker, customer workspace, stage-change, Chalan, PDF, activity, timeline, notification, and download-token paths; do not add duplicate domain models or workflows. Implement in four vertical slices, with a focused test gate after each slice.

**Tech Stack:** FastAPI, Pydantic, Motor/MongoDB, ReportLab, Expo Router, React Native/Web, TypeScript, pytest.

## Global Constraints

- Sanitary Bathroom is `first-floor`; preserve floor isolation and permission enforcement.
- Reuse existing Purchase Orders, Customer Purchases, Dispatch, Chalan, Timeline, Activity Feed, Notifications, MongoDB models, repository/service layer, Supabase/download-token path, PDF generator, workflow engine, and floor isolation.
- Do not create duplicate services, models, layouts, or business logic.
- Preserve the existing Customer Purchases purchase-card/list layout; only filter data and improve states/interactions.
- Do not destructively clean production fixtures or mutate live business data during verification.
- Do not deploy through EAS, TestFlight, App Store, Play Store, or hosting without explicit authorization.
- Every implementation step ends with a focused test or type-check command before commit.

---

## File Map

**Bulk movement and customer workspace:**

- Modify `backend/routes/purchases_tracker.py`: bulk response semantics and composable workspace filters.
- Modify `frontend/app/(admin)/purchases.tsx`: selection, bulk progress, partial-failure display, and retry behavior.
- Modify `frontend/app/(admin)/customers/[id].tsx`: search/brand/stage controls while preserving existing product cards.
- Modify or create focused tests under `backend/tests/unit/` and `backend/tests/` following existing purchase-test conventions.

**Chalan and PDF:**

- Modify `backend/routes/purchases_tracker.py`: lifecycle validation, floor-scoped fresh reads, and event consistency.
- Modify `backend/pdf_chalan.py`: complete Sanitary Chalan document fields and robust table layout.
- Extend `backend/tests/unit/test_purchases_chalan_generation.py`, `test_purchases_chalan_lifecycle.py`, and `test_pdf_chalan.py`.

**Shared verification:**

- Modify only adjacent shared producers if focused tests demonstrate a missing or duplicate event: `backend/services/activity_log.py`, `backend/services/notifications.py`, `backend/routes/activity_routes.py`, or the relevant purchase route.
- Add a verification report under `docs/superpowers/verification/2026-08-05-sanitary-bathroom-purchase-stabilization.md`.
- Inspect `frontend/eas.json` and `frontend/app.json` for deployment readiness only; do not submit or build a store artifact.

---

### Task 1: Reproduce and harden bulk stage movement

**Files:**
- Modify: `backend/routes/purchases_tracker.py:879-907`
- Test: `backend/tests/unit/test_purchases_tracker_bulk_move.py` (create if absent)
- Test: `backend/tests/unit/test_purchases_tracker_concurrency.py`

**Interfaces:**
- Consumes: `_apply_stage_change(item_id: str, to_stage: str, user: UserPublic, note: str | None, qty: float | None)`.
- Produces: `POST /purchases/items/bulk-move` returning `{count: int, succeeded: int, failed: int, results: list[{item_id: str, ok: bool, error?: str, error_code?: str, ...}]}`.

- [ ] **Step 1: Write failing endpoint tests** for one, five, and twenty selected item ids, including mixed supplier and mixed brand items. Assert every item is attempted and successful responses include item ids.
- [ ] **Step 2: Write failing partial-success tests** where one item is missing, one has a stale stage, and the remaining items are valid. Assert HTTP 200 with per-item failures, `succeeded + failed == len(results)`, and no false all-success count.
- [ ] **Step 3: Write failing permission and empty-selection tests** asserting warehouse authorization remains required and an empty list returns HTTP 400 before `_apply_stage_change` is called.
- [ ] **Step 4: Run the focused tests** with `backend/.venv/bin/pytest backend/tests/unit/test_purchases_tracker_bulk_move.py backend/tests/unit/test_purchases_tracker_concurrency.py -q`; confirm the new assertions fail against the current behavior.
- [ ] **Step 5: Implement the minimal response contract** in `bulk_move`: keep the existing sequential primitive, catch `HTTPException` into stable `error_code` values (`not_found`, `conflict`, `validation`, `forbidden`), and preserve successful mutation results.
- [ ] **Step 6: Re-run the focused tests** and then run `backend/.venv/bin/pytest backend/tests/unit/test_purchases_move_permissions.py backend/tests/unit/test_purchases_tracker_concurrency.py -q`.
- [ ] **Step 7: Commit** with `git add backend/routes/purchases_tracker.py backend/tests/unit/test_purchases_tracker_bulk_move.py backend/tests/unit/test_purchases_tracker_concurrency.py && git commit -m "fix: make purchase bulk moves partially failure aware"`.

### Task 2: Repair bulk selection UX and retry behavior

**Files:**
- Modify: `frontend/app/(admin)/purchases.tsx:120-225` and the bulk-action render block.
- Test: `frontend/` has no dedicated unit-test command in the current package scripts; validate this slice with `cd frontend && npx tsc --noEmit` plus the browser test ids listed in the verification task.

**Interfaces:**
- Consumes: Task 1 bulk response `{count, succeeded, failed, results}`.
- Produces: selection state that retains failed item ids and a visible partial-result message.

- [ ] **Step 1: Add a typed `BulkMoveResponse`** beside the existing `Item` types and make the API call use it.
- [ ] **Step 2: Add a `bulkBusy` state and disable the bulk action while the request is active; keep the selected set unchanged until the response is processed.
- [ ] **Step 3: Process results** by clearing successful ids, retaining failed ids, closing the move menu, and showing a success, partial-success, or failure toast with the failed count.
- [ ] **Step 4: Add a retry affordance** that reuses the retained failed-id set and the same destination stage; do not re-submit successful ids.
- [ ] **Step 5: Run `cd frontend && npx tsc --noEmit` and inspect the screen at desktop and 375px widths for disabled/loading/error/empty states.
- [ ] **Step 6: Commit** with `git add frontend/app/(admin)/purchases.tsx && git commit -m "fix: surface partial purchase bulk-move results"`.

### Task 3: Add composable customer workspace filters

**Files:**
- Modify: `backend/routes/purchases_tracker.py:365-470`
- Test: `backend/tests/unit/test_customer_purchase_workspace_filters.py` (create)

**Interfaces:**
- Consumes: existing `customer_id`, `floor_query`, `floor_scope_ids`, `_iter_items`, `PURCHASE_STAGES`, and `STAGE_LABELS`.
- Produces: `GET /purchases/customers/{customer_id}/workspace?q=&brand=&stage=` with `products`, `outstanding_items`, `brands`, and `stages` all derived from the same filtered set while summary totals remain explicitly documented as filtered workspace totals.

- [ ] **Step 1: Write failing tests** for no filters, brand-only, stage-only, brand+stage, search+brand+stage, and clearing filters. Assert every returned product matches all active predicates and facet counts match the returned products.
- [ ] **Step 2: Write a large-history test** with enough generated rows to expose an accidental per-item database query; assert the workspace uses the existing single item traversal and bounded related-record queries.
- [ ] **Step 3: Run the focused tests** with `backend/.venv/bin/pytest backend/tests/unit/test_customer_purchase_workspace_filters.py -q` and confirm failure before implementation.
- [ ] **Step 4: Add optional query parameters** with the existing stage validation and brand-id semantics. Pass them into `_iter_items` rather than filtering a second, divergent representation.
- [ ] **Step 5: Derive brands/stages/outstanding data from the filtered rows**, keep customer/floor access checks unchanged, and preserve the existing response keys for consumers that do not pass filters.
- [ ] **Step 6: Re-run focused tests plus `backend/.venv/bin/pytest backend/tests/unit/test_purchases_tracker_floor_scoping.py backend/tests/unit/test_customer_routes_floor_scoped_lookups.py -q`.
- [ ] **Step 7: Commit** with `git add backend/routes/purchases_tracker.py backend/tests/unit/test_customer_purchase_workspace_filters.py && git commit -m "feat: filter customer purchase workspaces"`.

### Task 4: Add filter controls without changing purchase-card layout

**Files:**
- Modify: `frontend/app/(admin)/customers/[id].tsx` around workspace state/load and the existing Products ordered card.

**Interfaces:**
- Consumes: Task 3 query parameters and filtered workspace response.
- Produces: removable search, brand, and stage controls that combine and reload the existing purchase cards.

- [ ] **Step 1: Add typed filter state** (`productSearch`, `brandFilter`, `stageFilter`) and a debounced workspace loader that appends only active query parameters.
- [ ] **Step 2: Render controls above the existing Products ordered card** using the current chip/card primitives; do not create a second product layout.
- [ ] **Step 3: Keep current All/Outstanding/Delayed client filters** composable with server filters, and show an explicit empty state when server filters return no products.
- [ ] **Step 4: Add loading/error retry handling** that preserves the selected filters and does not show stale rows as current after a failed request.
- [ ] **Step 5: Run `cd frontend && npx tsc --noEmit`; manually exercise search-only, brand-only, stage-only, combined, and clear-filter flows at desktop/tablet/mobile widths.
- [ ] **Step 6: Commit** with `git add frontend/app/(admin)/customers/[id].tsx && git commit -m "feat: add customer purchase filters"`.

### Task 5: Stabilize Sanitary Chalan lifecycle and event synchronization

**Files:**
- Modify: `backend/routes/purchases_tracker.py:1463-1675`
- Test: `backend/tests/unit/test_purchases_chalan_generation.py`
- Test: `backend/tests/unit/test_purchases_chalan_lifecycle.py`
- Test: `backend/tests/unit/test_purchases_chalan_permissions.py`

**Interfaces:**
- Consumes: existing `GenerateChalanBody`, `remaining_qty_by_item`, `compute_order_stage`, `log_event`, `notify`, `floor_query`, and Chalan embedded model.
- Produces: floor-scoped Sanitary generation, allowed stage transitions, idempotent event identity, and an authenticated Chalan PDF endpoint.

- [ ] **Step 1: Write failing lifecycle tests** for single, multi-item, partial, complete, repeated, over-release, and concurrent generation/dispatch. Assert cumulative quantities never exceed ordered quantities.
- [ ] **Step 2: Write failing synchronization tests** that perform a successful dispatch and assert exactly one corresponding activity/timeline/history record and one notification per intended recipient; repeat the request and assert no duplicate event is created.
- [ ] **Step 3: Write failing floor/permission tests** for a cross-floor PO id, insufficient role, and unauthorized Chalan id; assert no mutation occurs.
- [ ] **Step 4: Run the focused tests** with `backend/.venv/bin/pytest backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_purchases_chalan_lifecycle.py backend/tests/unit/test_purchases_chalan_permissions.py -q`.
- [ ] **Step 5: Trace the current dispatch handlers** and add only the missing CAS/idempotency guard or source-floor argument demonstrated by the failing tests; keep `purchase_orders.chalans[]` as the persisted state.
- [ ] **Step 6: Re-run focused tests and existing purchase transition tests** with `backend/.venv/bin/pytest backend/tests/unit/test_purchases_chalan_stage.py backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_purchases_chalan_lifecycle.py -q`.
- [ ] **Step 7: Commit** with `git add backend/routes/purchases_tracker.py backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_purchases_chalan_lifecycle.py backend/tests/unit/test_purchases_chalan_permissions.py && git commit -m "fix: synchronize sanitary chalan lifecycle"`.

### Task 6: Complete the Sanitary Chalan PDF

**Files:**
- Modify: `backend/pdf_chalan.py:38-130`
- Test: `backend/tests/unit/test_pdf_chalan.py`

**Interfaces:**
- Consumes: `build_chalan_pdf(chalan: dict, po: dict, customer: dict, branding: dict | None) -> bytes` and existing branding/download route.
- Produces: a valid PDF containing the complete Sanitary Chalan field set without table overflow or crashes on missing optional values.

- [ ] **Step 1: Add a fixture with long customer address, long product name, brand, size, finish, quantity, unit, rate, total, transport, remarks, and signature metadata.
- [ ] **Step 2: Write failing assertions** that generated bytes begin with `%PDF-`, contain expected text after extraction, and render all required headings/values without raising.
- [ ] **Step 3: Run `backend/.venv/bin/pytest backend/tests/unit/test_pdf_chalan.py -q` and confirm the missing fields fail.
- [ ] **Step 4: Extend the renderer** with wrapped `Paragraph` cells, stable numeric formatting, a totals row, transport/remarks blocks, customer address/phone, order number/dispatch date, company details, and signature areas. Preserve existing branding and filename behavior.
- [ ] **Step 5: Add missing-field fallback tests** for absent address, phone, rate, transport, remarks, and signature names; assert generation still succeeds.
- [ ] **Step 6: Re-run PDF tests plus `backend/.venv/bin/pytest backend/tests/unit/test_tile_orders_dispatch.py backend/tests/unit/test_pdf_tile_chalan.py -q`.
- [ ] **Step 7: Commit** with `git add backend/pdf_chalan.py backend/tests/unit/test_pdf_chalan.py && git commit -m "fix: complete sanitary chalan pdf"`.

### Task 7: Audit UI states, performance, and regression coverage

**Files:**
- Modify: `frontend/app/(admin)/purchases.tsx`, `frontend/app/(admin)/customers/[id].tsx`, or a shared purchase component only when a focused UI verification failure identifies a concrete defect; otherwise leave these files unchanged.
- Create: `docs/superpowers/verification/2026-08-05-sanitary-bathroom-purchase-stabilization.md`

**Interfaces:**
- Consumes: all prior slice contracts and existing regression suites.
- Produces: evidence-backed verification report and a clean, type-safe workflow.

- [ ] **Step 1: Run backend focused suites** for bulk movement, workspace filters, Chalan lifecycle, PDF, permissions, floor scoping, and concurrency; record exact command/output.
- [ ] **Step 2: Run the complete backend suite** with `backend/.venv/bin/pytest -q` and investigate every failure rather than weakening assertions.
- [ ] **Step 3: Run `cd frontend && npx tsc --noEmit`; fix type errors caused by the new response contracts.
- [ ] **Step 4: Start the existing backend/frontend development workflow and inspect Purchase Orders, Customer Purchases, Dispatch, Chalan, Purchase Detail, Timeline, and History at desktop, tablet, and 375px widths.
- [ ] **Step 5: Exercise the acceptance matrix:** 1/5/20 bulk moves; mixed supplier/brand selection; all filter combinations; single/multi/partial/complete dispatch; repeated/conflicting actions; PDF download; timeline/activity/notification/history; empty/loading/error states.
- [ ] **Step 6: Check for N+1 requests and redundant reloads in browser/network logs, and confirm large workspace histories remain bounded by existing limits and indexes.
- [ ] **Step 7: Inspect `frontend/eas.json` and `frontend/app.json` for readiness issues without running build/submit/deploy commands. Record deployment limitations explicitly.
- [ ] **Step 8: Write the verification report** with passed evidence, failed evidence, environment-limited checks, and any remaining production blocker.
- [ ] **Step 9: Commit** with `git add docs/superpowers/verification/2026-08-05-sanitary-bathroom-purchase-stabilization.md && git commit -m "docs: verify sanitary purchase stabilization"`.

## Final Review Checklist

- [ ] Every requirement in `docs/superpowers/specs/2026-08-05-sanitary-bathroom-purchase-stabilization-design.md` maps to a task above.
- [ ] No task introduces a duplicate model, service, layout, or workflow.
- [ ] Bulk response types match the frontend consumer.
- [ ] Workspace query parameters and returned facet counts use one filter contract.
- [ ] Chalan PDF fields and tests cover all required customer, order, product, logistics, company, and signature data.
- [ ] Ground Floor and existing purchase/payment/permission/floor-isolation regressions pass.
- [ ] Verification report distinguishes direct proof from unavailable live/native/deployment checks.
