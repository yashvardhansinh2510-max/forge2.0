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


def test_load_settings_defaults_to_production_and_no_demo_seed() -> None:
    cfg = load_settings(valid_env(), load_local_fallback=False)
    assert cfg.environment == "production"
    assert cfg.allow_demo_seed is False
    assert cfg.demo_password is None


def test_load_settings_rejects_demo_seed_in_production() -> None:
    env = valid_env()
    env["ENVIRONMENT"] = "production"
    env["FORGE_ALLOW_DEMO_SEED"] = "true"
    env["FORGE_DEMO_PASSWORD"] = "whatever-not-used"
    with pytest.raises(ConfigurationError, match="production"):
        load_settings(env, load_local_fallback=False)


def test_load_settings_allows_demo_seed_outside_production_with_password() -> None:
    env = valid_env()
    env["ENVIRONMENT"] = "development"
    env["FORGE_ALLOW_DEMO_SEED"] = "true"
    env["FORGE_DEMO_PASSWORD"] = "some-random-dev-password"
    cfg = load_settings(env, load_local_fallback=False)
    assert cfg.allow_demo_seed is True
    assert cfg.demo_password == "some-random-dev-password"


def test_load_settings_requires_demo_password_when_seeding_enabled() -> None:
    env = valid_env()
    env["ENVIRONMENT"] = "development"
    env["FORGE_ALLOW_DEMO_SEED"] = "true"
    with pytest.raises(ConfigurationError, match="FORGE_DEMO_PASSWORD"):
        load_settings(env, load_local_fallback=False)


def test_load_settings_rejects_invalid_environment_value() -> None:
    env = valid_env()
    env["ENVIRONMENT"] = "not-a-real-environment"
    with pytest.raises(ConfigurationError, match="ENVIRONMENT"):
        load_settings(env, load_local_fallback=False)
