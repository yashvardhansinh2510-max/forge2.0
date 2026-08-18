"""Restore verified product-media pointers from a private Supabase DB snapshot.

This repairs only existing media rows whose IDs occur in the snapshot.  It
never uploads, deletes, or substitutes an image.  Each restored pointer is
checked against the snapshot SHA-1 and recorded in ``media_repair_audits``.

Usage:
  python scripts/restore_media_from_snapshot.py 20260815_082216
  python scripts/restore_media_from_snapshot.py 20260815_082216 --apply
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
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
from services.catalog_service import schedule_catalog_refresh  # noqa: E402
from services.media_snapshot_recovery import plan_snapshot_media_restore  # noqa: E402
from settings import settings  # noqa: E402


async def load_snapshot(snapshot: str) -> list[dict]:
    bucket = settings.supabase_private_bucket
    url = f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{bucket}/backups/{snapshot}/product_media.json"
    headers = {"apikey": settings.supabase_service_role_key, "Authorization": f"Bearer {settings.supabase_service_role_key}"}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        raise ValueError("snapshot product_media.json is not a list")
    return rows


async def verify_source(item: dict) -> str | None:
    """Return a rejection reason, or None when exact snapshot bytes exist."""
    expected = item["after"].get("sha1")
    if not expected:
        return "snapshot has no SHA-1"
    try:
        raw = await get_media_storage().download(bucket=item["after"]["bucket"], key=item["after"]["storage_key"])
    except Exception as exc:  # report inaccessible source; do not guess
        return f"source unavailable: {type(exc).__name__}"
    actual = hashlib.sha1(raw).hexdigest()
    return None if actual == expected else "source checksum differs from snapshot"


async def main(snapshot: str, apply: bool, verify: bool) -> None:
    snapshot_rows, current_rows = await asyncio.gather(
        load_snapshot(snapshot),
        db.product_media.find({}, {"_id": 0}).to_list(100_000),
    )
    plan = plan_snapshot_media_restore(current_rows, snapshot_rows)
    verified, rejected = plan, []
    if verify or apply:
        semaphore = asyncio.Semaphore(16)
        async def checked(item: dict) -> tuple[dict, str | None]:
            async with semaphore:
                return item, await verify_source(item)
        checked_plan = await asyncio.gather(*(checked(item) for item in plan))
        verified = [item for item, reason in checked_plan if reason is None]
        rejected = [{"media_id": item["media_id"], "reason": reason} for item, reason in checked_plan if reason]
    report = {"snapshot": snapshot, "current_media": len(current_rows), "candidates": len(plan), "verified": len(verified) if (verify or apply) else None, "rejected": rejected, "applied": 0}
    if apply:
        now = datetime.now(timezone.utc).isoformat()
        for item in verified:
            audit = {"media_id": item["media_id"], "before": item["before"], "after": item["after"], "snapshot": snapshot, "reason": "restore verified pre-stretch media pointer", "created_at": now, "actor": "catalog-media-snapshot-recovery", "rollback": item["before"]}
            await db.product_media.update_one({"id": item["media_id"]}, {"$set": item["after"]})
            await db.media_repair_audits.insert_one(audit)
        report["applied"] = len(verified)
        if verified:
            schedule_catalog_refresh()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", help="private backup timestamp, e.g. 20260815_082216")
    parser.add_argument("--apply", action="store_true", help="write only checksum-verified pointer restores")
    parser.add_argument("--verify", action="store_true", help="download and checksum every recovery source during dry run")
    args = parser.parse_args()
    asyncio.run(main(args.snapshot, args.apply, args.verify))
