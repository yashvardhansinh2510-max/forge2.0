"""Persistence & Disaster Recovery — JSON snapshot backup.

Dumps the core collections to timestamped JSON files so a lost database can be
restored in minutes instead of re-importing supplier PDFs/Excels from scratch.

NOTE: this writes to backend/backups/ on local disk, which is itself ephemeral
in this container. Once MongoDB Atlas + Supabase are wired in, point
BACKUP_DIR at a mounted/synced location (or extend this script to also push
the produced .json files into a private Supabase bucket) so the backup
survives a session reset too.

Usage:
    python scripts/backup_db.py                 # backup everything
    python scripts/backup_db.py products customers   # backup only these collections
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULT_COLLECTIONS = [
    "products", "brands", "categories", "customers", "quotations",
    "purchase_orders", "payments", "followups", "users", "activity",
]

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", ROOT / "backups"))


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


async def backup(collections: list[str]) -> Path:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = BACKUP_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"created_at": ts, "mongo_db": db_name, "collections": {}}
    for name in collections:
        docs = await db[name].find({}, {"_id": 0}).to_list(200000)
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(docs, default=_json_default, indent=2), encoding="utf-8")
        manifest["collections"][name] = len(docs)
        print(f"  {name}: {len(docs)} docs -> {path}")

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    latest_link = BACKUP_DIR / "latest.json"
    latest_link.write_text(json.dumps({"path": str(out_dir), **manifest}, indent=2), encoding="utf-8")
    print(f"\nBackup complete: {out_dir}")
    client.close()
    return out_dir


if __name__ == "__main__":
    cols = sys.argv[1:] or DEFAULT_COLLECTIONS
    asyncio.run(backup(cols))
