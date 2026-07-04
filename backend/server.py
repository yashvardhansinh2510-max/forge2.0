"""Forge backend entrypoint. Wires routes and boots demo data on first run."""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from db import db  # noqa: E402
from routes.auth_routes import router as auth_router  # noqa: E402
from routes.dashboard_routes import router as dashboard_router  # noqa: E402
from routes.catalog_routes import router as catalog_router  # noqa: E402
from routes.customer_routes import router as customer_router  # noqa: E402
from routes.quotation_routes import router as quotation_router  # noqa: E402
from routes.misc_routes import router as misc_router  # noqa: E402
from seed import seed_if_empty  # noqa: E402

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
api.include_router(customer_router)
api.include_router(quotation_router)
api.include_router(misc_router)

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup():
    await seed_if_empty()
    logger.info("Forge API ready.")


@app.on_event("shutdown")
async def _shutdown():
    logger.info("Forge API shutting down.")
