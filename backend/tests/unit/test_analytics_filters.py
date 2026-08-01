"""One match builder. Floor access is enforced here, and revenue-status
queries date by ordered_at rather than updated_at."""
from __future__ import annotations

import pytest

from services.analytics.filters import AnalyticsFilter, FloorAccessError, build_match, date_field_for

WINDOW = ("2026-07-01T00:00:00+00:00", "2026-07-31T23:59:59+00:00")


def test_ordered_status_dates_by_ordered_at():
    assert date_field_for("ordered") == "ordered_at"


def test_other_statuses_date_by_created_at():
    for status in ("draft", "sent", "approved", "any"):
        assert date_field_for(status) == "created_at"


def test_status_and_window_are_always_applied():
    m = build_match(AnalyticsFilter(), accessible_floors=None, window=WINDOW)
    assert m["status"] == "ordered"
    assert m["ordered_at"] == {"$gte": WINDOW[0], "$lte": WINDOW[1]}


def test_all_floors_for_an_unrestricted_user_adds_no_floor_clause():
    m = build_match(AnalyticsFilter(floor_id="all"), accessible_floors=None, window=WINDOW)
    assert "floor_id" not in m


def test_all_floors_for_a_restricted_user_is_limited_to_their_floors():
    m = build_match(AnalyticsFilter(floor_id="all"), accessible_floors=["ground-floor"], window=WINDOW)
    assert m["floor_id"] == {"$in": ["ground-floor"]}


def test_explicit_floor_is_applied():
    m = build_match(AnalyticsFilter(floor_id="ground-floor"), accessible_floors=None, window=WINDOW)
    assert m["floor_id"] == {"$in": ["ground-floor"]}


def test_floor_outside_the_callers_access_is_refused():
    with pytest.raises(FloorAccessError):
        build_match(AnalyticsFilter(floor_id="first-floor"), accessible_floors=["ground-floor"], window=WINDOW)


def test_entity_filters_map_to_their_stored_fields():
    f = AnalyticsFilter(salesperson_id="u1", customer_id="c1", referrer_id="r1", referrer_type="architect")
    m = build_match(f, accessible_floors=None, window=WINDOW)
    assert m["created_by"] == "u1"
    assert m["customer_id"] == "c1"
    assert m["referrer_id"] == "r1"
    assert m["referrer_type"] == "architect"


def test_brand_filter_uses_the_supplied_product_ids():
    m = build_match(AnalyticsFilter(brand_id="b1"), accessible_floors=None, window=WINDOW, product_ids=["p1", "p2"])
    assert m["items.product_id"] == {"$in": ["p1", "p2"]}


def test_brand_filter_with_no_matching_products_matches_nothing():
    # An empty $in must not silently widen to "all products".
    m = build_match(AnalyticsFilter(brand_id="b1"), accessible_floors=None, window=WINDOW, product_ids=[])
    assert m["items.product_id"] == {"$in": []}


def test_open_window_omits_the_date_clause():
    m = build_match(AnalyticsFilter(), accessible_floors=None, window=(None, None))
    assert "ordered_at" not in m


def test_status_any_drops_the_status_clause():
    m = build_match(AnalyticsFilter(status="any"), accessible_floors=None, window=WINDOW)
    assert "status" not in m


def test_an_empty_accessible_floor_list_matches_nothing():
    """A staff account assigned to zero floors is restricted, not unrestricted
    — `[]` must not be conflated with None ("sees everything")."""
    m = build_match(AnalyticsFilter(floor_id="all"), accessible_floors=[], window=WINDOW)
    assert m["floor_id"] == {"$in": []}


def test_a_half_open_window_keeps_only_the_bound_it_has():
    m = build_match(AnalyticsFilter(), accessible_floors=None, window=(WINDOW[0], None))
    assert m["ordered_at"] == {"$gte": WINDOW[0]}


def test_brand_filter_without_resolved_product_ids_adds_no_clause():
    """product_ids=None means the caller has not resolved the brand yet;
    silently matching every product would overstate that brand's revenue."""
    m = build_match(AnalyticsFilter(brand_id="b1"), accessible_floors=None, window=WINDOW)
    assert "items.product_id" not in m
