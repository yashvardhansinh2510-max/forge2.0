"""Scaffold endpoints — the /purchase-orders scaffold has been REMOVED and replaced
by the full module at routes/purchase_routes.py. /payments and /followups remain
as simple list endpoints until their full modules land."""
from fastapi import APIRouter, Depends

from auth import get_current_user, require_min_role
from db import db
from models import UserPublic

router = APIRouter(tags=["ops"])


@router.get("/payments")
async def list_payments(_: UserPublic = Depends(get_current_user)):
    return await db.payments.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.get("/followups")
async def list_followups(_: UserPublic = Depends(get_current_user)):
    return await db.followups.find({}, {"_id": 0}).sort("due_at", 1).to_list(200)


@router.get("/notifications")
async def list_notifications(user: UserPublic = Depends(get_current_user)):
    return await db.notifications.find({"user_id": user.id}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/team")
async def list_team(_: UserPublic = Depends(require_min_role("manager"))):
    return await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("full_name", 1).to_list(200)


@router.get("/reports/overview")
async def reports_overview(_: UserPublic = Depends(get_current_user)):
    quotations = await db.quotations.find({}, {"_id": 0}).to_list(2000)
    by_status: dict[str, int] = {}
    revenue_by_month: dict[str, float] = {}
    for q in quotations:
        by_status[q.get("status", "draft")] = by_status.get(q.get("status", "draft"), 0) + 1
        if q.get("status") == "won":
            month = (q.get("updated_at") or "")[:7]
            if month:
                revenue_by_month[month] = revenue_by_month.get(month, 0) + q.get("grand_total", 0)
    return {"by_status": by_status, "revenue_by_month": revenue_by_month}
