"""Approve+import ALL classified imports (Vitra, Grohe, Geberit)."""
from __future__ import annotations
import asyncio
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from catalog_pipeline.orchestrator import import_accepted  # noqa: E402
from db import db  # noqa: E402


async def approve_brand(brand: str) -> dict:
    doc = await db.catalog_imports.find_one({"supplier_name": brand, "status": "classified"}, {"_id": 0}, sort=[("created_at", -1)])
    if not doc:
        return {"brand": brand, "error": "no_classified_job"}
    t0 = time.time()
    owner = await db.users.find_one({"email": "owner@forge.app"}, {"id": 1, "_id": 0})
    stats = await import_accepted(doc, (owner or {}).get("id", "system"))
    await db.catalog_imports.update_one(
        {"id": doc["id"]},
        {"$set": {"status": "imported",
                  "accepted_rows": stats["imported"] + stats["updated"],
                  "rejected_rows": stats["skipped"]}},
    )
    return {"brand": brand, "job_id": doc["id"], "runtime_s": round(time.time()-t0, 1), **stats}


async def main():
    out = []
    for b in ("Vitra", "Grohe", "Geberit"):
        print(f"→ {b} …", flush=True)
        r = await approve_brand(b)
        print(json.dumps(r, default=str), flush=True)
        out.append(r)
    # tallies
    prod = await db.products.count_documents({"active": True})
    fams = len(await db.products.distinct("family_key", {"family_key": {"$ne": None}}))
    subs = len(await db.products.distinct("subcategory", {"subcategory": {"$ne": None}}))
    sers = len(await db.products.distinct("series", {"series": {"$ne": None}}))
    cats = await db.categories.count_documents({})
    media = await db.product_media.count_documents({})
    print("\n=== TOTALS ===")
    print(json.dumps({"products": prod, "families": fams, "subcategories": subs,
                      "series": sers, "categories": cats, "media": media}, indent=2))
    Path("/app/memory/import_final_tally.json").write_text(json.dumps({"per_brand": out, "totals": {
        "products": prod, "families": fams, "subcategories": subs, "series": sers,
        "categories": cats, "media": media}}, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
