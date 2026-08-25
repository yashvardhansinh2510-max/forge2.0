#!/usr/bin/env python3
"""Test fail-fast behavior."""
import sys
sys.path.insert(0, '/app/backend')

from settings import ConfigurationError, load_settings

# Test with missing MONGO_URL
env = {
    "DB_NAME": "test",
    "JWT_SECRET": "x" * 32,
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-key",
    "SUPABASE_ANON_KEY": "test-anon",
    "SUPABASE_PUBLIC_BUCKET": "test-public",
    "SUPABASE_PRIVATE_BUCKET": "test-private",
}

try:
    cfg = load_settings(env, load_local_fallback=False)
    print("ERROR: Should have raised ConfigurationError")
    sys.exit(1)
except ConfigurationError as e:
    error_msg = str(e)
    print(f"ConfigurationError raised: {error_msg}")
    
    # Check error message mentions the missing variable
    if "MONGO_URL" not in error_msg:
        print("ERROR: Error message does not mention MONGO_URL")
        sys.exit(1)
    
    # Check error message mentions STARTUP_CHECK.md
    if "STARTUP_CHECK.md" not in error_msg:
        print("ERROR: Error message does not mention STARTUP_CHECK.md")
        sys.exit(1)
    
    # Check error message does NOT contain any secret values
    # (In this case there are no secrets in the env, but verify the pattern)
    if "test-key" in error_msg or "test-anon" in error_msg:
        print("ERROR: Error message contains secret values")
        sys.exit(1)
    
    print("✅ Error message is descriptive and does not expose secrets")
    sys.exit(0)
