"""Import the Milagro and Kenzo ground-floor tile workbooks.

Run with ``--dry-run`` first; normal mode snapshots Mongo before and after and
uploads the already-landscape artwork to the public Supabase product bucket.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from backup_db import backup as backup_db
from catalog_pipeline.base import MISSING
from catalog_pipeline.certifier import validate
from catalog_pipeline.orchestrator import _offload_row_images, import_accepted
from catalog_pipeline.adapters.tile_per_piece import KenzoAdapter, MilagroAdapter
from db import db
from models import CatalogImportJob

FLOOR_ID = "ground-floor"


async def import_file(path: Path, adapter, args: argparse.Namespace) -> dict:
    rows, extraction = adapter.extract(path.read_bytes(), path.name)
    rows, certification = validate(rows)
    for row in rows:
        if row.status == "pending" and row.confidence >= 0.85 and row.sku not in (MISSING, None) and row.mrp not in (MISSING, None):
            row.status = "accepted"
    public_rows = [row.to_public() for row in rows]
    source_rows, source_accepted = len(public_rows), sum(row["status"] == "accepted" for row in public_rows)
    if args.start or args.limit:
        end = args.start + args.limit if args.limit else None
        public_rows = public_rows[args.start:end]
    accepted = sum(row["status"] == "accepted" for row in public_rows)
    summary = {"brand": adapter.brand, "source_file": path.name, "rows": len(public_rows), "accepted": accepted,
               "source_rows": source_rows, "source_accepted": source_accepted, "start": args.start,
               "images_found": extraction.images_found, "images_mapped": extraction.images_mapped,
               "warnings": extraction.warnings, "certification": certification.to_public()}
    if args.dry_run:
        return summary
    owner = await db.users.find_one({"email": "owner@forge.app"}, {"id": 1, "_id": 0})
    blob_map = await _offload_row_images(public_rows)
    job = CatalogImportJob(filename=path.name, source_type="excel", supplier_name=adapter.brand,
                           total_rows=len(public_rows), accepted_rows=accepted, rejected_rows=0,
                           status="classified", rows=public_rows, created_by=(owner or {}).get("id", "system"), floor_id=FLOOR_ID)
    doc = job.dict()
    doc["extraction"] = extraction.__dict__
    doc["certification"] = certification.to_public()
    await db.catalog_imports.insert_one(doc)
    doc.pop("_id", None)
    stats = await import_accepted(doc, (owner or {}).get("id", "system"), blob_map=blob_map, floor_id=FLOOR_ID)
    await db.catalog_imports.update_one({"id": doc["id"]}, {"$set": {"status": "imported", "accepted_rows": stats["imported"] + stats["updated"], "rejected_rows": stats["skipped"]}})
    return {**summary, **stats, "job_id": doc["id"]}


async def main(args: argparse.Namespace) -> None:
    sources = [(Path(args.milagro), MilagroAdapter()), (Path(args.kenzo), KenzoAdapter())]
    sources = [(path, adapter) for path, adapter in sources if adapter.brand.lower() in args.brands]
    if not sources:
        raise SystemExit("No selected brand; choose milagro and/or kenzo")
    missing = [str(path) for path, _ in sources if not path.is_file()]
    if missing:
        raise SystemExit("Source file not found: " + ", ".join(missing))
    if not args.dry_run and not args.skip_snapshot:
        pre_snapshot = await backup_db(["products", "product_media", "brands", "categories", "catalog_imports"])
    else:
        pre_snapshot = None
    results = [await import_file(path, adapter, args) for path, adapter in sources]
    post_snapshot = await backup_db(["products", "product_media", "brands", "categories", "catalog_imports"]) if not args.dry_run and not args.skip_snapshot else None
    print(json.dumps({"mode": "dry-run" if args.dry_run else "import", "pre_snapshot": str(pre_snapshot) if pre_snapshot else None,
                      "post_snapshot": str(post_snapshot) if post_snapshot else None, "brands": results}, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--milagro", required=True)
    parser.add_argument("--kenzo", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--start", type=int, default=0, help="zero-based source row offset (for safe resumable batches)")
    parser.add_argument("--limit", type=int, default=0, help="maximum source rows per brand (0 imports all)")
    parser.add_argument("--skip-snapshot", action="store_true", help="for resumed batches after a pre-import snapshot exists")
    parser.add_argument("--brands", nargs="+", choices=["milagro", "kenzo"], default=["milagro", "kenzo"])
    args = parser.parse_args()
    if args.start < 0 or args.limit < 0:
        parser.error("--start and --limit must be non-negative")
    asyncio.run(main(args))
