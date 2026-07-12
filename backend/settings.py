"""Centralized, fail-fast runtime configuration for Forge.

Process environment variables are authoritative in deployed environments. A local
``backend/.env`` file is loaded only as a development/preview fallback and never
overrides values injected by the platform.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parent
LOCAL_ENV_FILE = BACKEND_DIR / ".env"


class ConfigurationError(RuntimeError):
    """Raised when Forge cannot start safely with the supplied configuration."""


@dataclass(frozen=True)
class Settings:
    mongo_url: str
    db_name: str
    jwt_secret: str
    jwt_algorithm: str
    jwt_exp_minutes: int
    media_storage_driver: str
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str
    supabase_public_bucket: str
    supabase_private_bucket: str

    def readiness_flags(self) -> dict[str, bool]:
        """Safe, non-secret status values for diagnostics and health responses."""
        return {
            "MONGO_URL": bool(self.mongo_url),
            "DB_NAME": bool(self.db_name),
            "JWT_SECRET": bool(self.jwt_secret),
            "SUPABASE_URL": bool(self.supabase_url),
            "SUPABASE_SERVICE_ROLE_KEY": bool(self.supabase_service_role_key),
            "SUPABASE_ANON_KEY": bool(self.supabase_anon_key),
            "SUPABASE_PUBLIC_BUCKET": bool(self.supabase_public_bucket),
            "SUPABASE_PRIVATE_BUCKET": bool(self.supabase_private_bucket),
        }


def _required(env: Mapping[str, str], name: str) -> str:
    value = (env.get(name) or "").strip()
    invalid = not value or value.startswith("<") or "..." in value
    if invalid:
        raise ConfigurationError(
            f"Missing or placeholder configuration: {name}. "
            "Set it in the deployment environment; backend/.env is only a local fallback. "
            "See STARTUP_CHECK.md."
        )
    return value


def load_settings(
    environ: Mapping[str, str] | None = None,
    *,
    load_local_fallback: bool = True,
) -> Settings:
    """Load and validate settings, preferring platform-injected process values."""
    if environ is None:
        if load_local_fallback:
            load_dotenv(LOCAL_ENV_FILE, override=False)
        env: Mapping[str, str] = os.environ
    else:
        env = environ

    mongo_url = _required(env, "MONGO_URL")
    db_name = _required(env, "DB_NAME")
    jwt_secret = _required(env, "JWT_SECRET")
    supabase_url = _required(env, "SUPABASE_URL").rstrip("/")
    service_key = _required(env, "SUPABASE_SERVICE_ROLE_KEY")
    anon_key = _required(env, "SUPABASE_ANON_KEY")
    public_bucket = _required(env, "SUPABASE_PUBLIC_BUCKET")
    private_bucket = _required(env, "SUPABASE_PRIVATE_BUCKET")

    if not mongo_url.startswith(("mongodb://", "mongodb+srv://")):
        raise ConfigurationError("MONGO_URL must start with mongodb:// or mongodb+srv://.")
    if any(ch.isspace() for ch in mongo_url):
        raise ConfigurationError("MONGO_URL contains whitespace; provide the exact Atlas URI on one line.")
    if not db_name or any(ch.isspace() for ch in db_name):
        raise ConfigurationError("DB_NAME must be a non-empty MongoDB database name without whitespace.")
    if len(jwt_secret) < 32:
        raise ConfigurationError("JWT_SECRET must contain at least 32 characters.")
    parsed = urlparse(supabase_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ConfigurationError("SUPABASE_URL must be a valid https:// project URL.")

    try:
        jwt_exp_minutes = int(env.get("JWT_EXP_MINUTES", "43200"))
    except ValueError as exc:
        raise ConfigurationError("JWT_EXP_MINUTES must be an integer.") from exc
    if jwt_exp_minutes <= 0:
        raise ConfigurationError("JWT_EXP_MINUTES must be greater than zero.")

    driver = (env.get("MEDIA_STORAGE_DRIVER") or "supabase").strip().lower()
    if driver != "supabase":
        raise ConfigurationError(
            f"Unsupported MEDIA_STORAGE_DRIVER={driver!r}; Forge production currently requires 'supabase'."
        )

    return Settings(
        mongo_url=mongo_url,
        db_name=db_name,
        jwt_secret=jwt_secret,
        jwt_algorithm=(env.get("JWT_ALGORITHM") or "HS256").strip(),
        jwt_exp_minutes=jwt_exp_minutes,
        media_storage_driver=driver,
        supabase_url=supabase_url,
        supabase_service_role_key=service_key,
        supabase_anon_key=anon_key,
        supabase_public_bucket=public_bucket,
        supabase_private_bucket=private_bucket,
    )


# Imported by runtime modules. Invalid configuration stops module import with a
# descriptive error before database/auth clients are constructed.
settings = load_settings()
