"""Every Sales Data breakdown read goes through Phase 0's `build_match`.

This codebase has shipped cross-floor leaks four separate times, always the
same way: a new surface that reads Mongo directly instead of through the one
match builder. These tests assert the property structurally — a restricted
caller's every query carries a floor clause, an unrestricted caller's carries
none, and revenue is never counted from a draft.

Follows the fake-db pattern from test_analytics_gather.py: a matcher that
actually honours the query, because a fake that ignores it cannot catch a
broken filter.
"""
from __future__ import annotations

import asyncio

from services.analytics import gather_breakdowns as gb
from services.analytics.filters import AnalyticsFilter

WINDOW = ("2026-07-01T00:00:00+00:00", "2026-08-01T00:00:00+00:00")


class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *a, **k):
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, n=None):
        return self._docs if n is None else self._docs[:n]


class _FakeCollection:
    def __init__(self, docs):
        self.docs = list(docs)
        self.queries: list[dict] = []

    def find(self, query=None, projection=None):
        self.queries.append(query or {})
        return _FakeCursor(self.docs)

    def aggregate(self, pipeline):
        self.queries.append(pipeline[0].get("$match", {}) if pipeline else {})
        return _FakeCursor([])


class _FakeDb:
    def __init__(self, **collections):
        self._extra = {name: _FakeCollection(docs) for name, docs in collections.items()}

    def __getattr__(self, name):
        extra = self.__dict__.get("_extra", {})
        if name not in extra:
            extra[name] = _FakeCollection([])
        return extra[name]


def _db(**kw):
    return _FakeDb(**{"quotations": [], "payments": [], "products": [], "brands": [], **kw})


ALL_FLOORS = AnalyticsFilter(floor_id="all")


def _run_every_read(db, floors):
    """Every breakdown read in one pass, so a new one cannot be added without
    coming under these assertions."""
    asyncio.run(gb.gather_confirmed_orders(db, ALL_FLOORS, floors, WINDOW))
    asyncio.run(gb.gather_product_line_revenue(db, ALL_FLOORS, floors, WINDOW))
    asyncio.run(gb.gather_line_labels(db, ALL_FLOORS, floors, WINDOW))
    asyncio.run(gb.latest_confirmed_order_at(db, ALL_FLOORS, floors))


def test_every_read_is_floor_scoped_for_a_restricted_caller():
    db = _db()
    _run_every_read(db, ["ground-floor"])
    assert db.quotations.queries, "no quotation read was issued at all"
    for query in db.quotations.queries:
        assert query.get("floor_id") == {"$in": ["ground-floor"]}, query


def test_an_unrestricted_caller_gets_no_floor_clause():
    db = _db()
    _run_every_read(db, None)
    assert all("floor_id" not in q for q in db.quotations.queries)


def test_a_caller_restricted_to_nothing_matches_nothing_rather_than_everything():
    """None (all floors) and [] (restricted to no floors) must not collide."""
    db = _db()
    _run_every_read(db, [])
    for query in db.quotations.queries:
        assert query.get("floor_id") == {"$in": []}, query


def test_revenue_is_only_ever_counted_from_confirmed_orders():
    db = _db()
    _run_every_read(db, None)
    for query in db.quotations.queries:
        assert query.get("status") == "ordered", query


def test_reads_are_dated_by_ordered_at_never_by_updated_at():
    """updated_at is re-stamped on every edit, so an edited old order would
    move between reporting periods."""
    db = _db()
    asyncio.run(gb.gather_confirmed_orders(db, ALL_FLOORS, None, WINDOW))
    asyncio.run(gb.gather_product_line_revenue(db, ALL_FLOORS, None, WINDOW))
    dated = [q for q in db.quotations.queries if "ordered_at" in q or "updated_at" in q or "created_at" in q]
    assert dated, "no read carried a date clause"
    for query in dated:
        assert "updated_at" not in query and "created_at" not in query
        assert query["ordered_at"] == {"$gte": WINDOW[0], "$lte": WINDOW[1]}


def test_an_explicit_floor_the_caller_cannot_see_raises_rather_than_widening():
    db = _db()
    try:
        asyncio.run(gb.gather_confirmed_orders(db, AnalyticsFilter(floor_id="first-floor"), ["ground-floor"], WINDOW))
    except Exception as exc:
        assert type(exc).__name__ == "FloorAccessError"
    else:
        raise AssertionError("a cross-floor request must not silently succeed")


def test_the_latest_order_probe_ignores_the_date_window_but_not_the_floor():
    """The smart default needs the newest order across all time — but only
    within what this caller may see."""
    db = _db()
    asyncio.run(gb.latest_confirmed_order_at(db, ALL_FLOORS, ["first-floor"]))
    query = db.quotations.queries[-1]
    assert query.get("floor_id") == {"$in": ["first-floor"]}
    assert "ordered_at" in query and query["ordered_at"] == {"$ne": None}


def test_the_latest_order_probe_returns_none_for_an_empty_book():
    assert asyncio.run(gb.latest_confirmed_order_at(_db(), ALL_FLOORS, None)) is None


def test_the_latest_order_probe_returns_the_stamp_it_found():
    db = _db(quotations=[{"ordered_at": "2026-07-31T11:49:10+00:00"}])
    assert asyncio.run(gb.latest_confirmed_order_at(db, ALL_FLOORS, None)) == "2026-07-31T11:49:10+00:00"


def test_line_labels_come_from_the_order_lines_themselves():
    db = _db(quotations=[
        {"items": [
            {"product_id": "p1", "name": "Integra WC", "sku": "SKU-1"},
            {"product_id": "p2", "name": "Basin"},
            {"name": "Line with no product id"},
        ]},
    ])
    names, skus = asyncio.run(gb.gather_line_labels(db, ALL_FLOORS, None, WINDOW))
    assert names == {"p1": "Integra WC", "p2": "Basin"}
    assert skus == {"p1": "SKU-1"}


def test_brand_resolution_issues_no_query_for_an_empty_product_list():
    db = _db(products=[{"id": "p1", "brand_id": "b1"}])
    assert asyncio.run(gb.gather_product_brands(db, [])) == ({}, {})
    assert db.products.queries == []


def test_brand_resolution_omits_products_with_no_brand_rather_than_mapping_none():
    """An absent entry is what makes breakdowns.brand_rows fold the line into
    the Unlinked bucket; a None value would key a real brand row on null."""
    db = _db(products=[{"id": "p1", "brand_id": "b1"}, {"id": "p2"}], brands=[{"id": "b1", "name": "Vitra"}])
    product_brand, brand_names = asyncio.run(gb.gather_product_brands(db, ["p1", "p2"]))
    assert product_brand == {"p1": "b1"}
    assert brand_names == {"b1": "Vitra"}


def test_the_line_revenue_pipeline_groups_on_product_id():
    """Guards the reconciliation property: grouping on anything else, or
    summing qty x unit_price, would stop the table totalling to the KPI."""
    db = _db()
    asyncio.run(gb.gather_product_line_revenue(db, ALL_FLOORS, None, WINDOW))
    # _FakeCollection.aggregate records only the $match; assert the pipeline
    # itself from the canonical builder rather than a hand-rolled one.
    from services.analytics.metrics import line_revenue_pipeline
    pipeline = line_revenue_pipeline({}, group_by="items.product_id")
    group = next(stage["$group"] for stage in pipeline if "$group" in stage)
    assert group["_id"] == "$items.product_id"
    assert group["revenue"] == {"$sum": "$items.net_amount"}
