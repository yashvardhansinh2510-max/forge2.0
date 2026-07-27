# Follow-ups Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the six changes from `docs/superpowers/specs/2026-07-27-followups-revamp-design.md` — floor-timed follow-up reminders, a walk-in "Add to Follow-ups" entry point, free rescheduling on every card, overdue/assigned-to-me-first sorting, and a manager-only assignment tracking view.

**Architecture:** All changes are additive to the existing Follow-ups · Sales Command Center (`backend/services/followup_engine.py` deterministic scoring/reconciliation engine, `backend/routes/followup_routes.py` API, `frontend/app/(admin)/followups.tsx` + `dashboard.tsx` UI). No schema migration, no new collections, no new external dependencies — every task extends an existing file or adds one new frontend screen / one new backend endpoint that reuses existing helpers.

**Tech Stack:** FastAPI + Motor (async MongoDB) backend, Expo/React Native frontend, pytest (`asyncio_mode = auto`, `testpaths = tests/unit`) for backend tests. No frontend test harness exists in this repo — frontend tasks are verified manually via the dev server/browser, not automated tests.

## Global Constraints

- No LLM calls anywhere in the follow-up engine — every rule, score, and sort order must stay a plain deterministic function (per `backend/services/followup_engine.py`'s existing module docstring and the design spec).
- Floor IDs are exactly `"ground-floor"` and `"first-floor"` (see `backend/auth.py`); any other/missing value falls back to `"first-floor"` behavior — `FOLLOWUP_DEFAULT_DAYS = 7` matches this.
- Backend unit tests run from the `backend/` directory: `cd backend && pytest tests/unit/<file> -v`. Do not touch `backend/tests/integration/` files except where a task explicitly says to (those are `pytest.ini`-excluded from default collection, gated on live-server env vars).
- Follow existing per-screen design-system conventions exactly — `frontend/app/(admin)/followups.tsx` and `dashboard.tsx` import from `@/src/components/ds`; `frontend/app/(admin)/customers/[id].tsx` and `team.tsx` import from `@/src/components/ui` (a parallel, separate component set — do not cross-import between the two in the same file).
- Every new/modified backend response field or endpoint must stay additive — do not remove or rename existing `Followup` fields, existing rule types, or existing endpoint paths.

---

### Task 1: Floor-timed follow-up rule (replaces `quotation_new` + `quotation_inactive`)

**Files:**
- Modify: `backend/models.py:844-848`
- Modify: `backend/services/followup_engine.py:29-58` (constants + `RULE_DEFINITIONS`), `:254-291` (reconcile logic)
- Modify: `backend/routes/followup_routes.py:114-116`
- Modify: `frontend/app/(admin)/followups.tsx:443`
- Modify: `backend/tests/integration/test_followups_v2.py:98-120`
- Create: `backend/tests/unit/test_followup_floor_timing.py`

**Interfaces:**
- Produces: `quotation_followup_delay_days(floor_id: str) -> int` and `quotation_followup_due_at(created_at: datetime, floor_id: str) -> Optional[datetime]` in `backend/services/followup_engine.py` — Task 5's report and any future caller can reuse these; not consumed elsewhere in this plan.
- Produces: new `FollowupRuleType` literal value `"quotation_followup"` (`backend/models.py`) — used by Task 1's own engine wiring and by the `waiting_for_customer` stat fix in this same task.

- [ ] **Step 1: Write the failing test for the delay-days lookup**

Create `backend/tests/unit/test_followup_floor_timing.py`:

```python
"""Regression test: the floor-timed follow-up rule replaces the old
quotation_new/quotation_inactive pair. Ground Floor (Tiles) surfaces a
reminder 4 days after a quotation/selection is created; First Floor
(Sanitary) surfaces one after 7 days — see
docs/superpowers/specs/2026-07-27-followups-revamp-design.md."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.followup_engine import (
    quotation_followup_delay_days, quotation_followup_due_at,
)


def test_ground_floor_delay_is_four_days():
    assert quotation_followup_delay_days("ground-floor") == 4


def test_first_floor_delay_is_seven_days():
    assert quotation_followup_delay_days("first-floor") == 7


def test_unknown_floor_defaults_to_seven_days():
    assert quotation_followup_delay_days("second-floor") == 7
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/unit/test_followup_floor_timing.py -v`
Expected: FAIL with `ImportError: cannot import name 'quotation_followup_delay_days'`

- [ ] **Step 3: Implement the delay-days lookup**

In `backend/services/followup_engine.py`, replace lines 29-34 (currently):

```python
# Mutually-exclusive day windows so payment_overdue / payment_partial never
# both fire for the same order.
PAYMENT_OVERDUE_DAYS = 5
QUOTATION_INACTIVE_DAYS = 3
QUOTATION_NEW_WINDOW_DAYS = 2
CUSTOMER_INACTIVE_DAYS = 21
```

with:

```python
# Mutually-exclusive day windows so payment_overdue / payment_partial never
# both fire for the same order.
PAYMENT_OVERDUE_DAYS = 5
CUSTOMER_INACTIVE_DAYS = 21

# Floor-timed follow-up window — how long after a quotation/selection is
# created before the first automated nudge appears. Ground Floor (Tiles)
# gets a shorter window than First Floor (Sanitary) per the 2026-07-27
# design decision. Unknown/missing floor falls back to the same default
# used elsewhere for floor_id (`backend/auth.py`'s "first-floor" default).
FLOOR_FOLLOWUP_DAYS = {"ground-floor": 4, "first-floor": 7}
FOLLOWUP_DEFAULT_DAYS = 7


def quotation_followup_delay_days(floor_id: str) -> int:
    return FLOOR_FOLLOWUP_DAYS.get(floor_id, FOLLOWUP_DEFAULT_DAYS)
```

(Line 35, `DELIVERED_RECENCY_DAYS = 5`, stays exactly where it is, right after — only the two `QUOTATION_*` constants are removed.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && pytest tests/unit/test_followup_floor_timing.py -v`
Expected: 3 PASS

- [ ] **Step 5: Write the failing test for the due-at gate**

Append to `backend/tests/unit/test_followup_floor_timing.py`:

```python
def test_not_due_yet_before_the_floor_window_elapses():
    created_at = datetime.now(timezone.utc) - timedelta(days=2)
    assert quotation_followup_due_at(created_at, "ground-floor") is None


def test_due_once_the_ground_floor_window_elapses():
    created_at = datetime.now(timezone.utc) - timedelta(days=5)
    due = quotation_followup_due_at(created_at, "ground-floor")
    assert due == created_at + timedelta(days=4)


def test_first_floor_not_due_at_four_days():
    created_at = datetime.now(timezone.utc) - timedelta(days=4)
    assert quotation_followup_due_at(created_at, "first-floor") is None


def test_first_floor_due_at_seven_days():
    created_at = datetime.now(timezone.utc) - timedelta(days=7)
    due = quotation_followup_due_at(created_at, "first-floor")
    assert due == created_at + timedelta(days=7)
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd backend && pytest tests/unit/test_followup_floor_timing.py -v`
Expected: FAIL with `ImportError: cannot import name 'quotation_followup_due_at'` (or `AttributeError`)

- [ ] **Step 7: Implement the due-at gate**

In `backend/services/followup_engine.py`, add this function directly after `quotation_followup_delay_days` (from Step 3):

```python
def quotation_followup_due_at(created_at: datetime, floor_id: str) -> Optional[datetime]:
    """None if the floor-timed follow-up window hasn't elapsed yet for a
    quotation/selection created at `created_at`; otherwise the fixed due_at
    instant (created_at + delay). Always the same value for the same
    inputs, so repeated reconcile passes never drift the due date — only a
    staff-initiated reschedule (PATCH .../due_at) changes it after that."""
    due = created_at + timedelta(days=quotation_followup_delay_days(floor_id))
    return due if datetime.now(timezone.utc) >= due else None
```

- [ ] **Step 8: Run to verify it passes**

Run: `cd backend && pytest tests/unit/test_followup_floor_timing.py -v`
Expected: 7 PASS

- [ ] **Step 9: Add the new rule type to the model**

In `backend/models.py`, lines 844-848 currently read:

```python
FollowupRuleType = Literal[
    "quotation_new", "quotation_inactive", "quotation_expiring", "quotation_expired",
    "payment_overdue", "payment_partial", "purchase_dispatched", "purchase_delivered",
    "customer_inactive", "shortage_reorder", "manual",
]
```

Replace with (keep the two retired values in the Literal so existing stored rows still deserialize — they just stop being generated):

```python
FollowupRuleType = Literal[
    "quotation_new", "quotation_inactive", "quotation_followup", "quotation_expiring",
    "quotation_expired", "payment_overdue", "payment_partial", "purchase_dispatched",
    "purchase_delivered", "customer_inactive", "shortage_reorder", "manual",
]
```

- [ ] **Step 10: Update `RULE_DEFINITIONS`**

In `backend/services/followup_engine.py`, lines 37-58, replace the first two entries:

```python
RULE_DEFINITIONS = [
    {"rule_type": "quotation_new", "label": "New quotation", "category": "quotation",
     "description": "Fires within ~2 days of a quotation being created — strike while interest is highest."},
    {"rule_type": "quotation_inactive", "label": "Quotation inactive", "category": "quotation",
     "description": f"No status change for {QUOTATION_INACTIVE_DAYS}+ days on a sent quotation."},
```

with:

```python
RULE_DEFINITIONS = [
    {"rule_type": "quotation_followup", "label": "Quotation/selection follow-up", "category": "quotation",
     "description": "Floor-timed nudge — Ground Floor (Tiles) at 4 days, First Floor (Sanitary) at 7 days after creation."},
```

(The remaining entries in the list — `quotation_expiring` through `shortage_reorder` — are unchanged.)

- [ ] **Step 11: Wire the new rule into `reconcile_followups()`**

In `backend/services/followup_engine.py`, the quotation loop currently has (originally lines ~268-291):

```python
        if status in ("draft", "sent", "pending_approval"):
            age_created = age_days(created_at)
            age_updated = age_days(updated_at)
            if age_created <= QUOTATION_NEW_WINDOW_DAYS:
                upsert(
                    f"quotation_new:{q['id']}", "quotation_new", "quotation", cust,
                    quotation=q, value=value,
                    due_at=((created_at or now) + timedelta(hours=6)).isoformat(),
                    urgency_bullet="Fresh quotation — high intent window", urgency_pts=18,
                    reason=f"New quotation just created — ₹{money_short(value)}. Reach out while interest is high.",
                    next_action="Call customer",
                    next_action_reason="Fresh quotation — strike while interest is highest.",
                    channel="call", tags=tags, days_since_contact=days_since_contact,
                )
            elif age_updated >= QUOTATION_INACTIVE_DAYS:
                upsert(
                    f"quotation_inactive:{q['id']}", "quotation_inactive", "quotation", cust,
                    quotation=q, value=value, due_at=now_iso(),
                    urgency_bullet=f"No response for {age_updated} days", urgency_pts=18,
                    reason=f"No response for {age_updated} days on a ₹{money_short(value)} quotation.",
                    next_action="Send WhatsApp",
                    next_action_reason="Customer has gone quiet — a nudge message often revives cold quotes.",
                    channel="whatsapp", tags=tags, days_since_contact=days_since_contact,
                )
```

Replace the entire block with:

```python
        if status in ("draft", "sent", "pending_approval") and created_at:
            q_floor_id = _followup_floor_id(q, None)
            due = quotation_followup_due_at(created_at, q_floor_id)
            if due:
                is_selection = q.get("doc_type") == "tiles_selection"
                age_created = age_days(created_at)
                upsert(
                    f"quotation_followup:{q['id']}", "quotation_followup", "quotation", cust,
                    quotation=q, value=value, due_at=due.isoformat(),
                    urgency_bullet=f"No follow-up since it was created {age_created} days ago", urgency_pts=20,
                    reason=(
                        f"{'Selection' if is_selection else 'Quotation'} created {age_created} day(s) ago — "
                        f"₹{money_short(value)}. Time to follow up."
                    ),
                    next_action="Call customer",
                    next_action_reason=f"{quotation_followup_delay_days(q_floor_id)}-day follow-up window has passed.",
                    channel="call", tags=tags, days_since_contact=days_since_contact,
                )
```

(`_followup_floor_id` is already defined earlier in this file and already used by every `upsert()` call — no new import needed.)

- [ ] **Step 12: Fix the `waiting_for_customer` stat**

In `backend/routes/followup_routes.py`, lines 114-116 currently read:

```python
    waiting_for_customer = sum(
        1 for d in docs if d.get("status") == "open" and d.get("rule_type") in ("quotation_inactive", "payment_partial")
    )
```

Replace with:

```python
    waiting_for_customer = sum(
        1 for d in docs if d.get("status") == "open" and d.get("rule_type") in ("quotation_followup", "payment_partial")
    )
```

- [ ] **Step 13: Fix the matching frontend filter**

In `frontend/app/(admin)/followups.tsx`, line 443 currently reads:

```typescript
      list = list.filter((f) => f.status === "open" && (f.rule_type === "quotation_inactive" || f.rule_type === "payment_partial"));
```

Replace with:

```typescript
      list = list.filter((f) => f.status === "open" && (f.rule_type === "quotation_followup" || f.rule_type === "payment_partial"));
```

- [ ] **Step 14: Update the integration test that assumed an immediate card**

In `backend/tests/integration/test_followups_v2.py`, `test_quotation_status_change_triggers_reconcile` (lines 98-120) asserted a `quotation_new`/`quotation_inactive` card appears the moment a fresh quotation is created — that's no longer true by design. Replace the whole method:

```python
    def test_quotation_status_change_triggers_reconcile(self, session, owner_token, catalog):
        payload = {
            "customer_id": catalog["customer"]["id"],
            "items": [_line(catalog["product"], 2)],
            "project_name": "TEST_reconcile_status_change",
        }
        r = session.post(f"{API}/quotations", json=payload, headers=_h(owner_token), timeout=20)
        assert r.status_code == 200, r.text
        quot = r.json()
        qid, qnum = quot["id"], quot["number"]

        r2 = session.patch(f"{API}/quotations/{qid}", json={"status": "sent"}, headers=_h(owner_token), timeout=20)
        assert r2.status_code == 200, r2.text

        # As of the 2026-07-27 floor-timed follow-up redesign, a same-day
        # quotation must NOT produce an automated quotation_followup card —
        # the first nudge is deferred to 4 days (ground floor) / 7 days
        # (first floor) after creation. Give the event-triggered reconcile
        # pass a moment to run, then confirm it correctly produced nothing
        # for this quotation yet.
        time.sleep(2)
        rows = session.get(f"{API}/followups", params={"q": qnum}, headers=_h(owner_token), timeout=15).json()
        matched = [row for row in rows if row.get("quotation_number") == qnum and row.get("rule_type") == "quotation_followup"]
        assert matched == [], "A same-day quotation must not surface a quotation_followup card yet"
```

- [ ] **Step 15: Run the full unit suite**

Run: `cd backend && pytest tests/unit -v`
Expected: all PASS, no collection errors (confirms `models.py` and `followup_engine.py` still import cleanly everywhere they're used, e.g. `test_followup_engine_floor_inheritance.py`, `test_followups_floor_scoping.py`).

- [ ] **Step 16: Commit**

```bash
git add backend/models.py backend/services/followup_engine.py backend/routes/followup_routes.py backend/tests/unit/test_followup_floor_timing.py backend/tests/integration/test_followups_v2.py "frontend/app/(admin)/followups.tsx"
git commit -m "feat: floor-timed follow-up rule replaces quotation_new/quotation_inactive"
```

---

### Task 2: Sort order — overdue and assigned-to-me always pinned to the top

**Files:**
- Modify: `backend/services/followup_engine.py` (add `_followup_sort_key` after `compute_bucket`, currently ending line 124)
- Modify: `backend/routes/followup_routes.py:35-39` (import), `:357` (sort call)
- Modify: `frontend/app/(admin)/followups.tsx:454`
- Create: `backend/tests/unit/test_followup_sort_order.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `_followup_sort_key(d: dict, current_user_id: Optional[str]) -> tuple` in `backend/services/followup_engine.py`, used by `list_followups` in `followup_routes.py`. No other task depends on this.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_followup_sort_order.py`:

```python
"""Regression test: the Follow-ups list — and, since dashboard.tsx's "Up
next" queue consumes GET /followups with no further re-sort, the Today
dashboard too — must never bury an overdue or assigned-to-me card behind a
higher-scored one. See
docs/superpowers/specs/2026-07-27-followups-revamp-design.md."""
from __future__ import annotations

from services.followup_engine import _followup_sort_key


def _fu(**kw):
    base = {"bucket": "today", "assigned_to": None, "priority_score": 50, "due_at": "2026-08-01T00:00:00Z"}
    base.update(kw)
    return base


def test_overdue_outranks_a_higher_score_in_a_later_bucket():
    overdue_low_score = _fu(bucket="overdue", priority_score=10)
    today_high_score = _fu(bucket="today", priority_score=90)
    ordered = sorted([today_high_score, overdue_low_score], key=lambda d: _followup_sort_key(d, None))
    assert ordered == [overdue_low_score, today_high_score]


def test_assigned_to_me_outranks_a_higher_score_in_the_same_bucket():
    mine = _fu(assigned_to="user-1", priority_score=40)
    someone_elses_higher_score = _fu(assigned_to="user-2", priority_score=95)
    ordered = sorted([someone_elses_higher_score, mine], key=lambda d: _followup_sort_key(d, "user-1"))
    assert ordered == [mine, someone_elses_higher_score]


def test_overdue_outranks_assigned_to_me_when_they_conflict():
    overdue_someone_elses = _fu(bucket="overdue", assigned_to="user-2", priority_score=10)
    mine_today = _fu(bucket="today", assigned_to="user-1", priority_score=99)
    ordered = sorted([mine_today, overdue_someone_elses], key=lambda d: _followup_sort_key(d, "user-1"))
    assert ordered == [overdue_someone_elses, mine_today]


def test_falls_back_to_priority_score_then_due_at():
    higher_score = _fu(priority_score=80, due_at="2026-08-05T00:00:00Z")
    lower_score_sooner_due = _fu(priority_score=60, due_at="2026-08-01T00:00:00Z")
    ordered = sorted([lower_score_sooner_due, higher_score], key=lambda d: _followup_sort_key(d, None))
    assert ordered == [higher_score, lower_score_sooner_due]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/unit/test_followup_sort_order.py -v`
Expected: FAIL with `ImportError: cannot import name '_followup_sort_key'`

- [ ] **Step 3: Implement `_followup_sort_key`**

In `backend/services/followup_engine.py`, add directly after the `compute_bucket` function (currently ends at line 124, right before the scoring section's comment banner):

```python
def _followup_sort_key(d: dict, current_user_id: Optional[str]) -> tuple:
    """Overdue always first (business-wide urgency, regardless of who it's
    assigned to), then cards assigned to the requesting user (so a
    manager's assignment is impossible to miss), then priority score, then
    soonest due. Used by GET /followups — see
    docs/superpowers/specs/2026-07-27-followups-revamp-design.md."""
    return (
        0 if d.get("bucket") == "overdue" else 1,
        0 if current_user_id and d.get("assigned_to") == current_user_id else 1,
        -(d.get("priority_score") or 0),
        d.get("due_at") or "",
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && pytest tests/unit/test_followup_sort_order.py -v`
Expected: 4 PASS

- [ ] **Step 5: Wire it into `list_followups`**

In `backend/routes/followup_routes.py`, the import block (lines 35-39) currently reads:

```python
from services.followup_engine import (
    RULE_DEFINITIONS, age_days, build_whatsapp_message, compute_bucket,
    ist_day_bounds_utc, money_short, parse_iso, reason_factors_for,
    reconcile_followups, score_followup,
)
```

Replace with:

```python
from services.followup_engine import (
    RULE_DEFINITIONS, _followup_sort_key, age_days, build_whatsapp_message,
    compute_bucket, ist_day_bounds_utc, money_short, parse_iso,
    reason_factors_for, reconcile_followups, score_followup,
)
```

Then, in `list_followups` (line 357), replace:

```python
    docs.sort(key=lambda d: (-(d.get("priority_score") or 0), d.get("due_at") or ""))
```

with:

```python
    docs.sort(key=lambda d: _followup_sort_key(d, user.id))
```

- [ ] **Step 6: Run the full unit suite**

Run: `cd backend && pytest tests/unit -v`
Expected: all PASS

- [ ] **Step 7: Apply the same ordering to the frontend's client-side sort**

`frontend/app/(admin)/followups.tsx`'s main list re-sorts the already-fetched items client-side (grouping by bucket happens after this, so this is what determines order *within* a bucket). Line 454 currently reads:

```typescript
    return [...list].sort((a, b) => (b.priority_score - a.priority_score) || (a.due_at || "").localeCompare(b.due_at || ""));
```

Replace with:

```typescript
    return [...list].sort((a, b) => {
      const mineA = a.assigned_to === staff?.id ? 0 : 1;
      const mineB = b.assigned_to === staff?.id ? 0 : 1;
      if (mineA !== mineB) return mineA - mineB;
      return (b.priority_score - a.priority_score) || (a.due_at || "").localeCompare(b.due_at || "");
    });
```

(No overdue tiebreak needed here — `sections` groups by `bucket` immediately after this sort using `SECTION_ORDER`, which already lists `"overdue"` first, so overdue cards already render in their own top section regardless of this sort's order. `staff` is already in this `useMemo`'s dependency array on the next line, so no dependency-array change is needed.)

- [ ] **Step 8: Manual verification**

Start the frontend dev server (`cd frontend && npm run start` or the project's existing preview workflow) and open Follow-ups as a staff user with at least one follow-up assigned to them and at least one overdue card assigned to someone else. Confirm: the overdue section renders first regardless of score; within the "Today" section, the card assigned to the logged-in user renders above a higher-scored card assigned to someone else.

- [ ] **Step 9: Commit**

```bash
git add backend/services/followup_engine.py backend/routes/followup_routes.py backend/tests/unit/test_followup_sort_order.py "frontend/app/(admin)/followups.tsx"
git commit -m "feat: overdue and assigned-to-me follow-ups always sort to the top"
```

---

### Task 3: Free rescheduling — quick push-day chips on every card

**Files:**
- Modify: `frontend/app/(admin)/followups.tsx` — main component (~line 386, new handler), `InboxSection` (~lines 1103-1152), `FollowupCard` (~lines 1247-1410), render call site (~lines 791-812)

**Interfaces:**
- Consumes: `PATCH /followups/{id}` (already exists, accepts `{ due_at: string }` — `backend/models.py`'s `FollowupUpdate`, unchanged).
- Produces: nothing consumed by later tasks.

No backend change — the `PATCH` endpoint used here already exists and is already exercised by the existing `assignFollowup`/`dismissFollowup`/`saveNote` handlers in this same file, so no new backend test is needed. This task is UI-only; there is no frontend test harness in this repo (confirmed: no `*.test.tsx` files, no jest config), so verification is manual.

- [ ] **Step 1: Add the `pushDue` handler**

In `frontend/app/(admin)/followups.tsx`, directly after the `customSnooze` handler (ends at line 386, right before `assignFollowup` begins), add:

```typescript
  const pushDue = useCallback(async (f: Followup, days: number) => {
    const dueIso = new Date(Date.now() + days * 86400000).toISOString();
    patchLocal(f.id, { due_at: dueIso });
    try { await api.patch(`/followups/${f.id}`, { due_at: dueIso }); toast.success(`Pushed ${days} day${days === 1 ? "" : "s"}`); refreshStatsQuiet(); }
    catch (e: any) { toast.error(e?.detail || "Could not reschedule"); loadList(); }
  }, [patchLocal, refreshStatsQuiet, loadList]);
```

- [ ] **Step 2: Thread `onPushDays` through `InboxSection`**

In `frontend/app/(admin)/followups.tsx`, `InboxSection`'s props (lines 1103-1114) currently read:

```typescript
function InboxSection({
  bucket, items, collapsed, onToggle, selectedId, assignees, rankMap, selectedIds, onToggleSelect,
  onSelect, onCall, onWhatsApp, onEmail, onComplete, onSnooze, onCustomSnooze, onAssign, onNote, onDismiss,
}: {
  bucket: Bucket; items: Followup[]; collapsed: boolean; onToggle: () => void; selectedId: string | null;
  assignees: Assignee[]; rankMap: Map<string, number>; selectedIds: Set<string>; onToggleSelect: (id: string) => void;
  onSelect: (f: Followup) => void;
  onCall: (f: Followup) => void; onWhatsApp: (f: Followup) => void; onEmail: (f: Followup) => void;
  onComplete: (f: Followup) => void; onSnooze: (f: Followup, preset: "15m" | "1h" | "tomorrow" | "next_week") => void;
  onCustomSnooze: (f: Followup) => void; onAssign: (f: Followup, userId: string) => void;
  onNote: (f: Followup) => void; onDismiss: (f: Followup) => void;
}) {
```

Replace with:

```typescript
function InboxSection({
  bucket, items, collapsed, onToggle, selectedId, assignees, rankMap, selectedIds, onToggleSelect,
  onSelect, onCall, onWhatsApp, onEmail, onComplete, onSnooze, onCustomSnooze, onPushDays, onAssign, onNote, onDismiss,
}: {
  bucket: Bucket; items: Followup[]; collapsed: boolean; onToggle: () => void; selectedId: string | null;
  assignees: Assignee[]; rankMap: Map<string, number>; selectedIds: Set<string>; onToggleSelect: (id: string) => void;
  onSelect: (f: Followup) => void;
  onCall: (f: Followup) => void; onWhatsApp: (f: Followup) => void; onEmail: (f: Followup) => void;
  onComplete: (f: Followup) => void; onSnooze: (f: Followup, preset: "15m" | "1h" | "tomorrow" | "next_week") => void;
  onCustomSnooze: (f: Followup) => void; onPushDays: (f: Followup, days: number) => void;
  onAssign: (f: Followup, userId: string) => void;
  onNote: (f: Followup) => void; onDismiss: (f: Followup) => void;
}) {
```

Then, in the same function's `FollowupCard` render (lines 1128-1146), add one line after `onCustomSnooze`:

```typescript
              onCustomSnooze={() => onCustomSnooze(f)}
              onPushDays={(days) => onPushDays(f, days)}
              onAssign={(uid) => onAssign(f, uid)}
```

- [ ] **Step 3: Wire it at the top-level render call site**

In `frontend/app/(admin)/followups.tsx`, the `<InboxSection>` render (lines 791-812) already passes `onCustomSnooze={setCustomSnoozeFor}` and `onAssign={assignFollowup}`. Add, directly after `onCustomSnooze={setCustomSnoozeFor}`:

```typescript
                  onCustomSnooze={setCustomSnoozeFor}
                  onPushDays={pushDue}
                  onAssign={assignFollowup}
```

- [ ] **Step 4: Add the push-chip button to `FollowupCard`**

In `frontend/app/(admin)/followups.tsx`, `FollowupCard`'s props (lines 1247-1254) currently read:

```typescript
function FollowupCard({
  f, active, assignees, rank, checked, onToggleSelect,
  onPress, onCall, onWhatsApp, onEmail, onComplete, onSnooze, onCustomSnooze, onAssign, onNote, onDismiss,
}: {
  f: Followup; active: boolean; assignees: Assignee[]; rank?: number; checked: boolean; onToggleSelect: () => void;
  onPress: () => void; onCall: () => void; onWhatsApp: () => void; onEmail: () => void;
  onComplete: () => void; onSnooze: (p: "15m" | "1h" | "tomorrow" | "next_week") => void;
  onCustomSnooze: () => void; onAssign: (userId: string) => void; onNote: () => void; onDismiss: () => void;
}) {
```

Replace with:

```typescript
function FollowupCard({
  f, active, assignees, rank, checked, onToggleSelect,
  onPress, onCall, onWhatsApp, onEmail, onComplete, onSnooze, onCustomSnooze, onPushDays, onAssign, onNote, onDismiss,
}: {
  f: Followup; active: boolean; assignees: Assignee[]; rank?: number; checked: boolean; onToggleSelect: () => void;
  onPress: () => void; onCall: () => void; onWhatsApp: () => void; onEmail: () => void;
  onComplete: () => void; onSnooze: (p: "15m" | "1h" | "tomorrow" | "next_week") => void;
  onCustomSnooze: () => void; onPushDays: (days: number) => void;
  onAssign: (userId: string) => void; onNote: () => void; onDismiss: () => void;
}) {
```

Then, in the actions row (lines 1346-1373), the existing Snooze `IconMenuButton` is immediately followed by the Assign `IconMenuButton`:

```typescript
            <IconMenuButton
              icon="clock" accessibilityLabel="Snooze" testID={`snooze-${f.id}`}
              items={[
                { label: "Snooze 15 min", icon: "clock", onPress: () => onSnooze("15m") },
                { label: "Snooze 1 hour", icon: "clock", onPress: () => onSnooze("1h") },
                { label: "Snooze till tomorrow", icon: "sunrise", onPress: () => onSnooze("tomorrow") },
                { label: "Snooze next week", icon: "calendar", onPress: () => onSnooze("next_week") },
                { label: "Custom snooze…", icon: "edit-2", onPress: onCustomSnooze },
              ]}
            />
            <IconMenuButton
              icon="user-plus" accessibilityLabel="Assign" testID={`assign-${f.id}`}
              items={assignees.map((a) => ({ label: `Assign to ${a.full_name}`, icon: "user" as FeatherName, onPress: () => onAssign(a.id) }))}
            />
```

Insert a new `IconMenuButton` between them:

```typescript
            <IconMenuButton
              icon="clock" accessibilityLabel="Snooze" testID={`snooze-${f.id}`}
              items={[
                { label: "Snooze 15 min", icon: "clock", onPress: () => onSnooze("15m") },
                { label: "Snooze 1 hour", icon: "clock", onPress: () => onSnooze("1h") },
                { label: "Snooze till tomorrow", icon: "sunrise", onPress: () => onSnooze("tomorrow") },
                { label: "Snooze next week", icon: "calendar", onPress: () => onSnooze("next_week") },
                { label: "Custom snooze…", icon: "edit-2", onPress: onCustomSnooze },
              ]}
            />
            <IconMenuButton
              icon="fast-forward" accessibilityLabel="Push follow-up date" testID={`push-${f.id}`}
              items={[
                { label: "Push +1 day", icon: "chevron-right", onPress: () => onPushDays(1) },
                { label: "Push +2 days", icon: "chevron-right", onPress: () => onPushDays(2) },
                { label: "Push +3 days", icon: "chevron-right", onPress: () => onPushDays(3) },
                { label: "Push +7 days", icon: "chevron-right", onPress: () => onPushDays(7) },
              ]}
            />
            <IconMenuButton
              icon="user-plus" accessibilityLabel="Assign" testID={`assign-${f.id}`}
              items={assignees.map((a) => ({ label: `Assign to ${a.full_name}`, icon: "user" as FeatherName, onPress: () => onAssign(a.id) }))}
            />
```

- [ ] **Step 5: Manual verification**

Start the frontend dev server and open Follow-ups. On any open card, open the new "Push follow-up date" menu (fast-forward icon, between Snooze and Assign) and click "Push +3 days". Confirm: a "Pushed 3 days" toast appears, the card's due date shown on the card updates to 3 days from now, and the card's `status` stays `open` (it does **not** move into the "Snoozed" section — only its due date changed). Reload the page and confirm the pushed date persisted.

- [ ] **Step 6: Commit**

```bash
git add "frontend/app/(admin)/followups.tsx"
git commit -m "feat: quick push-day chips for freely rescheduling any follow-up"
```

---

### Task 4: Walk-in → "Add to Follow-ups" on the customer detail screen

**Files:**
- Modify: `frontend/app/(admin)/customers/[id].tsx`

**Interfaces:**
- Consumes: `POST /followups` (already exists — `backend/routes/followup_routes.py`'s `create_followup`, accepts `{ customer_id, category, channel, reason, due_at }`, unchanged).
- Produces: nothing consumed by later tasks.

No backend change — reuses the existing manual-creation endpoint already used by `NewFollowupSheet` in `followups.tsx`. UI-only; verified manually.

- [ ] **Step 1: Add imports**

In `frontend/app/(admin)/customers/[id].tsx`, line 15-17 currently reads:

```typescript
import {
  Avatar, Badge, Button, Card, EmptyState, PageHeader,
  SegmentedControl, StatTile, StatusBadge,
} from "@/src/components/ui";
```

Replace with:

```typescript
import {
  Avatar, Badge, Button, Card, Chip, EmptyState, FormField, PageHeader,
  SegmentedControl, Sheet, StatTile, StatusBadge, TextField,
} from "@/src/components/ui";
```

- [ ] **Step 2: Add the `WalkInFollowupSheet` component**

In `frontend/app/(admin)/customers/[id].tsx`, add this new function directly above `export default function CustomerDetail()` (currently line 75):

```typescript
const WALK_IN_DAY_OPTIONS = [2, 4, 7, 14];

function WalkInFollowupSheet({ visible, onClose, customer, onCreate }: {
  visible: boolean; onClose: () => void; customer: Customer; onCreate: (payload: any) => Promise<void>;
}) {
  const [reason, setReason] = useState("Walk-in visit — no quotation yet.");
  const [days, setDays] = useState(4);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (visible) { setReason("Walk-in visit — no quotation yet."); setDays(4); }
  }, [visible]);

  const submit = async () => {
    if (!reason.trim()) { toast.error("Add a reason"); return; }
    setSaving(true);
    try {
      const dueIso = new Date(Date.now() + days * 86400000).toISOString();
      await onCreate({ customer_id: customer.id, category: "sales", channel: "call", reason: reason.trim(), due_at: dueIso });
    } finally { setSaving(false); }
  };

  return (
    <Sheet visible={visible} onClose={onClose} title="Add to Follow-ups" subtitle={customer.company || customer.name} width={420}
      footer={<>
        <Button label="Cancel" variant="secondary" onPress={onClose} size="md" />
        <View style={{ flex: 1 }} />
        <Button label="Add Reminder" variant="primary" icon="plus" loading={saving} onPress={submit} size="md" testID="walkin-followup-save" />
      </>}
    >
      <View style={{ padding: spacing.xl, gap: spacing.lg }}>
        <FormField label="Reason" required helper="What should the salesperson do and why?">
          <TextField value={reason} onChangeText={setReason} placeholder="e.g. Browsed tile samples, wants a quote next week" testID="walkin-followup-reason" />
        </FormField>
        <FormField label="Remind me in" helper="Defaults to 4 days — change it if the customer asked for something different">
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            {WALK_IN_DAY_OPTIONS.map((d) => (
              <Chip key={d} label={`${d} days`} active={days === d} onPress={() => setDays(d)} />
            ))}
          </View>
        </FormField>
      </View>
    </Sheet>
  );
}
```

- [ ] **Step 3: Add `toast` import**

Confirm `frontend/app/(admin)/customers/[id].tsx` already imports `toast` (it does, line 20: `import { toast } from "@/src/components/Toast";`) — no change needed here, just verifying the dependency `WalkInFollowupSheet` uses is already present.

- [ ] **Step 4: Add state and the create handler in `CustomerDetail`**

In `frontend/app/(admin)/customers/[id].tsx`, `CustomerDetail`'s state block (lines 80-90) currently ends with:

```typescript
  const [historyItemId, setHistoryItemId] = useState<string | null>(null);
```

Add directly after:

```typescript
  const [historyItemId, setHistoryItemId] = useState<string | null>(null);
  const [walkInSheet, setWalkInSheet] = useState(false);
```

Then, directly after the `load` callback's `useEffect` (line 113, `useEffect(() => { load(); }, [load]);`), add:

```typescript
  const createWalkInFollowup = useCallback(async (payload: any) => {
    try {
      await api.post("/followups", payload);
      toast.success("Follow-up added");
      setWalkInSheet(false);
    } catch (e: any) {
      toast.error(e?.detail || "Could not add follow-up");
    }
  }, []);
```

- [ ] **Step 5: Add the header button**

In `frontend/app/(admin)/customers/[id].tsx`, the `PageHeader`'s `actions` prop (lines 181-191) currently reads:

```typescript
        actions={
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Button
              icon="edit-2"
              label="Edit"
              variant="secondary"
              size="md"
              onPress={() => router.push(`/(admin)/customers/${customer.id}/edit` as any)}
            />
          </View>
        }
```

Replace with:

```typescript
        actions={
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Button
              icon="phone-call"
              label="Add to Follow-ups"
              variant="secondary"
              size="md"
              onPress={() => setWalkInSheet(true)}
              testID="add-to-followups-btn"
            />
            <Button
              icon="edit-2"
              label="Edit"
              variant="secondary"
              size="md"
              onPress={() => router.push(`/(admin)/customers/${customer.id}/edit` as any)}
            />
          </View>
        }
```

- [ ] **Step 6: Render the sheet**

In `frontend/app/(admin)/customers/[id].tsx`, the `HistorySheet` render (lines 544-548) is the last sheet before the closing `</SafeAreaView>`:

```typescript
      <HistorySheet
        visible={!!historyItemId}
        itemId={historyItemId}
        onClose={() => setHistoryItemId(null)}
      />
    </SafeAreaView>
  );
}
```

Add the new sheet directly after `HistorySheet` and before the closing tag:

```typescript
      <HistorySheet
        visible={!!historyItemId}
        itemId={historyItemId}
        onClose={() => setHistoryItemId(null)}
      />
      <WalkInFollowupSheet
        visible={walkInSheet}
        onClose={() => setWalkInSheet(false)}
        customer={customer}
        onCreate={createWalkInFollowup}
      />
    </SafeAreaView>
  );
}
```

(`customer` is guaranteed non-null at this point in the render — the function already early-returns above if `!customer`.)

- [ ] **Step 7: Manual verification**

Start the frontend dev server, open any customer's detail page, click "Add to Follow-ups", confirm the sheet opens with the reason pre-filled and "4 days" selected, change it to "7 days", type a reason, and save. Confirm a success toast appears and the sheet closes. Open Follow-ups and confirm the new card appears (it will be due in the future, so it will show under the correct bucket, not immediately actionable — that's expected).

- [ ] **Step 8: Commit**

```bash
git add "frontend/app/(admin)/customers/[id].tsx"
git commit -m "feat: add walk-in customers to Follow-ups from the customer detail screen"
```

---

### Task 5: Manager-only assignment tracking — backend endpoint

**Files:**
- Modify: `backend/routes/followup_routes.py` (imports at line 26, new helpers + endpoint)
- Create: `backend/tests/unit/test_followup_assignments.py`

**Interfaces:**
- Consumes: `require_min_role` from `backend/auth.py` (already exists, already used elsewhere — e.g. `backend/routes/customer_routes.py`'s `require_min_role("sales")`).
- Produces: `GET /followups/assignments` — Task 6's frontend screen consumes this endpoint's response shape: `{ id, assigned_to, assigned_to_name, customer_name, reason, category, status, bucket, days_pending, due_at, created_at }[]`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_followup_assignments.py`:

```python
"""Regression test: the manager-only assignment tracking view (GET
/followups/assignments) must (a) reject anyone below the manager role and
(b) shape/sort rows correctly — see
docs/superpowers/specs/2026-07-27-followups-revamp-design.md."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from auth import require_min_role
from models import UserPublic, now_iso
from routes import followup_routes as followups


def _user(role: str) -> UserPublic:
    return UserPublic(email="u@forge.app", full_name="U", role=role, floor_ids=["ground-floor", "first-floor"])


def test_sales_role_is_rejected():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_min_role("manager")(user=_user("sales")))
    assert exc.value.status_code == 403


def test_manager_role_is_allowed():
    user = asyncio.run(require_min_role("manager")(user=_user("manager")))
    assert user.role == "manager"


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


class _FakeFollowups:
    """Emulates just enough of Motor's find().to_list() to prove the
    endpoint's status filter works — real filtering happens in Mongo, this
    fake does the equivalent in Python so the test doesn't need a live DB.
    `list_assignments` calls floor_query(user, base); for a manager/owner/
    admin user (all-floor access) floor_query returns `base` unchanged (see
    backend/auth.py:299-306), so `query["status"]["$in"]` is always the
    right lookup for the test users used here."""

    def __init__(self, docs):
        self._docs = docs

    def find(self, query, _proj=None):
        allowed_statuses = set(query.get("status", {}).get("$in", []))
        self._filtered = [d for d in self._docs if d["status"] in allowed_statuses]
        return self

    async def to_list(self, _n):
        return self._filtered


def test_shapes_and_sorts_rows_oldest_open_first(monkeypatch):
    docs = [
        {"id": "f-done", "assigned_to": "u1", "assigned_to_name": "A", "customer_name": "C1",
         "reason": "R1", "category": "sales", "status": "done", "due_at": now_iso(),
         "created_at": _days_ago(10)},
        {"id": "f-open-recent", "assigned_to": "u1", "assigned_to_name": "A", "customer_name": "C2",
         "reason": "R2", "category": "sales", "status": "open", "due_at": now_iso(),
         "created_at": _days_ago(1)},
        {"id": "f-open-old", "assigned_to": "u1", "assigned_to_name": "A", "customer_name": "C3",
         "reason": "R3", "category": "sales", "status": "open", "due_at": now_iso(),
         "created_at": _days_ago(5)},
    ]

    class _Db:
        followups = _FakeFollowups(docs)

    monkeypatch.setattr(followups, "db", _Db())

    rows = asyncio.run(followups.list_assignments(include_completed=True, user=_user("manager")))

    assert [r["id"] for r in rows] == ["f-open-old", "f-open-recent", "f-done"]
    assert rows[0]["days_pending"] == 5


def test_excludes_completed_by_default(monkeypatch):
    docs = [
        {"id": "f-done", "assigned_to": "u1", "assigned_to_name": "A", "customer_name": "C1",
         "reason": "R1", "category": "sales", "status": "done", "due_at": now_iso(),
         "created_at": _days_ago(10)},
    ]

    class _Db:
        followups = _FakeFollowups(docs)

    monkeypatch.setattr(followups, "db", _Db())

    rows = asyncio.run(followups.list_assignments(include_completed=False, user=_user("manager")))
    assert rows == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/unit/test_followup_assignments.py -v`
Expected: FAIL — `test_sales_role_is_rejected` and `test_manager_role_is_allowed` pass immediately (they only exercise the pre-existing `require_min_role`), but the two `list_assignments` tests FAIL with `AttributeError: module 'routes.followup_routes' has no attribute 'list_assignments'`.

- [ ] **Step 3: Implement the endpoint**

In `backend/routes/followup_routes.py`, line 26 currently reads:

```python
from auth import floor_for_write, floor_query, get_current_user
```

Replace with:

```python
from auth import floor_for_write, floor_query, get_current_user, require_min_role
```

Then, add this directly after the `list_followups` function (ends at line 358, right before the `# Detail — powers the Customer Context Panel` banner):

```python
_ASSIGNMENT_STATUS_RANK = {"open": 0, "snoozed": 1, "done": 2, "dismissed": 2}


def _assignment_row(f: dict) -> dict:
    return {
        "id": f["id"], "assigned_to": f.get("assigned_to"), "assigned_to_name": f.get("assigned_to_name"),
        "customer_name": f.get("customer_name"), "reason": f.get("reason"), "category": f.get("category"),
        "status": f.get("status"), "bucket": compute_bucket(f),
        "days_pending": age_days(parse_iso(f.get("created_at"))),
        "due_at": f.get("due_at"), "created_at": f.get("created_at"),
    }


def _assignment_sort_key(row: dict) -> tuple:
    return (_ASSIGNMENT_STATUS_RANK.get(row["status"], 3), -row["days_pending"])


@router.get("/assignments")
async def list_assignments(
    include_completed: bool = False,
    user: UserPublic = Depends(require_min_role("manager")),
):
    """Who has what assigned, how long it's been pending, and whether it's
    done — manager/admin/owner only. See
    docs/superpowers/specs/2026-07-27-followups-revamp-design.md."""
    status_filter = ["open", "snoozed"] + (["done", "dismissed"] if include_completed else [])
    docs = await db.followups.find(
        floor_query(user, {"assigned_to": {"$ne": None}, "status": {"$in": status_filter}}),
        {"_id": 0},
    ).to_list(5000)
    rows = [_assignment_row(f) for f in docs]
    rows.sort(key=_assignment_sort_key)
    return rows
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && pytest tests/unit/test_followup_assignments.py -v`
Expected: 4 PASS

- [ ] **Step 5: Run the full unit suite**

Run: `cd backend && pytest tests/unit -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routes/followup_routes.py backend/tests/unit/test_followup_assignments.py
git commit -m "feat: manager-only GET /followups/assignments tracking endpoint"
```

---

### Task 6: Manager-only assignment tracking — frontend screen + entry point

**Files:**
- Create: `frontend/app/(admin)/followup-assignments.tsx`
- Modify: `frontend/app/(admin)/followups.tsx` (header actions)

**Interfaces:**
- Consumes: `GET /followups/assignments` from Task 5 — exact response shape `{ id, assigned_to, assigned_to_name, customer_name, reason, category, status, bucket, days_pending, due_at, created_at }[]`.

No backend change. New file is plain Expo Router file-based routing (no manual registration needed — `_layout.tsx` already renders `<Slot />`). UI-only; verified manually.

- [ ] **Step 1: Create the screen**

Create `frontend/app/(admin)/followup-assignments.tsx`:

```typescript
// BuildCon House · Follow-up Assignments — manager-only view of who has
// what assigned, how long it's been pending, and whether it's done.
// Backend: GET /followups/assignments (require_min_role("manager")).
import { useCallback, useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Avatar, Badge, EmptyState, Skeleton } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { useAuth } from "@/src/state/auth";
import { colors, spacing, type } from "@/src/theme/tokens";

type AssignmentRow = {
  id: string; assigned_to: string | null; assigned_to_name: string | null;
  customer_name: string; reason: string; category: string;
  status: "open" | "snoozed" | "done" | "dismissed"; bucket: string;
  days_pending: number; due_at: string; created_at: string;
};

const STATUS_TONE: Record<string, "brand" | "warning" | "success" | "neutral"> = {
  open: "brand", snoozed: "warning", done: "success", dismissed: "neutral",
};

const MANAGER_ROLES = ["owner", "admin", "manager"];

export default function FollowupAssignments() {
  const { staff } = useAuth();
  const [rows, setRows] = useState<AssignmentRow[] | null>(null);

  const load = useCallback(() => {
    api.get<AssignmentRow[]>("/followups/assignments")
      .then(setRows)
      .catch((e: any) => { toast.error(e?.detail || "Could not load assignments"); setRows([]); });
  }, []);

  useEffect(() => { load(); }, [load]);

  const allowed = !!staff && MANAGER_ROLES.includes(staff.role);
  if (!allowed) {
    return (
      <AdminPage title="Follow-up Assignments" overline="TEAM">
        <EmptyState icon="lock" title="Manager access only" subtitle="Ask an owner, admin or manager to share this view." />
      </AdminPage>
    );
  }

  return (
    <AdminPage title="Follow-up Assignments" overline="TEAM" subtitle="Who has what, how long it's been pending, and whether it's done.">
      {rows === null ? (
        <View style={{ gap: spacing.md }}>
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} h={56} />)}
        </View>
      ) : rows.length === 0 ? (
        <EmptyState icon="user-check" title="Nothing assigned" subtitle="Assignments will appear here once follow-ups are handed to someone." />
      ) : (
        <View style={styles.table}>
          {rows.map((r, i) => (
            <View key={r.id} style={[styles.row, i > 0 ? styles.rowBorder : null]}>
              <Avatar name={r.assigned_to_name || "—"} size={34} tone="brand" />
              <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
                <Text style={type.bodyMid} numberOfLines={1}>{r.assigned_to_name || "Unassigned"}</Text>
                <Text style={type.caption} numberOfLines={1}>{r.customer_name} · {r.reason}</Text>
              </View>
              <Text style={[type.bodySm, { width: 90, textAlign: "right" }]}>
                {r.days_pending} day{r.days_pending === 1 ? "" : "s"}
              </Text>
              <Badge label={r.status} tone={STATUS_TONE[r.status] || "neutral"} size="sm" />
            </View>
          ))}
        </View>
      )}
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  table: {
    borderRadius: 12, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary, overflow: "hidden",
  },
  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    paddingVertical: spacing.md, paddingHorizontal: spacing.lg,
  },
  rowBorder: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider },
});
```

- [ ] **Step 2: Add the entry-point button**

In `frontend/app/(admin)/followups.tsx`, add the router import — line 9 currently reads:

```typescript
import { Feather } from "@expo/vector-icons";
```

Replace with:

```typescript
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
```

Then, in `FollowupsScreen`, line 226 currently reads:

```typescript
  const { staff } = useAuth();
```

Replace with:

```typescript
  const { staff } = useAuth();
  const router = useRouter();
```

Then, in the `PageHeader`'s desktop `actions` branch (lines 638-649), currently:

```typescript
            <>
              <IconButton icon="rotate-cw" onPress={onRefresh} tone="surface" accessibilityLabel="Refresh" size={38} />
              <Button label="Automation Rules" icon="zap" variant="secondary" size="md" onPress={() => setRulesSheet(true)} />
              <Dropdown
                label="Export" icon="download" variant="secondary"
                items={[
                  { label: "Export as Excel (.xlsx)", icon: "file-text", onPress: () => doExport("xlsx") },
                  { label: "Export as CSV", icon: "file", onPress: () => doExport("csv") },
                ]}
              />
              <Button label="New Follow-up" icon="plus" variant="primary" size="md" onPress={() => setNewSheet(true)} testID="new-followup-btn" />
            </>
```

Replace with:

```typescript
            <>
              <IconButton icon="rotate-cw" onPress={onRefresh} tone="surface" accessibilityLabel="Refresh" size={38} />
              {staff && ["owner", "admin", "manager"].includes(staff.role) ? (
                <Button label="Team View" icon="users" variant="secondary" size="md" onPress={() => router.push("/(admin)/followup-assignments" as any)} testID="team-view-btn" />
              ) : null}
              <Button label="Automation Rules" icon="zap" variant="secondary" size="md" onPress={() => setRulesSheet(true)} />
              <Dropdown
                label="Export" icon="download" variant="secondary"
                items={[
                  { label: "Export as Excel (.xlsx)", icon: "file-text", onPress: () => doExport("xlsx") },
                  { label: "Export as CSV", icon: "file", onPress: () => doExport("csv") },
                ]}
              />
              <Button label="New Follow-up" icon="plus" variant="primary" size="md" onPress={() => setNewSheet(true)} testID="new-followup-btn" />
            </>
```

- [ ] **Step 3: Manual verification**

Start both the backend and frontend dev servers. Log in as a `sales` (or `warehouse`/`worker`) role user, open Follow-ups, and confirm the "Team View" button does not appear; if navigated to `/followup-assignments` directly by URL, confirm the "Manager access only" empty state renders (client-side) — separately confirm via a direct API call (e.g. browser devtools or curl with that user's token) that `GET /api/followups/assignments` returns `403`. Then log in as an `owner`/`admin`/`manager` role user, confirm the "Team View" button appears, click it, and confirm the assignments table renders with correct employee names, days-pending counts, and status badges matching what's visible in the main Follow-ups list.

- [ ] **Step 4: Commit**

```bash
git add "frontend/app/(admin)/followup-assignments.tsx" "frontend/app/(admin)/followups.tsx"
git commit -m "feat: manager-only Follow-up Assignments team view"
```
