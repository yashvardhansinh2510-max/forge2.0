"""Pure shaping for the Collections workspace. Reuses metrics.outstanding_pipeline's
figures verbatim (spec: "no new definition") — this module only buckets and sorts
what gather_performance.py already fetched."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.analytics.collections import collections_by_age, collections_by_customer

NOW = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _row(**kw) -> dict:
    base = dict(customer_id="c1", customer_name="JK Enterprises", ordered_at=_iso(10), grand_total=300000.0, collected=100000.0)
    base.update(kw)
    return base


def test_outstanding_is_grand_total_minus_collected():
    rows = collections_by_customer([_row()], now=NOW)
    assert rows[0].outstanding == 200000.0


def test_a_fully_collected_order_is_excluded():
    rows = collections_by_customer([_row(grand_total=300000.0, collected=300000.0)], now=NOW)
    assert rows == []


def test_an_overpaid_order_is_also_excluded_not_negative():
    rows = collections_by_customer([_row(grand_total=300000.0, collected=310000.0)], now=NOW)
    assert rows == []


def test_sorted_by_outstanding_descending():
    rows = collections_by_customer([
        _row(customer_id="a", grand_total=100000.0, collected=0.0),
        _row(customer_id="b", grand_total=900000.0, collected=0.0),
    ], now=NOW)
    assert [r.customer_id for r in rows] == ["b", "a"]


def test_age_bucket_boundaries():
    exactly_30 = collections_by_customer([_row(customer_id="a", ordered_at=_iso(30))], now=NOW)
    exactly_31 = collections_by_customer([_row(customer_id="b", ordered_at=_iso(31))], now=NOW)
    assert exactly_30[0].age_bucket == "0-30"
    assert exactly_31[0].age_bucket == "31-60"


def test_a_90_plus_bucket_has_no_upper_bound():
    rows = collections_by_customer([_row(ordered_at=_iso(400))], now=NOW)
    assert rows[0].age_bucket == "90+"


def test_by_age_reports_every_bucket_even_when_empty():
    result = collections_by_age([_row(ordered_at=_iso(5))], now=NOW)
    assert set(result.keys()) == {"0-30", "31-60", "61-90", "90+"}
    assert result["31-60"] == {"count": 0, "outstanding": 0.0}


def test_by_age_totals_match_by_customer_totals():
    rows = [_row(customer_id="a", ordered_at=_iso(5), grand_total=100000.0, collected=0.0),
            _row(customer_id="b", ordered_at=_iso(95), grand_total=50000.0, collected=0.0)]
    by_age = collections_by_age(rows, now=NOW)
    total_from_age = sum(b["outstanding"] for b in by_age.values())
    total_from_customer = sum(r.outstanding for r in collections_by_customer(rows, now=NOW))
    assert total_from_age == total_from_customer == 150000.0


def test_an_unparseable_ordered_at_is_still_listed_but_unbucketed():
    rows = collections_by_customer([_row(ordered_at="not-a-date")], now=NOW)
    assert len(rows) == 1
    assert rows[0].age_days is None
    assert rows[0].age_bucket is None
    by_age = collections_by_age([_row(ordered_at="not-a-date")], now=NOW)
    assert sum(b["count"] for b in by_age.values()) == 0   # excluded from every bucket, money not silently dropped from the customer view above
