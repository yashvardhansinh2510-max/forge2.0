# backend/scripts/run_qutone_import.py
"""Qutone brand batch importer (Ground Floor > Tiles) — processes the single
QUTONE 2026 pricelist. Safe to re-run: every row's SKU is deterministic
(series+name+size+finish), so re-running always upserts the same ~452
products instead of duplicating them.

Usage:
    python scripts/run_qutone_import.py --dry-run   # extract+validate+certify only, NO db writes
    python scripts/run_qutone_import.py              # full import (writes to Mongo + Supabase)
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
SOURCE_FILE = REPO_ROOT / "backend" / "temp" / "qutone_source_files" / "QUTONE 2026.xlsx"
REPORT_PATH = REPO_ROOT / "memory" / "qutone_qa_report.json"

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

    row_objs, cert = validate(rows)
    row_objs = _auto_accept(row_objs)
    all_rows_dicts = [r.to_public() for r in row_objs]
    accepted = sum(1 for r in all_rows_dicts if r.get("status") == "accepted")
    rejected = sum(1 for r in all_rows_dicts if r.get("status") == "rejected")
    needs_review = [r for r in all_rows_dicts if r.get("status") == "pending"]
    missing_images = sum(1 for r in all_rows_dicts if not r.get("images"))

    summary = {
        "mode": "dry-run" if dry_run else "import",
        "source_file": filename,
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

    # Offload embedded base64 images out of the row dicts into a dedicated
    # collection so the CatalogImportJob document stays well under MongoDB's
    # 16MB BSON cap (mutates all_rows_dicts in place).
    blob_map = await _offload_row_images(all_rows_dicts)

    job = CatalogImportJob(
        filename=filename,
        source_type="excel",  # type: ignore[arg-type]
        supplier_name="Qutone",
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
    media_after = await db.product_media.count_documents({"floor_id": FLOOR_ID, "source_type": "supplier"})

    post_report = await scan_catalog(baseline_snapshot_dir=str(pre_snapshot_dir))
    integrity_ok = post_report.ok

    post_snapshot_dir = await backup_db(
        ["products", "product_media", "brands", "categories", "customers",
         "quotations", "purchase_orders", "payments", "followups", "users", "suppliers"]
    )

    summary.update({
        "batch_result": "SUCCESS" if integrity_ok else "FAILED — INTEGRITY VIOLATION, MANUAL REVIEW REQUIRED",
        "categories_created_on_ground_floor": sorted(cats_after - cats_before),
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
    print(f"IMPORT REPORT — {summary['batch_result']}")
    print("=" * 70)
    print(json.dumps(summary, indent=2, default=str)[:20000])

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    if not integrity_ok:
        print(f"\n!!! INTEGRITY GUARD FAILED — restore from {pre_snapshot_dir} if needed. !!!")
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Extract+validate+certify only, no DB/storage writes")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
