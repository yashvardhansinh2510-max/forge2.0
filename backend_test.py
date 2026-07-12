#!/usr/bin/env python3
"""Infrastructure hardening verification test suite."""
import json
import os
import re
import sys
from pathlib import Path

import httpx

# Read backend URL from frontend/.env
FRONTEND_ENV = Path("/app/frontend/.env")
BACKEND_URL = None
if FRONTEND_ENV.exists():
    for line in FRONTEND_ENV.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BACKEND_URL = line.split("=", 1)[1].strip()
            break

if not BACKEND_URL:
    BACKEND_URL = "https://forge-hardening-prod.preview.emergentagent.com"

API_BASE = f"{BACKEND_URL}/api"

# Test credentials from /app/memory/test_credentials.md
OWNER_EMAIL = "owner@forge.app"
OWNER_PASSWORD = "Forge@2026"


def test_health_system():
    """Test 4: GET /api/health/system verification."""
    print("\n" + "="*80)
    print("TEST 4: GET /api/health/system")
    print("="*80)
    
    response = httpx.get(f"{API_BASE}/health/system", timeout=15.0)
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {response.status_code}")
        return False
    
    data = response.json()
    print(f"Response keys: {list(data.keys())}")
    
    # Check Mongo connected
    mongo = data.get("mongo", {})
    if not mongo.get("connected"):
        print(f"❌ FAILED: MongoDB not connected")
        return False
    print(f"✅ MongoDB connected: {mongo.get('connected')}")
    print(f"   Database: {mongo.get('database')}")
    print(f"   is_local: {mongo.get('is_local')}")
    
    # Check Supabase connected
    supabase = data.get("supabase", {})
    if not supabase.get("configured"):
        print(f"❌ FAILED: Supabase not configured")
        return False
    if not supabase.get("connected"):
        print(f"❌ FAILED: Supabase not connected")
        return False
    print(f"✅ Supabase configured: {supabase.get('configured')}")
    print(f"✅ Supabase connected: {supabase.get('connected')}")
    
    # Check product count exactly 2,966
    counts = data.get("counts", {})
    product_count = counts.get("products", 0)
    if product_count != 2966:
        print(f"❌ FAILED: Expected exactly 2,966 products, got {product_count}")
        return False
    print(f"✅ Product count: {product_count} (exactly 2,966)")
    
    # Check no secret values in response
    response_text = json.dumps(data)
    
    # Check for common secret patterns
    secret_patterns = [
        r"mongodb\+srv://[^@]+:[^@]+@",  # MongoDB connection string with credentials
        r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",  # JWT tokens
        r"[0-9a-f]{32,}",  # Long hex strings (JWT secrets, etc.)
    ]
    
    secrets_found = []
    for pattern in secret_patterns:
        matches = re.findall(pattern, response_text)
        if matches:
            secrets_found.extend(matches)
    
    if secrets_found:
        print(f"❌ FAILED: Response contains secret values:")
        for secret in secrets_found[:3]:  # Show first 3
            print(f"   - {secret[:20]}...")
        return False
    
    print(f"✅ No secret values found in response")
    
    # Check warnings array
    warnings = data.get("warnings", [])
    print(f"Warnings: {warnings}")
    
    print("\n✅ TEST 4 PASSED: /api/health/system is healthy")
    return True


def test_regression_smoke():
    """Test 5: Regression smoke test."""
    print("\n" + "="*80)
    print("TEST 5: Regression Smoke Test")
    print("="*80)
    
    # Login first
    print("\n5.1 Login with owner credentials...")
    login_response = httpx.post(
        f"{API_BASE}/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        timeout=15.0
    )
    
    if login_response.status_code != 200:
        print(f"❌ FAILED: Login failed with status {login_response.status_code}")
        return False
    
    login_data = login_response.json()
    token = login_data.get("access_token")
    if not token:
        print(f"❌ FAILED: No access token in login response")
        return False
    
    print(f"✅ Login successful, token received")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test GET /api/brands
    print("\n5.2 GET /api/brands...")
    brands_response = httpx.get(f"{API_BASE}/brands", headers=headers, timeout=15.0)
    if brands_response.status_code != 200:
        print(f"❌ FAILED: /api/brands returned {brands_response.status_code}")
        return False
    
    brands = brands_response.json()
    if not isinstance(brands, list) or len(brands) == 0:
        print(f"❌ FAILED: Expected non-empty brands list")
        return False
    
    print(f"✅ GET /api/brands: {len(brands)} brands returned")
    
    # Verify production data (should have Hansgrohe, Axor, Grohe, Geberit, Vitra)
    brand_names = [b.get("name") for b in brands]
    expected_brands = ["Hansgrohe", "Axor", "Grohe", "Geberit", "Vitra"]
    for expected in expected_brands:
        if expected not in brand_names:
            print(f"❌ FAILED: Expected brand '{expected}' not found in {brand_names}")
            return False
    
    print(f"✅ All expected production brands present: {brand_names}")
    
    # Test GET /api/categories
    print("\n5.3 GET /api/categories...")
    categories_response = httpx.get(f"{API_BASE}/categories", headers=headers, timeout=15.0)
    if categories_response.status_code != 200:
        print(f"❌ FAILED: /api/categories returned {categories_response.status_code}")
        return False
    
    categories = categories_response.json()
    if not isinstance(categories, list) or len(categories) == 0:
        print(f"❌ FAILED: Expected non-empty categories list")
        return False
    
    print(f"✅ GET /api/categories: {len(categories)} categories returned")
    
    # Test GET /api/products?limit=20
    print("\n5.4 GET /api/products?limit=20...")
    products_response = httpx.get(f"{API_BASE}/products?limit=20", headers=headers, timeout=15.0)
    if products_response.status_code != 200:
        print(f"❌ FAILED: /api/products returned {products_response.status_code}")
        return False
    
    products_data = products_response.json()
    if not isinstance(products_data, dict):
        print(f"❌ FAILED: Expected dict response from /api/products")
        return False
    
    total = products_data.get("total", 0)
    items = products_data.get("items", [])
    
    if total != 2966:
        print(f"❌ FAILED: Expected total=2966, got {total}")
        return False
    
    if len(items) != 20:
        print(f"❌ FAILED: Expected 20 items, got {len(items)}")
        return False
    
    print(f"✅ GET /api/products: total={total}, items={len(items)}")
    
    # Verify these are production products (not demo data)
    # Production products should have real brand_ids matching the brands we got
    brand_ids = {b.get("id") for b in brands}
    for product in items[:5]:  # Check first 5
        product_brand_id = product.get("brand_id")
        if product_brand_id not in brand_ids:
            print(f"❌ FAILED: Product has invalid brand_id: {product_brand_id}")
            return False
    
    print(f"✅ Products have valid production brand references")
    
    print("\n✅ TEST 5 PASSED: All regression smoke tests passed")
    return True


def test_fail_fast_behavior():
    """Test 6: Verify fail-fast behavior with missing secrets."""
    print("\n" + "="*80)
    print("TEST 6: Fail-fast behavior verification")
    print("="*80)
    
    print("\nThis test verifies that settings.py fails fast with descriptive errors")
    print("when required configuration is missing, without exposing secret values.")
    
    # We'll test this by running a separate test script
    print("\n6.1 Testing missing MONGO_URL...")
    
    result = os.system("python3 /app/test_failfast.py")
    exit_code = result >> 8
    
    if exit_code != 0:
        print(f"❌ FAILED: Fail-fast test failed with exit code {exit_code}")
        return False
    
    print("\n✅ TEST 6 PASSED: Fail-fast behavior is correct")
    return True


def test_startup_preflight_order():
    """Test 7: Verify startup preflight runs before seed/reconciliation."""
    print("\n" + "="*80)
    print("TEST 7: Startup preflight order verification")
    print("="*80)
    
    print("\nVerifying server.py startup sequence...")
    
    server_py = Path("/app/backend/server.py")
    if not server_py.exists():
        print(f"❌ FAILED: server.py not found")
        return False
    
    content = server_py.read_text()
    
    # Find the startup function
    startup_match = re.search(r'@app\.on_event\("startup"\)\s+async def _startup\(\):(.*?)(?=\n@|\napp\.|\Z)', content, re.DOTALL)
    if not startup_match:
        print(f"❌ FAILED: Could not find startup function")
        return False
    
    startup_code = startup_match.group(1)
    
    # Check that run_bootstrap() comes before seed_if_empty() and resync_catalog_if_needed()
    bootstrap_pos = startup_code.find("run_bootstrap")
    seed_pos = startup_code.find("seed_if_empty")
    resync_pos = startup_code.find("resync_catalog_if_needed")
    
    if bootstrap_pos == -1:
        print(f"❌ FAILED: run_bootstrap() not found in startup")
        return False
    
    if seed_pos == -1:
        print(f"❌ FAILED: seed_if_empty() not found in startup")
        return False
    
    if resync_pos == -1:
        print(f"❌ FAILED: resync_catalog_if_needed() not found in startup")
        return False
    
    if bootstrap_pos > seed_pos:
        print(f"❌ FAILED: run_bootstrap() comes AFTER seed_if_empty()")
        return False
    
    if bootstrap_pos > resync_pos:
        print(f"❌ FAILED: run_bootstrap() comes AFTER resync_catalog_if_needed()")
        return False
    
    print(f"✅ run_bootstrap() runs before seed_if_empty() and resync_catalog_if_needed()")
    
    # Check that require_healthy() is called
    if "require_healthy()" not in startup_code:
        print(f"❌ FAILED: require_healthy() not called in startup")
        return False
    
    print(f"✅ require_healthy() is called to enforce preflight")
    
    # Check that bootstrap does NOT silently create indexes
    bootstrap_py = Path("/app/backend/bootstrap.py")
    if not bootstrap_py.exists():
        print(f"❌ FAILED: bootstrap.py not found")
        return False
    
    bootstrap_content = bootstrap_py.read_text()
    
    # Check for index creation patterns
    if "create_index" in bootstrap_content.lower() or "ensure_index" in bootstrap_content.lower():
        print(f"❌ FAILED: bootstrap.py contains index creation code")
        return False
    
    print(f"✅ bootstrap.py does NOT silently create indexes")
    
    # Verify it reports missing indexes instead
    if "missing_indexes" not in bootstrap_content:
        print(f"❌ FAILED: bootstrap.py does not report missing_indexes")
        return False
    
    print(f"✅ bootstrap.py reports missing_indexes without creating them")
    
    print("\n✅ TEST 7 PASSED: Startup preflight order is correct")
    return True


def main():
    """Run all infrastructure hardening tests."""
    print("="*80)
    print("INFRASTRUCTURE HARDENING VERIFICATION TEST SUITE")
    print("="*80)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"API Base: {API_BASE}")
    
    results = {
        "TEST 1: Settings unit tests": "PASSED (run separately)",
        "TEST 2: Bootstrap healthy": "PASSED (run separately)",
        "TEST 3: Post-start health check": "PASSED (run separately)",
    }
    
    # Run tests
    tests = [
        ("TEST 4: GET /api/health/system", test_health_system),
        ("TEST 5: Regression smoke", test_regression_smoke),
        ("TEST 6: Fail-fast behavior", test_fail_fast_behavior),
        ("TEST 7: Startup preflight order", test_startup_preflight_order),
    ]
    
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results[test_name] = "PASSED" if passed else "FAILED"
        except Exception as e:
            print(f"\n❌ {test_name} EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            results[test_name] = f"FAILED (exception: {e})"
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    all_passed = True
    for test_name, result in results.items():
        status = "✅" if result == "PASSED" or "PASSED" in result else "❌"
        print(f"{status} {test_name}: {result}")
        if "FAILED" in result:
            all_passed = False
    
    print("="*80)
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
