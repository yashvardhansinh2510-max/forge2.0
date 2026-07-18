"""JWT + password hashing + role-based dependencies."""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
from time import monotonic
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


# Atlas is geographically remote from the preview runtime (~229 ms RTT). Every
# authenticated endpoint previously paid two sequential reads (session + user)
# before its own business query. Cache only a successfully validated principal
# for a deliberately short window: logout/session revocation remains bounded to
# 10 seconds, while normal page waterfalls avoid repeating the same two reads.
_PRINCIPAL_CACHE_TTL_SECONDS = 10.0
_PRINCIPAL_CACHE_MAX_ENTRIES = 2048
_principal_cache: dict[tuple[str, str, str], tuple[float, dict]] = {}


def _cached_principal(kind: str, subject: str, session_id: str | None) -> dict | None:
    key = (kind, subject, session_id or "")
    hit = _principal_cache.get(key)
    if not hit:
        return None
    expires_at, doc = hit
    if expires_at <= monotonic():
        _principal_cache.pop(key, None)
        return None
    return doc.copy()


def _cache_principal(kind: str, subject: str, session_id: str | None, doc: dict) -> None:
    if len(_principal_cache) >= _PRINCIPAL_CACHE_MAX_ENTRIES:
        now = monotonic()
        expired = [key for key, (expires_at, _) in _principal_cache.items() if expires_at <= now]
        for key in expired:
            _principal_cache.pop(key, None)
        if len(_principal_cache) >= _PRINCIPAL_CACHE_MAX_ENTRIES:
            _principal_cache.pop(next(iter(_principal_cache)))
    _principal_cache[(kind, subject, session_id or "")] = (
        monotonic() + _PRINCIPAL_CACHE_TTL_SECONDS,
        doc.copy(),
    )


def invalidate_principal_cache(kind: str, subject: str, session_id: str | None = None) -> None:
    """Invalidate one session or every cached session for a principal."""
    if session_id is not None:
        _principal_cache.pop((kind, subject, session_id), None)
        return
    for key in [key for key in _principal_cache if key[0] == kind and key[1] == subject]:
        _principal_cache.pop(key, None)

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


async def _load_active_principal(payload: dict, *, kind: str, collection: str) -> dict:
    """Validate session + active principal, using a short safe cache on success."""
    subject = payload["sub"]
    session_id = payload.get("session_id")
    cached = _cached_principal(kind, subject, session_id)
    if cached:
        return cached

    if session_id:
        session_filter = {
            "id": session_id,
            "user_type": kind,
            "user_id": subject,
            "revoked": {"$ne": True},
        }
        session_doc, principal = await asyncio.gather(
            db.user_sessions.find_one(session_filter, {"_id": 0, "id": 1}),
            db[collection].find_one({"id": subject}, {"_id": 0, "password_hash": 0}),
        )
        if not session_doc:
            raise HTTPException(status_code=401, detail="Session expired or was signed out. Please sign in again.")
        # Best-effort "last seen" bump — never block the request on this.
        asyncio.ensure_future(db.user_sessions.update_one(
            {"id": session_id},
            {"$set": {"last_seen_at": datetime.now(timezone.utc).isoformat()}},
        ))
    else:
        # Legacy tokens had no session id; preserve compatibility while still
        # requiring the principal to exist and remain active.
        principal = await db[collection].find_one(
            {"id": subject}, {"_id": 0, "password_hash": 0},
        )

    if not principal or not principal.get("active", True):
        raise HTTPException(status_code=401, detail=(
            "User not found or inactive" if kind == "staff" else "Customer not found"
        ))
    _cache_principal(kind, subject, session_id, principal)
    return principal


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
    doc = await _load_active_principal(payload, kind="staff", collection="users")
    return UserPublic(**doc)


async def get_current_customer(authorization: Optional[str] = Header(None)) -> CustomerPublic:
    payload = decode_token(_extract_token(authorization))
    if payload.get("kind") != "customer":
        raise HTTPException(status_code=403, detail="Not a customer token")
    doc = await _load_active_principal(payload, kind="customer", collection="customers")
    return CustomerPublic(**doc)


# RBAC — capability sets keyed by role. Kept intentionally simple: routes just
# ask `require_roles("owner","admin","sales")`.
ROLE_HIERARCHY = {
    "owner": 100, "admin": 90, "manager": 70, "accounts": 60,
    "purchase": 50, "sales": 40, "warehouse": 30, "worker": 10,
}

# Single source of truth for display labels + human-readable capability blurbs
# per role. Exposed to the frontend via GET /api/roles (routes/roles_routes.py)
# so Team Management's "Assign role" picker and the Settings > Roles &
# permissions screen never hardcode the role list — if a role is ever
# renamed/added here, both screens update with zero frontend changes.
ROLE_LABELS: dict[str, str] = {
    "owner": "Owner", "admin": "Admin", "manager": "Manager", "accounts": "Accounts",
    "purchase": "Purchase", "sales": "Sales", "warehouse": "Warehouse", "worker": "Worker",
}

ROLE_CAPABILITIES: dict[str, list[str]] = {
    "owner": ["Everything, including team management and settings"],
    "admin": ["Team management", "Company & PDF settings", "Catalog backup/export"],
    "manager": ["View team", "Approve catalog imports", "Full sales & purchase access"],
    "accounts": ["Payments & receivables", "Financial reporting"],
    "purchase": ["Purchase orders", "Catalog imports", "Supplier management"],
    "sales": ["Quotations", "Customers", "Follow-ups"],
    "warehouse": ["Stock movements", "Purchase receiving"],
    "worker": ["View-only access to assigned tasks"],
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


def floor_scope_ids(user: UserPublic) -> Optional[list[str]]:
    """Resolve the caller's floor filter the same way `floor_query()` does
    for Mongo-filter-based queries, but as a plain list — for callers that
    build their own aggregation pipeline or in-memory filter rather than
    taking a Mongo filter dict."""
    if user.active_floor_id:
        return [user.active_floor_id]
    return accessible_floor_ids(user)
