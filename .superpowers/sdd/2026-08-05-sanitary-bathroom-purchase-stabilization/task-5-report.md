# Task 5 Report — Sanitary Chalan Lifecycle and Event Synchronization

Date: 2026-08-05

Status: completed; review findings fixed; no blocker

## Scope implemented

- Kept `purchase_orders.chalans[]` as the only persisted Chalan lifecycle state.
- Kept the existing `GenerateChalanBody`, `remaining_qty_by_item`, `compute_order_stage`, `log_event`, `notify`, `floor_query`, PDF renderer, and authenticated PDF route.
- Added floor scope to every Chalan compare-and-swap write and post-write purchase-order read.
- Added source-floor, purchase, quotation, customer, and Chalan identities to lifecycle activity events so the one event is visible through the existing activity feed, purchase timeline, and customer history read models.
- Preserved recipient deduplication and verified exactly one notification per distinct creator/assignee for successful generation and completed dispatch.
- Added the Sanitary purchase-order detail link/title to first-floor notifications while preserving the existing Tiles notification behavior.
- Restricted dispatch to the existing `released -> dispatched` and `at_godown -> dispatched` paths; invalid/corrupt stages now fail before mutation.
- Floor-scoped the customer lookup used by the existing authenticated Chalan PDF endpoint. The PDF renderer was not changed.

## Follow-up review findings fixed

- Added replay-safe Chalan generation for partial releases. A caller-supplied idempotency key is persisted on the embedded Chalan; when no key is supplied, a deterministic request fingerprint is used so legacy callers also replay safely. Sequential and concurrent replays return the original Chalan and do not append a second batch or outbox row.
- Journaled every successful generation, Godown receipt, and dispatch in `event_outbox` in the same MongoDB transaction as the purchase-order compare-and-swap write. Immediate dispatch is best-effort only after commit; a failed immediate attempt leaves the persisted row pending for the existing worker.
- Added a Chalan lifecycle outbox materializer that upserts activity-feed/timeline/customer-history events and notifications with deterministic `automation_key` values. Worker retries therefore repair missing read models without duplicating rows.
- Added a purchase-order completion claim (`chalan_completion_event_key`) so two distinct final Chalan dispatches can each retain their own activity event while only one transition owns the order-complete notification set.
- Added bounded MongoDB transaction retries for Chalan dispatch: transient transaction/write-conflict failures replay the complete transaction, while unknown commit results retry the same commit and reconcile the deterministic Chalan/outbox identities if acknowledgement remains uncertain.
- Strengthened generation CAS with the exact ordered-item snapshot as well as the Chalan-array size, preventing a release validated against stale ordered quantities from committing after an item replacement.

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
- Persisted outbox rows and retry-idempotent activity/notification read-model rows with exact deterministic keys.
- Concurrent partial replay without a client-provided key.
- Concurrent dispatch of distinct final Chalans with one order-completion notification claim.
- A transient commit write conflict followed by a successful retry, preserving one mutation/outbox identity per Chalan and one final completion notification claim.
- An unknown commit result followed by a successful commit retry on the same transaction, without replaying the Chalan mutation or outbox insert.
- Rejection when the ordered-item snapshot changes before generation CAS.

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

Follow-up review verification on the durable-outbox/idempotency fix:

- Initial all-Chalan gate: `backend/.venv/bin/pytest -q backend/tests/unit/test_purchases_chalan_lifecycle.py backend/tests/unit/test_chalan_stage.py backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_models_chalan.py backend/tests/unit/test_purchases_chalan_permissions.py backend/tests/unit/test_pdf_chalan.py backend/tests/unit/test_pdf_tile_chalan.py`
- Result: `52 passed` before the two final edge assertions were added.
- Generation/lifecycle edge gate: `backend/.venv/bin/pytest -q backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_purchases_chalan_lifecycle.py`
- Result: `24 passed`.
- Focused Chalan plus purchase transition/concurrency gate: `backend/.venv/bin/pytest -q backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_purchases_chalan_lifecycle.py backend/tests/unit/test_purchases_chalan_permissions.py backend/tests/unit/test_chalan_stage.py backend/tests/unit/test_purchases_tracker_concurrency.py backend/tests/unit/test_purchases_move_permissions.py`
- Result: `57 passed`.
- Expanded purchase regression gate: `backend/.venv/bin/pytest -q backend/tests/unit/test_chalan_stage.py backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_purchases_chalan_lifecycle.py backend/tests/unit/test_purchases_chalan_permissions.py backend/tests/unit/test_purchases_move_permissions.py backend/tests/unit/test_purchases_orders_views.py backend/tests/unit/test_purchases_tracker_bulk_move.py backend/tests/unit/test_purchases_tracker_concurrency.py backend/tests/unit/test_purchases_tracker_floor_scoping.py backend/tests/unit/test_purchases_tracker_write_floor_inheritance.py backend/tests/unit/test_purchases_transfer_customer_floor_scope.py`
- Result: `84 passed`.

Final transaction-retry follow-up verification:

- Focused lifecycle/generation/permission/stage gate: `backend/.venv/bin/python -m pytest -q backend/tests/unit/test_purchases_chalan_lifecycle.py backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_purchases_chalan_permissions.py backend/tests/unit/test_chalan_stage.py`
- Result: `48 passed`.
- Expanded purchase regression gate: `backend/.venv/bin/python -m pytest -q backend/tests/unit/test_chalan_stage.py backend/tests/unit/test_purchases_chalan_generation.py backend/tests/unit/test_purchases_chalan_lifecycle.py backend/tests/unit/test_purchases_chalan_permissions.py backend/tests/unit/test_purchases_move_permissions.py backend/tests/unit/test_purchases_orders_views.py backend/tests/unit/test_purchases_tracker_bulk_move.py backend/tests/unit/test_purchases_tracker_concurrency.py backend/tests/unit/test_purchases_tracker_floor_scoping.py backend/tests/unit/test_purchases_tracker_write_floor_inheritance.py backend/tests/unit/test_purchases_transfer_customer_floor_scope.py`
- Result: `86 passed`.

## Notes and concerns

- The plan names `backend/tests/unit/test_purchases_chalan_stage.py`, but that file does not exist. The repository's existing transition suite is `backend/tests/unit/test_chalan_stage.py`; it was used in both transition gates.
- Chalan lifecycle activity and notifications are now transactionally journaled and retry-safe. The worker materializes both read models from the persisted outbox row with deterministic keys; a crash after the primary commit can delay synchronization but cannot permanently lose it or duplicate it on replay.
- Test output contains pre-existing FastAPI `Query(regex=...)` and Pydantic `.dict()` deprecation warnings. No warning-only cleanup was included.
- No PDF renderer, frontend, tile route/model, or unrelated dirty-worktree file is owned by this follow-up. The exact unstaged residuals in `backend/services/domain_outbox.py` are the three pre-existing `_handle_order_placed` edits that propagate `quantity_unit` into `PurchaseOrderItem`, propagate it into `TileCustomerOrderBrand`, and add `transportation_fee` to the tile customer-order total. All three remain untouched in the worktree. At the start of this follow-up no Chalan hunks were staged; only this follow-up's route, lifecycle-test, and report changes will be committed.

Follow-up commit subject: `fix: make chalan lifecycle durable`
