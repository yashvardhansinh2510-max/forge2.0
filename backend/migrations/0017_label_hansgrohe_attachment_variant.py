"""Label the verified Hansgrohe attachment variant without changing prices."""
from __future__ import annotations

from models import now_iso

PRODUCT_ID = "811a1b0f-1b20-401b-9f36-e8134b63bbf2"


async def up(db) -> None:
    await db.products.update_one(
        {"id": PRODUCT_ID, "sku": "26456000-2"},
        {"$set": {"variant_label": "With attachment", "updated_at": now_iso()}},
    )
