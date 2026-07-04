"""Product / Brand / Category endpoints + AI-assisted catalog import stub."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_user, require_min_role
from db import db, strip_ids
from models import Brand, Category, Product, ProductCreate, UserPublic

router = APIRouter(tags=["catalog"])


# ---------- Brands ----------
@router.get("/brands", response_model=list[Brand])
async def list_brands(_: UserPublic = Depends(get_current_user)):
    docs = await db.brands.find({}, {"_id": 0}).sort("name", 1).to_list(500)
    return [Brand(**d) for d in docs]


@router.get("/categories", response_model=list[Category])
async def list_categories(_: UserPublic = Depends(get_current_user)):
    docs = await db.categories.find({}, {"_id": 0}).sort("name", 1).to_list(500)
    return [Category(**d) for d in docs]


# ---------- Products ----------
@router.get("/products")
async def list_products(
    q: Optional[str] = Query(None, description="Free text search on name/sku/description"),
    brand_id: Optional[str] = None,
    category_id: Optional[str] = None,
    finish: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    _: UserPublic = Depends(get_current_user),
):
    query: dict = {"active": True}
    if brand_id:
        query["brand_id"] = brand_id
    if category_id:
        query["category_id"] = category_id
    if finish:
        query["finish"] = finish
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"sku": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}},
        ]
    total = await db.products.count_documents(query)
    docs = await db.products.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": strip_ids(docs)}


@router.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str, _: UserPublic = Depends(get_current_user)):
    doc = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    return Product(**doc)


@router.post("/products", response_model=Product)
async def create_product(
    body: ProductCreate,
    user: UserPublic = Depends(require_min_role("purchase")),
):
    if await db.products.find_one({"sku": body.sku}):
        raise HTTPException(status_code=409, detail="SKU already exists")
    prod = Product(**body.dict())
    await db.products.insert_one(prod.dict())
    return prod


# ---------- Catalog import (AI-assisted scaffold) ----------
@router.get("/catalog/imports")
async def list_import_jobs(_: UserPublic = Depends(require_min_role("purchase"))):
    docs = await db.catalog_imports.find({}, {"_id": 0, "rows": 0}).sort("created_at", -1).to_list(200)
    return docs
