"""Scaffold endpoints — the /purchase-orders scaffold has been REMOVED and replaced
by the full module at routes/purchase_routes.py. The /payments scaffold has been
REMOVED and replaced by routes/payment_routes.py. /followups has been REMOVED and
replaced by the full Sales Command Center module at routes/followup_routes.py."""

from fastapi import APIRouter, Depends

from auth import get_current_user, require_min_role
from db import db
from models import UserPublic
from settings import settings

router = APIRouter(tags=["ops"])


@router.get("/health/system")
async def health_system():
    """Persistence & Disaster Recovery — startup/session health check.

    Public (no auth) so it can be curled from anywhere/anytime, but it NEVER
    returns secret values — only booleans/counts. Covers every item in the
    "before you build a new feature" checklist: db reachability, storage
    reachability, data counts, and which required secrets are actually loaded
    in this session's environment.
    """
    mongo_url = settings.mongo_url
    is_local_mongo = ("localhost" in mongo_url) or ("127.0.0.1" in mongo_url) or (not mongo_url)

    mongo_ok = False
    mongo_error = None
    try:
        await db.command("ping")
        mongo_ok = True
    except Exception as exc:  # noqa: BLE001
        mongo_error = str(exc)

    counts = {}
    if mongo_ok:
        for name in [
            "products", "customers", "quotations", "purchase_orders",
            "payments", "followups", "users", "brands", "categories", "activity",
        ]:
            try:
                counts[name] = await db[name].count_documents({})
            except Exception:  # noqa: BLE001
                counts[name] = None

    supabase_url = settings.supabase_url
    supabase_key = settings.supabase_service_role_key
    supabase_configured = bool(supabase_url and supabase_key)
    supabase_ok = None
    supabase_error = None
    if supabase_configured:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(
                    f"{supabase_url.rstrip('/')}/storage/v1/bucket",
                    headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
                )
                supabase_ok = resp.status_code < 300
                if not supabase_ok:
                    supabase_error = f"HTTP {resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            supabase_ok = False
            supabase_error = str(exc)

    secrets_loaded = settings.readiness_flags()

    warnings = []
    if is_local_mongo:
        warnings.append(
            "MongoDB is pointing at a LOCAL/ephemeral instance — all data will be lost on the "
            "next session reset. Migrate to MongoDB Atlas to make this permanent."
        )
    if not supabase_configured:
        warnings.append(
            "Supabase Storage is not configured — product images/PDFs/attachments will be lost "
            "on the next session reset. Provide SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY."
        )
    if mongo_ok and counts.get("products", 0) is not None and counts.get("products", 0) <= 20:
        warnings.append(
            "Product catalog looks like demo-seed data (<=20 items), not the full imported "
            "catalog. Re-run the catalog importers or restore from a backup."
        )

    return {
        "backend": "running",
        "mongo": {"connected": mongo_ok, "is_local": is_local_mongo, "error": mongo_error},
        "supabase": {"configured": supabase_configured, "connected": supabase_ok, "error": supabase_error},
        "counts": counts,
        "secrets_loaded": secrets_loaded,
        "warnings": warnings,
        "healthy": mongo_ok and (supabase_ok is not False),
    }


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
