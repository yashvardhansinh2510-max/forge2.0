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
    # Recording a payment is require_min_role("accounts") on the real endpoint
    # (routes/payment_routes.py:264). Sales sits below that, so the action must
    # be hidden, not shown and then failing.
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


def test_an_unknown_role_gets_no_actions_rather_than_all_of_them():
    """Failing open here would hand an unrecognised role every operation on
    the row."""
    assert row_dict(_row(), "not-a-real-role")["actions"] == []


def test_action_roles_are_real_roles_from_the_hierarchy():
    from auth import ROLE_HIERARCHY
    for action, min_role in ACTION_ROLES.items():
        assert min_role in ROLE_HIERARCHY, f"{action} declares unknown role {min_role}"


def test_a_row_with_no_priority_engine_output_carries_none():
    """Most rules (quotation_stalled, brand_declining, ...) have no equivalent
    to followup_engine.score_followup — priority_score must default to None,
    never a fabricated number standing in for "we don't know"."""
    d = row_dict(_row(), "owner")
    assert d["priority_score"] is None
    assert d["reason_factors"] == []


def test_a_followup_rows_real_priority_engine_output_is_carried_through():
    row = _row(priority_score=82, reason_factors=("₹5.4L at stake", "No contact for 9 days"))
    d = row_dict(row, "owner")
    assert d["priority_score"] == 82
    assert d["reason_factors"] == ["₹5.4L at stake", "No contact for 9 days"]
