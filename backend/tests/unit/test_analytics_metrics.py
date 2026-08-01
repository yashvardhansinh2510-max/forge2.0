"""One definition per KPI. Line-level revenue sums the denormalized
net_amount so brand and product revenue reconcile to grand_total."""
from __future__ import annotations

from services.analytics.filters import AnalyticsFilter
from services.analytics.metrics import (
    METRIC_SOURCES,
    filter_signature,
    line_revenue_pipeline,
    outstanding_pipeline,
    revenue_pipeline,
)


def test_revenue_sums_grand_total():
    group = next(s["$group"] for s in revenue_pipeline({"status": "ordered"}) if "$group" in s)
    assert group["revenue"] == {"$sum": "$grand_total"}
    assert group["orders"] == {"$sum": 1}


def test_revenue_pipeline_starts_with_the_supplied_match():
    match = {"status": "ordered", "floor_id": {"$in": ["ground-floor"]}}
    assert revenue_pipeline(match)[0] == {"$match": match}


def test_line_revenue_sums_net_amount_not_qty_times_price():
    # qty x unit_price ignores the discount cascade — that is the drift this
    # whole layer exists to prevent.
    stages = line_revenue_pipeline({"status": "ordered"}, "items.product_id")
    group = next(s["$group"] for s in stages if "$group" in s)
    assert group["revenue"] == {"$sum": "$items.net_amount"}


def test_line_revenue_unwinds_items():
    assert {"$unwind": "$items"} in line_revenue_pipeline({}, "items.product_id")


def test_line_revenue_groups_by_the_requested_field():
    stages = line_revenue_pipeline({}, "items.category_id")
    group = next(s["$group"] for s in stages if "$group" in s)
    assert group["_id"] == "$items.category_id"


def test_outstanding_only_counts_completed_payments():
    # 23 of 31 live payments are "pending" — recorded, not received. Counting
    # those as collected would understate what the business is owed.
    stages = outstanding_pipeline({"status": "ordered"})
    lookup = next(s["$lookup"] for s in stages if "$lookup" in s)
    assert lookup["from"] == "payments"
    conditions = lookup["pipeline"][0]["$match"]["$expr"]["$and"]
    assert {"$eq": ["$status", "completed"]} in conditions
    assert {"$eq": ["$quotation_id", "$$qid"]} in conditions


def test_every_metric_declares_its_source_collections():
    for metric in ("revenue", "orders", "aov", "outstanding", "brand_revenue", "product_revenue", "customer_ltv"):
        assert METRIC_SOURCES[metric], f"{metric} has no declared sources"


def test_outstanding_reads_both_quotations_and_payments():
    assert set(METRIC_SOURCES["outstanding"]) == {"quotations", "payments"}


def test_filter_signature_is_stable_for_equal_filters():
    a = AnalyticsFilter(floor_id="ground-floor", preset="this_month")
    b = AnalyticsFilter(floor_id="ground-floor", preset="this_month")
    assert filter_signature(a) == filter_signature(b)


def test_filter_signature_differs_when_any_field_differs():
    a = AnalyticsFilter(floor_id="ground-floor")
    b = AnalyticsFilter(floor_id="first-floor")
    assert filter_signature(a) != filter_signature(b)


def test_filter_signature_covers_every_field_of_the_filter():
    """A field the signature ignores is a field that silently shares a cache
    entry across two different reports."""
    from dataclasses import fields

    base = AnalyticsFilter()
    for field in fields(AnalyticsFilter):
        current = getattr(base, field.name)
        changed = AnalyticsFilter(**{field.name: "zzz-probe" if current != "zzz-probe" else "other"})
        assert filter_signature(changed) != filter_signature(base), f"{field.name} is not in the signature"


def test_line_revenue_limit_is_applied_last():
    stages = line_revenue_pipeline({}, "items.product_id", limit=7)
    assert stages[-1] == {"$limit": 7}
    assert stages[-2] == {"$sort": {"revenue": -1}}
