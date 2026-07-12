"""JWT + password hashing + role-based dependencies."""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import bcrypt
import httpx
import jwt
from fastapi import Depends, Header, HTTPException, Query, Request

from db import db
from models import Role, UserPublic, CustomerPublic
from settings import settings

JWT_SECRET = settings.jwt_secret
JWT_ALG = settings.jwt_algorithm
JWT_EXP_MIN = settings.jwt_exp_minutes

GOOGLE_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(pw: str, pw_hash: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), pw_hash.encode("utf-8"))
    except Exception:
        return False


def create_token(subject: str, kind: str, extra: Optional[dict] = None) -> str:
    payload = {
        "sub": subject,
        "kind": kind,  # "staff" | "customer"
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXP_MIN),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e


def _extract_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return authorization.split(" ", 1)[1].strip()


async def _check_session(payload: dict) -> None:
    """If this token was issued with a session_id (all logins going forward),
    make sure that session hasn't been revoked ('logout everywhere' / one
    device kicked out). Tokens without a session_id (should not happen for
    new logins, kept only for safety) are allowed through unchecked."""
    sid = payload.get("session_id")
    if not sid:
        return
    sess = await db.user_sessions.find_one({"id": sid}, {"_id": 0, "revoked": 1})
    if not sess or sess.get("revoked"):
        raise HTTPException(status_code=401, detail="Session expired or was signed out. Please sign in again.")
    # Best-effort "last seen" bump — never block the request on this.
    async def _bump():
        await db.user_sessions.update_one({"id": sid}, {"$set": {"last_seen_at": datetime.now(timezone.utc).isoformat()}})
    asyncio.create_task(_bump())


def _device_label(user_agent: Optional[str]) -> str:
    if not user_agent:
        return "Unknown device"
    ua = user_agent.lower()
    if "chrome" in ua and "edg" not in ua:
        browser = "Chrome"
    elif "crios" in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "edg" in ua:
        browser = "Edge"
    elif "safari" in ua:
        browser = "Safari"
    else:
        browser = "Browser"
    if "iphone" in ua or "ipad" in ua:
        osname = "iOS"
    elif "android" in ua:
        osname = "Android"
    elif "mac os" in ua:
        osname = "macOS"
    elif "windows" in ua:
        osname = "Windows"
    elif "linux" in ua:
        osname = "Linux"
    else:
        osname = "device"
    return f"{browser} on {osname}"


async def create_session(
    user_type: str, user_id: str, request: Optional[Request], login_method: str = "password",
) -> str:
    """Record a device/browser session. Returns the session_id to embed in
    the JWT (`extra={"session_id": sid}` on create_token)."""
    sid = str(uuid4())
    ua = request.headers.get("user-agent") if request else None
    ip = (request.client.host if request and request.client else None)
    now = datetime.now(timezone.utc).isoformat()
    await db.user_sessions.insert_one({
        "id": sid, "user_type": user_type, "user_id": user_id, "login_method": login_method,
        "device_label": _device_label(ua), "user_agent": ua, "ip": ip,
        "created_at": now, "last_seen_at": now, "revoked": False,
    })
    return sid


async def verify_google_session(session_id: str) -> dict:
    """Server-side verification against Emergent's OAuth session-data API —
    never trust a client-supplied email/name/picture directly."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(GOOGLE_SESSION_URL, headers={"X-Session-ID": session_id})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Google sign-in service: {e}") from e
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Google sign-in session is invalid or expired")
    data = resp.json()
    if not data.get("email"):
        raise HTTPException(status_code=401, detail="Google did not return an email for this account")
    return data


async def get_current_user(
    authorization: Optional[str] = Header(None),
    _t: Optional[str] = Query(None, description="Fallback token for browser downloads"),
) -> UserPublic:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif _t:
        token = _t
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    payload = decode_token(token)
    if payload.get("kind") != "staff":
        raise HTTPException(status_code=403, detail="Not a staff token")
    await _check_session(payload)
    user_id = payload["sub"]
    doc = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not doc or not doc.get("active", True):
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return UserPublic(**doc)


async def get_current_customer(authorization: Optional[str] = Header(None)) -> CustomerPublic:
    payload = decode_token(_extract_token(authorization))
    if payload.get("kind") != "customer":
        raise HTTPException(status_code=403, detail="Not a customer token")
    await _check_session(payload)
    cid = payload["sub"]
    doc = await db.customers.find_one({"id": cid}, {"_id": 0, "password_hash": 0})
    if not doc:
        raise HTTPException(status_code=401, detail="Customer not found")
    return CustomerPublic(**doc)


# RBAC — capability sets keyed by role. Kept intentionally simple: routes just
# ask `require_roles("owner","admin","sales")`.
ROLE_HIERARCHY = {
    "owner": 100, "admin": 90, "manager": 70, "accounts": 60,
    "purchase": 50, "sales": 40, "warehouse": 30, "worker": 10,
}


def require_roles(*allowed: Role):
    async def _dep(user: UserPublic = Depends(get_current_user)) -> UserPublic:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail=f"Role '{user.role}' not allowed")
        return user
    return _dep


def require_min_role(min_role: Role):
    threshold = ROLE_HIERARCHY[min_role]

    async def _dep(user: UserPublic = Depends(get_current_user)) -> UserPublic:
        if ROLE_HIERARCHY.get(user.role, 0) < threshold:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user
    return _dep
