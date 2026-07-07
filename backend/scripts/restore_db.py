"""Persistence & Disaster Recovery — restore from a JSON snapshot produced by
backup_db.py.

Idempotent upsert-by-id: safe to re-run, never duplicates documents. Does NOT
delete anything that exists in the target DB but not in the snapshot (restore
is additive/repair, not a mirror), so it is safe to run against a DB that
already has some data.

Usage:
    python scripts/restore_db.py                       # restore the most recent backup
    python scripts/restore_db.py backups/20260101_0000  # restore a specific snapshot dir
    python scripts/restore_db.py --dry-run              # report counts only, write nothing
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", ROOT / "backups"))


def _resolve_snapshot_dir(arg: str | None) -> Path:
    if arg:
        p = Path(arg)
        if not p.is_absolute():
            p = ROOT / arg
        if not p.exists():
            raise SystemExit(f"Snapshot dir not found: {p}")
        return p
    latest = BACKUP_DIR / "latest.json"
    if not latest.exists():
        raise SystemExit(f"No backups found under {BACKUP_DIR}. Run backup_db.py first.")
    meta = json.loads(latest.read_text())
    return Path(meta["path"])


async def restore(snapshot_dir: Path, dry_run: bool = False) -> None:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    manifest_path = snapshot_dir / "manifest.json"
    collections = []
    if manifest_path.exists():
        collections = list(json.loads(manifest_path.read_text())["collections"].keys())
    else:
        collections = [p.stem for p in snapshot_dir.glob("*.json") if p.stem != "manifest"]

    print(f"Restoring from {snapshot_dir} ({'DRY RUN' if dry_run else 'LIVE'})")
    for name in collections:
        path = snapshot_dir / f"{name}.json"
        if not path.exists():
            continue
        docs = json.loads(path.read_text())
        if dry_run:
            print(f"  {name}: would upsert {len(docs)} docs")
            continue
        upserted = 0
        for doc in docs:
            key = {"id": doc["id"]} if "id" in doc else doc
            await db[name].update_one(key, {"$set": doc}, upsert=True)
            upserted += 1
        print(f"  {name}: upserted {upserted} docs")

    print("\nRestore complete." if not dry_run else "\nDry run complete — nothing written.")
    client.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    dry = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]
    snap = _resolve_snapshot_dir(args[0] if args else None)
    asyncio.run(restore(snap, dry_run=dry))
