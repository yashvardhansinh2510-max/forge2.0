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
