"""Panda 2026 catalog importer (Ground Floor > Tiles).

The import is idempotent: the adapter generates deterministic SKUs and the
orchestrator updates an existing Panda SKU instead of duplicating it. Product
metadata is persisted in MongoDB and embedded images are uploaded through the
configured Supabase media driver.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from catalog_pipeline.adapters import get_adapter  # noqa: E402
from catalog_pipeline.base import MISSING  # noqa: E402
from catalog_pipeline.certifier import validate  # noqa: E402
from catalog_pipeline.integrity_guard import scan_catalog  # noqa: E402
from catalog_pipeline.orchestrator import _offload_row_images, import_accepted  # noqa: E402
from backup_db import backup as backup_db  # noqa: E402
from db import db  # noqa: E402
from models import CatalogImportJob  # noqa: E402

FLOOR_ID = "ground-floor"
BRAND = "Panda"
SOURCE_FILE = Path(
    "/Users/yashvardhansinhjhala/Library/Containers/net.whatsapp.WhatsApp/Data/tmp/documents/"
    "DFAF364A-5C3B-4713-ADA1-EE3178BB668F/PANDA 2026.xlsx"
)
REPORT_PATH = Path(__file__).resolve().parent.parent.parent / "memory" / "panda_import_report.json"


def _auto_accept(rows):
    for row in rows:
        if (
            row.status == "pending"
            and row.confidence >= 0.85
            and row.sku not in (MISSING, None)
            and row.mrp not in (MISSING, None)
            and row.category not in (MISSING, None)
        ):
            row.status = "accepted"
    return rows


async def main(dry_run: bool) -> None:
    started = time.time()
    if not SOURCE_FILE.exists():
        raise SystemExit(f"Source file not found: {SOURCE_FILE}")

    adapter = get_adapter(BRAND)
    rows, extraction = adapter.extract(SOURCE_FILE.read_bytes(), SOURCE_FILE.name)
    validated_rows, certification = validate(rows)
    row_objs = _auto_accept(validated_rows)
    public_rows = [row.to_public() for row in row_objs]
    accepted = sum(row.get("status") == "accepted" for row in public_rows)
    rejected = sum(row.get("status") == "rejected" for row in public_rows)
    pending = sum(row.get("status") == "pending" for row in public_rows)
    summary = {
        "mode": "dry-run" if dry_run else "import",
        "brand": BRAND,
        "floor_id": FLOOR_ID,
        "source_file": str(SOURCE_FILE),
        "extraction": extraction.__dict__,
        "rows": len(public_rows),
        "accepted": accepted,
        "rejected": rejected,
        "pending": pending,
        "missing_images_in_source": sum(not row.get("images") for row in public_rows),
        "certification": certification.to_public(),
        "runtime_s": round(time.time() - started, 1),
    }
    if dry_run:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(json.dumps(summary, indent=2, default=str))
        return

    pre = await scan_catalog()
    if not pre.ok:
        raise SystemExit("Aborting: pre-import catalog integrity check failed")
    pre_snapshot = await backup_db(["products", "product_media", "brands", "categories"])

    owner = await db.users.find_one({"email": "owner@forge.app"}, {"id": 1, "_id": 0})
    before_products = await db.products.count_documents({"brand_id": {"$exists": True}, "floor_id": FLOOR_ID})
    existing_panda = await db.brands.find_one({"name": BRAND, "floor_id": FLOOR_ID}, {"_id": 0, "id": 1})
    before_panda_media = await db.product_media.count_documents(
        {"brand_id": existing_panda["id"], "floor_id": FLOOR_ID, "source_type": "supplier"}
    ) if existing_panda else 0

    blob_map = await _offload_row_images(public_rows)
    job = CatalogImportJob(
        filename=SOURCE_FILE.name,
        source_type="excel",  # type: ignore[arg-type]
        supplier_name=BRAND,
        total_rows=len(public_rows),
        accepted_rows=accepted,
        rejected_rows=rejected,
        status="classified",  # type: ignore[arg-type]
        rows=public_rows,
        created_by=(owner or {}).get("id", "system"),
        floor_id=FLOOR_ID,
    )
    doc = job.dict()
    doc["extraction"] = summary["extraction"]
    doc["certification"] = summary["certification"]
    await db.catalog_imports.insert_one(doc)
    doc.pop("_id", None)

    stats = await import_accepted(doc, (owner or {}).get("id", "system"), blob_map=blob_map, floor_id=FLOOR_ID)
    await db.catalog_imports.update_one(
        {"id": doc["id"]},
        {"$set": {"status": "imported", "accepted_rows": stats["imported"] + stats["updated"], "rejected_rows": stats["skipped"]}},
    )

    panda = await db.brands.find_one({"name": BRAND, "floor_id": FLOOR_ID}, {"_id": 0, "id": 1})
    after_products = await db.products.count_documents({"brand_id": panda["id"], "floor_id": FLOOR_ID})
    after_media = await db.product_media.count_documents({"brand_id": panda["id"], "floor_id": FLOOR_ID})
    post = await scan_catalog(baseline_snapshot_dir=str(pre_snapshot))
    post_snapshot = await backup_db(["products", "product_media", "brands", "categories"])
    summary.update({
        "batch_result": "SUCCESS" if post.ok else "FAILED",
        "job_id": doc["id"],
        "products_before_panda": before_products,
        "panda_products_after": after_products,
        "panda_media_after": after_media,
        "stats": stats,
        "media_uploaded_delta": after_media - before_panda_media,
        "pre_import_snapshot": str(pre_snapshot),
        "post_import_snapshot": str(post_snapshot),
        "integrity_guard": post.to_public(),
    })
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    if not post.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
