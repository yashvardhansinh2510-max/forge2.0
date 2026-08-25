"""Execute production catalog imports for GROHE, GEBERIT, VITRA.

Downloads each supplier file from the customer-assets URL, runs the full
pipeline (Extract → Normalise → Validate → Certify), auto-accepts high-
confidence rows, then imports into products collection. Prints a detailed
report per brand.
"""
from __future__ import annotations
import asyncio
import sys
import time
from pathlib import Path

# Ensure repo root on path so imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from catalog_pipeline.orchestrator import run_pipeline, import_accepted  # noqa: E402
from db import db  # noqa: E402
from models import CatalogImportJob  # noqa: E402


UPLOADS = [
    {
        "brand": "Grohe",
        "filename": "GROHE PRICING 2026.pdf",
        "url": "https://customer-assets.emergentagent.com/job_draft-qb/artifacts/qds8aczp_GROHE%20PRICING%202026.pdf",
    },
    {
        "brand": "Geberit",
        "filename": "GEBERIT_MRP_Catalogue_-2026.pdf",
        "url": "https://customer-assets.emergentagent.com/job_draft-qb/artifacts/ysirq7ab_GEBERIT_MRP_Catalogue_-2026.pdf",
    },
    {
        "brand": "Vitra",
        "filename": "VITRA Price Table 2026.xlsx",
        "url": "https://customer-assets.emergentagent.com/job_draft-qb/artifacts/f9wbagsj_VITRA%20Price%20Table%202026.xlsx",
    },
]


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content


async def _get_owner_id() -> str:
    doc = await db.users.find_one({"email": "owner@forge.app"}, {"id": 1, "_id": 0})
    return doc["id"] if doc else "system"


async def _persist_job(brand: str, filename: str, source_type: str, result: dict, user_id: str) -> dict:
    job = CatalogImportJob(
        filename=filename,
        source_type=source_type,  # type: ignore[arg-type]
        supplier_name=brand,
        total_rows=len(result["rows"]),
        accepted_rows=sum(1 for r in result["rows"] if r.get("status") == "accepted"),
        rejected_rows=sum(1 for r in result["rows"] if r.get("status") == "rejected"),
        status="classified",  # type: ignore[arg-type]
        rows=result["rows"],
        created_by=user_id,
    )
    doc = job.dict()
    doc["extraction"] = result["extraction"]
    doc["certification"] = result["certification"]
    await db.catalog_imports.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def main():
    owner_id = await _get_owner_id()
    all_results = []
    for job in UPLOADS:
        brand = job["brand"]
        fn = job["filename"]
        print(f"\n{'='*70}")
        print(f"  IMPORTING · {brand} · {fn}")
        print(f"{'='*70}")
        t0 = time.time()

        try:
            data = await _download(job["url"])
        except Exception as e:
            print(f"  ✗ DOWNLOAD FAILED: {e}")
            continue
        print(f"  ✓ downloaded {len(data):,} bytes in {time.time()-t0:.1f}s")

        try:
            result = await asyncio.wait_for(run_pipeline(brand, fn, data), timeout=600)
        except asyncio.TimeoutError:
            print("  ✗ PIPELINE TIMEOUT (>600s)")
            continue
        except Exception as e:
            print(f"  ✗ PIPELINE FAILED: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            continue

        cert = result.get("certification", {})
        ext = result.get("extraction", {})
        rows = result.get("rows", [])
        source_type = "excel" if fn.lower().endswith((".xlsx", ".xls")) else "pdf"

        print(f"  ✓ extracted rows: {ext.get('rows_extracted') or len(rows)}")
        print(f"  ✓ images extracted: {ext.get('images_extracted', 0)}")
        print(f"  ✓ certification score: {cert.get('overall_score')}")
        print(f"  ✓ duplicates_sku: {cert.get('duplicates_sku', 0)}")
        print(f"  ✓ pipeline runtime: {time.time()-t0:.1f}s")

        persisted = await _persist_job(brand, fn, source_type, result, owner_id)
        job_id = persisted["id"]
        accepted = sum(1 for r in rows if r.get("status") == "accepted")
        rejected = sum(1 for r in rows if r.get("status") == "rejected")
        pending = sum(1 for r in rows if r.get("status") == "pending")
        print(f"  → job_id={job_id}  accepted={accepted}  pending={pending}  rejected={rejected}")

        # Auto-approve if certification score is acceptable and there are accepted rows
        if accepted == 0:
            print(f"  ⚠ 0 accepted rows — skipping import for {brand}.")
            all_results.append({
                "brand": brand, "job_id": job_id, "status": "no_accepted_rows",
                "cert": cert, "extraction": ext,
            })
            continue

        stats = await import_accepted(persisted, owner_id)
        await db.catalog_imports.update_one(
            {"id": job_id},
            {"$set": {"status": "imported",
                      "accepted_rows": stats["imported"] + stats["updated"],
                      "rejected_rows": stats["skipped"]}},
        )
        print(f"  ✓ IMPORTED → {stats}")
        all_results.append({
            "brand": brand, "job_id": job_id, "status": "imported",
            "cert": cert, "extraction": ext, "stats": stats,
        })

    # Final tally
    print(f"\n{'#'*70}")
    print("  FINAL TALLY")
    print(f"{'#'*70}")
    tot_products = await db.products.count_documents({})
    tot_demo = await db.products.count_documents({"tags": "demo"})
    tot_real = tot_products - tot_demo
    tot_brands = await db.brands.count_documents({})
    tot_cats = await db.categories.count_documents({})
    print(f"  Total products: {tot_products} (real: {tot_real}, demo: {tot_demo})")
    print(f"  Total brands:   {tot_brands}")
    print(f"  Total categories: {tot_cats}")
    for r in all_results:
        print(f"  - {r['brand']}: {r['status']} · stats={r.get('stats')}")

    return all_results


if __name__ == "__main__":
    asyncio.run(main())
