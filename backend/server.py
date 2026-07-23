"""Forge backend entrypoint. Wires routes and boots demo data on first run."""
import asyncio
import logging
from time import monotonic
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from middleware import SecurityHeadersMiddleware

from bootstrap import _check_demo_accounts, run_bootstrap
from services.monitoring import init_monitoring

from db import db  # noqa: E402
from routes.auth_routes import router as auth_router  # noqa: E402
from routes.dashboard_routes import router as dashboard_router  # noqa: E402
from routes.catalog_routes import router as catalog_router  # noqa: E402
from routes.catalog_import_routes import router as catalog_import_router  # noqa: E402
from routes.customer_routes import router as customer_router  # noqa: E402
from routes.quotation_routes import router as quotation_router  # noqa: E402
from routes.misc_routes import router as misc_router  # noqa: E402
from routes.media_routes import router as media_router  # noqa: E402
from routes.supplier_routes import router as supplier_router  # noqa: E402
from routes.purchase_routes import router as purchase_router  # noqa: E402
from routes.purchases_tracker import router as purchases_tracker_router  # noqa: E402
from routes.payment_routes import router as payment_router  # noqa: E402
from routes.activity_routes import router as activity_router  # noqa: E402
from routes.followup_routes import router as followup_router  # noqa: E402
from routes.settings_routes import router as settings_router  # noqa: E402
from routes.roles_routes import router as roles_router  # noqa: E402
from routes.permissions_routes import router as permissions_router  # noqa: E402
from seed import resync_catalog_if_needed, seed_if_empty  # noqa: E402
from services import catalog_service  # noqa: E402
from services.domain_outbox import dispatch_pending, ensure_outbox_indexes, outbox_worker  # noqa: E402
from services.transfer_workflow import ensure_transfer_indexes  # noqa: E402
from services.download_tokens import ensure_download_token_indexes  # noqa: E402
from migrations.runner import run_migrations  # noqa: E402
from services.followup_engine import reconcile_followups  # noqa: E402
from services.floor_scope import ensure_floor_scope  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
logger = logging.getLogger("forge")

# Monitoring (Sentry + PostHog) — complete no-op until SENTRY_DSN/POSTHOG_API_KEY
# are set (see services/monitoring.py + backend/.env.example). Called before app
# construction so an unhandled exception anywhere downstream is captured.
_monitoring_status = init_monitoring()

app = FastAPI(title="Forge API", version="0.1.0")
api = APIRouter(prefix="/api")

# TTL-cached demo-account detection for /api/health — reuses the same
# lazy-refresh idiom as auth.py's principal cache. bcrypt is deliberately
# slow, so this must not run on every health poll; re-checking at most every
# 10 minutes still lets the "degraded" status self-clear soon after a real
# credential rotation, without needing a restart.
_DEMO_CHECK_TTL_SECONDS = 600.0
_demo_check_cache: dict[str, Any] = {"checked_at": 0.0, "emails": []}


async def _demo_accounts_detected() -> list[str]:
    if monotonic() - _demo_check_cache["checked_at"] > _DEMO_CHECK_TTL_SECONDS:
        try:
            _demo_check_cache["emails"] = await _check_demo_accounts(db)
        except Exception as e:  # noqa: BLE001 — health checks must never crash on this
            logger.warning("Demo-account health re-check failed: %s", e)
        _demo_check_cache["checked_at"] = monotonic()
    return _demo_check_cache["emails"]


@api.get("/")
async def root():
    return {"name": "Forge API", "version": "0.1.0", "status": "ok"}


@api.get("/health")
async def health():
    try:
        await db.command("ping")
    except Exception:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"status": "error", "detail": "database unavailable"})

    demo_accounts = await _demo_accounts_detected()
    if demo_accounts:
        return {
            "status": "degraded",
            "reasons": [f"Demo account still using known default password: {email}" for email in demo_accounts],
        }
    return {"status": "ok"}


# Feature routers
api.include_router(auth_router)
api.include_router(dashboard_router)
api.include_router(catalog_router)
api.include_router(catalog_import_router)
api.include_router(customer_router)
api.include_router(quotation_router)
api.include_router(misc_router)
api.include_router(media_router)
api.include_router(supplier_router)
api.include_router(purchase_router)
api.include_router(purchases_tracker_router)
api.include_router(payment_router)
api.include_router(activity_router)
api.include_router(followup_router)
api.include_router(settings_router)
api.include_router(roles_router)
api.include_router(permissions_router)

app.include_router(api)

# Security headers (defense-in-depth, no behavior change for existing
# clients) — registered before CORSMiddleware so CORS stays the outermost
# middleware, unchanged from its current behavior.
app.add_middleware(SecurityHeadersMiddleware)

# Security audit (Phase 1, 2026-08): Forge authenticates exclusively via a
# Bearer JWT stored client-side (see frontend/src/api/client.ts) — it never
# relies on cookies. `allow_credentials=True` combined with a wildcard origin
# is therefore both unnecessary AND flagged by every CORS scanner as unsafe
# (the two are mutually contradictory per the Fetch spec; browsers silently
# ignore the wildcard when credentials are requested). Preview URLs are
# dynamic per-session, so an allowlist of origins is not viable here — the
# safe fix is to disable credentialed CORS entirely, not to restrict origins.
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup():
    # Validate external infrastructure before any seed/reconciliation writes.
    # Uvicorn does not report the application ready until this preflight passes.
    await run_bootstrap()

    applied = await run_migrations(db)
    if applied:
        logger.info("Applied %d migration(s) on startup: %s", len(applied), ", ".join(applied))

    # Re-run preflight now that migrations may have just created indexes the
    # first pass reported missing (e.g. brands.slug/categories.slug via
    # migrations 0005/0007). Checking once, before migrations, would deadlock
    # a not-yet-fully-migrated database: preflight blocks startup, so the
    # migration that would satisfy it never gets the chance to run.
    preflight = await run_bootstrap()
    preflight.require_healthy()

    await ensure_floor_scope()
    await seed_if_empty()
    await resync_catalog_if_needed()
    await ensure_outbox_indexes()
    await ensure_transfer_indexes()
    await ensure_download_token_indexes()
    await dispatch_pending()
    # Durable background dispatcher — pending events retry on a schedule and
    # dead-letter after repeated failure instead of waiting for a restart.
    app.state.outbox_worker = asyncio.create_task(outbox_worker())
    snapshot = await catalog_service.refresh_catalog_snapshot()
    logger.info("Catalog read model ready: %d products.", len(snapshot.products))
    try:
        await reconcile_followups()
    except Exception as e:  # noqa: BLE001 — best-effort, frontend also triggers this on load
        logger.warning("Initial follow-up reconciliation skipped: %s", e)
    logger.info("Forge API ready; infrastructure preflight passed.")
    logger.info("Monitoring status: sentry=%s posthog=%s", _monitoring_status["sentry"], _monitoring_status["posthog"])


@app.on_event("shutdown")
async def _shutdown():
    worker = getattr(app.state, "outbox_worker", None)
    if worker:
        worker.cancel()
    logger.info("Forge API shutting down.")
