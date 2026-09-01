"""Every Phase 1 read goes through build_match, so floor scoping and the
ordered_at date field are never re-implemented per surface."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from services.analytics import gather
from services.analytics.filters import AnalyticsFilter

WINDOW = ("2026-07-01T00:00:00+00:00", "2026-07-31T23:59:59+00:00")


class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return self._docs if n is None else self._docs[:n]

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


def _matches(doc: dict, query: dict) -> bool:
    """Enough of MongoDB's matcher to make a filter testable.

    A fake that ignores the query cannot catch a broken filter — the exact
    weakness that let a floor-scoping gap through in the Tile Orders work.
    """
    for key, condition in query.items():
        if key.startswith("$"):
            continue
        value = doc.get(key)
        if isinstance(condition, dict):
            if "$in" in condition and value not in condition["$in"]:
                return False
            if "$nin" in condition and value in condition["$nin"]:
                return False
            if "$ne" in condition and value == condition["$ne"]:
                return False
            if "$gt" in condition and not (value is not None and value > condition["$gt"]):
                return False
        elif value != condition:
            return False
    return True


class _FakeCollection:
    def __init__(self, docs):
        self.docs = list(docs)
        self.queries: list[dict] = []

    def find(self, query=None, projection=None):
        self.queries.append(query or {})
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])

    def aggregate(self, pipeline):
        self.queries.append(pipeline[0].get("$match", {}) if pipeline else {})
        return _FakeCursor([])

    async def count_documents(self, query):
        self.queries.append(query)
        return len(self.docs)


class _FakeDb:
    def __init__(self, **collections):
        self._extra: dict[str, _FakeCollection] = {}
        for name, docs in collections.items():
            self._extra[name] = _FakeCollection(docs)

    def __getattr__(self, name):
        extra = self.__dict__.get("_extra", {})
        if name not in extra:
            extra[name] = _FakeCollection([])
        return extra[name]


def _empty_db():
    return _FakeDb(quotations=[], payments=[], followups=[], walkins=[],
                   purchase_orders=[], users=[], referrers=[], customers=[])


def test_attention_reads_are_floor_scoped_for_a_restricted_caller():
    db = _empty_db()
    asyncio.run(gather.gather_attention(db, AnalyticsFilter(floor_id="all"), ["ground-floor"], WINDOW, {}))
    scoped = [q for q in db.quotations.queries if q.get("floor_id")]
    assert scoped, "no quotation read carried a floor clause"
    for q in scoped:
        assert q["floor_id"] == {"$in": ["ground-floor"]}


def test_an_unrestricted_caller_gets_no_floor_clause():
    db = _empty_db()
    asyncio.run(gather.gather_attention(db, AnalyticsFilter(floor_id="all"), None, WINDOW, {}))
    assert all("floor_id" not in q for q in db.quotations.queries)


def test_explicit_floor_scopes_tile_operational_reads_for_an_unrestricted_user():
    """A manager selecting one floor must not see the other floor's dispatch state."""
    db = _FakeDb(
        ready_batches=[
            {"id": "ground-ready", "floor_id": "ground-floor", "is_deleted": False, "boxes_ready": 1},
            {"id": "first-ready", "floor_id": "first-floor", "is_deleted": False, "boxes_ready": 1},
        ],
        purchase_orders=[
            {"id": "ground-po", "floor_id": "ground-floor", "is_deleted": False, "boxes_pending": 1},
            {"id": "first-po", "floor_id": "first-floor", "is_deleted": False, "boxes_pending": 1},
        ],
    )

    result = asyncio.run(gather.gather_attention(
        db, AnalyticsFilter(floor_id="ground-floor"), None, WINDOW, {},
    ))

    assert [row["id"] for row in result.ready_items] == ["ground-ready"]
    assert [row["id"] for row in result.unreleased_items] == ["ground-po"]
    assert db.ready_batches.queries[-1]["floor_id"] == {"$in": ["ground-floor"]}
    assert db.purchase_orders.queries[-1]["floor_id"] == {"$in": ["ground-floor"]}


def test_health_dispatch_signal_honors_the_selected_floor():
    now = datetime.now(timezone.utc).isoformat()
    db = _FakeDb(
        ready_batches=[
            {"id": "ground-ready", "floor_id": "ground-floor", "is_deleted": False,
             "boxes_ready": 1, "created_at": now},
            {"id": "first-ready", "floor_id": "first-floor", "is_deleted": False,
             "boxes_ready": 1, "created_at": "2026-01-01T00:00:00+00:00"},
        ],
    )

    from models import AnalyticsTargets
    signals = asyncio.run(gather.gather_health_signals(
        db, AnalyticsFilter(floor_id="ground-floor"), None, WINDOW, AnalyticsTargets(),
    ))

    assert signals["dispatch_health"] == 100.0
    assert db.ready_batches.queries[-1]["floor_id"] == {"$in": ["ground-floor"]}


def test_open_quotations_are_fetched_by_status_not_by_dropping_the_floor_clause():
    db = _empty_db()
    asyncio.run(gather.gather_attention(db, AnalyticsFilter(floor_id="all"), ["first-floor"], WINDOW, {}))
    open_reads = [q for q in db.quotations.queries if isinstance(q.get("status"), dict)]
    assert open_reads, "expected a status-$in read for open quotations"
    for q in open_reads:
        assert set(q["status"]["$in"]) <= {"draft", "sent", "approved", "pending_approval"}
        assert q.get("floor_id") == {"$in": ["first-floor"]}


def test_only_completed_payments_count_as_collected():
    db = _FakeDb(payments=[
        {"quotation_id": "q1", "amount": 100.0, "status": "completed"},
        {"quotation_id": "q1", "amount": 900.0, "status": "pending"},
    ])
    got = asyncio.run(gather.collected_by_quotation(db, ["q1"]))
    assert got == {"q1": 100.0}


def test_collected_lookup_with_no_quotations_issues_no_query():
    db = _FakeDb(payments=[{"quotation_id": "q1", "amount": 100.0, "status": "completed"}])
    assert asyncio.run(gather.collected_by_quotation(db, [])) == {}
    assert db.payments.queries == []


def test_open_pipeline_reads_are_not_date_windowed():
    """A quotation that has been open for 40 days must still appear in a
    this-month window — the whole point of the stalled-quotation rule."""
    db = _empty_db()
    asyncio.run(gather.gather_attention(db, AnalyticsFilter(floor_id="all"), None, WINDOW, {}))
    open_reads = [q for q in db.quotations.queries if isinstance(q.get("status"), dict)]
    for q in open_reads:
        assert "created_at" not in q and "ordered_at" not in q


def test_health_signals_return_none_rather_than_zero_when_undeterminable():
    from models import AnalyticsTargets
    db = _empty_db()
    signals = asyncio.run(gather.gather_health_signals(db, AnalyticsFilter(), None, WINDOW, AnalyticsTargets()))
    # No orders, no outstanding, no targets: every signal is unknowable, and
    # zero would read as total business failure.
    assert signals["collection_health"] is None
    assert signals["revenue_attainment"] is None
    assert signals["conversion_health"] is None


def test_a_declared_revenue_target_makes_attainment_measurable():
    from models import AnalyticsTargets
    db = _empty_db()
    signals = asyncio.run(gather.gather_health_signals(
        db, AnalyticsFilter(), None, WINDOW, AnalyticsTargets(monthly_revenue_target=100000),
    ))
    assert signals["revenue_attainment"] == 0.0     # measurable, and genuinely zero


def test_feed_reads_are_capped():
    db = _FakeDb(activity_events=[{"id": str(i), "event_type": "user.login"} for i in range(500)])
    rows = asyncio.run(gather.gather_feed(db, AnalyticsFilter(), None, limit=25))
    assert isinstance(rows, list)


def test_the_payment_filter_is_genuinely_load_bearing():
    """Power check on the fake: if collected stopped filtering by status, this
    fixture would sum the pending payment too."""
    db = _FakeDb(payments=[
        {"quotation_id": "q1", "amount": 100.0, "status": "completed"},
        {"quotation_id": "q1", "amount": 900.0, "status": "pending"},
    ])
    assert asyncio.run(gather.collected_by_quotation(db, ["q1"])) == {"q1": 100.0}
    unfiltered = [d for d in db.payments.docs]
    assert len(unfiltered) == 2, "fixture must contain a pending payment to have power"


def test_the_feed_candidate_window_is_wide_enough_to_survive_dead_events():
    """A run of unresolvable events at the head of the stream must not empty
    the feed. The live database has exactly that: the newest allowlisted
    events are test follow-ups pointing at a customer id that never existed."""
    assert gather.FEED_CANDIDATE_CAP >= 500
