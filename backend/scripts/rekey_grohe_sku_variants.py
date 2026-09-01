"""Group existing Grohe catalogue rows by their SKU prefix.

Grohe's last three article-number characters encode the finish/colour.  This
one-time, brand-scoped migration updates the current sanitary catalogue so
that existing product cards use the same family rule as future imports.

It is dry-run by default.  ``--execute`` creates a JSON backup before any
write, updates only Grohe products that have sibling prefixes, and keeps each
product-linked media document aligned with its product's new family key.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from db import db


def sku_prefix(sku: str | None) -> str | None:
    value = re.sub(r"\s+", "", str(sku or ""))
    return value[:-3].lower() if len(value) > 3 and re.fullmatch(r"[A-Za-z0-9]+", value) else None


async def run(*, execute: bool) -> dict:
    brand = await db.brands.find_one({"$or": [{"slug": "grohe"}, {"name": {"$regex": "^grohe$", "$options": "i"}}]})
    if not brand:
        raise RuntimeError("Grohe brand was not found; no catalog data was changed.")

    products = await db.products.find(
        {"brand_id": brand["id"], "active": True},
        {"_id": 0},
    ).to_list(10_000)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for product in products:
        prefix = sku_prefix(product.get("sku"))
        if prefix:
            grouped[prefix].append(product)

    families = {prefix: rows for prefix, rows in grouped.items() if len(rows) > 1}
    changes = [
        {
            "product_id": product["id"], "sku": product["sku"],
            "from_family_key": product.get("family_key"),
            "to_family_key": f"grohe:sku:{prefix}",
        }
        for prefix, rows in sorted(families.items())
        for product in rows
        if product.get("family_key") != f"grohe:sku:{prefix}"
    ]
    report = {
        "dry_run": not execute,
        "grohe_products": len(products),
        "variant_families": len(families),
        "products_rekeyed": len(changes),
        "changes": changes,
    }
    if not execute:
        return report

    backup_dir = Path(__file__).resolve().parent.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"grohe_sku_variant_rekey_{stamp}.json"
    backup_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for change in changes:
        await db.products.update_one(
            {"id": change["product_id"], "brand_id": brand["id"]},
            {"$set": {"family_key": change["to_family_key"], "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        await db.product_media.update_many(
            {"product_id": change["product_id"], "brand_id": brand["id"]},
            {"$set": {"family_key": change["to_family_key"]}},
        )
    report["backup_path"] = str(backup_path)
    return report


if __name__ == "__main__":
    result = asyncio.run(run(execute="--execute" in sys.argv))
    print(json.dumps(result, indent=2))
