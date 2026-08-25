"""GROHE Unified Catalog Re-import (2026-08, ingestion-fix pass).

Replaces the previous 4-pass batch approach (full_replacement + batch2 +
batch3 + batch4) with a SINGLE pass over all 15 supplier files, using the
corrected `grohe_xlsx_extract.py` (SKU-tail finish fallback + `colour` field
now populated). Root-cause fix, not a per-product patch — every future
Grohe re-import uses the same corrected module.

Rules preserved from the original batch scripts (never loosened):
  - Never fabricate price/category/finish.
  - Row with no price in the supplier file -> excluded, reported.
  - SKU appearing under >1 file/category with no way to pick one with
    confidence -> excluded from BOTH, reported (never silently overwrite).
  - Full backup before any delete; nothing outside the Grohe brand is
    touched (quotations/purchases/payments/followups/customers untouched —
    they reference product IDs by snapshot, never live joins).

Usage:
    python scripts/run_grohe_unified_reimport.py --dry-run
    python scripts/run_grohe_unified_reimport.py --execute
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from db import db  # noqa: E402
from models import Product, Category  # noqa: E402
from catalog_pipeline.integrity_guard import scan_catalog  # noqa: E402
from grohe_xlsx_extract import (  # noqa: E402
    extract_all, GroheRow, FILES, FILES_BATCH2, FILES_BATCH3, FILES_BATCH4,
    ORIGINAL_FILENAMES, ORIGINAL_FILENAMES_BATCH2, ORIGINAL_FILENAMES_BATCH3,
    ORIGINAL_FILENAMES_BATCH4,
)
from run_grohe_full_replacement import dedupe_rows, backup_grohe, _json_default  # noqa: E402

XLSX_DIR = "/tmp/catalog_fix/grohe"
BACKUP_ROOT = Path(__file__).resolve().parent.parent / "backups"

ALL_FILES = {**FILES, **FILES_BATCH2, **FILES_BATCH3, **FILES_BATCH4}
ALL_ORIGINAL_FILENAMES = {
    **ORIGINAL_FILENAMES, **ORIGINAL_FILENAMES_BATCH2,
    **ORIGINAL_FILENAMES_BATCH3, **ORIGINAL_FILENAMES_BATCH4,
}

OLD_GROHE_CATEGORY_NAMES = list(ALL_FILES.keys()) + [
    "Faucets", "Showers", "Accessories", "Kitchen Sinks", "Urinals", "Bathtubs",
]


async def run(dry_run: bool) -> dict:
    report: dict = {"dry_run": dry_run}

    print("=" * 78)
    print("PHASE 1 — EXTRACT ALL 15 SUPPLIER FILES (corrected pipeline)")
    print("=" * 78)
    all_rows = extract_all(XLSX_DIR, ALL_FILES, ALL_ORIGINAL_FILENAMES)
    total_extracted = sum(len(v) for v in all_rows.values())
    print(f"Extracted {total_extracted} raw rows across {len(all_rows)} files.")

    per_category_rows: dict[str, list[GroheRow]] = {}
    skipped_no_price: list[dict] = []
    collapsed_all: list[dict] = []
    for cat, rows in all_rows.items():
        deduped, collapsed_log = await dedupe_rows(rows)
        collapsed_all.extend([{**c, "category": cat} for c in collapsed_log])
        priced = []
        for r in deduped:
            if r.mrp is None:
                skipped_no_price.append({"category": cat, "sku": r.sku, "description": r.description})
                continue
            priced.append(r)
        per_category_rows[cat] = priced

    # Cross-file conflict guard: same SKU in >1 category file with a
    # different description/price -> never guess which is correct, exclude
    # both, report. (Different files with an IDENTICAL row — same
    # description+price — collapse to one, since that's just the supplier
    # listing the same accessory in two kit sections, not a conflict.)
    sku_locations: dict[str, list[tuple[str, GroheRow]]] = defaultdict(list)
    for cat, rows in per_category_rows.items():
        for r in rows:
            sku_locations[r.sku].append((cat, r))

    conflicts: list[dict] = []
    excluded_skus: set[str] = set()
    for sku, locs in sku_locations.items():
        if len(locs) < 2:
            continue
        payloads = {(cat, r.description, r.mrp) for cat, r in locs}
        if len(payloads) > 1:
            excluded_skus.add(sku)
            conflicts.append({
                "sku": sku,
                "occurrences": [{"category": cat, "description": r.description, "mrp": r.mrp} for cat, r in locs],
            })

    final_rows: dict[str, list[GroheRow]] = {}
    for cat, rows in per_category_rows.items():
        kept = [r for r in rows if r.sku not in excluded_skus]
        # within-category, keep only first occurrence per SKU (identical dup)
        seen: set[str] = set()
        uniq = []
        for r in kept:
            if r.sku in seen:
                continue
            seen.add(r.sku)
            uniq.append(r)
        final_rows[cat] = uniq

    total_final = sum(len(v) for v in final_rows.values())
    total_images_ok = sum(1 for rows in final_rows.values() for r in rows if r.image.ok)
    print(f"After dedupe + price-validation + conflict exclusion: {total_final} importable products.")
    print(f"In-file collapsed duplicates: {len(collapsed_all)}  |  Skipped (no price): {len(skipped_no_price)}  "
          f"|  Cross-file SKU conflicts excluded: {len(conflicts)}")
    print(f"Image coverage: {total_images_ok}/{total_final}")

    finish_coverage = sum(1 for rows in final_rows.values() for r in rows if r.finish)
    print(f"Finish/colour coverage: {finish_coverage}/{total_final}")

    report["extracted_total"] = total_extracted
    report["final_importable"] = total_final
    report["collapsed_duplicates"] = collapsed_all
    report["skipped_no_price"] = skipped_no_price
    report["cross_file_conflicts_excluded"] = conflicts
    report["per_category_counts"] = {k: len(v) for k, v in final_rows.items()}
    report["image_coverage"] = f"{total_images_ok}/{total_final}"
    report["finish_coverage"] = f"{finish_coverage}/{total_final}"

    if conflicts:
        print("\n!!! CROSS-FILE SKU CONFLICTS (excluded from import, need human decision):")
        for c in conflicts:
            print(f"   SKU {c['sku']}: {c['occurrences']}")

    print("\n" + "=" * 78)
    print("PHASE 2 — PRE-FLIGHT")
    print("=" * 78)
    brand_doc = await db.brands.find_one({"name": {"$regex": "^grohe$", "$options": "i"}}, {"_id": 0})
    if not brand_doc:
        raise RuntimeError("Grohe brand not found — aborting, nothing touched.")
    brand_id = brand_doc["id"]
    old_count = await db.products.count_documents({"brand_id": brand_id})
    old_media_count = await db.product_media.count_documents({"brand_id": brand_id})
    print(f"Existing Grohe products: {old_count}  |  existing Grohe media docs: {old_media_count}")
    report["old_grohe_products"] = old_count
    report["old_grohe_media"] = old_media_count

    grohe_ids = {p["id"] async for p in db.products.find({"brand_id": brand_id}, {"_id": 0, "id": 1})}
    affected_quotations = 0
    affected_lines = 0
    async for q in db.quotations.find({}, {"_id": 0, "items": 1}):
        hit = [it for it in q.get("items", []) if it.get("product_id") in grohe_ids]
        if hit:
            affected_quotations += 1
            affected_lines += len(hit)
    report["quotations_with_frozen_grohe_snapshots"] = affected_quotations
    print(f"Historical quotations referencing current Grohe SKUs (snapshot-preserved, unaffected): "
          f"{affected_quotations} quotations / {affected_lines} lines")

    if dry_run:
        print("\nDRY RUN — no writes performed. Re-run with --execute to apply.")
        report["stopped"] = False
        report["dry_run_only"] = True
        return report

    print("\n" + "=" * 78)
    print("PHASE 3 — BACKUP")
    print("=" * 78)
    backup_dir = await backup_grohe(brand_id)
    report["backup_dir"] = str(backup_dir)

    print("\n" + "=" * 78)
    print("PHASE 4 — DELETE EXISTING GROHE CATALOG (products + media only)")
    print("=" * 78)
    del_products = await db.products.delete_many({"brand_id": brand_id})
    del_media = await db.product_media.delete_many({"brand_id": brand_id})
    print(f"Deleted {del_products.deleted_count} Grohe products, {del_media.deleted_count} Grohe media docs.")
    report["deleted_products"] = del_products.deleted_count
    report["deleted_media"] = del_media.deleted_count

    print("\n" + "=" * 78)
    print("PHASE 5 — CATEGORIES (create-or-reuse, filename-derived ONLY)")
    print("=" * 78)
    category_id_by_name: dict[str, str] = {}
    for cat_name in final_rows.keys():
        existing = await db.categories.find_one({"name": cat_name}, {"_id": 0})
        if existing:
            category_id_by_name[cat_name] = existing["id"]
        else:
            slug = cat_name.lower().replace(" ", "-")
            c = Category(name=cat_name, slug=slug)
            await db.categories.insert_one(c.dict())
            category_id_by_name[cat_name] = c.id
            print(f"  Created new category '{cat_name}' (id={c.id})")

    print("\n" + "=" * 78)
    print("PHASE 6 — IMPORT PRODUCTS + UPLOAD IMAGES")
    print("=" * 78)
    from services.media_service import upload_and_register

    imported = 0
    images_uploaded = 0
    for cat_name, rows in final_rows.items():
        cat_id = category_id_by_name[cat_name]
        for r in rows:
            family_name = r.description.strip().title() if r.description else None
            specs = {"sl_no": r.sl, "source_file": r.source_file, "segment": r.segment}
            if r.finish_hint_col:
                specs["finish_hint"] = r.finish_hint_col
            tags = [cat_name.lower(), "grohe"]
            if r.finish:
                tags.append(r.finish.lower())
            if r.segment:
                tags.append(r.segment.lower())

            payload = dict(
                name=(r.description or "Untitled")[:200],
                sku=r.sku,
                brand_id=brand_id,
                category_id=cat_id,
                family_key=r.family_key,
                family_name=family_name,
                variant_label=r.finish,
                colour=r.finish,
                finish=r.finish,
                description=r.description,
                mrp=r.mrp,
                price=r.mrp,
                specs=specs,
                tags=[t for t in tags if t],
                active=True,
            )
            p = Product(**payload)
            await db.products.insert_one(p.dict())
            imported += 1

            if r.image.ok:
                media_doc = await upload_and_register(
                    data=r.image.data, mime=r.image.mime or "image/jpeg",
                    brand_slug="grohe", product_id=p.id, family_key=r.family_key,
                    brand_id=brand_id, source_type="supplier", role="hero",
                    is_primary=True, sort_order=0,
                    notes=f"source_format={r.image.source_format}",
                )
                if media_doc:
                    images_uploaded += 1
    print(f"Imported {imported} products. Uploaded {images_uploaded} images.")
    report["imported_products"] = imported
    report["images_uploaded"] = images_uploaded

    print("\n" + "=" * 78)
    print("PHASE 7 — POST-MIGRATION VALIDATION")
    print("=" * 78)
    post_scan = await scan_catalog()
    report["post_scan_ok"] = post_scan.ok
    grohe_scoped = [d for d in post_scan.same_brand_duplicate_skus if d.get("brand_id") == brand_id]
    print(f"Post-migration integrity scan: ok={post_scan.ok}  grohe_scoped_dupe_skus={len(grohe_scoped)}")

    products_without_media = 0
    async for p in db.products.find({"brand_id": brand_id}, {"_id": 0, "id": 1}):
        cnt = await db.product_media.count_documents({"product_id": p["id"]})
        if cnt == 0:
            products_without_media += 1
    report["grohe_products_without_image"] = products_without_media
    print(f"Grohe products WITHOUT any image: {products_without_media}")

    report["stopped"] = False
    return report


if __name__ == "__main__":
    dry = "--execute" not in sys.argv
    result = asyncio.run(run(dry_run=dry))
    out_path = Path(__file__).resolve().parent.parent / "backups" / "grohe_unified_reimport_report.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=_json_default), encoding="utf-8")
    print(f"\nFull report written to {out_path}")
