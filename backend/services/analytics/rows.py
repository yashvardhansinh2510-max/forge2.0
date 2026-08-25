"""The one action-row shape shared by every actionable executive surface.

Attention (§9), Opportunity (§10), Today's Priorities (§14.2) and the Morning
Brief's recommended actions (§11) all emit this object from the same rules. If
each surface had its own row type they would drift, and the spec's guarantee —
"a rule can never fire here and not there" — would be unenforceable.

Actions are declared by the MINIMUM ROLE of the endpoint each one actually
calls, read from the routes themselves rather than assumed:

    record_payment      routes/payment_routes.py:264   require_min_role("accounts")
    assign              routes/followup_routes.py:578  get_current_user (any staff)
    schedule_followup   routes/followup_routes.py:534  get_current_user (any staff)
    whatsapp            routes/followup_routes.py:663  get_current_user (any staff)
    send_reminder       same contact endpoint          get_current_user (any staff)
    open / open_customer / open_po / call              navigation and dialling only

Corrected 2026-08-01 (Stage E, §18's live-permission check): `assign` was
declared "manager" from an unverified assumption in the original Task 1
pass, not from reading the real endpoint. `PATCH /followups/{id}` — the
actual reassignment path — has no role gate beyond authentication. The
error was over-restrictive (§14.1's failure direction is under-restrictive,
widening access), but a stated role requirement that doesn't match the
route it claims to describe is a correctness bug regardless of direction.

Sales Data is gated owner/admin/manager, but that gate must never widen access
to the underlying operation (§14.1 rule 1) — so the row filters its own actions
against the caller's real role, and an unrecognised role gets nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, get_args

from auth import ROLE_HIERARCHY

Action = Literal[
    "open",
    "open_customer",
    "open_po",
    "call",
    "whatsapp",
    "schedule_followup",
    "assign",
    "record_payment",
    "send_reminder",
]

# Action -> minimum role, matching require_min_role on the real endpoint.
ACTION_ROLES: dict[str, str] = {
    "open": "worker",
    "open_customer": "worker",
    "open_po": "worker",
    "call": "worker",
    "whatsapp": "worker",
    "send_reminder": "worker",
    "schedule_followup": "worker",
    "assign": "worker",
    "record_payment": "accounts",
}

RowKind = Literal["attention", "opportunity"]


@dataclass(frozen=True)
class ActionRow:
    """A problem or an opening, with the money at stake and a way to act on it.

    `impact` is rupees — the amount at risk for an attention row, the upside for
    an opportunity row. It is what every surface ranks by, so a row without one
    cannot be ranked and should never have been emitted.
    """

    rule: str
    kind: RowKind
    headline: str
    impact: float
    age_days: int | None
    context: list[tuple[str, str]]
    destination: str
    actions: tuple[str, ...]
    entity: dict[str, str] = field(default_factory=dict)
    history_state: str = "ok"
    # Today's Priorities (§14.2) stars reuse followup_engine.score_followup's
    # OUTPUT — already computed and stored on every Followup document — rather
    # than inventing a second priority scale. Only followup_overdue rows have
    # a real equivalent; every other rule leaves this None rather than
    # fabricating a number that class of row was never scored on.
    priority_score: int | None = None
    reason_factors: tuple[str, ...] = ()


def may_perform(action: str, role: str) -> bool:
    """Fails closed: an unknown action or an unknown role gets nothing."""
    required = ACTION_ROLES.get(action)
    if not required:
        return False
    return ROLE_HIERARCHY.get(role, 0) >= ROLE_HIERARCHY[required]


def rank(rows: list[ActionRow]) -> list[ActionRow]:
    """Impact first, then the oldest, then the rule name.

    Total and deterministic on purpose: the Overview shows the top few of the
    same list Today's Priorities shows in full, and an unstable order would let
    the two disagree about which rows those are.
    """
    return sorted(rows, key=lambda r: (-r.impact, -(r.age_days or 0), r.rule))


def row_dict(row: ActionRow, role: str) -> dict:
    """Serialize for the API, keeping only the actions this role may perform."""
    return {
        "rule": row.rule,
        "kind": row.kind,
        "headline": row.headline,
        "impact": row.impact,
        "age_days": row.age_days,
        "context": [list(pair) for pair in row.context],
        "destination": row.destination,
        "actions": [a for a in row.actions if may_perform(a, role)],
        "entity": dict(row.entity),
        "history_state": row.history_state,
        "priority_score": row.priority_score,
        "reason_factors": list(row.reason_factors),
    }


def rows_payload(rows: list[ActionRow], role: str) -> list[dict]:
    """Rank then serialize — the pairing every surface needs."""
    return [row_dict(row, role) for row in rank(rows)]


assert set(ACTION_ROLES) == set(get_args(Action)), "every Action must declare a role"
