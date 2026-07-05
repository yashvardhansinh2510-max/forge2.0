"""Customer CRUD (admin) + customer-portal self-serve endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from auth import (
    get_current_customer, get_current_user, hash_password, require_min_role,
)
from db import db
from models import (
    CustomerCreate, CustomerPublic, UserPublic,
)

router = APIRouter(tags=["customers"])


# ---------- Staff-side ----------
@router.get("/customers", response_model=list[CustomerPublic])
async def list_customers(_: UserPublic = Depends(get_current_user)):
    docs = await db.customers.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    return [CustomerPublic(**d) for d in docs]


@router.post("/customers", response_model=CustomerPublic)
async def create_customer(
    body: CustomerCreate,
    _: UserPublic = Depends(require_min_role("sales")),
):
    if await db.customers.find_one({"email": body.email.lower()}):
        raise HTTPException(status_code=409, detail="Customer email already exists")
    data = body.dict()
    data["email"] = data["email"].lower()
    password = data.pop("password", None)
    from models import CustomerPublic as CP
    cust = CP(**data)
    to_store = cust.dict()
    if password:
        to_store["password_hash"] = hash_password(password)
    await db.customers.insert_one(to_store)
    return cust


@router.get("/customers/{customer_id}", response_model=CustomerPublic)
async def get_customer(customer_id: str, _: UserPublic = Depends(get_current_user)):
    doc = await db.customers.find_one({"id": customer_id}, {"_id": 0, "password_hash": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Customer not found")
    return CustomerPublic(**doc)


# ---------- Customer-portal ----------
@router.get("/portal/quotations")
async def portal_quotations(cust: CustomerPublic = Depends(get_current_customer)):
    docs = await db.quotations.find({"customer_id": cust.id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return docs
