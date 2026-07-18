"""Apply pending numbered migrations (backend/migrations/NNNN_*.py).

Run via `./.venv/bin/python scripts/run_migrations.py` before deploying a
release that changes the schema. `--dry-run` lists what's pending without
touching the database. See migrations/runner.py for the full contract.
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

from db import db  # noqa: E402
from migrations.runner import run_migrations  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s :: %(message)s")
log = logging.getLogger("forge.migrations.cli")


async def main(dry_run: bool) -> None:
    ran = await run_migrations(db, dry_run=dry_run)
    if not ran:
        log.info("No pending migrations.")
    elif dry_run:
        log.info("Pending (not applied): %s", ", ".join(ran))
    else:
        log.info("Applied %d migration(s): %s", len(ran), ", ".join(ran))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="List pending migrations without applying them.")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
