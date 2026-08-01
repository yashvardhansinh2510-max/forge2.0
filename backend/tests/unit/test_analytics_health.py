"""One number the owner can audit. Weights renormalize over available
components; a score is never computed from an invented benchmark."""
from __future__ import annotations

from models import AnalyticsTargets
from services.analytics.health import COMPONENTS, health_score

ALL_SIGNALS = {
    "collection_health": 100.0,
    "overdue_money": 100.0,
    "pipeline_health": 100.0,
    "dispatch_health": 100.0,
    "followup_health": 100.0,
    "revenue_attainment": 100.0,
    "conversion_health": 100.0,
}


def test_the_seven_spec_components_exist_with_their_weights():
    weights = {c.key: c.weight for c in COMPONENTS}
    assert weights == {
        "collection_health": 20, "overdue_money": 10, "pipeline_health": 15,
        "dispatch_health": 10, "followup_health": 10, "revenue_attainment": 25,
        "conversion_health": 10,
    }


def test_weights_sum_to_one_hundred():
    total = 0
    for c in COMPONENTS:
        total += c.weight
    assert total == 100


def test_a_perfect_business_scores_one_hundred():
    result = health_score(ALL_SIGNALS, AnalyticsTargets(monthly_revenue_target=500000, target_conversion_pct=30))
    assert result["score"] == 100
    assert result["band"] == "Healthy"
    assert result["available"] == 7 and result["total"] == 7


def test_bands_follow_the_spec_boundaries():
    def band_of(value: float) -> str:
        signals = {k: value for k in ALL_SIGNALS}
        return health_score(signals, AnalyticsTargets(monthly_revenue_target=1, target_conversion_pct=1))["band"]
    assert band_of(85.0) == "Healthy"
    assert band_of(84.0) == "Watch"
    assert band_of(70.0) == "Watch"
    assert band_of(69.0) == "At risk"


def test_without_a_revenue_target_the_score_renormalizes_over_six_signals():
    # 6 of 7: the remaining weights (75) rescale to 100, so an all-100 business
    # still scores 100 rather than 75.
    signals = {**ALL_SIGNALS, "revenue_attainment": None}
    result = health_score(signals, AnalyticsTargets(target_conversion_pct=30))
    assert result["score"] == 100
    assert result["available"] == 6 and result["total"] == 7
    assert "revenue target" in result["missing_signal_note"].lower()


def test_renormalization_changes_the_weighting_not_just_the_denominator():
    # collection_health 100, everything else 0. With all 7 signals its share is
    # 20/100. Without the two target-backed ones it is 20/65.
    signals = {k: 0.0 for k in ALL_SIGNALS}
    signals["collection_health"] = 100.0
    full = health_score(signals, AnalyticsTargets(monthly_revenue_target=1, target_conversion_pct=1))["score"]
    partial = health_score({**signals, "revenue_attainment": None, "conversion_health": None}, AnalyticsTargets())["score"]
    assert full == 20
    assert partial == 31          # round(100 * 20/65)


def test_a_component_value_is_clamped_to_the_zero_hundred_band():
    # revenue at 300% of target is capped at 100 — an overshoot cannot mask a
    # failing component elsewhere.
    signals = {**{k: 0.0 for k in ALL_SIGNALS}, "revenue_attainment": 300.0}
    result = health_score(signals, AnalyticsTargets(monthly_revenue_target=1, target_conversion_pct=1))
    assert result["score"] == 25
    assert [c["value"] for c in result["components"] if c["key"] == "revenue_attainment"] == [100.0]


def test_every_component_reports_its_rule_and_destination_for_the_expander():
    result = health_score(ALL_SIGNALS, AnalyticsTargets(monthly_revenue_target=1, target_conversion_pct=1))
    for component in result["components"]:
        assert component["rule"], f"{component['key']} has no stated rule"
        assert component["destination"].startswith("/(admin)/")


def test_no_available_signals_at_all_returns_no_score_rather_than_zero():
    """Zero would read as "the business is failing"; the honest answer is that
    the score cannot be computed."""
    result = health_score({k: None for k in ALL_SIGNALS}, AnalyticsTargets())
    assert result["score"] is None
    assert result["band"] is None
    assert result["available"] == 0


def test_an_unavailable_component_is_reported_so_the_expander_can_explain_it():
    result = health_score({**ALL_SIGNALS, "dispatch_health": None}, AnalyticsTargets(monthly_revenue_target=1, target_conversion_pct=1))
    dispatch = next(c for c in result["components"] if c["key"] == "dispatch_health")
    assert dispatch["available"] is False and dispatch["value"] is None
    assert result["available"] == 6


def test_both_targets_missing_names_both_in_the_note():
    # gather.py yields None for a target-backed signal when the target is
    # unset, which is the only shape this pairing occurs in.
    signals = {**ALL_SIGNALS, "revenue_attainment": None, "conversion_health": None}
    note = health_score(signals, AnalyticsTargets())["missing_signal_note"].lower()
    assert "revenue target" in note and "conversion" in note
    assert "5 of 7" in note


def test_the_note_is_empty_when_every_signal_is_available():
    assert health_score(ALL_SIGNALS, AnalyticsTargets(monthly_revenue_target=1, target_conversion_pct=1))["missing_signal_note"] == ""
