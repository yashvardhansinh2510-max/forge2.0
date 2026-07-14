"""GROHE Catalog ADDITIVE Batch 2 (2026-08) — 5 more supplier files.

Same pipeline/rules as run_grohe_full_replacement.py, but ADDITIVE (this
batch does NOT delete or replace anything from batch 1 — it only adds new
categories/products). Files: Bau Line, Body Jet, Handshower, Kitchen Tap,
Short Body Basin Mixer.

Conflict policy (never guess):
  - If the SAME SKU appears in two DIFFERENT files of this batch under two
    different category names, that product cannot be assigned to exactly
    one supplier-defined category with confidence -> EXCLUDE both, report.
  - If a SKU in this batch already exists in the Grohe catalog (from batch
    1, under a different category) -> EXCLUDE, report. Never silently
    re-categorize or duplicate an existing product.
  - Rows with no price in the supplier file -> EXCLUDE, report (never
    fabricate a price).

Usage:
    python scripts/run_grohe_batch2_additive.py --dry-run
    python scripts/run_grohe_batch2_additive.py --execute
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
from grohe_xlsx_extract import extract_all, FILES_BATCH2, ORIGINAL_FILENAMES_BATCH2, GroheRow  # noqa: E402
from run_grohe_full_replacement import dedupe_rows, backup_grohe, _json_default  # noqa: E402

XLSX_DIR = "/tmp/grohe_analysis"
BACKUP_ROOT = Path(__file__).resolve().parent.parent / "backups"


async def run(dry_run: bool) -> dict:
    report: dict = {"dry_run": dry_run}

    print("=" * 78)
    print("BATCH 2 — EXTRACT & VALIDATE 5 SUPPLIER FILES")
    print("=" * 78)
    all_rows = extract_all(XLSX_DIR, FILES_BATCH2, ORIGINAL_FILENAMES_BATCH2)
    total_extracted = sum(len(v) for v in all_rows.values())
    print(f"Extracted {total_extracted} raw rows across {len(all_rows)} files.")

    brand_doc = await db.brands.find_one({"name": {"$regex": "^grohe$", "$options": "i"}}, {"_id": 0})
    brand_id = brand_doc["id"]
    existing_products = {p["sku"]: p async for p in db.products.find({"brand_id": brand_id}, {"_id": 0})}
    print(f"Existing Grohe products (batch 1, untouched by this run): {len(existing_products)}")

    # Phase A: within-file dedupe + no-price exclusion
    deduped_rows: dict[str, list[GroheRow]] = {}
    collapsed_all = []
    skipped_no_price = []
    for cat, rows in all_rows.items():
        deduped, collapsed_log = await dedupe_rows(rows)
        collapsed_all.extend([{**c, "category": cat} for c in collapsed_log])
        priced = []
        for r in deduped:
            if r.mrp is None:
                skipped_no_price.append({"category": cat, "sku": r.sku, "description": r.description})
                continue
            priced.append(r)
        deduped_rows[cat] = priced

    # Phase B: cross-file (within this batch) SKU conflicts — never guess which category wins
    sku_to_cats: dict[str, set[str]] = defaultdict(set)
    for cat, rows in deduped_rows.items():
        for r in rows:
            sku_to_cats[r.sku].add(cat)
    cross_file_conflicts = {sku: cats for sku, cats in sku_to_cats.items() if len(cats) > 1}

    # Phase C: conflicts against the ALREADY-IMPORTED batch-1 Grohe catalog
    existing_conflicts = []
    for cat, rows in deduped_rows.items():
        for r in rows:
            if r.sku in existing_products:
                existing_conflicts.append({
                    "sku": r.sku, "new_category": cat, "new_description": r.description,
                    "existing_name": existing_products[r.sku]["name"],
                    "existing_category_id": existing_products[r.sku].get("category_id"),
                })

    excluded_skus = set(cross_file_conflicts.keys()) | {c["sku"] for c in existing_conflicts}

    final_rows: dict[str, list[GroheRow]] = {}
    for cat, rows in deduped_rows.items():
        final_rows[cat] = [r for r in rows if r.sku not in excluded_skus]

    total_final = sum(len(v) for v in final_rows.values())
    total_images_ok = sum(1 for rows in final_rows.values() for r in rows if r.image.ok)
    print(f"After dedupe + price-validation + conflict-exclusion: {total_final} importable products.")
    print(f"Collapsed in-file duplicates: {len(collapsed_all)}")
    print(f"Skipped (no price in supplier file): {len(skipped_no_price)}")
    print(f"Cross-file category conflicts (excluded, need your decision): {len(cross_file_conflicts)} -> {cross_file_conflicts}")
    print(f"Conflicts with already-imported batch-1 products (excluded, need your decision): {len(existing_conflicts)}")
    for c in existing_conflicts:
        print(f"   {c}")
    print(f"Image coverage on final importable set: {total_images_ok}/{total_final}")

    if total_images_ok != total_final:
        print("\n!!! STOP CONDITION TRIGGERED — not every product has a verified image. !!!")
        missing = [(cat, r.sku) for cat, rows in final_rows.items() for r in rows if not r.image.ok]
        for cat, sku in missing:
            print(f"   MISSING IMAGE: [{cat}] {sku}")
        report["stopped"] = True
        report["missing_images"] = missing
        return report

    report.update({
        "extracted_total": total_extracted,
        "final_importable": total_final,
        "collapsed_duplicates": collapsed_all,
        "skipped_no_price": skipped_no_price,
        "cross_file_conflicts": cross_file_conflicts,
        "existing_catalog_conflicts": existing_conflicts,
        "per_category_counts": {k: len(v) for k, v in final_rows.items()},
    })

    pre_scan = await scan_catalog()
    grohe_ids = {p["id"] for p in existing_products.values()}
    grohe_scoped_issues = {
        "same_brand_duplicate_skus": [d for d in pre_scan.same_brand_duplicate_skus if d.get("brand_id") == brand_id],
        "invalid_brand_refs": [pid for pid in pre_scan.invalid_brand_refs if pid in grohe_ids],
        "invalid_category_refs": [pid for pid in pre_scan.invalid_category_refs if pid in grohe_ids],
    }
    if any(grohe_scoped_issues.values()):
        print("!!! Grohe-scoped integrity issue found — aborting, nothing touched.")
        print(json.dumps(grohe_scoped_issues, indent=2, default=_json_default))
        report["stopped"] = True
        report["reason"] = "grohe_scoped_pre_scan_failed"
        return report
    print(f"Pre-migration integrity scan: catalog-wide ok={pre_scan.ok} (Grohe-scoped issues: none)")

    if dry_run:
        print("\nDRY RUN — no writes performed. Re-run with --execute to apply.")
        report["stopped"] = False
        report["dry_run_only"] = True
        return report

    print("\n" + "=" * 78)
    print("BACKUP (Grohe-only snapshot BEFORE adding batch 2)")
    print("=" * 78)
    backup_dir = await backup_grohe(brand_id)
    report["backup_dir"] = str(backup_dir)

    print("\n" + "=" * 78)
    print("CATEGORIES (create-or-reuse, filename-derived ONLY)")
    print("=" * 78)
    category_id_by_name: dict[str, str] = {}
    created_categories = []
    for cat_name in final_rows.keys():
        existing = await db.categories.find_one({"name": cat_name}, {"_id": 0})
        if existing:
            category_id_by_name[cat_name] = existing["id"]
            print(f"  Reusing existing category '{cat_name}' (id={existing['id']})")
        else:
            slug = cat_name.lower().replace(" ", "-")
            c = Category(name=cat_name, slug=slug)
            await db.categories.insert_one(c.dict())
            category_id_by_name[cat_name] = c.id
            created_categories.append(cat_name)
            print(f"  Created new category '{cat_name}' (id={c.id})")
    report["created_categories"] = created_categories

    print("\n" + "=" * 78)
    print("IMPORT PRODUCTS + UPLOAD IMAGES")
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

            p = Product(
                name=(r.description or "Untitled")[:200], sku=r.sku, brand_id=brand_id,
                category_id=cat_id, family_key=r.family_key, family_name=family_name,
                variant_label=r.finish, finish=r.finish, description=r.description,
                mrp=r.mrp, price=r.mrp, specs=specs, tags=[t for t in tags if t], active=True,
            )
            await db.products.insert_one(p.dict())
            imported += 1

            media_doc = await upload_and_register(
                data=r.image.data, mime=r.image.mime or "image/jpeg",
                brand_slug="grohe", product_id=p.id, family_key=r.family_key,
                brand_id=brand_id, source_type="supplier", role="hero",
                is_primary=True, sort_order=0, notes=f"source_format={r.image.source_format}",
            )
            if media_doc:
                images_uploaded += 1
    print(f"Imported {imported} products. Uploaded {images_uploaded} images.")
    report["imported_products"] = imported
    report["images_uploaded"] = images_uploaded

    print("\n" + "=" * 78)
    print("POST-MIGRATION VALIDATION")
    print("=" * 78)
    post_scan = await scan_catalog()
    report["post_scan"] = post_scan.to_public()
    grohe_product_count = await db.products.count_documents({"brand_id": brand_id})
    grohe_media_count = await db.product_media.count_documents({"brand_id": brand_id})
    products_without_media = 0
    async for p in db.products.find({"brand_id": brand_id}, {"_id": 0, "id": 1}):
        cnt = await db.product_media.count_documents({"product_id": p["id"]})
        if cnt == 0:
            products_without_media += 1
    report["new_grohe_total"] = grohe_product_count
    report["new_grohe_media_total"] = grohe_media_count
    report["grohe_products_without_image"] = products_without_media
    print(f"Grohe total now: {grohe_product_count}  |  media docs: {grohe_media_count}  "
          f"|  products WITHOUT an image: {products_without_media}")

    brands = await db.brands.find({}, {"_id": 0}).to_list(20)
    totals = {}
    grand_total = 0
    for b in brands:
        c = await db.products.count_documents({"brand_id": b["id"]})
        totals[b["name"]] = c
        grand_total += c
    totals["TOTAL"] = grand_total
    report["final_catalog_totals"] = totals
    print(f"Final catalog totals: {json.dumps(totals, indent=2)}")

    report["stopped"] = False
    return report


if __name__ == "__main__":
    dry = "--execute" not in sys.argv
    result = asyncio.run(run(dry_run=dry))
    out_path = BACKUP_ROOT / "grohe_batch2_report.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=_json_default), encoding="utf-8")
    print(f"\nFull report written to {out_path}")
