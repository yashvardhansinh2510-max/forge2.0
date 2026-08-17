import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auth import TILES_FLOOR_ID
from catalog_pipeline.integrity_guard import scan_catalog
from db import db


async def main():
    brand = await db.brands.find_one({"name": "SANIT", "floor_id": TILES_FLOOR_ID}, {"_id": 0})
    category = await db.categories.find_one({"name": "Tiles", "floor_id": TILES_FLOOR_ID}, {"_id": 0})
    products = await db.products.find({"brand_id": brand["id"], "floor_id": TILES_FLOOR_ID}, {"_id": 0}).to_list(100)
    jobs = await db.catalog_imports.find({"supplier_name": "SANIT", "floor_id": TILES_FLOOR_ID}, {"_id": 0}).sort("created_at", -1).to_list(10)
    media = await db.product_media.find({"brand_id": brand["id"], "floor_id": TILES_FLOOR_ID, "source_type": "supplier"}, {"_id": 0, "product_id": 1, "public_url": 1, "storage_key": 1}).to_list(100)
    result = await scan_catalog()
    print(json.dumps({
        "brand": {"name": brand["name"], "floor_id": brand["floor_id"], "slug": brand["slug"]},
        "category": {"name": category["name"], "floor_id": category["floor_id"]},
        "product_count": len(products),
        "sku_count": len({p["sku"] for p in products}),
        "prices_present": all(isinstance(p.get("price"), (int, float)) and p["price"] >= 0 for p in products),
        "sizes_present": sum(bool(p.get("size")) for p in products),
        "media_count": len(media),
        "media_products_covered": len({m.get("product_id") for m in media}),
        "jobs": [{"id": j["id"], "status": j["status"], "accepted_rows": j.get("accepted_rows"), "source_asset": bool(j.get("source_asset"))} for j in jobs],
        "first_floor_leak_count": await db.products.count_documents({"brand_id": brand["id"], "floor_id": "first-floor"}),
        "integrity_guard": result.to_public(),
        "sample": [{k: p.get(k) for k in ("name", "sku", "size", "price", "floor_id")} for p in products[:3]],
    }, indent=2, default=str))


asyncio.run(main())
