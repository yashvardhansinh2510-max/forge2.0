from __future__ import annotations

import pytest

from routes.catalog_routes import _usage_ranked_product_page


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self._skip = 0
        self._limit = len(self.rows)

    def sort(self, fields):
        for field, direction in reversed(fields):
            self.rows.sort(key=lambda row: row.get(field) or "", reverse=direction < 0)
        return self

    def skip(self, n):
        self._skip = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    async def to_list(self, _n):
        return self.rows[self._skip:self._skip + self._limit]


class Products:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, _projection):
        ids_in = query.get("id", {}).get("$in")
        ids_out = set(query.get("id", {}).get("$nin", []))
        rows = self.rows
        if ids_in is not None:
            rows = [row for row in rows if row["id"] in set(ids_in)]
        if ids_out:
            rows = [row for row in rows if row["id"] not in ids_out]
        return Cursor(rows)


class Db:
    def __init__(self, rows):
        self.products = Products(rows)


@pytest.mark.parametrize("skip,expected", [
    (0, ["p2", "p1", "p3"]),
    (3, ["p4", "p5", "p6"]),
    (6, ["p7"]),
])
def test_usage_ranked_pages_are_stable_and_complete(monkeypatch, skip, expected):
    import routes.catalog_routes as catalog

    rows = [
        {"id": f"p{i}", "name": name}
        for i, name in enumerate(["ignored", "Bravo", "Alpha", "Charlie", "Delta", "Echo", "Foxtrot", "Golf"])
        if i > 0
    ]
    monkeypatch.setattr(catalog, "db", Db(rows))

    import asyncio
    result = asyncio.run(_usage_ranked_product_page(
        query={},
        ranked_ids={"p1", "p2"},
        rank_key=lambda row: {"p2": 0, "p1": 1}[row["id"]],
        skip=skip,
        limit=3,
    ))
    assert [row["id"] for row in result] == expected
