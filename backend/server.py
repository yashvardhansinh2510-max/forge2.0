"""Forge backend entrypoint. Wires routes and boots demo data on first run."""
import asyncio
import logging
from time import monotonic
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from middleware import SecurityHeadersMiddleware

from bootstrap import _check_demo_accounts, run_bootstrap
from settings import settings
from services.monitoring import init_monitoring
from media_storage import get_media_storage

from db import client, db  # noqa: E402
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
from access_profiles import profile_allows_request  # noqa: E402
from auth import decode_token  # noqa: E402
from routes.referrer_routes import router as referrer_router  # noqa: E402
from routes.sales_data_routes import router as sales_data_router  # noqa: E402
from routes.executive_analytics_routes import router as executive_analytics_router  # noqa: E402
from routes.analytics_settings_routes import router as analytics_settings_router  # noqa: E402
from routes.executive_overview_routes import router as executive_overview_router  # noqa: E402
from routes.sales_performance_routes import router as sales_performance_router  # noqa: E402
from routes.referral_analytics_routes import router as referral_analytics_router  # noqa: E402
from routes.sales_breakdown_routes import router as sales_breakdown_router  # noqa: E402
from routes.sales_workspace_routes import router as sales_workspace_router  # noqa: E402
from routes.tile_orders import router as tile_orders_router  # noqa: E402
from routes.walkin_routes import router as walkin_router  # noqa: E402
from seed import resync_catalog_if_needed, seed_if_empty  # noqa: E402
from services import catalog_service  # noqa: E402
from services.domain_outbox import dispatch_pending, ensure_outbox_indexes, outbox_worker  # noqa: E402
from services.transfer_workflow import ensure_transfer_indexes  # noqa: E402
from services.download_tokens import ensure_download_token_indexes  # noqa: E402
from services.tile_order_indexes import ensure_tile_order_indexes  # noqa: E402
from migrations.runner import run_migrations  # noqa: E402
from services.followup_engine import reconcile_followups  # noqa: E402
from services.floor_scope import ensure_floor_scope  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
logger = logging.getLogger("forge")

# Monitoring (Sentry) — complete no-op until SENTRY_DSN
# are set (see services/monitoring.py + backend/.env.example). Called before app
# construction so an unhandled exception anywhere downstream is captured.
_monitoring_status = init_monitoring()

app = FastAPI(title="Forge API", version="0.1.0")
api = APIRouter(prefix="/api")


@app.middleware("http")
async def enforce_access_profile(request: Request, call_next):
    """Apply a fail-closed API allow-list before any restricted route runs."""
    if request.method == "OPTIONS" or not request.url.path.startswith("/api/"):
        return await call_next(request)
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return await call_next(request)
    try:
        token = decode_token(authorization.split(" ", 1)[1].strip())
    except Exception:
        # Route dependencies supply the canonical authentication response.
        return await call_next(request)
    if token.get("user_type") == "staff" and not profile_allows_request(
        token.get("access_profile"), request.method, request.url.path,
    ):
        return JSONResponse(status_code=403, content={"detail": "This account is not permitted to use this function"})
    return await call_next(request)

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
        logger.critical("Production demo credentials detected for %d account(s)", len(demo_accounts))
        return JSONResponse(status_code=503, content={"status": "degraded", "reasons": ["unsafe demo credentials detected"]})
    return {"status": "ok"}


@api.get("/health/ready", include_in_schema=False)
async def readiness():
    """Infrastructure readiness for the deployment orchestrator.

    ``/health`` intentionally reports a non-2xx status for a detected default
    demo password so that monitoring alerts on that security condition.  It is
    not a process-readiness failure, however: using it for Docker's health
    check caused Railway to continuously mark an otherwise working API
    unhealthy.  Keep the warning on ``/health`` and make the container probe
    depend only on the datastore it needs to serve traffic.
    """
    try:
        await db.command("ping")
        from media_storage.supabase_driver import supabase_ready
        await supabase_ready()
    except Exception:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"status": "error", "detail": "database unavailable"})
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
api.include_router(referrer_router)
api.include_router(sales_data_router)
api.include_router(executive_analytics_router)
api.include_router(analytics_settings_router)
api.include_router(executive_overview_router)
api.include_router(sales_performance_router)
api.include_router(referral_analytics_router)
api.include_router(sales_breakdown_router)
api.include_router(sales_workspace_router)
api.include_router(tile_orders_router)
api.include_router(walkin_router)

app.include_router(api)


@app.get("/", include_in_schema=False)
async def service_root():
    """Provide a useful response when the service URL is opened directly."""
    return {"name": "Forge API", "version": "0.1.0", "status": "ok"}


@app.get("/sentry-debug", include_in_schema=False)
async def trigger_error():
    """Trigger a controlled exception to verify Sentry reporting."""
    if settings.environment == "production":
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    division_by_zero = 1 / 0
    return division_by_zero

# Security headers (defense-in-depth, no behavior change for existing
# clients) — registered before CORSMiddleware so CORS stays the outermost
# middleware, unchanged from its current behavior.
app.add_middleware(SecurityHeadersMiddleware)
# Mobile clients and the hosted web app receive several JSON-heavy responses.
# Compress them at the API boundary; images already use their native formats.
app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)

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
    # The first pass gates external dependencies but permits index gaps that a
    # pending migration is about to create.  The post-migration pass enforces
    # the complete index contract before any ordinary application writes.
    preflight = await run_bootstrap(enforce_indexes=False)
    # No migration, seed, cache refresh, or reconciliation write may occur
    # until both persistence dependencies are proven healthy.
    preflight.require_healthy()

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
    await ensure_tile_order_indexes()
    await ensure_transfer_indexes()
    await ensure_download_token_indexes()
    await dispatch_pending()
    # Durable background dispatcher — pending events retry on a schedule and
    # dead-letter after repeated failure instead of waiting for a restart.
    app.state.outbox_worker = asyncio.create_task(outbox_worker())
    snapshot = await catalog_service.refresh_catalog_snapshot()
    logger.info("Catalog read model ready: %d products.", len(snapshot.products))
    try:
        from services.automation_rules import ensure_seeded
        await ensure_seeded()
    except Exception as e:  # noqa: BLE001 — best-effort, defaults still work without a DB row
        logger.warning("Automation rules seed skipped: %s", e)
    try:
        await reconcile_followups()
    except Exception as e:  # noqa: BLE001 — best-effort, frontend also triggers this on load
        logger.warning("Initial follow-up reconciliation skipped: %s", e)
    logger.info("Forge API ready; infrastructure preflight passed.")
    logger.info("Monitoring status: sentry=%s", _monitoring_status["sentry"])


@app.on_event("shutdown")
async def _shutdown():
    worker = getattr(app.state, "outbox_worker", None)
    if worker:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
    storage = get_media_storage()
    close_storage = getattr(storage, "close", None)
    if close_storage:
        await close_storage()
    client.close()
    logger.info("Forge API shutting down.")
