"""Persistence & Disaster Recovery — pull a backup snapshot DOWN from the
Supabase private bucket into local disk, for when the local `backend/backups/`
directory is empty (i.e. this is a brand-new session/container and the only
surviving copy of the last snapshot is the one backup_db.py pushed to
Supabase).

Usage:
    python scripts/pull_backup_from_supabase.py --list         # list available snapshot timestamps
    python scripts/pull_backup_from_supabase.py                # pull the most recent snapshot
    python scripts/pull_backup_from_supabase.py 20260707_023215  # pull a specific one
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", ROOT / "backups"))


async def _list_snapshots(client: httpx.AsyncClient, base: str, bucket: str, headers: dict) -> list[str]:
    resp = await client.post(
        f"{base}/storage/v1/object/list/{bucket}",
        headers=headers,
        json={"prefix": "backups/", "limit": 1000},
    )
    resp.raise_for_status()
    entries = resp.json()
    names = sorted({e["name"] for e in entries if e.get("name")}, reverse=True)
    return names


async def main() -> None:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    bucket = os.environ.get("SUPABASE_PRIVATE_BUCKET", "forge-private")
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    args = sys.argv[1:]
    async with httpx.AsyncClient(timeout=30.0) as client:
        snapshots = await _list_snapshots(client, url, bucket, headers)
        if "--list" in args:
            print("Available snapshots in Supabase:")
            for s in snapshots:
                print(f"  {s}")
            return
        if not snapshots:
            raise SystemExit("No snapshots found in Supabase private bucket.")

        ts = args[0] if args and not args[0].startswith("--") else snapshots[0]
        out_dir = BACKUP_DIR / ts
        out_dir.mkdir(parents=True, exist_ok=True)

        list_resp = await client.post(
            f"{url}/storage/v1/object/list/{bucket}",
            headers=headers,
            json={"prefix": f"backups/{ts}/", "limit": 1000},
        )
        list_resp.raise_for_status()
        files = [e["name"] for e in list_resp.json() if e.get("name", "").endswith(".json")]
        if not files:
            raise SystemExit(f"No files found under backups/{ts}/ in Supabase.")

        for fname in files:
            obj_url = f"{url}/storage/v1/object/{bucket}/backups/{ts}/{fname}"
            r = await client.get(obj_url, headers=headers)
            r.raise_for_status()
            (out_dir / fname).write_bytes(r.content)
            print(f"  pulled {fname} ({len(r.content)} bytes)")

        (BACKUP_DIR / "latest.json").write_text(
            f'{{"path": "{out_dir}"}}', encoding="utf-8",
        )
        print(f"\nPulled snapshot {ts} -> {out_dir}")
        print("Now run: python scripts/restore_db.py --dry-run   (then without --dry-run to apply)")


if __name__ == "__main__":
    asyncio.run(main())
