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
    q: Optional[str] = Query(None, description="Free text search on name/sku/description/series/family"),
    brand_id: Optional[str] = None,
    category_id: Optional[str] = None,
    subcategory: Optional[str] = None,
    series: Optional[str] = None,
    family_key: Optional[str] = None,
    finish: Optional[str] = None,
    colour: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    _: UserPublic = Depends(get_current_user),
):
    query: dict = {"active": True}
    if brand_id:
        query["brand_id"] = brand_id
    if category_id:
        query["category_id"] = category_id
    if subcategory:
        query["subcategory"] = subcategory
    if series:
        query["series"] = series
    if family_key:
        query["family_key"] = family_key
    if finish:
        query["finish"] = finish
    if colour:
        query["colour"] = colour
    if q:
        query["$or"] = [
            {"name":        {"$regex": q, "$options": "i"}},
            {"sku":         {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"series":      {"$regex": q, "$options": "i"}},
            {"family_name": {"$regex": q, "$options": "i"}},
            {"subcategory": {"$regex": q, "$options": "i"}},
            {"finish":      {"$regex": q, "$options": "i"}},
            {"colour":      {"$regex": q, "$options": "i"}},
            {"dimensions":  {"$regex": q, "$options": "i"}},
            {"tags":        {"$regex": q, "$options": "i"}},
        ]
    total = await db.products.count_documents(query)
    docs = await db.products.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": strip_ids(docs)}


# ---------- Hierarchy + family-grouped views ----------
@router.get("/catalog/hierarchy")
async def catalog_hierarchy(_: UserPublic = Depends(get_current_user)):
    """Return the full Brand → Category → Subcategory → Series → Family tree.

    Only counts active products. Perfect for browsable navigation in the
    catalog and quotation-builder pickers.
    """
    pipeline = [
        {"$match": {"active": True}},
        {"$group": {
            "_id": {
                "brand_id":    "$brand_id",
                "category_id": "$category_id",
                "subcategory": "$subcategory",
                "series":      "$series",
                "family_key":  "$family_key",
                "family_name": "$family_name",
            },
            "product_count": {"$sum": 1},
            "min_price":     {"$min": "$price"},
            "sample_image":  {"$first": {"$arrayElemAt": ["$images", 0]}},
            "image_quality": {"$first": "$image_quality"},
        }},
    ]
    rows = await db.products.aggregate(pipeline).to_list(5000)
    brands = {b["id"]: b for b in await db.brands.find({}, {"_id": 0}).to_list(500)}
    cats = {c["id"]: c for c in await db.categories.find({}, {"_id": 0}).to_list(500)}

    # Fold into brand → category → subcategory → series → family tree
    tree: dict = {}
    for r in rows:
        k = r["_id"]
        bid = k.get("brand_id") or "_"
        cid = k.get("category_id") or "_"
        subcat = k.get("subcategory") or "General"
        series = k.get("series") or "Uncategorised"
        family_key = k.get("family_key") or f"{bid}:{cid}:{subcat}:{series}:_"
        family_name = k.get("family_name") or series

        brand = brands.get(bid, {"id": bid, "name": "Unknown"})
        category = cats.get(cid, {"id": cid, "name": "Uncategorised"})
        b = tree.setdefault(bid, {"brand": brand, "categories": {}})
        c = b["categories"].setdefault(cid, {"category": category, "subcategories": {}})
        s = c["subcategories"].setdefault(subcat, {"name": subcat, "series": {}})
        se = s["series"].setdefault(series, {"name": series, "families": {}})
        fam = se["families"].setdefault(family_key, {
            "family_key": family_key, "family_name": family_name,
            "product_count": 0, "min_price": 0.0,
            "sample_image": None, "image_quality": None,
        })
        fam["product_count"] += r["product_count"]
        if fam["min_price"] == 0 or r["min_price"] < fam["min_price"]:
            fam["min_price"] = r["min_price"]
        if not fam["sample_image"] and r.get("sample_image"):
            fam["sample_image"] = r["sample_image"]
        if not fam["image_quality"]:
            fam["image_quality"] = r.get("image_quality")

    # Flatten to arrays for JSON friendliness
    def _flatten(d: dict) -> list:
        out = []
        for bid, b in d.items():
            cats_out = []
            for cid, c in b["categories"].items():
                subs_out = []
                for subname, s in c["subcategories"].items():
                    ser_out = []
                    for sername, se in s["series"].items():
                        fams_out = list(se["families"].values())
                        fams_out.sort(key=lambda f: f["family_name"] or "")
                        ser_out.append({
                            "name": sername, "family_count": len(fams_out),
                            "product_count": sum(f["product_count"] for f in fams_out),
                            "families": fams_out,
                        })
                    ser_out.sort(key=lambda x: x["name"])
                    subs_out.append({
                        "name": subname, "series_count": len(ser_out),
                        "product_count": sum(sr["product_count"] for sr in ser_out),
                        "series": ser_out,
                    })
                subs_out.sort(key=lambda x: x["name"])
                cats_out.append({
                    "category": c["category"],
                    "subcategory_count": len(subs_out),
                    "product_count": sum(sub["product_count"] for sub in subs_out),
                    "subcategories": subs_out,
                })
            cats_out.sort(key=lambda x: x["category"].get("name", ""))
            out.append({
                "brand": b["brand"],
                "category_count": len(cats_out),
                "product_count": sum(c["product_count"] for c in cats_out),
                "categories": cats_out,
            })
        out.sort(key=lambda x: x["brand"].get("name", ""))
        return out

    return {"tree": _flatten(tree)}


@router.get("/products/families")
async def list_families(
    brand_id: Optional[str] = None,
    category_id: Optional[str] = None,
    subcategory: Optional[str] = None,
    series: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 60,
    skip: int = 0,
    _: UserPublic = Depends(get_current_user),
):
    """Return products grouped by family_key — one card per family, variants
    collapsed underneath. Ideal for the premium grouped catalog view.
    """
    match: dict = {"active": True, "family_key": {"$ne": None}}
    if brand_id:      match["brand_id"] = brand_id
    if category_id:   match["category_id"] = category_id
    if subcategory:   match["subcategory"] = subcategory
    if series:        match["series"] = series
    if q:
        match["$or"] = [
            {"name":        {"$regex": q, "$options": "i"}},
            {"family_name": {"$regex": q, "$options": "i"}},
            {"series":      {"$regex": q, "$options": "i"}},
            {"subcategory": {"$regex": q, "$options": "i"}},
            {"finish":      {"$regex": q, "$options": "i"}},
            {"colour":      {"$regex": q, "$options": "i"}},
            {"sku":         {"$regex": q, "$options": "i"}},
        ]

    pipeline = [
        {"$match": match},
        {"$sort": {"family_name": 1, "colour": 1, "sku": 1}},
        {"$group": {
            "_id": "$family_key",
            "family_key":  {"$first": "$family_key"},
            "family_name": {"$first": "$family_name"},
            "brand_id":    {"$first": "$brand_id"},
            "category_id": {"$first": "$category_id"},
            "subcategory": {"$first": "$subcategory"},
            "series":      {"$first": "$series"},
            "min_price":   {"$min": "$price"},
            "max_price":   {"$max": "$price"},
            "product_count": {"$sum": 1},
            "sample_image": {"$first": {"$arrayElemAt": ["$images", 0]}},
            "sample_image_quality": {"$first": "$image_quality"},
            "variants": {"$push": {
                "id": "$id", "sku": "$sku", "variant_label": "$variant_label",
                "colour": "$colour", "finish": "$finish", "finish_code": "$finish_code",
                "price": "$price", "mrp": "$mrp",
                "image": {"$arrayElemAt": ["$images", 0]},
                "image_quality": "$image_quality",
            }},
        }},
        {"$sort": {"family_name": 1}},
        {"$skip": skip}, {"$limit": limit},
    ]
    fams = await db.products.aggregate(pipeline).to_list(limit)
    for f in fams:
        f.pop("_id", None)
    # total distinct families for this query
    total_pipeline = [
        {"$match": match}, {"$group": {"_id": "$family_key"}}, {"$count": "n"},
    ]
    total = 0
    async for r in db.products.aggregate(total_pipeline):
        total = r.get("n", 0)
    return {"total": total, "items": fams}


@router.get("/products/recent")
async def recent_products(
    limit: int = 12,
    user: UserPublic = Depends(get_current_user),
):
    """Products this user has recently added to a quotation."""
    usages = await db.product_usage.find(
        {"user_id": user.id}, {"_id": 0}
    ).sort("last_used_at", -1).limit(limit).to_list(limit)
    if not usages:
        return []
    ids = [u["product_id"] for u in usages]
    docs = await db.products.find({"id": {"$in": ids}, "active": True}, {"_id": 0}).to_list(limit)
    by_id = {d["id"]: d for d in docs}
    # preserve recent order
    return [by_id[i] for i in ids if i in by_id]


@router.get("/products/frequent")
async def frequent_products(
    limit: int = 12,
    user: UserPublic = Depends(get_current_user),
):
    """Products this user adds most often."""
    usages = await db.product_usage.find(
        {"user_id": user.id}, {"_id": 0}
    ).sort("count", -1).limit(limit).to_list(limit)
    if not usages:
        return []
    ids = [u["product_id"] for u in usages]
    docs = await db.products.find({"id": {"$in": ids}, "active": True}, {"_id": 0}).to_list(limit)
    by_id = {d["id"]: d for d in docs}
    return [by_id[i] for i in ids if i in by_id]


@router.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str, _: UserPublic = Depends(get_current_user)):
    doc = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    return Product(**doc)


@router.get("/products/{product_id}/alternates")
async def product_alternates(
    product_id: str,
    limit: int = 12,
    user: UserPublic = Depends(get_current_user),
):
    """Return alternate products a salesperson might swap in for `product_id`.

    Smart-mix ranking (closest matches first):
      Tier 1  same brand + same category + same name-prefix  (approximates family)
      Tier 2  same brand + same category
      Tier 3  same category (any brand)

    Within every tier we rank by (this user's usage count DESC, price ASC) so
    the salesperson sees products they actually reach for. The current product
    itself is always excluded.
    """
    src = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Product not found")

    # First two words of the name (case-insensitive) form our family bucket.
    name_prefix = " ".join((src.get("name") or "").split()[:2]).strip().lower()

    # Pull per-user usage counts so we can rank tiers by "products this user likes".
    usages = await db.product_usage.find({"user_id": user.id}, {"_id": 0}).to_list(2000)
    usage_by_id = {u["product_id"]: int(u.get("count", 0)) for u in usages}

    # Pull a wide pool once, then classify in Python — keeps the query index-friendly
    # and lets us score across tiers in a single pass without triple round-trips.
    pool = await db.products.find(
        {
            "active": True,
            "category_id": src.get("category_id"),
            "id": {"$ne": product_id},
        },
        {"_id": 0},
    ).limit(400).to_list(400)

    def tier(p: dict) -> int:
        p_name_prefix = " ".join((p.get("name") or "").split()[:2]).strip().lower()
        same_brand = p.get("brand_id") == src.get("brand_id")
        same_prefix = bool(name_prefix) and p_name_prefix == name_prefix
        if same_brand and same_prefix:
            return 1
        if same_brand:
            return 2
        return 3

    scored = []
    for p in pool:
        t = tier(p)
        scored.append((t, -usage_by_id.get(p["id"], 0), float(p.get("price", 0)), p))
    scored.sort(key=lambda x: (x[0], x[1], x[2]))

    out = [p for _t, _u, _pr, p in scored[:limit]]
    return {
        "source_product_id": product_id,
        "items": out,
        "tiers": {
            "family": sum(1 for t, *_ in scored if t == 1),
            "brand_category": sum(1 for t, *_ in scored if t == 2),
            "category": sum(1 for t, *_ in scored if t == 3),
        },
    }


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
