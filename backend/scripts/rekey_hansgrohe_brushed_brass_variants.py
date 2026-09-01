"""Repair legacy AXOR/Hansgrohe Brushed Brass family-key fragmentation.

Older imports treated ``Brushed Brass`` as a generic Bronze SKU-tail fallback,
so the finish text became part of the family key.  This idempotent repair
only changes rows when their finish-stripped target family already exists in
the same brand, category and floor.  Product IDs, SKUs, prices and product
media ownership remain untouched; only display/family metadata is corrected.

Run without flags to inspect.  ``--execute`` writes a JSON backup first.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from db import db


SUFFIX = "-brushed-brass"


async def run(*, execute: bool) -> dict:
    brands = await db.brands.find(
        {"slug": {"$in": ["hansgrohe", "axor"]}}, {"_id": 0, "id": 1, "name": 1}
    ).to_list(10)
    brand_ids = [brand["id"] for brand in brands]
    products = await db.products.find(
        {
            "brand_id": {"$in": brand_ids},
            "active": True,
            "family_key": {"$regex": f"{SUFFIX}$"},
        },
        {"_id": 0},
    ).to_list(1000)

    changes: list[dict] = []
    for product in products:
        source_key = str(product.get("family_key") or "")
        target_key = source_key.removesuffix(SUFFIX)
        if target_key == source_key:
            continue
        sibling = await db.products.find_one({
            "brand_id": product["brand_id"], "floor_id": product["floor_id"],
            "category_id": product["category_id"], "family_key": target_key,
            "active": True,
        }, {"_id": 0, "id": 1})
        if sibling:
            changes.append({
                "product_id": product["id"], "sku": product["sku"],
                "from_family_key": source_key, "to_family_key": target_key,
                "from_finish": product.get("finish"), "to_finish": "Brushed Brass",
            })

    report = {"dry_run": not execute, "candidates": len(products), "rekeyed": len(changes), "changes": changes}
    if not execute:
        return report

    backup_dir = Path(__file__).resolve().parent.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"hansgrohe_brushed_brass_variant_rekey_{stamp}.json"
    backup_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    now = datetime.now(timezone.utc).isoformat()
    for change in changes:
        await db.products.update_one(
            {"id": change["product_id"]},
            {"$set": {
                "family_key": change["to_family_key"], "finish": "Brushed Brass",
                "colour": "Brushed Brass", "variant_label": "Brushed Brass", "finish_code": "BR",
                "updated_at": now,
            }},
        )
        await db.product_media.update_many(
            {"product_id": change["product_id"]}, {"$set": {"family_key": change["to_family_key"]}}
        )
    report["backup_path"] = str(backup_path)
    return report


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run(execute="--execute" in sys.argv)), indent=2))
