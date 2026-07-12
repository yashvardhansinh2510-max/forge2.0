"""Forge infrastructure preflight.

Usage:
    python bootstrap.py
    python bootstrap.py --health-url http://127.0.0.1:8001/api/health

The first form validates configuration, MongoDB, Supabase buckets, required
collections, and required indexes. The optional health URL is a post-start check
used by deployment/recovery workflows because an HTTP endpoint cannot be checked
before Uvicorn binds its socket.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

from settings import ConfigurationError, Settings, settings


REQUIRED_COLLECTIONS = {
    "brands",
    "categories",
    "customers",
    "followups",
    "notifications",
    "payments",
    "product_media",
    "product_usage",
    "products",
    "purchase_orders",
    "quotations",
    "suppliers",
    "user_sessions",
    "users",
}

# These are existing application indexes, not new optimization proposals.
# Signatures are checked by key pattern so Atlas-generated index names are valid.
REQUIRED_INDEXES: dict[str, list[tuple[tuple[str, int], ...]]] = {
    "products": [
        (("id", 1),),
        (("sku", 1),),
        (("family_key", 1),),
        (("active", 1), ("brand_id", 1)),
        (("active", 1), ("category_id", 1)),
    ],
    "product_media": [(("product_id", 1),), (("family_key", 1),)],
    "product_usage": [(("user_id", 1),), (("product_id", 1),)],
    "user_sessions": [(("id", 1),), (("user_type", 1), ("user_id", 1))],
}


@dataclass
class BootstrapReport:
    checks: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return not self.errors

    def require_healthy(self) -> None:
        if self.errors:
            lines = "\n  - ".join(self.errors)
            raise RuntimeError(
                "Forge startup preflight failed:\n  - " + lines +
                "\nSee STARTUP_CHECK.md and RECOVERY.md."
            )

    def to_public_dict(self) -> dict[str, Any]:
        return {"healthy": self.healthy, "checks": self.checks, "errors": self.errors}


def _index_signature(spec: dict[str, Any]) -> tuple[tuple[str, int], ...]:
    return tuple((str(k), int(v)) for k, v in spec.get("key", []))


async def _check_mongo(cfg: Settings, report: BootstrapReport) -> None:
    client = AsyncIOMotorClient(
        cfg.mongo_url,
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=8000,
    )
    try:
        await client.admin.command("ping")
        database = client[cfg.db_name]
        existing_collections = set(await database.list_collection_names())
        missing_collections = sorted(REQUIRED_COLLECTIONS - existing_collections)
        report.checks["mongo"] = {
            "connected": True,
            "database": cfg.db_name,
            "required_collections": len(REQUIRED_COLLECTIONS),
            "missing_collections": missing_collections,
        }
        if missing_collections:
            report.errors.append(
                "MongoDB is missing required collections: " + ", ".join(missing_collections)
            )

        missing_indexes: dict[str, list[list[list[Any]]]] = {}
        for collection, expected in REQUIRED_INDEXES.items():
            current = await database[collection].index_information()
            signatures = {_index_signature(spec) for spec in current.values()}
            absent = [sig for sig in expected if sig not in signatures]
            if absent:
                missing_indexes[collection] = [[list(part) for part in sig] for sig in absent]
        report.checks["mongo"]["missing_indexes"] = missing_indexes
        if missing_indexes:
            report.errors.append(
                "MongoDB required indexes are missing; review bootstrap output before adding them: "
                + ", ".join(sorted(missing_indexes))
            )
    except Exception as exc:  # noqa: BLE001
        report.checks["mongo"] = {"connected": False, "database": cfg.db_name}
        report.errors.append(f"MongoDB connection failed: {type(exc).__name__}: {exc}")
    finally:
        client.close()


async def _check_supabase(cfg: Settings, report: BootstrapReport) -> None:
    headers = {
        "apikey": cfg.supabase_service_role_key,
        "Authorization": f"Bearer {cfg.supabase_service_role_key}",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{cfg.supabase_url}/storage/v1/bucket", headers=headers)
        if response.status_code >= 300:
            raise RuntimeError(f"bucket listing returned HTTP {response.status_code}")
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        bucket_ids = {str(row.get("id") or row.get("name")) for row in rows if isinstance(row, dict)}
        required = {cfg.supabase_public_bucket, cfg.supabase_private_bucket}
        missing = sorted(required - bucket_ids)
        report.checks["supabase"] = {
            "connected": True,
            "required_buckets": sorted(required),
            "missing_buckets": missing,
        }
        if missing:
            report.errors.append("Supabase is missing required buckets: " + ", ".join(missing))
    except Exception as exc:  # noqa: BLE001
        report.checks["supabase"] = {"connected": False}
        report.errors.append(f"Supabase connection failed: {type(exc).__name__}: {exc}")


async def _check_health(health_url: str, report: BootstrapReport) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(health_url)
        ok = response.status_code == 200 and response.json().get("status") == "ok"
        report.checks["health_endpoint"] = {"reachable": ok, "status_code": response.status_code}
        if not ok:
            report.errors.append(f"Health endpoint is not ready: {health_url} returned HTTP {response.status_code}")
    except Exception as exc:  # noqa: BLE001
        report.checks["health_endpoint"] = {"reachable": False}
        report.errors.append(f"Health endpoint failed: {type(exc).__name__}: {exc}")


async def run_bootstrap(
    cfg: Settings = settings,
    *,
    health_url: str | None = None,
) -> BootstrapReport:
    report = BootstrapReport(checks={"configuration": cfg.readiness_flags()})
    await asyncio.gather(_check_mongo(cfg, report), _check_supabase(cfg, report))
    if health_url:
        await _check_health(health_url, report)
    return report


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Validate Forge production infrastructure")
    parser.add_argument("--health-url", help="Optional post-start /api/health URL")
    args = parser.parse_args()
    report = await run_bootstrap(health_url=args.health_url)
    print(json.dumps(report.to_public_dict(), indent=2))
    return 0 if report.healthy else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(_main()))
    except ConfigurationError as exc:
        print(json.dumps({"healthy": False, "checks": {"configuration": False}, "errors": [str(exc)]}, indent=2))
        raise SystemExit(2) from exc
