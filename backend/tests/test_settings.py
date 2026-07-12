from __future__ import annotations

import pytest

from settings import ConfigurationError, load_settings


def valid_env() -> dict[str, str]:
    return {
        "MONGO_URL": "mongodb+srv://user:pass@example.mongodb.net/",
        "DB_NAME": "buildcon",
        "JWT_SECRET": "x" * 32,
        "JWT_ALGORITHM": "HS256",
        "JWT_EXP_MINUTES": "43200",
        "MEDIA_STORAGE_DRIVER": "supabase",
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-value",
        "SUPABASE_ANON_KEY": "anon-value",
        "SUPABASE_PUBLIC_BUCKET": "forge-products",
        "SUPABASE_PRIVATE_BUCKET": "forge-private",
    }


def test_load_settings_accepts_complete_process_environment() -> None:
    cfg = load_settings(valid_env(), load_local_fallback=False)
    assert cfg.db_name == "buildcon"
    assert cfg.supabase_public_bucket == "forge-products"
    assert all(cfg.readiness_flags().values())


@pytest.mark.parametrize("missing", [
    "MONGO_URL",
    "DB_NAME",
    "JWT_SECRET",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_ANON_KEY",
    "SUPABASE_PUBLIC_BUCKET",
    "SUPABASE_PRIVATE_BUCKET",
])
def test_load_settings_fails_fast_for_missing_required_values(missing: str) -> None:
    env = valid_env()
    env.pop(missing)
    with pytest.raises(ConfigurationError, match=missing):
        load_settings(env, load_local_fallback=False)


def test_load_settings_rejects_placeholder_and_wrapped_mongo_uri() -> None:
    env = valid_env()
    env["SUPABASE_ANON_KEY"] = "eyJ...truncated"
    with pytest.raises(ConfigurationError, match="SUPABASE_ANON_KEY"):
        load_settings(env, load_local_fallback=False)

    env = valid_env()
    env["MONGO_URL"] = "mongodb+srv://user:pass@example.mongodb.net/ ?appName=x"
    with pytest.raises(ConfigurationError, match="whitespace"):
        load_settings(env, load_local_fallback=False)
