"""Staff + customer authentication endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from auth import (
    create_session, create_token, decode_token, get_current_customer, get_current_user,
    hash_password, invalidate_principal_cache, verify_google_session, verify_password,
)
from db import db
from models import (
    ChangePasswordPayload, CustomerLoginPayload, CustomerPublic, CustomerTokenResponse,
    GoogleSessionPayload, LoginPayload, SessionInfo, TokenResponse, UserPublic, now_iso,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def staff_login(body: LoginPayload, request: Request):
    doc = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not doc or not verify_password(body.password, doc.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not doc.get("active", True):
        raise HTTPException(status_code=403, detail="Account disabled")
    sid = await create_session("staff", doc["id"], request, login_method="password")
    token = create_token(doc["id"], "staff", {"role": doc["role"], "session_id": sid})
    doc.pop("password_hash", None)
    return TokenResponse(access_token=token, user=UserPublic(**doc))


@router.get("/me", response_model=UserPublic)
async def staff_me(user: UserPublic = Depends(get_current_user)):
    return user


@router.post("/change-password")
async def staff_change_password(body: ChangePasswordPayload, user: UserPublic = Depends(get_current_user)):
    """Settings > Account > Password. Staff-only for now — the customer
    portal is intentionally read-only (Phase 5 decision) and has no account-
    management surface yet."""
    doc = await db.users.find_one({"id": user.id}, {"_id": 0, "password_hash": 1})
    if not doc or not verify_password(body.current_password, doc.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    await db.users.update_one(
        {"id": user.id},
        {"$set": {"password_hash": hash_password(body.new_password), "updated_at": now_iso()}},
    )
    invalidate_principal_cache("staff", user.id)
    return {"changed": True}


@router.post("/customer/login", response_model=CustomerTokenResponse)
async def customer_login(body: CustomerLoginPayload, request: Request):
    doc = await db.customers.find_one({"email": body.email.lower()}, {"_id": 0})
    if not doc or not doc.get("password_hash") or not verify_password(body.password, doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    sid = await create_session("customer", doc["id"], request, login_method="password")
    token = create_token(doc["id"], "customer", {"session_id": sid})
    doc.pop("password_hash", None)
    return CustomerTokenResponse(access_token=token, customer=CustomerPublic(**doc))


@router.get("/customer/me", response_model=CustomerPublic)
async def customer_me(cust: CustomerPublic = Depends(get_current_customer)):
    return cust


# ---------- Sign in with Google ----------
# Verified server-side against Emergent's OAuth session-data API — the
# frontend only ever hands us a one-time session_id, never a trusted profile.

@router.post("/google/staff", response_model=TokenResponse)
async def google_staff_login(body: GoogleSessionPayload, request: Request):
    profile = await verify_google_session(body.session_id)
    email = profile["email"].lower()
    doc = await db.users.find_one({"email": email}, {"_id": 0})
    if not doc:
        # Deliberately NOT auto-creating staff accounts — an unmatched email
        # must never get in, and must never get a default role.
        raise HTTPException(
            status_code=404,
            detail="No staff account found for this email. Please contact your administrator.",
        )
    if not doc.get("active", True):
        raise HTTPException(status_code=403, detail="Account disabled")
    if profile.get("picture") and not doc.get("avatar_url"):
        await db.users.update_one({"id": doc["id"]}, {"$set": {"avatar_url": profile["picture"]}})
        doc["avatar_url"] = profile["picture"]
    sid = await create_session("staff", doc["id"], request, login_method="google")
    token = create_token(doc["id"], "staff", {"role": doc["role"], "session_id": sid})
    doc.pop("password_hash", None)
    return TokenResponse(access_token=token, user=UserPublic(**doc))


@router.post("/google/customer", response_model=CustomerTokenResponse)
async def google_customer_login(body: GoogleSessionPayload, request: Request):
    profile = await verify_google_session(body.session_id)
    email = profile["email"].lower()
    doc = await db.customers.find_one({"email": email}, {"_id": 0})
    if not doc:
        # Frictionless self-service onboarding — first Google sign-in creates
        # the portal account. Matching is strictly by email, so any customer
        # record staff already created with this same email is reused
        # instead of duplicated ("merge by email").
        new_doc = {
            "id": None, "name": profile.get("name") or email.split("@")[0],
            "company": None, "email": email, "phone": None, "address": None,
            "city": None, "gstin": None, "tier": "retail", "notes": None,
            "avatar_url": profile.get("picture"),
        }
        from models import CustomerPublic as _CP
        created = _CP(**{k: v for k, v in new_doc.items() if k != "id"})
        to_store = created.dict()
        await db.customers.insert_one(to_store)
        doc = to_store
    elif profile.get("picture") and not doc.get("avatar_url"):
        await db.customers.update_one({"id": doc["id"]}, {"$set": {"avatar_url": profile["picture"]}})
        doc["avatar_url"] = profile["picture"]
    sid = await create_session("customer", doc["id"], request, login_method="google")
    token = create_token(doc["id"], "customer", {"session_id": sid})
    doc.pop("password_hash", None)
    return CustomerTokenResponse(access_token=token, customer=CustomerPublic(**doc))


# ---------- Session management (works for either staff or customer token) ----------

def _principal_from_token(authorization: Optional[str]) -> tuple[str, str, Optional[str]]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    payload = decode_token(authorization.split(" ", 1)[1].strip())
    kind, sub, sid = payload.get("kind"), payload.get("sub"), payload.get("session_id")
    if kind not in ("staff", "customer") or not sub:
        raise HTTPException(status_code=401, detail="Invalid token")
    return kind, sub, sid


@router.post("/logout")
async def logout_current_session(authorization: Optional[str] = Header(None)):
    """Revoke only the current device's session (regular sign-out — NOT
    'logout everywhere'). Safe to call even for legacy tokens without a
    session_id (no-op in that case)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return {"revoked": False}
    try:
        payload = decode_token(authorization.split(" ", 1)[1].strip())
    except HTTPException:
        return {"revoked": False}
    sid = payload.get("session_id")
    if not sid:
        return {"revoked": False}
    invalidate_principal_cache(payload.get("kind", ""), payload.get("sub", ""), sid)
    await db.user_sessions.update_one({"id": sid}, {"$set": {"revoked": True}})
    return {"revoked": True}


@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(authorization: Optional[str] = Header(None)):
    """Active devices/browsers for the signed-in user — 'remember trusted devices'."""
    kind, sub, current_sid = _principal_from_token(authorization)
    docs = await db.user_sessions.find(
        {"user_type": kind, "user_id": sub, "revoked": {"$ne": True}}, {"_id": 0},
    ).sort("last_seen_at", -1).to_list(100)
    return [
        SessionInfo(
            id=d["id"], device_label=d.get("device_label"), login_method=d.get("login_method", "password"),
            created_at=d["created_at"], last_seen_at=d["last_seen_at"], current=(d["id"] == current_sid),
        )
        for d in docs
    ]


@router.post("/sessions/logout-all")
async def logout_all_sessions(authorization: Optional[str] = Header(None)):
    """Revoke every active session for this user — 'logout from all devices'."""
    kind, sub, _ = _principal_from_token(authorization)
    invalidate_principal_cache(kind, sub)
    res = await db.user_sessions.update_many(
        {"user_type": kind, "user_id": sub, "revoked": {"$ne": True}}, {"$set": {"revoked": True}},
    )
    return {"revoked_count": res.modified_count}


@router.delete("/sessions/{session_id}")
async def revoke_one_session(session_id: str, authorization: Optional[str] = Header(None)):
    kind, sub, _ = _principal_from_token(authorization)
    invalidate_principal_cache(kind, sub, session_id)
    res = await db.user_sessions.update_one(
        {"id": session_id, "user_type": kind, "user_id": sub}, {"$set": {"revoked": True}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"revoked": True}
