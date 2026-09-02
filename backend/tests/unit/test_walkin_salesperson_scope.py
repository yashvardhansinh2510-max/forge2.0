"""Salesperson assignment must respect both role and floor ownership."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from routes import walkin_routes


class _Users:
    def __init__(self, rows: list[dict]):
        self.rows = {row["id"]: row for row in rows}

    async def find_one(self, query, *_args, **_kwargs):
        return self.rows.get(query["id"])


def _set_users(monkeypatch, rows: list[dict]):
    monkeypatch.setattr(walkin_routes, "db", type("Db", (), {"users": _Users(rows)})())


def test_salesperson_must_have_the_walkins_floor(monkeypatch):
    _set_users(monkeypatch, [{"id": "sanitary-sales", "full_name": "Sanitary Sales", "role": "sales", "active": True, "floor_ids": ["first-floor"]}])

    with pytest.raises(HTTPException, match="does not have access"):
        asyncio.run(walkin_routes._salesperson_for_floor("sanitary-sales", "ground-floor"))


def test_warehouse_staff_cannot_be_assigned_as_salesperson(monkeypatch):
    _set_users(monkeypatch, [{"id": "warehouse", "full_name": "Warehouse", "role": "warehouse", "active": True, "floor_ids": ["ground-floor"]}])

    with pytest.raises(HTTPException, match="cannot own sales"):
        asyncio.run(walkin_routes._salesperson_for_floor("warehouse", "ground-floor"))


def test_profile_bound_salesperson_uses_the_profiles_floor(monkeypatch):
    staff = {"id": "tile-sales", "full_name": "Tile Sales", "role": "sales", "active": True, "floor_ids": ["first-floor"], "access_profile": "ground_tile_quotations_followups"}
    _set_users(monkeypatch, [staff])

    assert asyncio.run(walkin_routes._salesperson_for_floor("tile-sales", "ground-floor")) == staff
