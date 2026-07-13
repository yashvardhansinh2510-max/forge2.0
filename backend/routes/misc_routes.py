"""Scaffold endpoints — the /purchase-orders scaffold has been REMOVED and replaced
by the full module at routes/purchase_routes.py. The /payments scaffold has been
REMOVED and replaced by routes/payment_routes.py. /followups has been REMOVED and
replaced by the full Sales Command Center module at routes/followup_routes.py."""

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user, hash_password, invalidate_principal_cache, require_min_role
from db import db
from models import TeamCreatePayload, TeamUpdatePayload, UserPublic, now_iso
from services.activity_log import log_event
from services.invite_service import generate_temp_password, get_invite_service, temp_password_expiry_iso
from settings import settings
from typing import Optional

router = APIRouter(tags=["ops"])

# Settings > System > Version. Bump manually alongside meaningful releases —
# there's no build pipeline yet to derive this automatically.
FORGE_VERSION = "1.0.0"


def _sanitize_error(err: Optional[str]) -> Optional[str]:
    """Security audit (Phase 1, 2026-08): this endpoint is intentionally public
    (no auth) for ops/curl diagnostics, but driver exceptions (pymongo/httpx)
    can embed the connection string or internal hostnames in their message.
    Strip any credentials-looking substring and cap the length — callers only
    need the failure class, not a full stack-trace-grade string."""
    if not err:
        return err
    import re
    err = re.sub(r"://[^@/\s]+@", "://<redacted>@", err)
    return err[:200]


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
        "version": FORGE_VERSION,
        "mongo": {"connected": mongo_ok, "is_local": is_local_mongo, "error": _sanitize_error(mongo_error)},
        "supabase": {"configured": supabase_configured, "connected": supabase_ok, "error": _sanitize_error(supabase_error)},
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


@router.post("/team")
async def create_team_member(body: TeamCreatePayload, user: UserPublic = Depends(require_min_role("admin"))):
    if await db.users.find_one({"email": body.email.lower()}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=409, detail="A team member with this email already exists")
    doc = UserPublic(
        email=body.email.lower(), full_name=body.full_name, role=body.role, phone=body.phone,
        # New staff must set their own password on first login — the admin-
        # supplied password here is only a onboarding credential, never a
        # long-term secret someone else chose for them.
        must_change_password=True, temp_password_expires_at=temp_password_expiry_iso(),
    ).dict()
    doc["password_hash"] = hash_password(body.password)
    await db.users.insert_one(doc)
    doc.pop("password_hash", None)
    doc.pop("_id", None)
    await log_event(
        event_type="user.created", entity_type="user", entity_id=doc["id"],
        actor=user, summary="Staff Account Created",
        payload={"role": body.role, "email": doc["email"]},
    )
    return doc


@router.patch("/team/{user_id}")
async def update_team_member(
    user_id: str, body: TeamUpdatePayload, user: UserPublic = Depends(require_min_role("admin")),
):
    if user_id == user.id and body.active is False:
        raise HTTPException(status_code=400, detail="You can't deactivate your own account")
    if user_id == user.id and body.role is not None and body.role != user.role:
        raise HTTPException(status_code=400, detail="You can't change your own role")
    before = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Team member not found")
    patch = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="Nothing to update")
    patch["updated_at"] = now_iso()
    await db.users.update_one({"id": user_id}, {"$set": patch})
    doc = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})

    if "role" in patch and patch["role"] != before.get("role"):
        await log_event(
            event_type="user.role_changed", entity_type="user", entity_id=user_id, actor=user,
            summary="Staff Role Changed",
            payload={"from": before.get("role"), "to": patch["role"]},
        )
    if "active" in patch and patch["active"] != before.get("active", True):
        await log_event(
            event_type="user.enabled" if patch["active"] else "user.disabled",
            entity_type="user", entity_id=user_id, actor=user,
            summary="Staff Account Enabled" if patch["active"] else "Staff Account Disabled",
        )
    return doc


@router.post("/team/{user_id}/reset-password")
async def reset_team_member_password(user_id: str, user: UserPublic = Depends(require_min_role("admin"))):
    """Team > Reset Password. Generates a secure temporary password shown
    ONCE to the admin (manual-share, no email/SMS integration yet — see
    services/invite_service.py). The account is forced to change it on next
    login and it self-expires in 72h if unused."""
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Use Settings > Change password to reset your own password")
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Team member not found")
    temp_pw = generate_temp_password()
    expires_at = temp_password_expiry_iso()
    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "password_hash": hash_password(temp_pw),
            "must_change_password": True,
            "temp_password_expires_at": expires_at,
            "updated_at": now_iso(),
        }},
    )
    invalidate_principal_cache("staff", user_id)
    result = await get_invite_service().deliver(
        recipient_email=target.get("email"), recipient_name=target.get("full_name", "this team member"),
        temp_password=temp_pw, expires_at=expires_at, kind="staff_reset",
    )
    await log_event(
        event_type="user.password_reset", entity_type="user", entity_id=user_id, actor=user,
        summary="Staff Password Reset",
    )
    return {
        "delivery_method": result.delivery_method,
        "temporary_password": result.temporary_password,
        "expires_at": result.expires_at,
        "message": result.message,
    }


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
