"""Production monitoring — Sentry error reporting gated behind environment.

Production readiness audit (2026-08): Forge had zero monitoring/observability
beyond structured stdout logging + the existing /api/health/system endpoint.
This module adds Sentry + PostHog wiring that is a COMPLETE no-op until
credentials are supplied — nothing here changes runtime behavior today.

Required env vars to activate (see backend/.env.example + PRODUCTION.md):
  SENTRY_DSN                  — enables error/crash reporting when set
  SENTRY_ENVIRONMENT          — optional, defaults to "production"
  SENTRY_TRACES_SAMPLE_RATE   — optional, defaults to "0" (tracing off)
Monitoring is never a hard dependency of application startup.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("forge.monitoring")

def init_monitoring() -> dict[str, bool]:
    """Call once at process startup (server.py, before the app object is
    used). Returns which integrations activated, for a one-line startup log
    — never raises, even if a package is missing or a DSN is malformed."""
    status = {"sentry": False}

    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.starlette import StarletteIntegration

            sentry_sdk.init(
                dsn=dsn,
                integrations=[
                    StarletteIntegration(transaction_style="endpoint"),
                    FastApiIntegration(transaction_style="endpoint"),
                ],
                traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0") or "0"),
                send_default_pii=False,
                environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
            )
            status["sentry"] = True
        except Exception as exc:  # noqa: BLE001 — monitoring must never block startup
            logger.warning("Sentry configured but failed to initialize: %s", exc)
    else:
        logger.info("SENTRY_DSN not set — error monitoring disabled (safe no-op).")

    return status
