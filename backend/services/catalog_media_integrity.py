"""Read and repair product-media identity without guessing at replacements."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def find_media_integrity_issues(products: list[dict], media_rows: list[dict]) -> list[dict]:
    """Return deterministic identity problems without mutating catalog data."""
    product_by_id = {row["id"]: row for row in products if row.get("id")}
    valid_families = {
        (row.get("brand_id"), row.get("floor_id"), row.get("family_key"))
        for row in products if row.get("family_key")
    }
    issues: list[dict] = []
    for media in media_rows:
        media_id = media.get("id")
        if not media.get("product_id") and not media.get("family_key"):
            issues.append({"media_id": media_id, "kind": "identityless"})
            continue
        product = product_by_id.get(media.get("product_id")) if media.get("product_id") else None
        if media.get("product_id") and not product:
            issues.append({"media_id": media_id, "kind": "orphan_product", "product_id": media.get("product_id")})
            continue
        if product and media.get("family_key") and media.get("family_key") != product.get("family_key"):
            issues.append({
                "media_id": media_id, "kind": "foreign_product_family",
                "product_id": product["id"], "expected_family_key": product.get("family_key"),
                "actual_family_key": media.get("family_key"),
            })
            continue
        if not product and media.get("family_key") and (
            media.get("brand_id"), media.get("floor_id"), media.get("family_key")
        ) not in valid_families:
            issues.append({"media_id": media_id, "kind": "orphan_family", "family_key": media.get("family_key")})
    return issues


async def audit_catalog_media(db: Any) -> dict:
    products, media_rows = await __import__("asyncio").gather(
        db.products.find({}, {"_id": 0, "id": 1, "brand_id": 1, "floor_id": 1, "family_key": 1}).to_list(50_000),
        db.product_media.find({}, {"_id": 0, "id": 1, "product_id": 1, "brand_id": 1, "floor_id": 1, "family_key": 1, "public_url": 1, "storage_key": 1, "sha1": 1, "width": 1, "height": 1}).to_list(100_000),
    )
    issues = find_media_integrity_issues(products, media_rows)
    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "products": len(products), "media": len(media_rows), "issues": issues,
        "counts": {kind: sum(issue["kind"] == kind for issue in issues) for kind in sorted({issue["kind"] for issue in issues})},
    }


async def repair_foreign_product_families(db: Any, report: dict, *, actor: str = "catalog-media-repair") -> dict:
    """Repair only product-linked stale family keys and retain a rollback record."""
    repaired: list[str] = []
    for issue in report["issues"]:
        if issue["kind"] != "foreign_product_family" or not issue.get("expected_family_key"):
            continue
        media = await db.product_media.find_one({"id": issue["media_id"]}, {"_id": 0})
        if not media or media.get("family_key") != issue["actual_family_key"]:
            continue
        change = {
            "media_id": media["id"], "before": {key: media.get(key) for key in ("family_key", "storage_key", "sha1", "width", "height")},
            "after": {"family_key": issue["expected_family_key"]}, "actor": actor,
            "created_at": datetime.now(timezone.utc).isoformat(), "reason": "product-linked media had a stale family_key",
        }
        await db.product_media.update_one({"id": media["id"]}, {"$set": {"family_key": issue["expected_family_key"]}})
        await db.media_repair_audits.insert_one(change)
        repaired.append(media["id"])
    return {"repaired_media_ids": repaired, "repaired": len(repaired)}
