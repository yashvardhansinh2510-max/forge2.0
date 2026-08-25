# Follow-ups revamp: floor-timed reminders, walk-ins, free rescheduling, priority sort, team view

Date: 2026-07-27
Status: approved by user, pending implementation plan

## Background

The Follow-ups workspace (`frontend/app/(admin)/followups.tsx`,
`backend/services/followup_engine.py`, `backend/routes/followup_routes.py`)
already has a deterministic, LLM-free scoring/reconciliation engine, manual
follow-up creation, assign, snooze (presets + custom date), bulk actions, and
a personal "Today" home (`frontend/app/(admin)/dashboard.tsx`, powered by the
same `GET /followups` endpoint). See
`memory/followups_ux_audit_and_redesign.md` for the prior UX audit — that
audit's presentation/IA findings (chrome-before-work, buried actions, etc.)
are **not** in scope here; this spec is a narrower set of business-rule and
workflow changes requested directly by the user:

1. A way to add a walk-in showroom visitor to Follow-ups.
2. Follow-up timing tied to which floor a quotation/selection was made on,
   not a fixed one-size-fits-all window.
3. Every follow-up — automated or manual — must be freely reschedulable
   ("push it 2 days", "remind me after 3 days"), not just closed/completed.
4. A follow-up that's overdue (missed) must be impossible to miss — pinned
   to the top of the queue, not buried by score.
5. A task assigned to a specific employee should be visible at the top of
   *their* queue immediately.
6. A manager-visible view of who has what assigned, how long it's been
   pending, and whether it's done.

Two floors exist today (`backend/auth.py`, `backend/models.py`): `ground-floor`
(Tiles — `doc_type` `tiles_selection` or `tiles_quotation`) and `first-floor`
(Sanitaryware — `doc_type` `standard`, the system-wide default). Both are
stored as `Quotation` documents; "selection" and "quotation" are two
`doc_type` values on the same collection, not separate models.

## Decisions made with the user

- **Floor decides the timer, not doc type.** Ground Floor (Tiles) — quotation
  or selection, either `doc_type` — surfaces a follow-up reminder **4 days**
  after creation. First Floor (Sanitary) — same, either `doc_type` —
  surfaces after **7 days**. (The user's original notes had a bullet that
  read "first floor, 4 days" which conflicts with two other bullets both
  saying "first floor, 7 days" — confirmed with the user that the 4-day
  bullet meant Ground Floor.)
- **Walk-ins are always an existing Customer record.** No new lightweight
  name+phone capture form — staff use the existing Customer create/detail
  flow (`frontend/app/(admin)/customers/new.tsx`, `[id].tsx`), then a new
  "Add to Follow-ups" action on the customer detail screen.
- **Assigned tasks pin to the top of the assignee's queue immediately**, not
  only once due.
- **Overdue also pins to the top**, ahead of everything else — a missed
  follow-up must be the first thing anyone sees, regardless of who it's
  assigned to.
- **Team view is a new screen, manager role and above only**
  (`require_min_role("manager")` — covers manager/admin/owner per
  `ROLE_HIERARCHY` in `backend/auth.py`).

## Design

### 1. Floor-timed follow-up rule (replaces `quotation_new` + `quotation_inactive`)

Today's engine (`backend/services/followup_engine.py`) fires `quotation_new`
almost immediately (within `QUOTATION_NEW_WINDOW_DAYS=2`) and then
`quotation_inactive` at `QUOTATION_INACTIVE_DAYS=3+` — two overlapping,
floor-blind cards for the same quotation. Both are retired in favor of one
floor-aware rule:

```python
FLOOR_FOLLOWUP_DAYS = {"ground-floor": 4, "first-floor": 7}
FOLLOWUP_DEFAULT_DAYS = 7  # fallback, matches the existing floor_id default
```

New rule type `quotation_followup` (added to `FollowupRuleType` in
`backend/models.py`, replacing `quotation_new`/`quotation_inactive` in
`RULE_DEFINITIONS`; the two retired literal values stay valid on the
`FollowupRuleType` type so historical rows already in the database keep
deserializing, they just stop being generated).

For each quotation with `status in ("draft", "sent", "pending_approval")`:
compute `delay_days = FLOOR_FOLLOWUP_DAYS.get(floor_inherit(q), FOLLOWUP_DEFAULT_DAYS)`.
Once `age_days(created_at) >= delay_days`, upsert a single
`quotation_followup:{id}` card with `due_at = created_at + delay_days days`
(a fixed timestamp, not "now" — so it reads as due exactly on day N, then
overdue after that if untouched). Label distinguishes selection vs
quotation in the reason text via `doc_type`. Same auto-resolve behavior as
today: the moment the quotation leaves that status range (ordered, or
expired/replaced), the card disappears from `desired` and auto-resolves on
the next reconcile pass — unchanged mechanism, just a different trigger
condition.

This is the only engine behavior change. `quotation_expiring`,
`quotation_expired`, `payment_overdue`, `payment_partial`,
`purchase_dispatched`, `purchase_delivered`, `customer_inactive`,
`shortage_reorder` are untouched.

### 2. Walk-in → "Add to Follow-ups"

New button on the customer detail screen
(`frontend/app/(admin)/customers/[id].tsx`). Opens the existing
`NewFollowupSheet` (already built in `followups.tsx`, currently only reachable
from the Follow-ups workspace) pre-filled with:
`customer_id` = this customer, `category="sales"`, `reason="Walk-in visit — no quotation yet."`,
`due_at` = now + 4 days (editable before saving, per §3 — staff can change
the date right there if e.g. the visitor says "call me next week").

No backend change: `POST /followups` (`create_followup` in
`followup_routes.py`) already accepts `due_at` and defaults sensibly. The
walk-in path is purely a new frontend entry point into an existing endpoint.

### 3. Reschedule anywhere, freely

Backend already supports arbitrary rescheduling two ways — `POST
/followups/{id}/snooze` with an explicit `until` ISO date (any date, not
just the four presets), and `PATCH /followups/{id}` with a new `due_at`
(status stays `open`). Both are already excluded from being overwritten by
the next `reconcile_followups()` pass (`patch = {k: v for k, v in
fields.items() if k != "due_at"}`, and `snoozed` rows are skipped entirely)
— so this is safe for automated cards too, not just manual ones.

What's missing is fast access. Add a row of quick push chips to every card
(list view and detail/context panel) — **+1d · +2d · +3d · +7d · pick a
date** — calling `PATCH /followups/{id}` with a computed `due_at`. This
sits alongside (not replacing) the existing snooze presets aimed at
same-day retiming (15m/1h). No new backend endpoint — the chips are a thin
UI layer over the existing `PATCH` route.

### 4 & 5. "Never lose one" sort order

Single sort-key change in `list_followups`
(`backend/routes/followup_routes.py`), which already backs both the main
Follow-ups list and the dashboard's "Up next" queue
(`GET /followups?limit=12` in `frontend/app/(admin)/dashboard.tsx`) — one
change, both surfaces fixed:

```python
docs.sort(key=lambda d: (
    0 if d["bucket"] == "overdue" else 1,
    0 if d.get("assigned_to") == user.id else 1,
    -(d.get("priority_score") or 0),
    d.get("due_at") or "",
))
```

Overdue is business-wide urgency, so it outranks everything, for everyone.
Within the same urgency tier, a task assigned to *you* surfaces before
unassigned/other people's tasks of the same or higher score. This
simultaneously satisfies "assigned tasks pin to the top of my Today list"
(true within their tier) and "a missed follow-up is impossible to miss"
(true globally).

### 6. Team assignment view (manager+)

New endpoint `GET /followups/assignments`
(`require_min_role("manager")` — manager/admin/owner) in
`followup_routes.py`. Returns every follow-up with a non-null `assigned_to`,
`status in ("open", "snoozed")` by default (an `include_completed` query
flag adds `done`/`dismissed` rows from the last 30 days), shaped as:

```
{ id, assigned_to, assigned_to_name, customer_name, reason, category,
  status, bucket, days_pending, due_at, created_at }
```

`days_pending = age_days(created_at)` — consistent with the `age_days`
helper already used everywhere else in the engine. Sorted oldest-pending
first within `status="open"`, then `"snoozed"`, then completed (if
included).

New frontend screen `frontend/app/(admin)/followup-assignments.tsx` — a flat
table: Employee · Customer/Task · Days pending · Status. Reachable via a
"Team view" button in the Follow-ups workspace header
(`frontend/app/(admin)/followups.tsx`), rendered only when
`ROLE_HIERARCHY[user.role] >= ROLE_HIERARCHY["manager"]` client-side (the
real gate is the backend's `require_min_role("manager")` — the client check
is just to avoid showing a button that 403s for sales/warehouse/worker
roles).

## Explicitly not touched

- The broader presentation/IA audit (`memory/followups_ux_audit_and_redesign.md`)
  — chrome density, card layout, bulk workflows, keyboard shortcuts, mobile
  gestures. Out of scope for this pass.
- `quotation_expiring` / `quotation_expired` / `payment_overdue` /
  `payment_partial` / `purchase_dispatched` / `purchase_delivered` /
  `customer_inactive` / `shortage_reorder` rules — unchanged.
- No schema migration for existing `quotation_new`/`quotation_inactive`
  rows already in the database — they remain valid, readable, actionable
  history; only new generation stops.
- No change to how snooze/assign/complete work today beyond the new quick
  push chips and the sort key — the underlying endpoints are reused as-is.

## Testing

Mirror existing patterns (`backend/tests/unit/`,
`backend/tests/integration/test_followups_v2.py`):

- `reconcile_followups()`: a ground-floor quotation created 3 days ago
  produces no `quotation_followup` card yet; at 4 days it does, with
  `due_at` = creation + 4 days. Same for first-floor at 6 vs 7 days.
- The card auto-resolves once the quotation's status leaves
  draft/sent/pending_approval, same as today's mechanism.
- A manually-pushed `due_at` on an open automated card survives the next
  `reconcile_followups()` pass unchanged.
- `list_followups` sort: an overdue low-score card ranks above a
  today-bucket high-score card; among equal bucket, a card assigned to the
  requesting user ranks above one that isn't.
- `GET /followups/assignments`: 403 for a `sales`/`warehouse`/`worker` role
  user; 200 with correct `days_pending` for `manager`/`admin`/`owner`.
- `POST /followups` from the walk-in entry point creates a card with
  `category="sales"` and the staff-chosen `due_at`.

Live verification: create a ground-floor tiles selection and a first-floor
quotation for two test customers, backdate `created_at` (or wait) to confirm
the 4-day/7-day split; use the new push chips on an automated card and
confirm reconcile doesn't reset it; open the Team view as a manager account
and as a sales account to confirm the role gate.

## Rollout

Single milestone. Additive engine rule change (no schema migration — new
`rule_type` literal value, existing rows untouched), one new backend
endpoint, one new frontend screen, sort-key and UI additions to existing
screens. Safe to revert via git if anything regresses.
