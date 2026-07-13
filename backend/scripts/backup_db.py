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
    "products", "product_media", "brands", "categories", "customers", "quotations",
    "purchase_orders", "payments", "followups", "users", "suppliers",
    # Production readiness audit (2026-08): this list previously said "activity" —
    # that collection does not exist; the real audit-trail collection (see
    # services/activity_log.py) is "activity_events" and had 254 real documents
    # silently excluded from every backup taken before this fix. Also added
    # "settings" (company/PDF config) and "notifications" and "catalog_imports",
    # "purchase_shortages", "purchase_transfers" — all real business data that
    # were similarly never backed up. Deliberately still excluding
    # "user_sessions" (ephemeral login sessions, regenerate on next login),
    # "event_outbox" (a self-draining dispatch queue, not source of truth), and
    # "product_usage" (a derived "most used" cache that rebuilds from behavior)
    # — these are safe to omit because nothing is lost if they're empty after a
    # restore.
    "activity_events", "settings", "notifications", "catalog_imports",
    "purchase_shortages", "purchase_transfers",
]

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", ROOT / "backups"))


async def _push_to_supabase(out_dir: Path, ts: str) -> None:
    """Best-effort: also push this snapshot into the private Supabase bucket so
    the backup itself survives a session reset (local disk does not).
    No-ops quietly if Supabase isn't configured."""
    if not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")):
        print("  (Supabase not configured — backup stays local-only, will not survive a session reset)")
        return
    import sys as _sys
    _sys.path.insert(0, str(ROOT))
    from media_storage import get_media_storage
    from media_storage.factory import private_bucket

    storage = get_media_storage()
    bucket = private_bucket()
    for path in out_dir.glob("*.json"):
        data = path.read_bytes()
        key = f"backups/{ts}/{path.name}"
        try:
            await storage.upload(bucket=bucket, key=key, data=data, content_type="application/json")
        except Exception as e:  # noqa: BLE001
            print(f"  ! Supabase push failed for {path.name}: {e}")
            return
    print(f"  Pushed snapshot to Supabase private bucket '{bucket}' at backups/{ts}/ (persists across session resets)")


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
    await _push_to_supabase(out_dir, ts)
    print(f"\nBackup complete: {out_dir}")
    client.close()
    return out_dir


if __name__ == "__main__":
    cols = sys.argv[1:] or DEFAULT_COLLECTIONS
    asyncio.run(backup(cols))
