# AGENTS.md — BuildCon House ERP (forge2.0)

Guidance for any AI agent (Emergent, Claude Code, or otherwise) picking up work in this repo. Read this before re-deriving context from scratch — it's meant to save tokens, not replace judgment.

## What this project is

FastAPI + MongoDB Atlas (cloud, not local) + Supabase (file storage) backend, Expo/React Native Web frontend (Expo Router). A multi-floor ERP for a bathroom-fittings + tiles distributor: `first-floor` (display name "The Sanitary Bathroom") holds the existing ~2,600-product sanitaryware catalog and all real business data today; `ground-floor` is the new tile section (schema/isolation work in progress, no real tile data yet); `second-floor` also exists as a floor entity but is otherwise unused so far.

- Live Atlas DB: `buildcon_house` (not `buildcon`, a stale demo DB on the same cluster).
- Supabase buckets: `forge-products` (public), `forge-private`.
- Local dev: `backend/.venv` (Python 3.14), `backend/.env` / `frontend/.env` hold real credentials (gitignored, not committed — verified clean).
- Backend commonly runs on port 8010 (`uvicorn server:app --port 8010`) since something else occupies 8000 on the primary dev Mac.

## Important — this repo has concurrent editors

**This repo is being worked on by more than one agent/process at once.** As of 2026-07-18 there were ~99–106 files sitting uncommitted in the working tree from a separate, non-Claude-Code process (git log shows a long history of `auto-commit for <uuid>` entries — almost certainly an Emergent-platform agent working the same codebase in parallel). That work is legitimate and already includes real, wanted fixes (e.g. a session-security hardening pass in `auth.py`, an optimistic-concurrency rewrite of `_apply_stage_change` in `purchases_tracker.py`, and a role-permission fix lowering `move_item`/`bulk_move`/`transfer_item*` from `require_min_role("sales")` to `"warehouse"`).

**If you are about to commit and a file you're touching has other unrelated uncommitted changes in it: do not sweep them into your commit.** `git add <file>` stages the whole file, not just your diff — use `git add -p` and select only your own hunks, so each commit accurately describes its own contents and the other process's in-progress work isn't silently relabeled or buried under an unrelated commit message. This was a real mistake made and then corrected during the floor-isolation-fix work below — see that section for the concrete example.

**Update (2026-07-18):** all ~99 files of that backlog have now been committed as `96ffda2` ("chore: commit accumulated prior-session work..."), since Task 1's isolated commit turned out to depend on foundational `auth.py` helpers (`floor_query`/`floor_for_write`/`accessible_floor_ids`) that were themselves part of that uncommitted backlog — every prior session's work had been sitting uncommitted, at real risk of loss, this whole time. Going forward, the working tree should stay much closer to git history; if you find a large uncommitted backlog again, treat it the same way (commit it honestly labeled as pre-existing work, don't silently absorb it into an unrelated task commit).

## Current effort: floor-isolation fix + tile-ready catalog schema

**Root cause (confirmed 2026-07-17 by direct query against the live Atlas DB, not assumption):** every real record in the database — all 2,601 products, 69 follow-ups, 13 purchase orders, 12 payments, 5 customers, 41 quotations, 5 suppliers — was tagged `floor_id="first-floor"`, and switching the UI to Ground floor showed that same first-floor data instead of an empty state, because a specific, mechanically-identifiable set of backend read *and* write paths never applied floor scoping at all. Full root-cause writeup, the complete list of every affected code site, and exact before/after code for every fix are in:

**`docs/superpowers/specs/2026-07-17-floor-isolation-and-tile-catalog-design.md`** (design/spec — read this for *why*)
**`docs/superpowers/plans/2026-07-17-floor-isolation-fix.md`** (implementation plan — read this for *exact code*, task-by-task, TDD-style)

Do not re-derive the root cause or re-scan the codebase for affected endpoints — both are already fully enumerated in those two files. If you need to know "is X in scope," check the plan's 20 task headers first.

### Established pattern (use this, don't invent a new one)

- `floor_query(user, base)` — Mongo filter dict, for queries that take a filter (`db.collection.find(floor_query(user, {...}))`).
- `floor_for_write(user)` — single floor_id string, for **human-initiated** creates (`Quotation(..., floor_id=floor_for_write(user))`).
- `floor_scope_ids(user)` — plain `Optional[list[str]]`, for code that builds its own aggregation pipeline or in-memory filter instead of taking a Mongo filter dict (added in Task 1 of the plan above).
- **Automation/event-handler-created records** (background workflows with no live user, e.g. `domain_outbox.py`, `transfer_workflow.py`, `followup_engine.py`) inherit `floor_id` from their immediate **source document** instead — never `floor_for_write()` — since these handlers often only have an actor id/name string, and a record derived from a ground-floor source must stay ground-floor regardless of which floor the triggering user happens to have selected. See the plan's Milestone B for the exact helper functions (`_transfer_floor_id`, `_source_floor_id`, `_followup_floor_id`) already added for this.

All four live in `backend/auth.py` (the first three) or as small local helpers next to their one caller (the fourth kind) — don't scatter re-implementations of the same logic across files.

### Task status (20 tasks total, 3 milestones)

Update this table as work lands. Commit SHAs below are on `main` (this repo commits directly to main — no feature-branch convention here).

| # | Task | Status | Commit(s) |
|---|------|--------|-----------|
| 1 | Purchases Tracker main board (`_iter_items` + `GET /items`) + `floor_scope_ids` in `auth.py` | **Done** (spec + code-quality review both passed) | `4ffad24` |
| 2 | Purchases Tracker facet endpoints (`/stages`, `/brands`, `/customers`) | **Done** (spec + code-quality review both passed) | `a1d0174` |
| 3 | Purchases Tracker remaining read endpoints (`customer_workspace`, `dispatch_record`, `list_shortages`, `export_xlsx`, `get_item`, `item_transfer_history`) | **Done** (spec + code-quality review both passed; 2 minor style-consistency notes left as optional follow-up, see review) | `bfdeb65` |
| 4 | Follow-ups `/insights` | **Done** (spec + code-quality review both passed) | `781a65b` |
| 5 | Reports overview | **Done** (spec + code-quality review both passed) | `da9e240` |
| 6 | Dashboard `followups_due` counter | **Done** (spec + code-quality review both passed) — **Milestone A (read-path scoping) fully complete** | `00b70fd` |
| 7 | `domain_outbox.py::_handle_order_placed` (PO + Payment floor inheritance) | Not started | — |
| 8 | `domain_outbox.py::_upsert_followup` | Not started | — |
| 9 | `followup_engine.py` rule-based auto-follow-up engine | Not started | — |
| 10 | `transfer_workflow.py::execute_transfer` | Not started | — |
| 11 | `transfer_workflow.py::handle_purchase_transferred` | Not started | — |
| 12 | Legacy inline transfer/reorder code in `purchases_tracker.py` | Not started | — |
| 13 | Follow-up call-back rescheduling (`POST /{id}/log-call`) | Not started | — |
| 14 | `Brand`/`Category` gain `floor_id` + backfill migration `0004` | Not started | — |
| 15 | Floor-scope the in-memory catalog engine (`catalog_service.py`) | Not started | — |
| 16 | Thread floor scope through Catalog routes; fix product-creation floor default | Not started | — |
| 17 | `POST /brands`, `POST /categories` | Not started | — |
| 18 | `size` field on `Product` + search/facets | Not started | — |
| 19 | SKU uniqueness migration `0005` (per floor+brand) — **has a manual pre-step: a known live duplicate SKU (`26456000`, two Hansgrohe products) must be resolved before this migration is run against production, or its index will fail to build** | Not started | — |
| 20 | Frontend `variantDescriptor()` helper + `PickerCard`/`VariantChip`/`SwapSheet`/`ProductModal` display fix | Not started | — |

**Explicitly out of scope for this plan** (decided with the user, don't re-litigate): no new MongoDB/Supabase infrastructure (already cloud-hosted, confirmed via `backend/.env`'s real Atlas `mongodb+srv://` URL); no tile product data import (schema/isolation only — data entry is separate, later work); no Cmd+K quick-search brand-scoping (confirmed not needed — Catalog page + Quotation Builder search, both fixed here, are what matter); no `LineRow`/`Line`-type/`QuotationLineItem` changes for `size` (LineRow only shows a colour swatch, not a text fallback chain — not affected by the bug this plan fixes).

### How to continue implementing

1. Open `docs/superpowers/plans/2026-07-17-floor-isolation-fix.md`, find the next "Not started" task by number, and follow it exactly — it already has complete before/after code, the exact test to write first (TDD), and the exact commit message.
2. Run backend tests from `backend/` using `.venv/bin/pytest tests/unit -q` (existing venv, don't create a new one). Baseline as of 2026-07-18 is 45 passed, 0 failed — any new failures are yours to explain, not pre-existing.
3. Before committing, run `git status --short` on the specific files you touched. If any of them show unrelated pre-existing changes beyond your own diff, use `git add -p` and select only your hunks (see "Important — this repo has concurrent editors" above). Don't skip this — it's the difference between a reviewable commit and a misleading one.
4. Update the task status table above when a task lands.
5. This repo pushes to `origin` (`https://github.com/yashvardhansinh2510-max/forge2.0.git`) on branch `main`. Confirm with the user before pushing if you're unsure whether local commits are ready.

### Known gotchas (don't rediscover these the hard way)

- **Migration idempotency:** `backend/migrations/` migrations must be forward-only and safe to run twice, but MongoDB's `create_index` throws `OperationFailure` code 85 (`IndexOptionsConflict`) if a same-key index already exists under a different name — this has happened twice already (see `migrations/0002` and `0003`'s docstrings). Always wrap `create_index` calls the way `migrations/0003`'s `_create_index_tolerant` helper does.
- **Catalog is an in-memory snapshot, not per-request Mongo queries:** `backend/services/catalog_service.py` loads the whole product catalog into memory at startup (Atlas is ~228ms round-trip away; the full catalog is a few MB) and refreshes on writes. Don't add per-request Mongo queries to catalog read paths — thread new filters through the existing `_matches_filters`/snapshot functions instead.
- **Floor `first-floor`'s display name is "The Sanitary Bathroom"** in the live `db.floors` collection, but its `id`/`slug` is still literally `"first-floor"` — don't rename the slug, only ever the `name` field, or every `floor_id` reference throughout the codebase breaks.
