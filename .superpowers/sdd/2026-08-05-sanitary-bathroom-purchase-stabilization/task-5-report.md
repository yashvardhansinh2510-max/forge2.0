# Task 5 Report — Sanitary Chalan Lifecycle and Event Synchronization

Date: 2026-08-05

Status: completed; no blocker

## Scope implemented

- Kept `purchase_orders.chalans[]` as the only persisted Chalan lifecycle state.
- Kept the existing `GenerateChalanBody`, `remaining_qty_by_item`, `compute_order_stage`, `log_event`, `notify`, `floor_query`, PDF renderer, and authenticated PDF route.
- Added floor scope to every Chalan compare-and-swap write and post-write purchase-order read.
- Added source-floor, purchase, quotation, customer, and Chalan identities to lifecycle activity events so the one event is visible through the existing activity feed, purchase timeline, and customer history read models.
- Preserved recipient deduplication and verified exactly one notification per distinct creator/assignee for successful generation and completed dispatch.
- Added the Sanitary purchase-order detail link/title to first-floor notifications while preserving the existing Tiles notification behavior.
- Restricted dispatch to the existing `released -> dispatched` and `at_godown -> dispatched` paths; invalid/corrupt stages now fail before mutation.
- Floor-scoped the customer lookup used by the existing authenticated Chalan PDF endpoint. The PDF renderer was not changed.

## Focused coverage added

- Single-item and multi-item generation.
- Partial release followed by complete release.
- Repeated complete generation and repeated dispatch with no duplicate mutation/event/notification.
- Over-release rejection and cumulative quantity bounds.
- Concurrent generation and concurrent dispatch with one CAS winner and one conflict.
- Partial dispatch versus completed dispatch notification behavior.
- Exactly one source-identified activity/timeline/customer-history event per successful transition.
- One notification per distinct intended recipient.
- Cross-floor PO rejection, insufficient-role rejection, and unknown Chalan-id rejection with no mutation.
- Floor-scoped Chalan writes, fresh reads, activity events, notifications, and PDF customer lookup.

## Verification

Initial baseline:

- `backend/.venv/bin/pytest backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_purchases_chalan_lifecycle.py backend/tests/unit/test_purchases_chalan_permissions.py backend/tests/unit/test_chalan_stage.py -q`
- Result: `24 passed`.

Red run after adding Task 5 regressions and before route changes:

- `backend/.venv/bin/pytest backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_purchases_chalan_lifecycle.py backend/tests/unit/test_purchases_chalan_permissions.py -q`
- Result: `7 failed, 26 passed`; failures demonstrated missing write/event/PDF floor scope and invalid-stage dispatch acceptance. Two concurrency expectations initially exposed a fake-snapshot timing defect; the harness was corrected to return the snapshot captured before the barrier, after which the existing CAS behavior was verified accurately.

Focused green run:

- `backend/.venv/bin/pytest backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_purchases_chalan_lifecycle.py backend/tests/unit/test_purchases_chalan_permissions.py -q`
- Result: `33 passed`.

Focused Chalan plus existing purchase transition/concurrency run:

- `backend/.venv/bin/pytest backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_purchases_chalan_lifecycle.py backend/tests/unit/test_purchases_chalan_permissions.py backend/tests/unit/test_chalan_stage.py backend/tests/unit/test_purchases_tracker_concurrency.py backend/tests/unit/test_purchases_move_permissions.py -q`
- Result: `53 passed`.

Expanded purchase regression gate:

- `backend/.venv/bin/pytest backend/tests/unit/test_chalan_stage.py backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_purchases_chalan_lifecycle.py backend/tests/unit/test_purchases_chalan_permissions.py backend/tests/unit/test_purchases_move_permissions.py backend/tests/unit/test_purchases_orders_views.py backend/tests/unit/test_purchases_tracker_bulk_move.py backend/tests/unit/test_purchases_tracker_concurrency.py backend/tests/unit/test_purchases_tracker_floor_scoping.py backend/tests/unit/test_purchases_tracker_write_floor_inheritance.py backend/tests/unit/test_purchases_transfer_customer_floor_scope.py -q`
- Result: `80 passed`.
- `git diff --check` passed for all Task 5 code and test files.

## Notes and concerns

- The plan names `backend/tests/unit/test_purchases_chalan_stage.py`, but that file does not exist. The repository's existing transition suite is `backend/tests/unit/test_chalan_stage.py`; it was used in both transition gates.
- Exactly-once behavior is enforced and tested for repeated and concurrent HTTP requests by the embedded-Chalan CAS: only the successful mutation proceeds to `log_event` and `notify`. The existing producers are intentionally best-effort and are not transactionally coupled to the PO update, so a process crash between the primary write and a side-effect write remains an existing durability window. Closing that would require an outbox/transaction change outside the route-only Task 5 scope.
- Test output contains pre-existing FastAPI `Query(regex=...)` and Pydantic `.dict()` deprecation warnings. No warning-only cleanup was included.
- No PDF renderer, frontend, tile route/model, or unrelated dirty-worktree file was changed or staged by Task 5.

Commit subject: `fix: synchronize sanitary chalan lifecycle`
