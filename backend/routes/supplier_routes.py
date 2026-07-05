"""Supplier CRUD — dealership records per brand."""
from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user, require_min_role
from db import db
from models import Supplier, SupplierCreate, UserPublic
from services.activity_log import log_event

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("")
async def list_suppliers(_: UserPublic = Depends(get_current_user)):
    docs = await db.suppliers.find({}, {"_id": 0}).sort("name", 1).to_list(500)
    return docs


@router.post("", response_model=Supplier)
async def create_supplier(
    body: SupplierCreate,
    user: UserPublic = Depends(require_min_role("purchase")),
):
    data = body.dict()
    if data.get("brand_id"):
        b = await db.brands.find_one({"id": data["brand_id"]}, {"_id": 0, "name": 1})
        if b:
            data["brand_name"] = b["name"]
    sup = Supplier(**data)
    await db.suppliers.insert_one(sup.dict())
    await log_event(
        event_type="customer.created",  # reuse generic for supplier - or add new
        entity_type="customer",
        entity_id=sup.id,
        actor=user,
        summary=f"Supplier {sup.name} added",
        payload={"supplier_id": sup.id},
    )
    return sup


@router.get("/{supplier_id}", response_model=Supplier)
async def get_supplier(supplier_id: str, _: UserPublic = Depends(get_current_user)):
    doc = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return Supplier(**doc)


@router.patch("/{supplier_id}", response_model=Supplier)
async def update_supplier(
    supplier_id: str,
    body: SupplierCreate,
    _: UserPublic = Depends(require_min_role("purchase")),
):
    doc = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Supplier not found")
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if patch.get("brand_id"):
        b = await db.brands.find_one({"id": patch["brand_id"]}, {"_id": 0, "name": 1})
        if b:
            patch["brand_name"] = b["name"]
    from datetime import datetime, timezone
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.suppliers.update_one({"id": supplier_id}, {"$set": patch})
    fresh = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    return Supplier(**fresh)
