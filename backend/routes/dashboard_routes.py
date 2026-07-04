"""Dashboard aggregates. Fast, role-agnostic snapshot for internal home screen."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from auth import get_current_user
from db import db
from models import UserPublic

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def dashboard_stats(user: UserPublic = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    quotations = await db.quotations.find({}, {"_id": 0}).to_list(1000)
    customers = await db.customers.count_documents({})
    products = await db.products.count_documents({"active": True})

    # revenue = grand_total of won quotations this month
    revenue_month = sum(
        q.get("grand_total", 0) for q in quotations
        if q.get("status") == "won" and q.get("updated_at", "") >= month_start
    )
    open_pipeline = sum(
        q.get("grand_total", 0) for q in quotations
        if q.get("status") in ("draft", "pending_approval", "sent")
    )
    pending_approval = sum(1 for q in quotations if q.get("status") == "pending_approval")
    quotes_this_month = sum(1 for q in quotations if q.get("created_at", "") >= month_start)

    # recent activity - last 8 quotations
    recent = sorted(quotations, key=lambda q: q.get("updated_at", ""), reverse=True)[:8]
    recent_activity = [
        {
            "id": q["id"],
            "kind": "quotation",
            "title": f"{q['number']} · {q['customer_name']}",
            "status": q["status"],
            "amount": q.get("grand_total", 0),
            "at": q.get("updated_at"),
        }
        for q in recent
    ]

    # top products by units quoted
    counts: dict[str, dict] = {}
    for q in quotations:
        for it in q.get("items", []):
            key = it["product_id"]
            entry = counts.setdefault(key, {"product_id": key, "name": it["name"], "sku": it["sku"], "image": it.get("image"), "qty": 0, "revenue": 0})
            entry["qty"] += it.get("qty", 0)
            entry["revenue"] += it.get("qty", 0) * it.get("unit_price", 0)
    top_products = sorted(counts.values(), key=lambda x: x["revenue"], reverse=True)[:5]

    # follow-ups due today for the logged-in user
    today_end = (now + timedelta(days=1)).isoformat()
    followups_due = await db.followups.count_documents({
        "status": "open",
        "due_at": {"$lte": today_end},
        "assigned_to": user.id,
    })

    return {
        "revenue_month": round(revenue_month, 2),
        "open_pipeline": round(open_pipeline, 2),
        "pending_approval": pending_approval,
        "quotes_this_month": quotes_this_month,
        "customers": customers,
        "products": products,
        "followups_due": followups_due,
        "recent_activity": recent_activity,
        "top_products": top_products,
    }
