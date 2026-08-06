# Kitchen and Furniture Digital Notebook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Kitchen/Furniture prototype with a floor-isolated, autosaved notebook backed by the existing `followups` collection and services.

**Architecture:** Add a narrow notebook adapter around the existing follow-up collection, activity/timeline helpers, customer lookup, permissions, and floor scoping. The adapter exposes an allowlisted notebook DTO, optimistic-lock field patches, conversion on the same row, server-side pagination, and an idempotent migration from `project_followups`. Replace the prototype route with one shared notebook screen per floor and two view states.

**Tech Stack:** FastAPI, Pydantic, MongoDB/Motor, existing activity/timeline and auth helpers, Expo Router, React Native/Web, TypeScript, Node’s `--experimental-strip-types` test runner.

## Global Constraints

- Exactly two feature floor modules: Kitchen Floor (`second-floor`) and Furniture Floor (`third-floor`).
- Exactly two feature views: Follow-ups and Quotation Follow-ups.
- Follow-up fields are exactly Customer Name, Mobile Number, Address, Kitchen Type (GI/SS), Referred By, Architect / Interior Designer, Status (New/Pending/Won/Lost), and Notes.
- Quotation Follow-up adds exactly Quotation Price, Estimated Value, and Quotation Date.
- Notebook editing is autosaved; there is no Save button anywhere.
- Lost requires non-empty Notes and an immutable timeline event containing note/reason, date, and user.
- Won requires confirmation, locks Follow-up fields, cannot return to New, and still permits quotation-field updates after conversion.
- Every read/write is floor-scoped; no duplicate customers or duplicate notebook rows per customer/floor.
- Existing unrelated ERP floors/modules and their uncommitted work must not be removed or overwritten.
- No new CRM pipeline, site-visit fields, dashboards, KPI cards, kanban, charts, or parallel notebook collection.
- Desktop supports resizable/sticky columns; tablet/phone use horizontal scrolling and touch targets of at least 44px.
- Lists support 10,000+ rows through server-side pagination/incremental loading, debounced search, and virtualized rendering.

---

## File Map

### Backend

- Modify `backend/models.py`: add notebook fields/DTOs and remove prototype-only DTO declarations after migration code no longer imports them.
- Create `backend/services/followup_notebook.py`: normalization, allowlists, status transitions, customer resolution, serialization, optimistic-lock updates, and timeline event mapping. This is an adapter over `db.followups`, not a second model.
- Modify `backend/routes/followup_routes.py`: add floor-scoped notebook list/create/detail/patch/convert/timeline endpoints using the adapter and existing auth/activity helpers.
- Create `backend/migrations/0015_migrate_project_followups_to_notebook.py`: idempotently map old prototype documents into `followups`, preserving the old collection.
- Modify `backend/server.py`: remove `project_followup_router` registration once the replacement endpoints are present.
- Delete `backend/routes/project_followup_routes.py` after migration and tests no longer import it.
- Add `backend/tests/unit/test_followup_notebook.py`: unit tests for adapter and route-level behavior with fake collections.
- Add `backend/tests/unit/test_migrate_project_followups_to_notebook.py`: migration mapping/idempotency tests.

### Frontend

- Create `frontend/src/components/notebook/notebookTypes.ts`: strict row, field, status, filter, and patch types.
- Create `frontend/src/components/notebook/notebookModel.ts`: pure allowlist, formatting, cell-navigation, filter, and optimistic-state helpers.
- Create `frontend/src/components/notebook/NotebookCell.tsx`: one-cell editor/status surface.
- Create `frontend/src/components/notebook/NotebookGrid.tsx`: virtualized, horizontally scrollable notebook with sticky/resizable columns.
- Create `frontend/src/components/notebook/NotebookToolbar.tsx`: exact tabs/filters/search/new-row controls.
- Replace `frontend/app/(admin)/project/[floor].tsx` with `frontend/app/(admin)/notebook/[floor].tsx`.
- Modify `frontend/app/(admin)/_layout.tsx`: point the two feature nav items at `/notebook/kitchen` and `/notebook/furniture`; remove the prototype project route reference.
- Modify `frontend/src/constants/floors.ts`: keep the existing IDs but make their Kitchen/Furniture display mapping explicit and remove stale prototype labels.
- Add `frontend/scripts/test-notebook.mjs`: executable pure-model tests.
- Modify `frontend/package.json`: add `test:notebook` script.
- Delete `frontend/app/(admin)/project/[floor].tsx` after replacement is verified.

### Verification

- Create `docs/superpowers/verification/2026-08-06-kitchen-furniture-notebook.md` only after implementation, containing commands, responsive evidence, and requirement-by-requirement results.

---

## Task 1: Define the notebook contract and pure domain helpers

**Files:**
- Modify: `backend/models.py:993-1125`
- Create: `backend/services/followup_notebook.py`
- Create: `backend/tests/unit/test_followup_notebook.py`

**Interfaces:**
- `NotebookStatus = Literal["new", "pending", "won", "lost"]`
- `NotebookField = Literal["customer_name", "customer_phone", "address", "kitchen_type", "referred_by", "architect_interior_designer", "status", "notes", "quotation_price", "estimated_value", "quotation_date"]`
- `normalize_mobile(value: str) -> str`
- `NOTEBOOK_FIELDS: frozenset[str]`
- `QUOTATION_FIELDS: frozenset[str]`
- `validate_notebook_patch(patch: dict, *, converted: bool, current: dict) -> None`
- `notebook_projection(*, converted: bool) -> dict`
- `serialize_notebook_row(document: dict) -> dict`
- `timeline_event_for_field(field: str, old_value, new_value) -> tuple[str, str]`

- [ ] **Step 1: Write failing contract tests.** Cover exact allowed fields, required Customer Name/Mobile/Kitchen Type, GI/SS validation, normalized mobiles, quotation fields rejected before conversion, and response projection excluding CRM/automation fields.

```python
def test_notebook_contract_rejects_unlisted_fields():
    with pytest.raises(ValueError, match="unsupported field"):
        validate_notebook_patch({"project_stage": "production"}, converted=False, current={})

def test_notebook_contract_requires_identity_and_kitchen_type():
    with pytest.raises(ValueError, match="customer_phone"):
        validate_notebook_patch({"customer_name": "A", "kitchen_type": "GI"}, converted=False, current={})

def test_projection_hides_shared_followup_metadata():
    row = serialize_notebook_row({"id": "1", "customer_name": "A", "priority_score": 90, "status": "new"})
    assert set(row) == {"id", "customer_name", "status", "is_converted"}
```

- [ ] **Step 2: Run the focused tests and verify they fail.**

Run: `cd backend && .venv/bin/pytest tests/unit/test_followup_notebook.py -q`

Expected: FAIL because the notebook contract module and DTO fields do not yet exist.

- [ ] **Step 3: Implement the smallest contract.** Add optional notebook fields to the shared follow-up representation, define DTOs with `extra="forbid"`, normalize `customer_phone`, validate required fields and status transitions, and project only the exact notebook fields plus internal `id`, `is_converted`, `updated_at`, and conflict metadata needed by the client.

- [ ] **Step 4: Run focused tests.**

Run: `cd backend && .venv/bin/pytest tests/unit/test_followup_notebook.py -q`

Expected: PASS.

- [ ] **Step 5: Commit only Task 1 files.**

```bash
git add backend/models.py backend/services/followup_notebook.py backend/tests/unit/test_followup_notebook.py
git commit -m "feat: define notebook follow-up contract"
```

## Task 2: Add customer reuse, one-row identity, and optimistic locking

**Files:**
- Modify: `backend/services/followup_notebook.py`
- Modify: `backend/models.py`
- Create: `backend/migrations/0015_migrate_project_followups_to_notebook.py` (index portion only; mapping is Task 3)
- Modify: `backend/tests/unit/test_followup_notebook.py`

**Interfaces:**
- `async resolve_or_create_customer(db, *, user, floor_id: str, name: str, phone: str, address: str | None) -> dict`
- `notebook_query(user, floor_id: str, extra: dict | None = None) -> dict`
- `async patch_notebook_row(db, *, user, floor_id: str, row_id: str, patch: dict, expected_updated_at: str) -> dict`
- `NotebookConflictError(row: dict, changed_fields: list[str])`

- [ ] **Step 1: Add failing tests** for same-floor mobile reuse, cross-floor non-reuse, duplicate notebook-row resolution, stale `updated_at` returning a conflict, and successful field-level patch updating only one key.

- [ ] **Step 2: Run the tests to verify failure.**

Run: `cd backend && .venv/bin/pytest tests/unit/test_followup_notebook.py -q -k 'customer or duplicate or conflict or patch'`

Expected: FAIL on missing resolver/patch helpers.

- [ ] **Step 3: Implement customer and locking helpers.** Use `floor_query(user, ...)` for every lookup, normalize mobile once, use a floor+mobile lookup before creation, catch duplicate-key races by re-reading the existing customer, and update with a filter containing the prior `updated_at`. Return a typed conflict payload rather than overwriting.

- [ ] **Step 4: Add the partial unique index definition.** Create a tolerant index on `followups.notebook_key` where `notebook_key` is present, with `notebook_key = floor_id + ":" + customer_id`; do not make the global follow-up collection unique by customer because automated follow-ups can legitimately coexist.

- [ ] **Step 5: Run focused tests.**

Run: `cd backend && .venv/bin/pytest tests/unit/test_followup_notebook.py -q`

Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add backend/models.py backend/services/followup_notebook.py backend/migrations/0015_migrate_project_followups_to_notebook.py backend/tests/unit/test_followup_notebook.py
git commit -m "feat: add notebook identity and optimistic locking"
```

## Task 3: Migrate the prototype collection safely

**Files:**
- Create: `backend/migrations/0015_migrate_project_followups_to_notebook.py`
- Create: `backend/tests/unit/test_migrate_project_followups_to_notebook.py`
- Modify: `backend/services/followup_notebook.py`

**Interfaces:**
- `async up(db) -> None`
- `legacy_to_notebook_document(legacy: dict, *, customer: dict, floor_id: str) -> dict`
- `migration_key(legacy: dict) -> str`

- [ ] **Step 1: Write migration tests.** Use an in-memory fake database to verify mapping of `business_type` to `kitchen_type`, phone normalization, status conversion (`quotation_created` → `new` plus `is_converted=True`), quotation amount/budget/date mapping, floor stamping, timeline event creation, and rerunning without additional rows/events.

- [ ] **Step 2: Run migration tests and verify failure.**

Run: `cd backend && .venv/bin/pytest tests/unit/test_migrate_project_followups_to_notebook.py -q`

Expected: FAIL because migration helpers are absent.

- [ ] **Step 3: Implement idempotent mapping.** Read only `project_followups`; resolve/create customers through the shared helper; derive `notebook_key`; insert only when the migration key is absent; preserve the source collection untouched; write one migration timeline event per inserted row; ignore unsupported stage/site-visit/CRM fields.

- [ ] **Step 4: Run migration tests.**

Run: `cd backend && .venv/bin/pytest tests/unit/test_migrate_project_followups_to_notebook.py -q`

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add backend/migrations/0015_migrate_project_followups_to_notebook.py backend/tests/unit/test_migrate_project_followups_to_notebook.py backend/services/followup_notebook.py
git commit -m "feat: migrate project follow-ups into notebook"
```

## Task 4: Add floor-scoped notebook API endpoints

**Files:**
- Modify: `backend/routes/followup_routes.py`
- Modify: `backend/server.py`
- Modify: `backend/services/followup_notebook.py`
- Modify: `backend/tests/unit/test_followup_notebook.py`

**Interfaces:**
- `GET /followups/notebook/{floor_id}` with `status`, `q`, `cursor`, and `limit` returns `{rows, next_cursor}`.
- `POST /followups/notebook/{floor_id}` resolves the customer and returns one serialized notebook row.
- `PATCH /followups/notebook/{floor_id}/{row_id}` accepts `{field, value, updated_at}` and returns the row or HTTP 409 conflict.
- `POST /followups/notebook/{floor_id}/{row_id}/convert` accepts `{quotation_price, estimated_value, quotation_date, updated_at}` and returns the same serialized row.
- `GET /followups/notebook/{floor_id}/{row_id}/timeline` returns newest-first immutable events.

- [ ] **Step 1: Write route tests.** Cover exact filters, six filter values, search fields (name/phone/address/architect/referred/notes only), pagination, floor isolation, create defaults, patch allowlist, conversion idempotency, Lost rejection, Won lock/transition, and timeline ordering.

- [ ] **Step 2: Run focused route tests and verify failure.**

Run: `cd backend && .venv/bin/pytest tests/unit/test_followup_notebook.py -q -k 'route or api'`

Expected: FAIL because endpoints are not registered.

- [ ] **Step 3: Implement list and create.** Use `floor_query(user, {"notebook_key": {"$exists": True}})`, cursor pagination ordered by `updated_at` descending then `id`, and a `$or` search restricted to the six text fields. Return only the notebook projection.

- [ ] **Step 4: Implement field patch and conversion.** Enforce `updated_at`, immutable timeline event creation, server-side Lost/Won transitions, and atomic same-row conversion. Reject quotation fields on the normal patch endpoint and reject conversion on a non-notebook or cross-floor row.

- [ ] **Step 5: Implement timeline endpoint.** Query `activity_events` by `entity_type="followup"`, `entity_id`, and floor; sort by `created_at` descending; return only immutable event data.

- [ ] **Step 6: Run focused tests.**

Run: `cd backend && .venv/bin/pytest tests/unit/test_followup_notebook.py -q`

Expected: PASS.

- [ ] **Step 7: Commit.**

```bash
git add backend/routes/followup_routes.py backend/server.py backend/services/followup_notebook.py backend/tests/unit/test_followup_notebook.py
git commit -m "feat: add floor-scoped notebook follow-up api"
```

## Task 5: Replace the prototype backend route and frontend route wiring

**Files:**
- Modify: `backend/server.py`
- Delete: `backend/routes/project_followup_routes.py`
- Modify: `frontend/app/(admin)/_layout.tsx`
- Modify: `frontend/src/constants/floors.ts`
- Delete: `frontend/app/(admin)/project/[floor].tsx`
- Create: `frontend/app/(admin)/notebook/[floor].tsx`

- [ ] **Step 1: Add route-level checks.** Assert the sidebar contains exactly the Kitchen Floor and Furniture Floor notebook entries for this feature, both IDs resolve to the new route, and no project route is referenced.

- [ ] **Step 2: Change route wiring without changing the screen yet.** Point `/project/kitchen` and `/project/furniture` to `/notebook/kitchen` and `/notebook/furniture`, preserve existing floor IDs, and remove `project_followup_router` registration. Do not touch unrelated navigation items.

- [ ] **Step 3: Remove prototype backend imports and route file.** Confirm `rg -n 'project-workspaces|ProjectFollowup|project_followup_routes|/project/' backend frontend` has no feature references except migration/tests documenting legacy input.

- [ ] **Step 4: Run TypeScript and backend import checks.**

Run: `cd frontend && npx tsc --noEmit`; `cd backend && .venv/bin/python -m compileall routes services models.py`

Expected: PASS after the new screen placeholder is registered.

- [ ] **Step 5: Commit.**

```bash
git add backend/server.py backend/routes/project_followup_routes.py 'frontend/app/(admin)/_layout.tsx' frontend/src/constants/floors.ts 'frontend/app/(admin)/notebook/[floor].tsx' 'frontend/app/(admin)/project/[floor].tsx'
git commit -m "refactor: replace project workspace with notebook route"
```

## Task 6: Build the pure frontend notebook model and autosave state

**Files:**
- Create: `frontend/src/components/notebook/notebookTypes.ts`
- Create: `frontend/src/components/notebook/notebookModel.ts`
- Create: `frontend/scripts/test-notebook.mjs`
- Modify: `frontend/package.json`

**Interfaces:**
- `NOTEBOOK_COLUMNS: readonly NotebookColumn[]`
- `QUOTATION_COLUMNS: readonly NotebookColumn[]`
- `NOTEBOOK_FILTERS: readonly NotebookFilter[]`
- `searchNotebookRows(rows, query): NotebookRow[]`
- `nextCell(position, key, rowCount, columnCount): CellPosition | null`
- `applyCellPatch(row, field, value): NotebookRow`
- `formatRupees(value): string`
- `formatIndianDate(value): string`

- [ ] **Step 1: Write executable pure-model tests.** Test exact column/filter lists, quotation-only columns, search-field inclusion/exclusion, keyboard navigation, currency/date formatting, and immutable single-field updates.

- [ ] **Step 2: Run the tests and verify failure.**

Run: `cd frontend && node --experimental-strip-types --no-warnings scripts/test-notebook.mjs`

Expected: FAIL because the pure model is absent.

- [ ] **Step 3: Implement pure types/helpers.** Keep the list of editable fields explicit; do not derive it from backend response keys. Map Enter/Tab/Shift+Tab/Down/Escape/arrow keys to cell positions and keep quotation fields unavailable until `is_converted` is true.

- [ ] **Step 4: Add the npm script and run tests.**

Run: `cd frontend && node --experimental-strip-types --no-warnings scripts/test-notebook.mjs`

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add frontend/src/components/notebook/notebookTypes.ts frontend/src/components/notebook/notebookModel.ts frontend/scripts/test-notebook.mjs frontend/package.json
git commit -m "feat: add notebook frontend model"
```

## Task 7: Build the virtualized notebook grid and toolbar

**Files:**
- Create: `frontend/src/components/notebook/NotebookCell.tsx`
- Create: `frontend/src/components/notebook/NotebookGrid.tsx`
- Create: `frontend/src/components/notebook/NotebookToolbar.tsx`
- Modify: `frontend/app/(admin)/notebook/[floor].tsx`

**Interfaces:**
- `NotebookCell({row, field, editable, onCommit, onNavigate})`
- `NotebookGrid({rows, view, onPatch, onConvert, onConflict})`
- `NotebookToolbar({view, filter, query, onViewChange, onFilterChange, onQueryChange, onStartNew})`

- [ ] **Step 1: Build the cell state machine.** Render a cell as text until selected; then render only that cell as an editor. Track `saving`, `saved`, `error`, and `conflict` states independently. On commit call the parent with `{field, value, updated_at}` and keep the prior value until the response succeeds.

- [ ] **Step 2: Build the virtualized grid.** Use React Native `FlatList`/`VirtualizedList` with server-page append, a horizontal `ScrollView`, sticky header/customer column where supported, responsive minimum widths, 44px touch targets, and a desktop column-width map persisted in local storage.

- [ ] **Step 3: Build exact toolbar controls.** Render only Follow-ups, Quotation Follow-ups, All, Pending, Won, Lost, New, Quotation, search, and New Follow-up. Do not add KPI cards, stages, site-visit controls, or dashboards.

- [ ] **Step 4: Add Lost/Won/conversion behavior.** Disable Lost until Notes is non-empty, confirm Won before calling the API, prevent edits on Won Follow-up fields, and show conversion inline with the three quotation inputs. Do not add a Save button.

- [ ] **Step 5: Run pure tests and typecheck.**

Run: `cd frontend && node --experimental-strip-types --no-warnings scripts/test-notebook.mjs && npx tsc --noEmit`

Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add frontend/src/components/notebook 'frontend/app/(admin)/notebook/[floor].tsx'
git commit -m "feat: build autosaved notebook grid"
```

## Task 8: Add responsive creation, timeline, pagination, and conflict UX

**Files:**
- Modify: `frontend/app/(admin)/notebook/[floor].tsx`
- Modify: `frontend/src/components/notebook/NotebookCell.tsx`
- Modify: `frontend/src/components/notebook/NotebookGrid.tsx`
- Modify: `frontend/src/components/notebook/NotebookToolbar.tsx`

- [ ] **Step 1: Implement API hooks.** Load the first page on floor/view/filter/search changes, debounce search, append `next_cursor` on scroll, and invalidate/reload only the affected row after patch/conversion/conflict.

- [ ] **Step 2: Implement autosave.** Use blur/Enter for cell patches, show Saving/Saved/Error, restore the last confirmed value on errors, and keep all other cells untouched. On HTTP 409 reload the row and apply a changed-cell highlight.

- [ ] **Step 3: Implement creation.** Use an inline draft row on desktop/tablet and a phone bottom sheet only for new rows. Auto-create once required fields are valid; no Save button. Resolve existing customers by mobile through the backend endpoint.

- [ ] **Step 4: Implement timeline.** Load newest-first events for the selected row and render the exact event vocabulary without edit/delete affordances.

- [ ] **Step 5: Implement empty/loading/error states.** Show “No follow-ups yet.” with New Follow-up, a compact loading row, and an inline retry state without modal error flows.

- [ ] **Step 6: Run frontend checks.**

Run: `cd frontend && node --experimental-strip-types --no-warnings scripts/test-notebook.mjs && npx tsc --noEmit && npx expo export --platform web`

Expected: PASS with no TypeScript errors or export failures.

- [ ] **Step 7: Commit.**

```bash
git add 'frontend/app/(admin)/notebook/[floor].tsx' frontend/src/components/notebook
git commit -m "feat: add notebook autosave and responsive workflow"
```

## Task 9: Remove stale prototype artifacts and validate navigation/isolation

**Files:**
- Modify: `frontend/app/(admin)/_layout.tsx`
- Modify: `frontend/src/constants/floors.ts`
- Modify: `backend/server.py`
- Delete: `frontend/app/(admin)/project/[floor].tsx`
- Delete: `backend/routes/project_followup_routes.py`

- [ ] **Step 1: Search for stale feature references.**

Run: `rg -n 'project-workspaces|ProjectFollowup|project_followup_routes|PROJECT JOURNAL|site_visit_scheduled|quotation_created|current_stage|estimated_budget|quotation_amount' backend frontend --glob '!**/test_reports/**'`

Expected: no runtime references; only migration compatibility mappings and tests may mention legacy names.

- [ ] **Step 2: Verify sidebar and route count.** Confirm only Kitchen Floor and Furniture Floor entries point into `/notebook/`, and the shared screen has only two view states.

- [ ] **Step 3: Run floor-isolation tests.** Add/execute tests showing a Kitchen request cannot see Furniture rows and a Furniture request cannot see Kitchen rows, including search, pagination, detail, patch, conversion, and timeline.

- [ ] **Step 4: Commit cleanup.**

```bash
git add 'frontend/app/(admin)/_layout.tsx' frontend/src/constants/floors.ts backend/server.py 'frontend/app/(admin)/project/[floor].tsx' backend/routes/project_followup_routes.py
git commit -m "chore: remove kitchen furniture prototype paths"
```

## Task 10: Full verification and production audit

**Files:**
- Create: `docs/superpowers/verification/2026-08-06-kitchen-furniture-notebook.md`
- Modify only if verification exposes a defect: the specific implementation file and its focused test.

- [ ] **Step 1: Run backend unit tests.**

Run: `cd backend && .venv/bin/pytest tests/unit -q`

Expected: all existing and new unit tests pass.

- [ ] **Step 2: Run frontend model/type/build checks.**

Run: `cd frontend && node --experimental-strip-types --no-warnings scripts/test-notebook.mjs && npx tsc --noEmit && npx expo export --platform web`

Expected: all commands pass.

- [ ] **Step 3: Verify responsive behavior.** Check the notebook at 320px, 390px, 430px, 768px, and 1440px. Record that phone uses the new-row bottom sheet only, all other cells edit inline, touch targets are at least 44px, columns scroll without clipping, and desktop has sticky/resizable columns.

- [ ] **Step 4: Verify runtime console and workflow behavior.** In a running app, exercise create, mobile reuse, field autosave, reload persistence, conflict response, conversion, Lost-disabled/Lost-audit, Won-lock, pagination, filters, search exclusion, and both-floor isolation. Record zero console errors.

- [ ] **Step 5: Audit the exact definition of done.** Confirm two feature modules, two views, exact allowlists, no Save buttons, no duplicate customers/rows, immutable timeline, migration idempotency, no stale prototype runtime references, no regressions, and clean working tree except known unrelated user work.

- [ ] **Step 6: Write verification evidence.** Include command output, test counts, screenshots or viewport evidence, and any remaining limitations. Do not claim production readiness if any item is missing.

- [ ] **Step 7: Commit verification evidence.**

```bash
git add docs/superpowers/verification/2026-08-06-kitchen-furniture-notebook.md
git commit -m "test: verify kitchen furniture notebook"
```

---

## Self-review checklist

- Spec coverage: autosave, conflicts, search fields, same-row conversion, exact timeline, notebook appearance, column behavior, keyboard workflow, required fields, Won workflow, currency/date formatting, 10k-row pagination/virtualization, empty state, mobile bottom sheet, exact definition of done: covered by Tasks 1–10.
- Placeholder scan: no TBD/TODO or unspecified “appropriate” work appears in the plan.
- Interface consistency: backend row fields use `customer_phone`, `kitchen_type`, `is_converted`, and `updated_at` consistently; frontend uses the same field names and patch payload.
- Scope: the plan removes only the Kitchen/Furniture prototype path and preserves unrelated ERP floors/modules and unrelated worktree changes.
- Safety: migration is additive/idempotent and leaves `project_followups` untouched; cleanup occurs only after migration and tests pass.
