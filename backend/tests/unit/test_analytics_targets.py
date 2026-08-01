"""Unset targets must be reported as unavailable, never defaulted to a
number — the Health Score renormalizes over available signals rather than
scoring against an invented benchmark."""
from __future__ import annotations

from models import AnalyticsTargets
from routes.analytics_settings_routes import available_target_signals


def test_defaults_leave_owner_declared_targets_unset():
    t = AnalyticsTargets()
    assert t.monthly_revenue_target is None
    assert t.target_conversion_pct is None
    assert t.target_collection_pct == 90
    assert t.payment_terms_days == 30


def test_no_owner_targets_means_neither_signal_is_available():
    assert available_target_signals(AnalyticsTargets()) == []


def test_revenue_target_enables_only_revenue_attainment():
    assert available_target_signals(AnalyticsTargets(monthly_revenue_target=500000)) == ["revenue_attainment"]


def test_both_targets_enable_both_signals():
    t = AnalyticsTargets(monthly_revenue_target=500000, target_conversion_pct=30)
    assert available_target_signals(t) == ["revenue_attainment", "conversion_health"]


def test_zero_is_not_a_target():
    # A zero revenue target would make attainment infinite; treat it as unset.
    assert available_target_signals(AnalyticsTargets(monthly_revenue_target=0)) == []
