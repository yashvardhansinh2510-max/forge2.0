"""Backfill product imagery to the canonical 16:10 no-crop landscape format.

Run ``python -m scripts.backfill_landscape_product_media --dry-run`` first.
The script is idempotent and intentionally retains replaced storage objects;
the JSON report is the audit trail for a separately approved cleanup.
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

import httpx
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

from db import db  # noqa: E402
from media_storage import get_media_storage  # noqa: E402
from services.media_service import _detect_dims_and_quality, make_storage_key, upload_and_register  # noqa: E402
from services.product_image_normalizer import NORMALIZABLE_IMAGE_MIMES, PRODUCT_IMAGE_ASPECT_RATIO, normalize_product_image  # noqa: E402

log = logging.getLogger("forge.backfill_landscape_media")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s :: %(message)s")
_DATA_URL_RE = re.compile(r"^data:([^;]+);base64,(.+)$", re.DOTALL)


def _is_landscape_media(doc: dict) -> bool:
    width, height = doc.get("width"), doc.get("height")
    return bool(width and height and abs((float(width) / float(height)) - PRODUCT_IMAGE_ASPECT_RATIO) < 0.001 and doc.get("mime") != "image/gif")


async def _legacy_bytes(ref: str) -> tuple[bytes | None, str | None]:
    if ref.startswith("data:"):
        match = _DATA_URL_RE.match(ref)
        if not match:
            return None, None
        return base64.b64decode(match.group(2)), match.group(1)
    if ref.startswith("blob:"):
        blob = await db.catalog_image_blobs.find_one({"sha1": ref[5:]}, {"_id": 0, "data_url": 1})
        return await _legacy_bytes((blob or {}).get("data_url") or "")
    if ref.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(ref)
            response.raise_for_status()
        return response.content, response.headers.get("content-type", "").split(";", 1)[0].lower()
    return None, None


async def _backfill_media_doc(doc: dict, *, dry_run: bool, report: dict) -> None:
    if doc.get("mime") not in NORMALIZABLE_IMAGE_MIMES:
        report["skipped_non_image"] += 1
        return
    if _is_landscape_media(doc):
        report["already_landscape"] += 1
        return
    storage = get_media_storage()
    raw = await storage.download(bucket=doc["bucket"], key=doc["storage_key"])
    data, mime = normalize_product_image(raw, doc["mime"])
    sha1 = hashlib.sha1(data).hexdigest()
    width, height, quality = _detect_dims_and_quality(data, mime)
    key = make_storage_key(
        brand_slug=(doc.get("brand_id") or "unknown"), family_key=doc.get("family_key"),
        product_id=doc.get("product_id"), source_type=doc.get("source_type", "supplier"),
        role=doc.get("role", "gallery"), sha1=sha1, mime=mime,
    )
    if dry_run:
        report["would_replace"] += 1
        return
    obj = await storage.upload(bucket=doc["bucket"], key=key, data=data, content_type=mime)
    await db.product_media.update_one({"id": doc["id"]}, {"$set": {
        "storage_key": obj.key, "public_url": obj.public_url, "width": width, "height": height,
        "quality": quality, "sha1": sha1, "mime": mime, "size_bytes": len(data),
    }})
    report["replaced"] += 1
    report["retained_originals"].append({"media_id": doc["id"], "bucket": doc["bucket"], "storage_key": doc["storage_key"]})


async def _backfill_legacy_product(product: dict, *, dry_run: bool, report: dict) -> None:
    for index, ref in enumerate(product.get("images") or []):
        if not isinstance(ref, str) or not ref:
            continue
        raw, mime = await _legacy_bytes(ref)
        if not raw or mime not in NORMALIZABLE_IMAGE_MIMES:
            report["legacy_failed"].append({"product_id": product.get("id"), "index": index, "reason": "unreadable or non-image"})
            continue
        normalized, normalized_mime = normalize_product_image(raw, mime)
        sha1 = hashlib.sha1(normalized).hexdigest()
        existing = await db.product_media.find_one({"product_id": product["id"], "sha1": sha1}, {"_id": 0, "id": 1})
        if existing:
            report["legacy_already_migrated"] += 1
            continue
        if dry_run:
            report["would_migrate_legacy"] += 1
            continue
        # Service normalizes again defensively; this remains idempotent by hash.
        await upload_and_register(
            data=raw, mime=mime, brand_slug=product.get("brand_id") or "unknown", product_id=product["id"],
            family_key=product.get("family_key"), brand_id=product.get("brand_id"), floor_id=product.get("floor_id", "first-floor"),
            source_type="supplier", role="hero" if index == 0 else "gallery", is_primary=index == 0,
            sort_order=index * 10,
        )
        report["migrated_legacy"] += 1


async def run(*, dry_run: bool) -> dict:
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "dry_run": dry_run, "replaced": 0,
              "would_replace": 0, "already_landscape": 0, "skipped_non_image": 0, "migrated_legacy": 0,
              "would_migrate_legacy": 0, "legacy_already_migrated": 0, "legacy_failed": [], "failed": [], "retained_originals": []}
    async for doc in db.product_media.find({}, {"_id": 0}):
        try:
            await _backfill_media_doc(doc, dry_run=dry_run, report=report)
        except Exception as exc:  # keep other products moving and report the exact failed record
            report["failed"].append({"media_id": doc.get("id"), "reason": str(exc)})
    async for product in db.products.find({"images": {"$ne": []}}, {"_id": 0}):
        try:
            await _backfill_legacy_product(product, dry_run=dry_run, report=report)
        except Exception as exc:
            report["failed"].append({"product_id": product.get("id"), "reason": str(exc)})
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = await run(dry_run=args.dry_run)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
