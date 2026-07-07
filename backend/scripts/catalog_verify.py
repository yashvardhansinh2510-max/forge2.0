"""catalog:verify - reusable integrity command.

Run this:
  * before every deployment
  * after every catalog import batch
  * any time you suspect the catalog

Usage:
    python scripts/catalog_verify.py                          # scan only, no baseline
    python scripts/catalog_verify.py backups/20260707_031204   # also diff vs a baseline snapshot

Exit code 0 = clean. Exit code 1 = integrity failure (see report for detail).
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from catalog_pipeline.integrity_guard import scan_catalog  # noqa: E402


async def main() -> int:
    baseline = sys.argv[1] if len(sys.argv) > 1 else None
    report = await scan_catalog(baseline)
    public = report.to_public()

    print("=" * 70)
    print("CATALOG INTEGRITY REPORT")
    print("=" * 70)
    print(f"products={public['total_products']}  media={public['total_media']}  "
          f"brands={public['total_brands']}  categories={public['total_categories']}")
    print(f"same_brand_duplicate_skus (HARD FAIL): {len(public['same_brand_duplicate_skus'])}")
    print(f"cross_brand_sku_collisions (informational): {len(public['cross_brand_sku_collisions'])}")
    print(f"invalid_brand_refs (HARD FAIL): {len(public['invalid_brand_refs'])}")
    print(f"invalid_category_refs (HARD FAIL): {len(public['invalid_category_refs'])}")
    print(f"orphaned_media (HARD FAIL): {len(public['orphaned_media'])}")
    print(f"media_brand_mismatches (HARD FAIL): {len(public['media_brand_mismatches'])}")
    print(f"missing_images (informational): {public['missing_images']}")
    if baseline:
        print(f"unexpected_modifications vs {baseline} (HARD FAIL): {len(public['unexpected_modifications'])}")
        for m in public["unexpected_modifications"][:20]:
            print(f"    {m}")

    print()
    print("RESULT:", "PASS (clean)" if public["ok"] else "FAIL (see above)")

    Path("/app/memory/catalog_verify_latest.json").write_text(json.dumps(public, indent=2), encoding="utf-8")
    return 0 if public["ok"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
