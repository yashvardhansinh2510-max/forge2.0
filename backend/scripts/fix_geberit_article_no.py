"""One-time targeted data repair: 2 Geberit products whose `name` field is
the literal PDF-extraction placeholder "*Article No." (SKUs 154.050.00.1 and
154.053.00.1). Confirmed via web lookup of the real Geberit CleanPoint
catalog codes — these are shower floor drains, not junk rows.

Touches ONLY the `name` field. SKU, price, images, category, brand, specs,
series, id, timestamps and relationships are untouched.

Usage: python scripts/fix_geberit_article_no.py
"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import db  # noqa: E402
from catalog_pipeline.integrity_guard import scan_catalog  # noqa: E402

FIXES = {
    "154.050.00.1": "Geberit CleanPoint Shower Floor Drain — Screed Height 90–220mm",
    "154.053.00.1": "Geberit CleanPoint Cross-Floor Shower Drain",
}


async def main() -> None:
    report = {"updated": [], "not_found": [], "unchanged_untouched_fields_verified": True}

    # ----- 1. Pre-repair integrity scan -----
    before = await scan_catalog()
    print(f"[integrity guard] BEFORE: ok={before.ok} products={before.total_products}")

    # ----- 2. Snapshot the exact pre-repair docs for these 2 SKUs (for the report + rollback) -----
    pre_docs = {}
    async for p in db.products.find({"sku": {"$in": list(FIXES.keys())}}, {"_id": 0}):
        pre_docs[p["sku"]] = p

    # ----- 3. Apply the name-only repair -----
    now = datetime.now(timezone.utc).isoformat()
    for sku, new_name in FIXES.items():
        pre = pre_docs.get(sku)
        if not pre:
            report["not_found"].append(sku)
            continue
        res = await db.products.update_one(
            {"sku": sku, "id": pre["id"]},
            {"$set": {"name": new_name, "updated_at": now}},
        )
        report["updated"].append({
            "sku": sku, "product_id": pre["id"],
            "old_name": pre.get("name"), "new_name": new_name,
            "matched": res.matched_count, "modified": res.modified_count,
        })

    # ----- 4. Verify ONLY name+updated_at changed for these 2 docs -----
    for sku, pre in pre_docs.items():
        post = await db.products.find_one({"sku": sku, "id": pre["id"]}, {"_id": 0})
        for field in pre.keys():
            if field in ("name", "updated_at"):
                continue
            if post.get(field) != pre.get(field):
                report["unchanged_untouched_fields_verified"] = False
                report.setdefault("field_drift", []).append(
                    {"sku": sku, "field": field, "before": pre.get(field), "after": post.get(field)}
                )

    # ----- 5. Post-repair integrity scan -----
    after = await scan_catalog()
    print(f"[integrity guard] AFTER:  ok={after.ok} products={after.total_products}")
    report["integrity_before_ok"] = before.ok
    report["integrity_after_ok"] = after.ok
    report["products_count_unchanged"] = before.total_products == after.total_products

    out_path = Path("/app/memory/geberit_article_no_repair_report.json")
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    print(f"\nReport written to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
