"""Import approved Hansgrohe job into production. Removes standalone AXOR brand."""
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


async def main():
    # 1. Ensure standalone AXOR brand is disabled (products only go under Hansgrohe)
    axor = await db.brands.find_one({"name": "Axor"})
    if axor:
        await db.brands.update_one({"id": axor["id"]}, {"$set": {"active": False}})
        # Also move any (erroneously created) products from AXOR brand → Hansgrohe
        hg = await db.brands.find_one({"name": "Hansgrohe"})
        if hg:
            n = await db.products.update_many({"brand_id": axor["id"]}, {"$set": {"brand_id": hg["id"], "collection": "AXOR"}})
            if n.modified_count:
                print(f"reassigned {n.modified_count} products from Axor brand → Hansgrohe/AXOR collection")

    # 2. Approve
    doc = await db.catalog_imports.find_one(
        {"supplier_name": "Hansgrohe", "status": "classified"},
        {"_id": 0}, sort=[("created_at", -1)],
    )
    if not doc:
        print("no classified Hansgrohe job found")
        return

    owner = await db.users.find_one({"email": "owner@forge.app"}, {"id": 1, "_id": 0})
    t0 = time.time()
    print(f"→ Hansgrohe import (job {doc['id']}) — this uploads to Supabase in parallel; may take 3–5 min...", flush=True)
    stats = await import_accepted(doc, (owner or {}).get("id", "system"))
    await db.catalog_imports.update_one(
        {"id": doc["id"]},
        {"$set": {"status": "imported",
                  "accepted_rows": stats["imported"] + stats["updated"],
                  "rejected_rows": stats["skipped"]}},
    )
    print(f"done in {round(time.time()-t0,1)}s → {json.dumps(stats)}")

    # 3. Cleanup blobs (they've served their purpose)
    ok = await db.catalog_image_blobs.count_documents({})
    print(f"catalog_image_blobs rows remaining: {ok}  (kept for rollback safety)")

    # 4. Report
    hg = await db.brands.find_one({"name": "Hansgrohe"}, {"_id": 0})
    p = await db.products.count_documents({"brand_id": hg["id"], "active": True})
    m = await db.product_media.count_documents({"brand_id": hg["id"]})
    axor_count = await db.products.count_documents({"brand_id": hg["id"], "collection": "AXOR", "active": True})
    hg_count = await db.products.count_documents({"brand_id": hg["id"], "collection": "Hansgrohe", "active": True})
    fams = len(await db.products.distinct("family_key", {"brand_id": hg["id"], "family_key": {"$ne": None}, "active": True}))
    cats = len(await db.products.distinct("category_id", {"brand_id": hg["id"], "active": True}))
    sers = len(await db.products.distinct("series", {"brand_id": hg["id"], "series": {"$ne": None}, "active": True}))
    print(f"HANSGROHE FINAL  products={p}  (AXOR={axor_count} · main={hg_count})  media={m}  families={fams}  categories={cats}  series={sers}")


if __name__ == "__main__":
    asyncio.run(main())
