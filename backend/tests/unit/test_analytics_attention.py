"""Only problems, each with a ₹ impact and a destination. Rules whose
comparison has no history are suppressed, never fired on a fabricated delta."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.analytics import attention

NOW = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def test_every_threshold_in_the_spec_has_a_constant():
    for key in (
        "QUOTATION_STALE_DAYS", "QUOTATION_HIGH_VALUE", "PAYMENT_OVERDUE_DAYS",
        "DISPATCH_WAITING_DAYS", "RELEASE_STUCK_DAYS", "SALESPERSON_INACTIVE_DAYS",
        "SUPPLIER_DELAY_DAYS", "BRAND_DECLINE_PCT", "REFERRER_QUIET_DAYS",
        "CUSTOMER_INACTIVE_DAYS", "BRAND_GROWTH_PCT", "PARTNER_UNTOUCHED_DAYS",
        "APPROVED_NOT_ORDERED_DAYS", "WALKIN_UNQUOTED_DAYS",
    ):
        assert key in attention.THRESHOLDS, f"{key} missing from the one constant block"


def test_the_spec_starting_values_are_the_defaults():
    t = attention.THRESHOLDS
    assert t["QUOTATION_STALE_DAYS"] == 7
    assert t["QUOTATION_HIGH_VALUE"] == 100000
    assert t["DISPATCH_WAITING_DAYS"] == 3
    assert t["RELEASE_STUCK_DAYS"] == 5
    assert t["SALESPERSON_INACTIVE_DAYS"] == 5
    assert t["BRAND_DECLINE_PCT"] == 25
    assert t["REFERRER_QUIET_DAYS"] == 60
    assert t["CUSTOMER_INACTIVE_DAYS"] == 180


def test_a_high_value_quotation_older_than_the_threshold_fires():
    quotations = [{
        "id": "q1", "number": "FQ-1", "status": "sent", "grand_total": 540000.0,
        "customer_name": "JK Enterprises", "customer_id": "c1", "created_by_name": "Rahul",
        "updated_at": _iso(9), "created_at": _iso(9), "referrer_name": "ABC Architects",
    }]
    rows = attention.quotation_stalled(quotations, now=NOW, thresholds=attention.THRESHOLDS)
    assert len(rows) == 1
    assert rows[0].impact == 540000.0
    assert rows[0].age_days == 9
    assert rows[0].destination == "/(admin)/quotations/q1"
    assert "open" in rows[0].actions and "call" in rows[0].actions


def test_a_fresh_quotation_does_not_fire():
    quotations = [{"id": "q1", "status": "sent", "grand_total": 540000.0, "created_at": _iso(1)}]
    assert attention.quotation_stalled(quotations, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_a_low_value_stale_quotation_does_not_fire():
    quotations = [{"id": "q1", "status": "sent", "grand_total": 5000.0, "created_at": _iso(30)}]
    assert attention.quotation_stalled(quotations, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_an_ordered_quotation_is_not_a_stalled_quotation():
    quotations = [{"id": "q1", "status": "ordered", "grand_total": 540000.0, "created_at": _iso(30)}]
    assert attention.quotation_stalled(quotations, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_payment_overdue_uses_the_owner_declared_terms():
    orders = [{
        "id": "q1", "number": "FQ-1", "customer_id": "c1", "customer_name": "Menon",
        "ordered_at": _iso(45), "grand_total": 300000.0, "collected": 60000.0,
    }]
    t = {**attention.THRESHOLDS, "PAYMENT_OVERDUE_DAYS": 30}
    rows = attention.payment_overdue(orders, now=NOW, thresholds=t)
    assert len(rows) == 1
    assert rows[0].impact == 240000.0          # outstanding, not order value
    assert rows[0].destination == "/(admin)/payments"


def test_a_fully_collected_order_is_never_overdue():
    orders = [{"id": "q1", "ordered_at": _iso(90), "grand_total": 300000.0, "collected": 300000.0}]
    assert attention.payment_overdue(orders, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_an_order_inside_the_terms_window_is_not_overdue():
    orders = [{"id": "q1", "ordered_at": _iso(10), "grand_total": 300000.0, "collected": 0.0}]
    t = {**attention.THRESHOLDS, "PAYMENT_OVERDUE_DAYS": 30}
    assert attention.payment_overdue(orders, now=NOW, thresholds=t) == []


def test_followup_overdue_fires_on_due_date_and_carries_its_value():
    followups = [{
        "id": "f1", "status": "open", "due_at": _iso(4), "value": 120000.0,
        "customer_name": "Ravi", "customer_id": "c1", "customer_phone": "+919000000000",
    }]
    rows = attention.followup_overdue(followups, now=NOW, thresholds=attention.THRESHOLDS)
    assert len(rows) == 1 and rows[0].impact == 120000.0
    assert rows[0].destination == "/(admin)/followups"
    assert "whatsapp" in rows[0].actions


def test_a_completed_followup_never_fires():
    followups = [{"id": "f1", "status": "completed", "due_at": _iso(40), "value": 120000.0}]
    assert attention.followup_overdue(followups, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_brand_decline_is_suppressed_when_there_is_no_prior_period():
    brands = [{"brand_id": "b1", "brand_name": "Dimore", "revenue": 100000.0, "previous": 0.0, "prior_window_exists": False}]
    assert attention.brand_declining(brands, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_brand_decline_fires_on_a_real_drop_and_reports_the_delta():
    brands = [{"brand_id": "b1", "brand_name": "Dimore", "revenue": 300000.0, "previous": 1000000.0, "prior_window_exists": True}]
    rows = attention.brand_declining(brands, now=NOW, thresholds=attention.THRESHOLDS)
    assert len(rows) == 1
    assert rows[0].impact == 700000.0
    assert rows[0].destination.startswith("/(admin)/sales-data/brands")


def test_a_small_brand_dip_does_not_fire():
    brands = [{"brand_id": "b1", "brand_name": "Dimore", "revenue": 900000.0, "previous": 1000000.0, "prior_window_exists": True}]
    assert attention.brand_declining(brands, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_supplier_delay_fires_past_expected_delivery():
    pos = [{"id": "po1", "number": "FPO-1", "supplier_name": "Dimore", "supplier_id": "s1",
            "expected_delivery_at": _iso(6), "status": "ordered", "total": 480000.0}]
    rows = attention.supplier_delayed(pos, now=NOW, thresholds=attention.THRESHOLDS)
    assert len(rows) == 1 and rows[0].age_days == 6
    assert rows[0].destination == "/(admin)/purchases"


def test_a_received_purchase_order_is_never_delayed():
    pos = [{"id": "po1", "expected_delivery_at": _iso(30), "status": "fully_received", "total": 480000.0}]
    assert attention.supplier_delayed(pos, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_dispatch_waiting_fires_on_ready_undispatched_material():
    items = [{"id": "i1", "purchase_order_id": "po1", "customer_name": "JK", "customer_order_id": "co1",
              "ready_at": _iso(6), "value": 220000.0, "boxes_ready": 12}]
    rows = attention.dispatch_waiting(items, now=NOW, thresholds=attention.THRESHOLDS)
    assert len(rows) == 1 and rows[0].impact == 220000.0
    assert rows[0].destination.startswith("/(admin)/tiles/orders")


def test_release_stuck_fires_on_an_unreleased_line():
    items = [{"id": "i1", "purchase_order_id": "po1", "brand_name": "Dimore",
              "ordered_at": _iso(9), "value": 90000.0, "boxes_pending": 20}]
    rows = attention.release_stuck(items, now=NOW, thresholds=attention.THRESHOLDS)
    assert len(rows) == 1 and rows[0].impact == 90000.0


def test_salesperson_inactive_fires_with_their_open_pipeline_as_impact():
    people = [{"id": "u1", "full_name": "Rahul", "last_activity_at": _iso(12), "open_pipeline": 850000.0}]
    rows = attention.salesperson_inactive(people, now=NOW, thresholds=attention.THRESHOLDS)
    assert len(rows) == 1 and rows[0].impact == 850000.0


def test_an_active_salesperson_does_not_fire():
    people = [{"id": "u1", "full_name": "Rahul", "last_activity_at": _iso(1), "open_pipeline": 850000.0}]
    assert attention.salesperson_inactive(people, now=NOW, thresholds=attention.THRESHOLDS) == []


def test_referrer_quiet_fires_past_the_threshold():
    referrers = [{"referrer_id": "r1", "referrer_name": "ABC Architects",
                  "last_referral_at": _iso(90), "monthly_revenue": 400000.0}]
    rows = attention.referrer_quiet(referrers, now=NOW, thresholds=attention.THRESHOLDS)
    assert len(rows) == 1 and rows[0].impact == 400000.0


def test_attention_rows_returns_every_rule_ranked_by_impact():
    data = attention.AttentionInput(
        quotations=[{"id": "q1", "status": "sent", "grand_total": 540000.0, "created_at": _iso(9), "customer_name": "JK"}],
        orders=[{"id": "q2", "ordered_at": _iso(45), "grand_total": 300000.0, "collected": 0.0, "customer_name": "Menon"}],
        followups=[], ready_items=[], unreleased_items=[], salespeople=[],
        purchase_orders=[], brands=[], referrers=[],
    )
    rows = attention.attention_rows(data, now=NOW)
    assert [r.impact for r in rows] == sorted([r.impact for r in rows], reverse=True)
    assert {r.rule for r in rows} == {"quotation_stalled", "payment_overdue"}


def test_no_rule_ever_returns_a_row_with_zero_impact():
    """A row with no ₹ impact cannot be ranked and gives the owner nothing to
    weigh — the rule should not have fired."""
    data = attention.AttentionInput(
        quotations=[{"id": "q1", "status": "sent", "grand_total": 0.0, "created_at": _iso(30)}],
        orders=[{"id": "q2", "ordered_at": _iso(90), "grand_total": 0.0, "collected": 0.0}],
        followups=[{"id": "f1", "status": "open", "due_at": _iso(9), "value": 0.0}],
        ready_items=[], unreleased_items=[], salespeople=[], purchase_orders=[], brands=[], referrers=[],
    )
    assert attention.attention_rows(data, now=NOW) == []


def test_a_missing_timestamp_never_fires_a_rule_and_never_raises():
    """Real documents predate half these fields. An unknown age must not be
    treated as infinitely old."""
    data = attention.AttentionInput(
        quotations=[{"id": "q1", "status": "sent", "grand_total": 540000.0}],
        orders=[{"id": "q2", "grand_total": 300000.0, "collected": 0.0}],
        followups=[{"id": "f1", "status": "open", "value": 120000.0}],
        ready_items=[{"id": "i1", "value": 220000.0}],
        unreleased_items=[{"id": "i2", "value": 90000.0}],
        salespeople=[{"id": "u1", "open_pipeline": 850000.0}],
        purchase_orders=[{"id": "po1", "status": "ordered", "total": 480000.0}],
        brands=[], referrers=[{"referrer_id": "r1", "monthly_revenue": 400000.0}],
    )
    assert attention.attention_rows(data, now=NOW) == []


def test_every_row_carries_at_least_one_action():
    data = attention.AttentionInput(
        quotations=[{"id": "q1", "status": "sent", "grand_total": 540000.0, "created_at": _iso(9)}],
        orders=[], followups=[], ready_items=[], unreleased_items=[], salespeople=[],
        purchase_orders=[], brands=[], referrers=[],
    )
    rows = attention.attention_rows(data, now=NOW)
    assert rows and all(r.actions for r in rows)


def test_overdue_is_strict_not_day_floored():
    """A follow-up due at 09:00, read at 15:00, is overdue. age_days floors to
    whole days and would call it on time — live verification found 115 of 246
    open follow-ups in exactly that state, inflating the Health Score."""
    from datetime import timedelta
    due_this_morning = (NOW - timedelta(hours=6)).isoformat()
    assert attention.is_overdue(due_this_morning, NOW) is True
    assert attention.age_days(due_this_morning, NOW) == 0
    assert attention.is_overdue((NOW + timedelta(hours=6)).isoformat(), NOW) is False
    assert attention.is_overdue(None, NOW) is False


def test_the_alarm_waits_out_its_grace_period_but_health_does_not():
    """Two different questions, one explicit constant — not an accident of
    rounding. The alarm holds off for a day; is_overdue fires immediately."""
    from datetime import timedelta
    due_hours_ago = (NOW - timedelta(hours=6)).isoformat()
    followups = [{"id": "f1", "status": "open", "due_at": due_hours_ago, "value": 120000.0}]
    assert attention.followup_overdue(followups, now=NOW, thresholds=attention.THRESHOLDS) == []
    assert attention.is_overdue(due_hours_ago, NOW) is True

    due_two_days_ago = (NOW - timedelta(days=2)).isoformat()
    fired = attention.followup_overdue(
        [{"id": "f2", "status": "open", "due_at": due_two_days_ago, "value": 120000.0}],
        now=NOW, thresholds=attention.THRESHOLDS,
    )
    assert len(fired) == 1
