"""JWT + password hashing + role-based dependencies."""
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Query, status

from db import db, strip_id
from models import Role, UserPublic, CustomerPublic

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXP_MIN = int(os.environ.get("JWT_EXP_MINUTES", "1440"))


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
    user_id = payload["sub"]
    doc = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not doc or not doc.get("active", True):
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return UserPublic(**doc)


async def get_current_customer(authorization: Optional[str] = Header(None)) -> CustomerPublic:
    payload = decode_token(_extract_token(authorization))
    if payload.get("kind") != "customer":
        raise HTTPException(status_code=403, detail="Not a customer token")
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
