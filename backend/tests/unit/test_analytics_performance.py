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
