# backend/scripts/run_oyster_import.py
"""Oyster brand batch importer — processes the 4 Oyster category files
(Body Jet, Shower, Outlet/Hand Shower/Angle Valve, Basin Mixer) idempotently,
tracking progress in memory/oyster_import_manifest.json so re-running never
reprocesses an already-completed file.

Usage:
    python scripts/run_oyster_import.py --dry-run   # extract+validate+certify only, NO db writes
    python scripts/run_oyster_import.py              # full import (writes to Mongo + Supabase)
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

from catalog_pipeline.adapters.oyster import OysterAdapter  # noqa: E402
from catalog_pipeline.certifier import validate  # noqa: E402
from catalog_pipeline.base import MISSING  # noqa: E402
from catalog_pipeline.orchestrator import import_accepted, _offload_row_images  # noqa: E402
from catalog_pipeline.integrity_guard import scan_catalog  # noqa: E402
from db import db  # noqa: E402
from models import CatalogImportJob  # noqa: E402
from backup_db import backup as backup_db  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "memory" / "oyster_import_manifest.json"
REPORT_PATH = REPO_ROOT / "memory" / "oyster_qa_report.json"

# Local absolute paths to the 4 source files, copied into a stable in-repo
# location (backend/temp/oyster_source_files/, matching the existing
# backend/temp/grohe_source_files_2026_migration/ precedent) — the original
# WhatsApp-forwarded copies live in an ephemeral app temp-cache directory
# that gets cleared periodically, which happened once already during this
# import's development. Each file maps 1:1 to a category — see oyster.py
# FILE_TO_CATEGORY.
_SOURCE_DIR = REPO_ROOT / "backend" / "temp" / "oyster_source_files"
SOURCE_FILES = [
    str(_SOURCE_DIR / "OYSTER BODY JET.xlsx"),
    str(_SOURCE_DIR / "OYSTER SHOWER.xlsx"),
    str(_SOURCE_DIR / "OYSTER SPOUT&HS&ANGLE W& TIGGER.xlsx"),
    str(_SOURCE_DIR / "OYSTER BESIN MIXER.xlsx"),
]


def _norm(path: str) -> str:
    return Path(path).stem.strip().lower().replace(" ", "_")


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"processed_files": [], "batches": []}


def _save_manifest(m: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(m, indent=2), encoding="utf-8")


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
    manifest = _load_manifest()
    already_done = set(manifest["processed_files"])

    to_process = [f for f in SOURCE_FILES if _norm(f) not in already_done]
    already_skipped = [f for f in SOURCE_FILES if _norm(f) in already_done]

    if not dry_run:
        pre_report = await scan_catalog()
        if not pre_report.ok:
            print("ABORTING — catalog integrity check FAILED before this import even started.")
            print(json.dumps(pre_report.to_public(), indent=2))
            raise SystemExit(1)
        print(f"Pre-import integrity check: PASS ({pre_report.total_products} products)")

        pre_snapshot_dir = await backup_db(["products", "product_media", "brands", "categories"])
        print(f"Pre-import snapshot: {pre_snapshot_dir}")

    adapter = OysterAdapter()
    all_rows = []
    per_file: list[dict] = []
    errors: list[str] = []

    for path in to_process:
        filename = Path(path).name
        try:
            data = Path(path).read_bytes()
        except Exception as e:
            errors.append(f"{filename}: read failed - {e}")
            continue
        try:
            rows, rep = adapter.extract(data, filename)
        except Exception as e:
            errors.append(f"{filename}: extraction failed - {e}")
            continue
        all_rows.extend(rows)
        per_file.append({
            "file": filename, "rows": rep.parsed_rows,
            "images_found": rep.images_found, "images_mapped": rep.images_mapped,
            "warnings": rep.warnings,
        })
        print(f"[{filename}] rows={rep.parsed_rows} images_mapped={rep.images_mapped}/{rep.images_found}")

    if not all_rows:
        if errors:
            print("ABORTING — every file in this batch failed to read or extract:")
            for e in errors:
                print(f"  - {e}")
            raise SystemExit(1)
        print("Nothing new to process.")
        return

    row_objs, cert = validate(all_rows)
    row_objs = _auto_accept(row_objs)
    all_rows_dicts = [r.to_public() for r in row_objs]
    accepted = sum(1 for r in all_rows_dicts if r.get("status") == "accepted")
    rejected = sum(1 for r in all_rows_dicts if r.get("status") == "rejected")
    needs_review = [r for r in all_rows_dicts if r.get("status") == "pending"]

    summary = {
        "mode": "dry-run" if dry_run else "import",
        "files_processed": [Path(f).name for f in to_process],
        "already_done_skipped": [Path(f).name for f in already_skipped],
        "per_file": per_file,
        "total_rows": len(all_rows_dicts),
        "accepted": accepted,
        "rejected_true_duplicates": rejected,
        "needs_manual_review": len(needs_review),
        "needs_manual_review_detail": [
            {"sku": r.get("sku"), "description": r.get("description"), "issues": r.get("issues")}
            for r in needs_review
        ],
        "certification": cert.to_public(),
        "errors": errors,
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
    cats_before = {c["name"] for c in await db.categories.find({}, {"_id": 0, "name": 1}).to_list(200)}

    # Offload embedded base64 images out of the row dicts into a dedicated
    # collection so the CatalogImportJob document stays well under MongoDB's
    # 16MB BSON cap (mutates all_rows_dicts in place).
    blob_map = await _offload_row_images(all_rows_dicts)

    job = CatalogImportJob(
        filename=f"Oyster batch ({len(to_process)} files)",
        source_type="excel",  # type: ignore[arg-type]
        supplier_name="Oyster",
        total_rows=len(all_rows_dicts),
        accepted_rows=accepted,
        rejected_rows=rejected,
        status="classified",  # type: ignore[arg-type]
        rows=all_rows_dicts,
        created_by=(owner or {}).get("id", "system"),
    )
    doc = job.dict()
    doc["extraction"] = {"per_file": per_file}
    doc["certification"] = cert.to_public()
    await db.catalog_imports.insert_one(doc)
    doc.pop("_id", None)

    stats = {"imported": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
    if accepted:
        stats = await import_accepted(doc, (owner or {}).get("id", "system"), blob_map=blob_map)
        await db.catalog_imports.update_one(
            {"id": doc["id"]},
            {"$set": {"status": "imported", "accepted_rows": stats["imported"] + stats["updated"],
                      "rejected_rows": stats["skipped"]}},
        )

    cats_after = {c["name"] for c in await db.categories.find({}, {"_id": 0, "name": 1}).to_list(200)}
    missing_images = sum(1 for r in all_rows_dicts if r.get("status") == "accepted" and not r.get("images"))

    post_report = await scan_catalog(baseline_snapshot_dir=str(pre_snapshot_dir))
    integrity_ok = post_report.ok

    if integrity_ok:
        manifest["processed_files"].extend(_norm(f) for f in to_process)
        manifest["batches"].append({
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "files": [Path(f).name for f in to_process],
            "stats": stats,
        })
        _save_manifest(manifest)

    post_snapshot_dir = await backup_db(
        ["products", "product_media", "brands", "categories", "customers",
         "quotations", "purchase_orders", "payments", "followups", "users", "suppliers"]
    )

    summary.update({
        "batch_result": "SUCCESS" if integrity_ok else "FAILED — INTEGRITY VIOLATION, MANUAL REVIEW REQUIRED",
        "categories_created": sorted(cats_after - cats_before),
        "products_imported": stats["imported"],
        "products_updated": stats["updated"],
        "products_skipped": stats["skipped"],
        "import_errors": stats.get("errors", []),
        "missing_images": missing_images,
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
