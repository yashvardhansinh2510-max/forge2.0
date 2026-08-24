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
from io import BytesIO
from pathlib import Path

import httpx
from dotenv import load_dotenv
from PIL import Image, ImageOps, UnidentifiedImageError

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
    # New images are exactly 16:10. Permit a tiny rounding tolerance for old
    # lossless encoder metadata, but do not treat an arbitrary wide image as
    # canonical just because it happens to be horizontal.
    return bool(
        width and height and doc.get("mime") != "image/gif"
        and abs((width / height) - PRODUCT_IMAGE_ASPECT_RATIO) < 0.01
    )


def _stored_bytes_are_landscape(data: bytes) -> bool:
    """Verify the actual uploaded raster, not just its cached metadata.

    An EXIF orientation tag is deliberately not accepted: the canonical asset
    must be physically upright so browser, PDF, and catalog renderers agree.
    """
    try:
        with Image.open(BytesIO(data)) as opened:
            raw_size = opened.size
            upright = ImageOps.exif_transpose(opened)
            upright.load()
            return (
                upright.size == raw_size
                and abs((upright.width / upright.height) - PRODUCT_IMAGE_ASPECT_RATIO) < 0.01
            )
    except (UnidentifiedImageError, OSError, ValueError):
        return False


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


async def _backfill_media_doc(doc: dict, *, dry_run: bool, verify_storage: bool, report: dict) -> None:
    if doc.get("mime") not in NORMALIZABLE_IMAGE_MIMES:
        report["skipped_non_image"] += 1
        return
    if _is_landscape_media(doc) and not verify_storage:
        report["already_landscape"] += 1
        return
    storage = get_media_storage()
    raw = await storage.download(bucket=doc["bucket"], key=doc["storage_key"])
    if _stored_bytes_are_landscape(raw):
        report["verified_storage"] += 1
        if not _is_landscape_media(doc) and not dry_run:
            width, height, quality = _detect_dims_and_quality(raw, doc["mime"])
            await db.product_media.update_one({"id": doc["id"]}, {"$set": {
                "width": width, "height": height, "quality": quality, "size_bytes": len(raw),
            }})
            report["metadata_corrected"] += 1
        return
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


async def _run_bounded(
    records: list[dict], worker, *, workers: int, report: dict, kind: str,
) -> None:
    """Process independent storage records concurrently with bounded pressure.

    A successful update writes horizontal normalized dimensions to Mongo, so
    re-running this job naturally resumes after a deploy, interruption, or
    one failed object. Nothing relies on an in-memory checkpoint.
    """
    gate = asyncio.Semaphore(workers)

    async def process(record: dict) -> None:
        async with gate:
            try:
                await worker(record)
            except Exception as exc:  # complete the rest and retain a repair list
                report["failed"].append({f"{kind}_id": record.get("id"), "reason": str(exc)})

    tasks = [asyncio.create_task(process(record)) for record in records]
    for index, task in enumerate(asyncio.as_completed(tasks), 1):
        await task
        if index % 100 == 0 or index == len(records):
            log.info("%s progress: %d/%d", kind, index, len(records))


async def run(*, dry_run: bool, workers: int = 8, verify_storage: bool = False) -> dict:
    if workers < 1:
        raise ValueError("workers must be at least 1")
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "dry_run": dry_run, "replaced": 0,
              "would_replace": 0, "already_landscape": 0, "skipped_non_image": 0, "migrated_legacy": 0,
              "would_migrate_legacy": 0, "legacy_already_migrated": 0, "legacy_failed": [], "failed": [],
              "retained_originals": [], "workers": workers, "scanned_media": 0, "candidate_media": 0,
              "scanned_legacy_products": 0, "verify_storage": verify_storage, "verified_storage": 0,
              "metadata_corrected": 0}
    media_docs = await db.product_media.find({}, {"_id": 0}).to_list(50_000)
    report["scanned_media"] = len(media_docs)
    candidates: list[dict] = []
    for doc in media_docs:
        if doc.get("mime") not in NORMALIZABLE_IMAGE_MIMES:
            report["skipped_non_image"] += 1
        elif verify_storage or not _is_landscape_media(doc):
            candidates.append(doc)
        else:
            report["already_landscape"] += 1
    report["candidate_media"] = len(candidates)
    await _run_bounded(
        candidates,
        lambda doc: _backfill_media_doc(doc, dry_run=dry_run, verify_storage=verify_storage, report=report),
        workers=workers, report=report, kind="media",
    )

    legacy_products = await db.products.find({"images": {"$ne": []}}, {"_id": 0}).to_list(50_000)
    report["scanned_legacy_products"] = len(legacy_products)
    await _run_bounded(
        legacy_products,
        lambda product: _backfill_legacy_product(product, dry_run=dry_run, report=report),
        workers=workers, report=report, kind="product",
    )
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=8, help="Bounded concurrent storage operations (default: 8)")
    parser.add_argument("--verify-storage", action="store_true", help="Decode every stored image before accepting its landscape metadata")
    args = parser.parse_args()
    report = await run(dry_run=args.dry_run, workers=args.workers, verify_storage=args.verify_storage)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
