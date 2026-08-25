"""Regression test: the Follow-ups list — and, since dashboard.tsx's "Up
next" queue consumes GET /followups with no further re-sort, the Today
dashboard too — must never bury an overdue or assigned-to-me card behind a
higher-scored one. See
docs/superpowers/specs/2026-07-27-followups-revamp-design.md."""
from __future__ import annotations

from services.followup_engine import _followup_sort_key


def _fu(**kw):
    base = {"bucket": "today", "status": "open", "assigned_to": None, "priority_score": 50, "due_at": "2026-08-01T00:00:00Z"}
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


def test_unresolved_outranks_a_completed_row_assigned_to_me():
    done_but_mine = _fu(status="done", assigned_to="user-1", priority_score=90)
    open_someone_elses = _fu(status="open", assigned_to="user-2", priority_score=10)
    ordered = sorted([done_but_mine, open_someone_elses], key=lambda d: _followup_sort_key(d, "user-1"))
    assert ordered == [open_someone_elses, done_but_mine]
