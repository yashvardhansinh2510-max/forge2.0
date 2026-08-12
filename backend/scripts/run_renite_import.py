"""Import RENITE tiles into Ground Floor and archive the supplied workbook.

Usage:
    python scripts/run_renite_import.py --source "/absolute/path/RENITE 2026.xlsx"
    python scripts/run_renite_import.py --source "/absolute/path/RENITE 2026.xlsx" --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from auth import TILES_FLOOR_ID
from catalog_pipeline.adapters.renite import ReniteAdapter
from catalog_pipeline.certifier import validate
from catalog_pipeline.integrity_guard import scan_catalog
from catalog_pipeline.orchestrator import _offload_row_images, import_accepted
from db import db
from media_storage.factory import get_media_storage, private_bucket
from models import CatalogImportJob


def _auto_accept(rows):
    for row in rows:
        if row.status == "pending" and row.confidence >= 0.85 and row.sku and row.mrp is not None and row.category:
            row.status = "accepted"
    return rows


async def main(source: Path, dry_run: bool) -> None:
    if not source.is_file():
        raise SystemExit(f"Source workbook not found: {source}")
    data = source.read_bytes()
    rows, extraction = ReniteAdapter().extract(data, source.name)
    validated, certification = validate(rows)
    validated = _auto_accept(validated)
    public_rows = [row.to_public() for row in validated]
    accepted = sum(row["status"] == "accepted" for row in public_rows)
    rejected = sum(row["status"] == "rejected" for row in public_rows)
    summary = {
        "source_file": source.name, "source_sha1": hashlib.sha1(data).hexdigest(),
        "total_rows": len(public_rows), "accepted": accepted, "rejected": rejected,
        "missing_images": sum(not row["images"] for row in public_rows),
        "extraction": extraction.__dict__, "certification": certification.to_public(),
    }
    if not public_rows or rejected or accepted != len(public_rows):
        raise SystemExit(f"RENITE validation did not produce a clean accepted batch: {json.dumps(summary)}")
    if dry_run:
        print(json.dumps({**summary, "mode": "dry-run"}, indent=2, default=str))
        return

    before = await scan_catalog()
    if not before.ok:
        raise SystemExit("Catalog integrity guard failed before import; no changes made.")
    owner = await db.users.find_one({"email": "owner@forge.app"}, {"id": 1, "_id": 0})
    source_key = f"catalog-sources/ground-floor/renite/{summary['source_sha1']}/{source.name}"
    storage = get_media_storage()
    source_asset = {
        "bucket": private_bucket(), "storage_key": source_key,
        "sha1": summary["source_sha1"], "size_bytes": len(data),
        "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    if not await storage.exists(bucket=private_bucket(), key=source_key):
        stored = await storage.upload(
            bucket=private_bucket(), key=source_key, data=data,
            content_type=source_asset["content_type"], upsert=False, cache_control="private, max-age=0",
        )
        source_asset.update({"sha1": stored.sha1, "size_bytes": stored.size_bytes})
    blob_map = await _offload_row_images(public_rows)
    job = CatalogImportJob(
        filename=source.name, source_type="excel", supplier_name="Renite",
        total_rows=len(public_rows), accepted_rows=accepted, rejected_rows=rejected,
        status="classified", rows=public_rows, created_by=(owner or {}).get("id", "system"),
        floor_id=TILES_FLOOR_ID,
    ).model_dump()
    job["extraction"] = extraction.__dict__
    job["certification"] = certification.to_public()
    job["source_asset"] = source_asset
    await db.catalog_imports.insert_one(job)
    job.pop("_id", None)
    result = await import_accepted(job, (owner or {}).get("id", "system"), blob_map=blob_map, floor_id=TILES_FLOOR_ID)
    if result["failed"] or result["skipped"]:
        await db.catalog_imports.update_one({"id": job["id"]}, {"$set": {"status": "failed", "error": json.dumps(result)}})
        raise SystemExit(f"Import incomplete; job {job['id']} is recoverable through its snapshots: {json.dumps(result)}")
    await db.catalog_imports.update_one({"id": job["id"]}, {"$set": {"status": "imported"}})
    after = await scan_catalog()
    if not after.ok:
        raise SystemExit(f"Post-import integrity guard failed; job {job['id']} can be rolled back.")
    print(json.dumps({**summary, "job_id": job["id"], "source_asset": job["source_asset"], "import_result": result, "catalog_integrity": "passed"}, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    asyncio.run(main(arguments.source, arguments.dry_run))
