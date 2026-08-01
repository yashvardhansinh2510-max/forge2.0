"""The analytics gate never widens access, a FloorAccessError is a 403, and
the overview carries exactly the six above-the-fold elements."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from routes import executive_overview_routes as routes


def test_every_endpoint_requires_an_analytics_role():
    for name in ("overview", "health", "attention", "opportunities", "brief", "feed", "today"):
        route = next(r for r in routes.router.routes if r.path.endswith(f"/{name}"))
        assert route.dependant.dependencies, f"/{name} has no role dependency"


def test_a_cross_floor_request_is_a_403_not_a_500():
    from services.analytics.filters import FloorAccessError
    exc = routes._floor_error_to_http(FloorAccessError("first-floor"))
    assert isinstance(exc, HTTPException) and exc.status_code == 403


def test_the_overview_payload_has_exactly_the_six_above_the_fold_keys():
    # Spec §7: adding a seventh element requires amending the contract, so this
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
    sales_view = routes._serialize_rows([row], role="sales")
    assert "open" in manager_view[0]["actions"]
    assert set(manager_view[0]["actions"]) <= set(owner_view[0]["actions"])
    assert "record_payment" not in sales_view[0]["actions"]


def test_todays_priorities_is_the_same_rule_set_as_the_overview():
    """A rule can never fire in Today's Priorities and not in the Overview —
    they must call the same functions, not two lists."""
    import inspect
    source = inspect.getsource(routes)
    assert "attention_rows(" in source and "opportunity_rows(" in source
    assert "TODAY_RULES" not in source, "a second rule set was introduced"
    # Both surfaces funnel through one helper.
    assert source.count("async def _rows_for(") == 1


def test_the_brief_recommends_from_the_same_ranked_rows():
    import inspect
    brief_source = inspect.getsource(routes._brief)
    assert "_rows_for(" in brief_source, "the brief must not build its own rule list"
    assert "BRIEF_ACTION_LIMIT" in brief_source


def test_serialized_rows_are_ranked_by_impact():
    from services.analytics.rows import ActionRow

    def row(impact):
        return ActionRow(rule="r", kind="attention", headline="h", impact=impact, age_days=1,
                         context=[], destination="/(admin)/payments", actions=("open",), entity={})

    out = routes._serialize_rows([row(10.0), row(900.0), row(100.0)], role="owner")
    assert [r["impact"] for r in out] == [900.0, 100.0, 10.0]


def test_the_overview_row_limit_is_a_stated_constant_not_a_magic_number():
    assert routes.OVERVIEW_ROW_LIMIT > 0 and routes.BRIEF_ACTION_LIMIT == 3
