"""The mirror of Attention: where to grow. Same row shape, ranked by upside ₹,
same suppression rule for comparisons with no history."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.analytics import opportunity
from services.analytics.attention import THRESHOLDS

NOW = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def test_opportunity_rules_share_the_attention_threshold_block():
    # A second copy of these numbers is how two surfaces start disagreeing.
    assert opportunity.THRESHOLDS is THRESHOLDS


def test_partner_with_untouched_pipeline_fires():
    partners = [{
        "referrer_id": "r1", "referrer_name": "ABC Architects", "open_value": 1240000.0,
        "last_followup_at": _iso(21), "phone": "+919000000000",
    }]
    rows = opportunity.partner_untouched(partners, now=NOW, thresholds=THRESHOLDS)
    assert len(rows) == 1
    assert rows[0].impact == 1240000.0
    assert rows[0].kind == "opportunity"
    assert "schedule_followup" in rows[0].actions


def test_a_recently_contacted_partner_does_not_fire():
    partners = [{"referrer_id": "r1", "open_value": 1240000.0, "last_followup_at": _iso(2)}]
    assert opportunity.partner_untouched(partners, now=NOW, thresholds=THRESHOLDS) == []


def test_a_partner_with_no_open_pipeline_does_not_fire():
    partners = [{"referrer_id": "r1", "open_value": 0.0, "last_followup_at": _iso(90)}]
    assert opportunity.partner_untouched(partners, now=NOW, thresholds=THRESHOLDS) == []


def test_a_partner_never_contacted_still_fires():
    """No follow-up ever logged is the strongest version of "untouched", not a
    missing-data case to skip."""
    partners = [{"referrer_id": "r1", "referrer_name": "ABC", "open_value": 500000.0,
                 "last_followup_at": None, "first_open_quotation_at": _iso(40)}]
    assert len(opportunity.partner_untouched(partners, now=NOW, thresholds=THRESHOLDS)) == 1


def test_fast_growing_brand_fires_with_the_revenue_delta_as_upside():
    brands = [{"brand_id": "b1", "brand_name": "Qutone", "revenue": 900000.0, "previous": 400000.0, "prior_window_exists": True}]
    rows = opportunity.brand_growing(brands, now=NOW, thresholds=THRESHOLDS)
    assert len(rows) == 1 and rows[0].impact == 500000.0


def test_brand_growth_without_a_prior_window_is_suppressed():
    brands = [{"brand_id": "b1", "brand_name": "Qutone", "revenue": 900000.0, "previous": 0.0, "prior_window_exists": False}]
    assert opportunity.brand_growing(brands, now=NOW, thresholds=THRESHOLDS) == []


def test_approved_quotation_not_ordered_fires_after_the_threshold():
    quotations = [{"id": "q1", "number": "FQ-9", "status": "approved", "grand_total": 250000.0,
                   "customer_name": "Ravi", "customer_id": "c1", "updated_at": _iso(5)}]
    rows = opportunity.approved_not_ordered(quotations, now=NOW, thresholds=THRESHOLDS)
    assert len(rows) == 1 and rows[0].destination == "/(admin)/quotations/q1"


def test_an_approved_quotation_inside_the_grace_window_does_not_fire():
    quotations = [{"id": "q1", "status": "approved", "grand_total": 250000.0, "updated_at": _iso(1)}]
    assert opportunity.approved_not_ordered(quotations, now=NOW, thresholds=THRESHOLDS) == []


def test_high_intent_walkin_not_quoted_fires_inside_the_window_only():
    fresh = [{"id": "w1", "customer_name": "New Buyer", "customer_id": "c9", "budget": 300000.0,
              "interested_products": ["tiles"], "visited_at": _iso(3), "selection_quotation_id": None}]
    stale = [{**fresh[0], "id": "w2", "visited_at": _iso(30)}]
    assert len(opportunity.walkin_unquoted(fresh, now=NOW, thresholds=THRESHOLDS)) == 1
    assert opportunity.walkin_unquoted(stale, now=NOW, thresholds=THRESHOLDS) == []


def test_a_walkin_that_already_has_a_quotation_does_not_fire():
    walkins = [{"id": "w1", "budget": 300000.0, "interested_products": ["tiles"],
                "visited_at": _iso(3), "selection_quotation_id": "q1"}]
    assert opportunity.walkin_unquoted(walkins, now=NOW, thresholds=THRESHOLDS) == []


def test_a_walkin_with_no_stated_interest_is_not_high_intent():
    walkins = [{"id": "w1", "budget": 300000.0, "interested_products": [],
                "visited_at": _iso(3), "selection_quotation_id": None}]
    assert opportunity.walkin_unquoted(walkins, now=NOW, thresholds=THRESHOLDS) == []


def test_top_customer_gone_quiet_fires_past_the_inactive_threshold():
    customers = [{"customer_id": "c1", "customer_name": "JK", "last_order_at": _iso(200),
                  "average_order": 180000.0, "lifetime_revenue": 2400000.0, "phone": "+919000000000"}]
    rows = opportunity.customer_gone_quiet(customers, now=NOW, thresholds=THRESHOLDS)
    assert len(rows) == 1 and rows[0].impact == 180000.0
    assert rows[0].destination == "/(admin)/customers/c1"


def test_customer_likely_to_reorder_needs_a_derivable_cadence():
    """One historical order cannot establish a cadence — inventing one would
    manufacture an opportunity out of nothing."""
    one_order = [{"customer_id": "c1", "orders": 1, "mean_gap_days": None,
                  "last_order_at": _iso(90), "average_order": 100000.0, "has_open_quotation": False}]
    assert opportunity.customer_likely_to_reorder(one_order, now=NOW, thresholds=THRESHOLDS) == []

    repeat = [{"customer_id": "c1", "customer_name": "JK", "orders": 4, "mean_gap_days": 45,
               "last_order_at": _iso(60), "average_order": 100000.0, "has_open_quotation": False}]
    assert len(opportunity.customer_likely_to_reorder(repeat, now=NOW, thresholds=THRESHOLDS)) == 1


def test_a_customer_with_an_open_quotation_is_already_being_served():
    repeat = [{"customer_id": "c1", "orders": 4, "mean_gap_days": 45,
               "last_order_at": _iso(60), "average_order": 100000.0, "has_open_quotation": True}]
    assert opportunity.customer_likely_to_reorder(repeat, now=NOW, thresholds=THRESHOLDS) == []


def test_salesperson_underloaded_needs_someone_to_compare_against():
    single = [{"id": "u1", "full_name": "Rahul", "conversion_pct": 60.0, "open_quotations": 1, "average_order": 100000.0}]
    assert opportunity.salesperson_underloaded(single, now=NOW, thresholds=THRESHOLDS) == []


def test_salesperson_underloaded_fires_for_the_best_converter_with_the_lightest_load():
    people = [
        {"id": "u1", "full_name": "Rahul", "conversion_pct": 60.0, "open_quotations": 1, "average_order": 200000.0},
        {"id": "u2", "full_name": "Aarav", "conversion_pct": 20.0, "open_quotations": 9, "average_order": 100000.0},
    ]
    rows = opportunity.salesperson_underloaded(people, now=NOW, thresholds=THRESHOLDS)
    assert len(rows) == 1
    assert rows[0].entity["salesperson_id"] == "u1"
    assert rows[0].impact == 1600000.0        # 200000 x (9 - 1) capacity gap


def test_opportunity_rows_are_ranked_by_upside():
    data = opportunity.OpportunityInput(
        partners=[{"referrer_id": "r1", "referrer_name": "ABC", "open_value": 100000.0, "last_followup_at": _iso(30)}],
        brands=[{"brand_id": "b1", "brand_name": "Qutone", "revenue": 900000.0, "previous": 400000.0, "prior_window_exists": True}],
        quotations=[], walkins=[], customers=[], salespeople=[],
    )
    rows = opportunity.opportunity_rows(data, now=NOW)
    assert [r.impact for r in rows] == [500000.0, 100000.0]
    assert all(r.kind == "opportunity" for r in rows)


def test_no_opportunity_row_ever_has_zero_upside():
    data = opportunity.OpportunityInput(
        partners=[{"referrer_id": "r1", "open_value": 0.0, "last_followup_at": _iso(90)}],
        brands=[], quotations=[{"id": "q1", "status": "approved", "grand_total": 0.0, "updated_at": _iso(9)}],
        walkins=[], customers=[], salespeople=[],
    )
    assert opportunity.opportunity_rows(data, now=NOW) == []
