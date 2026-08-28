"""Durable, bounded catalog-import approval jobs.

The Mongo document is the source of truth: a process crash leaves a job in a
resumable state and successful rows are never selected again.  Workers are
deliberately in-process (there is no queue service in this deployment), so the
API exposes explicit resume/retry operations and never claims distributed
exactly-once delivery.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from pymongo import ReturnDocument

from catalog_pipeline.orchestrator import import_accepted
from db import db
from services import catalog_service

logger = logging.getLogger("forge.catalog_import.jobs")
MAX_CONCURRENT_IMPORT_JOBS = 2
ROW_BATCH_SIZE = 20
_workers = asyncio.Semaphore(MAX_CONCURRENT_IMPORT_JOBS)
_scheduled: set[str] = set()


def pending_rows(rows: list[dict]) -> list[dict]:
    """Return accepted rows that have not completed successfully."""
    return [r for r in rows if r.get("status") == "accepted" and r.get("import_state") != "succeeded"]


def apply_batch_result(rows: list[dict], result: dict) -> tuple[int, int]:
    """Record terminal per-row results without changing the reviewer decision."""
    failures = {str(e.get("row_id")): str(e.get("error") or "Import failed") for e in result.get("errors", [])}
    attempted = set(result.get("attempted_row_ids") or [])
    succeeded = 0
    failed = 0
    for row in rows:
        row_id = str(row.get("row_id"))
        if row_id not in attempted:
            continue
        if row_id in failures:
            row.update({"import_state": "failed", "import_error": failures[row_id], "imported_at": None})
            failed += 1
        else:
            row.update({"import_state": "succeeded", "import_error": None, "imported_at": datetime.now(timezone.utc).isoformat()})
            succeeded += 1
    return succeeded, failed


async def enqueue(job_id: str, actor_id: str) -> None:
    """Schedule at most one local worker per job; persisted status enables resume."""
    if job_id in _scheduled:
        return
    _scheduled.add(job_id)
    asyncio.create_task(_run(job_id, actor_id), name=f"catalog-import-{job_id}")


async def _run(job_id: str, actor_id: str) -> None:
    try:
        async with _workers:
            while True:
                job = await db.catalog_imports.find_one({"id": job_id}, {"_id": 0})
                if not job:
                    return
                rows = job.get("rows") or []
                batch = pending_rows(rows)[:ROW_BATCH_SIZE]
                if not batch:
                    failures = sum(1 for row in rows if row.get("import_state") == "failed")
                    await db.catalog_imports.update_one({"id": job_id}, {"$set": {
                        "status": "partial_failed" if failures else "imported",
                        "import_finished_at": datetime.now(timezone.utc).isoformat(),
                        "import_progress": {"completed": sum(row.get("import_state") == "succeeded" for row in rows), "failed": failures, "total": len([r for r in rows if r.get("status") == "accepted"])},
                    }})
                    catalog_service.schedule_catalog_refresh()
                    return
                result = await import_accepted({**job, "rows": batch}, actor_id, floor_id=job.get("floor_id"))
                apply_batch_result(rows, result)
                completed = sum(row.get("import_state") == "succeeded" for row in rows)
                failed = sum(row.get("import_state") == "failed" for row in rows)
                await db.catalog_imports.update_one({"id": job_id, "status": "processing"}, {"$set": {
                    "rows": rows,
                    "import_progress": {"completed": completed, "failed": failed, "total": len([r for r in rows if r.get("status") == "accepted"])},
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }})
    except Exception:  # leave completed rows persisted; retry endpoint can resume safely
        logger.exception("catalog import job failed job=%s", job_id)
        await db.catalog_imports.update_one({"id": job_id}, {"$set": {"status": "failed", "error": "Background import interrupted; retry failed rows or resume the job."}})
    finally:
        _scheduled.discard(job_id)


async def claim_for_processing(job_id: str, floor_filter: dict[str, Any]) -> dict | None:
    """Atomically claim an eligible job so duplicate approve requests get no work."""
    query = dict(floor_filter)
    query["status"] = {"$in": ["classified", "reviewed", "partial_failed", "failed"]}
    return await db.catalog_imports.find_one_and_update(
        query,
        {"$set": {"status": "processing", "error": None, "import_started_at": datetime.now(timezone.utc).isoformat()}},
        return_document=ReturnDocument.AFTER,
    )
