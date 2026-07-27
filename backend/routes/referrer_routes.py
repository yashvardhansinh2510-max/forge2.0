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
    """Case-insensitive existing-name check (same type) before inserting.
    Two sales reps could otherwise create "Rakesh Sharma" and "rakesh
    sharma" as separate people, permanently splitting that person's revenue
    on the Sales Data dashboard with no way to merge (v1 has no
    update/delete). Rather than rejecting the duplicate, return the
    pre-existing record — the picker's "+ Add new" flow expects a
    successful create-or-select response, so this lets the frontend proceed
    exactly as if it had created one. Same name but a different type (e.g.
    an architect and an interior designer sharing a name) still creates a
    separate record."""
    existing = await db.referrers.find({"type": body.type}, {"_id": 0}).to_list(2000)
    for doc in existing:
        if doc.get("name", "").strip().lower() == body.name.strip().lower():
            return Referrer(**doc)

    referrer = Referrer(**body.dict(), created_by=user.id)
    await db.referrers.insert_one(referrer.dict())
    return referrer
