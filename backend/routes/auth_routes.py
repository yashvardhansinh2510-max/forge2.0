"""Staff + customer authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from auth import (
    create_token, get_current_customer, get_current_user,
    hash_password, verify_password,
)
from db import db
from models import (
    CustomerLoginPayload, CustomerPublic, CustomerTokenResponse,
    LoginPayload, TokenResponse, UserPublic,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def staff_login(body: LoginPayload):
    doc = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not doc or not verify_password(body.password, doc.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not doc.get("active", True):
        raise HTTPException(status_code=403, detail="Account disabled")
    token = create_token(doc["id"], "staff", {"role": doc["role"]})
    doc.pop("password_hash", None)
    return TokenResponse(access_token=token, user=UserPublic(**doc))


@router.get("/me", response_model=UserPublic)
async def staff_me(user: UserPublic = Depends(get_current_user)):
    return user


@router.post("/customer/login", response_model=CustomerTokenResponse)
async def customer_login(body: CustomerLoginPayload):
    doc = await db.customers.find_one({"email": body.email.lower()}, {"_id": 0})
    if not doc or not doc.get("password_hash") or not verify_password(body.password, doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(doc["id"], "customer")
    doc.pop("password_hash", None)
    return CustomerTokenResponse(access_token=token, customer=CustomerPublic(**doc))


@router.get("/customer/me", response_model=CustomerPublic)
async def customer_me(cust: CustomerPublic = Depends(get_current_customer)):
    return cust
