"""Hansgrohe/AXOR batch importer — processes a small batch of the 14 original
Hansgrohe XLSX files (only 5 can be uploaded to chat at once), idempotently,
tracking progress across batches in /app/memory/hansgrohe_import_manifest.json
so re-running never reprocesses an already-completed file and "remaining
files" can always be reported accurately.

Usage:
    python scripts/run_hansgrohe_batch.py '<json-list-of-{"filename":..,"url":..}>'

Or edit BATCH below and run with no args.
"""
from __future__ import annotations
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import httpx  # noqa: E402
from catalog_pipeline.adapters.hansgrohe import HansgroheAdapter  # noqa: E402
from catalog_pipeline.certifier import validate  # noqa: E402
from catalog_pipeline.base import MISSING  # noqa: E402
from catalog_pipeline.orchestrator import import_accepted  # noqa: E402
from db import db  # noqa: E402
from models import CatalogImportJob  # noqa: E402

MANIFEST_PATH = Path("/app/memory/hansgrohe_import_manifest.json")

ALL_14_FILES = [
    "BM.xlsx", "Ceramic.xlsx", "HFAV.xlsx", "Holder.xlsx",
    "Thermostat.xlsx", "WBM.xlsx", "TBM.xlsx", "3hole.xlsx",
    "Single_lever.xlsx", "Spout.xlsx",
    "handshower.xlsx", "Showerhose.xlsx",
    "kitchen.xlsx", "SHOWERS_HANSGROHE.xlsx",
    "rail.xlsx",  # discovered mid-recovery, not in the original 14 — tracked anyway
]


def _norm(name: str) -> str:
    return Path(name).stem.strip().lower().replace(" ", "_")


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"processed_files": [], "batches": []}


def _save_manifest(m: dict) -> None:
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


async def _download(client: httpx.AsyncClient, url: str) -> bytes:
    r = await client.get(url, timeout=120.0, follow_redirects=True)
    r.raise_for_status()
    return r.content


async def main(batch: list[dict]) -> None:
    t0 = time.time()
    manifest = _load_manifest()
    already_done = set(manifest["processed_files"])

    to_process = [f for f in batch if _norm(f["filename"]) not in already_done]
    already_skipped = [f["filename"] for f in batch if _norm(f["filename"]) in already_done]

    adapter = HansgroheAdapter()
    all_rows = []
    per_file: list[dict] = []
    errors: list[str] = []

    async with httpx.AsyncClient() as client:
        for f in to_process:
            try:
                data = await _download(client, f["url"])
            except Exception as e:
                errors.append(f"{f['filename']}: download failed - {e}")
                continue
            try:
                rows, rep = adapter.extract(data, f["filename"])
            except Exception as e:
                errors.append(f"{f['filename']}: extraction failed - {e}")
                continue
            all_rows.extend(rows)
            per_file.append({
                "file": f["filename"], "rows": rep.parsed_rows,
                "images_found": rep.images_found, "images_mapped": rep.images_mapped,
                "warnings": rep.warnings,
            })
            print(f"[{f['filename']}] rows={rep.parsed_rows} images_mapped={rep.images_mapped}")

    if not all_rows:
        print("Nothing new to process.")
        report = {
            "files_processed": [], "already_done_skipped": already_skipped,
            "categories_created": [], "products_imported": 0, "products_updated": 0,
            "products_skipped": 0, "duplicate_skus": 0, "missing_images": 0,
            "errors": errors,
            "remaining_files": [f for f in ALL_14_FILES if _norm(f) not in already_done],
        }
        print(json.dumps(report, indent=2))
        return

    row_objs, cert = validate(all_rows)
    row_objs = _auto_accept(row_objs)
    all_rows_dicts = [r.to_public() for r in row_objs]

    owner = await db.users.find_one({"email": "owner@forge.app"}, {"id": 1, "_id": 0})
    accepted = sum(1 for r in all_rows_dicts if r.get("status") == "accepted")
    rejected = sum(1 for r in all_rows_dicts if r.get("status") == "rejected")

    cats_before = {c["name"] for c in await db.categories.find({}, {"_id": 0, "name": 1}).to_list(200)}

    job = CatalogImportJob(
        filename=f"Hansgrohe batch ({len(to_process)} files)",
        source_type="excel",  # type: ignore[arg-type]
        supplier_name="Hansgrohe",
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

    stats = {"imported": 0, "updated": 0, "skipped": 0}
    if accepted:
        stats = await import_accepted(doc, (owner or {}).get("id", "system"))
        await db.catalog_imports.update_one(
            {"id": doc["id"]},
            {"$set": {"status": "imported", "accepted_rows": stats["imported"] + stats["updated"],
                      "rejected_rows": stats["skipped"]}},
        )

    cats_after = {c["name"] for c in await db.categories.find({}, {"_id": 0, "name": 1}).to_list(200)}
    missing_images = sum(1 for r in all_rows_dicts if r.get("status") == "accepted" and not r.get("images"))

    manifest["processed_files"].extend(_norm(f["filename"]) for f in to_process)
    manifest["batches"].append({
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": [f["filename"] for f in to_process],
        "stats": stats,
    })
    _save_manifest(manifest)

    report = {
        "files_processed": [f["filename"] for f in to_process],
        "already_done_skipped": already_skipped,
        "categories_created": sorted(cats_after - cats_before),
        "products_imported": stats["imported"],
        "products_updated": stats["updated"],
        "products_skipped": stats["skipped"],
        "duplicate_skus_in_batch": cert.duplicates_sku,
        "missing_images": missing_images,
        "errors": errors,
        "runtime_s": round(time.time() - t0, 1),
        "remaining_files": [f for f in ALL_14_FILES if _norm(f) not in set(manifest["processed_files"])],
    }
    print("\n" + "=" * 70)
    print("BATCH REPORT")
    print("=" * 70)
    print(json.dumps(report, indent=2))

    Path("/app/memory/hansgrohe_batch_report_latest.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8",
    )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        BATCH = json.loads(sys.argv[1])
    else:
        BATCH = []
    asyncio.run(main(BATCH))
