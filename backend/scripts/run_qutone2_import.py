# backend/scripts/run_qutone2_import.py
"""Qutone catalog EXTENSION importer (Ground Floor > Tiles) — merges
QUTONE2.xlsx into the EXISTING "Qutone" brand. This is deliberately NOT a
new adapter: QUTONE2.xlsx ships the identical column layout the original
QutoneAdapter already parses (SR./PRODUCT NAME/IMAGE/PRODUCT SIZE/SERIES
NAME/FINISHES/BOX IN PIS/BOX SQFT/RATE), so reusing that adapter unchanged
is the correct "extend, don't duplicate" behavior — a second adapter class
would be a parallel implementation the task explicitly forbids.

Merge safety (verified before writing this script, not assumed):
* orchestrator.import_accepted() resolves the brand by exact name ("Qutone")
  within floor_id="ground-floor" and reuses the existing brand doc — it
  never creates "Qutone 2"/"Qutone New"/etc. Confirmed by reading
  orchestrator.py's `_resolve_brand`/brand lookup before running anything.
* QutoneAdapter's SKU is deterministic from (series, name, size,
  finish_code) — the same formula the original 452-product import already
  used. Every one of QUTONE2.xlsx's 14 rows was checked directly against
  the live DB before this script was written: 0 name-substring matches, 0
  SKU collisions with any of the 452 existing Qutone products. So this run
  is expected to be 100% new inserts, never touching an existing document —
  but the script still goes through the normal update-or-insert path (not
  insert-only) so it stays correct if a future refreshed file DOES overlap.

Safe to re-run: re-running always upserts the same rows instead of
duplicating them (same idempotency contract as every other brand importer
in this pipeline).

Usage:
    python scripts/run_qutone2_import.py --dry-run   # extract+validate+certify only, NO db writes
    python scripts/run_qutone2_import.py              # full import (writes to Mongo + Supabase)
"""
from __future__ import annotations
import argparse
import asyncio
import json
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from catalog_pipeline.adapters.qutone import QutoneAdapter  # noqa: E402
from catalog_pipeline.certifier import validate  # noqa: E402
from catalog_pipeline.base import MISSING  # noqa: E402
from catalog_pipeline.orchestrator import import_accepted, _offload_row_images  # noqa: E402
from catalog_pipeline.integrity_guard import scan_catalog  # noqa: E402
from db import db  # noqa: E402
from models import CatalogImportJob  # noqa: E402
from backup_db import backup as backup_db  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_FILE = REPO_ROOT / "backend" / "temp" / "qutone_source_files" / "QUTONE2.xlsx"
REPORT_PATH = REPO_ROOT / "memory" / "qutone2_merge_report.json"

FLOOR_ID = "ground-floor"


def _auto_accept(row_objs):
    for r in row_objs:
        if (
            r.status == "pending"
            and r.confidence >= 0.85
            and r.sku not in (MISSING, None)
            and r.mrp not in (MISSING, None)
            and r.category not in (MISSING, None)
        ):
            r.status = "accepted"
    return row_objs


async def main(dry_run: bool) -> None:
    t0 = time.time()

    if not SOURCE_FILE.exists():
        print(f"ABORTING - source file not found: {SOURCE_FILE}")
        raise SystemExit(1)

    # Pre-flight: confirm the target brand is the EXISTING Qutone, never a
    # new one, before touching anything.
    existing_brand = await db.brands.find_one({"name": "Qutone", "floor_id": FLOOR_ID}, {"_id": 0})
    if not existing_brand:
        print("ABORTING — no existing 'Qutone' brand found on ground-floor. "
              "This script is for EXTENDING the existing brand only.")
        raise SystemExit(1)
    existing_count_before = await db.products.count_documents(
        {"brand_id": existing_brand["id"], "floor_id": FLOOR_ID}
    )
    print(f"Existing Qutone brand id={existing_brand['id']} — {existing_count_before} products before this run.")

    if not dry_run:
        pre_report = await scan_catalog()
        if not pre_report.ok:
            print("ABORTING — catalog integrity check FAILED before this import even started.")
            print(json.dumps(pre_report.to_public(), indent=2))
            raise SystemExit(1)
        print(f"Pre-import integrity check: PASS ({pre_report.total_products} products)")

        pre_snapshot_dir = await backup_db(["products", "product_media", "brands", "categories"])
        print(f"Pre-import snapshot: {pre_snapshot_dir}")

    adapter = QutoneAdapter()
    filename = SOURCE_FILE.name
    data = SOURCE_FILE.read_bytes()
    rows, rep = adapter.extract(data, filename)
    print(f"[{filename}] rows={rep.parsed_rows} images_mapped={rep.images_mapped}/{rep.images_found}")

    if not rows:
        print("ABORTING — extraction produced 0 rows.")
        raise SystemExit(1)

    # Merge-safety check: how many of this batch's SKUs already exist under
    # the EXISTING Qutone brand? Logged explicitly so the final report is
    # honest about "new vs already-there", not just "accepted".
    pre_existing_skus: set[str] = set()
    for r in rows:
        if r.sku and r.sku != MISSING:
            doc = await db.products.find_one(
                {"sku": r.sku, "brand_id": existing_brand["id"], "floor_id": FLOOR_ID}, {"_id": 0, "id": 1}
            )
            if doc:
                pre_existing_skus.add(r.sku)
    print(f"Rows whose SKU already exists in the current Qutone catalog: {len(pre_existing_skus)}/{len(rows)}")

    row_objs, cert = validate(rows)
    row_objs = _auto_accept(row_objs)
    all_rows_dicts = [r.to_public() for r in row_objs]
    accepted = sum(1 for r in all_rows_dicts if r.get("status") == "accepted")
    rejected = sum(1 for r in all_rows_dicts if r.get("status") == "rejected")
    needs_review = [r for r in all_rows_dicts if r.get("status") == "pending"]
    missing_images = sum(1 for r in all_rows_dicts if not r.get("images"))

    summary = {
        "mode": "dry-run" if dry_run else "import",
        "operation": "MERGE into existing Qutone brand (not a new brand)",
        "source_file": filename,
        "existing_qutone_brand_id": existing_brand["id"],
        "existing_qutone_products_before": existing_count_before,
        "rows_matching_pre_existing_sku": sorted(pre_existing_skus),
        "extraction": {
            "rows": rep.parsed_rows, "images_found": rep.images_found,
            "images_mapped": rep.images_mapped, "warnings": rep.warnings,
        },
        "total_rows": len(all_rows_dicts),
        "accepted": accepted,
        "rejected_true_duplicates": rejected,
        "needs_manual_review": len(needs_review),
        "needs_manual_review_detail": [
            {"sku": r.get("sku"), "name": r.get("name"), "issues": r.get("issues")}
            for r in needs_review
        ],
        "missing_images_in_source": missing_images,
        "certification": cert.to_public(),
        "runtime_s": round(time.time() - t0, 1),
    }

    if dry_run:
        print("\n" + "=" * 70)
        print("DRY RUN — no database or storage writes performed")
        print("=" * 70)
        print(json.dumps(summary, indent=2, default=str)[:20000])
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"\nFull dry-run report written to {REPORT_PATH}")
        return

    owner = await db.users.find_one({"email": "owner@forge.app"}, {"id": 1, "_id": 0})
    media_before = await db.product_media.count_documents({"floor_id": FLOOR_ID, "source_type": "supplier"})
    cats_before = {c["name"] for c in await db.categories.find({"floor_id": FLOOR_ID}, {"_id": 0, "name": 1}).to_list(200)}
    brands_before = {b["name"] for b in await db.brands.find({"floor_id": FLOOR_ID}, {"_id": 0, "name": 1}).to_list(200)}

    # Offload embedded base64 images out of the row dicts into a dedicated
    # collection so the CatalogImportJob document stays well under MongoDB's
    # 16MB BSON cap (mutates all_rows_dicts in place).
    blob_map = await _offload_row_images(all_rows_dicts)

    job = CatalogImportJob(
        filename=filename,
        source_type="excel",  # type: ignore[arg-type]
        supplier_name="Qutone",  # EXACT match to the existing brand — never a new one
        total_rows=len(all_rows_dicts),
        accepted_rows=accepted,
        rejected_rows=rejected,
        status="classified",  # type: ignore[arg-type]
        rows=all_rows_dicts,
        created_by=(owner or {}).get("id", "system"),
        floor_id=FLOOR_ID,
    )
    doc = job.dict()
    doc["extraction"] = summary["extraction"]
    doc["certification"] = cert.to_public()
    await db.catalog_imports.insert_one(doc)
    doc.pop("_id", None)

    stats = {"imported": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
    if accepted:
        stats = await import_accepted(doc, (owner or {}).get("id", "system"), blob_map=blob_map, floor_id=FLOOR_ID)
        await db.catalog_imports.update_one(
            {"id": doc["id"]},
            {"$set": {"status": "imported", "accepted_rows": stats["imported"] + stats["updated"],
                      "rejected_rows": stats["skipped"]}},
        )

    cats_after = {c["name"] for c in await db.categories.find({"floor_id": FLOOR_ID}, {"_id": 0, "name": 1}).to_list(200)}
    brands_after = {b["name"] for b in await db.brands.find({"floor_id": FLOOR_ID}, {"_id": 0, "name": 1}).to_list(200)}
    media_after = await db.product_media.count_documents({"floor_id": FLOOR_ID, "source_type": "supplier"})
    existing_count_after = await db.products.count_documents({"brand_id": existing_brand["id"], "floor_id": FLOOR_ID})

    post_report = await scan_catalog(baseline_snapshot_dir=str(pre_snapshot_dir))
    integrity_ok = post_report.ok

    post_snapshot_dir = await backup_db(
        ["products", "product_media", "brands", "categories", "customers",
         "quotations", "purchase_orders", "payments", "followups", "users", "suppliers"]
    )

    new_brands_created = sorted(brands_after - brands_before)
    summary.update({
        "batch_result": "SUCCESS" if (integrity_ok and not new_brands_created) else
                         "FAILED — INTEGRITY VIOLATION OR UNEXPECTED NEW BRAND, MANUAL REVIEW REQUIRED",
        "new_brands_created_on_ground_floor": new_brands_created,  # MUST be [] — a non-empty list here is a bug
        "categories_created_on_ground_floor": sorted(cats_after - cats_before),
        "existing_qutone_products_after": existing_count_after,
        "net_new_qutone_products": existing_count_after - existing_count_before,
        "products_imported": stats["imported"],
        "products_updated": stats["updated"],
        "products_skipped": stats["skipped"],
        "products_failed": stats["failed"],
        "duplicates_skipped": rejected + stats["skipped"],
        "import_errors": stats.get("errors", []),
        "images_uploaded": media_after - media_before,
        "missing_images_final": missing_images,
        "pre_import_snapshot": str(pre_snapshot_dir),
        "post_import_snapshot": str(post_snapshot_dir),
        "integrity_guard": post_report.to_public(),
    })
    print("\n" + "=" * 70)
    print(f"MERGE REPORT — {summary['batch_result']}")
    print("=" * 70)
    print(json.dumps(summary, indent=2, default=str)[:20000])

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    if not integrity_ok or new_brands_created:
        print(f"\n!!! MERGE VALIDATION FAILED — restore from {pre_snapshot_dir} if needed. !!!")
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Extract+validate+certify only, no DB/storage writes")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
