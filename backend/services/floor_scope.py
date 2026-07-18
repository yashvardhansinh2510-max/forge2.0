"""Floor/department scope bootstrap and shared defaults."""
from db import db
from models import now_iso

DEFAULT_FLOORS = (
    ("ground-floor", "Ground floor"),
    ("first-floor", "The Sanitary Bathroom"),
    ("second-floor", "Second floor"),
)

SCOPED_COLLECTIONS = (
    "customers", "products", "quotations", "suppliers", "purchase_orders",
    "payments", "followups", "product_media",
)


async def ensure_floor_scope() -> None:
    """Create the initial departments and backfill legacy data once.

    Existing Forge data represents the current First-floor department, so it
    is deliberately migrated there. New records receive a floor from the
    authenticated user's assignment.
    """
    if await db.floors.count_documents({}) == 0:
        now = now_iso()
        await db.floors.insert_many([
            {"id": slug, "name": name, "slug": slug, "active": True,
             "created_at": now, "updated_at": now}
            for slug, name in DEFAULT_FLOORS
        ])
    for collection in SCOPED_COLLECTIONS:
        await db[collection].update_many(
            {"floor_id": {"$exists": False}},
            {"$set": {"floor_id": "first-floor"}},
        )
    # Staff created before floor scoping saw every record. Grant them every
    # floor once so the feature's default-deny doesn't blank their app; owners
    # can narrow assignments afterwards in Team settings. Only runs for users
    # that have never had a floor_ids field.
    all_floor_ids = [doc["id"] async for doc in db.floors.find({"active": True}, {"_id": 0, "id": 1})]
    await db.users.update_many(
        {"floor_ids": {"$exists": False}},
        {"$set": {"floor_ids": all_floor_ids}},
    )
