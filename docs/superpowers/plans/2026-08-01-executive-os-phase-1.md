# Executive Operating System — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Executive Overview as a working operating system — Business Health Score, Morning Brief, Attention Center, Opportunity Center, Activity Feed, the Command Center action model, and Today's Priorities — with every number sourced from the Phase 0 analytics layer.

**Architecture:** Three layers, strictly separated. (1) **Pure rule modules** in `backend/services/analytics/` take already-fetched rows and return `ActionRow` objects — no database access, so every rule is unit-testable and no rule can invent its own query. (2) A **gather layer** per surface performs the Mongo reads through Phase 0's `build_match`, so floor scoping and date fields are never re-implemented. (3) **One HTTP router** exposes the surfaces, each wrapped in Phase 0's `cache.cached`. The frontend consumes them through shared components in `src/components/analytics/`; Attention, Opportunity, Today's Priorities and the Morning Brief's recommended actions all render the *same* `ActionRow` shape from the *same* rules, so they can never contradict each other.

**Tech Stack:** FastAPI · MongoDB (motor) · Pydantic · pytest · Expo / React Native Web · expo-router · react-native-svg

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-01-executive-operating-system-design.md` is frozen. Do not add a KPI, card, rule, or drill-down that is not in it. Adding a seventh element above the fold requires amending §7's contract first.
- **Every number comes from the Phase 0 analytics layer.** `services/analytics/{filters,periods,metrics,cache}.py` already exist and are tested. No route may build its own `$match`, its own revenue `$group`, or its own comparison. Revenue dates by `ordered_at`; line revenue sums `items.net_amount`.
- **No fabricated values.** A missing comparison returns a `history_state` (`ok` / `no_prior_period` / `insufficient_history`), never `+100%` or `0%`. A rule whose comparison window has no history is **suppressed**, not fired on a fabricated delta.
- **One rule set.** Overview, Today's Priorities and the Morning Brief's recommended actions read the same `attention.py` / `opportunity.py` rules. A rule that fires in one must fire in all.
- **All thresholds live in one constant block** in `attention.py`. Never inline a threshold at a rule site.
- **Permissions are re-checked per action.** The analytics gate (`owner`/`admin`/`manager`) must never widen access to an underlying operation. Actions the caller lacks rights for are **hidden**, not shown-and-failing.
- **No nested interactive elements.** Action rows must not set `accessibilityRole="button"` on an outer `Pressable` that contains buttons (the 2026-07-24 `QueueRow` bug). Verified against the live accessibility tree, not by eye.
- **44px minimum tap target** on every control.
- **8pt spacing system**, large readable typography, zero layout shift, zero console warnings, responsive at 1280 / 768 / 375, keyboard accessible.
- **No placeholder UI, no mock data, no duplicated components, no duplicated business logic.** Every card renders the owner question it answers, in small type under the value.
- **Backend tests:** `cd backend && ./.venv/bin/python -m pytest tests/unit -v`. Baseline entering Phase 1: **482 passed, 0 failures**. It may never go down.
- **Frontend has no test framework.** Verification is `npx tsc --noEmit` (currently fully clean — any error is new) plus a live browser pass.
- **The shared backend on `:8010` does not auto-reload** and may be in use by another session. Ask before restarting it.
- Python is `backend/.venv/bin/python` (3.14). Never a system python.

**Deviation from the Phase 0 plan's style, deliberate:** that plan carried full source for every module, and six of those blocks shipped real defects (an unrunnable `await` in a genexp, a backfill that would have zeroed legacy revenue, a `ValueError` on calendar shifts). Verbatim plan code was not where the value was — the *tests* and the *contracts* were. This plan therefore specifies complete test code and exact interfaces for every task, plus full code only where the logic is non-obvious, and requires the implementer to write the straightforward code against those tests.

---

## Live data reality (probed 2026-08-01, do not re-derive)

- `activity_events` uses field **`event_type`**, not `type`. 2,456 rows, 49 distinct types. The two loudest are `product.image_uploaded` (890) and `user.login` (497) — 57% noise, exactly as §13.1 says.
- **The spec's allowlist names three event types that do not exist under those names.** Real values: dispatch completion is **`purchase.chalan_dispatched`** (4 rows) and **`dispatch.created`** (25) / **`dispatch.delivered`** (2); godown receipt is **`purchase.chalan_godown_received`** (1) and **`item.moved_to_godown`** (15); the walk-in → quotation event is **`walkin.quotation_created`** (3), there is no `walkin.selection_completed`. Map to the real names.
- `payment.recorded` is emitted by `routes/payment_routes.py:376` but **has zero rows** — the 31 live payments were seeded, not recorded through the route. The feed must handle a legitimately empty payment stream.
- Event docs carry `entity_type`, `entity_id`, `quotation_id`, `customer_id`, `purchase_id`, `actor_name`, `summary`, `payload`, `created_at`. **No `floor_id`** — derive by joining the referenced entity (§13.1).
- `payments.status` ∈ {`completed`: 8, `pending`: 23}. Only `completed` counts as collected.
- `followups` carries `value`, `due_at`, `status`, `priority_score`, `priority_level`, `reason_factors`, `customer_tier`, `last_contacted_at`, `assigned_to`, `suggested_channel`, `category`, `quotation_id`, `customer_phone`, `floor_id`.
- `walkins` carries `interested_products`, `budget`, `status`, `visited_at`, `selection_quotation_id`, `salesperson_id`, `floor_id`, `is_deleted`.
- `followup_engine.score_followup(value, days_since_contact, urgency_pts, tier) -> (score:int, level:str)` where level ∈ {`critical`≥80, `high`≥60, `medium`≥35, `low`}. `reason_factors_for(value, days_since_contact, urgency_bullet, tier) -> list[str]`. Reuse both; do not invent a second priority scale.
- Ordered revenue is ₹39,77,337.00 over 35 orders across 16 customers; outstanding ₹38,32,023.00 (collected ₹1,45,314.00). 10 product ids on ordered quotations (₹5,44,910) resolve to no product doc — the known reimport orphan gap. Surfaces must not crash on it and must not silently drop it.

---

## File Structure

**Backend — created**

| File | Responsibility |
|---|---|
| `backend/services/analytics/rows.py` | The one `ActionRow` shape + `Action` ids shared by Attention, Opportunity, Priorities, Brief |
| `backend/services/analytics/attention.py` | The single threshold constant block + every §9 attention rule (pure) |
| `backend/services/analytics/opportunity.py` | Every §10 opportunity rule (pure) |
| `backend/services/analytics/health.py` | §8 Business Health Score, renormalizing over available signals |
| `backend/services/analytics/feed.py` | §13.1 executive allowlist, floor derivation by entity join, value joins |
| `backend/services/analytics/brief.py` | §11 Morning Brief composition (no new rules) |
| `backend/services/analytics/gather.py` | The only place Phase 1 surfaces read Mongo; builds rule inputs via `build_match` |
| `backend/routes/executive_overview_routes.py` | `/api/analytics/{overview,health,attention,opportunities,brief,feed,today}` |

**Backend — modified**

| File | Change |
|---|---|
| `backend/services/domain_outbox.py` | Call `cache.bump()` on the writes that change analytics (Phase 0's deferred wiring) |
| `backend/server.py` | Register the new router |

**Frontend — created**

| File | Responsibility |
|---|---|
| `frontend/src/components/analytics/StateViews.tsx` | loading · empty · `no_prior_period` · `insufficient_history` — one implementation |
| `frontend/src/components/analytics/KpiCard.tsx` | value · comparison · delta · sparkline · **the question** · drill-down |
| `frontend/src/components/analytics/KpiRow.tsx` | the KPI strip |
| `frontend/src/components/analytics/HealthScoreCard.tsx` | score · band · direction · expandable component breakdown |
| `frontend/src/components/analytics/MorningBrief.tsx` | §11 |
| `frontend/src/components/analytics/ActionRow.tsx` | §14.1 context fields + permission-filtered actions, `HoverCard`-based |
| `frontend/src/components/analytics/AttentionList.tsx` | ranked attention rows (renders `ActionRow`) |
| `frontend/src/components/analytics/OpportunityList.tsx` | ranked opportunity rows (renders `ActionRow`) |
| `frontend/src/components/analytics/ActivityFeed.tsx` | §13.1 grouped Today / Yesterday / This Week |
| `frontend/src/components/analytics/MoneyBlockedCard.tsx` | ₹-first operational summary |
| `frontend/src/api/executive.ts` | typed client for the new endpoints |
| `frontend/app/(admin)/sales-data/today.tsx` | §14.2 Today's Priorities |

**Frontend — modified**

| File | Change |
|---|---|
| `frontend/app/(admin)/sales-data/executive.tsx` | Replaced by the new Executive Overview (§7 Workspace 1 above-the-fold contract) |
| `frontend/app/(admin)/sales-data/index.tsx` | Redirect to `/sales-data/executive` (legacy screen code stays until Phase 6) |

**Execution staging** — a stage is not done until implementation, full test run, live-database verification, browser verification, visual-quality confirmation, and a ledger entry are all complete.

| Stage | Tasks | Gate |
|---|---|---|
| **A** | 1–5 (rows, attention, opportunity, health, feed) | pure rules, unit tests only |
| **B** | 6–8 (gather, routes, cache wiring) | live-database verification of every endpoint |
| **C** | 9–12 (shared components) | `tsc` clean + component render check |
| **D** | 13–15 (Overview, Today's Priorities, routing) | full browser pass at 1280/768/375 |
| **E** | 16 (§18 verification protocol) | all 12 points |

---

## Task 1: `rows.py` — the one action-row shape

Attention, Opportunity, Today's Priorities and the Brief's recommended actions must be the same object, or they will drift.

**Files:**
- Create: `backend/services/analytics/rows.py`
- Test: `backend/tests/unit/test_analytics_rows.py`

**Interfaces:**
- Produces:
  - `Action = Literal["open","call","whatsapp","schedule_followup","assign","record_payment","send_reminder","open_customer","open_po"]`
  - `ACTION_ROLES: dict[Action, tuple[str, ...]]` — minimum role each action's underlying endpoint requires
  - `@dataclass(frozen=True) ActionRow` with fields: `rule: str`, `kind: Literal["attention","opportunity"]`, `headline: str`, `impact: float`, `age_days: int | None`, `context: list[tuple[str, str]]`, `destination: str`, `actions: tuple[Action, ...]`, `entity: dict[str, str]`, `history_state: str = "ok"`
  - `row_dict(row: ActionRow, role: str) -> dict` — serializes, filtering `actions` to those the role may perform
  - `rank(rows: list[ActionRow]) -> list[ActionRow]` — by `impact` desc, then `age_days` desc, then `rule` (stable and total, so identical inputs always produce identical order)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_analytics_rows.py`:

```python
"""One row shape for every actionable surface. Actions are filtered by the
caller's real role — the analytics gate must never widen access to an
underlying operation (spec §14.1 rule 1)."""
from __future__ import annotations

from services.analytics.rows import ACTION_ROLES, ActionRow, rank, row_dict


def _row(**kw) -> ActionRow:
    base = dict(
        rule="quotation_stalled", kind="attention", headline="₹5.4L quotation pending 9 days",
        impact=540000.0, age_days=9, context=[("Customer", "JK Enterprises")],
        destination="/(admin)/quotations/q1", actions=("open", "call", "record_payment"),
        entity={"quotation_id": "q1", "phone": "+919999999999"},
    )
    base.update(kw)
    return ActionRow(**base)


def test_rows_rank_by_impact_desc():
    rows = [_row(impact=100.0), _row(impact=900.0), _row(impact=500.0)]
    assert [r.impact for r in rank(rows)] == [900.0, 500.0, 100.0]


def test_ties_break_by_age_then_rule_so_ordering_is_deterministic():
    a = _row(impact=100.0, age_days=2, rule="b_rule")
    b = _row(impact=100.0, age_days=9, rule="a_rule")
    c = _row(impact=100.0, age_days=9, rule="z_rule")
    assert [r.rule for r in rank([a, b, c])] == ["a_rule", "z_rule", "b_rule"]


def test_a_missing_age_never_crashes_the_sort():
    rows = [_row(impact=5.0, age_days=None), _row(impact=5.0, age_days=1)]
    assert len(rank(rows)) == 2


def test_owner_sees_every_action():
    assert row_dict(_row(), "owner")["actions"] == ["open", "call", "record_payment"]


def test_a_role_without_rights_does_not_see_the_action():
    # "manager" may read Sales Data but recording a payment is an accounts/admin
    # operation — it must be hidden, not shown and then failing.
    assert "record_payment" not in row_dict(_row(), "sales")["actions"]


def test_read_only_actions_are_available_to_every_analytics_role():
    for role in ("owner", "admin", "manager"):
        actions = row_dict(_row(), role)["actions"]
        assert "open" in actions and "call" in actions


def test_every_action_declares_its_roles():
    from typing import get_args
    from services.analytics.rows import Action
    for action in get_args(Action):
        assert ACTION_ROLES.get(action), f"{action} has no declared roles"


def test_serialization_carries_everything_the_ui_renders():
    d = row_dict(_row(), "owner")
    assert d["headline"] and d["impact"] == 540000.0 and d["age_days"] == 9
    assert d["context"] == [["Customer", "JK Enterprises"]] or d["context"] == [("Customer", "JK Enterprises")]
    assert d["destination"] == "/(admin)/quotations/q1"
    assert d["entity"]["quotation_id"] == "q1"
    assert d["history_state"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_rows.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics.rows'`

- [ ] **Step 3: Write the module**

Create `backend/services/analytics/rows.py`. Requirements the tests pin:

- `ACTION_ROLES` maps each action to the roles that may perform it, taken from the **existing** endpoints, not invented: `open`/`open_customer`/`open_po`/`call`/`whatsapp` are read/dial operations available to `owner`,`admin`,`manager`; `schedule_followup`/`assign`/`send_reminder` follow `routes/followup_routes.py`'s own `require_min_role("sales")` (so `owner`,`admin`,`manager`,`sales`); `record_payment` follows `routes/payment_routes.py`'s gate — read that file and copy its real requirement rather than guessing.
- `rank` sorts by `(-impact, -(age_days or 0), rule)`. Use an explicit key function; `age_days` may be `None`.
- `row_dict` returns plain JSON-safe types and filters `actions` through `ACTION_ROLES`.

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_rows.py -v`
Expected: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/rows.py backend/tests/unit/test_analytics_rows.py
git commit -m "Add the shared executive action-row shape

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: `attention.py` — thresholds and every §9 rule

**Files:**
- Create: `backend/services/analytics/attention.py`
- Test: `backend/tests/unit/test_analytics_attention.py`

**Interfaces:**
- Consumes: `ActionRow`, `rank` (Task 1); `periods.compare`, `HISTORY_INSUFFICIENT` (Phase 0)
- Produces:
  - A single `THRESHOLDS` constant block holding every value in §9's two tables
  - One pure function per rule, each `(...rows, now: datetime, thresholds: dict) -> list[ActionRow]`:
    `quotation_stalled`, `payment_overdue`, `dispatch_waiting`, `release_stuck`, `followup_overdue`, `salesperson_inactive`, `supplier_delayed`, `brand_declining`, `referrer_quiet`
  - `attention_rows(data: AttentionInput) -> list[ActionRow]` — runs every rule and returns them ranked
  - `@dataclass AttentionInput` carrying the already-fetched lists the rules need

**Why pure:** every rule is unit-testable without Mongo, and the gather layer (Task 6) stays the only thing that queries. A rule that fetches its own data would bypass `build_match` and its floor scoping.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_analytics_attention.py`:

```python
"""Only problems, each with a ₹ impact and a destination. Rules whose
comparison has no history are suppressed, never fired on a fabricated delta."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.analytics import attention

NOW = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def test_every_threshold_in_the_spec_has_a_constant():
    for key in (
        "QUOTATION_STALE_DAYS", "QUOTATION_HIGH_VALUE", "PAYMENT_OVERDUE_DAYS",
        "DISPATCH_WAITING_DAYS", "RELEASE_STUCK_DAYS", "SALESPERSON_INACTIVE_DAYS",
        "SUPPLIER_DELAY_DAYS", "BRAND_DECLINE_PCT", "REFERRER_QUIET_DAYS",
        "CUSTOMER_INACTIVE_DAYS", "BRAND_GROWTH_PCT", "PARTNER_UNTOUCHED_DAYS",
        "APPROVED_NOT_ORDERED_DAYS", "WALKIN_UNQUOTED_DAYS",
    ):
        assert key in attention.THRESHOLDS, f"{key} missing from the one constant block"


def test_the_spec_starting_values_are_the_defaults():
    t = attention.THRESHOLDS
    assert t["QUOTATION_STALE_DAYS"] == 7
    assert t["QUOTATION_HIGH_VALUE"] == 100000
    assert t["DISPATCH_WAITING_DAYS"] == 3
    assert t["RELEASE_STUCK_DAYS"] == 5
    assert t["SALESPERSON_INACTIVE_DAYS"] == 5
    assert t["BRAND_DECLINE_PCT"] == 25
    assert t["REFERRER_QUIET_DAYS"] == 60
    assert t["CUSTOMER_INACTIVE_DAYS"] == 180


def test_a_high_value_quotation_older_than_the_threshold_fires():
    quotations = [{
        "id": "q1", "number": "FQ-1", "status": "sent", "grand_total": 540000.0,
        "customer_name": "JK Enterprises", "customer_id": "c1", "created_by_name": "Rahul",
        "updated_at": _iso(9), "created_at": _iso(9), "referrer_name": "ABC Architects",
    }]
    rows = attention.quotation_stalled(quotations, now=NOW, thresholds=attention.THRESHOLDS)
    assert len(rows) == 1
    assert rows[0].impact == 540000.0
    assert rows[0].age_days == 9
    assert rows[0].destination == "/(admin)/quotations/q1"
    assert "open" in rows[0].actions and "call" in rows[0].actions


def test_a_fresh_quotation_does_not_fire():
    quotations = [{"id": "q1", "status": "sent", "grand_total": 540000.0, "created_at": _iso(1)}]
    assert attention.quotation_stalled(quotations, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_a_low_value_stale_quotation_does_not_fire():
    quotations = [{"id": "q1", "status": "sent", "grand_total": 5000.0, "created_at": _iso(30)}]
    assert attention.quotation_stalled(quotations, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_an_ordered_quotation_is_not_a_stalled_quotation():
    quotations = [{"id": "q1", "status": "ordered", "grand_total": 540000.0, "created_at": _iso(30)}]
    assert attention.quotation_stalled(quotations, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_payment_overdue_uses_the_owner_declared_terms():
    orders = [{
        "id": "q1", "number": "FQ-1", "customer_id": "c1", "customer_name": "Menon",
        "ordered_at": _iso(45), "grand_total": 300000.0, "collected": 60000.0,
    }]
    t = {**attention.THRESHOLDS, "PAYMENT_OVERDUE_DAYS": 30}
    rows = attention.payment_overdue(orders, now=NOW, thresholds=t)
    assert len(rows) == 1
    assert rows[0].impact == 240000.0          # outstanding, not order value
    assert rows[0].destination == "/(admin)/payments"


def test_a_fully_collected_order_is_never_overdue():
    orders = [{"id": "q1", "ordered_at": _iso(90), "grand_total": 300000.0, "collected": 300000.0}]
    assert attention.payment_overdue(orders, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_an_order_inside_the_terms_window_is_not_overdue():
    orders = [{"id": "q1", "ordered_at": _iso(10), "grand_total": 300000.0, "collected": 0.0}]
    t = {**attention.THRESHOLDS, "PAYMENT_OVERDUE_DAYS": 30}
    assert attention.payment_overdue(orders, now=NOW, thresholds=t) == []


def test_followup_overdue_fires_on_due_date_and_carries_its_value():
    followups = [{
        "id": "f1", "status": "open", "due_at": _iso(4), "value": 120000.0,
        "customer_name": "Ravi", "customer_id": "c1", "customer_phone": "+919000000000",
    }]
    rows = attention.followup_overdue(followups, now=NOW, thresholds=attention.THRESHOLDS)
    assert len(rows) == 1 and rows[0].impact == 120000.0
    assert rows[0].destination == "/(admin)/followups"
    assert "whatsapp" in rows[0].actions


def test_a_completed_followup_never_fires():
    followups = [{"id": "f1", "status": "completed", "due_at": _iso(40), "value": 120000.0}]
    assert attention.followup_overdue(followups, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_brand_decline_is_suppressed_when_there_is_no_prior_period():
    brands = [{"brand_id": "b1", "brand_name": "Dimore", "revenue": 100000.0, "previous": 0.0, "prior_window_exists": False}]
    assert attention.brand_declining(brands, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_brand_decline_fires_on_a_real_drop_and_reports_the_delta():
    brands = [{"brand_id": "b1", "brand_name": "Dimore", "revenue": 300000.0, "previous": 1000000.0, "prior_window_exists": True}]
    rows = attention.brand_declining(brands, now=NOW, thresholds=attention.THRESHOLDS)
    assert len(rows) == 1
    assert rows[0].impact == 700000.0
    assert rows[0].destination.startswith("/(admin)/sales-data/brands")


def test_a_small_brand_dip_does_not_fire():
    brands = [{"brand_id": "b1", "brand_name": "Dimore", "revenue": 900000.0, "previous": 1000000.0, "prior_window_exists": True}]
    assert attention.brand_declining(brands, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_supplier_delay_fires_past_expected_delivery():
    pos = [{"id": "po1", "number": "FPO-1", "supplier_name": "Dimore", "supplier_id": "s1",
            "expected_delivery_at": _iso(6), "status": "ordered", "total": 480000.0}]
    rows = attention.supplier_delayed(pos, now=NOW, thresholds=attention.THRESHOLDS)
    assert len(rows) == 1 and rows[0].age_days == 6
    assert rows[0].destination == "/(admin)/purchases"


def test_a_received_purchase_order_is_never_delayed():
    pos = [{"id": "po1", "expected_delivery_at": _iso(30), "status": "fully_received", "total": 480000.0}]
    assert attention.supplier_delayed(pos, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_attention_rows_returns_every_rule_ranked_by_impact():
    data = attention.AttentionInput(
        quotations=[{"id": "q1", "status": "sent", "grand_total": 540000.0, "created_at": _iso(9), "customer_name": "JK"}],
        orders=[{"id": "q2", "ordered_at": _iso(45), "grand_total": 300000.0, "collected": 0.0, "customer_name": "Menon"}],
        followups=[], ready_items=[], unreleased_items=[], salespeople=[],
        purchase_orders=[], brands=[], referrers=[],
    )
    rows = attention.attention_rows(data, now=NOW)
    assert [r.impact for r in rows] == sorted([r.impact for r in rows], reverse=True)
    assert {r.rule for r in rows} == {"quotation_stalled", "payment_overdue"}


def test_no_rule_ever_returns_a_row_with_zero_impact():
    """A row with no ₹ impact cannot be ranked and gives the owner nothing to
    weigh — the rule should not have fired."""
    data = attention.AttentionInput(
        quotations=[{"id": "q1", "status": "sent", "grand_total": 0.0, "created_at": _iso(30)}],
        orders=[{"id": "q2", "ordered_at": _iso(90), "grand_total": 0.0, "collected": 0.0}],
        followups=[{"id": "f1", "status": "open", "due_at": _iso(9), "value": 0.0}],
        ready_items=[], unreleased_items=[], salespeople=[], purchase_orders=[], brands=[], referrers=[],
    )
    assert attention.attention_rows(data, now=NOW) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_attention.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics.attention'`

- [ ] **Step 3: Write the constant block**

```python
THRESHOLDS: dict[str, float] = {
    "QUOTATION_STALE_DAYS": 7,
    "QUOTATION_HIGH_VALUE": 100000,
    "PAYMENT_OVERDUE_DAYS": 30,      # overridden per-request from settings.analytics_targets
    "DISPATCH_WAITING_DAYS": 3,
    "RELEASE_STUCK_DAYS": 5,
    "SALESPERSON_INACTIVE_DAYS": 5,
    "SUPPLIER_DELAY_DAYS": 0,
    "BRAND_DECLINE_PCT": 25,
    "REFERRER_QUIET_DAYS": 60,
    "CUSTOMER_INACTIVE_DAYS": 180,
    "BRAND_GROWTH_PCT": 25,
    "PARTNER_UNTOUCHED_DAYS": 14,
    "APPROVED_NOT_ORDERED_DAYS": 3,
    "WALKIN_UNQUOTED_DAYS": 14,
}
```

Every rule takes `thresholds: dict` and reads from it. **Never inline a number at a rule site** — the constant block is the feature.

- [ ] **Step 4: Write the rules**

Each rule is a pure function returning `list[ActionRow]`. Shared requirements the tests pin:

- Age is whole days between the relevant timestamp and `now`, computed by one shared `_age_days(iso, now)` helper that tolerates a missing or unparseable timestamp by returning `None` (and a rule with an unknown age does not fire on an age threshold).
- **A row is never emitted with `impact <= 0`.** Enforce this once, in `attention_rows`, and also return early per rule.
- `quotation_stalled`: status ∈ {`draft`,`sent`,`approved`}, `grand_total >= QUOTATION_HIGH_VALUE`, age from `created_at` > `QUOTATION_STALE_DAYS`. Impact = `grand_total`. Actions: `open`, `call`, `whatsapp`, `schedule_followup`, `assign`.
- `payment_overdue`: outstanding = `grand_total - collected` > 0 and days since `ordered_at` > `PAYMENT_OVERDUE_DAYS`. Impact = outstanding. Actions: `call`, `send_reminder`, `open_customer`, `record_payment`.
- `dispatch_waiting`: ready, undispatched, age > `DISPATCH_WAITING_DAYS`. Impact = order value. Destination `/(admin)/tiles/orders`.
- `release_stuck`: unreleased line, age > `RELEASE_STUCK_DAYS`. Impact = line value.
- `followup_overdue`: `status == "open"` and `due_at < now`. Impact = `value`. Actions include `whatsapp` and `call`.
- `salesperson_inactive`: no walk-in / quotation / follow-up within `SALESPERSON_INACTIVE_DAYS`. Impact = their open pipeline value.
- `supplier_delayed`: `expected_delivery_at` more than `SUPPLIER_DELAY_DAYS` in the past **and** status not in the terminal received/cancelled set. Impact = PO value.
- `brand_declining` / `referrer_quiet`: comparison rules. Each input row carries `prior_window_exists`; when it is `False`, **suppress the row entirely** (do not emit with `history_state`) — §9 says suppressed, not fired.

- [ ] **Step 5: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_attention.py -v`
Expected: PASS — 18 passed

- [ ] **Step 6: Commit**

```bash
git add backend/services/analytics/attention.py backend/tests/unit/test_analytics_attention.py
git commit -m "Add the Attention Center rules and the single threshold block

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: `opportunity.py` — every §10 rule

**Files:**
- Create: `backend/services/analytics/opportunity.py`
- Test: `backend/tests/unit/test_analytics_opportunity.py`

**Interfaces:**
- Consumes: `ActionRow`, `rank` (Task 1); `THRESHOLDS` (Task 2 — the same block, never a second copy)
- Produces: `partner_untouched`, `brand_growing`, `customer_likely_to_reorder`, `walkin_unquoted`, `approved_not_ordered`, `customer_gone_quiet`, `salesperson_underloaded`, and `opportunity_rows(data: OpportunityInput) -> list[ActionRow]`

**Explicitly out of scope for Phase 1:** §10's *Repeat-buyer cross-sell* rule needs frequently-bought-together data that no service computes yet. Do not stub it, do not fabricate it — omit the rule and record the omission in the ledger and in the module docstring.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_analytics_opportunity.py`:

```python
"""The mirror of Attention: where to grow. Same row shape, ranked by upside ₹,
same suppression rule for comparisons with no history."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.analytics import opportunity
from services.analytics.attention import THRESHOLDS

NOW = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def test_opportunity_rules_share_the_attention_threshold_block():
    # A second copy of these numbers is how two surfaces start disagreeing.
    assert opportunity.THRESHOLDS is THRESHOLDS


def test_partner_with_untouched_pipeline_fires():
    partners = [{
        "referrer_id": "r1", "referrer_name": "ABC Architects", "open_value": 1240000.0,
        "last_followup_at": _iso(21), "phone": "+919000000000",
    }]
    rows = opportunity.partner_untouched(partners, now=NOW, thresholds=THRESHOLDS)
    assert len(rows) == 1
    assert rows[0].impact == 1240000.0
    assert rows[0].kind == "opportunity"
    assert "schedule_followup" in rows[0].actions


def test_a_recently_contacted_partner_does_not_fire():
    partners = [{"referrer_id": "r1", "open_value": 1240000.0, "last_followup_at": _iso(2)}]
    assert opportunity.partner_untouched(partners, now=NOW, thresholds=THRESHOLDS) == []


def test_a_partner_with_no_open_pipeline_does_not_fire():
    partners = [{"referrer_id": "r1", "open_value": 0.0, "last_followup_at": _iso(90)}]
    assert opportunity.partner_untouched(partners, now=NOW, thresholds=THRESHOLDS) == []


def test_fast_growing_brand_fires_with_the_revenue_delta_as_upside():
    brands = [{"brand_id": "b1", "brand_name": "Qutone", "revenue": 900000.0, "previous": 400000.0, "prior_window_exists": True}]
    rows = opportunity.brand_growing(brands, now=NOW, thresholds=THRESHOLDS)
    assert len(rows) == 1 and rows[0].impact == 500000.0


def test_brand_growth_without_a_prior_window_is_suppressed():
    brands = [{"brand_id": "b1", "brand_name": "Qutone", "revenue": 900000.0, "previous": 0.0, "prior_window_exists": False}]
    assert opportunity.brand_growing(brands, now=NOW, thresholds=THRESHOLDS) == []


def test_approved_quotation_not_ordered_fires_after_the_threshold():
    quotations = [{"id": "q1", "number": "FQ-9", "status": "approved", "grand_total": 250000.0,
                   "customer_name": "Ravi", "customer_id": "c1", "updated_at": _iso(5)}]
    rows = opportunity.approved_not_ordered(quotations, now=NOW, thresholds=THRESHOLDS)
    assert len(rows) == 1 and rows[0].destination == "/(admin)/quotations/q1"


def test_an_approved_quotation_inside_the_grace_window_does_not_fire():
    quotations = [{"id": "q1", "status": "approved", "grand_total": 250000.0, "updated_at": _iso(1)}]
    assert opportunity.approved_not_ordered(quotations, now=NOW, thresholds=THRESHOLDS) == []


def test_high_intent_walkin_not_quoted_fires_inside_the_window_only():
    fresh = [{"id": "w1", "customer_name": "New Buyer", "customer_id": "c9", "budget": 300000.0,
              "interested_products": ["tiles"], "visited_at": _iso(3), "selection_quotation_id": None}]
    stale = [{**fresh[0], "id": "w2", "visited_at": _iso(30)}]
    assert len(opportunity.walkin_unquoted(fresh, now=NOW, thresholds=THRESHOLDS)) == 1
    assert opportunity.walkin_unquoted(stale, now=NOW, thresholds=THRESHOLDS) == []


def test_a_walkin_that_already_has_a_quotation_does_not_fire():
    walkins = [{"id": "w1", "budget": 300000.0, "interested_products": ["tiles"],
                "visited_at": _iso(3), "selection_quotation_id": "q1"}]
    assert opportunity.walkin_unquoted(walkins, now=NOW, thresholds=THRESHOLDS) == []


def test_top_customer_gone_quiet_fires_past_the_inactive_threshold():
    customers = [{"customer_id": "c1", "customer_name": "JK", "last_order_at": _iso(200),
                  "average_order": 180000.0, "lifetime_revenue": 2400000.0, "phone": "+919000000000"}]
    rows = opportunity.customer_gone_quiet(customers, now=NOW, thresholds=THRESHOLDS)
    assert len(rows) == 1 and rows[0].impact == 180000.0
    assert rows[0].destination == "/(admin)/customers/c1"


def test_opportunity_rows_are_ranked_by_upside():
    data = opportunity.OpportunityInput(
        partners=[{"referrer_id": "r1", "referrer_name": "ABC", "open_value": 100000.0, "last_followup_at": _iso(30)}],
        brands=[{"brand_id": "b1", "brand_name": "Qutone", "revenue": 900000.0, "previous": 400000.0, "prior_window_exists": True}],
        quotations=[], walkins=[], customers=[], salespeople=[],
    )
    rows = opportunity.opportunity_rows(data, now=NOW)
    assert [r.impact for r in rows] == [500000.0, 100000.0]
    assert all(r.kind == "opportunity" for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_opportunity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics.opportunity'`

- [ ] **Step 3: Write the module**

Import `THRESHOLDS` from `attention` — `from services.analytics.attention import THRESHOLDS` — and re-export the same object (the first test asserts identity, not equality). Reuse the same `_age_days` helper by importing it rather than copying it.

Rule requirements beyond what the tests pin:
- `customer_likely_to_reorder`: order cadence due (days since last order > their historical mean gap) **and** no open quotation. Upside = their historical average order. Suppress when fewer than 2 historical orders — a cadence cannot be derived from one.
- `salesperson_underloaded`: highest conversion, fewest open quotations. Upside = their average order × capacity gap. Suppress when there are fewer than 2 salespeople to compare.

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_opportunity.py -v`
Expected: PASS — 12 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/opportunity.py backend/tests/unit/test_analytics_opportunity.py
git commit -m "Add the Opportunity Center rules

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: `health.py` — Business Health Score

**Files:**
- Create: `backend/services/analytics/health.py`
- Test: `backend/tests/unit/test_analytics_health.py`

**Interfaces:**
- Consumes: `AnalyticsTargets` (Phase 0 model), `periods.compare`
- Produces:
  - `@dataclass(frozen=True) Component` — `key`, `label`, `value` (0-100), `weight`, `rule`, `destination`
  - `COMPONENTS: tuple[...]` — the seven §8 definitions, weights included
  - `health_score(signals: dict[str, float | None], targets: AnalyticsTargets) -> dict` returning `{score, band, components, available, total, missing_signal_note}`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_analytics_health.py`:

```python
"""One number the owner can audit. Weights renormalize over available
components; a score is never computed from an invented benchmark."""
from __future__ import annotations

import pytest

from models import AnalyticsTargets
from services.analytics.health import COMPONENTS, health_score

ALL_SIGNALS = {
    "collection_health": 100.0,
    "overdue_money": 100.0,
    "pipeline_health": 100.0,
    "dispatch_health": 100.0,
    "followup_health": 100.0,
    "revenue_attainment": 100.0,
    "conversion_health": 100.0,
}


def test_the_seven_spec_components_exist_with_their_weights():
    weights = {c.key: c.weight for c in COMPONENTS}
    assert weights == {
        "collection_health": 20, "overdue_money": 10, "pipeline_health": 15,
        "dispatch_health": 10, "followup_health": 10, "revenue_attainment": 25,
        "conversion_health": 10,
    }


def test_weights_sum_to_one_hundred():
    assert sum(c.weight for c in COMPONENTS) == 100


def test_a_perfect_business_scores_one_hundred():
    result = health_score(ALL_SIGNALS, AnalyticsTargets(monthly_revenue_target=500000, target_conversion_pct=30))
    assert result["score"] == 100
    assert result["band"] == "Healthy"
    assert result["available"] == 7 and result["total"] == 7


def test_bands_follow_the_spec_boundaries():
    def score_of(value: float) -> str:
        signals = {k: value for k in ALL_SIGNALS}
        return health_score(signals, AnalyticsTargets(monthly_revenue_target=1, target_conversion_pct=1))["band"]
    assert score_of(85.0) == "Healthy"
    assert score_of(84.0) == "Watch"
    assert score_of(70.0) == "Watch"
    assert score_of(69.0) == "At risk"


def test_without_a_revenue_target_the_score_renormalizes_over_six_signals():
    # 6 of 7: the remaining weights (75) rescale to 100, so an all-100 business
    # still scores 100 rather than 75.
    signals = {**ALL_SIGNALS, "revenue_attainment": None}
    result = health_score(signals, AnalyticsTargets(target_conversion_pct=30))
    assert result["score"] == 100
    assert result["available"] == 6 and result["total"] == 7
    assert "revenue target" in result["missing_signal_note"].lower()


def test_renormalization_changes_the_weighting_not_just_the_denominator():
    # collection_health 100, everything else 0. With all 7 signals its share is
    # 20/100. Without the two target-backed ones it is 20/65.
    signals = {k: 0.0 for k in ALL_SIGNALS}
    signals["collection_health"] = 100.0
    full = health_score(signals, AnalyticsTargets(monthly_revenue_target=1, target_conversion_pct=1))["score"]
    partial = health_score({**signals, "revenue_attainment": None, "conversion_health": None}, AnalyticsTargets())["score"]
    assert full == 20
    assert partial == 31          # round(100 * 20/65)


def test_a_component_value_is_clamped_to_the_zero_hundred_band():
    # revenue at 300% of target is capped at 100 — an overshoot cannot mask a
    # failing component elsewhere.
    signals = {**{k: 0.0 for k in ALL_SIGNALS}, "revenue_attainment": 300.0}
    result = health_score(signals, AnalyticsTargets(monthly_revenue_target=1, target_conversion_pct=1))
    assert result["score"] == 25
    assert [c["value"] for c in result["components"] if c["key"] == "revenue_attainment"] == [100.0]


def test_every_component_reports_its_rule_and_destination_for_the_expander():
    result = health_score(ALL_SIGNALS, AnalyticsTargets(monthly_revenue_target=1, target_conversion_pct=1))
    for component in result["components"]:
        assert component["rule"], f"{component['key']} has no stated rule"
        assert component["destination"].startswith("/(admin)/")


def test_no_available_signals_at_all_returns_no_score_rather_than_zero():
    """Zero would read as "the business is failing"; the honest answer is that
    the score cannot be computed."""
    result = health_score({k: None for k in ALL_SIGNALS}, AnalyticsTargets())
    assert result["score"] is None
    assert result["band"] is None
    assert result["available"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics.health'`

- [ ] **Step 3: Write the module**

```python
def health_score(signals, targets):
    available = [(c, signals.get(c.key)) for c in COMPONENTS if signals.get(c.key) is not None]
    if not available:
        return {"score": None, "band": None, "components": [], "available": 0,
                "total": len(COMPONENTS), "missing_signal_note": "..."}
    total_weight = 0
    weighted = 0.0
    for component, value in available:
        clamped = max(0.0, min(100.0, float(value)))
        weighted += clamped * component.weight
        total_weight += component.weight
    score = round(weighted / total_weight)
    ...
```

Note the fold: accumulate explicitly, do not use `sum()` over floats (Phase 0 established that CPython ≥3.12's compensated summation shifts money-adjacent values; keep the codebase consistent). Band boundaries are `>= 85` Healthy, `>= 70` Watch, else At risk. `missing_signal_note` names the specific missing target and links to Settings, per §8's exact wording: *"Based on N of 7 signals — set a revenue target to include revenue attainment"*.

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_health.py -v`
Expected: PASS — 9 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/health.py backend/tests/unit/test_analytics_health.py
git commit -m "Add the Business Health Score

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: `feed.py` — the executive activity allowlist

**Files:**
- Create: `backend/services/analytics/feed.py`
- Test: `backend/tests/unit/test_analytics_feed.py`

**Interfaces:**
- Produces:
  - `EXECUTIVE_EVENTS: dict[str, str]` — real `event_type` → feed line template
  - `feed_rows(events, entity_floors, values, now) -> list[dict]` — pure; allowlist filter, floor derivation, value join, grouping key
  - `group_of(created_at, now) -> Literal["today","yesterday","this_week","older"]`

**The allowlist must use the REAL event_type values probed above**, not the spec's aspirational names: `quotation.order_placed`, `quotation.created`, `quotation.status_changed`, `payment.recorded`, `ready_batch.created`, `dispatch.created`, `dispatch.delivered`, `purchase.chalan_dispatched`, `purchase.chalan_godown_received`, `item.moved_to_godown`, `walkin.created`, `walkin.quotation_created`, `followup.call_logged`, `supplier.assigned`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_analytics_feed.py`:

```python
"""An allowlist, not a noise filter: 57% of activity_events is
product.image_uploaded and user.login. An event not on the list can never
reach the owner's feed, so instrumentation added elsewhere cannot flood it."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.analytics.feed import EXECUTIVE_EVENTS, feed_rows, group_of

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def _iso(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


def test_the_noisiest_operational_events_are_not_on_the_allowlist():
    for noisy in ("product.image_uploaded", "user.login", "quotation.pdf_generated", "product.updated"):
        assert noisy not in EXECUTIVE_EVENTS


def test_the_executive_events_are_on_the_allowlist_under_their_real_names():
    for real in ("quotation.order_placed", "quotation.created", "payment.recorded",
                 "ready_batch.created", "purchase.chalan_dispatched", "walkin.created",
                 "followup.call_logged", "supplier.assigned"):
        assert real in EXECUTIVE_EVENTS


def test_an_event_off_the_allowlist_is_dropped():
    events = [{"id": "e1", "event_type": "product.image_uploaded", "created_at": _iso(1), "quotation_id": None}]
    assert feed_rows(events, entity_floors={}, values={}, now=NOW) == []


def test_an_allowed_event_renders_with_its_joined_value():
    events = [{"id": "e1", "event_type": "quotation.order_placed", "created_at": _iso(2),
               "quotation_id": "q1", "actor_name": "Rahul", "summary": "FQ-1 · JK"}]
    rows = feed_rows(events, entity_floors={"q1": "first-floor"}, values={"q1": 480000.0}, now=NOW)
    assert len(rows) == 1
    assert rows[0]["value"] == 480000.0
    assert rows[0]["destination"] == "/(admin)/quotations/q1"
    assert rows[0]["group"] == "today"


def test_an_event_whose_entity_no_longer_resolves_is_omitted_not_shown_unscoped():
    # activity_events has no floor_id; an unresolvable entity means the floor
    # cannot be derived, and showing it anyway is a floor leak.
    events = [{"id": "e1", "event_type": "quotation.order_placed", "created_at": _iso(1), "quotation_id": "gone"}]
    assert feed_rows(events, entity_floors={}, values={}, now=NOW) == []


def test_value_is_never_read_from_the_payload():
    """payload carries small diffs, not money. A value shown must come from the
    joined record or not be shown at all."""
    events = [{"id": "e1", "event_type": "quotation.order_placed", "created_at": _iso(1),
               "quotation_id": "q1", "payload": {"grand_total": 999999.0}}]
    rows = feed_rows(events, entity_floors={"q1": "first-floor"}, values={}, now=NOW)
    assert rows[0]["value"] is None


def test_grouping_covers_today_yesterday_and_this_week():
    assert group_of(_iso(1), NOW) == "today"
    assert group_of(_iso(30), NOW) == "yesterday"
    assert group_of(_iso(24 * 4), NOW) == "this_week"
    assert group_of(_iso(24 * 30), NOW) == "older"


def test_rows_are_newest_first():
    events = [
        {"id": "old", "event_type": "quotation.created", "created_at": _iso(5), "quotation_id": "q1"},
        {"id": "new", "event_type": "quotation.created", "created_at": _iso(1), "quotation_id": "q1"},
    ]
    rows = feed_rows(events, entity_floors={"q1": "first-floor"}, values={"q1": 1.0}, now=NOW)
    assert [r["id"] for r in rows] == ["new", "old"]


def test_only_approved_and_rejected_status_changes_reach_the_feed():
    def event(to_status):
        return {"id": to_status, "event_type": "quotation.status_changed", "created_at": _iso(1),
                "quotation_id": "q1", "payload": {"from": "draft", "to": to_status}}
    rows = feed_rows([event("approved"), event("draft"), event("rejected")],
                     entity_floors={"q1": "first-floor"}, values={"q1": 1.0}, now=NOW)
    assert {r["id"] for r in rows} == {"approved", "rejected"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_feed.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics.feed'`

- [ ] **Step 3: Write the module**

`feed_rows` is pure: the caller (Task 6) resolves `entity_floors` (entity id → floor) and `values` (entity id → ₹) with real queries and passes them in. An event resolves its entity in priority order `quotation_id` → `customer_id` → `purchase_id`; if none resolves in `entity_floors`, drop the row. `quotation.status_changed` additionally requires `payload["to"] ∈ {"approved","rejected"}`.

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_feed.py -v`
Expected: PASS — 9 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/feed.py backend/tests/unit/test_analytics_feed.py
git commit -m "Add the executive activity feed allowlist

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## STAGE A GATE

Before Task 6: full suite green (`482 + 56 = 538` expected), every rule pure and DB-free, ledger entry written. Report to the user: what was built, what was verified, tests, live verification (n/a for pure modules — say so), remaining work.

---

## Task 6: `gather.py` — the only place Phase 1 reads Mongo

**Files:**
- Create: `backend/services/analytics/gather.py`
- Test: `backend/tests/unit/test_analytics_gather.py`

**Interfaces:**
- Consumes: `build_match`, `AnalyticsFilter`, `date_field_for` (Phase 0); `AttentionInput` (Task 2), `OpportunityInput` (Task 3)
- Produces:
  - `async gather_attention(db, f, accessible_floors, window, thresholds) -> AttentionInput`
  - `async gather_opportunity(db, f, accessible_floors, window, thresholds) -> OpportunityInput`
  - `async gather_health_signals(db, f, accessible_floors, window, targets) -> dict[str, float | None]`
  - `async gather_feed(db, f, accessible_floors, limit) -> list[dict]`
  - `async collected_by_quotation(db, quotation_ids) -> dict[str, float]` — completed payments only

**The load-bearing rule:** every read goes through `build_match`. No hand-written `{"floor_id": ...}` anywhere in this file. Attention rules need *open* quotations, so they call `build_match` with `AnalyticsFilter(status="any")` plus an explicit status set — never by dropping the floor clause.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_analytics_gather.py`. Use the hand-rolled fake-db pattern already in `tests/unit/test_tile_orders_delivered.py` (this suite has no pytest-asyncio — drive with `asyncio.run`, and remember `tiles_floor_query`-style `$and` wrapping does not apply here):

```python
"""Every Phase 1 read goes through build_match, so floor scoping and the
ordered_at date field are never re-implemented per surface."""
from __future__ import annotations

import asyncio

from services.analytics import gather
from services.analytics.filters import AnalyticsFilter

WINDOW = ("2026-07-01T00:00:00+00:00", "2026-07-31T23:59:59+00:00")


class _FakeCursor:
    def __init__(self, docs): self._docs = list(docs)
    def sort(self, *a, **k): return self
    def limit(self, *a, **k): return self
    async def to_list(self, n): return self._docs[:n]
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


def test_attention_reads_are_floor_scoped_for_a_restricted_caller():
    db = _FakeDb(quotations=[], payments=[], followups=[], walkins=[], purchase_orders=[])
    asyncio.run(gather.gather_attention(db, AnalyticsFilter(floor_id="all"), ["ground-floor"], WINDOW, {}))
    scoped = [q for q in db.quotations.queries if q.get("floor_id")]
    assert scoped, "no quotation read carried a floor clause"
    for q in scoped:
        assert q["floor_id"] == {"$in": ["ground-floor"]}


def test_an_unrestricted_caller_gets_no_floor_clause():
    db = _FakeDb(quotations=[], payments=[], followups=[], walkins=[], purchase_orders=[])
    asyncio.run(gather.gather_attention(db, AnalyticsFilter(floor_id="all"), None, WINDOW, {}))
    assert all("floor_id" not in q for q in db.quotations.queries)


def test_open_quotations_are_fetched_by_status_not_by_dropping_the_floor_clause():
    db = _FakeDb(quotations=[], payments=[], followups=[], walkins=[], purchase_orders=[])
    asyncio.run(gather.gather_attention(db, AnalyticsFilter(floor_id="all"), ["first-floor"], WINDOW, {}))
    open_reads = [q for q in db.quotations.queries if isinstance(q.get("status"), dict)]
    assert open_reads, "expected a status-$in read for open quotations"
    for q in open_reads:
        assert set(q["status"]["$in"]) <= {"draft", "sent", "approved", "pending_approval"}
        assert q.get("floor_id") == {"$in": ["first-floor"]}


def test_only_completed_payments_count_as_collected():
    db = _FakeDb(payments=[
        {"quotation_id": "q1", "amount": 100.0, "status": "completed"},
        {"quotation_id": "q1", "amount": 900.0, "status": "pending"},
    ])
    got = asyncio.run(gather.collected_by_quotation(db, ["q1"]))
    assert got == {"q1": 100.0}


def test_collected_lookup_with_no_quotations_issues_no_query():
    db = _FakeDb(payments=[{"quotation_id": "q1", "amount": 100.0, "status": "completed"}])
    assert asyncio.run(gather.collected_by_quotation(db, [])) == {}
    assert db.payments.queries == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_gather.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics.gather'`

- [ ] **Step 3: Write the module**

Each `gather_*` builds its matches with `build_match(AnalyticsFilter(...), accessible_floors, window)` and then mutates only non-floor keys (e.g. replacing `status` with `{"$in": [...]}` for the open-pipeline read). Health signals map to §8's rules:

| Signal | Computation |
|---|---|
| `collection_health` | `collected ÷ ordered` × 100 over the window; `None` when ordered is 0 |
| `overdue_money` | `(1 − overdue_outstanding ÷ total_outstanding)` × 100; `None` when there is no outstanding |
| `pipeline_health` | share of open quotation **value** (not count) newer than `QUOTATION_STALE_DAYS` |
| `dispatch_health` | share of ready material dispatched within `DISPATCH_WAITING_DAYS` |
| `followup_health` | share of open follow-ups not overdue |
| `revenue_attainment` | `revenue ÷ targets.monthly_revenue_target` × 100, `None` when no target |
| `conversion_health` | `conversion ÷ targets.target_conversion_pct` × 100, `None` when no target |

A signal with no denominator returns `None` (excluded and renormalized), never `0.0` — zero would read as failure.

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_gather.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/gather.py backend/tests/unit/test_analytics_gather.py
git commit -m "Add the Phase 1 gather layer

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: `executive_overview_routes.py` — the HTTP surface

**Files:**
- Create: `backend/routes/executive_overview_routes.py`
- Modify: `backend/server.py`
- Test: `backend/tests/unit/test_executive_overview_routes.py`

**Interfaces:**
- Consumes: everything from Tasks 1-6, plus `cache.cached`, `METRIC_SOURCES`, `filter_signature`, `revenue_pipeline`, `outstanding_pipeline`, `resolve`, `previous`, `compare`, `load_targets`
- Produces, all under the existing `/analytics` prefix and all gated `require_roles("owner","admin","manager")`:
  - `GET /analytics/overview` — the six above-the-fold elements in one payload
  - `GET /analytics/health`
  - `GET /analytics/attention`
  - `GET /analytics/opportunities`
  - `GET /analytics/brief`
  - `GET /analytics/feed`
  - `GET /analytics/today`

Every endpoint takes the standard filter query params (`floor_id`, `preset`, `date_from`, `date_to`) and wraps its loader in `cache.cached(metric_id, METRIC_SOURCES[...], filter_signature(f), accessible_floors, loader)`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_executive_overview_routes.py`:

```python
"""The analytics gate never widens access, a FloorAccessError is a 403, and
the overview carries exactly the six above-the-fold elements."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from models import UserPublic
from routes import executive_overview_routes as routes


def _user(role="owner", floors=None):
    return UserPublic(id="u1", email="o@forge.app", full_name="Owner", role=role, floor_ids=floors or [])


def test_every_endpoint_requires_an_analytics_role():
    for name in ("overview", "health", "attention", "opportunities", "brief", "feed", "today"):
        route = next(r for r in routes.router.routes if r.path.endswith(f"/{name}"))
        depends = [d.dependency for d in route.dependant.dependencies]
        assert depends, f"/{name} has no role dependency"


def test_a_cross_floor_request_is_a_403_not_a_500():
    from services.analytics.filters import FloorAccessError
    with pytest.raises(HTTPException) as exc:
        routes._floor_error_to_http(FloorAccessError("first-floor"))
    assert exc.value.status_code == 403


def test_the_overview_payload_has_exactly_the_six_above_the_fold_keys():
    # Spec 7: adding a seventh element requires amending the contract, so this
    # test is the contract's enforcement.
    assert routes.ABOVE_THE_FOLD == (
        "health", "brief", "kpis", "money_blocked", "attention", "opportunities",
    )


def test_actions_are_filtered_by_the_callers_role_not_the_analytics_gate():
    from services.analytics.rows import ActionRow
    row = ActionRow(
        rule="payment_overdue", kind="attention", headline="Payment overdue", impact=1000.0,
        age_days=40, context=[], destination="/(admin)/payments",
        actions=("open", "record_payment"), entity={"quotation_id": "q1"},
    )
    manager_view = routes._serialize_rows([row], role="manager")
    owner_view = routes._serialize_rows([row], role="owner")
    assert "open" in manager_view[0]["actions"]
    assert set(manager_view[0]["actions"]) <= set(owner_view[0]["actions"])


def test_todays_priorities_is_the_same_rule_set_as_the_overview():
    """A rule can never fire in Today's Priorities and not in the Overview -
    they must call the same functions, not two lists."""
    import inspect
    source = inspect.getsource(routes)
    assert source.count("attention_rows(") >= 1 and source.count("opportunity_rows(") >= 1
    assert "TODAY_RULES" not in source, "a second rule set was introduced"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_executive_overview_routes.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the router**

Register it in `server.py` the way every sibling is registered — `api.include_router(executive_overview_router)`, top-level import with `# noqa: E402`. **Not** `app.include_router(..., prefix="/api")`: `api` already carries the prefix.

`/analytics/overview` returns `{"health": …, "brief": …, "kpis": …, "money_blocked": …, "attention": [...], "opportunities": [...], "period": {...}, "history_state": …}` — the top 3-5 rows per list, with `total` counts so the UI can link to Today's Priorities for the rest. `/analytics/today` returns every row.

`/analytics/brief` composes from the same services: yesterday's revenue/orders/collections via `revenue_pipeline` over a `resolve("yesterday")` window, best brand via `line_revenue_pipeline`, and **recommended actions = the top three of `rank(attention + opportunity)`** — not a separate rule set (§11).

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit -v`
Expected: PASS, suite up by 5

- [ ] **Step 5: Verify the app boots**

Run: `cd backend && ./.venv/bin/python -c "import server; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add backend/routes/executive_overview_routes.py backend/server.py backend/tests/unit/test_executive_overview_routes.py
git commit -m "Add the executive overview endpoints

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: Wire cache invalidation into the write paths

Phase 0 built `cache.bump()` and deliberately left it uncalled. Phase 1 is the first consumer, so it gets wired now — §14.1 rule 2 depends on it (acting must refresh the numbers).

**Files:**
- Modify: `backend/services/domain_outbox.py`
- Test: `backend/tests/unit/test_analytics_cache_wiring.py`

- [ ] **Step 1: Write the failing test**

```python
"""Acting on an Attention row must refresh the numbers. Every analytics-visible
write bumps its collection version, which changes every dependent cache key."""
from __future__ import annotations

import asyncio

from services.analytics import cache


def test_a_quotation_write_invalidates_every_quotation_backed_metric():
    async def go():
        cache.reset_memory_state()
        before = await cache.cache_key("revenue", ["quotations"], "sig", None)
        await cache.bump("quotations")
        assert await cache.cache_key("revenue", ["quotations"], "sig", None) != before
    asyncio.run(go())


def test_the_outbox_bumps_on_every_analytics_visible_event():
    import inspect
    from services import domain_outbox
    source = inspect.getsource(domain_outbox)
    assert "cache.bump" in source or "from services.analytics.cache import bump" in source
```

- [ ] **Step 2: Wire it**

Bump the collection each handler writes: order placed → `quotations`, `purchase_orders`, `customer_orders`; payment recorded → `payments`; ready/dispatch → `ready_batches`, `dispatches`; follow-up writes → `followups`. Bump **after** the transaction commits, next to the existing post-commit `notify()` call — the 22 Jul fix established that ordering and it must not be undone.

- [ ] **Step 3: Run the tests and commit**

```bash
git add backend/services/domain_outbox.py backend/tests/unit/test_analytics_cache_wiring.py
git commit -m "Bump analytics cache versions on analytics-visible writes

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## STAGE B GATE — live-database verification

Run every endpoint against live `buildcon_house` with a real session (`curl POST /api/auth/login`, ask the user for credentials), and for each one:

1. **Three-way floor probe** — no `X-Floor-Id`, `first-floor`, `ground-floor` — asserting the returned rows' own floor set. This catches ambient-state leaks the UI hides (the 2026-07-31 recipe).
2. **Reconcile against a direct Mongo query, value for value**: `/analytics/overview`'s revenue KPI must equal ₹39,77,337.00 for an all-time ordered window, and outstanding ₹38,32,023.00.
3. Confirm the Attention rows that fire correspond to real records — open each one's `destination` id in Mongo and check the row's ₹ impact matches the record.
4. Confirm no row has `impact <= 0` and no comparison rule fired with `prior_window_exists: false`.

The backend on `:8010` must be restarted for any of this to exercise new code — **ask the user first**. Record everything in the ledger, then report in the required format.

---

## Task 9: `StateViews` + `KpiCard` + `KpiRow`

**Files:**
- Create: `frontend/src/components/analytics/StateViews.tsx`
- Create: `frontend/src/components/analytics/KpiCard.tsx`
- Create: `frontend/src/components/analytics/KpiRow.tsx`
- Create: `frontend/src/api/executive.ts`

**Interfaces:**
- Produces:
  - `<LoadingView/>`, `<EmptyView title subtitle/>`, `<NoPriorPeriodView/>`, `<InsufficientHistoryView/>`, `<StateView state={HistoryState}/>`
  - `type HistoryState = "ok" | "no_prior_period" | "insufficient_history"`
  - `<KpiCard label value question delta direction historyState sparkline onPress/>`
  - `<KpiRow>{children}</KpiRow>` — the sticky strip
  - `executiveApi.overview(params)`, `.health()`, `.attention()`, `.opportunities()`, `.brief()`, `.feed()`, `.today()` — typed wrappers over `api.get`, mirroring `src/api/tileOrders.ts`

**Requirements:**
- **The question ships on the card**, in `type.caption`, under the value — it is not documentation (§7).
- A `delta` is rendered **only** when `historyState === "ok"`. Otherwise the card renders the matching `StateView` copy in place of the delta. Never `+100%`, never `0%`.
- `Sparkline` from Phase 0 is the trend mark; a series with fewer than 2 points renders its own empty state (already handled).
- Reuse `fmtMoneyCompact` from `src/design/tokens` — the 2026-07-16 lesson is that `money()` inside a narrow tile truncates mid-digit on RN-Web, and `adjustsFontSizeToFit` is a silent no-op there.
- 8pt spacing, 44px minimum touch target on the pressable card, `HoverCard` semantics (no `accessibilityRole="button"` on a card that contains buttons).

- [ ] **Step 1: Write the components**
- [ ] **Step 2: Typecheck** — `cd frontend && npx tsc --noEmit`, expected clean
- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/analytics/ frontend/src/api/executive.ts
git commit -m "Add executive KPI card, KPI row, and state views

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: `HealthScoreCard` + `MorningBrief`

**Files:**
- Create: `frontend/src/components/analytics/HealthScoreCard.tsx`
- Create: `frontend/src/components/analytics/MorningBrief.tsx`

**Requirements:**
- Health card renders score, band, direction line, and *"Based on N of 7 signals"*. Tapping expands to every component with its raw value, its stated rule, its weight, and a link to the workspace that would improve it. When `score` is `null` the card says the score cannot be computed and links to Settings to set a target — it never renders `0`.
- Band colours come from existing status tokens; do not add new colour tokens.
- Morning Brief renders `Good morning, <name>`, the Yesterday block, and Recommended actions. **Lines with no data are omitted, not shown as zero** (§11). Every figure is a link to its record.
- Both are pure presentational components over the API payload — no computation in the component. A number computed in the frontend is a number that can disagree with the backend.

- [ ] **Step 1: Write the components**
- [ ] **Step 2: Typecheck**
- [ ] **Step 3: Commit**

---

## Task 11: `ActionRow` + `AttentionList` + `OpportunityList`

**Files:**
- Create: `frontend/src/components/analytics/ActionRow.tsx`
- Create: `frontend/src/components/analytics/AttentionList.tsx`
- Create: `frontend/src/components/analytics/OpportunityList.tsx`

**Requirements — these are the §14.1 rules and they are not negotiable:**
1. The row is a `HoverCard` (`src/components/ds.tsx`), which deliberately never sets `accessibilityRole="button"` on its wrapping `Pressable`. Action buttons live inside it. This is the exact shape that produced `<button>`-in-`<button>` in the 2026-07-24 `QueueRow` bug.
2. Actions render **only** what the payload returned — the backend already filtered by role. The frontend must not re-derive permissions, and must not render a disabled button for a missing one.
3. Every action control is at least 44px.
4. `Call` uses `Linking.openURL('tel:…')` (the pattern in `dashboard.tsx:180`). `WhatsApp` posts to the existing `/followups/{id}/contact` and opens the returned `wa_url`. `Record Payment`, `Schedule Follow-up` and `Assign` open the existing operational surfaces. **No new write path is created in this task.**
5. Context fields render as label/value pairs from `row.context`, in payload order.
6. Both lists show a calm all-clear when empty — Attention's is a confirmation that nothing is wrong, never a "you're doing great" card that fires on real problems.

- [ ] **Step 1: Write the components**
- [ ] **Step 2: Typecheck**
- [ ] **Step 3: Commit**

---

## Task 12: `ActivityFeed` + `MoneyBlockedCard`

**Files:**
- Create: `frontend/src/components/analytics/ActivityFeed.tsx`
- Create: `frontend/src/components/analytics/MoneyBlockedCard.tsx`

**Requirements:**
- Feed groups Today / Yesterday / This Week with a sticky group header; each entry shows time, actor, line, and value when the backend joined one; each entry links to its record.
- `MoneyBlockedCard` is ₹-first: total blocked, split by awaiting release / awaiting dispatch / awaiting payment, each segment linking to Operations. Values come from the API, not recomputed.
- Long lists scroll inside their own container; the page body never scrolls horizontally.

- [ ] **Step 1: Write the components**
- [ ] **Step 2: Typecheck**
- [ ] **Step 3: Commit**

---

## STAGE C GATE

`npx tsc --noEmit` clean, every component rendered at least once against real API data in the browser, no console warnings. Ledger entry, then report.

---

## Task 13: The Executive Overview screen

**Files:**
- Modify: `frontend/app/(admin)/sales-data/executive.tsx` (replaced wholesale)

**The above-the-fold contract (§7) — exactly these six, in this order, and nothing else:**

1. Business Health
2. Morning Brief
3. Revenue KPIs (Revenue · Orders · Average Order · Outstanding)
4. Money Blocked
5. Attention Center
6. Opportunity Center

Below the fold, in order: Revenue trend · Revenue by Floor · Pending Quotations · Pending Follow-ups · Top 5 movers · Activity Feed.

**Requirements:**
- One `useEffect`-driven fetch of `/analytics/overview`; the below-fold sections may lazy-load, but nothing renders a skeleton that never resolves.
- Filter state lives in **URL query params** (§16.3) so every drill-down is shareable and back-navigable.
- `useRequireFloorAccess` is not appropriate here (this is a company-wide report gated by role) — use the same role gate the existing screen uses, and pass the active floor through as the default `floor_id` param.
- Zero layout shift: reserve the height of each card while loading rather than growing the page as data lands.
- Responsive at 1280 / 768 / 375. The KPI strip wraps rather than scrolling horizontally on phone.

- [ ] **Step 1: Build the screen**
- [ ] **Step 2: Typecheck**
- [ ] **Step 3: Browser pass at all three widths**
- [ ] **Step 4: Commit**

---

## Task 14: Today's Priorities

**Files:**
- Create: `frontend/app/(admin)/sales-data/today.tsx`

**Requirements:**
- Header: `Today's Priorities` + `N things need attention` (real count, never a manufactured one).
- Every row from `/analytics/today` — the *full* set the Overview truncates — rendered as `ActionRow`.
- **Stars come from `followup_engine.score_followup`'s existing level**, mapped `critical→5, high→4, medium→3, low→2` with a floor of 1; tapping the stars shows `reason_factors`. Do not invent a second priority scale.
- `Done today` reads the feed allowlist filtered to today and to completion-shaped events (payments recorded, dispatches completed, orders placed, follow-ups closed). It is a record, not a checklist.
- Genuine all-clear state when nothing fires.

- [ ] **Step 1: Build the screen**
- [ ] **Step 2: Typecheck**
- [ ] **Step 3: Browser pass**
- [ ] **Step 4: Commit**

---

## Task 15: Routing

**Files:**
- Modify: `frontend/app/(admin)/sales-data/index.tsx`

Replace the legacy screen's default export with `<Redirect href="/(admin)/sales-data/executive" />`, per the user's decision on 2026-08-01. The legacy component code and `sales_data_routes.py` stay in the repo until Phase 6 removes them, but nothing navigates there.

Confirm the Phase 0 `WorkspaceSwitcher` already points Overview → Executive and Today's Priorities → `/sales-data/today`; both routes now exist, so those two members must no longer 404.

- [ ] **Step 1: Make the change**
- [ ] **Step 2: Verify `/sales-data` lands on the Executive Overview and `/sales-data/today` resolves**
- [ ] **Step 3: Commit**

---

## STAGE D GATE

Browser pass at 1280 / 768 / 375 on both screens; accessibility tree checked for nested interactive elements; zero console warnings; zero layout shift. Ledger entry, then report.

---

## Task 16: Phase 1 verification (§18 protocol, all 12 points)

No new code.

- [ ] Every KPI cross-checked against a direct Mongo query, value for value
- [ ] Every aggregation reconciles: product = brand = category = quotation revenue
- [ ] Health Score recomputed by hand for one period and matched component by component
- [ ] Every filter verified, including the three-way floor probe
- [ ] Every drill-down opens the right record with filter context preserved
- [ ] Exports open and match on-screen data (or are recorded as not-yet-in-scope if Phase 1 ships no export)
- [ ] **Every Command Center action re-checks its own permission** — call each action's endpoint as a role that should be refused and confirm it is
- [ ] No nested interactive elements, checked against the live accessibility tree
- [ ] Responsive pass at 1280 / 768 / 375
- [ ] No placeholder components, no empty cards, no fabricated values
- [ ] Backend unit tests for every new service module
- [ ] Fix, re-verify, and only then declare Phase 1 complete

---

## Self-Review

**Spec coverage.** §17's Phase 1 list: Executive Overview (Task 13) · Business Health Score (Tasks 4, 10) · Attention Center (Tasks 2, 11) · Opportunity Center (Tasks 3, 11) · Morning Brief (Tasks 7, 10) · Activity Feed (Tasks 5, 12) · Command Center action model (Tasks 1, 11) · Today's Priorities (Task 14). §7 Workspace 1's card table is covered by Task 13's above/below-fold layout. §18's protocol is Task 16.

**Deliberately deferred, with reasons stated rather than hidden:** §10's *Repeat-buyer cross-sell* rule (no frequently-bought-together service exists; would require fabricating affinity data); §15 Global search and §16.3's `FilterBar`/`DataTable`/`ExportMenu`/`HeatBadge`/`RelationshipTimeline` (Phases 2-5 content, not Phase 1); Workspace 1's export row (§6 says every table exports — Phase 1 ships no table that isn't a list of action rows, so `ExportMenu` lands with the first real table in Phase 2).

**Placeholder scan.** Every task carries either complete test code or an explicit, checkable requirement list. No "TBD", no "similar to Task N", no "add error handling".

**Type consistency.** `ActionRow`'s field names are identical in Tasks 1, 2, 3, 7 and 11. `THRESHOLDS` is one object, imported by identity in Task 3 and asserted as such. `HistoryState` matches the backend's `history_state` strings from Phase 0's `periods.py`. `AttentionInput`/`OpportunityInput` are constructed only in Task 6 and consumed only in Tasks 2/3.

**Known risk, flagged not assumed away:** the live database has 35 ordered quotations, all backfilled to `updated_at` by migration 0012, so *every* comparison rule will report `insufficient_history` or `no_prior_period` for windows that need a real prior period. That is the honest, designed behaviour — but it means Stage B's live verification will show mostly-suppressed comparison rules, and that must be recorded as correct rather than debugged as a failure.
