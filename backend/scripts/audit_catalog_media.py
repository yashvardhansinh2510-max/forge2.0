"""Audit catalog media identity; apply only deterministic stale-key repairs."""
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
from services.catalog_media_integrity import audit_catalog_media, repair_foreign_product_families  # noqa: E402
from services.catalog_service import schedule_catalog_refresh  # noqa: E402


async def main(apply: bool) -> None:
    report = await audit_catalog_media(db)
    result = {"audit": report, "repair": None}
    if apply:
        result["repair"] = await repair_foreign_product_families(db, report)
        if result["repair"]["repaired"]:
            schedule_catalog_refresh()
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-stale-family-keys", action="store_true", help="repair only product-linked stale family keys")
    args = parser.parse_args()
    asyncio.run(main(args.apply_stale_family_keys))
