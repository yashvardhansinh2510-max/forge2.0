"""GEBERIT Catalog Re-import (2026-08, ingestion-fix pass).

Same architecture-first approach as the Vitra re-import: re-runs the
rewritten (PyMuPDF-based, position-aware) GeberitAdapter through the SAME
production pipeline (`run_pipeline` -> `validate` -> `import_accepted`)
every catalog import uses.

Root causes fixed: (1) images were mapped by page only ("first image on
the page wins for every SKU on it") — now matched geometrically to each
SKU's own text block; (2) colour/finish was guessed from a noisy backward
text search that often grabbed spec-sheet bullets instead of the real
line — now read directly from the supplier's own structured
"Article No./Colour/MRP" block, verbatim, zero guessing.

Usage:
    python scripts/run_geberit_reimport.py --dry-run
    python scripts/run_geberit_reimport.py --execute
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

from db import db  # noqa: E402
from catalog_pipeline.integrity_guard import scan_catalog  # noqa: E402
from catalog_pipeline.orchestrator import run_pipeline, import_accepted  # noqa: E402

SOURCE_FILE = "/tmp/catalog_fix/geberit/GEBERIT_MRP_Catalogue_2026.pdf"
BACKUP_ROOT = Path(__file__).resolve().parent.parent / "backups"


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


async def backup_brand(brand_name: str, brand_id: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = BACKUP_ROOT / f"{brand_name.lower()}_reimport_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    products = await db.products.find({"brand_id": brand_id}, {"_id": 0}).to_list(2000)
    media = await db.product_media.find({"brand_id": brand_id}, {"_id": 0}).to_list(2000)
    (out_dir / "products.json").write_text(json.dumps(products, default=_json_default, indent=2), encoding="utf-8")
    (out_dir / "product_media.json").write_text(json.dumps(media, default=_json_default, indent=2), encoding="utf-8")
    return out_dir


async def run(dry_run: bool) -> dict:
    report: dict = {"dry_run": dry_run}
    with open(SOURCE_FILE, "rb") as f:
        data = f.read()

    print("=" * 78)
    print("PHASE 1 — EXTRACT + VALIDATE (rewritten position-aware GeberitAdapter)")
    print("=" * 78)
    pipeline_result = await run_pipeline("Geberit", "GEBERIT_MRP_Catalogue_2026.pdf", data)
    rows = pipeline_result["rows"]
    cert = pipeline_result["certification"]
    print(f"Extraction: {pipeline_result['extraction']}")
    print(f"Certification: production_ready={cert['production_ready']} overall_score={cert['overall_score']} "
          f"products_ready={cert['products_ready']} products_needing_review={cert['products_needing_review']}")

    accepted = [r for r in rows if r["status"] == "accepted"]
    pending = [r for r in rows if r["status"] != "accepted"]
    print(f"Auto-accepted (confidence>=0.85, has sku/mrp/category): {len(accepted)}")
    print(f"Needs manual review (excluded from this pass): {len(pending)}")
    conflict_rows = [r for r in pending if any("Conflict" in i for i in r["issues"])]
    print(f"  of which genuine price conflicts: {len(conflict_rows)}")
    for r in conflict_rows:
        print(f"   SKU {r['sku']}: {r['issues']}")

    images_ok = sum(1 for r in accepted if r["images"])
    colour_ok = sum(1 for r in accepted if r["colour"])
    report["extraction"] = pipeline_result["extraction"]
    report["certification"] = cert
    report["accepted_count"] = len(accepted)
    report["conflicts_excluded"] = [{"sku": r["sku"], "issues": r["issues"]} for r in conflict_rows]
    report["image_coverage"] = f"{images_ok}/{len(accepted)}"
    report["colour_coverage"] = f"{colour_ok}/{len(accepted)}"
    print(f"Image coverage among accepted rows: {images_ok}/{len(accepted)}")
    print(f"Colour/finish coverage among accepted rows: {colour_ok}/{len(accepted)}")

    print("\n" + "=" * 78)
    print("PHASE 2 — PRE-FLIGHT")
    print("=" * 78)
    brand_doc = await db.brands.find_one({"name": {"$regex": "^geberit$", "$options": "i"}}, {"_id": 0})
    if not brand_doc:
        raise RuntimeError("Geberit brand not found — aborting, nothing touched.")
    brand_id = brand_doc["id"]
    old_count = await db.products.count_documents({"brand_id": brand_id})
    old_media_count = await db.product_media.count_documents({"brand_id": brand_id})
    print(f"Existing Geberit products: {old_count}  |  existing Geberit media docs: {old_media_count}")
    report["old_products"] = old_count
    report["old_media"] = old_media_count

    geberit_ids = {p["id"] async for p in db.products.find({"brand_id": brand_id}, {"_id": 0, "id": 1})}
    affected_quotations = 0
    async for q in db.quotations.find({}, {"_id": 0, "items": 1}):
        if any(it.get("product_id") in geberit_ids for it in q.get("items", [])):
            affected_quotations += 1
    report["quotations_with_frozen_snapshots"] = affected_quotations
    print(f"Historical quotations referencing current Geberit SKUs (snapshot-preserved, unaffected): {affected_quotations}")

    # Which currently-existing SKUs would NOT be refreshed this pass
    # (either dropped due to a conflict, or simply absent from the new
    # extraction — e.g. a spec/accessory row this stricter parser no longer
    # accepts). These keep their OLD (possibly wrong) media untouched unless
    # we explicitly purge — surfaced here so nothing disappears silently.
    accepted_skus = {r["sku"] for r in accepted}
    existing_skus = set()
    async for p in db.products.find({"brand_id": brand_id}, {"_id": 0, "sku": 1}):
        existing_skus.add(p["sku"])
    stale_skus = existing_skus - accepted_skus
    report["existing_skus_not_refreshed_this_pass"] = len(stale_skus)
    print(f"Existing SKUs NOT covered by this corrected pass (will keep old data untouched): {len(stale_skus)}")

    if dry_run:
        print("\nDRY RUN — no writes performed. Re-run with --execute to apply.")
        report["dry_run_only"] = True
        return report

    print("\n" + "=" * 78)
    print("PHASE 3 — BACKUP + DELETE MEDIA FOR REFRESHED SKUS ONLY")
    print("=" * 78)
    backup_dir = await backup_brand("geberit", brand_id)
    report["backup_dir"] = str(backup_dir)
    # Only purge media for products this pass is actually about to
    # re-populate. The ~295 SKUs this corrected pass doesn't touch (plain
    # single-line accessory rows below the auto-accept confidence bar) keep
    # whatever media they already had — never leave a product imageless
    # just because it wasn't part of this pass.
    refreshed_ids = [
        p["id"] async for p in db.products.find(
            {"brand_id": brand_id, "sku": {"$in": list(accepted_skus)}}, {"_id": 0, "id": 1}
        )
    ]
    del_media = await db.product_media.delete_many({"brand_id": brand_id, "product_id": {"$in": refreshed_ids}})
    print(f"Backed up to {backup_dir}. Purged {del_media.deleted_count} old (mis-attributed) media docs "
          f"for the {len(refreshed_ids)} products being refreshed this pass.")
    report["purged_media"] = del_media.deleted_count

    print("\n" + "=" * 78)
    print("PHASE 4 — IMPORT via production pipeline (import_accepted)")
    print("=" * 78)
    job = {"supplier_name": "Geberit", "rows": accepted}
    result = await import_accepted(job, user_id="system_migration_2026_08")
    print(f"Result: {result}")
    report["import_result"] = result

    print("\n" + "=" * 78)
    print("PHASE 5 — POST-MIGRATION VALIDATION")
    print("=" * 78)
    post_scan = await scan_catalog()
    print(f"Post-migration integrity scan: ok={post_scan.ok}")
    report["post_scan_ok"] = post_scan.ok

    new_count = await db.products.count_documents({"brand_id": brand_id})
    products_without_media = 0
    async for p in db.products.find({"brand_id": brand_id}, {"_id": 0, "id": 1}):
        cnt = await db.product_media.count_documents({"product_id": p["id"]})
        if cnt == 0:
            products_without_media += 1
    report["new_products"] = new_count
    report["products_without_image"] = products_without_media
    print(f"Geberit products now: {new_count}  |  WITHOUT any image: {products_without_media}")
    return report


if __name__ == "__main__":
    dry = "--execute" not in sys.argv
    result = asyncio.run(run(dry_run=dry))
    out_path = Path(__file__).resolve().parent.parent / "backups" / "geberit_reimport_report.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=_json_default), encoding="utf-8")
    print(f"\nFull report written to {out_path}")
