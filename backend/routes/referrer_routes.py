"""Referrer directory — architects & interior designers who refer business.
Minimal CRUD: list (used by the quotation builder's picker and the Sales
Data dashboard) and create (inline quick-add from that same picker). No
update/delete for v1 — see
docs/superpowers/specs/2026-07-27-sales-data-dashboard-design.md."""
from fastapi import APIRouter, Depends, Query

from auth import require_min_role
from db import db
from models import Referrer, ReferrerCreate, ReferrerType, UserPublic

router = APIRouter(tags=["referrers"])


@router.get("/referrers", response_model=list[Referrer])
async def list_referrers(
    type: ReferrerType | None = Query(None),
    user: UserPublic = Depends(require_min_role("sales")),
):
    query: dict = {}
    if type:
        query["type"] = type
    docs = await db.referrers.find(query, {"_id": 0}).sort("name", 1).to_list(2000)
    return [Referrer(**d) for d in docs]


@router.post("/referrers", response_model=Referrer)
async def create_referrer(
    body: ReferrerCreate,
    user: UserPublic = Depends(require_min_role("sales")),
):
    referrer = Referrer(**body.dict(), created_by=user.id)
    await db.referrers.insert_one(referrer.dict())
    return referrer
