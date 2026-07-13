"""Forge backend entrypoint. Wires routes and boots demo data on first run."""
import logging

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from bootstrap import run_bootstrap

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
from seed import resync_catalog_if_needed, seed_if_empty  # noqa: E402
from services import catalog_service  # noqa: E402
from services.domain_outbox import dispatch_pending, ensure_outbox_indexes  # noqa: E402
from services.transfer_workflow import ensure_transfer_indexes  # noqa: E402
from services.followup_engine import reconcile_followups  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
logger = logging.getLogger("forge")

app = FastAPI(title="Forge API", version="0.1.0")
api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"name": "Forge API", "version": "0.1.0", "status": "ok"}


@api.get("/health")
async def health():
    try:
        await db.command("ping")
        return {"status": "ok"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "detail": str(e)}


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

app.include_router(api)

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
    preflight = await run_bootstrap()
    preflight.require_healthy()

    await seed_if_empty()
    await resync_catalog_if_needed()
    await ensure_outbox_indexes()
    await ensure_transfer_indexes()
    await dispatch_pending()
    snapshot = await catalog_service.refresh_catalog_snapshot()
    logger.info("Catalog read model ready: %d products.", len(snapshot.products))
    try:
        await reconcile_followups()
    except Exception as e:  # noqa: BLE001 — best-effort, frontend also triggers this on load
        logger.warning("Initial follow-up reconciliation skipped: %s", e)
    logger.info("Forge API ready; infrastructure preflight passed.")


@app.on_event("shutdown")
async def _shutdown():
    logger.info("Forge API shutting down.")
