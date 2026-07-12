"""Product / Brand / Category endpoints + AI-assisted catalog import stub."""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_user, require_min_role
from db import db, strip_ids
from models import Product, ProductCreate, UserPublic
from services import catalog_service, media_service

router = APIRouter(tags=["catalog"])


# ---------- Brands ----------
@router.get("/brands")
async def list_brands(_: UserPublic = Depends(get_current_user)):
    """Return every brand + its active product count. Counts drive the
    left-rail brand badges in the Quotation Builder V4."""
    return await catalog_service.list_brands_with_counts()


@router.get("/categories")
async def list_categories(
    brand_id: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    """Return categories + per-brand-scoped product counts.

    When `brand_id` is passed, counts reflect ONLY that brand — this is what
    powers the left-rail "Categories under Hansgrohe" list.
    """
    return await catalog_service.list_categories_with_counts(brand_id)




async def _usage_ranked_product_page(
    *,
    query: dict,
    ranked_ids: set[str],
    rank_key,
    skip: int,
    limit: int,
) -> list[dict]:
    """Return a deterministic page with sparse usage-ranked products first.

    Usage exists for only a small fraction of the catalog. The previous path
    downloaded all 2,966 matching {id,name} rows on every page and sorted them
    in Python. This path fetches only matching usage IDs, then lets Mongo page
    the non-usage remainder by the indexed/stable (name,id) order.
    """
    ranked_pool: list[dict] = []
    if ranked_ids:
        ranked_pool = await db.products.find(
            {**query, "id": {"$in": list(ranked_ids)}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(len(ranked_ids))
        ranked_pool.sort(key=rank_key)

    ranked_count = len(ranked_pool)
    selected_ranked = ranked_pool[skip:min(skip + limit, ranked_count)] if skip < ranked_count else []
    regular_skip = max(0, skip - ranked_count)
    regular_needed = limit - len(selected_ranked)

    async def _ranked_full() -> list[dict]:
        ids = [d["id"] for d in selected_ranked]
        if not ids:
            return []
        rows = await db.products.find({"id": {"$in": ids}}, {"_id": 0}).to_list(len(ids))
        by_id = {row["id"]: row for row in rows}
        return [by_id[pid] for pid in ids if pid in by_id]

    async def _regular_full() -> list[dict]:
        if regular_needed <= 0:
            return []
        regular_query = query if not ranked_ids else {**query, "id": {"$nin": list(ranked_ids)}}
        return await db.products.find(regular_query, {"_id": 0}).sort([
            ("name", 1), ("id", 1),
        ]).skip(regular_skip).limit(regular_needed).to_list(regular_needed)

    ranked_full, regular_full = await asyncio.gather(_ranked_full(), _regular_full())
    return [*ranked_full, *regular_full]

# ---------- Products ----------
@router.get("/products")
async def list_products(
    q: Optional[str] = Query(None, description="Free text search on name/sku/description/series/family/finish/colour/tags"),
    brand_id: Optional[str] = None,
    category_id: Optional[str] = None,
    subcategory: Optional[str] = None,
    series: Optional[str] = None,
    family_key: Optional[str] = None,
    finish: Optional[str] = None,
    colour: Optional[str] = None,
    sort: str = Query("popular", description="popular | recent | price_asc | price_desc | name"),
    limit: int = 60,
    skip: int = 0,
    user: UserPublic = Depends(get_current_user),
):
    return await catalog_service.list_products_page(
        user_id=user.id,
        q=q,
        brand_id=brand_id,
        category_id=category_id,
        subcategory=subcategory,
        series=series,
        family_key=family_key,
        finish=finish,
        colour=colour,
        sort=sort,
        limit=limit,
        skip=skip,
    )


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
    rows, brands, cats = await catalog_service.hierarchy_rows()

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
    return await catalog_service.list_family_groups(
        brand_id=brand_id,
        category_id=category_id,
        subcategory=subcategory,
        series=series,
        q=q,
        limit=limit,
        skip=skip,
    )


# ---------- Ranked search (Iteration 2A) ----------
@router.get("/catalog/search")
async def catalog_search(
    q: str = Query("", description="Free-text query"),
    brand_id: Optional[str] = None,
    category_id: Optional[str] = None,
    subcategory: Optional[str] = None,
    series: Optional[str] = None,
    limit: int = 30,
    group: bool = Query(True, description="Group variants by family_key (Shopify-style)"),
    _: UserPublic = Depends(get_current_user),
):
    """Ranked catalog search.

    Ranking priority (highest first):
      1. Exact SKU / SKU prefix
      2. Product name / family name (Mongo text score)
      3. Series / subcategory / finish / colour matches
      4. Fallback dimension / description matches

    Results are grouped by `family_key` by default so callers don't see 6
    duplicates of the same product with different finishes.
    """
    return await catalog_service.search_catalog(
        q=q,
        brand_id=brand_id,
        category_id=category_id,
        subcategory=subcategory,
        series=series,
        limit=limit,
        group=group,
    )


@router.get("/catalog/facets")
async def catalog_facets(
    brand_id: Optional[str] = None,
    category_id: Optional[str] = None,
    subcategory: Optional[str] = None,
    series: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    """Return the facet buckets (brands, categories, finishes, colours,
    price range) for the current selection. Powers the multi-facet filter UI.
    """
    return await catalog_service.facet_buckets(
        brand_id=brand_id,
        category_id=category_id,
        subcategory=subcategory,
        series=series,
    )


# ---------- Family-first canonical page (Iteration 2A shell — used by 2B) ----------
@router.get("/families/{family_key}")
async def get_family(family_key: str, _: UserPublic = Depends(get_current_user)):
    """Return everything the Shopify-style family page needs in a single
    call: family metadata + variants + gallery + specs union. Missing data
    is honestly reported (nulls / empty arrays), never fabricated.
    """
    prods = await db.products.find(
        {"family_key": family_key, "active": True}, {"_id": 0},
    ).sort([("colour", 1), ("finish", 1), ("sku", 1)]).to_list(200)
    if not prods:
        raise HTTPException(status_code=404, detail="Family not found")

    brand = await db.brands.find_one({"id": prods[0].get("brand_id")}, {"_id": 0})
    category = await db.categories.find_one({"id": prods[0].get("category_id")}, {"_id": 0})

    # Aggregate gallery: family-level media first, then union of variant media.
    family_media = await db.product_media.find(
        {"family_key": family_key}, {"_id": 0},
    ).sort([("is_primary", -1), ("sort_order", 1)]).to_list(200)
    variant_ids = [p["id"] for p in prods]
    variant_media = await db.product_media.find(
        {"product_id": {"$in": variant_ids}}, {"_id": 0},
    ).sort([("is_primary", -1), ("sort_order", 1)]).to_list(1000)

    def _pack_media(m: dict) -> dict:
        return {
            "id": m["id"], "url": m.get("public_url"),
            "role": m.get("role"), "source_type": m.get("source_type"),
            "width": m.get("width"), "height": m.get("height"),
            "quality": m.get("quality"), "is_primary": m.get("is_primary"),
            "product_id": m.get("product_id"), "family_key": m.get("family_key"),
        }

    gallery = [_pack_media(m) for m in family_media if m.get("public_url")]
    for m in variant_media:
        if m.get("public_url"):
            gallery.append(_pack_media(m))

    # Union of specs across variants (variant-specific fields kept in per-variant list).
    variants_out = []
    all_specs: dict = {}
    for p in prods:
        variants_out.append({
            "id": p["id"], "sku": p["sku"], "name": p.get("name"),
            "colour": p.get("colour"), "finish": p.get("finish"),
            "finish_code": p.get("finish_code"), "variant_label": p.get("variant_label"),
            "price": p.get("price"), "mrp": p.get("mrp"), "stock": p.get("stock", 0),
            "dimensions": p.get("dimensions"), "material": p.get("material"),
            "warranty": p.get("warranty"), "specs": p.get("specs") or {},
            "hero_image": next(
                (m["public_url"] for m in variant_media
                 if m.get("product_id") == p["id"] and m.get("public_url")), None,
            ),
        })
        for k, v in (p.get("specs") or {}).items():
            all_specs.setdefault(k, v)

    return {
        "family_key": family_key,
        "family_name": prods[0].get("family_name") or prods[0].get("name"),
        "brand": brand,
        "category": category,
        "subcategory": prods[0].get("subcategory"),
        "series": prods[0].get("series"),
        "description": prods[0].get("description"),
        "min_price": min(p.get("price", 0) for p in prods),
        "max_price": max(p.get("price", 0) for p in prods),
        "variant_count": len(prods),
        "variants": variants_out,
        "gallery": gallery,
        "specs_union": all_specs,
        "hero_image_url": next((g["url"] for g in gallery if g.get("is_primary")), (gallery[0]["url"] if gallery else None)),
        "downloads": [],   # Populated in Phase 2B via product_media role=spec-sheet
        "compatible_ids": prods[0].get("compatible_ids") or [],
        "accessory_ids":  prods[0].get("accessory_ids") or [],
        "related_ids":    prods[0].get("related_ids") or [],
    }


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
    ordered = [by_id[i] for i in ids if i in by_id]
    await media_service.hydrate_media_batch(ordered)
    await media_service.hydrate_variants_batch(ordered)
    return ordered


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
    ordered = [by_id[i] for i in ids if i in by_id]
    await media_service.hydrate_media_batch(ordered)
    await media_service.hydrate_variants_batch(ordered)
    return ordered


@router.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str, _: UserPublic = Depends(get_current_user)):
    doc = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    await media_service.hydrate_product_media(doc)
    await media_service.hydrate_variants_batch([doc])
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
    await media_service.hydrate_media_batch(out)
    await media_service.hydrate_variants_batch(out)
    return {
        "source_product_id": product_id,
        "items": out,
        "tiers": {
            "family": sum(1 for t, *_ in scored if t == 1),
            "brand_category": sum(1 for t, *_ in scored if t == 2),
            "category": sum(1 for t, *_ in scored if t == 3),
        },
    }


@router.get("/products/{product_id}/complete-the-set")
async def complete_the_set(
    product_id: str,
    limit: int = 12,
    _: UserPublic = Depends(get_current_user),
):
    """"Complete the set" — same family (Series/Collection) but different
    category. E.g. viewing a Talis E basin mixer suggests the Talis E shower
    valve, spout, robe hook — the classic bathroom cross-sell.
    """
    src = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Product not found")

    match: dict = {"active": True, "id": {"$ne": product_id}, "category_id": {"$ne": src.get("category_id")}}
    fam_key = src.get("family_key")
    series = src.get("series")
    collection = src.get("collection")
    ors = []
    if fam_key:
        ors.append({"family_key": fam_key})
    if series:
        ors.append({"series": series, "brand_id": src.get("brand_id")})
    if collection:
        ors.append({"collection": collection, "brand_id": src.get("brand_id")})
    if not ors:
        return {"source_product_id": product_id, "items": []}
    match["$or"] = ors

    docs = await db.products.find(match, {"_id": 0}).limit(limit).to_list(limit)
    # Group by category so we show one representative per companion category.
    by_cat: dict[str, dict] = {}
    for d in docs:
        cid = d.get("category_id") or "_"
        if cid not in by_cat:
            by_cat[cid] = d
    items = list(by_cat.values())[:limit]
    await media_service.hydrate_media_batch(items)
    await media_service.hydrate_variants_batch(items)
    return {"source_product_id": product_id, "items": items}


@router.post("/products/custom", response_model=Product)
async def create_custom_product(
    body: ProductCreate,
    user: UserPublic = Depends(require_min_role("sales")),
):
    """Create a custom / one-off product from the Quotation Builder.

    When body.is_custom=True, the SKU can collide with existing rows (we
    auto-suffix). If False, we behave like /products with duplicate-SKU
    rejection.
    """
    sku = body.sku or f"CUSTOM-{datetime.now(timezone.utc).strftime('%y%m%d%H%M%S')}"
    if body.is_custom:
        # Auto-uniquify — never fail because the user typed the same SKU twice.
        base = sku
        n = 1
        while await db.products.find_one({"sku": sku}):
            n += 1
            sku = f"{base}-{n}"
    elif await db.products.find_one({"sku": sku}):
        raise HTTPException(status_code=409, detail="SKU already exists")

    payload = body.dict()
    payload["sku"] = sku
    payload["tags"] = list(set([*(payload.get("tags") or []), "custom"]))
    prod = Product(**payload)
    await db.products.insert_one(prod.dict())
    return prod


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
