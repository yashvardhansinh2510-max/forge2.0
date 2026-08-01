"""Every Performance-workspace read goes through build_match, so floor scoping
is never re-implemented per surface. Reuses the fake-db pattern already proven
in test_analytics_gather.py — copy those three classes, not a fourth variant."""
from __future__ import annotations

import asyncio

from services.analytics import gather_performance
from services.analytics.filters import AnalyticsFilter

WINDOW = ("2026-07-01T00:00:00+00:00", "2026-07-31T23:59:59+00:00")


class _FakeCursor:
    def __init__(self, docs): self._docs = list(docs)
    def sort(self, *a, **k): return self
    def limit(self, *a, **k): return self
    async def to_list(self, n=None): return self._docs[:n] if n else list(self._docs)
    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


class _FakeCollection:
    def __init__(self, docs): self.docs = list(docs); self.queries = []
    def find(self, query=None, projection=None):
        self.queries.append(query or {})
        return _FakeCursor(self.docs)
    def aggregate(self, pipeline):
        self.queries.append(pipeline[0].get("$match", {}) if pipeline else {})
        return _FakeCursor([])
    async def count_documents(self, query): self.queries.append(query); return len(self.docs)


class _FakeDb:
    def __init__(self, **collections):
        for name, docs in collections.items():
            setattr(self, name, _FakeCollection(docs))
    def __getattr__(self, _name): return _FakeCollection([])


def test_revenue_trend_reads_are_floor_scoped_for_a_restricted_caller():
    db = _FakeDb(quotations=[])
    asyncio.run(gather_performance.gather_revenue_trend(db, AnalyticsFilter(floor_id="all"), ["ground-floor"], WINDOW, "month"))
    scoped = [q for q in db.quotations.queries if isinstance(q, dict) and q.get("floor_id")]
    assert scoped, "no revenue-trend read carried a floor clause"


def test_gather_salespeople_returns_three_shapes():
    db = _FakeDb(quotations=[], walkins=[], users=[])
    current, prev_revenue, prev_rank = asyncio.run(
        gather_performance.gather_salespeople(db, AnalyticsFilter(floor_id="all"), None, WINDOW, WINDOW)
    )
    assert current == [] and prev_revenue == {} and prev_rank == {}


def test_gather_funnel_marks_the_three_untracked_transitions_as_none():
    db = _FakeDb(walkins=[], quotations=[], purchase_orders=[], dispatches=[], payments=[])
    counts, durations, avg_order = asyncio.run(
        gather_performance.gather_funnel(db, AnalyticsFilter(floor_id="all"), None, WINDOW)
    )
    assert durations["selections"] is None or durations["selections"] == []
    assert durations["quotations"] is None
    assert durations["approved"] is None
    assert durations["confirmed_orders"] is None


def test_gather_category_revenue_reads_categories_for_names():
    db = _FakeDb(quotations=[], categories=[{"id": "c1", "name": "Tiles"}])
    raw, names = asyncio.run(gather_performance.gather_category_revenue(db, AnalyticsFilter(floor_id="all"), None, WINDOW))
    assert names == {"c1": "Tiles"}
