"""Rotate any staff account still on the historical, publicly-known demo
password (see BACKEND_AUDIT_2026-07-17.md Critical #1).

Only ever touches accounts whose CURRENT password still verifies (via
bcrypt.checkpw, never a string compare) against the legacy default — an
account that has already been rotated is never touched again.

Safe by default: runs as a dry run unless --apply is passed. Never prints the
new passwords to stdout/logs — they're written to a local, timestamped file
under backend/backups/ so they can be handed to real staff securely (or
discarded, if these turn out to be genuinely unused demo-only accounts).

This script is NOT run automatically as part of any deploy or CI step — it
connects to whatever MONGO_URL/DB_NAME your current environment points at,
so run it deliberately against the environment you intend to rotate:

    python -m scripts.rotate_demo_credentials              # dry run
    python -m scripts.rotate_demo_credentials --apply       # actually rotate
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from bootstrap import LEGACY_DEMO_PASSWORD  # noqa: E402
from seed import DEMO_STAFF  # noqa: E402
from services.invite_service import temp_password_expiry_iso  # noqa: E402

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", ROOT / "backups"))


async def _find_matching_accounts(db) -> list[dict]:
    emails = [email for email, _name, _role in DEMO_STAFF]
    docs = await db.users.find(
        {"email": {"$in": emails}}, {"_id": 0, "id": 1, "email": 1, "password_hash": 1},
    ).to_list(len(emails) + 1)
    legacy_bytes = LEGACY_DEMO_PASSWORD.encode("utf-8")
    matches = []
    for doc in docs:
        pw_hash = doc.get("password_hash")
        if not pw_hash:
            continue
        try:
            if bcrypt.checkpw(legacy_bytes, pw_hash.encode("utf-8")):
                matches.append(doc)
        except (ValueError, TypeError):
            continue
    return matches


async def rotate(apply: bool) -> int:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    matches = await _find_matching_accounts(db)
    if not matches:
        print(f"No accounts found still on the legacy default password (db={db_name}).")
        client.close()
        return 0

    print(f"Found {len(matches)} account(s) still on the legacy default password:")
    for m in matches:
        print(f"  - {m['email']}")

    if not apply:
        print("\nDry run only — no changes made. Re-run with --apply to rotate.")
        client.close()
        return 0

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    # BUG FIX: this previously set expiry to `now` (effectively already
    # expired), so the temp password would be rejected as expired on the
    # very next login attempt — no one could ever actually use it. Use the
    # same TTL helper the staff-invite flow uses.
    temp_expires = temp_password_expiry_iso()
    new_passwords: dict[str, str] = {}

    for m in matches:
        new_password = secrets.token_urlsafe(18)
        new_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        await db.users.update_one(
            {"id": m["id"]},
            {"$set": {
                "password_hash": new_hash,
                "must_change_password": True,
                "temp_password_expires_at": temp_expires,
                "updated_at": now_iso,
            }},
        )
        await db.user_sessions.update_many(
            {"user_type": "staff", "user_id": m["id"]},
            {"$set": {"revoked": True}},
        )
        new_passwords[m["email"]] = new_password
        print(f"  Rotated {m['email']} — all existing sessions revoked, must_change_password set.")

    ts = now.strftime("%Y%m%d_%H%M%S")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BACKUP_DIR / f"credential_rotation_{ts}.json"
    out_path.write_text(json.dumps({
        "rotated_at": now_iso,
        "db": db_name,
        "accounts": new_passwords,
        "note": "One-time temporary passwords. must_change_password=True forces a real reset on next login.",
    }, indent=2), encoding="utf-8")
    os.chmod(out_path, 0o600)

    print(f"\nRotated {len(matches)} account(s). Temporary passwords written to: {out_path}")
    print("Handle that file as a secret — hand passwords to real staff securely, then delete it.")
    client.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually rotate (default: dry run only)")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(rotate(args.apply)))
