"""Product / Brand / Category endpoints + AI-assisted catalog import stub."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_user, require_min_role
from db import db, strip_ids
from models import Product, ProductCreate, UserPublic
from services import media_service

router = APIRouter(tags=["catalog"])


# ---------- Brands ----------
@router.get("/brands")
async def list_brands(_: UserPublic = Depends(get_current_user)):
    """Return every brand + its active product count. Counts drive the
    left-rail brand badges in the Quotation Builder V4."""
    docs = await db.brands.find({}, {"_id": 0}).sort("name", 1).to_list(500)
    # Single aggregation to count products by brand.
    agg = await db.products.aggregate([
        {"$match": {"active": True}},
        {"$group": {"_id": "$brand_id", "count": {"$sum": 1}}},
    ]).to_list(1000)
    counts = {r["_id"]: r["count"] for r in agg}
    for d in docs:
        d["product_count"] = counts.get(d.get("id"), 0)
    return docs


@router.get("/categories")
async def list_categories(
    brand_id: Optional[str] = None,
    _: UserPublic = Depends(get_current_user),
):
    """Return categories + per-brand-scoped product counts.

    When `brand_id` is passed, counts reflect ONLY that brand — this is what
    powers the left-rail "Categories under Hansgrohe" list.
    """
    docs = await db.categories.find({}, {"_id": 0}).sort("name", 1).to_list(500)
    match: dict = {"active": True}
    if brand_id:
        match["brand_id"] = brand_id
    agg = await db.products.aggregate([
        {"$match": match},
        {"$group": {"_id": "$category_id", "count": {"$sum": 1}}},
    ]).to_list(1000)
    counts = {r["_id"]: r["count"] for r in agg}
    out = []
    for d in docs:
        cnt = counts.get(d.get("id"), 0)
        if brand_id and cnt == 0:
            # Hide categories with zero products for the selected brand — the
            # builder's brand→category tree should show only what's shoppable.
            continue
        d["product_count"] = cnt
        out.append(d)
    return out


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
            {"collection":  {"$regex": q, "$options": "i"}},
            {"finish":      {"$regex": q, "$options": "i"}},
            {"colour":      {"$regex": q, "$options": "i"}},
            {"dimensions":  {"$regex": q, "$options": "i"}},
            {"tags":        {"$regex": q, "$options": "i"}},
        ]
    total = await db.products.count_documents(query)

    # ----- Global + per-user usage lookups (bounded, cached in-process) -----
    global_usage_agg = await db.product_usage.aggregate([
        {"$group": {"_id": "$product_id", "total": {"$sum": "$count"}}},
    ]).to_list(20000)
    global_usage = {r["_id"]: int(r["total"]) for r in global_usage_agg}
    my_usage_rows = await db.product_usage.find(
        {"user_id": user.id}, {"_id": 0, "product_id": 1, "count": 1, "last_used_at": 1}
    ).to_list(20000)
    my_usage = {r["product_id"]: int(r.get("count", 0)) for r in my_usage_rows}
    my_recent_at = {r["product_id"]: r.get("last_used_at") for r in my_usage_rows}

    # "Popular" = product is in the top 15% globally by aggregated usage.
    popular_ids: set[str] = set()
    if global_usage:
        sorted_counts = sorted(global_usage.values(), reverse=True)
        cutoff_idx = max(0, min(len(sorted_counts) - 1, int(len(sorted_counts) * 0.15)))
        threshold = sorted_counts[cutoff_idx] if sorted_counts else 0
        if threshold > 0:
            popular_ids = {pid for pid, cnt in global_usage.items() if cnt >= threshold}

    # ----- Sort -----
    if sort == "recent":
        # Products with recent usage first (by this user), then everything else.
        docs = await db.products.find(query, {"_id": 0}).to_list(min(8000, total or 8000))
        docs.sort(key=lambda d: (my_recent_at.get(d["id"]) or "", d.get("name") or ""), reverse=True)
        docs = docs[skip:skip + limit]
    elif sort == "price_asc":
        docs = await db.products.find(query, {"_id": 0}).sort("price", 1).skip(skip).limit(limit).to_list(limit)
    elif sort == "price_desc":
        docs = await db.products.find(query, {"_id": 0}).sort("price", -1).skip(skip).limit(limit).to_list(limit)
    elif sort == "name":
        docs = await db.products.find(query, {"_id": 0}).sort("name", 1).skip(skip).limit(limit).to_list(limit)
    else:  # popular / most_used (default)
        # Pull a wide pool then rank by (global usage DESC, my usage DESC, name ASC).
        # Cap is comfortably above the full catalog size (2966 at last count)
        # so pagination actually reaches every product — not just the first
        # 2000 in Mongo's natural order — even on the unfiltered "All brands"
        # view, which is the very first thing a salesperson sees.
        pool_cap = min(8000, total or 8000)
        pool = await db.products.find(query, {"_id": 0}).limit(pool_cap).to_list(pool_cap)
        pool.sort(key=lambda d: (
            -global_usage.get(d["id"], 0),
            -my_usage.get(d["id"], 0),
            d.get("name") or "",
        ))
        docs = pool[skip:skip + limit]

    docs = strip_ids(docs)
    for d in docs:
        await media_service.hydrate_product_media(d)
        pid = d.get("id")
        d["usage_count"] = global_usage.get(pid, 0)
        d["my_usage_count"] = my_usage.get(pid, 0)
        d["popular"] = pid in popular_ids
        d["frequently_used"] = my_usage.get(pid, 0) >= 3
        d["recently_used"] = bool(my_recent_at.get(pid))
    await media_service.hydrate_variants_batch(docs)
    return {"total": total, "items": docs}


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
    if brand_id:
        match["brand_id"] = brand_id
    if category_id:
        match["category_id"] = category_id
    if subcategory:
        match["subcategory"] = subcategory
    if series:
        match["series"] = series
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
    # Enrich each family with a hero image from product_media (falls back to
    # legacy embedded sample_image if the family has no media rows yet).
    for f in fams:
        f.pop("_id", None)
        hero = await db.product_media.find_one(
            {"$or": [{"family_key": f.get("family_key")},
                     {"product_id": (f.get("variants") or [{}])[0].get("id")}]},
            {"_id": 0, "public_url": 1, "quality": 1, "source_type": 1},
            sort=[("is_primary", -1), ("sort_order", 1)],
        )
        if hero and hero.get("public_url"):
            f["sample_image"] = hero["public_url"]
            f["sample_image_quality"] = hero.get("quality") or f.get("sample_image_quality")
            f["sample_image_source"] = hero.get("source_type")
    # total distinct families for this query
    total_pipeline = [
        {"$match": match}, {"$group": {"_id": "$family_key"}}, {"$count": "n"},
    ]
    total = 0
    async for r in db.products.aggregate(total_pipeline):
        total = r.get("n", 0)
    return {"total": total, "items": fams}


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
    q = (q or "").strip()
    filters: dict = {"active": True}
    if brand_id:
        filters["brand_id"] = brand_id
    if category_id:
        filters["category_id"] = category_id
    if subcategory:
        filters["subcategory"] = subcategory
    if series:
        filters["series"] = series

    if not q:
        # No query — return a lightweight top families list respecting filters.
        docs = await db.products.find(filters, {"_id": 0}).limit(limit * 3).to_list(limit * 3)
    else:
        # Try Mongo text search first
        text_query = {**filters, "$text": {"$search": q}}
        try:
            docs = await db.products.find(
                text_query,
                {"_id": 0, "score": {"$meta": "textScore"}},
            ).sort([("score", {"$meta": "textScore"})]).limit(limit * 3).to_list(limit * 3)
        except Exception:  # noqa: BLE001
            docs = []
        # Fallback / augment with regex on SKU + name (catches partial matches
        # that Mongo's text index misses like "7040" → "70405L003-...").
        if len(docs) < limit:
            regex_query = {
                **filters,
                "$or": [
                    {"sku": {"$regex": q, "$options": "i"}},
                    {"name": {"$regex": q, "$options": "i"}},
                    {"family_name": {"$regex": q, "$options": "i"}},
                    {"series": {"$regex": q, "$options": "i"}},
                    {"finish": {"$regex": q, "$options": "i"}},
                    {"colour": {"$regex": q, "$options": "i"}},
                    {"dimensions": {"$regex": q, "$options": "i"}},
                ],
            }
            more = await db.products.find(regex_query, {"_id": 0}).limit(limit * 3).to_list(limit * 3)
            seen = {d["id"] for d in docs}
            for m in more:
                if m["id"] not in seen:
                    docs.append(m)

    # ----- Scoring -----
    q_lower = q.lower()

    def score(p: dict) -> float:
        s = float(p.get("score") or 0.0) * 2.0   # baseline from text score
        sku = (p.get("sku") or "").lower()
        name = (p.get("name") or "").lower()
        family = (p.get("family_name") or "").lower()
        series_l = (p.get("series") or "").lower()
        subcat = (p.get("subcategory") or "").lower()
        finish = (p.get("finish") or "").lower()
        colour = (p.get("colour") or "").lower()
        dims = (p.get("dimensions") or "").lower()
        desc = (p.get("description") or "").lower()

        if q_lower:
            if sku == q_lower:
                s += 100
            elif sku.startswith(q_lower):
                s += 60
            elif q_lower in sku:
                s += 30
            if q_lower in name:
                s += 12
            if q_lower in family:
                s += 10
            if q_lower in series_l:
                s += 6
            if q_lower in subcat:
                s += 4
            if q_lower in finish:
                s += 3
            if q_lower in colour:
                s += 3
            if q_lower in dims:
                s += 1
            if q_lower in desc:
                s += 1
        return s

    for p in docs:
        p["_score"] = score(p)
    docs.sort(key=lambda p: p["_score"], reverse=True)

    if not group:
        for d in docs[:limit]:
            await media_service.hydrate_product_media(d)
        return {"query": q, "total": len(docs), "grouped": False, "items": docs[:limit]}

    # ----- Group by family_key -----
    groups: dict = {}
    order: list[str] = []
    for p in docs:
        key = p.get("family_key") or f"solo:{p['id']}"
        if key not in groups:
            groups[key] = {
                "family_key": p.get("family_key"),
                "family_name": p.get("family_name") or p.get("name"),
                "brand_id": p.get("brand_id"),
                "category_id": p.get("category_id"),
                "subcategory": p.get("subcategory"),
                "series": p.get("series"),
                "score": p["_score"],
                "product_count": 0,
                "min_price": p.get("price"),
                "max_price": p.get("price"),
                "variants": [],
                "sample_product_id": p["id"],
            }
            order.append(key)
        g = groups[key]
        g["product_count"] += 1
        g["min_price"] = min(g["min_price"], p.get("price") or g["min_price"])
        g["max_price"] = max(g["max_price"], p.get("price") or g["max_price"])
        g["variants"].append({
            "id": p["id"], "sku": p["sku"], "colour": p.get("colour"),
            "finish": p.get("finish"), "price": p.get("price"),
        })

    grouped = [groups[k] for k in order][:limit]

    # Attach hero image per group (from product_media)
    for g in grouped:
        hero = None
        if g.get("family_key"):
            hero = await db.product_media.find_one(
                {"family_key": g["family_key"]},
                {"_id": 0, "public_url": 1, "quality": 1, "source_type": 1},
                sort=[("is_primary", -1), ("sort_order", 1)],
            )
        if not hero:
            hero = await db.product_media.find_one(
                {"product_id": g["sample_product_id"]},
                {"_id": 0, "public_url": 1, "quality": 1, "source_type": 1},
                sort=[("is_primary", -1), ("sort_order", 1)],
            )
        if hero:
            g["hero_image_url"] = hero.get("public_url")
            g["image_quality"] = hero.get("quality")
            g["image_source"] = hero.get("source_type")

    return {"query": q, "total": len(order), "grouped": True, "items": grouped}


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
    match: dict = {"active": True}
    if brand_id:
        match["brand_id"] = brand_id
    if category_id:
        match["category_id"] = category_id
    if subcategory:
        match["subcategory"] = subcategory
    if series:
        match["series"] = series

    async def _bucket(field: str) -> list[dict]:
        pipeline = [
            {"$match": {**match, field: {"$nin": [None, ""]}}},
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
            {"$sort": {"count": -1, "_id": 1}},
            {"$limit": 100},
        ]
        rows = await db.products.aggregate(pipeline).to_list(100)
        return [{"value": r["_id"], "count": r["count"]} for r in rows]

    price_stats = await db.products.aggregate([
        {"$match": match},
        {"$group": {"_id": None, "min": {"$min": "$price"}, "max": {"$max": "$price"}}},
    ]).to_list(1)
    price = price_stats[0] if price_stats else {"min": 0, "max": 0}

    return {
        "brands":        await _bucket("brand_id"),
        "categories":    await _bucket("category_id"),
        "subcategories": await _bucket("subcategory"),
        "series":        await _bucket("series"),
        "finishes":      await _bucket("finish"),
        "colours":       await _bucket("colour"),
        "materials":     await _bucket("material"),
        "price":         {"min": price.get("min", 0) or 0, "max": price.get("max", 0) or 0},
    }


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
    for p in ordered:
        await media_service.hydrate_product_media(p)
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
    for p in ordered:
        await media_service.hydrate_product_media(p)
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
    for p in out:
        await media_service.hydrate_product_media(p)
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
    for p in items:
        await media_service.hydrate_product_media(p)
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
