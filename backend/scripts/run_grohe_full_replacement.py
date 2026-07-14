"""GROHE Full Catalog Replacement — production migration (2026-08).

Executes the user-approved plan:
  1. Backup the ENTIRE existing Grohe catalog (products, media, categories
     referenced, import jobs) to local JSON + Supabase private bucket.
  2. Pre-migration integrity scan (abort if the catalog is already broken).
  3. Delete ALL existing Grohe products + their product_media docs.
  4. Delete any category that becomes empty (0 products, ANY brand) as a
     direct result of the Grohe removal.
  5. Create the 3 new supplier-filename categories; reuse the existing
     "Single Lever" category (already used by Hansgrohe/AXOR — categories
     are a global cross-brand taxonomy in this schema, confirmed in models.py).
  6. Import the 133 valid rows (145 extracted - 9 in-file duplicates
     collapsed - 3 rows with no supplier-provided price) as new Products,
     uploading every image (100% coverage, real supplier artwork only) to
     Supabase via the existing media_service pipeline.
  7. Post-migration integrity scan — must be clean.
  8. Print the full deliverables report.

Never touches Hansgrohe / AXOR / Geberit / Vitra products, media, or
categories that remain in use by them.

Usage:
    python scripts/run_grohe_full_replacement.py --dry-run   # plan only, no writes
    python scripts/run_grohe_full_replacement.py --execute   # the real migration
"""
from __future__ import annotations

import asyncio
import json
import os
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
from grohe_xlsx_extract import extract_all, GroheRow  # noqa: E402

XLSX_DIR = "/tmp/grohe_analysis"
BACKUP_ROOT = Path(__file__).resolve().parent.parent / "backups"

OLD_GROHE_CATEGORY_NAMES = [
    "Faucets", "Showers", "Accessories", "Kitchen Sinks", "Urinals", "Bathtubs",
]


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


async def dedupe_rows(rows: list[GroheRow]) -> tuple[list[GroheRow], list[dict]]:
    """Collapse in-file duplicate SKUs (same row repeated verbatim across
    multiple kit sections). When two rows for the same SKU carry DIFFERENT
    images, prefer the native raster photo over an EMF-converted technical
    drawing (both are genuine supplier images — this is a quality
    preference between two real options, never a fabrication)."""
    by_sku: dict[str, list[GroheRow]] = defaultdict(list)
    for r in rows:
        by_sku[r.sku].append(r)
    kept: list[GroheRow] = []
    collapsed_log: list[dict] = []
    for sku, group in by_sku.items():
        if len(group) == 1:
            kept.append(group[0])
            continue
        best = sorted(
            group,
            key=lambda r: (0 if (r.image.source_format not in (None,) and "converted" not in (r.image.source_format or "")) else 1),
        )[0]
        kept.append(best)
        collapsed_log.append({
            "sku": sku, "kept_row": best.row_num,
            "collapsed_rows": [r.row_num for r in group if r is not best],
            "descriptions": list({r.description for r in group}),
        })
    return kept, collapsed_log


async def backup_grohe(brand_id: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = BACKUP_ROOT / f"grohe_full_replace_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    products = await db.products.find({"brand_id": brand_id}, {"_id": 0}).to_list(5000)
    media = await db.product_media.find({"brand_id": brand_id}, {"_id": 0}).to_list(5000)
    cat_ids = list({p["category_id"] for p in products if p.get("category_id")})
    categories = await db.categories.find({"id": {"$in": cat_ids}}, {"_id": 0}).to_list(200)
    brand_doc = await db.brands.find_one({"id": brand_id}, {"_id": 0})
    import_jobs = await db.catalog_imports.find(
        {"supplier_name": {"$regex": "grohe", "$options": "i"}}, {"_id": 0}
    ).to_list(200)

    payload = {
        "products.json": products,
        "product_media.json": media,
        "categories.json": categories,
        "brand.json": [brand_doc] if brand_doc else [],
        "catalog_imports.json": import_jobs,
    }
    manifest = {"created_at": ts, "brand": "Grohe", "brand_id": brand_id, "counts": {}}
    for fname, docs in payload.items():
        (out_dir / fname).write_text(json.dumps(docs, default=_json_default, indent=2), encoding="utf-8")
        manifest["counts"][fname] = len(docs)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"  Local backup written: {out_dir}")
    for k, v in manifest["counts"].items():
        print(f"    {k}: {v} docs")

    # Push to Supabase private bucket (survives session resets)
    try:
        from media_storage import get_media_storage
        from media_storage.factory import private_bucket
        storage = get_media_storage()
        bucket = private_bucket()
        for path in out_dir.glob("*.json"):
            data = path.read_bytes()
            key = f"backups/grohe_full_replace_{ts}/{path.name}"
            await storage.upload(bucket=bucket, key=key, data=data, content_type="application/json")
        print(f"  Pushed to Supabase private bucket '{bucket}' at backups/grohe_full_replace_{ts}/")
    except Exception as e:  # noqa: BLE001
        print(f"  ! Supabase backup push failed (local backup still valid): {e}")

    return out_dir


async def run(dry_run: bool) -> dict:
    report: dict = {"dry_run": dry_run}

    print("=" * 78)
    print("PHASE 2 — EXTRACT & VALIDATE 4 SUPPLIER FILES")
    print("=" * 78)
    all_rows = extract_all(XLSX_DIR)
    total_extracted = sum(len(v) for v in all_rows.values())
    print(f"Extracted {total_extracted} raw rows across {len(all_rows)} files.")

    final_rows: dict[str, list[GroheRow]] = {}
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
        final_rows[cat] = priced

    total_final = sum(len(v) for v in final_rows.values())
    total_images_ok = sum(1 for rows in final_rows.values() for r in rows if r.image.ok)
    print(f"After dedupe + price-validation: {total_final} importable products.")
    print(f"Collapsed duplicates: {len(collapsed_all)}  |  Skipped (no price in supplier file): {len(skipped_no_price)}")
    print(f"Image coverage: {total_images_ok}/{total_final}")

    if total_images_ok != total_final:
        print("\n!!! STOP CONDITION TRIGGERED — not every product has a verified image. !!!")
        missing = [(cat, r.sku) for cat, rows in final_rows.items() for r in rows if not r.image.ok]
        for cat, sku in missing:
            print(f"   MISSING IMAGE: [{cat}] {sku}")
        report["stopped"] = True
        report["missing_images"] = missing
        return report

    report["extracted_total"] = total_extracted
    report["final_importable"] = total_final
    report["collapsed_duplicates"] = collapsed_all
    report["skipped_no_price"] = skipped_no_price
    report["per_category_counts"] = {k: len(v) for k, v in final_rows.items()}

    print("\n" + "=" * 78)
    print("PHASE 1 (recap) / PRE-FLIGHT — CURRENT GROHE STATE")
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

    # Quotations referencing soon-to-be-deleted products (informational only —
    # line items snapshot their own sku/name/price/image, never break).
    grohe_ids = {p["id"] async for p in db.products.find({"brand_id": brand_id}, {"_id": 0, "id": 1})}
    affected_quotations = 0
    affected_lines = 0
    async for q in db.quotations.find({}, {"_id": 0, "items": 1}):
        hit = [it for it in q.get("items", []) if it.get("product_id") in grohe_ids]
        if hit:
            affected_quotations += 1
            affected_lines += len(hit)
    report["quotations_with_frozen_grohe_snapshots"] = affected_quotations
    report["quotation_lines_with_frozen_grohe_snapshots"] = affected_lines
    print(f"Historical quotations referencing current Grohe SKUs (snapshot-preserved, unaffected): "
          f"{affected_quotations} quotations / {affected_lines} lines")

    pre_scan = await scan_catalog()
    report["pre_scan_ok"] = pre_scan.ok
    print(f"Pre-migration integrity scan (catalog-wide): ok={pre_scan.ok}  "
          f"same_brand_dupe_skus={len(pre_scan.same_brand_duplicate_skus)}  "
          f"orphaned_media={len(pre_scan.orphaned_media)}")
    # Scope the abort decision to GROHE specifically — a pre-existing issue on
    # another brand (e.g. the already-documented Hansgrohe SKU 26456000
    # duplicate from a prior session's audit, flagged then as "needs human
    # decision, not auto-resolved") must never block or be silently fixed by
    # a Grohe-only migration. "Do NOT touch Hansgrohe" cuts both ways.
    grohe_scoped_issues = {
        "same_brand_duplicate_skus": [d for d in pre_scan.same_brand_duplicate_skus if d.get("brand_id") == brand_id],
        "invalid_brand_refs": [pid for pid in pre_scan.invalid_brand_refs if pid in grohe_ids],
        "invalid_category_refs": [pid for pid in pre_scan.invalid_category_refs if pid in grohe_ids],
        "media_brand_mismatches": [m for m in pre_scan.media_brand_mismatches if m.get("product_brand") == brand_id or m.get("media_brand") == brand_id],
    }
    other_brand_pre_existing_issues = pre_scan.to_public() if not pre_scan.ok else None
    report["pre_existing_non_grohe_issues"] = other_brand_pre_existing_issues
    if any(grohe_scoped_issues.values()):
        print("!!! Grohe-scoped integrity issue found — aborting, nothing touched.")
        print(json.dumps(grohe_scoped_issues, indent=2, default=_json_default))
        report["stopped"] = True
        report["reason"] = "grohe_scoped_pre_scan_failed"
        return report
    if not pre_scan.ok:
        print("  (Pre-existing issue found scopes ONLY to another brand — not this migration's concern, "
              "not fixed, not blocking. Flagging in the final report for visibility.)")

    if dry_run:
        print("\nDRY RUN — no writes performed. Re-run with --execute to apply.")
        report["stopped"] = False
        report["dry_run_only"] = True
        return report

    print("\n" + "=" * 78)
    print("PHASE 1 — BACKUP (Grohe-only, independently restorable)")
    print("=" * 78)
    backup_dir = await backup_grohe(brand_id)
    report["backup_dir"] = str(backup_dir)

    print("\n" + "=" * 78)
    print("PHASE 7 — DELETE EXISTING GROHE CATALOG")
    print("=" * 78)
    del_products = await db.products.delete_many({"brand_id": brand_id})
    del_media = await db.product_media.delete_many({"brand_id": brand_id})
    print(f"Deleted {del_products.deleted_count} Grohe products, {del_media.deleted_count} Grohe media docs.")
    report["deleted_products"] = del_products.deleted_count
    report["deleted_media"] = del_media.deleted_count

    print("\nCategory cleanup — checking the 6 previously-Grohe categories for emptiness...")
    removed_categories = []
    for cat_name in OLD_GROHE_CATEGORY_NAMES:
        cat = await db.categories.find_one({"name": cat_name}, {"_id": 0})
        if not cat:
            continue
        remaining = await db.products.count_documents({"category_id": cat["id"]})
        if remaining == 0:
            await db.categories.delete_one({"id": cat["id"]})
            removed_categories.append(cat_name)
            print(f"  Deleted empty category: {cat_name}")
        else:
            print(f"  Kept category (still in use by {remaining} other-brand products): {cat_name}")
    report["removed_categories"] = removed_categories

    print("\n" + "=" * 78)
    print("PHASE 3 — CATEGORIES (create-or-reuse, filename-derived ONLY)")
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
    print("PHASE 4-6 — IMPORT PRODUCTS + UPLOAD IMAGES")
    print("=" * 78)
    from services.media_service import upload_and_register

    imported = 0
    images_uploaded = 0
    new_product_ids: list[str] = []
    for cat_name, rows in final_rows.items():
        cat_id = category_id_by_name[cat_name]
        for r in rows:
            family_name = r.description.strip().title() if r.description else None
            specs = {
                "sl_no": r.sl,
                "source_file": r.source_file,
                "segment": r.segment,
            }
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
                finish=r.finish,
                description=r.description,
                mrp=r.mrp,
                price=r.mrp,   # no separate dealer/trade price column in these 4 files
                specs=specs,
                tags=[t for t in tags if t],
                active=True,
            )
            p = Product(**payload)
            await db.products.insert_one(p.dict())
            new_product_ids.append(p.id)
            imported += 1

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
    print("PHASE 8 — POST-MIGRATION VALIDATION")
    print("=" * 78)
    post_scan = await scan_catalog()
    report["post_scan"] = post_scan.to_public()
    print(f"Post-migration integrity scan: ok={post_scan.ok}")
    print(f"  same_brand_duplicate_skus={len(post_scan.same_brand_duplicate_skus)}")
    print(f"  invalid_brand_refs={len(post_scan.invalid_brand_refs)}")
    print(f"  invalid_category_refs={len(post_scan.invalid_category_refs)}")
    print(f"  orphaned_media={len(post_scan.orphaned_media)}")
    print(f"  media_brand_mismatches={len(post_scan.media_brand_mismatches)}")
    print(f"  missing_images (catalog-wide)={post_scan.missing_images}")

    # 100% image-coverage proof at the DB level for the NEW Grohe products specifically
    grohe_media_count = await db.product_media.count_documents({"brand_id": brand_id})
    grohe_product_count = await db.products.count_documents({"brand_id": brand_id})
    products_without_media = 0
    async for p in db.products.find({"brand_id": brand_id}, {"_id": 0, "id": 1}):
        cnt = await db.product_media.count_documents({"product_id": p["id"]})
        if cnt == 0:
            products_without_media += 1
    report["new_grohe_products"] = grohe_product_count
    report["new_grohe_media"] = grohe_media_count
    report["grohe_products_without_image"] = products_without_media
    print(f"New Grohe products: {grohe_product_count}  |  media docs: {grohe_media_count}  "
          f"|  products WITHOUT an image: {products_without_media}")

    # Final catalog totals per brand
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
    out_path = Path(__file__).resolve().parent.parent / "backups" / "grohe_migration_report.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=_json_default), encoding="utf-8")
    print(f"\nFull report written to {out_path}")
