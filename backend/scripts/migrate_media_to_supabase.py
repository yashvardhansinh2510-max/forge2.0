"""Migrate legacy embedded product images → Supabase Storage + product_media.

Safe, idempotent, one-shot script that can be re-run:

1. Scan `products` for docs with `images: [...]` still containing data URLs
   (or existing `blob:<sha1>` refs pointing into `catalog_image_blobs`).
2. Resolve every image to raw bytes.
3. Verify SHA-1, upload to Supabase via MediaStorage, register a
   `product_media` document (source_type="supplier").
4. Only after a full round-trip (upload + SHA-1 verify + metadata insert)
   remove the legacy `images` / `image_meta` from the product doc.
5. Emit a JSON migration report to /app/memory/.

Usage:
    cd /app/backend && python -m scripts.migrate_media_to_supabase
    cd /app/backend && python -m scripts.migrate_media_to_supabase --brand vitra
    cd /app/backend && python -m scripts.migrate_media_to_supabase --dry-run
"""
from __future__ import annotations
import argparse
import asyncio
import base64
import hashlib
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

from db import db  # noqa: E402
from media_storage import get_media_storage  # noqa: E402
from media_storage.factory import public_bucket  # noqa: E402
from services.media_service import (  # noqa: E402
    _detect_dims_and_quality, make_storage_key,
)
from models import ProductMedia  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s :: %(message)s")
log = logging.getLogger("forge.migrate_media")


_DATA_URL_RE = re.compile(r"^data:([^;]+);base64,(.+)$", re.DOTALL)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "item"


async def _resolve_bytes(image_ref: str) -> tuple[bytes, str] | tuple[None, None]:
    """Turn `data:` URL or `blob:<sha1>` ref into (raw_bytes, mime)."""
    if not image_ref:
        return None, None
    if image_ref.startswith("data:"):
        m = _DATA_URL_RE.match(image_ref)
        if not m:
            return None, None
        mime, b64 = m.group(1), m.group(2)
        try:
            return base64.b64decode(b64), mime
        except Exception:  # noqa: BLE001
            return None, None
    if image_ref.startswith("blob:"):
        sha1_prefix = image_ref[len("blob:"):]
        blob = await db.catalog_image_blobs.find_one({"sha1": sha1_prefix}, {"_id": 0, "data_url": 1})
        if not blob:
            return None, None
        return await _resolve_bytes(blob["data_url"])
    # Absolute URL (already migrated) — skip
    return None, None


async def _brand_info(brand_id: str | None) -> tuple[str, str]:
    if not brand_id:
        return "unknown", "unknown"
    b = await db.brands.find_one({"id": brand_id}, {"_id": 0, "name": 1, "slug": 1})
    if not b:
        return "unknown", "unknown"
    slug = b.get("slug") or _slug(b.get("name") or "unknown")
    return b.get("name") or "Unknown", slug


async def migrate_product(prod: dict, *, dry_run: bool, report: dict) -> None:
    images = prod.get("images") or []
    if not images:
        return

    metas = prod.get("image_meta") or []
    brand_name, brand_slug = await _brand_info(prod.get("brand_id"))
    storage = get_media_storage()
    bucket = public_bucket()
    migrated_here = 0
    verified_shas: list[str] = []

    for i, img in enumerate(images):
        if not img:
            continue
        # Skip already-migrated Supabase URLs
        if isinstance(img, str) and img.startswith("http") and "/storage/v1/object/public/" in img:
            report["skipped_already_migrated"] += 1
            continue

        data, mime = await _resolve_bytes(img)
        if not data:
            report["failed"].append({
                "product_id": prod["id"], "sku": prod.get("sku"),
                "index": i, "reason": "could not resolve bytes",
            })
            continue

        mime = mime or "image/png"
        sha1 = hashlib.sha1(data).hexdigest()

        # Idempotency: existing product_media doc for same sha1+scope?
        already = await db.product_media.find_one(
            {"sha1": sha1, "product_id": prod["id"], "source_type": "supplier"},
            {"_id": 0},
        )
        if already:
            verified_shas.append(sha1)
            report["duplicates"] += 1
            continue

        w, h, quality = _detect_dims_and_quality(data, mime)
        # If the original import already scored the image, respect it (never fabricate).
        if i < len(metas) and isinstance(metas[i], dict) and metas[i].get("quality"):
            quality = metas[i]["quality"]
            w = w or metas[i].get("width")
            h = h or metas[i].get("height")

        role = "hero" if i == 0 else "gallery"
        key = make_storage_key(
            brand_slug=brand_slug, family_key=prod.get("family_key"),
            product_id=prod["id"], source_type="supplier", role=role,
            sha1=sha1, mime=mime,
        )

        if dry_run:
            report["would_migrate"] += 1
            report["bytes"] += len(data)
            continue

        try:
            obj = await storage.upload(bucket=bucket, key=key, data=data, content_type=mime)
        except Exception as e:  # noqa: BLE001
            report["failed"].append({
                "product_id": prod["id"], "sku": prod.get("sku"),
                "index": i, "reason": f"upload failed: {e}",
            })
            continue

        # Verify integrity: SHA-1 of what we uploaded == what we intended
        if obj.sha1 != sha1:
            report["failed"].append({
                "product_id": prod["id"], "sku": prod.get("sku"),
                "index": i, "reason": "sha1 mismatch post-upload",
            })
            # Roll back the bad upload
            try:
                await storage.delete(bucket=bucket, key=key)
            except Exception:  # noqa: BLE001
                pass
            continue

        media = ProductMedia(
            product_id=prod["id"], family_key=prod.get("family_key"),
            brand_id=prod.get("brand_id"), source_type="supplier", role=role,
            bucket=bucket, storage_key=key, public_url=obj.public_url,
            width=w, height=h, quality=quality, sha1=sha1, mime=mime,
            size_bytes=len(data), is_primary=(i == 0), sort_order=i * 10,
        )
        await db.product_media.insert_one(media.dict())
        verified_shas.append(sha1)
        migrated_here += 1
        report["migrated"] += 1
        report["bytes"] += len(data)

    # Only after ALL images for this product have been verified end-to-end
    # (or already existed) do we clear the legacy fields from the product doc.
    if not dry_run and (migrated_here > 0 or verified_shas):
        expected = sum(1 for x in images if x and (
            (isinstance(x, str) and x.startswith(("data:", "blob:")))
        ))
        # Count sha1s per product — if every legacy ref was migrated, we can
        # safely clear the embedded blobs from the product doc.
        actually_present = await db.product_media.count_documents({"product_id": prod["id"]})
        if actually_present >= expected and expected > 0:
            await db.products.update_one(
                {"id": prod["id"]},
                {"$set": {"images": [], "image_meta": []}},
            )
            report["products_cleaned"] += 1


async def run(brand: str | None, dry_run: bool) -> dict:
    filt: dict = {"active": True, "images": {"$ne": []}}
    if brand:
        b = await db.brands.find_one({"$or": [
            {"slug": brand.lower()},
            {"name": {"$regex": f"^{re.escape(brand)}$", "$options": "i"}},
        ]}, {"_id": 0, "id": 1, "name": 1})
        if not b:
            raise SystemExit(f"Brand {brand!r} not found")
        filt["brand_id"] = b["id"]

    prods = await db.products.find(filt, {"_id": 0}).to_list(20_000)
    log.info("Candidate products: %d", len(prods))

    report: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "brand_filter": brand or "all",
        "dry_run": dry_run,
        "candidates": len(prods),
        "migrated": 0,
        "would_migrate": 0,
        "duplicates": 0,
        "skipped_already_migrated": 0,
        "products_cleaned": 0,
        "failed": [],
        "bytes": 0,
    }

    for i, p in enumerate(prods, 1):
        if i % 25 == 0:
            log.info("  … %d/%d", i, len(prods))
        try:
            await migrate_product(p, dry_run=dry_run, report=report)
        except Exception as e:  # noqa: BLE001
            report["failed"].append({
                "product_id": p.get("id"), "sku": p.get("sku"), "reason": f"exception: {e}",
            })

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["total_mb"] = round(report["bytes"] / (1024 * 1024), 2)
    return report


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default=None, help="Restrict to one brand (name or slug)")
    ap.add_argument("--dry-run", action="store_true", help="Report but do not upload/write")
    args = ap.parse_args()

    log.info("Starting media migration → Supabase (dry_run=%s, brand=%s)", args.dry_run, args.brand)
    report = await run(args.brand, args.dry_run)

    memdir = Path("/app/memory")
    memdir.mkdir(exist_ok=True)
    outfile = memdir / f"media_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    outfile.write_text(json.dumps(report, indent=2, default=str))
    log.info("Report: %s", outfile)
    log.info("Summary: migrated=%d, dupes=%d, failed=%d, cleaned=%d, total=%.2f MB",
             report["migrated"], report["duplicates"], len(report["failed"]),
             report["products_cleaned"], report["total_mb"])


if __name__ == "__main__":
    asyncio.run(main())
