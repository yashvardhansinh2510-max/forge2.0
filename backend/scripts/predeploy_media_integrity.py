"""Read-only, paginated media integrity gate. Never writes or deletes data."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

from db import db  # noqa: E402
from media_storage.factory import get_media_storage  # noqa: E402
from services.catalog_media_integrity import find_media_integrity_issues  # noqa: E402
from services.media_integrity_gate import inspect_media_bytes  # noqa: E402


async def main(page_size: int, delay: float, max_items: int | None) -> int:
    """Downloads each referenced object at a bounded rate and returns nonzero on issues."""
    products = await db.products.find({}, {"_id": 0, "id": 1, "brand_id": 1, "floor_id": 1, "family_key": 1}).to_list(100_000)
    media_rows = []
    offset = 0
    while max_items is None or len(media_rows) < max_items:
        take = min(page_size, max_items - len(media_rows)) if max_items else page_size
        page = await db.product_media.find({}, {"_id": 0}).sort("_id", 1).skip(offset).limit(take).to_list(take)
        if not page:
            break
        media_rows.extend(page)
        offset += len(page)
    issues = find_media_integrity_issues(products, media_rows)
    storage = get_media_storage()
    for index, media in enumerate(media_rows):
        key, bucket = media.get("storage_key"), media.get("bucket")
        if not key or not bucket:
            issues.append({"media_id": media.get("id"), "kind": "missing_storage_reference"})
            continue
        try:
            data = await storage.download(bucket=bucket, key=key)
        except Exception as exc:  # provider error includes missing objects
            issues.append({"media_id": media.get("id"), "kind": "missing_object", "detail": str(exc)[:200]})
            continue
        for issue in inspect_media_bytes(media, data):
            issues.append({"media_id": media.get("id"), **issue})
        if delay and index + 1 < len(media_rows):
            await asyncio.sleep(delay)
    report = {"read_only": True, "scanned": len(media_rows), "page_size": page_size, "issues": issues, "counts": {kind: sum(row.get("kind") == kind for row in issues) for kind in sorted({row.get("kind") for row in issues})}}
    print(json.dumps(report, indent=2, default=str))
    return 1 if issues else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--delay-seconds", type=float, default=0.05)
    parser.add_argument("--max-items", type=int, default=None, help="safe smoke-test cap; omit for full scan")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.page_size, args.delay_seconds, args.max_items)))
