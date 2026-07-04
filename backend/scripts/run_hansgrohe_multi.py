"""Run Hansgrohe multi-file import (all XLSX in /app/backend/temp/hansgrohe/).

Merges rows from all files into a single classified catalog_imports job under
supplier_name='Hansgrohe'. AXOR products stay under Hansgrohe brand with
collection='AXOR'. Category comes verbatim from each file's stem.
"""
from __future__ import annotations
import asyncio, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from catalog_pipeline.adapters.hansgrohe import HansgroheAdapter  # noqa: E402
from catalog_pipeline.certifier import validate  # noqa: E402
from catalog_pipeline.base import MISSING  # noqa: E402
from db import db  # noqa: E402
from models import CatalogImportJob  # noqa: E402
import pickle  # noqa: E402


CACHE_PATH = Path("/tmp/hansgrohe_rows.pkl")


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


SRC = Path("/app/backend/temp/hansgrohe")
# 14 unique files; handshower.xlsx sent twice — kept once.
FILES = [
    "BM.xlsx", "Ceramic.xlsx", "HFAV.xlsx", "Holder.xlsx",
    "Thermostat.xlsx", "WBM.xlsx", "TBM.xlsx", "3hole.xlsx",
    "Single_lever.xlsx", "Spout.xlsx",
    "handshower.xlsx", "Showerhose.xlsx",
    "kitchen.xlsx", "SHOWERS_HANSGROHE.xlsx",
]


async def main():
    t0 = time.time()
    adapter = HansgroheAdapter()

    all_rows = []
    per_file_stats = []
    total_images_found = 0
    total_images_mapped = 0
    warnings: list[str] = []

    # Resume from cached extraction if present (extraction is 25+ min)
    use_cache = "--no-cache" not in sys.argv and CACHE_PATH.exists()
    if use_cache:
        try:
            cached = pickle.loads(CACHE_PATH.read_bytes())
            all_rows = cached["rows"]
            per_file_stats = cached["per_file"]
            total_images_found = cached["images_found"]
            total_images_mapped = cached["images_mapped"]
            warnings = cached["warnings"]
            # Re-tune confidence for cached rows (adapter rule may have changed since cache)
            from catalog_pipeline.base import MISSING as _M
            for _r in all_rows:
                _has_mrp = _r.mrp not in (_M, None)
                _has_full = _has_mrp and _r.series and _r.series != _M and _r.finish and _r.finish != _M
                _r.confidence = 0.94 if _has_full else (0.86 if _has_mrp else 0.6)
            print(f"loaded {len(all_rows)} rows from cache {CACHE_PATH}", flush=True)
        except Exception as e:
            print(f"cache load failed ({e}); re-extracting", flush=True)
            use_cache = False

    if not use_cache:
        for name in FILES:
            p = SRC / name
            if not p.exists():
                warnings.append(f"missing file: {name}")
                continue
            rows, rep = adapter.extract(p.read_bytes(), name)
            all_rows.extend(rows)  # keep as ProductRow objects
            total_images_found += rep.images_found
            total_images_mapped += rep.images_mapped
            for w in rep.warnings:
                warnings.append(f"[{name}] {w}")
            per_file_stats.append({
                "file": name,
                "rows": rep.parsed_rows,
                "images_found": rep.images_found,
                "images_mapped": rep.images_mapped,
            })
            print(f"[{name}] rows={rep.parsed_rows} images_mapped={rep.images_mapped}", flush=True)

        # Cache extraction (expensive, ~25 min) so a downstream bug doesn't force a re-run
        try:
            CACHE_PATH.write_bytes(pickle.dumps({
                "rows": all_rows, "per_file": per_file_stats,
                "images_found": total_images_found, "images_mapped": total_images_mapped,
                "warnings": warnings,
            }))
            print(f"cached rows → {CACHE_PATH}", flush=True)
        except Exception as e:
            print(f"cache write failed: {e}", flush=True)

    # Validate + certify across the merged batch
    row_objs, cert = validate(all_rows)
    row_objs = _auto_accept(row_objs)
    all_rows_dicts = [r.to_public() for r in row_objs]

    # ---- Externalise base64 images into `catalog_image_blobs` collection ----
    # A ~1400-row job with per-row hero images produces a ~29MB doc which
    # exceeds MongoDB's 16MB BSON limit. Strategy: hash each data_url, write
    # it once to catalog_image_blobs, and replace the row's `images` list with
    # a compact `blob:<sha1>` reference. The orchestrator's import_accepted
    # already knows how to dereference this.
    import hashlib
    unique_blobs: dict[str, str] = {}   # sha1 → data_url
    for row in all_rows_dicts:
        imgs = row.get("images") or []
        new_refs: list[str] = []
        for u in imgs:
            if not u:
                continue
            if u.startswith("blob:"):
                new_refs.append(u); continue
            sha1 = hashlib.sha1(u.encode("utf-8")).hexdigest()[:32]
            unique_blobs.setdefault(sha1, u)
            new_refs.append(f"blob:{sha1}")
        row["images"] = new_refs

    # Upsert blobs (idempotent). Batch of 100 to keep insert time bounded.
    from motor.motor_asyncio import AsyncIOMotorCollection  # noqa: F401
    if unique_blobs:
        pairs = list(unique_blobs.items())
        for i in range(0, len(pairs), 100):
            chunk = pairs[i:i + 100]
            ops = []
            for sha1, data_url in chunk:
                ops.append({"sha1": sha1, "data_url": data_url})
            try:
                await db.catalog_image_blobs.insert_many(ops, ordered=False)
            except Exception:
                # Duplicate sha1s (from prior runs) → upsert individually
                for op in ops:
                    await db.catalog_image_blobs.update_one({"sha1": op["sha1"]}, {"$set": op}, upsert=True)
    print(f"externalised {len(unique_blobs)} unique image blobs → catalog_image_blobs", flush=True)

    owner = await db.users.find_one({"email": "owner@forge.app"}, {"id": 1, "_id": 0})
    accepted = sum(1 for r in all_rows_dicts if r.get("status") == "accepted")
    rejected = sum(1 for r in all_rows_dicts if r.get("status") == "rejected")

    job = CatalogImportJob(
        filename="Hansgrohe multi-file bundle (9 XLSX)",
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
    doc["extraction"] = {
        "rows_extracted": len(all_rows_dicts),
        "images_extracted": total_images_found,
        "images_mapped": total_images_mapped,
        "per_file": per_file_stats,
        "warnings": warnings,
    }
    doc["certification"] = cert.to_public()

    # Replace any previous classified Hansgrohe job (idempotent)
    await db.catalog_imports.delete_many({"supplier_name": "Hansgrohe", "status": "classified"})
    await db.catalog_imports.insert_one(doc)
    doc.pop("_id", None)

    # QA report
    families = {r.get("family_key") for r in all_rows_dicts if r.get("family_key")}
    subcats  = {r.get("subcategory") for r in all_rows_dicts if r.get("subcategory")}
    series   = {r.get("series") for r in all_rows_dicts if r.get("series")}
    finishes = {r.get("finish") for r in all_rows_dicts if r.get("finish")}
    colours  = {r.get("colour") for r in all_rows_dicts if r.get("colour")}
    variants = sum(1 for r in all_rows_dicts if r.get("variant"))
    cats = {r.get("category") for r in all_rows_dicts if r.get("category")}
    axor_rows = sum(1 for r in all_rows_dicts if r.get("collection") == "AXOR")
    hg_rows   = sum(1 for r in all_rows_dicts if r.get("collection") == "Hansgrohe")

    qa_md = f"""# Hansgrohe — QA Report
job_id: `{doc['id']}`
runtime: {round(time.time()-t0,1)} s

## Certification
- overall_score: **{cert.overall_score}**
- production_ready: {cert.production_ready}
- duplicates_sku: {cert.duplicates_sku}
- cross_family_skus: {cert.cross_family_skus}

## Row status
- accepted: {accepted}
- pending:  {sum(1 for r in all_rows_dicts if r.get('status')=='pending')}
- rejected: {rejected}

## Collection split
- Hansgrohe (main): {hg_rows}
- AXOR (premium):   {axor_rows}

## Structural counts
- categories:    {len(cats)}   ({sorted(cats)})
- subcategories: {len(subcats)}
- series:        {len(series)}
- families:      {len(families)}
- variants:      {variants}
- finishes:      {len(finishes)}
- colours:       {len(colours)}

## Per-file
{json.dumps(per_file_stats, indent=2)}

## Image quality
{json.dumps(cert.image_quality, indent=2)}
"""
    Path("/app/memory/hansgrohe_qa_report.md").write_text(qa_md, encoding="utf-8")
    print("\n=== HANSGROHE ===")
    print(f"total_rows={len(all_rows_dicts)}  accepted={accepted}  rejected={rejected}")
    print(f"score={cert.overall_score}  duplicates={cert.duplicates_sku}  cross_family={cert.cross_family_skus}")
    print(f"categories={sorted(cats)}  families={len(families)}  series={len(series)}")
    print(f"AXOR rows={axor_rows}  HG rows={hg_rows}")


if __name__ == "__main__":
    asyncio.run(main())
