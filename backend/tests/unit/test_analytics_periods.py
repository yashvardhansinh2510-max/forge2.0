"""Never +100%, never 0%, never a fabricated delta. When there is nothing to
compare against, say so."""
from __future__ import annotations

from datetime import datetime, timezone

from services.analytics.periods import (
    HISTORY_INSUFFICIENT,
    HISTORY_NO_PRIOR,
    HISTORY_OK,
    compare,
    previous,
    resolve,
)

NOW = datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc)


def test_today_starts_at_midnight_utc():
    p = resolve("today", now=NOW)
    assert p.start.startswith("2026-08-01T00:00:00")
    assert p.label == "Today"


def test_yesterday_is_a_full_closed_day():
    p = resolve("yesterday", now=NOW)
    assert p.start.startswith("2026-07-31T00:00:00")
    assert p.end.startswith("2026-08-01T00:00:00")


def test_this_week_starts_monday():
    # 2026-08-01 is a Saturday; the week starts Monday 2026-07-27.
    assert resolve("this_week", now=NOW).start.startswith("2026-07-27")


def test_last_n_days_preset():
    assert resolve("last_7_days", now=NOW).start.startswith("2026-07-26")


def test_this_month_starts_on_the_first():
    assert resolve("this_month", now=NOW).start.startswith("2026-08-01")


def test_last_month_is_the_whole_previous_month():
    p = resolve("last_month", now=NOW)
    assert p.start.startswith("2026-07-01")
    assert p.end.startswith("2026-08-01")


def test_custom_passes_the_supplied_bounds_through():
    p = resolve("custom", date_from="2026-01-01", date_to="2026-03-31", now=NOW)
    assert (p.start, p.end) == ("2026-01-01", "2026-03-31")


def test_all_is_an_open_window():
    p = resolve("all", now=NOW)
    assert p.start is None and p.end is None


def test_previous_period_is_the_immediately_preceding_equal_span():
    p = resolve("last_month", now=NOW)          # July
    prev = previous(p)
    assert prev.start.startswith("2026-06-01")
    assert prev.end.startswith("2026-07-01")


def test_previous_year_shifts_by_twelve_months():
    prev = previous(resolve("last_month", now=NOW), mode="year")
    assert prev.start.startswith("2025-07-01")


def test_previous_of_an_open_window_is_none():
    assert previous(resolve("all", now=NOW)) is None


def test_compare_reports_a_real_delta():
    result = compare(120.0, 100.0, prior_window_exists=True)
    assert result["delta_pct"] == 20.0
    assert result["direction"] == "up"
    assert result["history_state"] == HISTORY_OK


def test_compare_reports_a_decline():
    assert compare(75.0, 100.0, prior_window_exists=True)["direction"] == "down"


def test_empty_prior_window_is_not_a_hundred_percent_growth():
    result = compare(500.0, 0.0, prior_window_exists=True)
    assert result["delta_pct"] is None
    assert result["history_state"] == HISTORY_NO_PRIOR


def test_no_prior_window_at_all_is_insufficient_history():
    result = compare(500.0, 0.0, prior_window_exists=False)
    assert result["delta_pct"] is None
    assert result["history_state"] == HISTORY_INSUFFICIENT


def test_flat_is_a_real_zero_not_a_missing_comparison():
    result = compare(100.0, 100.0, prior_window_exists=True)
    assert result["delta_pct"] == 0.0
    assert result["direction"] == "flat"
    assert result["history_state"] == HISTORY_OK


def test_a_calendar_shift_off_a_31st_clamps_instead_of_crashing():
    """A month-over-month comparison of a window ending on the 31st has no
    31st to land on in a 30-day month. Clamp to the month's last day — the
    naive replace(month=...) raises ValueError and would 500 the endpoint."""
    p = resolve("last_31_days", now=datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc))
    prev = previous(p, mode="month")
    assert prev is not None
    assert prev.end.startswith("2026-07-31")


def test_a_leap_day_shifted_a_year_back_clamps_to_the_28th():
    p = resolve("custom", date_from="2024-02-29T00:00:00+00:00", date_to="2024-03-01T00:00:00+00:00")
    prev = previous(p, mode="year")
    assert prev.start.startswith("2023-02-28")


def test_an_unknown_comparison_mode_has_no_previous_window():
    assert previous(resolve("last_month", now=NOW), mode="fortnight") is None


def test_previous_of_a_calendar_quarter_steps_back_a_whole_quarter():
    """The calendar-aware step must use the window's own length in months, not
    assume one month: Apr-Jul compares against Jan-Apr."""
    p = resolve("custom", date_from="2026-04-01T00:00:00+00:00", date_to="2026-07-01T00:00:00+00:00")
    prev = previous(p)
    assert prev.start.startswith("2026-01-01")
    assert prev.end.startswith("2026-04-01")


def test_previous_of_a_month_to_date_window_stays_a_span_shift():
    """This month so far is not calendar-aligned at its end, so it compares
    against an equal-length span, not the whole previous month."""
    p = resolve("this_month", now=NOW)          # 1 Aug 00:00 -> 1 Aug 10:30
    prev = previous(p)
    assert prev.start.startswith("2026-07-31T13:30")
    assert prev.end.startswith("2026-08-01T00:00")
