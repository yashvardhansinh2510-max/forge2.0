"""Read-only backend pre-deploy gate: health, required indexes and media audit."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

from bootstrap import run_bootstrap  # noqa: E402
from media_storage.supabase_driver import supabase_ready  # noqa: E402


async def main() -> int:
    checks: dict[str, str] = {}
    try:
        report = await run_bootstrap(enforce_indexes=True)
        checks["mongodb_ping"] = "pass" if report.checks.get("mongo", {}).get("connected") else "fail"
        checks["required_indexes"] = "pass" if not report.checks.get("mongo", {}).get("missing_indexes") else "fail"
        await supabase_ready()  # explicit authenticated bucket access check
        checks["supabase_buckets"] = "pass"
        if not report.healthy:
            checks["bootstrap_errors"] = "; ".join(report.errors)
            print(json.dumps({"read_only": True, "checks": checks}, indent=2))
            return 1
    except Exception as exc:  # operational details stay local; no credential output
        checks["failure"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        print(json.dumps({"read_only": True, "checks": checks}, indent=2))
        return 1
    print(json.dumps({"read_only": True, "checks": checks}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
