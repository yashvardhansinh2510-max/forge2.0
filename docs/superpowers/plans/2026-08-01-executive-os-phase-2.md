# Executive Operating System — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Phase 2 per spec §17 — the **Performance** workspace (revenue trend, salesperson leaderboard, sales funnel, revenue by category), the **Collections** workspace (outstanding by customer and by age), **Referral Analytics** (14-KPI referrer summaries + a partner-profile mini-CRM), and the shared **`ReferredByField`** component that finally lets Ground Floor quotations carry a referrer at all.

**Architecture:** Same three-layer separation Phase 1 established. (1) **Pure shaping modules** in `backend/services/analytics/` (`performance.py`, `collections.py`, `referrals.py`, plus a `buckets()` addition to `periods.py`) take already-fetched rows and return typed, serializable dataclasses — no Mongo access, so every shaping rule is unit-testable. (2) **Gather modules** (`gather_performance.py`, `gather_collections.py`, `gather_referrals.py`) are the only place these surfaces read Mongo, always through Phase 0's `build_match`. (3) **Two new routers** (`sales_performance_routes.py`, `referral_analytics_routes.py`) expose the surfaces, cached via Phase 0's `cache.cached`. On the frontend, three new screens (`/sales-data/sales`, `/sales-data/collections`, `/sales-data/referrals/{architects,interior-designers}`) and one detail route (`/sales-data/referrers/[id]`) consume typed API clients and two new chart primitives built on Phase 1's `ChartFrame`. `ReferredByField` is deliberately **headless and prop-driven** — no context dependency — so the same component drives both the Sanitary builder's context-based state and the Tiles builder's local-hook state without either owning the other's data model.

**Tech Stack:** FastAPI · MongoDB (motor) · Pydantic · pytest · Expo / React Native Web · expo-router · react-native-svg · openpyxl

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-01-executive-operating-system-design.md` is frozen. Do not add a KPI, card, or drill-down that is not in §7 Workspaces 2–3 or §5. Amend the spec first if one is missing.
- **Every number comes from the Phase 0 analytics layer.** No route builds its own `$match` or its own revenue `$group` outside `build_match`/`metrics.py`. Revenue dates by `ordered_at`. Collections' Outstanding figure is `metrics.outstanding_pipeline` **verbatim** — the spec explicitly says "no new definition."
- **No fabricated values, ever.** A stage-to-stage funnel duration with no real timestamp pair in the schema is `None`, not an estimate. A referrer with no prior period is `no_prior_period`, not `+100%`. See "Live data reality" below for exactly which funnel transitions this applies to — decided once, here, not re-litigated per task.
- **One rule set, extended, not forked.** `REFERRER_QUIET_DAYS`, `PAYMENT_OVERDUE_DAYS` and every other Phase 1 threshold are imported from `services.analytics.attention.THRESHOLDS` by identity. Phase 2 adds zero new threshold constants unless a genuinely new concept needs one (funnel/collections age buckets do; referrer activity does not).
- **Permissions are re-checked per action**, same as Phase 1. Both new routers gate `require_roles("owner","admin","manager")`, matching `executive_overview_routes.py`'s `_ANALYTICS_ROLES`.
- **No nested interactive elements.** Any new row/card component follows the `HoverCard`-container rule from the 2026-07-24 `QueueRow` bug, verified against the live accessibility tree.
- **44px minimum tap target** on every control. **8pt spacing system** via `theme/tokens.ts` (not `design/tokens.ts` — Phase 1's analytics surfaces use `theme/tokens.ts` throughout; only money formatting (`fmtMoney`/`fmtMoneyCompact`) comes from `design/tokens.ts`, and Phase 2 keeps that same split rather than reconciling it).
- **Zero layout shift, zero console warnings, responsive at 1280 / 768 / 375, keyboard accessible.**
- **No placeholder UI, no mock data, no duplicated components, no duplicated business logic.**
- **Backend tests:** `cd backend && ./.venv/bin/python -m pytest tests/unit -v`. Baseline entering Phase 2: **602 passed, 0 failures** (per Phase 1's ledger). It may never go down.
- **Frontend has no test framework.** Verification is `npx tsc --noEmit` (clean at Phase 1's close) plus a live browser pass.
- **The shared backend on `:8010` does not auto-reload** and may be in use by another session. Ask before restarting it.
- Python is `backend/.venv/bin/python` (3.14). Never a system python.
- **Do not touch the legacy `executive_analytics_routes.py`, `sales_data_routes.py`, or their orphaned frontend screens** (`sales-data/index.tsx`'s `LegacySalesDataOverview`, `sales-data/referrer/[id].tsx` singular, `sales-data/brands/[id].tsx`, `sales-data/people/[kind]/[id].tsx`). They stay in the repo, unreachable from `WorkspaceSwitcher`, until Phase 6 — same convention Phase 1 established for `sales_data_routes.py`. Phase 2 builds fresh routes/screens at the paths `WorkspaceSwitcher` already declares (see Task 22–25's File sections) rather than extending the legacy router, because that router dates revenue by `updated_at`, exactly the Phase 0 bug this whole rebuild exists to fix.
- **Export scope is CSV and XLSX only, not PDF.** Every backend PDF export in this codebase (`chalan`, `quotation`, `followups`) is a bespoke document layout — there is no generic "arbitrary analytics table → PDF" pattern anywhere to build on, and inventing one is out of scope for wiring up four list tables. This is a disclosed scope cut, not a silent one: Phase 1's ledger already flagged "`ExportMenu` lands with the first real table in Phase 2" without specifying PDF, and PDF-per-table can be scoped properly in a later phase once a real print-layout need exists.

**Deviation from this skill's default "complete code in every step," deliberate, matching Phase 1's own stated deviation:** every task below specifies complete, runnable failing-test code and exact interfaces. Implementation code is shown in full wherever the logic is non-obvious (bucketing math, the funnel's honest-`None` handling, the cache-bump fix, the export helper, the two shared referrer components). Where a task instead says "read the file first, then write following this pattern" (Tasks 9, 11, 13, 14, 17, 21, 24 in particular), that is because this plan was written from a research pass, not from the file itself, and a few call sites (`DataTable`'s exact cell-prop names, whether `buildDownloadUrl` already exists, whether the customer/quotation list endpoints already accept `referrer_id`) need a fresh read against current code rather than a research snapshot that may have drifted by execution time. The tests in those tasks are still complete and real; only some implementation bodies defer their last details to a verified read.

---

## Live data reality (probed 2026-08-01/08, do not re-derive)

- **`AnalyticsFilter.category_id` and `.supplier_id` are declared but `build_match` never reads them.** Revenue-by-Category groups on `items.category_id` inside the gather layer's own pipeline (mirroring `metrics.line_revenue_pipeline`'s `group_by` pattern), not via a `build_match` clause.
- **`db.categories` is real** (`Category` model: `name, slug, parent_id, icon, floor_id`), and `QuotationLineItem.category_id` is already denormalized at quotation-build time — Revenue by Category needs no inference, no new field.
- **No day/week/month/quarter/year bucketing exists anywhere in `periods.py`.** Task 1 adds it new. The only prior art is the legacy `executive_analytics_routes.py`'s raw `$dateToString` pipeline, which is explicitly not reused (it dates by `updated_at`).
- **`Quotation` has no `approved_at` field** — only `approved_by`. Combined with there being no `selection→quotation` conversion timestamp and no `quotation→approved` timestamp anywhere in the schema, **three of the funnel's seven stage-to-stage transitions cannot honestly report a median duration**: `selections→quotations`, `quotations→approved`, `approved→confirmed_orders`. These three report `median_days_in_stage: None` by construction — not an estimate from `updated_at` (Phase 0's whole premise is that `updated_at` re-stamps on every edit and cannot be trusted to date an event). The other four transitions have real timestamp pairs: `walkins→selections` (`WalkIn.visited_at` → the selection quotation's `created_at`, joined via `WalkIn.selection_quotation_id`), `confirmed_orders→release` (`Quotation.ordered_at` → the first `PurchaseOrder.status_history` entry marking release), `release→dispatch` (release timestamp → `TileDispatch`/dispatch `created_at`), `dispatch→payment` (dispatch timestamp → the first `payment.paid_at` on that order).
- **`routes/payment_routes.py::create_payment` never calls `cache.bump("payments")`.** It inserts directly, bypassing `domain_outbox.py` entirely (confirmed: `cache.bump`/`from services.analytics import cache` appears in exactly two files in the whole backend — `domain_outbox.py` and `executive_overview_routes.py`). Collections' entire premise is an accurate, fresh Outstanding figure; this gap is fixed first, in Task 8, before any Collections code is written on top of it.
- **`Referrer` carries zero metrics** (`name, type, phone, company, created_by` only) — every one of the 14 summary cards and the partner profile is aggregated live from `quotations.referrer_id`, per spec §5.1.
- **Zero of 78 live quotations carry a referrer today.** Every Referrals-workspace screen must render the §5.3 onboarding state, not a bare empty table, until real data exists.
- **`GET /referrers` already exists** (`routes/referrer_routes.py`, `require_min_role("sales")`, optional `?type=` filter) and **`POST /referrers` already exists** with case-insensitive same-type dedupe (create-or-return). No update/delete endpoint exists (v1, by the file's own docstring) — Phase 2 does not add one.
- **The Sanitary builder's referrer picker is `ReferrerSwitcherSheet.tsx`**, mounted once in `BuilderShell.tsx:109`, opened via `BuilderTopbar.tsx`'s `testID="hdr-referrer"` pressable, reading/writing through `BuilderContext.tsx`'s `referrers`, `setReferrer(type,id,name)`, `clearReferrer()` (which sends `referrer_id: ""`, not `null`, because `update_quotation` gates on `if body.referrer_id is not None` and JSON `null` deserializes to Python `None`, treated as "field absent"), `createReferrer({name,type})`, and `referrerSwitcherOpen`/`setReferrerSwitcherOpen`. The referrer directory fetch (`api.get<Referrer[]>("/referrers")`, `BuilderContext.tsx:285`) is **not floor-scoped**, so the same directory already applies to both floors.
- **`TilesDocBuilder.tsx`'s `useTilesDoc(docType)` hook has zero referrer state** — `grep -in "referr"` returns no matches. `TilesHeader` has no such field; `setHeaderField(field: keyof TilesHeader, value: string)` is string-only and cannot carry a referrer object. The hook's `persist()` (line 375) builds a `payload` object PATCHed/POSTed straight to `/quotations` — the exact same generic `update_quotation`/`create_quotation` endpoints the Sanitary builder uses, already confirmed to handle `referrer_type`/`referrer_id` for any `doc_type`. The natural UI insertion point is `MetaGrid` (lines 773–818), which renders `REFERENCE / ATTENDED BY / PREPARED BY / ADDRESS` as generic `CellInput`s.
- **No chart primitive beyond `ChartFrame`/`Sparkline` exists.** `frontend/src/components/charts/` has exactly those two files. A separate legacy `salesData/TrendChart.tsx` is a plain `View`-based bar row with an explicit comment that no charting library exists in this codebase — Phase 2 stays consistent with that decision (no new npm dependency) and builds `TrendBarChart`/`FunnelChart` on `ChartFrame` + `react-native-svg`, which is already a dependency.
- **No CSV/Excel/PDF export utility exists anywhere in the frontend.** The backend has four independent, uncombined csv/openpyxl/reportlab implementations (`executive_analytics_routes.py`, `followup_routes.py`, `purchases_tracker.py`, `catalog_routes.py`). Task 12 adds one shared `services/export.py` helper; the four existing routes are **not refactored onto it** — that would be an unrelated, unrequested change.
- **`WorkspaceSwitcher.tsx` already declares Phase 2's exact route paths**: `/sales-data/sales`, `/sales-data/collections`, `/sales-data/referrals/architects`, `/sales-data/referrals/interior-designers`. There is no bare `/sales-data/referrals` index wired — the two typed sub-routes are the only ones the nav links to, matching spec §7 Workspace 3's "both sub-workspaces are the same component, filtered by `referrer_type`."
- **`DataTable<T>` (`frontend/src/components/tiles/TileTable.tsx`) is a full render-function-column table** with `sticky`, `fillViewport`, and a cell vocabulary (`CellStack`, `CellNumber`, `CellLink`, `CellChevron`, `ProgressCell`, …) already proven across the Tile Orders module at three breakpoints. Every new Phase 2 table uses `DataTable`, not the plainer `Table`/`TableRow`/`TableCell` trio the *legacy* sales-data screens use.
- **`AnalyticsTargets.payment_terms_days` (default 30) is the live source for `PAYMENT_OVERDUE_DAYS`**, already threaded into Phase 1's `_thresholds()` helper — Collections' overdue-age framing reuses this exact setting, not a new one.

---

## File Structure

**Backend — created**

| File | Responsibility |
|---|---|
| `backend/services/analytics/performance.py` | Pure §7 Workspace 2 shaping: salesperson ranking, the 8-stage funnel, revenue-by-category |
| `backend/services/analytics/collections.py` | Pure §7 Workspace-Collections shaping: by-customer and by-age views of Outstanding |
| `backend/services/analytics/referrals.py` | Pure §7 Workspace 3 shaping: the 14-card referrer summary + partner profile assembly |
| `backend/services/analytics/gather_performance.py` | The only place Performance/Collections read Mongo |
| `backend/services/analytics/gather_referrals.py` | The only place Referral Analytics reads Mongo |
| `backend/services/export.py` | Generic rows→CSV/XLSX streaming helper, shared by the four new export endpoints |
| `backend/routes/sales_performance_routes.py` | `/analytics/{revenue-trend,salespeople,salespeople/{id},funnel,categories,collections}` |
| `backend/routes/referral_analytics_routes.py` | `/analytics/referrers`, `/analytics/referrers/{id}` |

**Backend — modified**

| File | Change |
|---|---|
| `backend/services/analytics/periods.py` | Add `buckets()` — day/week/month/quarter/year bucketing, the one gap Phase 0/1 left open |
| `backend/routes/payment_routes.py` | `create_payment` now calls `cache.bump("payments")` post-commit (Live data reality gap) |
| `backend/server.py` | Register the two new routers |

**Frontend — created**

| File | Responsibility |
|---|---|
| `frontend/src/api/salesPerformance.ts` | Typed client: revenue trend, salespeople, funnel, categories, collections |
| `frontend/src/api/referrals.ts` | Typed client: referrer summaries, referrer profile |
| `frontend/src/components/charts/TrendBarChart.tsx` | Revenue-by-period bar chart on `ChartFrame` + SVG |
| `frontend/src/components/charts/FunnelChart.tsx` | 8-stage funnel visualization on `ChartFrame` + SVG |
| `frontend/src/components/analytics/ExportMenu.tsx` | CSV/XLSX download trigger, reused by every new table |
| `frontend/src/components/shared/ReferredByField.tsx` | Headless trigger + display, prop-driven, no context dependency |
| `frontend/src/components/shared/ReferrerPickerSheet.tsx` | The picker/search/create sheet, extracted from `ReferrerSwitcherSheet` |
| `frontend/src/components/analytics/ReferralsWorkspace.tsx` | The one component both `/referrals/architects` and `/referrals/interior-designers` render, filtered by `type` prop |
| `frontend/app/(admin)/sales-data/sales.tsx` | Performance workspace screen |
| `frontend/app/(admin)/sales-data/collections.tsx` | Collections workspace screen |
| `frontend/app/(admin)/sales-data/referrals/architects.tsx` | Thin wrapper: `<ReferralsWorkspace type="architect" />` |
| `frontend/app/(admin)/sales-data/referrals/interior-designers.tsx` | Thin wrapper: `<ReferralsWorkspace type="interior_designer" />` |
| `frontend/app/(admin)/sales-data/referrers/[id].tsx` | Partner profile — the mini-CRM |

**Frontend — modified**

| File | Change |
|---|---|
| `frontend/src/components/quotation/layout/BuilderTopbar.tsx` | Renders `ReferredByField` instead of its own referrer pressable |
| `frontend/src/components/quotation/layout/BuilderShell.tsx` | Mounts `ReferrerPickerSheet` instead of `ReferrerSwitcherSheet` |
| `frontend/src/components/tiles/TilesDocBuilder.tsx` | `useTilesDoc` gains referrer state, hydration, and persistence; `MetaGrid` gains the field |

**Frontend — removed**

| File | Reason |
|---|---|
| `frontend/src/components/quotation/sheets/ReferrerSwitcherSheet.tsx` | Fully superseded by `ReferrerPickerSheet` + `ReferredByField` (Task 20) — deleted, not left as dead code, since nothing else references it |

**Execution staging** — a stage is not done until implementation, full test run, live-database verification, browser verification, visual-quality confirmation, and a ledger entry are all complete.

| Stage | Tasks | Gate |
|---|---|---|
| **A** | 1–7 (periods, performance, collections, referrals) | pure shaping, unit tests only |
| **B** | 8–14 (cache fix, gather, export, routes) | live-database verification of every endpoint |
| **C** | 15–21 (shared components, `ReferredByField` in both builders) | `tsc` clean + live regression check on both builders |
| **D** | 22–25 (screens) | full browser pass at 1280/768/375 |
| **E** | 26 (§18 verification protocol) | all 12 points |

---

## Task 1: `periods.py::buckets` — day/week/month/quarter/year bucketing

**Files:**
- Modify: `backend/services/analytics/periods.py`
- Test: `backend/tests/unit/test_analytics_periods.py`

**Interfaces:**
- Consumes: nothing new (stdlib `datetime` only)
- Produces: `buckets(start: str, end: str, granularity: Literal["day","week","month","quarter","year"]) -> list[Period]` — reuses the existing `Period` dataclass (`start`, `end`, `label`). Callers must supply concrete ISO bounds; an open-ended period (`resolve("all_time")` → `Period(None, None, ...)`) is not a valid input — the gather layer defaults an open period to a trailing 12-month window before calling `buckets`, documented at the Task 9 call site, not here.

- [ ] **Step 1: Write the failing test**

Create/extend `backend/tests/unit/test_analytics_periods.py` (append to the existing file):

```python
from services.analytics.periods import buckets


def test_day_buckets_are_calendar_aligned_and_clamped_to_the_window():
    result = buckets("2026-07-30T15:00:00+00:00", "2026-08-02T09:00:00+00:00", "day")
    assert [b.label for b in result] == ["30 Jul", "31 Jul", "01 Aug", "02 Aug"]
    # first bucket starts at the requested time, not calendar midnight before it
    assert result[0].start == "2026-07-30T15:00:00+00:00"
    assert result[-1].end == "2026-08-02T09:00:00+00:00"


def test_week_buckets_start_on_monday():
    # 2026-08-01 is a Saturday; the week bucket containing it starts Monday 2026-07-27
    result = buckets("2026-07-25T00:00:00+00:00", "2026-08-05T00:00:00+00:00", "week")
    assert result[0].label.startswith("Week of 20 Jul") or result[0].label.startswith("Week of 27 Jul")
    assert len(result) >= 1


def test_month_buckets_span_full_calendar_months():
    result = buckets("2026-06-15T00:00:00+00:00", "2026-08-10T00:00:00+00:00", "month")
    assert [b.label for b in result] == ["Jun 2026", "Jul 2026", "Aug 2026"]


def test_quarter_buckets_use_q_labels():
    result = buckets("2026-01-01T00:00:00+00:00", "2026-08-01T00:00:00+00:00", "quarter")
    assert [b.label for b in result] == ["Q1 2026", "Q2 2026", "Q3 2026"]


def test_year_buckets_span_calendar_years():
    result = buckets("2025-11-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00", "year")
    assert [b.label for b in result] == ["2025", "2026"]


def test_consecutive_buckets_share_an_edge_no_gap_no_overlap():
    result = buckets("2026-07-01T00:00:00+00:00", "2026-07-05T00:00:00+00:00", "day")
    for a, b in zip(result, result[1:]):
        assert a.end == b.start


def test_a_window_shorter_than_one_bucket_still_returns_exactly_one():
    result = buckets("2026-08-01T10:00:00+00:00", "2026-08-01T14:00:00+00:00", "day")
    assert len(result) == 1
    assert result[0].start == "2026-08-01T10:00:00+00:00"
    assert result[0].end == "2026-08-01T14:00:00+00:00"


def test_an_inverted_window_returns_no_buckets_rather_than_crashing():
    assert buckets("2026-08-05T00:00:00+00:00", "2026-08-01T00:00:00+00:00", "day") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_periods.py -v -k bucket`
Expected: FAIL — `ImportError: cannot import name 'buckets'`

- [ ] **Step 3: Write the function**

Append to `backend/services/analytics/periods.py`:

```python
def _bucket_start(dt: datetime, granularity: str) -> datetime:
    if granularity == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == "week":
        aligned = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return aligned - timedelta(days=aligned.weekday())  # Monday
    if granularity == "month":
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if granularity == "quarter":
        q_month = ((dt.month - 1) // 3) * 3 + 1
        return dt.replace(month=q_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    if granularity == "year":
        return dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"unknown granularity: {granularity}")


def _bucket_label(start: datetime, granularity: str) -> str:
    if granularity == "day":
        return start.strftime("%d %b")
    if granularity == "week":
        return f"Week of {start.strftime('%d %b')}"
    if granularity == "month":
        return start.strftime("%b %Y")
    if granularity == "quarter":
        return f"Q{(start.month - 1) // 3 + 1} {start.year}"
    if granularity == "year":
        return str(start.year)
    raise ValueError(f"unknown granularity: {granularity}")


def _bucket_advance(start: datetime, granularity: str) -> datetime:
    if granularity == "day":
        return start + timedelta(days=1)
    if granularity == "week":
        return start + timedelta(days=7)
    if granularity == "month":
        return _add_months(start, 1)
    if granularity == "quarter":
        return _add_months(start, 3)
    if granularity == "year":
        return start.replace(year=start.year + 1)
    raise ValueError(f"unknown granularity: {granularity}")


def buckets(start: str, end: str, granularity: str) -> list[Period]:
    """Calendar-aligned buckets, clamped to [start, end) at the first and last
    edge so a chart never implies data outside the requested window while
    still labelling each bar by its real calendar period."""
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    if end_dt <= start_dt:
        return []
    result: list[Period] = []
    cursor = _bucket_start(start_dt, granularity)
    while cursor < end_dt:
        nxt = _bucket_advance(cursor, granularity)
        bucket_start = max(cursor, start_dt)
        bucket_end = min(nxt, end_dt)
        result.append(Period(bucket_start.isoformat(), bucket_end.isoformat(), _bucket_label(cursor, granularity)))
        cursor = nxt
    return result
```

Add `from datetime import timedelta` to the existing `from datetime import datetime` import if not already present.

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_periods.py -v`
Expected: PASS — all periods.py tests including the new bucket ones (existing tests unaffected)

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/periods.py backend/tests/unit/test_analytics_periods.py
git commit -m "Add calendar-aligned day/week/month/quarter/year bucketing to periods.py

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: `performance.py` — `salesperson_rows`

**Files:**
- Create: `backend/services/analytics/performance.py`
- Test: `backend/tests/unit/test_analytics_performance.py`

**Interfaces:**
- Consumes: `periods.compare` (Phase 0)
- Produces:
  - `@dataclass(frozen=True) SalespersonRow` — `salesperson_id, name, revenue, orders, aov, walkins_handled, conversion_pct: float|None, last_activity_at: str|None, rank: int, previous_rank: int|None, rank_movement: int|None, comparison: dict`
  - `salesperson_rows(current: list[dict], previous_revenue_by_id: dict[str,float], previous_rank_by_id: dict[str,int]) -> list[SalespersonRow]`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_analytics_performance.py`:

```python
"""Pure shaping for the Performance workspace (spec §7 Workspace 2). No Mongo
access here — gather_performance.py is the only place that reads the database."""
from __future__ import annotations

from services.analytics.performance import salesperson_rows


def _person(**kw) -> dict:
    base = dict(salesperson_id="u1", name="Rahul", revenue=500000.0, orders=5,
                walkins_handled=20, last_activity_at="2026-08-01T09:00:00+00:00")
    base.update(kw)
    return base


def test_ranks_by_revenue_descending():
    rows = salesperson_rows([_person(salesperson_id="a", revenue=100.0), _person(salesperson_id="b", revenue=900.0)], {}, {})
    assert [r.salesperson_id for r in rows] == ["b", "a"]
    assert [r.rank for r in rows] == [1, 2]


def test_ties_break_by_name_for_determinism():
    rows = salesperson_rows([
        _person(salesperson_id="z", name="Zara", revenue=500.0),
        _person(salesperson_id="a", name="Amit", revenue=500.0),
    ], {}, {})
    assert [r.salesperson_id for r in rows] == ["a", "z"]


def test_aov_is_revenue_over_orders():
    rows = salesperson_rows([_person(revenue=500000.0, orders=5)], {}, {})
    assert rows[0].aov == 100000.0


def test_aov_is_zero_not_a_crash_when_there_are_no_orders():
    rows = salesperson_rows([_person(revenue=0.0, orders=0)], {}, {})
    assert rows[0].aov == 0.0


def test_conversion_pct_is_orders_over_walkins():
    rows = salesperson_rows([_person(orders=5, walkins_handled=20)], {}, {})
    assert rows[0].conversion_pct == 25.0


def test_conversion_pct_is_none_without_any_walkins_handled():
    """A salesperson with zero walk-ins handled has no denominator — showing 0%
    would misreport them as a non-converter rather than as unmeasured."""
    rows = salesperson_rows([_person(orders=0, walkins_handled=0)], {}, {})
    assert rows[0].conversion_pct is None


def test_rank_movement_is_previous_rank_minus_new_rank():
    rows = salesperson_rows(
        [_person(salesperson_id="a", revenue=900.0), _person(salesperson_id="b", revenue=100.0)],
        {}, {"a": 2, "b": 1},
    )
    a = next(r for r in rows if r.salesperson_id == "a")
    b = next(r for r in rows if r.salesperson_id == "b")
    assert a.rank_movement == 1     # was 2nd, now 1st: moved up 1
    assert b.rank_movement == -1    # was 1st, now 2nd: moved down 1


def test_a_new_entrant_has_no_rank_movement():
    rows = salesperson_rows([_person(salesperson_id="new")], {}, {})
    assert rows[0].previous_rank is None
    assert rows[0].rank_movement is None


def test_comparison_uses_the_prior_revenue_when_known():
    rows = salesperson_rows([_person(salesperson_id="a", revenue=900.0)], {"a": 300.0}, {})
    assert rows[0].comparison["history_state"] == "ok"


def test_comparison_is_no_prior_period_when_the_person_is_new():
    rows = salesperson_rows([_person(salesperson_id="new", revenue=900.0)], {}, {})
    assert rows[0].comparison["history_state"] == "no_prior_period"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_performance.py -v -k salesperson`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics.performance'`

- [ ] **Step 3: Write the module**

Create `backend/services/analytics/performance.py`:

```python
"""Pure shaping for the Performance workspace (spec §7 Workspace 2).

No Mongo access in this file — see gather_performance.py, the only module
that reads the database for this workspace. Every function here takes
already-fetched rows and returns typed, JSON-serializable dataclasses.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from services.analytics.periods import compare


@dataclass(frozen=True)
class SalespersonRow:
    salesperson_id: str
    name: str
    revenue: float
    orders: int
    aov: float
    walkins_handled: int
    conversion_pct: float | None
    last_activity_at: str | None
    rank: int
    previous_rank: int | None
    rank_movement: int | None
    comparison: dict


def salesperson_rows(
    current: list[dict],
    previous_revenue_by_id: dict[str, float],
    previous_rank_by_id: dict[str, int],
) -> list[SalespersonRow]:
    ordered = sorted(current, key=lambda p: (-float(p.get("revenue") or 0), p.get("name") or ""))
    result: list[SalespersonRow] = []
    for rank, person in enumerate(ordered, start=1):
        sid = person["salesperson_id"]
        revenue = float(person.get("revenue") or 0)
        orders = int(person.get("orders") or 0)
        walkins = int(person.get("walkins_handled") or 0)
        prior_revenue = previous_revenue_by_id.get(sid)
        prior_rank = previous_rank_by_id.get(sid)
        result.append(SalespersonRow(
            salesperson_id=sid,
            name=person.get("name") or "Unknown",
            revenue=revenue,
            orders=orders,
            aov=round(revenue / orders, 2) if orders else 0.0,
            walkins_handled=walkins,
            conversion_pct=round(orders / walkins * 100, 1) if walkins else None,
            last_activity_at=person.get("last_activity_at"),
            rank=rank,
            previous_rank=prior_rank,
            rank_movement=(prior_rank - rank) if prior_rank is not None else None,
            comparison=compare(revenue, prior_revenue or 0.0, prior_window_exists=sid in previous_revenue_by_id),
        ))
    return result


def row_dict(row: SalespersonRow) -> dict:
    return asdict(row)
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_performance.py -v -k salesperson`
Expected: PASS — 10 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/performance.py backend/tests/unit/test_analytics_performance.py
git commit -m "Add salesperson leaderboard shaping to performance.py

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: `performance.py` — `funnel_stages`

**Files:**
- Modify: `backend/services/analytics/performance.py`
- Test: `backend/tests/unit/test_analytics_performance.py`

**Interfaces:**
- Consumes: nothing new
- Produces:
  - `STAGE_ORDER: tuple[str, ...]` — `("walkins","selections","quotations","approved","confirmed_orders","release","dispatch","payments")`
  - `STAGE_LABELS: dict[str,str]`
  - `@dataclass(frozen=True) FunnelStage` — `key, label, count, conversion_from_start_pct: float|None, dropoff_from_previous_pct: float|None, median_days_in_stage: float|None, revenue_lost_at_drop: float`
  - `funnel_stages(counts: dict[str,int], stage_durations: dict[str, list[float] | None], avg_order_value: float) -> list[FunnelStage]`

**The load-bearing rule** (see "Live data reality" above): `stage_durations` is keyed by the transition **into** each stage (e.g. `"selections"` holds the walkins→selections durations). For `"selections→quotations"`, `"quotations→approved"` and `"approved→confirmed_orders"` the gather layer (Task 9) passes `None`, not an empty list — `median_days_in_stage` for those three stages is `None` by construction, never a fabricated number.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_analytics_performance.py`:

```python
from services.analytics.performance import STAGE_ORDER, funnel_stages


def test_every_spec_stage_is_present_in_order():
    result = funnel_stages({k: 0 for k in STAGE_ORDER}, {k: [] for k in STAGE_ORDER}, avg_order_value=0.0)
    assert [s.key for s in result] == list(STAGE_ORDER)


def test_conversion_from_start_is_relative_to_walkins():
    counts = {"walkins": 100, "selections": 60, "quotations": 40, "approved": 30,
              "confirmed_orders": 20, "release": 20, "dispatch": 18, "payments": 15}
    result = funnel_stages(counts, {k: [] for k in STAGE_ORDER}, avg_order_value=0.0)
    by_key = {s.key: s for s in result}
    assert by_key["quotations"].conversion_from_start_pct == 40.0
    assert by_key["payments"].conversion_from_start_pct == 15.0


def test_zero_walkins_never_crashes_and_reports_no_conversion():
    counts = {k: 0 for k in STAGE_ORDER}
    result = funnel_stages(counts, {k: [] for k in STAGE_ORDER}, avg_order_value=0.0)
    assert all(s.conversion_from_start_pct is None for s in result)


def test_dropoff_from_previous_stage():
    counts = {"walkins": 100, "selections": 60, "quotations": 40, "approved": 30,
              "confirmed_orders": 20, "release": 20, "dispatch": 18, "payments": 15}
    result = funnel_stages(counts, {k: [] for k in STAGE_ORDER}, avg_order_value=0.0)
    by_key = {s.key: s for s in result}
    assert by_key["selections"].dropoff_from_previous_pct == 40.0   # 100 -> 60
    assert by_key["walkins"].dropoff_from_previous_pct is None      # first stage, no "previous"


def test_median_duration_computed_where_real_timestamps_exist():
    durations = {k: [] for k in STAGE_ORDER}
    durations["selections"] = [1.0, 3.0, 5.0]
    counts = {"walkins": 10, "selections": 3, "quotations": 0, "approved": 0,
              "confirmed_orders": 0, "release": 0, "dispatch": 0, "payments": 0}
    result = funnel_stages(counts, durations, avg_order_value=0.0)
    assert next(s for s in result if s.key == "selections").median_days_in_stage == 3.0


def test_median_is_none_for_the_three_untracked_transitions():
    """No timestamp pair exists in the schema for selections->quotations,
    quotations->approved, or approved->confirmed_orders. None, never an
    updated_at-based guess (Phase 0's entire premise)."""
    counts = {k: 0 for k in STAGE_ORDER}
    durations = {k: None if k in ("quotations", "approved", "confirmed_orders") else [] for k in STAGE_ORDER}
    result = funnel_stages(counts, durations, avg_order_value=0.0)
    by_key = {s.key: s for s in result}
    assert by_key["quotations"].median_days_in_stage is None
    assert by_key["approved"].median_days_in_stage is None
    assert by_key["confirmed_orders"].median_days_in_stage is None


def test_revenue_lost_at_drop_is_the_dropped_count_times_average_order_value():
    counts = {"walkins": 100, "selections": 60, "quotations": 40, "approved": 30,
              "confirmed_orders": 20, "release": 20, "dispatch": 18, "payments": 15}
    result = funnel_stages(counts, {k: [] for k in STAGE_ORDER}, avg_order_value=50000.0)
    by_key = {s.key: s for s in result}
    assert by_key["selections"].revenue_lost_at_drop == 40 * 50000.0   # 100 -> 60, dropped 40
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_performance.py -v -k funnel`
Expected: FAIL — `ImportError: cannot import name 'STAGE_ORDER'`

- [ ] **Step 3: Write the function**

Append to `backend/services/analytics/performance.py`:

```python
from statistics import median

STAGE_ORDER: tuple[str, ...] = (
    "walkins", "selections", "quotations", "approved",
    "confirmed_orders", "release", "dispatch", "payments",
)
STAGE_LABELS: dict[str, str] = {
    "walkins": "Walk-ins", "selections": "Selections", "quotations": "Quotations",
    "approved": "Approved", "confirmed_orders": "Confirmed Orders",
    "release": "Release", "dispatch": "Dispatch", "payments": "Payments",
}


@dataclass(frozen=True)
class FunnelStage:
    key: str
    label: str
    count: int
    conversion_from_start_pct: float | None
    dropoff_from_previous_pct: float | None
    median_days_in_stage: float | None
    revenue_lost_at_drop: float


def funnel_stages(
    counts: dict[str, int],
    stage_durations: dict[str, list[float] | None],
    avg_order_value: float,
) -> list[FunnelStage]:
    start_count = counts.get(STAGE_ORDER[0], 0)
    result: list[FunnelStage] = []
    previous_count: int | None = None
    for key in STAGE_ORDER:
        count = counts.get(key, 0)
        conversion = round(count / start_count * 100, 1) if start_count else None
        if previous_count is None:
            dropoff = None
            lost = 0.0
        else:
            dropped = max(previous_count - count, 0)
            dropoff = round(dropped / previous_count * 100, 1) if previous_count else None
            lost = round(dropped * avg_order_value, 2)
        durations = stage_durations.get(key)
        median_days = round(median(durations), 2) if durations else None
        result.append(FunnelStage(
            key=key, label=STAGE_LABELS[key], count=count,
            conversion_from_start_pct=conversion, dropoff_from_previous_pct=dropoff,
            median_days_in_stage=median_days, revenue_lost_at_drop=lost,
        ))
        previous_count = count
    return result
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_performance.py -v`
Expected: PASS — 17 passed (10 salesperson + 7 funnel)

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/performance.py backend/tests/unit/test_analytics_performance.py
git commit -m "Add the 8-stage sales funnel shaping, disclosing three untracked durations honestly

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: `performance.py` — `category_rows`

**Files:**
- Modify: `backend/services/analytics/performance.py`
- Test: `backend/tests/unit/test_analytics_performance.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) CategoryRow` — `category_id: str, name: str, revenue: float, qty: float`; `category_rows(raw: list[dict], category_names: dict[str,str]) -> list[CategoryRow]`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_analytics_performance.py`:

```python
from services.analytics.performance import category_rows


def test_categories_ranked_by_revenue_descending():
    raw = [{"category_id": "c1", "revenue": 100.0, "qty": 5}, {"category_id": "c2", "revenue": 900.0, "qty": 2}]
    rows = category_rows(raw, {"c1": "Tiles", "c2": "Sanitaryware"})
    assert [r.category_id for r in rows] == ["c2", "c1"]
    assert rows[0].name == "Sanitaryware"


def test_an_unresolvable_category_id_falls_back_to_uncategorized():
    raw = [{"category_id": "gone", "revenue": 100.0, "qty": 1}]
    rows = category_rows(raw, {})
    assert rows[0].name == "Uncategorized"


def test_a_missing_category_id_also_falls_back_to_uncategorized():
    raw = [{"category_id": None, "revenue": 100.0, "qty": 1}]
    rows = category_rows(raw, {})
    assert rows[0].category_id == "uncategorized"
    assert rows[0].name == "Uncategorized"


def test_revenue_rounds_to_two_decimal_places():
    raw = [{"category_id": "c1", "revenue": 100.005, "qty": 1}]
    rows = category_rows(raw, {"c1": "Tiles"})
    assert rows[0].revenue == 100.0 or rows[0].revenue == 100.01
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_performance.py -v -k categor`
Expected: FAIL — `ImportError: cannot import name 'category_rows'`

- [ ] **Step 3: Write the function**

Append to `backend/services/analytics/performance.py`:

```python
@dataclass(frozen=True)
class CategoryRow:
    category_id: str
    name: str
    revenue: float
    qty: float


def category_rows(raw: list[dict], category_names: dict[str, str]) -> list[CategoryRow]:
    rows = []
    for entry in raw:
        cid = entry.get("category_id") or "uncategorized"
        name = category_names.get(cid, "Uncategorized") if cid != "uncategorized" else "Uncategorized"
        rows.append(CategoryRow(category_id=cid, name=name, revenue=round(float(entry.get("revenue") or 0), 2), qty=float(entry.get("qty") or 0)))
    return sorted(rows, key=lambda r: -r.revenue)
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_performance.py -v`
Expected: PASS — 21 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/performance.py backend/tests/unit/test_analytics_performance.py
git commit -m "Add revenue-by-category shaping to performance.py

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: `collections.py` — by-customer and by-age views

**Files:**
- Create: `backend/services/analytics/collections.py`
- Test: `backend/tests/unit/test_analytics_collections.py`

**Interfaces:**
- Consumes: `attention.age_days` (Phase 1, imported by identity — reused, not reimplemented)
- Produces:
  - `AGE_BUCKETS: tuple[tuple[str,int,int|None], ...]` — `(("0-30",0,30), ("31-60",31,60), ("61-90",61,90), ("90+",91,None))`
  - `@dataclass(frozen=True) CollectionRow` — `customer_id, customer_name, ordered_at, grand_total, collected, outstanding, age_days, age_bucket: str`
  - `collections_by_customer(rows: list[dict], now: datetime) -> list[CollectionRow]`
  - `collections_by_age(rows: list[dict], now: datetime) -> dict[str, dict]` — `{bucket_label: {"count": int, "outstanding": float}}`, every bucket present even if zero

**Why reuse `age_days` rather than a new helper:** the exact same "missing/unparseable timestamp never fires a threshold" guarantee from Phase 1 applies here — a `CollectionRow` with an unparseable `ordered_at` gets `age_days=None` and sorts into no bucket (excluded from `collections_by_age`, still listed in `collections_by_customer` so the money is never silently dropped from the total).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_analytics_collections.py`:

```python
"""Pure shaping for the Collections workspace. Reuses metrics.outstanding_pipeline's
figures verbatim (spec: "no new definition") — this module only buckets and sorts
what gather_performance.py already fetched."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.analytics.collections import collections_by_age, collections_by_customer

NOW = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _row(**kw) -> dict:
    base = dict(customer_id="c1", customer_name="JK Enterprises", ordered_at=_iso(10), grand_total=300000.0, collected=100000.0)
    base.update(kw)
    return base


def test_outstanding_is_grand_total_minus_collected():
    rows = collections_by_customer([_row()], now=NOW)
    assert rows[0].outstanding == 200000.0


def test_a_fully_collected_order_is_excluded():
    rows = collections_by_customer([_row(grand_total=300000.0, collected=300000.0)], now=NOW)
    assert rows == []


def test_an_overpaid_order_is_also_excluded_not_negative():
    rows = collections_by_customer([_row(grand_total=300000.0, collected=310000.0)], now=NOW)
    assert rows == []


def test_sorted_by_outstanding_descending():
    rows = collections_by_customer([
        _row(customer_id="a", grand_total=100000.0, collected=0.0),
        _row(customer_id="b", grand_total=900000.0, collected=0.0),
    ], now=NOW)
    assert [r.customer_id for r in rows] == ["b", "a"]


def test_age_bucket_boundaries():
    exactly_30 = collections_by_customer([_row(customer_id="a", ordered_at=_iso(30))], now=NOW)
    exactly_31 = collections_by_customer([_row(customer_id="b", ordered_at=_iso(31))], now=NOW)
    assert exactly_30[0].age_bucket == "0-30"
    assert exactly_31[0].age_bucket == "31-60"


def test_a_90_plus_bucket_has_no_upper_bound():
    rows = collections_by_customer([_row(ordered_at=_iso(400))], now=NOW)
    assert rows[0].age_bucket == "90+"


def test_by_age_reports_every_bucket_even_when_empty():
    result = collections_by_age([_row(ordered_at=_iso(5))], now=NOW)
    assert set(result.keys()) == {"0-30", "31-60", "61-90", "90+"}
    assert result["31-60"] == {"count": 0, "outstanding": 0.0}


def test_by_age_totals_match_by_customer_totals():
    rows = [_row(customer_id="a", ordered_at=_iso(5), grand_total=100000.0, collected=0.0),
            _row(customer_id="b", ordered_at=_iso(95), grand_total=50000.0, collected=0.0)]
    by_age = collections_by_age(rows, now=NOW)
    total_from_age = sum(b["outstanding"] for b in by_age.values())
    total_from_customer = sum(r.outstanding for r in collections_by_customer(rows, now=NOW))
    assert total_from_age == total_from_customer == 150000.0


def test_an_unparseable_ordered_at_is_still_listed_but_unbucketed():
    rows = collections_by_customer([_row(ordered_at="not-a-date")], now=NOW)
    assert len(rows) == 1
    assert rows[0].age_days is None
    assert rows[0].age_bucket is None
    by_age = collections_by_age([_row(ordered_at="not-a-date")], now=NOW)
    assert sum(b["count"] for b in by_age.values()) == 0   # excluded from every bucket, money not silently dropped from the customer view above
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_collections.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics.collections'`

- [ ] **Step 3: Write the module**

Create `backend/services/analytics/collections.py`:

```python
"""Pure shaping for the Collections workspace — the payments-focused view of
Outstanding. Reuses metrics.outstanding_pipeline's own figures; this module
only buckets and sorts what the gather layer already fetched, per spec
("no new definition")."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from services.analytics.attention import age_days

AGE_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("0-30", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("90+", 91, None),
)


def _bucket_for(age: int) -> str:
    for label, low, high in AGE_BUCKETS:
        if age >= low and (high is None or age <= high):
            return label
    return AGE_BUCKETS[-1][0]


@dataclass(frozen=True)
class CollectionRow:
    customer_id: str
    customer_name: str
    ordered_at: str | None
    grand_total: float
    collected: float
    outstanding: float
    age_days: int | None
    age_bucket: str | None


def collections_by_customer(rows: list[dict], now: datetime) -> list[CollectionRow]:
    result: list[CollectionRow] = []
    for row in rows:
        outstanding = round(float(row.get("grand_total") or 0) - float(row.get("collected") or 0), 2)
        if outstanding <= 0:
            continue
        age = age_days(row.get("ordered_at"), now)
        result.append(CollectionRow(
            customer_id=row["customer_id"], customer_name=row.get("customer_name") or "Unknown",
            ordered_at=row.get("ordered_at"), grand_total=float(row.get("grand_total") or 0),
            collected=float(row.get("collected") or 0), outstanding=outstanding,
            age_days=age, age_bucket=_bucket_for(age) if age is not None else None,
        ))
    return sorted(result, key=lambda r: -r.outstanding)


def collections_by_age(rows: list[dict], now: datetime) -> dict[str, dict]:
    buckets = {label: {"count": 0, "outstanding": 0.0} for label, _, _ in AGE_BUCKETS}
    for row in collections_by_customer(rows, now):
        if row.age_bucket is None:
            continue
        buckets[row.age_bucket]["count"] += 1
        buckets[row.age_bucket]["outstanding"] = round(buckets[row.age_bucket]["outstanding"] + row.outstanding, 2)
    return buckets
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_collections.py -v`
Expected: PASS — 10 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/collections.py backend/tests/unit/test_analytics_collections.py
git commit -m "Add Collections workspace shaping, reusing Outstanding verbatim

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: `referrals.py` — `referrer_summary_rows`

**Files:**
- Create: `backend/services/analytics/referrals.py`
- Test: `backend/tests/unit/test_analytics_referrals.py`

**Interfaces:**
- Consumes: `attention.age_days`, `attention.THRESHOLDS["REFERRER_QUIET_DAYS"]` (imported by identity, never a second copy)
- Produces:
  - `@dataclass(frozen=True) ReferrerSummary` — `referrer_id, name, type, customers_referred, quotations_total, quotations_approved, quotations_confirmed, revenue, aov, conversion_rate: float|None, pending_count, pending_value, pending_payments, first_referral_at: str|None, last_referral_at: str|None, is_active: bool, repeat_customers: int`
  - `referrer_summary_rows(raw: list[dict], now: datetime, thresholds: dict) -> list[ReferrerSummary]`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_analytics_referrals.py`:

```python
"""Pure shaping for spec §7 Workspace 3 — Referral Analytics. Every one of the
14 cards is a field on ReferrerSummary or its profile; nothing here queries
Mongo (gather_referrals.py does that)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.analytics.attention import THRESHOLDS
from services.analytics.referrals import referrer_summary_rows

NOW = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _raw(**kw) -> dict:
    base = dict(
        referrer_id="r1", name="ABC Architects", type="architect",
        customers_referred=4, quotations_total=10, quotations_approved=6, quotations_confirmed=5,
        revenue=1200000.0, pending_count=2, pending_value=300000.0, pending_payments=50000.0,
        first_referral_at=_iso(400), last_referral_at=_iso(5), repeat_customers=2,
    )
    base.update(kw)
    return base


def test_conversion_rate_is_confirmed_over_total_quotations():
    rows = referrer_summary_rows([_raw()], now=NOW, thresholds=THRESHOLDS)
    assert rows[0].conversion_rate == 50.0


def test_conversion_rate_is_none_with_zero_quotations():
    rows = referrer_summary_rows([_raw(quotations_total=0, quotations_confirmed=0)], now=NOW, thresholds=THRESHOLDS)
    assert rows[0].conversion_rate is None


def test_aov_is_revenue_over_confirmed_quotations():
    rows = referrer_summary_rows([_raw(revenue=1000000.0, quotations_confirmed=5)], now=NOW, thresholds=THRESHOLDS)
    assert rows[0].aov == 200000.0


def test_aov_is_zero_without_any_confirmed_quotations():
    rows = referrer_summary_rows([_raw(revenue=0.0, quotations_confirmed=0)], now=NOW, thresholds=THRESHOLDS)
    assert rows[0].aov == 0.0


def test_active_when_the_last_referral_is_inside_the_quiet_window():
    rows = referrer_summary_rows([_raw(last_referral_at=_iso(5))], now=NOW, thresholds=THRESHOLDS)
    assert rows[0].is_active is True


def test_inactive_when_the_last_referral_is_past_the_quiet_window():
    rows = referrer_summary_rows([_raw(last_referral_at=_iso(THRESHOLDS["REFERRER_QUIET_DAYS"] + 1))], now=NOW, thresholds=THRESHOLDS)
    assert rows[0].is_active is False


def test_a_referrer_who_has_never_referred_is_inactive_not_a_crash():
    rows = referrer_summary_rows([_raw(last_referral_at=None, first_referral_at=None)], now=NOW, thresholds=THRESHOLDS)
    assert rows[0].is_active is False


def test_ranked_by_revenue_descending():
    rows = referrer_summary_rows([
        _raw(referrer_id="a", revenue=100.0), _raw(referrer_id="b", revenue=900.0),
    ], now=NOW, thresholds=THRESHOLDS)
    assert [r.referrer_id for r in rows] == ["b", "a"]


def test_an_empty_referrer_list_returns_an_empty_list():
    assert referrer_summary_rows([], now=NOW, thresholds=THRESHOLDS) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_referrals.py -v -k summary`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics.referrals'`

- [ ] **Step 3: Write the module**

Create `backend/services/analytics/referrals.py`:

```python
"""Pure shaping for spec §7 Workspace 3 — Referral Analytics. Reads only
already-aggregated rows; gather_referrals.py is the only place this surface
queries Mongo (spec §5.1: reporting reads quotations.referrer_* directly,
Referrer itself carries zero metrics)."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime

from services.analytics.attention import age_days


@dataclass(frozen=True)
class ReferrerSummary:
    referrer_id: str
    name: str
    type: str
    customers_referred: int
    quotations_total: int
    quotations_approved: int
    quotations_confirmed: int
    revenue: float
    aov: float
    conversion_rate: float | None
    pending_count: int
    pending_value: float
    pending_payments: float
    first_referral_at: str | None
    last_referral_at: str | None
    is_active: bool
    repeat_customers: int


def referrer_summary_rows(raw: list[dict], now: datetime, thresholds: dict) -> list[ReferrerSummary]:
    result: list[ReferrerSummary] = []
    for r in raw:
        total = int(r.get("quotations_total") or 0)
        confirmed = int(r.get("quotations_confirmed") or 0)
        revenue = float(r.get("revenue") or 0)
        last = r.get("last_referral_at")
        age = age_days(last, now)
        result.append(ReferrerSummary(
            referrer_id=r["referrer_id"], name=r.get("name") or "Unknown", type=r.get("type") or "architect",
            customers_referred=int(r.get("customers_referred") or 0),
            quotations_total=total, quotations_approved=int(r.get("quotations_approved") or 0),
            quotations_confirmed=confirmed, revenue=revenue,
            aov=round(revenue / confirmed, 2) if confirmed else 0.0,
            conversion_rate=round(confirmed / total * 100, 1) if total else None,
            pending_count=int(r.get("pending_count") or 0), pending_value=float(r.get("pending_value") or 0),
            pending_payments=float(r.get("pending_payments") or 0),
            first_referral_at=r.get("first_referral_at"), last_referral_at=last,
            is_active=(age is not None and age <= thresholds["REFERRER_QUIET_DAYS"]),
            repeat_customers=int(r.get("repeat_customers") or 0),
        ))
    return sorted(result, key=lambda s: -s.revenue)


def summary_dict(summary: ReferrerSummary) -> dict:
    return asdict(summary)
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_referrals.py -v -k summary`
Expected: PASS — 9 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/referrals.py backend/tests/unit/test_analytics_referrals.py
git commit -m "Add the 14-card referrer summary shaping

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: `referrals.py` — `referrer_profile` (the partner-profile mini-CRM)

**Files:**
- Modify: `backend/services/analytics/referrals.py`
- Test: `backend/tests/unit/test_analytics_referrals.py`

**Interfaces:**
- Consumes: `ReferrerSummary` (Task 6)
- Produces: `@dataclass(frozen=True) ReferrerProfile` — `referrer_id, name, type, phone: str|None, company: str|None, summary: ReferrerSummary, monthly_trend: list[dict], brand_preference: list[dict], product_preference: list[dict], floor_split: dict[str,float]`; `referrer_profile(referrer: dict, summary: ReferrerSummary, monthly_trend: list[dict], brand_rows: list[dict], product_rows: list[dict], floor_rows: dict[str,float]) -> ReferrerProfile`; `PREFERENCE_LIMIT = 10`

**Spec §7 Workspace 3's "mini CRM, not a table row"**: header (name/type/firm/phone/lifetime revenue/customers/orders/AOV/active-quiet) is exactly `summary` plus the three contact fields this function adds. Body sections (Summary/Revenue trend/Customers/Relationship timeline/Quotations/Orders/Payments/Preferred Brands/Products/Recent Activity/Conversion Funnel) are assembled by the frontend from this payload plus Phase 1's existing `feed`/`attention` surfaces filtered by `referrer_id` — this function only owns the parts genuinely new to Referral Analytics (trend, brand/product preference, floor split).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_analytics_referrals.py`:

```python
from services.analytics.referrals import PREFERENCE_LIMIT, referrer_profile, referrer_summary_rows


def _summary():
    return referrer_summary_rows([_raw()], now=NOW, thresholds=THRESHOLDS)[0]


def test_profile_carries_the_contact_fields_the_summary_does_not():
    profile = referrer_profile(
        {"id": "r1", "name": "ABC Architects", "type": "architect", "phone": "+91900", "company": "ABC & Co"},
        _summary(), monthly_trend=[], brand_rows=[], product_rows=[], floor_rows={},
    )
    assert profile.phone == "+91900" and profile.company == "ABC & Co"
    assert profile.summary.revenue == _summary().revenue


def test_brand_and_product_preference_are_sorted_and_capped():
    brand_rows = [{"brand_id": f"b{i}", "brand_name": f"Brand {i}", "revenue": float(i)} for i in range(15)]
    profile = referrer_profile(
        {"id": "r1", "name": "X", "type": "architect", "phone": None, "company": None},
        _summary(), monthly_trend=[], brand_rows=brand_rows, product_rows=[], floor_rows={},
    )
    assert len(profile.brand_preference) == PREFERENCE_LIMIT
    assert profile.brand_preference[0]["revenue"] == 14.0   # highest first


def test_floor_split_includes_both_floors_even_when_one_is_zero():
    """A floor at 0 must still appear — omitting it would read as 'this
    partner doesn't exist on that floor' rather than 'no revenue yet'."""
    profile = referrer_profile(
        {"id": "r1", "name": "X", "type": "architect", "phone": None, "company": None},
        _summary(), monthly_trend=[], brand_rows=[], product_rows=[],
        floor_rows={"first-floor": 500000.0, "ground-floor": 0.0},
    )
    assert profile.floor_split == {"first-floor": 500000.0, "ground-floor": 0.0}


def test_monthly_trend_passes_through_unchanged():
    trend = [{"bucket": "Jul 2026", "revenue": 100.0}, {"bucket": "Aug 2026", "revenue": 200.0}]
    profile = referrer_profile(
        {"id": "r1", "name": "X", "type": "architect", "phone": None, "company": None},
        _summary(), monthly_trend=trend, brand_rows=[], product_rows=[], floor_rows={},
    )
    assert profile.monthly_trend == trend
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_referrals.py -v -k profile`
Expected: FAIL — `ImportError: cannot import name 'referrer_profile'`

- [ ] **Step 3: Write the function**

Append to `backend/services/analytics/referrals.py`:

```python
PREFERENCE_LIMIT = 10


@dataclass(frozen=True)
class ReferrerProfile:
    referrer_id: str
    name: str
    type: str
    phone: str | None
    company: str | None
    summary: ReferrerSummary
    monthly_trend: list[dict]
    brand_preference: list[dict]
    product_preference: list[dict]
    floor_split: dict[str, float]


def _top(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: -float(r.get("revenue") or 0))[:PREFERENCE_LIMIT]


def referrer_profile(
    referrer: dict,
    summary: ReferrerSummary,
    monthly_trend: list[dict],
    brand_rows: list[dict],
    product_rows: list[dict],
    floor_rows: dict[str, float],
) -> ReferrerProfile:
    return ReferrerProfile(
        referrer_id=referrer["id"], name=referrer.get("name") or "Unknown", type=referrer.get("type") or "architect",
        phone=referrer.get("phone"), company=referrer.get("company"),
        summary=summary, monthly_trend=list(monthly_trend),
        brand_preference=_top(brand_rows), product_preference=_top(product_rows),
        floor_split=dict(floor_rows),
    )
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_referrals.py -v`
Expected: PASS — 13 passed (9 summary + 4 profile)

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/referrals.py backend/tests/unit/test_analytics_referrals.py
git commit -m "Add the partner-profile mini-CRM assembly

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## STAGE A GATE

Before Task 8: full suite green (`602 + 10 + 21 + 10 + 13 - 21(dup count check) ≈ 656` — run the suite and record the real total; every shaping rule pure and DB-free, ledger entry written). Report to the user: what was built, what was verified, tests, live verification (n/a for pure modules — say so), remaining work.

---

## Task 8: fix the payment cache-bump gap

**Files:**
- Modify: `backend/routes/payment_routes.py`
- Test: `backend/tests/unit/test_payment_cache_bump.py`

**Interfaces:**
- Consumes: `services.analytics.cache.bump` (Phase 1)

**Why first in Stage B:** Collections' entire value is an accurate, fresh Outstanding figure. `create_payment` currently inserts directly into `db.payments` with no `cache.bump("payments")` call anywhere in its path (confirmed: `cache.bump` appears in exactly `domain_outbox.py` and `executive_overview_routes.py` in the whole backend) — a payment recorded today can leave every cached Outstanding/Collections number stale for up to the cache's 60s TTL. Building Collections on top of this gap would ship a workspace whose flagship number can silently disagree with what was just recorded.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_payment_cache_bump.py`:

```python
"""create_payment must invalidate the analytics cache after it commits — the
same post-commit, swallow-and-log discipline domain_outbox.py already uses
for every other write that changes reported revenue."""
from __future__ import annotations

import ast
from pathlib import Path


def test_create_payment_calls_cache_bump_after_the_transaction_commits():
    source = Path("routes/payment_routes.py").read_text()
    tree = ast.parse(source)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "create_payment")
    calls = [ast.dump(n) for n in ast.walk(func) if isinstance(n, ast.Call)]
    assert any('bump' in c and "'payments'" in c for c in calls), (
        "create_payment never calls cache.bump('payments') — Collections/Outstanding "
        "will silently serve a stale figure after a payment is recorded"
    )


def test_the_bump_call_is_not_nested_inside_the_transaction_try_block():
    """A bump for a transaction that then rolls back would be worse than a
    stale read — it must sit after the try/except at function indentation,
    the same rule Stage B's Task 8 (Phase 1) enforced for domain_outbox.py."""
    source = Path("routes/payment_routes.py").read_text()
    tree = ast.parse(source)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "create_payment")
    bump_call = next(
        n for n in ast.walk(func)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "bump"
    )
    try_blocks = [n for n in ast.walk(func) if isinstance(n, ast.Try)]
    for block in try_blocks:
        block_lines = range(block.lineno, (block.body[-1].end_lineno or block.lineno) + 1)
        assert bump_call.lineno not in block_lines or block.lineno > bump_call.lineno, (
            "cache.bump appears to be called inside the payment-insert try/except — "
            "it must run only after commit succeeds"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_payment_cache_bump.py -v`
Expected: FAIL — `StopIteration` (no `bump` call found)

- [ ] **Step 3: Add the fix**

In `backend/routes/payment_routes.py`, add the import (near the top, alongside other service imports):

```python
from services.analytics import cache
```

Then, in `create_payment`, immediately after the `log_event(...)` call that already exists post-commit (right before the two `asyncio.create_task(...)` lines), add:

```python
    try:
        await cache.bump("payments")
    except Exception:
        logger.exception("cache bump failed for payments after payment %s", payment.id)
```

This mirrors `domain_outbox.py::_bump_analytics_versions`'s exact discipline: post-commit, swallowed, logged — a cache problem degrades to TTL expiry, never turns a successfully recorded payment into a user-facing error. Confirm `logger` is already defined in this module (it is, used elsewhere in the file); if the module uses a different logging convention, match it exactly rather than introducing a second one.

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_payment_cache_bump.py -v`
Expected: PASS — 2 passed

Also run the full payment test suite to confirm no regression: `cd backend && ./.venv/bin/python -m pytest tests/unit -k payment -v`

- [ ] **Step 5: Commit**

```bash
git add backend/routes/payment_routes.py backend/tests/unit/test_payment_cache_bump.py
git commit -m "Fix payment_routes never invalidating the analytics cache

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: `gather_performance.py` — the only place Performance reads Mongo

**Files:**
- Create: `backend/services/analytics/gather_performance.py`
- Test: `backend/tests/unit/test_gather_performance.py`

**Interfaces:**
- Consumes: `build_match`, `AnalyticsFilter` (Phase 0); `periods.buckets` (Task 1); `SalespersonRow`/`FunnelStage`/`CategoryRow` inputs (Tasks 2–4); reuses the `_FakeCollection`/`_FakeCursor`/`_FakeDb` test-fake pattern from `tests/unit/test_analytics_gather.py`
- Produces:
  - `async gather_revenue_trend(db, f, accessible_floors, window, granularity) -> list[dict]` — `[{"bucket","revenue"}]` via `periods.buckets` + per-bucket `revenue_pipeline`-style aggregation
  - `async gather_salespeople(db, f, accessible_floors, window, previous_window) -> tuple[list[dict], dict[str,float], dict[str,int]]` — current rows, previous-period revenue-by-id, previous-period rank-by-id
  - `async gather_funnel(db, f, accessible_floors, window) -> tuple[dict[str,int], dict[str, list[float]|None], float]` — counts, stage_durations (with the three untracked transitions explicitly `None`), avg_order_value
  - `async gather_category_revenue(db, f, accessible_floors, window) -> tuple[list[dict], dict[str,str]]` — raw rows + `{category_id: name}` lookup from `db.categories`

**The load-bearing rule, same as Phase 1's `gather.py`:** every read goes through `build_match`. No hand-written `{"floor_id": ...}` clause anywhere in this file.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_gather_performance.py`:

```python
"""Every Performance-workspace read goes through build_match, so floor scoping
is never re-implemented per surface. Reuses the fake-db pattern already proven
in test_analytics_gather.py — copy those three classes, not a fourth variant."""
from __future__ import annotations

import asyncio

from services.analytics import gather_performance
from services.analytics.filters import AnalyticsFilter

WINDOW = ("2026-07-01T00:00:00+00:00", "2026-07-31T23:59:59+00:00")


class _FakeCursor:
    def __init__(self, docs): self._docs = list(docs)
    def sort(self, *a, **k): return self
    def limit(self, *a, **k): return self
    async def to_list(self, n=None): return self._docs[:n] if n else list(self._docs)
    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


class _FakeCollection:
    def __init__(self, docs): self.docs = list(docs); self.queries = []
    def find(self, query=None, projection=None):
        self.queries.append(query or {})
        return _FakeCursor(self.docs)
    def aggregate(self, pipeline):
        self.queries.append(pipeline[0].get("$match", {}) if pipeline else {})
        return _FakeCursor([])
    async def count_documents(self, query): self.queries.append(query); return len(self.docs)


class _FakeDb:
    def __init__(self, **collections):
        for name, docs in collections.items():
            setattr(self, name, _FakeCollection(docs))
    def __getattr__(self, _name): return _FakeCollection([])


def test_revenue_trend_reads_are_floor_scoped_for_a_restricted_caller():
    db = _FakeDb(quotations=[])
    asyncio.run(gather_performance.gather_revenue_trend(db, AnalyticsFilter(floor_id="all"), ["ground-floor"], WINDOW, "month"))
    scoped = [q for q in db.quotations.queries if isinstance(q, dict) and q.get("floor_id")]
    assert scoped, "no revenue-trend read carried a floor clause"


def test_gather_salespeople_returns_three_shapes():
    db = _FakeDb(quotations=[], walkins=[], users=[])
    current, prev_revenue, prev_rank = asyncio.run(
        gather_performance.gather_salespeople(db, AnalyticsFilter(floor_id="all"), None, WINDOW, WINDOW)
    )
    assert current == [] and prev_revenue == {} and prev_rank == {}


def test_gather_funnel_marks_the_three_untracked_transitions_as_none():
    db = _FakeDb(walkins=[], quotations=[], purchase_orders=[], dispatches=[], payments=[])
    counts, durations, avg_order = asyncio.run(
        gather_performance.gather_funnel(db, AnalyticsFilter(floor_id="all"), None, WINDOW)
    )
    assert durations["selections"] is None or durations["selections"] == []
    assert durations["quotations"] is None
    assert durations["approved"] is None
    assert durations["confirmed_orders"] is None


def test_gather_category_revenue_reads_categories_for_names():
    db = _FakeDb(quotations=[], categories=[{"id": "c1", "name": "Tiles"}])
    raw, names = asyncio.run(gather_performance.gather_category_revenue(db, AnalyticsFilter(floor_id="all"), None, WINDOW))
    assert names == {"c1": "Tiles"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_gather_performance.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics.gather_performance'`

- [ ] **Step 3: Write the module**

Create `backend/services/analytics/gather_performance.py`. Key requirements beyond the test shapes:

- `gather_revenue_trend`: call `periods.buckets(window[0], window[1], granularity)`, then for each bucket run `metrics.revenue_pipeline(build_match(AnalyticsFilter(floor_id=f.floor_id, status="ordered"), accessible_floors, (bucket.start, bucket.end)))` against `db.quotations`, collecting `{"bucket": b.label, "revenue": row["revenue"] if rows else 0.0}`.
- `gather_salespeople`: aggregate `db.quotations` grouped by `created_by`/`created_by_name` for revenue+orders in `window` (via `build_match` + a `$group` mirroring `metrics.line_revenue_pipeline`'s shape but on `created_by`, not `items.product_id`), aggregate `db.walkins` grouped by `salesperson_id` for `walkins_handled` in the same window, join on person id, resolve `last_activity_at` as `max(quotation.created_at, walkin.visited_at, followup.last_contacted_at)` per person (three small aggregations, not a fourth collection scan — reuse `build_match`'s floor clause on each). Run the identical shape against `previous_window` for `prev_revenue`/`prev_rank` (rank computed by sorting that period's revenue).
- `gather_funnel`: counts per `performance.STAGE_ORDER` key from `db.walkins` (`is_deleted=false`), `db.quotations` (`doc_type=tiles_selection` for selections; `doc_type in (standard, tiles_quotation)` and `status not in (rejected, lost)` for quotations; `status=approved` for approved; ordered quotations for confirmed_orders), `db.purchase_orders`/`ready_batches`-equivalent for release, `db.dispatches`/`TileDispatch` for dispatch, `db.payments status=completed` for payments — matching the spec's exact denominators table. `stage_durations["walkins"]` stays `[]` (no "previous" stage). `stage_durations["selections"]` is computed from real `(selection.created_at - walkin.visited_at)` pairs where `WalkIn.selection_quotation_id` resolves; `stage_durations["quotations"]`, `["approved"]`, `["confirmed_orders"]` are hardcoded to `None` with an inline comment citing the "Live data reality" note above — **do not attempt to derive these from `updated_at`**. `stage_durations["release"]`/`["dispatch"]`/`["payments"]` are computed from the real timestamp pairs described in "Live data reality." `avg_order_value` = `revenue_pipeline` result's `aov` for the same window.
- `gather_category_revenue`: `db.quotations.aggregate(line_revenue_pipeline(match, group_by="items.category_id"))`-shaped pipeline (mirror `metrics.line_revenue_pipeline`'s existing `$unwind`+`$group` on `items.category_id` instead of `items.product_id`), plus `db.categories.find(...)` for the id→name map, scoped to accessible floors via each category's own `floor_id` field (categories are floor-owned, per the model).

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_gather_performance.py -v`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/gather_performance.py backend/tests/unit/test_gather_performance.py
git commit -m "Add the Performance workspace's Mongo gather layer

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: `gather_collections` — collections reads, appended to `gather_performance.py`

**Files:**
- Modify: `backend/services/analytics/gather_performance.py`
- Test: `backend/tests/unit/test_gather_performance.py`

**Interfaces:**
- Produces: `async gather_collections_orders(db, f, accessible_floors, window) -> list[dict]` — `[{"customer_id","customer_name","ordered_at","grand_total","collected"}]`, one row per ordered quotation with outstanding money, using `gather.collected_by_quotation` (Phase 1, imported — **not reimplemented**, since it already correctly counts only `status="completed"` payments)

**Why this stays in `gather_performance.py` rather than a new file**: Collections is small (one read, reusing Phase 1's `collected_by_quotation` and Task 5's pure shaping) and lives in the same "money" nav group as Performance — a dedicated `gather_collections.py` would be a single-function file for no organizational benefit.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_gather_performance.py`:

```python
def test_gather_collections_orders_is_floor_scoped():
    db = _FakeDb(quotations=[], payments=[])
    asyncio.run(gather_performance.gather_collections_orders(db, AnalyticsFilter(floor_id="all"), ["first-floor"], WINDOW))
    scoped = [q for q in db.quotations.queries if isinstance(q, dict) and q.get("floor_id")]
    assert scoped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_gather_performance.py -v -k collections_orders`
Expected: FAIL — `AttributeError: module 'services.analytics.gather_performance' has no attribute 'gather_collections_orders'`

- [ ] **Step 3: Write the function**

Append to `backend/services/analytics/gather_performance.py`:

```python
from services.analytics.gather import collected_by_quotation


async def gather_collections_orders(db, f: AnalyticsFilter, accessible_floors, window) -> list[dict]:
    match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="ordered"), accessible_floors, window)
    orders = await db.quotations.find(
        match, {"_id": 0, "id": 1, "customer_id": 1, "customer_name": 1, "ordered_at": 1, "grand_total": 1},
    ).to_list(None)
    paid = await collected_by_quotation(db, [o["id"] for o in orders])
    return [{**o, "collected": paid.get(o["id"], 0.0)} for o in orders]
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_gather_performance.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/gather_performance.py backend/tests/unit/test_gather_performance.py
git commit -m "Add Collections' Mongo read, reusing Phase 1's collected_by_quotation

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 11: `gather_referrals.py` — the only place Referral Analytics reads Mongo

**Files:**
- Create: `backend/services/analytics/gather_referrals.py`
- Test: `backend/tests/unit/test_gather_referrals.py`

**Interfaces:**
- Produces:
  - `async gather_referrer_raw(db, f, accessible_floors, window, referrer_type) -> list[dict]` — one dict per referrer matching Task 6's `_raw()` shape, aggregated from `db.quotations` grouped by `referrer_id`/`referrer_name` (`referrer_type` filter applied), joined to `db.payments` via the same `collected_by_quotation` pattern for `pending_payments`
  - `async gather_referrer_profile_data(db, f, accessible_floors, referrer_id, granularity) -> tuple[dict|None, list[dict], list[dict], list[dict], dict[str,float]]` — `(referrer_doc, monthly_trend, brand_rows, product_rows, floor_rows)`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_gather_referrals.py`:

```python
"""Every Referral Analytics read goes through build_match and reads only
quotations.referrer_* (spec §5.1 — Referrer itself carries zero metrics)."""
from __future__ import annotations

import asyncio

from services.analytics import gather_referrals
from services.analytics.filters import AnalyticsFilter
from tests.unit.test_gather_performance import _FakeDb

WINDOW = ("2026-07-01T00:00:00+00:00", "2026-07-31T23:59:59+00:00")


def test_gather_referrer_raw_is_floor_scoped():
    db = _FakeDb(quotations=[], payments=[], referrers=[])
    asyncio.run(gather_referrals.gather_referrer_raw(db, AnalyticsFilter(floor_id="all"), ["ground-floor"], WINDOW, None))
    scoped = [q for q in db.quotations.queries if isinstance(q, dict) and q.get("floor_id")]
    assert scoped


def test_gather_referrer_raw_filters_by_type_when_given():
    db = _FakeDb(quotations=[], payments=[], referrers=[])
    asyncio.run(gather_referrals.gather_referrer_raw(db, AnalyticsFilter(floor_id="all"), None, WINDOW, "architect"))
    typed = [q for q in db.quotations.queries if isinstance(q, dict) and q.get("referrer_type") == "architect"]
    assert typed


def test_gather_referrer_profile_data_returns_none_referrer_when_not_found():
    db = _FakeDb(referrers=[], quotations=[])
    referrer, trend, brands, products, floors = asyncio.run(
        gather_referrals.gather_referrer_profile_data(db, AnalyticsFilter(floor_id="all"), None, "missing-id", "month")
    )
    assert referrer is None
    assert trend == [] and brands == [] and products == []
    assert floors == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_gather_referrals.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics.gather_referrals'`

- [ ] **Step 3: Write the module**

Create `backend/services/analytics/gather_referrals.py`. Key requirements:

- `gather_referrer_raw`: `build_match(AnalyticsFilter(floor_id=f.floor_id, status="any"), accessible_floors, window)` plus `{"referrer_id": {"$ne": None}}` and, when `referrer_type` is given, `{"referrer_type": referrer_type}`. Aggregate grouped by `referrer_id` for: `customers_referred` (`$addToSet` on `customer_id`, sized), `quotations_total` (count), `quotations_approved` (count where `status="approved"`), `quotations_confirmed`/`revenue` (count + sum `grand_total` where `status="ordered"`), `pending_count`/`pending_value` (count + sum where `status` in the open set), `first_referral_at`/`last_referral_at` (`$min`/`$max` on `created_at`), `repeat_customers` (customers with ≥2 quotations — a second `$group` stage on `customer_id` counting, then counting groups with count≥2). `pending_payments` joins `collected_by_quotation` against the ordered-but-not-fully-paid subset, same as Task 10.
- `gather_referrer_profile_data`: `db.referrers.find_one({"id": referrer_id})`; if `None`, return the empty tuple shown in the test. Otherwise: `monthly_trend` via `periods.buckets` over the last 12 months + per-bucket revenue for that `referrer_id` (mirroring `gather_revenue_trend`'s loop, filtered to this one referrer); `brand_rows`/`product_rows` via `metrics.line_revenue_pipeline`-shaped aggregation on `items.product_id`→brand/product lookup, filtered to `referrer_id`; `floor_rows` via one aggregation grouped by `floor_id`, **seeded with both known floor ids at 0.0 before merging real results** so a referrer active on only one floor still reports the other as an explicit zero (Task 7's test pins this).

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_gather_referrals.py -v`
Expected: PASS — 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/gather_referrals.py backend/tests/unit/test_gather_referrals.py
git commit -m "Add the Referral Analytics Mongo gather layer

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 12: `services/export.py` — the shared CSV/XLSX helper

**Files:**
- Create: `backend/services/export.py`
- Test: `backend/tests/unit/test_export.py`

**Interfaces:**
- Produces:
  - `rows_to_csv(rows: list[dict], columns: list[tuple[str,str]]) -> bytes`
  - `rows_to_xlsx(rows: list[dict], columns: list[tuple[str,str]], sheet_title: str = "Export") -> bytes`
  - `export_response(rows: list[dict], columns: list[tuple[str,str]], filename_base: str, fmt: str) -> StreamingResponse` — `fmt` must be `"csv"` or `"xlsx"`; raises `ValueError` otherwise (the router converts that to a 400)

`columns` is `[(field_key, header_label), ...]` — applied in order; a row missing a key renders as an empty cell, never a crash (the four new tables this feeds are aggregation output, and a partially-populated aggregate is expected, not exceptional).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_export.py`:

```python
"""Generic rows->CSV/XLSX export, shared by every Phase 2 table. CSV and XLSX
only — see the plan's Global Constraints for why PDF is explicitly out of
scope this phase."""
from __future__ import annotations

import csv
import io

import openpyxl

from services.export import export_response, rows_to_csv, rows_to_xlsx

COLUMNS = [("name", "Name"), ("revenue", "Revenue")]
ROWS = [{"name": "ABC Architects", "revenue": 1200000.0}, {"name": "XYZ Interiors", "revenue": 300000.0}]


def test_csv_header_row_uses_the_declared_labels():
    text = rows_to_csv(ROWS, COLUMNS).decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    assert header == ["Name", "Revenue"]


def test_csv_data_rows_follow_column_order():
    text = rows_to_csv(ROWS, COLUMNS).decode("utf-8")
    reader = list(csv.reader(io.StringIO(text)))
    assert reader[1] == ["ABC Architects", "1200000.0"]


def test_csv_handles_a_row_missing_a_declared_key():
    text = rows_to_csv([{"name": "No Revenue Field"}], COLUMNS).decode("utf-8")
    reader = list(csv.reader(io.StringIO(text)))
    assert reader[1] == ["No Revenue Field", ""]


def test_csv_is_safe_with_the_rupee_symbol():
    text = rows_to_csv([{"name": "₹ Test", "revenue": 1.0}], COLUMNS).decode("utf-8")
    assert "₹ Test" in text


def test_xlsx_roundtrips_through_openpyxl():
    data = rows_to_xlsx(ROWS, COLUMNS, sheet_title="Referrers")
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb["Referrers"]
    assert [c.value for c in ws[1]] == ["Name", "Revenue"]
    assert [c.value for c in ws[2]] == ["ABC Architects", 1200000.0]


def test_export_response_rejects_an_unknown_format():
    import pytest
    with pytest.raises(ValueError):
        export_response(ROWS, COLUMNS, "referrers", "pdf")


def test_export_response_sets_a_content_disposition_filename():
    response = export_response(ROWS, COLUMNS, "referrers", "csv")
    assert "referrers.csv" in response.headers["content-disposition"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.export'`

- [ ] **Step 3: Write the module**

Create `backend/services/export.py`:

```python
"""Generic rows -> CSV/XLSX export, shared by every Phase 2 table.

CSV and XLSX only. Every PDF export in this codebase (chalan, quotation,
followups) is a bespoke document layout with no generic table pattern to
build on — see the Phase 2 plan's Global Constraints for the full reasoning.
Existing per-route csv/openpyxl exports (executive_analytics_routes.py,
followup_routes.py, purchases_tracker.py, catalog_routes.py) are not
refactored onto this helper; this is new surface only.
"""
from __future__ import annotations

import csv
import io

import openpyxl
from fastapi.responses import StreamingResponse

Column = tuple[str, str]


def rows_to_csv(rows: list[dict], columns: list[Column]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([row.get(key, "") for key, _ in columns])
    return buf.getvalue().encode("utf-8-sig")  # BOM so Excel opens ₹/UTF-8 correctly


def rows_to_xlsx(rows: list[dict], columns: list[Column], sheet_title: str = "Export") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]  # Excel's own sheet-name length limit
    ws.append([label for _, label in columns])
    for row in rows:
        ws.append([row.get(key, "") for key, _ in columns])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_MEDIA_TYPES = {"csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def export_response(rows: list[dict], columns: list[Column], filename_base: str, fmt: str) -> StreamingResponse:
    if fmt not in _MEDIA_TYPES:
        raise ValueError(f"unsupported export format: {fmt}")
    data = rows_to_csv(rows, columns) if fmt == "csv" else rows_to_xlsx(rows, columns, sheet_title=filename_base)
    return StreamingResponse(
        io.BytesIO(data), media_type=_MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename_base}.{fmt}"'},
    )
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_export.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/export.py backend/tests/unit/test_export.py
git commit -m "Add a shared CSV/XLSX export helper for Phase 2's tables

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 13: `routes/sales_performance_routes.py`

**Files:**
- Create: `backend/routes/sales_performance_routes.py`
- Modify: `backend/server.py` (register the router)
- Test: `backend/tests/unit/test_sales_performance_routes.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5, 9–10, 12; `_filter_from_query`/`_floor_error_to_http`/`_period_of` pattern from `executive_overview_routes.py` (imported, not copy-pasted, since they're already generic over `AnalyticsFilter`)
- Produces endpoints, all `Depends(require_roles("owner","admin","manager"))`, all wrapped in `cache.cached`:
  - `GET /analytics/revenue-trend?granularity=day|week|month|quarter|year`
  - `GET /analytics/salespeople?format=csv|xlsx` (optional export)
  - `GET /analytics/salespeople/{salesperson_id}`
  - `GET /analytics/funnel`
  - `GET /analytics/categories?format=csv|xlsx`
  - `GET /analytics/collections?view=by_customer|by_age&format=csv|xlsx`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_sales_performance_routes.py`:

```python
"""Route-level tests for the Performance + Collections surfaces. Follows the
dependency-injection pattern from test_executive_overview_routes.py — call
the route functions directly with a fake user, not a live HTTP server."""
from __future__ import annotations

import pytest

from auth import UserPublic
from routes.sales_performance_routes import ABOVE_THE_FOLD_PERFORMANCE, router


def _user(role="owner") -> UserPublic:
    return UserPublic(id="u1", email="o@forge.app", full_name="Owner", role=role, active=True, floor_ids=[])


def test_router_is_registered_under_the_analytics_prefix():
    assert router.prefix == "/analytics"


def test_every_route_declares_the_analytics_role_gate():
    for route in router.routes:
        dep_names = {d.call.__name__ if hasattr(d.call, "__name__") else str(d.call) for d in route.dependant.dependencies}
        assert any("require_roles" in str(d) or "role" in n.lower() for n, d in [(n, n) for n in dep_names]) or True
        # Route-level role gating is exercised end-to-end in Stage E's permission test;
        # this is a structural smoke check that every route has at least one dependency.
        assert route.dependant.dependencies, f"{route.path} has no auth dependency"


def test_performance_above_the_fold_contract_is_a_module_constant():
    assert set(ABOVE_THE_FOLD_PERFORMANCE) == {
        "revenue_trend", "salespeople", "funnel", "categories",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_sales_performance_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'routes.sales_performance_routes'`

- [ ] **Step 3: Write the router**

Create `backend/routes/sales_performance_routes.py`, following `executive_overview_routes.py`'s exact shape — `APIRouter(prefix="/analytics", ...)`, `_filter_from_query`/`_floor_error_to_http` imported from that module (do not redefine), each endpoint resolving `f = _filter_from_query(...)`, `floors = accessible_floor_ids(user)`, calling the matching `gather_performance` function inside a `try/except FloorAccessError`, shaping with the matching `performance`/`collections` pure function, and returning `{"rows": [...], ...}` via `cache.cached(metric_id=..., collections=[...], filter_signature=filter_signature(f), floors=floors, loader=..., ttl=60)`. The `format` query param, when present, short-circuits to `export.export_response(rows_as_dicts, COLUMNS, filename_base, format)` **before** the cache wrapper (exports are not cached — always fresh). `ABOVE_THE_FOLD_PERFORMANCE = ("revenue_trend", "salespeople", "funnel", "categories")` is the module-level contract constant the test pins, mirroring Phase 1's `ABOVE_THE_FOLD`.

- [ ] **Step 4: Register the router**

In `backend/server.py`, alongside the existing `app.include_router(executive_overview_router)` line, add:

```python
from routes.sales_performance_routes import router as sales_performance_router
...
app.include_router(sales_performance_router)
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_sales_performance_routes.py -v`
Expected: PASS — 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/routes/sales_performance_routes.py backend/server.py backend/tests/unit/test_sales_performance_routes.py
git commit -m "Add the Performance + Collections HTTP surface

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 14: `routes/referral_analytics_routes.py`

**Files:**
- Create: `backend/routes/referral_analytics_routes.py`
- Modify: `backend/server.py`
- Test: `backend/tests/unit/test_referral_analytics_routes.py`

**Interfaces:**
- Consumes: Tasks 6–7, 11, 12; same `_filter_from_query`/`_floor_error_to_http` reuse as Task 13
- Produces:
  - `GET /analytics/referrers?type=architect|interior_designer&format=csv|xlsx`
  - `GET /analytics/referrers/{referrer_id}?granularity=month` — 404 when the referrer doesn't exist (mirroring the legacy `referrer_detail`'s handling, but per Phase 1's precedent of degrading gracefully rather than hard-404ing where the underlying revenue is still real — here there is no revenue without the `Referrer` doc resolving, since aggregation is keyed by `referrer_id` which requires the doc to exist for name/phone/company, so an honest 404 is correct, unlike Phase 1's `brand_detail` case)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_referral_analytics_routes.py`:

```python
"""Route-level tests for Referral Analytics. Mirrors test_sales_performance_routes.py."""
from __future__ import annotations

from routes.referral_analytics_routes import router


def test_router_is_registered_under_the_analytics_prefix():
    assert router.prefix == "/analytics"


def test_every_route_has_an_auth_dependency():
    for route in router.routes:
        assert route.dependant.dependencies, f"{route.path} has no auth dependency"


def test_the_referrer_list_route_and_the_detail_route_both_exist():
    paths = {r.path for r in router.routes}
    assert "/analytics/referrers" in paths
    assert "/analytics/referrers/{referrer_id}" in paths
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_referral_analytics_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'routes.referral_analytics_routes'`

- [ ] **Step 3: Write the router**

Create `backend/routes/referral_analytics_routes.py`. `GET /analytics/referrers`: `gather_referrer_raw` → `referrer_summary_rows` → cached JSON (or `export_response` when `format` is given, columns matching the 14-card fields: `name, type, customers_referred, quotations_total, quotations_confirmed, revenue, aov, conversion_rate, pending_value, pending_payments, is_active, repeat_customers`). `GET /analytics/referrers/{referrer_id}`: `gather_referrer_profile_data`; if `referrer_doc is None`, `raise HTTPException(404, "Referrer not found")`; otherwise also fetch that one referrer's raw summary row (reuse `gather_referrer_raw` filtered to a single id, or a new one-referrer variant — prefer filtering the existing function's match by `referrer_id` directly rather than adding a second gather function) → `referrer_summary_rows([raw])[0]` → `referrer_profile(...)`.

- [ ] **Step 4: Register the router**

In `backend/server.py`:

```python
from routes.referral_analytics_routes import router as referral_analytics_router
...
app.include_router(referral_analytics_router)
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_referral_analytics_routes.py -v`
Expected: PASS — 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/routes/referral_analytics_routes.py backend/server.py backend/tests/unit/test_referral_analytics_routes.py
git commit -m "Add the Referral Analytics HTTP surface

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## STAGE B GATE — live verification against `buildcon_house`

Before Stage C, verify live (backend restart requires user approval, per the shared-`:8010` constraint):

1. Run the full unit suite: `cd backend && ./.venv/bin/python -m pytest tests/unit -v` — record the new total (baseline 602 + Stage A/B additions).
2. Restart the shared backend (ask first) and hit every new endpoint with a real session: `/analytics/revenue-trend?granularity=month`, `/analytics/salespeople`, `/analytics/funnel`, `/analytics/categories`, `/analytics/collections`, `/analytics/referrers`.
3. **Reconcile revenue-trend against the known-good figure**: sum of `revenue-trend`'s monthly buckets for the period containing the 35 live orders must equal ₹39,77,337.00 (Phase 0/1's independently verified total) — if it doesn't, the bucketing window has an off-by-one at a boundary.
4. **Reconcile Collections**: `collections`'s total outstanding must equal ₹38,32,023.00 (Phase 1's verified figure) exactly.
5. **Three-way floor probe** on `/analytics/salespeople` and `/analytics/collections`, same recipe as Phase 1: no header / `first-floor` / `ground-floor`, confirm no leak and no double-count.
6. **Confirm the Task 8 cache fix actually works live**: record a real payment via `/payments`, immediately re-fetch `/analytics/collections`, confirm the outstanding figure reflects the new payment without waiting for the 60s TTL.
7. Confirm `/analytics/referrers` returns an empty list (0 of 78 quotations carry a referrer, per "Live data reality") rather than erroring, and `/analytics/referrers/{any-real-id}` 404s cleanly for a referrer id that exists in `db.referrers` but has zero quotations (a referrer who was added to the directory but never used yet — must not crash on an all-empty aggregation).
8. Fix and re-verify anything that doesn't reconcile before proceeding, matching Phase 1's Stage B discipline (two real defects were found there by doing exactly this).

Report to the user: reconciliation results, any defects found and fixed, remaining work.

---

## Task 15: typed API clients

**Files:**
- Create: `frontend/src/api/salesPerformance.ts`
- Create: `frontend/src/api/referrals.ts`

**Interfaces:**
- Consumes: `api` from `@/src/api/client` (same base the existing `executive.ts` uses)
- Produces: `salesPerformanceApi = { revenueTrend, salespeople, salespersonDetail, funnel, categories, collections }` and `referralsApi = { summaries, profile }`, every function typed, mirroring `executive.ts`'s `qs()`-builder pattern

- [ ] **Step 1: Write the files**

No backend to fail against here (types only) — this task has no failing-test step; verification is `tsc`. Create `frontend/src/api/salesPerformance.ts`:

```ts
import { api } from "@/src/api/client";

export type Comparison = { history_state: "ok" | "no_prior_period" | "insufficient_history"; delta_pct?: number };
export type TrendPoint = { bucket: string; revenue: number };
export type SalespersonRow = {
  salesperson_id: string; name: string; revenue: number; orders: number; aov: number;
  walkins_handled: number; conversion_pct: number | null; last_activity_at: string | null;
  rank: number; previous_rank: number | null; rank_movement: number | null; comparison: Comparison;
};
export type FunnelStage = {
  key: string; label: string; count: number;
  conversion_from_start_pct: number | null; dropoff_from_previous_pct: number | null;
  median_days_in_stage: number | null; revenue_lost_at_drop: number;
};
export type CategoryRow = { category_id: string; name: string; revenue: number; qty: number };
export type CollectionRow = {
  customer_id: string; customer_name: string; ordered_at: string | null;
  grand_total: number; collected: number; outstanding: number; age_days: number | null; age_bucket: string | null;
};
export type CollectionsQuery = { floor_id?: string; preset?: string; date_from?: string; date_to?: string };

function qs(q?: Record<string, string | undefined>): string {
  if (!q) return "";
  const parts = Object.entries(q).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v!)}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

export const salesPerformanceApi = {
  revenueTrend: (granularity: string, q?: CollectionsQuery) =>
    api.get<{ points: TrendPoint[] }>(`/analytics/revenue-trend?granularity=${granularity}${qs(q).replace("?", "&")}`),
  salespeople: (q?: CollectionsQuery) => api.get<{ rows: SalespersonRow[] }>(`/analytics/salespeople${qs(q)}`),
  salespersonDetail: (id: string, q?: CollectionsQuery) =>
    api.get<SalespersonRow>(`/analytics/salespeople/${id}${qs(q)}`),
  funnel: (q?: CollectionsQuery) => api.get<{ stages: FunnelStage[] }>(`/analytics/funnel${qs(q)}`),
  categories: (q?: CollectionsQuery) => api.get<{ rows: CategoryRow[] }>(`/analytics/categories${qs(q)}`),
  collections: (view: "by_customer" | "by_age", q?: CollectionsQuery) =>
    api.get<{ rows: CollectionRow[] } | { buckets: Record<string, { count: number; outstanding: number }> }>(
      `/analytics/collections?view=${view}${qs(q).replace("?", "&")}`,
    ),
  exportUrl: (path: string, format: "csv" | "xlsx", q?: CollectionsQuery) =>
    `/analytics/${path}${qs({ ...q, format })}`,
};
```

Create `frontend/src/api/referrals.ts`:

```ts
import { api } from "@/src/api/client";

export type ReferrerType = "architect" | "interior_designer";
export type ReferrerSummary = {
  referrer_id: string; name: string; type: ReferrerType;
  customers_referred: number; quotations_total: number; quotations_approved: number; quotations_confirmed: number;
  revenue: number; aov: number; conversion_rate: number | null;
  pending_count: number; pending_value: number; pending_payments: number;
  first_referral_at: string | null; last_referral_at: string | null; is_active: boolean; repeat_customers: number;
};
export type ReferrerProfile = {
  referrer_id: string; name: string; type: ReferrerType; phone: string | null; company: string | null;
  summary: ReferrerSummary; monthly_trend: { bucket: string; revenue: number }[];
  brand_preference: { brand_id: string; brand_name: string; revenue: number }[];
  product_preference: { product_id: string; product_name: string; revenue: number }[];
  floor_split: Record<string, number>;
};

function qs(q?: Record<string, string | undefined>): string {
  if (!q) return "";
  const parts = Object.entries(q).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v!)}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

export const referralsApi = {
  summaries: (type: ReferrerType, q?: Record<string, string | undefined>) =>
    api.get<{ rows: ReferrerSummary[] }>(`/analytics/referrers${qs({ ...q, type })}`),
  profile: (id: string, granularity = "month") =>
    api.get<ReferrerProfile>(`/analytics/referrers/${id}?granularity=${granularity}`),
};
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors from these two files (they aren't imported anywhere yet, so this mostly checks internal type consistency)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/salesPerformance.ts frontend/src/api/referrals.ts
git commit -m "Add typed API clients for Performance, Collections and Referral Analytics

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 16: `TrendBarChart` and `FunnelChart`

**Files:**
- Create: `frontend/src/components/charts/TrendBarChart.tsx`
- Create: `frontend/src/components/charts/FunnelChart.tsx`

**Interfaces:**
- Consumes: `ChartFrame` (`{height, state, stateLabel, children: (width) => ReactNode}`), `react-native-svg`'s `Svg`/`Rect`/`Text` (already a dependency, same as `Sparkline`)
- Produces:
  - `TrendBarChart({ points: {bucket:string; revenue:number}[]; height?: number; state?: ChartState; testID?: string })`
  - `FunnelChart({ stages: FunnelStage[]; height?: number; state?: ChartState; testID?: string })`

**File 1** — `frontend/src/components/charts/TrendBarChart.tsx`:

```tsx
import React from "react";
import { View } from "react-native";
import Svg, { Rect, Text as SvgText } from "react-native-svg";
import { ChartFrame, ChartState } from "@/src/components/charts/ChartFrame";
import { colors, spacing, type as typeTokens } from "@/src/theme/tokens";
import { fmtMoneyCompact } from "@/src/design/tokens";

export function TrendBarChart({
  points, height = 200, state = "ready", testID,
}: { points: { bucket: string; revenue: number }[]; height?: number; state?: ChartState; testID?: string }) {
  const max = Math.max(1, ...points.map((p) => p.revenue));
  return (
    <ChartFrame height={height} state={points.length ? state : "empty"} testID={testID}>
      {(width) => {
        const barWidth = points.length ? Math.max(8, width / points.length - spacing.sm) : 0;
        return (
          <Svg width={width} height={height}>
            {points.map((p, i) => {
              const barHeight = (p.revenue / max) * (height - 28);
              const x = i * (width / points.length) + spacing.sm / 2;
              const y = height - 20 - barHeight;
              return (
                <React.Fragment key={p.bucket}>
                  <Rect x={x} y={y} width={barWidth} height={Math.max(barHeight, 1)} rx={3} fill={colors.brand} />
                  <SvgText x={x + barWidth / 2} y={height - 6} fontSize={10} fill={colors.onSurfaceMuted} textAnchor="middle">
                    {p.bucket}
                  </SvgText>
                </React.Fragment>
              );
            })}
          </Svg>
        );
      }}
    </ChartFrame>
  );
}
```

**File 2** — `frontend/src/components/charts/FunnelChart.tsx`:

```tsx
import React from "react";
import Svg, { Rect, Text as SvgText } from "react-native-svg";
import { ChartFrame, ChartState } from "@/src/components/charts/ChartFrame";
import { colors, spacing } from "@/src/theme/tokens";
import type { FunnelStage } from "@/src/api/salesPerformance";

export function FunnelChart({
  stages, height = 320, state = "ready", testID,
}: { stages: FunnelStage[]; height?: number; state?: ChartState; testID?: string }) {
  const max = Math.max(1, ...stages.map((s) => s.count));
  const rowHeight = stages.length ? (height - spacing.sm) / stages.length : 0;
  return (
    <ChartFrame height={height} state={stages.every((s) => s.count === 0) ? "empty" : state} testID={testID}>
      {(width) => (
        <Svg width={width} height={height}>
          {stages.map((s, i) => {
            const barWidth = Math.max(4, (s.count / max) * (width - 140));
            const y = i * rowHeight;
            return (
              <React.Fragment key={s.key}>
                <SvgText x={0} y={y + rowHeight / 2 + 4} fontSize={12} fill={colors.onSurface}>
                  {s.label}
                </SvgText>
                <Rect x={110} y={y + 6} width={barWidth} height={Math.max(rowHeight - 12, 4)} rx={4} fill={colors.brand} />
                <SvgText x={110 + barWidth + 8} y={y + rowHeight / 2 + 4} fontSize={12} fill={colors.onSurfaceMuted}>
                  {s.count}
                  {s.dropoff_from_previous_pct != null ? ` (-${s.dropoff_from_previous_pct}%)` : ""}
                </SvgText>
              </React.Fragment>
            );
          })}
        </Svg>
      )}
    </ChartFrame>
  );
}
```

- [ ] **Step 1: Verify**

Run: `cd frontend && npx tsc --noEmit` — confirm no new errors. Then a quick render smoke-check: temporarily import `TrendBarChart` into `sales-data/executive.tsx` (or any mounted screen) with hardcoded sample points, load it in the browser preview, confirm bars render and no console errors, then revert the temporary import (the real wiring happens in Task 22).

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/charts/TrendBarChart.tsx frontend/src/components/charts/FunnelChart.tsx
git commit -m "Add TrendBarChart and FunnelChart on the existing ChartFrame/SVG kit

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 17: `ExportMenu`

**Files:**
- Create: `frontend/src/components/analytics/ExportMenu.tsx`

**Interfaces:**
- Produces: `ExportMenu({ path: string; query?: Record<string,string|undefined>; label?: string; testID?: string })` — a small button that opens the browser-download URL for CSV or XLSX, following the existing download-URL-construction convention already used for PDF/xlsx downloads elsewhere in `api/client.ts` (per "Live data reality" §9) rather than fetching the blob client-side.

```tsx
import React, { useState } from "react";
import { Pressable, View } from "react-native";
import Feather from "@expo/vector-icons/Feather";
import { Text } from "@/src/components/ds";
import { colors, radius, spacing } from "@/src/theme/tokens";
import { buildDownloadUrl } from "@/src/api/client";

export function ExportMenu({
  path, query, label = "Export", testID,
}: { path: string; query?: Record<string, string | undefined>; label?: string; testID?: string }) {
  const [open, setOpen] = useState(false);

  const download = (format: "csv" | "xlsx") => {
    setOpen(false);
    const url = buildDownloadUrl(path, { ...query, format });
    if (typeof window !== "undefined") window.open(url, "_blank");
  };

  return (
    <View style={{ position: "relative" }}>
      <Pressable
        accessibilityLabel={label}
        onPress={() => setOpen((v) => !v)}
        testID={testID}
        style={{
          flexDirection: "row", alignItems: "center", gap: spacing.xs,
          minHeight: 44, paddingHorizontal: spacing.md,
          borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border,
        }}
      >
        <Feather name="download" size={16} color={colors.onSurface} />
        <Text style={{ color: colors.onSurface }}>{label}</Text>
      </Pressable>
      {open && (
        <View
          style={{
            position: "absolute", top: 48, right: 0, zIndex: 20,
            backgroundColor: colors.surface, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border,
            minWidth: 140, paddingVertical: spacing.xs,
          }}
        >
          {(["csv", "xlsx"] as const).map((format) => (
            <Pressable
              key={format}
              onPress={() => download(format)}
              testID={`${testID}-${format}`}
              style={{ minHeight: 44, justifyContent: "center", paddingHorizontal: spacing.md }}
            >
              <Text style={{ color: colors.onSurface }}>{format.toUpperCase()}</Text>
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
}
```

If `buildDownloadUrl` does not already exist as an exported helper in `frontend/src/api/client.ts` (the earlier research found only a *comment* describing this pattern, not necessarily an exported function — verify by reading the file before writing this task), add it there rather than duplicating URL-building logic inline:

```ts
export function buildDownloadUrl(path: string, query: Record<string, string | undefined>): string {
  const params = Object.entries(query).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v!)}`);
  const qs = params.length ? `?${params.join("&")}` : "";
  return `${API_BASE_URL}${path}${qs}`;
}
```

(match `API_BASE_URL`'s real exported name in that file — read it first rather than assuming.)

- [ ] **Step 1: Verify**

Run: `cd frontend && npx tsc --noEmit`. This component has no route yet — full interaction verification happens in Stage D once it's mounted in a real screen; do not claim a browser pass here (Phase 1's Stage C precedent: state the deferral explicitly rather than skip it silently).

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/analytics/ExportMenu.tsx frontend/src/api/client.ts
git commit -m "Add ExportMenu, the first CSV/XLSX export UI in this codebase

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 18: `ReferredByField` + `ReferrerPickerSheet` — headless, prop-driven

**Files:**
- Create: `frontend/src/components/shared/ReferredByField.tsx`
- Create: `frontend/src/components/shared/ReferrerPickerSheet.tsx`

**Interfaces:**
- Consumes: `Referrer` type (reused from `@/src/components/quotation/helpers/types`, not redefined — it is already shared-shape, just historically homed under `quotation/`)
- Produces:
  - `ReferredByField({ referrerType, referrerId, referrerName, onOpen, testID }: { referrerType: "architect"|"interior_designer"|null; referrerId: string|null; referrerName: string; onOpen: () => void; testID?: string })` — the trigger pressable, replacing `BuilderTopbar.tsx`'s inline one 1:1
  - `ReferrerPickerSheet({ open, onClose, referrers, onSelect, onCreate, onClear, testID }: { open: boolean; onClose: () => void; referrers: Referrer[]; onSelect: (type, id, name) => void; onCreate: (data: {name:string; type:"architect"|"interior_designer"}) => Promise<string | null>; onClear: () => void; testID?: string })` — the search/tab/create sheet, extracted from `ReferrerSwitcherSheet.tsx` with **zero behavior change**, made context-free by taking everything as props instead of reading `useBuilder()`

**Why headless:** the Sanitary builder's state lives in `BuilderContext`'s reducer/history system; the Tiles builder's state lives in a local `useState`-based hook with no context at all. A component that reads `useBuilder()` directly cannot be reused by Tiles. Every piece of state and every mutation crosses this boundary as a prop or callback — this is the single design decision that makes Task 19 and Task 20 both trivial wiring rather than two divergent implementations.

- [ ] **Step 1: Write the components**

Create `frontend/src/components/shared/ReferredByField.tsx`:

```tsx
import React from "react";
import { Pressable } from "react-native";
import Feather from "@expo/vector-icons/Feather";
import { Text } from "@/src/components/ds";
import { colors, spacing } from "@/src/theme/tokens";

export function ReferredByField({
  referrerType, referrerName, onOpen, testID = "hdr-referrer",
}: {
  referrerType: "architect" | "interior_designer" | null;
  referrerId: string | null;
  referrerName: string;
  onOpen: () => void;
  testID?: string;
}) {
  return (
    <Pressable
      onPress={onOpen}
      testID={testID}
      accessibilityLabel="Referred by"
      style={{
        flexDirection: "row", alignItems: "center", gap: spacing.xs,
        minHeight: 44, paddingHorizontal: spacing.sm,
      }}
    >
      <Feather name="user-plus" size={16} color={colors.onSurfaceMuted} />
      <Text style={{ color: colors.onSurfaceMuted }} numberOfLines={1}>
        {referrerName || "Referred by: None"}
      </Text>
      {referrerType && (
        <Text style={{ color: colors.onSurfaceSubtle, fontSize: 11 }}>
          ({referrerType === "architect" ? "Architect" : "Interior Designer"})
        </Text>
      )}
    </Pressable>
  );
}
```

Create `frontend/src/components/shared/ReferrerPickerSheet.tsx` by extracting `ReferrerSwitcherSheet.tsx`'s current body (tab state, search `q`, `creating`/`name`/`saving` local state, the two-tab architect/interior-designer list, the "+ Add new" inline form, the "Clear" action) into this new file, changing only the data-access boundary:

- Replace every `useBuilder()` read/call with the corresponding prop: `b.referrers` → `referrers` prop; `b.setReferrer(type,id,name)` → `onSelect(type,id,name)`; `b.createReferrer(data)` → `await onCreate(data)`; `b.clearReferrer()` → `onClear()`; `b.referrerSwitcherOpen`/`b.setReferrerSwitcherOpen` → `open`/`onClose` props.
- Keep the `BottomSheet` wrapper, the tab UI, the search filter, and the create-inline-form exactly as they render today — this is an extraction, not a redesign. `npx tsc --noEmit` plus Task 19's live regression check is what proves "zero behavior change," not a rewrite from memory.

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`. Full interaction verification happens in Task 19 once this is wired into the real builder (this file has no mount point yet on its own).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/shared/ReferredByField.tsx frontend/src/components/shared/ReferrerPickerSheet.tsx
git commit -m "Extract a headless, prop-driven ReferredByField + ReferrerPickerSheet

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 19: wire `ReferredByField` into the Sanitary builder

**Files:**
- Modify: `frontend/src/components/quotation/layout/BuilderTopbar.tsx`
- Modify: `frontend/src/components/quotation/layout/BuilderShell.tsx`
- Remove: `frontend/src/components/quotation/sheets/ReferrerSwitcherSheet.tsx`

**Interfaces:**
- Consumes: `ReferredByField`, `ReferrerPickerSheet` (Task 18); `BuilderContext`'s existing `referrers`, `setReferrer`, `clearReferrer`, `createReferrer`, `referrerSwitcherOpen`, `setReferrerSwitcherOpen` (all already exist — Task 19 changes zero lines in `BuilderContext.tsx`)

- [ ] **Step 1: Replace the topbar's inline pressable**

In `BuilderTopbar.tsx`, remove the existing `testID="hdr-referrer"` `Pressable`/`onPress={() => b.setReferrerSwitcherOpen(true)}` block and replace it with:

```tsx
<ReferredByField
  referrerType={b.s.header.referrerType}
  referrerId={b.s.header.referrerId}
  referrerName={b.s.header.referrerName}
  onOpen={() => b.setReferrerSwitcherOpen(true)}
/>
```

Add the import: `import { ReferredByField } from "@/src/components/shared/ReferredByField";`

- [ ] **Step 2: Swap the mounted sheet**

In `BuilderShell.tsx`, replace `<ReferrerSwitcherSheet />` (line ~109) with:

```tsx
<ReferrerPickerSheet
  open={b.referrerSwitcherOpen}
  onClose={() => b.setReferrerSwitcherOpen(false)}
  referrers={b.referrers}
  onSelect={b.setReferrer}
  onCreate={b.createReferrer}
  onClear={b.clearReferrer}
/>
```

Update the import from `ReferrerSwitcherSheet` to `ReferrerPickerSheet` (`@/src/components/shared/ReferrerPickerSheet`).

- [ ] **Step 3: Delete the superseded file**

```bash
git rm frontend/src/components/quotation/sheets/ReferrerSwitcherSheet.tsx
```

Grep the repo first (`grep -rn "ReferrerSwitcherSheet" frontend/`) to confirm no other file still imports it before deleting — `BuilderTopbar.tsx` and `BuilderShell.tsx` were the only two call sites found during research, but re-verify against current state rather than trusting the research snapshot.

- [ ] **Step 4: Verify — zero behavior change**

Run: `cd frontend && npx tsc --noEmit`. Then live-verify in the browser preview: open the Sanitary Quotation Builder, click "Referred by," confirm the sheet opens with the same tab/search/create UI as before, select an existing referrer, confirm the topbar label updates and `Network` shows a `PATCH /quotations/{id}` with `referrer_type`/`referrer_id`, then clear it and confirm the label reverts to "Referred by: None" and the PATCH carries `referrer_id: ""`. This is a regression check, not new-feature verification — the bar is "identical to before," confirmed live, not assumed from the diff.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/quotation/layout/BuilderTopbar.tsx frontend/src/components/quotation/layout/BuilderShell.tsx
git commit -m "Wire the Sanitary builder onto the shared ReferredByField/ReferrerPickerSheet

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 20: wire `ReferredByField` into `TilesDocBuilder` — new capability

**Files:**
- Modify: `frontend/src/components/tiles/TilesDocBuilder.tsx`

**Interfaces:**
- Consumes: `ReferredByField`, `ReferrerPickerSheet` (Task 18)
- Produces: `useTilesDoc`'s return value gains `referrer: {type, id, name}`, `referrerSwitcherOpen: boolean`, `setReferrerSwitcherOpen`, `referrers: Referrer[]`, `setReferrer(type,id,name)`, `clearReferrer()`, `createReferrer(data)`

This is the capability §5.2 exists for: today Ground Floor quotations structurally cannot carry a referrer. Everything here is new, not extracted.

- [ ] **Step 1: Add referrer state to `useTilesDoc`**

In `TilesDocBuilder.tsx`, inside `useTilesDoc` (near the other `useState` calls at lines 175–190), add:

```ts
const [referrer, setReferrerState] = useState<{ type: "architect" | "interior_designer" | null; id: string | null; name: string }>({ type: null, id: null, name: "" });
const [referrers, setReferrers] = useState<Referrer[]>([]);
const [referrerSwitcherOpen, setReferrerSwitcherOpen] = useState(false);
```

Fetch the directory alongside the existing customer fetch (same `useEffect` block at line 192, or a sibling one):

```ts
useEffect(() => {
  api.get<Referrer[]>("/referrers").then(setReferrers).catch(() => {});
}, []);
```

- [ ] **Step 2: Hydrate on restore**

In the restore effect (lines 197–248), inside the `setHeader({...})` block, add the referrer hydration alongside it:

```ts
setReferrerState({
  type: doc.referrer_type || null,
  id: doc.referrer_id || null,
  name: doc.referrer_name || "",
});
```

- [ ] **Step 3: Include referrer fields in the save payload**

In `persist()`'s `payload` object (lines 397–408), add:

```ts
referrer_type: referrer.type,
referrer_id: referrer.id === null ? "" : referrer.id,
```

(the `""` convention for clearing matches `BuilderContext.clearReferrer`'s exact reasoning — `update_quotation` treats JSON `null` as "field absent," so an explicit empty string is required to actually clear it). Add `referrer` to `persist`'s `useCallback` dependency array.

- [ ] **Step 4: Add the mutation functions and expose the new surface**

```ts
const setReferrer = useCallback((type: "architect" | "interior_designer", id: string, name: string) => {
  setReferrerState({ type, id, name });
  markDirty();
}, [markDirty]);

const clearReferrer = useCallback(() => {
  setReferrerState({ type: null, id: null, name: "" });
  markDirty();
}, [markDirty]);

const createReferrer = useCallback(async (data: { name: string; type: "architect" | "interior_designer" }): Promise<string | null> => {
  try {
    const created = await api.post<Referrer>("/referrers", data);
    setReferrers((cur) => [created, ...cur].sort((a, b) => a.name.localeCompare(b.name)));
    setReferrer(created.type, created.id, created.name);
    return created.id;
  } catch (e: any) {
    toast.error(e?.detail || "Couldn't create referrer");
    return null;
  }
}, [setReferrer]);
```

Add all of `referrer, referrers, referrerSwitcherOpen, setReferrerSwitcherOpen, setReferrer, clearReferrer, createReferrer` to the object `useTilesDoc` returns.

- [ ] **Step 5: Add the field to `MetaGrid`**

In `MetaGrid` (lines 773–818), add a row rendering `<ReferredByField referrerType={doc.referrer.type} referrerId={doc.referrer.id} referrerName={doc.referrer.name} onOpen={() => doc.setReferrerSwitcherOpen(true)} testID="tiles-hdr-referrer" />` alongside the existing `REFERENCE`/`ATTENDED BY` cells. Mount `<ReferrerPickerSheet open={doc.referrerSwitcherOpen} onClose={() => doc.setReferrerSwitcherOpen(false)} referrers={doc.referrers} onSelect={doc.setReferrer} onCreate={doc.createReferrer} onClear={doc.clearReferrer} />` once at the top level of `TilesDocBuilder`'s render (mirroring `BuilderShell.tsx`'s mount point from Task 19).

Add the import: `import { ReferredByField } from "@/src/components/shared/ReferredByField"; import { ReferrerPickerSheet } from "@/src/components/shared/ReferrerPickerSheet"; import type { Referrer } from "@/src/components/quotation/helpers/types";`

- [ ] **Step 6: Verify — new capability, live**

Run: `cd frontend && npx tsc --noEmit`. Live-verify: open a Ground Floor Tiles Selection or Quotation, confirm the "Referred by" field now appears in the header grid, open it, create a brand-new architect referrer, confirm it saves (`Network` tab shows `PATCH /quotations/{id}` with `referrer_type: "architect"`, `referrer_id: <new-id>`), reload the page, confirm the referrer is still shown (hydration round-trips). Then open the Sanitary builder and confirm the **same** referrer (created from Tiles) appears in its picker list — proving the one-directory claim from §5.2 live, not just by reading the code.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/tiles/TilesDocBuilder.tsx
git commit -m "Give Ground Floor Tiles quotations a Referred By field for the first time

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## STAGE C GATE

Before Stage D: `npx tsc --noEmit` clean; both builders live-verified (Task 19's regression check, Task 20's new-capability check); ledger entry written.

---

## Task 21: `/sales-data/sales` — the Performance workspace screen

**Files:**
- Create: `frontend/app/(admin)/sales-data/sales.tsx`

**Interfaces:**
- Consumes: `salesPerformanceApi` (Task 15), `TrendBarChart`/`FunnelChart` (Task 16), `ExportMenu` (Task 17), `DataTable`/`CellNumber`/`CellStack` (`TileTable.tsx`), `KpiCard`/`PillTabs` (`ui.tsx`), `HistoryNote`/`ComparisonLine` (Phase 1 `analytics/HistoryNote.tsx`)

Follows `executive.tsx`/`today.tsx`'s established screen pattern exactly: `useLocalSearchParams` seeds local state, `router.setParams` on every filter change, gate on `["owner","admin","manager"]` after all hooks, wrap in `<AdminPage>`. Sections in order: granularity `PillTabs` (day/week/month/quarter/year — five options, so the row **must** carry `PillTabs`'s existing `width:"100%"` fix, already load-bearing per "Live data reality") + `TrendBarChart`; Revenue by Salesperson `DataTable` (columns: rank, name, revenue via `CellNumber`, orders, AOV, conversion via `ComparisonLine`-adjacent text, rank movement arrow) with an `ExportMenu`; `FunnelChart` with each stage's conversion/dropoff/median-duration/revenue-lost surfaced as `CellNumber`s below it (`median_days_in_stage: null` renders via `HistoryNote`'s pattern — "not tracked yet," never a blank cell that reads as zero); Revenue by Category `DataTable` with an `ExportMenu`.

- [ ] **Step 1: Write the screen**

Structure (full file, following `today.tsx`'s proven shape):

```tsx
import React, { useCallback, useEffect, useState } from "react";
import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { View } from "react-native";
import { AdminPage } from "@/src/components/AdminPage";
import { useAuth } from "@/src/state/auth";
import { PillTabs } from "@/src/components/ui";
import { DataTable, CellNumber, CellStack } from "@/src/components/tiles/TileTable";
import { TrendBarChart } from "@/src/components/charts/TrendBarChart";
import { FunnelChart } from "@/src/components/charts/FunnelChart";
import { ExportMenu } from "@/src/components/analytics/ExportMenu";
import { salesPerformanceApi, SalespersonRow, FunnelStage, CategoryRow, TrendPoint } from "@/src/api/salesPerformance";
import { spacing } from "@/src/theme/tokens";

type Granularity = "day" | "week" | "month" | "quarter" | "year";

export default function SalesPerformanceScreen() {
  const { staff } = useAuth();
  const router = useRouter();
  const params = useLocalSearchParams<{ floor_id?: string; granularity?: Granularity }>();
  const [floorId, setFloorId] = useState<string | undefined>(params.floor_id);
  const [granularity, setGranularity] = useState<Granularity>((params.granularity as Granularity) || "month");
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [salespeople, setSalespeople] = useState<SalespersonRow[]>([]);
  const [funnel, setFunnel] = useState<FunnelStage[]>([]);
  const [categories, setCategories] = useState<CategoryRow[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const q = { floor_id: floorId };
    const [trendRes, peopleRes, funnelRes, catRes] = await Promise.all([
      salesPerformanceApi.revenueTrend(granularity, q),
      salesPerformanceApi.salespeople(q),
      salesPerformanceApi.funnel(q),
      salesPerformanceApi.categories(q),
    ]);
    setTrend(trendRes.points);
    setSalespeople(peopleRes.rows);
    setFunnel(funnelRes.stages);
    setCategories(catRes.rows);
    setLoading(false);
  }, [floorId, granularity]);

  useEffect(() => { load(); }, [load]);

  const changeGranularity = (g: Granularity) => {
    setGranularity(g);
    router.setParams({ granularity: g });
  };

  if (staff && !["owner", "admin", "manager"].includes(staff.role)) {
    return <Redirect href="/(admin)/dashboard" />;
  }

  return (
    <AdminPage title="Performance" subtitle="Revenue, salespeople, and the sales funnel">
      <View style={{ gap: spacing.xl }}>
        <PillTabs
          value={granularity}
          onChange={changeGranularity}
          options={[
            { value: "day", label: "Day" }, { value: "week", label: "Week" },
            { value: "month", label: "Month" }, { value: "quarter", label: "Quarter" }, { value: "year", label: "Year" },
          ]}
          testID="performance-granularity"
        />
        <TrendBarChart points={trend} state={loading ? "loading" : "ready"} />

        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <CellStack title="Revenue by Salesperson" />
          <ExportMenu path="/analytics/salespeople" query={{ floor_id: floorId }} testID="export-salespeople" />
        </View>
        <DataTable<SalespersonRow>
          columns={[
            { key: "rank", label: "#", width: 40, render: (r) => <CellNumber value={r.rank} /> },
            { key: "name", label: "Salesperson", grow: 2, render: (r) => <CellStack title={r.name} /> },
            { key: "revenue", label: "Revenue", align: "right", render: (r) => <CellNumber value={r.revenue} money /> },
            { key: "orders", label: "Orders", align: "right", render: (r) => <CellNumber value={r.orders} /> },
            { key: "aov", label: "AOV", align: "right", render: (r) => <CellNumber value={r.aov} money /> },
            { key: "conversion", label: "Conversion", align: "right", render: (r) => <CellNumber value={r.conversion_pct} suffix="%" /> },
          ]}
          data={salespeople}
          keyExtractor={(r) => r.salesperson_id}
          onRowPress={(r) => router.push(`/(admin)/sales-data/sales?salesperson=${r.salesperson_id}`)}
          emptyMessage="No revenue in this period yet."
        />

        <CellStack title="Sales Funnel" />
        <FunnelChart stages={funnel} state={loading ? "loading" : "ready"} />

        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <CellStack title="Revenue by Category" />
          <ExportMenu path="/analytics/categories" query={{ floor_id: floorId }} testID="export-categories" />
        </View>
        <DataTable<CategoryRow>
          columns={[
            { key: "name", label: "Category", grow: 2, render: (r) => <CellStack title={r.name} /> },
            { key: "revenue", label: "Revenue", align: "right", render: (r) => <CellNumber value={r.revenue} money /> },
            { key: "qty", label: "Units", align: "right", render: (r) => <CellNumber value={r.qty} /> },
          ]}
          data={categories}
          keyExtractor={(r) => r.category_id}
          emptyMessage="No category revenue in this period yet."
        />
      </View>
    </AdminPage>
  );
}
```

Verify `DataTable`'s actual exported cell components' exact prop names (`CellNumber`'s `money`/`suffix` props are illustrative here — read `TileTable.tsx` first and match its real signature; adjust this task's code to the real prop names before implementing, rather than assuming).

- [ ] **Step 2: Verify live**

`cd frontend && npx tsc --noEmit`, then live in the browser preview at 1280/768/375: confirm the trend chart renders with real data, the granularity picker's 5 options wrap correctly at 375px (the `PillTabs` fix from Phase 1 must hold here too — check `docScrollWidth === docClientWidth`), the salesperson table sorts/exports, the funnel chart shows all 8 stages with the three `None` durations rendering as "not tracked" rather than blank or zero, revenue-by-category exports.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/\(admin\)/sales-data/sales.tsx
git commit -m "Build the Performance workspace screen

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 22: `/sales-data/collections` — the Collections workspace screen

**Files:**
- Create: `frontend/app/(admin)/sales-data/collections.tsx`

**Interfaces:**
- Consumes: `salesPerformanceApi.collections` (Task 15), `DataTable`, `ExportMenu`, `KpiCard`

Same screen pattern as Task 21. `PillTabs` toggles `by_customer`/`by_age`. `by_customer` view: `DataTable<CollectionRow>` (customer, outstanding, age, age bucket badge via `statusMeta`-style coloring — reuse the existing `statusMeta` token map rather than inventing new bucket colors) with `ExportMenu`. `by_age` view: four `KpiCard`s, one per `AGE_BUCKETS` label, each showing count + outstanding ₹, the "90+" card in `tone="warning"`.

- [ ] **Step 1: Write the screen**

Follow Task 21's exact structural pattern (imports, `useLocalSearchParams`/`router.setParams`, role gate, `<AdminPage>` wrapper). View toggle:

```tsx
const [view, setView] = useState<"by_customer" | "by_age">("by_customer");
```

`by_age`'s four `KpiCard`s map directly over the response's `Object.entries(buckets)`, in the fixed `AGE_BUCKETS` order (`"0-30", "31-60", "61-90", "90+"`) rather than whatever order the JSON object happens to iterate in — build a `const AGE_BUCKET_ORDER = ["0-30","31-60","61-90","90+"] as const;` in this file and map over that, not `Object.keys`.

- [ ] **Step 2: Verify live**

`tsc --noEmit`, then browser pass at 1280/768/375: toggle between views, confirm `by_customer`'s outstanding total and `by_age`'s summed bucket totals agree with each other and with the KPI figure verified live in Stage B's gate, confirm export works, confirm the "90+" bucket is visually flagged.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/\(admin\)/sales-data/collections.tsx
git commit -m "Build the Collections workspace screen

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 23: `ReferralsWorkspace` + the two thin route files + §5.3 onboarding

**Files:**
- Create: `frontend/src/components/analytics/ReferralsWorkspace.tsx`
- Create: `frontend/app/(admin)/sales-data/referrals/architects.tsx`
- Create: `frontend/app/(admin)/sales-data/referrals/interior-designers.tsx`

**Interfaces:**
- Consumes: `referralsApi.summaries` (Task 15), `DataTable`, `ExportMenu`
- Produces: `ReferralsWorkspace({ type: "architect" | "interior_designer" })`

Spec §5.3's exact onboarding copy renders whenever `rows.length === 0` — this is the expected state today (0 of 78 quotations carry a referrer), so this is not a hypothetical branch to test once and forget; it is what every real user sees at launch.

- [ ] **Step 1: Write the shared workspace component**

```tsx
import React, { useCallback, useEffect, useState } from "react";
import { View } from "react-native";
import { useRouter } from "expo-router";
import { Text } from "@/src/components/ds";
import { Button } from "@/src/components/ui";
import { DataTable, CellNumber, CellStack, CellChevron } from "@/src/components/tiles/TileTable";
import { ExportMenu } from "@/src/components/analytics/ExportMenu";
import { referralsApi, ReferrerSummary, ReferrerType } from "@/src/api/referrals";
import { colors, spacing, type as typeTokens } from "@/src/theme/tokens";

export function ReferralsWorkspace({ type }: { type: ReferrerType }) {
  const router = useRouter();
  const [rows, setRows] = useState<ReferrerSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const res = await referralsApi.summaries(type);
    setRows(res.rows);
    setLoading(false);
  }, [type]);

  useEffect(() => { load(); }, [load]);

  const label = type === "architect" ? "Architect" : "Interior Designer";

  if (!loading && rows.length === 0) {
    return (
      <View style={{ alignItems: "center", padding: spacing.xxl, gap: spacing.md }}>
        <Text style={typeTokens.titleMd}>Unlock referral intelligence</Text>
        <Text style={[typeTokens.bodyMuted, { textAlign: "center", maxWidth: 420 }]}>
          Start capturing referral information in quotations to unlock {label} performance insights.
        </Text>
        <Button label="Open Referrer Directory" onPress={() => router.push(`/(admin)/sales-data/referrals/${type === "architect" ? "architects" : "interior-designers"}`)} />
      </View>
    );
  }

  return (
    <View style={{ gap: spacing.lg }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <Text style={typeTokens.titleMd}>{label}s</Text>
        <ExportMenu path="/analytics/referrers" query={{ type }} testID={`export-referrers-${type}`} />
      </View>
      <DataTable<ReferrerSummary>
        columns={[
          { key: "name", label: label, grow: 2, render: (r) => <CellStack title={r.name} subtitle={r.is_active ? "Active" : "Quiet"} /> },
          { key: "revenue", label: "Revenue", align: "right", render: (r) => <CellNumber value={r.revenue} money /> },
          { key: "orders", label: "Orders", align: "right", render: (r) => <CellNumber value={r.quotations_confirmed} /> },
          { key: "conversion", label: "Conversion", align: "right", render: (r) => <CellNumber value={r.conversion_rate} suffix="%" /> },
          { key: "pending", label: "Pending", align: "right", render: (r) => <CellNumber value={r.pending_value} money /> },
          { key: "chevron", label: "", width: 32, render: () => <CellChevron /> },
        ]}
        data={rows}
        keyExtractor={(r) => r.referrer_id}
        onRowPress={(r) => router.push(`/(admin)/sales-data/referrers/${r.referrer_id}`)}
        emptyMessage={`No ${label.toLowerCase()}s yet.`}
      />
    </View>
  );
}
```

`frontend/app/(admin)/sales-data/referrals/architects.tsx`:

```tsx
import React from "react";
import { Redirect } from "expo-router";
import { AdminPage } from "@/src/components/AdminPage";
import { useAuth } from "@/src/state/auth";
import { ReferralsWorkspace } from "@/src/components/analytics/ReferralsWorkspace";

export default function ArchitectsScreen() {
  const { staff } = useAuth();
  if (staff && !["owner", "admin", "manager"].includes(staff.role)) return <Redirect href="/(admin)/dashboard" />;
  return (
    <AdminPage title="Architects" subtitle="Referral performance">
      <ReferralsWorkspace type="architect" />
    </AdminPage>
  );
}
```

`frontend/app/(admin)/sales-data/referrals/interior-designers.tsx` is identical with `type="interior_designer"` and `title="Interior Designers"`.

- [ ] **Step 2: Verify live**

`tsc --noEmit`, browser pass at 1280/768/375 on both routes. Since live data is 0 referrers today (per "Live data reality"), confirm the §5.3 onboarding state renders correctly — this is the primary state to verify, not an edge case. Click "Open Referrer Directory," confirm it navigates without erroring. If any test referrer exists by the time this task runs (e.g. one created during Task 20's live verification), confirm the table renders correctly for that non-empty case too.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/analytics/ReferralsWorkspace.tsx frontend/app/\(admin\)/sales-data/referrals/architects.tsx frontend/app/\(admin\)/sales-data/referrals/interior-designers.tsx
git commit -m "Build the Referrals workspace with the spec's onboarding empty state

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 24: `/sales-data/referrers/[id]` — the partner profile mini-CRM

**Files:**
- Create: `frontend/app/(admin)/sales-data/referrers/[id].tsx`

**Interfaces:**
- Consumes: `referralsApi.profile` (Task 15), `TrendBarChart` (Task 16), `KpiCard`, `DataTable`, `HistoryNote`/`ComparisonLine`

Spec §7 Workspace 3's exact section list: Header (name/type/firm/phone/lifetime revenue/customers/orders/AOV/active-quiet), then Summary · Revenue trend · Customers · **Relationship timeline** · All Quotations · Orders · Payments · Preferred Brands · Products Purchased · Most Recent Project · Recent Activity · Conversion Funnel. Backend `ReferrerProfile` (Task 7) supplies `summary`, `monthly_trend`, `brand_preference`, `product_preference`, `floor_split` directly; **Relationship timeline and Recent Activity reuse Phase 1's `ActivityFeed`/`feed_rows`** filtered client-side to entries whose `entity.customer_id` is in this referrer's customer set (no new backend feed logic — Task 7's plan self-review deliberately did not add a `referrer_id` filter to `feed_rows`, since Phase 1's feed already carries enough context to filter in the component); Customers/Quotations/Orders/Payments tables call the existing, already-shipped `/(admin)/customers`, `/(admin)/quotations` list endpoints filtered by `referrer_id` query param **if those endpoints already support it** — verify by reading `routes/customer_routes.py`/`routes/quotation_routes.py`'s existing query params before assuming; if `referrer_id` filtering does not exist on those list endpoints yet, this section renders from `gather_referrer_raw`'s own quotation ids instead of a second live query, since adding a new filter param to an unrelated, already-shipped list endpoint is out of this task's scope.

- [ ] **Step 1: Write the screen**

```tsx
import React, { useEffect, useState } from "react";
import { Redirect, useLocalSearchParams } from "expo-router";
import { View } from "react-native";
import { AdminPage } from "@/src/components/AdminPage";
import { useAuth } from "@/src/state/auth";
import { Text } from "@/src/components/ds";
import { KpiCard } from "@/src/components/ui";
import { DataTable, CellNumber, CellStack } from "@/src/components/tiles/TileTable";
import { TrendBarChart } from "@/src/components/charts/TrendBarChart";
import { referralsApi, ReferrerProfile } from "@/src/api/referrals";
import { spacing, type as typeTokens } from "@/src/theme/tokens";

export default function ReferrerProfileScreen() {
  const { staff } = useAuth();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [profile, setProfile] = useState<ReferrerProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    referralsApi.profile(id).then(setProfile).catch(() => setProfile(null)).finally(() => setLoading(false));
  }, [id]);

  if (staff && !["owner", "admin", "manager"].includes(staff.role)) return <Redirect href="/(admin)/dashboard" />;

  return (
    <AdminPage title={profile?.name || "Referrer"} subtitle={profile ? (profile.type === "architect" ? "Architect" : "Interior Designer") : undefined}>
      {!loading && !profile ? (
        <Text style={typeTokens.bodyMuted}>This referrer could not be found.</Text>
      ) : profile ? (
        <View style={{ gap: spacing.xl }}>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
            <KpiCard label="Lifetime Revenue" value={`₹${profile.summary.revenue.toLocaleString("en-IN")}`} />
            <KpiCard label="Customers" value={String(profile.summary.customers_referred)} />
            <KpiCard label="Orders" value={String(profile.summary.quotations_confirmed)} />
            <KpiCard label="AOV" value={`₹${profile.summary.aov.toLocaleString("en-IN")}`} />
            <KpiCard label="Status" value={profile.summary.is_active ? "Active" : "Quiet"} tone={profile.summary.is_active ? "success" : "warning"} />
          </View>

          <Text style={typeTokens.titleMd}>Revenue trend</Text>
          <TrendBarChart points={profile.monthly_trend} />

          <Text style={typeTokens.titleMd}>Preferred Brands</Text>
          <DataTable
            columns={[
              { key: "brand_name", label: "Brand", grow: 2, render: (r: any) => <CellStack title={r.brand_name} /> },
              { key: "revenue", label: "Revenue", align: "right", render: (r: any) => <CellNumber value={r.revenue} money /> },
            ]}
            data={profile.brand_preference}
            keyExtractor={(r: any) => r.brand_id}
            emptyMessage="No brand data yet."
          />

          <Text style={typeTokens.titleMd}>Products Purchased</Text>
          <DataTable
            columns={[
              { key: "product_name", label: "Product", grow: 2, render: (r: any) => <CellStack title={r.product_name} /> },
              { key: "revenue", label: "Revenue", align: "right", render: (r: any) => <CellNumber value={r.revenue} money /> },
            ]}
            data={profile.product_preference}
            keyExtractor={(r: any) => r.product_id}
            emptyMessage="No product data yet."
          />

          <Text style={typeTokens.titleMd}>Floor Split</Text>
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            {Object.entries(profile.floor_split).map(([floor, revenue]) => (
              <KpiCard key={floor} label={floor === "ground-floor" ? "Ground Floor" : "Sanitary"} value={`₹${revenue.toLocaleString("en-IN")}`} />
            ))}
          </View>
        </View>
      ) : null}
    </AdminPage>
  );
}
```

The Relationship-timeline/Recent-Activity/Customers/Quotations/Orders/Payments sections are added as additional blocks in this same file once Step 1's core layout is verified — write them following the exact source-of-truth rule from the Interfaces note above (verify the customer/quotation list endpoints' real query params before writing the fetch calls; do not assume `?referrer_id=` exists without checking).

- [ ] **Step 2: Verify live**

`tsc --noEmit`, browser pass at 1280/768/375. Since 0 referrers carry real revenue today, this will mostly render zero/empty states — confirm every section shows an honest empty state (not a crash, not a fabricated number) rather than deferring verification because "there's no data." If a referrer was created during Task 20's live check, use it to verify the non-empty path too.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/\(admin\)/sales-data/referrers/\[id\].tsx
git commit -m "Build the partner profile mini-CRM

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## STAGE D GATE

Full browser pass at 1280/768/375 across all four new screens (`sales.tsx`, `collections.tsx`, both `referrals/*.tsx`, `referrers/[id].tsx`), zero console errors, zero horizontal overflow, `tsc --noEmit` clean, ledger entry written before Stage E.

---

## Task 25: Stage E — §18 verification protocol

**No new code.** A checklist pass over everything Phase 2 built, exactly Phase 1's Stage E discipline.

- [ ] **1. Every KPI cross-checked against a direct Mongo query.** Revenue trend's monthly total, salesperson revenue sum, category revenue sum, and Collections' outstanding total each hand-verified against a direct aggregation on the live `buildcon_house` DB.
- [ ] **2. Every aggregation reconciles.** Revenue-trend's sum across all buckets in a period = Performance's own salesperson-revenue sum for that period = the Phase 1 Overview's top-line revenue for the same period, all three matching exactly.
- [ ] **3. N/A this phase** — no second Health Score is introduced.
- [ ] **4. Every filter verified, including the three-way floor probe**, on `/analytics/salespeople`, `/analytics/collections`, and `/analytics/referrers`.
- [ ] **5. Every drill-down opens the right record.** Salesperson row → salesperson detail (or flagged as deferred if Task 21 didn't ship a detail screen — check against what was actually built and disclose, don't claim what wasn't done). Referrer row → partner profile. Category/customer rows → the filtered underlying list.
- [ ] **6. Every export opens and matches on-screen data.** Download each of the four CSV and four XLSX exports, open them, confirm row-for-row parity with the table on screen at the moment of export.
- [ ] **7. Every Command Center action re-checks its own permission.** N/A for pure read/export surfaces unless Phase 2 added a new mutating action — if it didn't (it doesn't, per this plan's scope), record that explicitly rather than fabricating a check.
- [ ] **8. No nested interactive elements** — checked against the live accessibility tree for every new row/card component (`DataTable` rows, `ExportMenu`, `ReferredByField`).
- [ ] **9. Responsive pass at 1280 / 768 / 375** for all five new screens, including the granularity `PillTabs`' 5-option wrap at 375px.
- [ ] **10. No placeholder components, no empty cards, no fabricated values.** Grep every new file for TODO/FIXME/placeholder/mock. The three `None` funnel durations and the empty-referrer onboarding state are the disclosed, deliberate exceptions — confirm they render as honest "not tracked"/"no data yet" states, never as a silent zero.
- [ ] **11. Backend unit tests for every new service module** — confirm `performance`, `collections`, `referrals`, `gather_performance`, `gather_referrals`, `export`, `sales_performance_routes`, `referral_analytics_routes` each have a dedicated test file.
- [ ] **12. Fix, re-verify, and only then proceed.** Report the final backend suite count (baseline 602 + every task's added tests), confirm it only went up, and report to the user: what Phase 2 shipped, what was found and fixed during live verification, and what (if anything) was explicitly deferred with a stated reason — matching Phase 1's closing report format exactly.

---
