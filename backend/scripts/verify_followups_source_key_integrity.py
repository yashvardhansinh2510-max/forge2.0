"""One-off DB verification script (not a pytest test) — connects directly to
Mongo using backend/.env's MONGO_URL/DB_NAME to independently confirm:
  1. The partial unique index on followups.source_key actually exists.
  2. Zero duplicate source_key values exist collection-wide (any status),
     not just among currently-OPEN rows.
Run once, ad-hoc, from /app/backend.
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    indexes = await db.followups.index_information()
    src_idx = [(name, spec) for name, spec in indexes.items() if "source_key" in str(spec.get("key"))]
    print("Indexes on followups touching source_key:")
    for name, spec in src_idx:
        print(f"  {name}: unique={spec.get('unique')} partialFilterExpression={spec.get('partialFilterExpression')}")

    pipeline = [
        {"$match": {"source_key": {"$ne": None}}},
        {"$group": {"_id": "$source_key", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
    ]
    dupes = await db.followups.aggregate(pipeline).to_list(1000)
    print(f"\nDuplicate source_key groups (collection-wide, any status): {len(dupes)}")
    for d in dupes[:20]:
        print(f"  {d['_id']}: {d['count']} rows")

    total = await db.followups.count_documents({})
    automated = await db.followups.count_documents({"is_automated": True})
    print(f"\nTotal followups: {total}, automated: {automated}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
