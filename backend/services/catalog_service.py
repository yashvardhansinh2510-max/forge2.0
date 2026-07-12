"""In-process read model for Forge's supplier catalog.

MongoDB Atlas is geographically remote from the API runtime (~228 ms per
round trip), while the complete production catalog is small (~3 MB products +
~2.6 MB media metadata). Loading one immutable snapshot at startup removes the
multi-round-trip tax from every catalog request. Mutating routes refresh the
snapshot explicitly; a stale-while-revalidate timer is a safety net for writes
performed by offline import scripts.
"""
from __future__ import annotations

import asyncio
import copy
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Optional

from db import db
from models import ProductMedia

_SNAPSHOT_MAX_AGE_SECONDS = 300.0
_MEDIA_PRIORITY = {"internal": 0, "manufacturer": 1, "supplier": 2}
_SEARCH_FIELDS = (
    "name", "sku", "description", "series", "family_name", "subcategory",
    "collection", "finish", "colour", "dimensions", "tags",
)


@dataclass
class CatalogSnapshot:
    products: tuple[dict, ...]
    product_by_id: dict[str, dict]
    products_by_family: dict[str, tuple[dict, ...]]
    media_by_product: dict[str, tuple[ProductMedia, ...]]
    media_by_family: dict[str, tuple[ProductMedia, ...]]
    media_rows_by_product: dict[str, tuple[dict, ...]]
    media_rows_by_family: dict[str, tuple[dict, ...]]
    brands: tuple[dict, ...]
    categories: tuple[dict, ...]
    global_usage: dict[str, int]
    usage_by_user: dict[str, dict[str, dict]]
    loaded_at: float


_snapshot: CatalogSnapshot | None = None
_refresh_lock = asyncio.Lock()
_background_refresh: asyncio.Task | None = None


def _media_sort_key(row: dict) -> tuple[int, int, int]:
    return (
        _MEDIA_PRIORITY.get(row.get("source_type", "supplier"), 3),
        0 if row.get("is_primary") else 1,
        int(row.get("sort_order", 100)),
    )


def _build_snapshot(
    products: list[dict], media_rows: list[dict], brands: list[dict],
    categories: list[dict], usage_rows: list[dict],
) -> CatalogSnapshot:
    product_by_id = {row["id"]: row for row in products}
    products_by_family_raw: dict[str, list[dict]] = defaultdict(list)
    for row in products:
        if row.get("family_key"):
            products_by_family_raw[row["family_key"]].append(row)

    media_product_raw: dict[str, list[dict]] = defaultdict(list)
    media_family_raw: dict[str, list[dict]] = defaultdict(list)
    for row in media_rows:
        if row.get("product_id"):
            media_product_raw[row["product_id"]].append(row)
        if row.get("family_key"):
            media_family_raw[row["family_key"]].append(row)
    for rows in media_product_raw.values():
        rows.sort(key=_media_sort_key)
    for rows in media_family_raw.values():
        rows.sort(key=_media_sort_key)

    global_usage: dict[str, int] = defaultdict(int)
    usage_by_user: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in usage_rows:
        pid = row.get("product_id")
        uid = row.get("user_id")
        if not pid:
            continue
        global_usage[pid] += int(row.get("count", 0))
        if uid:
            usage_by_user[uid][pid] = row

    return CatalogSnapshot(
        products=tuple(products),
        product_by_id=product_by_id,
        products_by_family={key: tuple(rows) for key, rows in products_by_family_raw.items()},
        media_by_product={
            key: tuple(ProductMedia(**row) for row in rows)
            for key, rows in media_product_raw.items()
        },
        media_by_family={
            key: tuple(ProductMedia(**row) for row in rows)
            for key, rows in media_family_raw.items()
        },
        media_rows_by_product={key: tuple(rows) for key, rows in media_product_raw.items()},
        media_rows_by_family={key: tuple(rows) for key, rows in media_family_raw.items()},
        brands=tuple(sorted(brands, key=lambda row: row.get("name") or "")),
        categories=tuple(sorted(categories, key=lambda row: row.get("name") or "")),
        global_usage=dict(global_usage),
        usage_by_user={uid: dict(rows) for uid, rows in usage_by_user.items()},
        loaded_at=monotonic(),
    )


async def refresh_catalog_snapshot() -> CatalogSnapshot:
    """Reload all compact catalog read-model collections in one RTT group."""
    global _snapshot
    async with _refresh_lock:
        products, media_rows, brands, categories, usage_rows = await asyncio.gather(
            db.products.find({"active": True}, {"_id": 0}).to_list(10000),
            db.product_media.find({}, {"_id": 0}).to_list(20000),
            db.brands.find({}, {"_id": 0}).to_list(500),
            db.categories.find({}, {"_id": 0}).to_list(500),
            db.product_usage.find({}, {"_id": 0}).to_list(50000),
        )
        _snapshot = _build_snapshot(products, media_rows, brands, categories, usage_rows)
        return _snapshot


async def get_catalog_snapshot() -> CatalogSnapshot:
    global _background_refresh
    if _snapshot is None:
        return await refresh_catalog_snapshot()
    if monotonic() - _snapshot.loaded_at > _SNAPSHOT_MAX_AGE_SECONDS:
        if _background_refresh is None or _background_refresh.done():
            _background_refresh = asyncio.create_task(refresh_catalog_snapshot())
    return _snapshot


def schedule_catalog_refresh() -> None:
    """Refresh after a catalog/media mutation without delaying its response."""
    global _background_refresh
    if _background_refresh is None or _background_refresh.done():
        _background_refresh = asyncio.create_task(refresh_catalog_snapshot())


def note_product_usage(user_id: str, product_ids: list[str], at: str) -> None:
    """Keep popularity/recent/frequent reads coherent with a completed write."""
    if _snapshot is None:
        return
    mine = _snapshot.usage_by_user.setdefault(user_id, {})
    for product_id in set(product_ids):
        previous = mine.get(product_id, {})
        mine[product_id] = {
            "user_id": user_id,
            "product_id": product_id,
            "count": int(previous.get("count", 0)) + 1,
            "last_used_at": at,
        }
        _snapshot.global_usage[product_id] = _snapshot.global_usage.get(product_id, 0) + 1


def _dedup_media(rows: list[ProductMedia]) -> list[ProductMedia]:
    seen: set[str] = set()
    out: list[ProductMedia] = []
    for row in sorted(rows, key=lambda item: (
        _MEDIA_PRIORITY.get(item.source_type, 3),
        0 if item.is_primary else 1,
        int(item.sort_order),
    )):
        if row.id in seen:
            continue
        seen.add(row.id)
        out.append(row)
    return out


def _apply_media(product: dict, snapshot: CatalogSnapshot) -> None:
    rows = list(snapshot.media_by_product.get(product.get("id"), ()))
    if product.get("family_key"):
        rows.extend(snapshot.media_by_family.get(product["family_key"], ()))
    rows = _dedup_media(rows)

    summary = {"supplier": 0, "manufacturer": 0, "internal": 0}
    for media in rows:
        summary[media.source_type] += 1
    best_quality = "missing"
    for quality in ("excellent", "good", "acceptable", "poor", "missing"):
        if any(media.quality == quality for media in rows):
            best_quality = quality
            break

    gallery: list[dict] = []
    hero_url: Optional[str] = None
    for media in rows:
        if not media.public_url:
            continue
        gallery.append({
            "id": media.id,
            "url": media.public_url,
            "role": media.role,
            "source_type": media.source_type,
            "width": media.width,
            "height": media.height,
            "quality": media.quality,
            "is_primary": media.is_primary,
        })
        if not hero_url and (media.is_primary or media.role == "hero"):
            hero_url = media.public_url
    if not hero_url and gallery:
        hero_url = gallery[0]["url"]

    if not gallery and product.get("images"):
        legacy = product.get("images") or []
        gallery = [
            {
                "url": url, "role": "gallery", "source_type": "supplier",
                "quality": product.get("image_quality") or "missing",
                "width": None, "height": None, "is_primary": index == 0,
            }
            for index, url in enumerate(legacy) if url
        ]
        if gallery:
            hero_url = legacy[0]
            summary["supplier"] = len(gallery)
            best_quality = product.get("image_quality") or best_quality

    product["media_summary"] = {
        **summary, "best_quality": best_quality, "total": sum(summary.values()),
    }
    product["hero_image_url"] = hero_url
    product["gallery"] = gallery
    if gallery:
        product["images"] = [item["url"] for item in gallery if item.get("url")]
    elif hero_url:
        product["images"] = [hero_url]


def _primary_product_image(snapshot: CatalogSnapshot, product_id: str) -> Optional[str]:
    for row in snapshot.media_rows_by_product.get(product_id, ()):
        if row.get("public_url"):
            return row["public_url"]
    return None


def _hydrate_variants(product: dict, snapshot: CatalogSnapshot, limit: int = 8) -> None:
    if product.get("variants") or not product.get("family_key"):
        return
    variants = []
    for sibling in snapshot.products_by_family.get(product["family_key"], ()):
        if sibling["id"] == product["id"]:
            continue
        variants.append({
            "id": sibling["id"],
            "sku": sibling["sku"],
            "finish": sibling.get("finish"),
            "color": sibling.get("colour") or sibling.get("color"),
            "price": float(sibling.get("price") or 0),
            "mrp": float(sibling.get("mrp") or sibling.get("price") or 0),
            "stock": int(sibling.get("stock") or 0),
            "image": _primary_product_image(snapshot, sibling["id"]),
        })
    if variants:
        product["variants"] = variants[:limit]


def hydrate_product(product: dict, snapshot: CatalogSnapshot) -> dict:
    out = copy.deepcopy(product)
    _apply_media(out, snapshot)
    _hydrate_variants(out, snapshot)
    return out


def _matches_filters(product: dict, *, brand_id: Optional[str], category_id: Optional[str],
                     subcategory: Optional[str], series: Optional[str], family_key: Optional[str],
                     finish: Optional[str], colour: Optional[str]) -> bool:
    expected = {
        "brand_id": brand_id,
        "category_id": category_id,
        "subcategory": subcategory,
        "series": series,
        "family_key": family_key,
        "finish": finish,
        "colour": colour,
    }
    return all(value is None or product.get(field) == value for field, value in expected.items())


def _matches_search(product: dict, pattern: re.Pattern | None) -> bool:
    if pattern is None:
        return True
    for field in _SEARCH_FIELDS:
        value = product.get(field)
        if isinstance(value, list):
            text = " ".join(str(item) for item in value)
        else:
            text = str(value or "")
        if pattern.search(text):
            return True
    return False


def _compile_search(query: Optional[str]) -> re.Pattern | None:
    if not query:
        return None
    try:
        return re.compile(query, re.IGNORECASE)
    except re.error:
        return re.compile(re.escape(query), re.IGNORECASE)


def _iso_timestamp(value: object) -> float:
    if not isinstance(value, str) or not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


async def list_products_page(
    *, user_id: str, q: Optional[str], brand_id: Optional[str], category_id: Optional[str],
    subcategory: Optional[str], series: Optional[str], family_key: Optional[str],
    finish: Optional[str], colour: Optional[str], sort: str, limit: int, skip: int,
) -> dict:
    snapshot = await get_catalog_snapshot()
    pattern = _compile_search(q)
    matching = [
        product for product in snapshot.products
        if _matches_filters(
            product, brand_id=brand_id, category_id=category_id,
            subcategory=subcategory, series=series, family_key=family_key,
            finish=finish, colour=colour,
        ) and _matches_search(product, pattern)
    ]
    total = len(matching)
    my_rows = snapshot.usage_by_user.get(user_id, {})

    if sort == "price_asc":
        matching.sort(key=lambda row: (float(row.get("price") or 0), row["id"]))
    elif sort == "price_desc":
        matching.sort(key=lambda row: (-float(row.get("price") or 0), row["id"]))
    elif sort == "name":
        matching.sort(key=lambda row: (row.get("name") or "", row["id"]))
    else:
        if sort == "recent":
            ranked = [row for row in matching if my_rows.get(row["id"], {}).get("last_used_at")]
            ranked.sort(key=lambda row: (
                -_iso_timestamp(my_rows[row["id"]].get("last_used_at")),
                row.get("name") or "", row["id"],
            ))
        else:
            ranked = [row for row in matching if snapshot.global_usage.get(row["id"], 0) > 0]
            ranked.sort(key=lambda row: (
                -snapshot.global_usage.get(row["id"], 0),
                -int(my_rows.get(row["id"], {}).get("count", 0)),
                row.get("name") or "", row["id"],
            ))
        ranked_ids = {row["id"] for row in ranked}
        regular = [row for row in matching if row["id"] not in ranked_ids]
        regular.sort(key=lambda row: (row.get("name") or "", row["id"]))
        matching = [*ranked, *regular]

    usage_counts = sorted(snapshot.global_usage.values(), reverse=True)
    popular_ids: set[str] = set()
    if usage_counts:
        cutoff = min(len(usage_counts) - 1, int(len(usage_counts) * 0.15))
        threshold = usage_counts[cutoff]
        if threshold > 0:
            popular_ids = {
                product_id for product_id, count in snapshot.global_usage.items()
                if count >= threshold
            }

    docs = [hydrate_product(row, snapshot) for row in matching[skip:skip + limit]]
    for doc in docs:
        product_id = doc["id"]
        mine = my_rows.get(product_id, {})
        doc["usage_count"] = snapshot.global_usage.get(product_id, 0)
        doc["my_usage_count"] = int(mine.get("count", 0))
        doc["popular"] = product_id in popular_ids
        doc["frequently_used"] = int(mine.get("count", 0)) >= 3
        doc["recently_used"] = bool(mine.get("last_used_at"))
    return {"total": total, "items": docs}


async def list_brands_with_counts() -> list[dict]:
    snapshot = await get_catalog_snapshot()
    counts = Counter(row.get("brand_id") for row in snapshot.products)
    out = copy.deepcopy(list(snapshot.brands))
    for row in out:
        row["product_count"] = counts.get(row.get("id"), 0)
    return out


async def list_categories_with_counts(brand_id: Optional[str]) -> list[dict]:
    snapshot = await get_catalog_snapshot()
    counts = Counter(
        row.get("category_id") for row in snapshot.products
        if not brand_id or row.get("brand_id") == brand_id
    )
    out = []
    for category in snapshot.categories:
        count = counts.get(category.get("id"), 0)
        if brand_id and count == 0:
            continue
        row = copy.deepcopy(category)
        row["product_count"] = count
        out.append(row)
    return out


async def recent_or_frequent_products(user_id: str, *, limit: int, recent: bool) -> list[dict]:
    snapshot = await get_catalog_snapshot()
    rows = list(snapshot.usage_by_user.get(user_id, {}).values())
    if recent:
        rows.sort(key=lambda row: -_iso_timestamp(row.get("last_used_at")))
    else:
        rows.sort(key=lambda row: -int(row.get("count", 0)))
    out = []
    for usage in rows[:limit]:
        product = snapshot.product_by_id.get(usage.get("product_id"))
        if product:
            out.append(hydrate_product(product, snapshot))
    return out


async def product_by_id(product_id: str) -> dict | None:
    snapshot = await get_catalog_snapshot()
    product = snapshot.product_by_id.get(product_id)
    return hydrate_product(product, snapshot) if product else None


async def hierarchy_rows() -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    snapshot = await get_catalog_snapshot()
    groups: dict[tuple, dict] = {}
    for product in snapshot.products:
        key = (
            product.get("brand_id"), product.get("category_id"), product.get("subcategory"),
            product.get("series"), product.get("family_key"), product.get("family_name"),
        )
        row = groups.setdefault(key, {
            "_id": {
                "brand_id": key[0], "category_id": key[1], "subcategory": key[2],
                "series": key[3], "family_key": key[4], "family_name": key[5],
            },
            "product_count": 0,
            "min_price": float(product.get("price") or 0),
            "sample_image": (product.get("images") or [None])[0],
            "image_quality": product.get("image_quality"),
        })
        row["product_count"] += 1
        row["min_price"] = min(row["min_price"], float(product.get("price") or 0))
    return (
        list(groups.values()),
        {row["id"]: copy.deepcopy(row) for row in snapshot.brands},
        {row["id"]: copy.deepcopy(row) for row in snapshot.categories},
    )


async def list_family_groups(
    *, brand_id: Optional[str], category_id: Optional[str], subcategory: Optional[str],
    series: Optional[str], q: Optional[str], limit: int, skip: int,
) -> dict:
    snapshot = await get_catalog_snapshot()
    pattern = _compile_search(q)
    products = [
        row for row in snapshot.products
        if row.get("family_key")
        and _matches_filters(
            row, brand_id=brand_id, category_id=category_id, subcategory=subcategory,
            series=series, family_key=None, finish=None, colour=None,
        )
        and (pattern is None or any(pattern.search(str(row.get(field) or "")) for field in (
            "name", "family_name", "series", "subcategory", "finish", "colour", "sku",
        )))
    ]
    products.sort(key=lambda row: (
        row.get("family_name") or "", row.get("colour") or "", row.get("sku") or "",
    ))
    groups: dict[str, dict] = {}
    for product in products:
        key = product["family_key"]
        group = groups.setdefault(key, {
            "family_key": key,
            "family_name": product.get("family_name"),
            "brand_id": product.get("brand_id"),
            "category_id": product.get("category_id"),
            "subcategory": product.get("subcategory"),
            "series": product.get("series"),
            "min_price": float(product.get("price") or 0),
            "max_price": float(product.get("price") or 0),
            "product_count": 0,
            "sample_image": (product.get("images") or [None])[0],
            "sample_image_quality": product.get("image_quality"),
            "variants": [],
        })
        price = float(product.get("price") or 0)
        group["min_price"] = min(group["min_price"], price)
        group["max_price"] = max(group["max_price"], price)
        group["product_count"] += 1
        group["variants"].append({
            "id": product["id"], "sku": product["sku"],
            "variant_label": product.get("variant_label"), "colour": product.get("colour"),
            "finish": product.get("finish"), "finish_code": product.get("finish_code"),
            "price": product.get("price"), "mrp": product.get("mrp"),
            "image": (product.get("images") or [None])[0],
            "image_quality": product.get("image_quality"),
        })
    ordered = sorted(groups.values(), key=lambda row: row.get("family_name") or "")
    page = copy.deepcopy(ordered[skip:skip + limit])
    for group in page:
        sample_id = (group.get("variants") or [{}])[0].get("id")
        media = (
            snapshot.media_rows_by_family.get(group.get("family_key"), ())
            or snapshot.media_rows_by_product.get(sample_id, ())
        )
        hero = next((row for row in media if row.get("public_url")), None)
        if hero:
            group["sample_image"] = hero["public_url"]
            group["sample_image_quality"] = hero.get("quality") or group.get("sample_image_quality")
            group["sample_image_source"] = hero.get("source_type")
    return {"total": len(ordered), "items": page}


async def facet_buckets(
    *, brand_id: Optional[str], category_id: Optional[str], subcategory: Optional[str],
    series: Optional[str],
) -> dict:
    snapshot = await get_catalog_snapshot()
    products = [
        row for row in snapshot.products
        if _matches_filters(
            row, brand_id=brand_id, category_id=category_id, subcategory=subcategory,
            series=series, family_key=None, finish=None, colour=None,
        )
    ]

    def bucket(field: str) -> list[dict]:
        counts = Counter(row.get(field) for row in products if row.get(field) not in (None, ""))
        return [
            {"value": value, "count": count}
            for value, count in sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))[:100]
        ]

    prices = [float(row.get("price") or 0) for row in products]
    return {
        "brands": bucket("brand_id"),
        "categories": bucket("category_id"),
        "subcategories": bucket("subcategory"),
        "series": bucket("series"),
        "finishes": bucket("finish"),
        "colours": bucket("colour"),
        "materials": bucket("material"),
        "price": {"min": min(prices, default=0), "max": max(prices, default=0)},
    }


async def search_catalog(
    *, q: str, brand_id: Optional[str], category_id: Optional[str], subcategory: Optional[str],
    series: Optional[str], limit: int, group: bool,
) -> dict:
    snapshot = await get_catalog_snapshot()
    query = (q or "").strip()
    q_lower = query.lower()
    products = [
        row for row in snapshot.products
        if _matches_filters(
            row, brand_id=brand_id, category_id=category_id, subcategory=subcategory,
            series=series, family_key=None, finish=None, colour=None,
        )
    ]

    def score(product: dict) -> float:
        sku = (product.get("sku") or "").lower()
        name = (product.get("name") or "").lower()
        family = (product.get("family_name") or "").lower()
        series_l = (product.get("series") or "").lower()
        subcat = (product.get("subcategory") or "").lower()
        finish_l = (product.get("finish") or "").lower()
        colour_l = (product.get("colour") or "").lower()
        dimensions = (product.get("dimensions") or "").lower()
        description = (product.get("description") or "").lower()
        value = 0.0
        if sku == q_lower:
            value += 100
        elif sku.startswith(q_lower):
            value += 60
        elif q_lower in sku:
            value += 30
        value += 12 if q_lower in name else 0
        value += 10 if q_lower in family else 0
        value += 6 if q_lower in series_l else 0
        value += 4 if q_lower in subcat else 0
        value += 3 if q_lower in finish_l else 0
        value += 3 if q_lower in colour_l else 0
        value += 1 if q_lower in dimensions else 0
        value += 1 if q_lower in description else 0
        return value

    if query:
        scored = [(score(row), row) for row in products]
        docs = [row for value, row in sorted(scored, key=lambda item: item[0], reverse=True) if value > 0][:limit * 3]
    else:
        docs = products[:limit * 3]

    if not group:
        items = [hydrate_product(row, snapshot) for row in docs[:limit]]
        return {"query": query, "total": len(docs), "grouped": False, "items": items}

    groups: dict[str, dict] = {}
    order: list[str] = []
    for product in docs:
        key = product.get("family_key") or f"solo:{product['id']}"
        if key not in groups:
            groups[key] = {
                "family_key": product.get("family_key"),
                "family_name": product.get("family_name") or product.get("name"),
                "brand_id": product.get("brand_id"), "category_id": product.get("category_id"),
                "subcategory": product.get("subcategory"), "series": product.get("series"),
                "score": score(product) if query else 0,
                "product_count": 0, "min_price": product.get("price"),
                "max_price": product.get("price"), "variants": [],
                "sample_product_id": product["id"],
            }
            order.append(key)
        family = groups[key]
        family["product_count"] += 1
        family["min_price"] = min(family["min_price"], product.get("price") or family["min_price"])
        family["max_price"] = max(family["max_price"], product.get("price") or family["max_price"])
        family["variants"].append({
            "id": product["id"], "sku": product["sku"], "colour": product.get("colour"),
            "finish": product.get("finish"), "price": product.get("price"),
        })

    grouped = [groups[key] for key in order][:limit]
    for family in grouped:
        media = ()
        if family.get("family_key"):
            media = snapshot.media_rows_by_family.get(family["family_key"], ())
        if not media:
            media = snapshot.media_rows_by_product.get(family["sample_product_id"], ())
        hero = next((row for row in media if row.get("public_url")), None)
        if hero:
            family["hero_image_url"] = hero.get("public_url")
            family["image_quality"] = hero.get("quality")
            family["image_source"] = hero.get("source_type")
    return {"query": query, "total": len(order), "grouped": True, "items": grouped}
