"""Run one brand import end-to-end. Extract → Validate → Certify.
Does NOT auto-approve; writes a QA report to /app/memory/{brand}_qa_report.md.
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
from catalog_pipeline.orchestrator import run_pipeline  # noqa: E402
from db import db  # noqa: E402
from models import CatalogImportJob  # noqa: E402


SOURCES = {
    "Vitra":   ("VITRA Price Table 2026.xlsx",        "/app/backend/temp/vitra.xlsx",   None),
    "Grohe":   ("GROHE PRICING 2026.pdf",             "/app/backend/temp/grohe.pdf",    None),
    "Geberit": ("GEBERIT_MRP_Catalogue_-2026.pdf",    "/app/backend/temp/geberit.pdf",  None),
}


async def owner_id() -> str:
    d = await db.users.find_one({"email": "owner@forge.app"}, {"id": 1, "_id": 0})
    return d["id"] if d else "system"


async def run_one(brand: str) -> dict:
    fn, path, url = SOURCES[brand]
    t0 = time.time()
    if url and not Path(path).exists():
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as c:
            r = await c.get(url); r.raise_for_status()
            Path(path).write_bytes(r.content)
    data = Path(path).read_bytes()
    print(f"[{brand}] loaded {len(data):,} bytes")

    result = await run_pipeline(brand, fn, data)
    rows = result["rows"]
    ext  = result.get("extraction", {}) or {}
    cert = result.get("certification", {}) or {}
    stype = "excel" if fn.lower().endswith((".xlsx",".xls")) else "pdf"

    job = CatalogImportJob(
        filename=fn, source_type=stype, supplier_name=brand,  # type: ignore[arg-type]
        total_rows=len(rows),
        accepted_rows=sum(1 for r in rows if r.get("status")=="accepted"),
        rejected_rows=sum(1 for r in rows if r.get("status")=="rejected"),
        status="classified",  # type: ignore[arg-type]
        rows=rows, created_by=await owner_id(),
    )
    doc = job.dict()
    doc["extraction"] = ext; doc["certification"] = cert
    await db.catalog_imports.insert_one(doc); doc.pop("_id", None)

    accepted = sum(1 for r in rows if r.get("status")=="accepted")
    pending  = sum(1 for r in rows if r.get("status")=="pending")
    rejected = sum(1 for r in rows if r.get("status")=="rejected")

    # QA report
    families = set()
    subcats  = set()
    series   = set()
    finishes = set()
    colours  = set()
    dims     = 0
    with_img = 0
    for r in rows:
        if r.get("family_key"):    families.add(r["family_key"])
        if r.get("subcategory"):   subcats.add(r["subcategory"])
        if r.get("series"):        series.add(r["series"])
        if r.get("finish"):        finishes.add(r["finish"])
        if r.get("colour"):        colours.add(r["colour"])
        if r.get("dimensions"):    dims += 1
        if r.get("images") or r.get("image_meta"):  with_img += 1

    qa = {
        "brand": brand,
        "job_id": doc["id"],
        "runtime_s": round(time.time()-t0, 1),
        "extraction": ext,
        "certification": cert,
        "accepted": accepted, "pending": pending, "rejected": rejected,
        "counts": {
            "rows": len(rows), "families": len(families),
            "subcategories": len(subcats), "series": len(series),
            "finishes": len(finishes), "colours": len(colours),
            "with_dimensions": dims, "with_images": with_img,
        },
    }

    out = Path("/app/memory") / f"{brand.lower()}_qa_report.md"
    out.write_text(f"""# {brand} — QA Report
job_id: `{doc['id']}`
runtime: {qa['runtime_s']} s

## Extraction
- rows_extracted: {ext.get('rows_extracted', len(rows))}
- images_extracted: {ext.get('images_extracted', 0)}

## Certification
- overall_score: **{cert.get('overall_score')}**
- production_ready: {cert.get('production_ready')}
- duplicates_sku: {cert.get('duplicates_sku', 0)}
- cross_family_skus: {cert.get('cross_family_skus', 0)}

## Row status
- accepted: {accepted}
- pending:  {pending}
- rejected: {rejected}

## Structural counts
- families:      {qa['counts']['families']}
- subcategories: {qa['counts']['subcategories']}
- series:        {qa['counts']['series']}
- finishes:      {qa['counts']['finishes']}
- colours:       {qa['counts']['colours']}
- with_dimensions: {qa['counts']['with_dimensions']}
- with_images:     {qa['counts']['with_images']}

## Image quality
{json.dumps(cert.get('image_quality') or {}, indent=2)}
""", encoding="utf-8")
    (Path("/app/memory") / f"{brand.lower()}_qa_report.json").write_text(json.dumps(qa, indent=2, default=str), encoding="utf-8")
    print(f"[{brand}] DONE  score={cert.get('overall_score')}  accepted={accepted}  pending={pending}  rejected={rejected}")
    return qa


async def main():
    brand = sys.argv[1] if len(sys.argv) > 1 else "Vitra"
    q = await run_one(brand)
    print(json.dumps({k: q[k] for k in ("brand","accepted","pending","rejected","counts")}, default=str))


if __name__ == "__main__":
    asyncio.run(main())
