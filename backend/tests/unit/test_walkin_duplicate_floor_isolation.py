"""Floor isolation for Walk-ins' customer duplicate detection.

`services/duplicate_detection.find_customer_matches` searched `db.customers`
with no floor filter at all, which made it two problems at once:

  * a read leak — `GET /walkins/check-duplicate` returned the other business
    unit's customer name, company, both phone numbers, email, city and address
    to anyone who could type a name into the walk-in form;
  * a write leak — a HIGH-confidence phone match is auto-reused with no staff
    prompt, so creating a Ground Floor walk-in for someone who already existed
    as a Sanitary Bathroom customer silently attached that walk-in (and every
    quotation, order and payment downstream of it) to the other unit's record.

Separately, `POST /walkins` accepted any `use_existing_customer_id` that merely
existed, with no floor check.
"""
from __future__ import annotations

import asyncio

import routes.walkin_routes as walkin_routes
import services.duplicate_detection as dupes


class _FakeCustomers:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows or []
        self.queries: list[dict] = []

    def find(self, query, projection=None):
        self.queries.append(query)
        return self

    async def to_list(self, _limit):
        return list(self.rows)

    async def find_one(self, query, projection=None, session=None):
        self.queries.append(query)
        return next(
            (r for r in self.rows if all(r.get(k) == v for k, v in query.items())),
            None,
        )


class _Db:
    def __init__(self, customers):
        self.customers = customers


def _floor_clauses(query: dict) -> list[dict]:
    return [c for c in query.get("$and", []) if "floor_id" in c]


def test_every_tier_is_floor_scoped(monkeypatch):
    """All three confidence tiers issue their own query — a filter applied to
    only the HIGH tier would still leak names through LOW."""
    customers = _FakeCustomers()
    monkeypatch.setattr(dupes, "db", _Db(customers))

    asyncio.run(dupes.find_customer_matches(
        phone="9820012345", email="a@b.com", name="Menon", city="Mumbai",
        floor_ids=["ground-floor"],
    ))

    assert len(customers.queries) == 3, "expected one query per confidence tier"
    for query in customers.queries:
        assert _floor_clauses(query) == [{"floor_id": {"$in": ["ground-floor"]}}]


def test_omitting_floor_ids_leaves_the_query_unrestricted(monkeypatch):
    """Documents the escape hatch explicitly so nobody adds a caller that
    silently relies on it."""
    customers = _FakeCustomers()
    monkeypatch.setattr(dupes, "db", _Db(customers))

    asyncio.run(dupes.find_customer_matches(phone="9820012345", floor_ids=None))

    assert customers.queries and all("$and" not in q for q in customers.queries)


def test_check_duplicate_endpoint_passes_the_callers_floor(monkeypatch):
    captured: dict = {}

    async def fake_matches(**kwargs):
        captured.update(kwargs)
        return {"high": [], "medium": [], "low": []}

    monkeypatch.setattr(dupes, "find_customer_matches", fake_matches)

    from models import UserPublic
    user = UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id="ground-floor",
    )
    asyncio.run(walkin_routes.check_duplicate(
        phone="9820012345", alternate_phone=None, email=None,
        name=None, city=None, address=None, user=user,
    ))

    assert captured["floor_ids"] == ["ground-floor"]


def test_find_or_create_customer_matches_within_the_walkins_department(monkeypatch):
    captured: dict = {}

    async def fake_matches(**kwargs):
        captured.update(kwargs)
        return {"high": [{"id": "c1"}], "medium": [], "low": []}

    monkeypatch.setattr(dupes, "find_customer_matches", fake_matches)

    from models import UserPublic
    import services.walkin_service as walkin_service

    user = UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id="first-floor",
    )
    result = asyncio.run(walkin_service.find_or_create_customer(
        name="Menon", phone="9820012345", alternate_phone=None, email=None,
        floor_id="ground-floor", user=user,
    ))

    # The walk-in's own department wins over the caller's ambient active floor.
    assert captured["floor_ids"] == ["ground-floor"]
    assert result["id"] == "c1"
