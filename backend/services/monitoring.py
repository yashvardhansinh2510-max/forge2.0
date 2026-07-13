"""Production monitoring — Sentry (crash/error reporting) + PostHog
(product analytics), both fully gated behind environment variables.

Production readiness audit (2026-08): Forge had zero monitoring/observability
beyond structured stdout logging + the existing /api/health/system endpoint.
This module adds Sentry + PostHog wiring that is a COMPLETE no-op until
credentials are supplied — nothing here changes runtime behavior today.

Required env vars to activate (see backend/.env.example + PRODUCTION.md):
  SENTRY_DSN                  — enables error/crash reporting when set
  SENTRY_ENVIRONMENT          — optional, defaults to "production"
  SENTRY_TRACES_SAMPLE_RATE   — optional, defaults to "0" (tracing off)
  POSTHOG_API_KEY             — enables server-side analytics events when set
  POSTHOG_HOST                — optional, defaults to PostHog Cloud US

Neither integration is a hard dependency of app startup: `init_monitoring()`
never raises, and `posthog_client()` returns None when disabled so callers
can simply do `if (ph := posthog_client()): ph.capture(...)`.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("forge.monitoring")

_posthog_client = None
_posthog_checked = False


def init_monitoring() -> dict[str, bool]:
    """Call once at process startup (server.py, before the app object is
    used). Returns which integrations activated, for a one-line startup log
    — never raises, even if a package is missing or a DSN is malformed."""
    status = {"sentry": False, "posthog": False}

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

    # PostHog is lazily constructed on first use (see posthog_client()) so we
    # only report here whether a key is present, not whether it's valid.
    status["posthog"] = bool((os.environ.get("POSTHOG_API_KEY") or "").strip())
    if not status["posthog"]:
        logger.info("POSTHOG_API_KEY not set — product analytics disabled (safe no-op).")

    return status


def posthog_client():
    """Returns a configured PostHog client, or None if POSTHOG_API_KEY is
    unset/invalid. Safe to call from any route — never raises."""
    global _posthog_client, _posthog_checked
    if _posthog_checked:
        return _posthog_client
    _posthog_checked = True

    api_key = (os.environ.get("POSTHOG_API_KEY") or "").strip()
    if not api_key:
        return None
    try:
        from posthog import Posthog

        _posthog_client = Posthog(
            api_key=api_key,
            host=os.environ.get("POSTHOG_HOST", "https://us.i.posthog.com"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("PostHog configured but failed to initialize: %s", exc)
        _posthog_client = None
    return _posthog_client


def capture_event(distinct_id: str, event: str, properties: dict | None = None) -> None:
    """Best-effort server-side analytics event — no-op when PostHog is
    disabled, and never raises on failure (analytics must never break a
    business request)."""
    client = posthog_client()
    if not client:
        return
    try:
        client.capture(distinct_id=distinct_id, event=event, properties=properties or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("PostHog capture_event failed (ignored): %s", exc)
