"""Period resolution and the comparison engine.

The comparison logic is complete now and starts producing real numbers the
moment history accumulates — no future code change. Until then it reports
WHY a comparison is unavailable instead of inventing one.
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

HISTORY_OK = "ok"
HISTORY_NO_PRIOR = "no_prior_period"
HISTORY_INSUFFICIENT = "insufficient_history"


@dataclass(frozen=True)
class Period:
    start: Optional[str]
    end: Optional[str]
    label: str


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_months(dt: datetime, months: int) -> datetime:
    """Shift by calendar months, clamping the day to the target month's length.

    The 31st shifted back a month, or Feb 29 shifted back a year, has no
    equivalent day. replace(month=...) raises ValueError there, which would
    surface as a 500 on any MoM/YoY comparison of a window that happens to
    land on such a date.
    """
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    return dt.replace(year=year, month=month, day=min(dt.day, monthrange(year, month)[1]))


def _is_month_boundary(dt: datetime) -> bool:
    return dt.day == 1 and (dt.hour, dt.minute, dt.second, dt.microsecond) == (0, 0, 0, 0)


def _whole_months_between(start: datetime, end: datetime) -> int:
    """Months spanned when BOTH ends sit exactly on a month boundary, else 0.

    0 means "not calendar-aligned" — a to-date or arbitrary custom range,
    which compares against an equal span rather than a calendar step.
    """
    if not (_is_month_boundary(start) and _is_month_boundary(end)):
        return 0
    return (end.year - start.year) * 12 + (end.month - start.month)


def resolve(preset: str, date_from: Optional[str] = None, date_to: Optional[str] = None, now: Optional[datetime] = None) -> Period:
    """Turn a preset into a concrete window. `all` and an unknown preset both
    yield an open window rather than raising — a report with no date filter is
    a legitimate request."""
    if preset == "custom":
        return Period(date_from, date_to, "Custom range")

    now = now or datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if preset == "today":
        return Period(_iso(today), _iso(now), "Today")
    if preset == "yesterday":
        return Period(_iso(today - timedelta(days=1)), _iso(today), "Yesterday")
    if preset == "this_week":
        return Period(_iso(today - timedelta(days=today.weekday())), _iso(now), "This week")
    if preset.startswith("last_") and preset.endswith("_days"):
        days = int(preset.split("_")[1])
        return Period(_iso(today - timedelta(days=days - 1)), _iso(now), f"Last {days} days")
    if preset == "this_month":
        return Period(_iso(_month_start(today)), _iso(now), "This month")
    if preset == "last_month":
        end = _month_start(today)
        return Period(_iso(_add_months(end, -1)), _iso(end), "Last month")
    if preset == "quarter":
        start = today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return Period(_iso(start), _iso(now), "This quarter")
    if preset == "year":
        return Period(_iso(today.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)), _iso(now), "This year")
    return Period(None, None, "All time")


def previous(period: Period, mode: str = "period") -> Optional[Period]:
    """The window this one is compared against.

    "period" is the immediately preceding equal span; "month"/"quarter"/"year"
    shift by that calendar amount for MoM/QoQ/YoY. An open window has no
    previous — returns None, which compare() turns into insufficient_history.
    """
    if not period.start or not period.end:
        return None
    start = datetime.fromisoformat(period.start)
    end = datetime.fromisoformat(period.end)

    if mode == "period":
        months = _whole_months_between(start, end)
        if months:
            # A calendar-aligned window steps back by calendar months, not by
            # its own length in days: the month before a 31-day July is June,
            # not "the 31 days ending 1 July", which would start on 31 May and
            # double-count a day of June.
            return Period(_iso(_add_months(start, -months)), _iso(start), f"Previous {period.label.lower()}")
        span = end - start
        return Period(_iso(start - span), _iso(start), f"Previous {period.label.lower()}")
    shift = {"month": -1, "quarter": -3, "year": -12}.get(mode)
    if shift is None:
        return None
    return Period(_iso(_add_months(start, shift)), _iso(_add_months(end, shift)), f"{period.label} a {mode} ago")


def compare(current: float, previous_value: float, prior_window_exists: bool) -> dict:
    """Compare two periods, or explain why we cannot.

    prior_window_exists=False means there is no comparable window at all (an
    open-ended period, or a comparison reaching before the business has data).
    A prior window that exists but is empty is a different, equally honest
    answer: no_prior_period. Neither is ever rendered as +100%.
    """
    if not prior_window_exists:
        return {"delta_pct": None, "direction": None, "history_state": HISTORY_INSUFFICIENT}
    if not previous_value:
        return {"delta_pct": None, "direction": None, "history_state": HISTORY_NO_PRIOR}
    delta = round((current - previous_value) / previous_value * 100, 1)
    direction = "flat" if delta == 0 else ("up" if delta > 0 else "down")
    return {"delta_pct": delta, "direction": direction, "history_state": HISTORY_OK}
