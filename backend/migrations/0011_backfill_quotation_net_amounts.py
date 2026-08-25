"""Denormalize each quotation line's post-discount total onto
items[].net_amount.

Before this, per-line revenue was recomputed per report as qty x unit_price
— ignoring the product/room/category/project discount cascade — so brand and
product revenue never summed to grand_total. Analytics now sums net_amount,
which is stamped at write time (routes/quotation_routes.py); this migration
backfills every document written before that landed.

Uses services.pricing.stamp_net_amounts — the SAME positional stamping the
write path uses — rather than the id-keyed per_line_net_amounts. Line ids are
client-supplied and unenforced, and pre-id legacy lines have no "id" at all;
an id-keyed lookup collapses duplicates onto one value and resolves a missing
id to 0.0, which would zero out real revenue on exactly the oldest documents
this migration exists to fix.

Idempotent: recomputing from the same source fields always yields the same
value, so re-running is a no-op. Nothing is deleted.
"""
from __future__ import annotations

from models import RoomDiscountCfg

from services.pricing import stamp_net_amounts


def compute_net_amount_items(doc: dict) -> list[dict]:
    """Return the doc's items with net_amount stamped, leaving every other
    field untouched. Pure — no database access, no mutation of the input —
    so it is unit-testable."""
    return stamp_net_amounts(
        [dict(raw) for raw in doc.get("items", []) or []],
        doc.get("project_discount_pct", 0) or 0,
        doc.get("category_discounts", {}) or {},
        {k: RoomDiscountCfg(**v) for k, v in (doc.get("room_discounts") or {}).items()},
    )


async def up(db) -> None:
    cursor = db.quotations.find({"items.0": {"$exists": True}}, {"_id": 0})
    async for doc in cursor:
        await db.quotations.update_one(
            {"id": doc["id"]},
            {"$set": {"items": compute_net_amount_items(doc)}},
        )
