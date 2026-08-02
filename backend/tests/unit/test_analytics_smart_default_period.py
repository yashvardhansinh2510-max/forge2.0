"""The Sales Data page must never open onto an empty screen while a full
book sits one day the other side of a month boundary — but it must also never
silently redefine what "this month" means.

`smart_default_period` is the whole of that decision, and it is pure: the
route hands it the newest ordered_at it can see and renders whatever comes
back, so every rule below is testable without a database.
"""
from __future__ import annotations

from datetime import datetime, timezone

from services.analytics.periods import month_period, smart_default_period

# The live situation this was built for: the whole book is July, today is
# 2 August, and "this month" would render zeroes on every card.
AUG_2 = datetime(2026, 8, 2, 9, 30, tzinfo=timezone.utc)
JULY_LAST_ORDER = "2026-07-31T11:49:10.641527+00:00"


def test_the_current_month_wins_when_it_actually_contains_an_order():
    preset, period, fallback = smart_default_period("2026-08-01T10:00:00+00:00", now=AUG_2)
    assert preset == "this_month"
    assert fallback is False
    assert period.label == "This month"


def test_an_empty_current_month_falls_back_to_the_month_of_the_newest_order():
    preset, period, fallback = smart_default_period(JULY_LAST_ORDER, now=AUG_2)
    assert preset == "custom"
    assert fallback is True
    assert period.label == "July 2026"
    assert period.start == "2026-07-01T00:00:00+00:00"
    assert period.end == "2026-08-01T00:00:00+00:00"


def test_the_fallback_window_is_the_whole_calendar_month_not_a_rolling_30_days():
    """A rolling window would quietly change the meaning of every figure on
    the page; a calendar month is a period the owner can name."""
    _, period, _ = smart_default_period(JULY_LAST_ORDER, now=AUG_2)
    assert period == month_period(datetime(2026, 7, 15, tzinfo=timezone.utc))


def test_a_business_with_no_orders_at_all_gets_this_month_and_no_banner():
    """Claiming a fallback happened when there was nothing to fall back to
    would be a false statement to the owner."""
    preset, period, fallback = smart_default_period(None, now=AUG_2)
    assert (preset, fallback) == ("this_month", False)
    assert period.label == "This month"


def test_an_unparseable_stamp_degrades_to_this_month_instead_of_500ing():
    preset, _, fallback = smart_default_period("not-a-timestamp", now=AUG_2)
    assert (preset, fallback) == ("this_month", False)


def test_a_naive_timestamp_is_treated_as_utc_rather_than_crashing_the_compare():
    """Mongo docs written before the tz-aware migration carry no offset;
    comparing one against an aware datetime raises TypeError."""
    preset, _, fallback = smart_default_period("2026-07-31T11:49:10.641527", now=AUG_2)
    assert (preset, fallback) == ("custom", True)


def test_a_z_suffixed_stamp_is_accepted():
    preset, _, fallback = smart_default_period("2026-07-31T11:49:10Z", now=AUG_2)
    assert (preset, fallback) == ("custom", True)


def test_an_order_earlier_today_still_counts_as_this_month():
    preset, _, fallback = smart_default_period("2026-08-02T08:00:00+00:00", now=AUG_2)
    assert (preset, fallback) == ("this_month", False)


def test_the_first_instant_of_the_month_counts_as_this_month():
    """Boundary: an order stamped exactly at the month start is inside it."""
    preset, _, fallback = smart_default_period("2026-08-01T00:00:00+00:00", now=AUG_2)
    assert (preset, fallback) == ("this_month", False)


def test_a_year_old_book_falls_back_to_that_month_not_to_last_month():
    _, period, fallback = smart_default_period("2025-11-04T00:00:00+00:00", now=AUG_2)
    assert fallback is True
    assert period.label == "November 2025"


def test_month_period_spans_exactly_one_calendar_month_across_a_year_boundary():
    period = month_period(datetime(2026, 12, 20, tzinfo=timezone.utc))
    assert period.start == "2026-12-01T00:00:00+00:00"
    assert period.end == "2027-01-01T00:00:00+00:00"
    assert period.label == "December 2026"
