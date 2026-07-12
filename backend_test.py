#!/usr/bin/env python3
"""
Performance Sprint 2 — Backend Catalog Query Optimization Testing
Test only backend catalog endpoints with direct localhost requests.
"""
import asyncio
import json
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Set

import httpx

# Test configuration
BASE_URL = "http://127.0.0.1:8001/api"
CREDENTIALS = {
    "owner": {"email": "owner@forge.app", "password": "Forge@2026"},
    "sales": {"email": "sales@forge.app", "password": "Forge@2026"},
}

# Expected catalog totals
EXPECTED_TOTAL_PRODUCTS = 2966
EXPECTED_BRANDS = 5
EXPECTED_CATEGORIES = 26

# Performance targets (warm medians, after startup)
TARGET_LATENCY_MS = 200


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.errors: List[str] = []
        self.timings: Dict[str, List[float]] = {}

    def record_timing(self, endpoint: str, duration_ms: float):
        if endpoint not in self.timings:
            self.timings[endpoint] = []
        self.timings[endpoint].append(duration_ms)

    def pass_test(self, name: str):
        self.passed += 1
        print(f"✅ {name}")

    def fail_test(self, name: str, reason: str):
        self.failed += 1
        error_msg = f"❌ {name}: {reason}"
        print(error_msg)
        self.errors.append(error_msg)

    def warn_test(self, name: str, reason: str):
        self.warnings += 1
        print(f"⚠️  {name}: {reason}")

    def print_summary(self):
        print("\n" + "=" * 80)
        print("PERFORMANCE SPRINT 2 — BACKEND CATALOG OPTIMIZATION TEST SUMMARY")
        print("=" * 80)
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print(f"⚠️  Warnings: {self.warnings}")
        
        if self.timings:
            print("\n" + "-" * 80)
            print("PERFORMANCE METRICS (warm medians, target <200ms)")
            print("-" * 80)
            for endpoint, times in sorted(self.timings.items()):
                if times:
                    median = sorted(times)[len(times) // 2]
                    min_time = min(times)
                    max_time = max(times)
                    status = "✅" if median < TARGET_LATENCY_MS else "⚠️"
                    print(f"{status} {endpoint:50s} median: {median:6.1f}ms  (min: {min_time:6.1f}ms, max: {max_time:6.1f}ms, n={len(times)})")
        
        if self.errors:
            print("\n" + "-" * 80)
            print("FAILED TESTS:")
            print("-" * 80)
            for error in self.errors:
                print(error)
        
        print("\n" + "=" * 80)
        if self.failed == 0:
            print("✅ ALL TESTS PASSED")
        else:
            print(f"❌ {self.failed} TEST(S) FAILED")
        print("=" * 80)


async def login(client: httpx.AsyncClient, email: str, password: str) -> str:
    """Login and return JWT token."""
    response = await client.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "password": password}
    )
    if response.status_code != 200:
        raise Exception(f"Login failed: {response.status_code} {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


async def timed_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    results: TestResults,
    endpoint_name: str,
    **kwargs
) -> tuple[httpx.Response, float]:
    """Make a timed HTTP request and record the duration."""
    start = time.perf_counter()
    response = await client.request(method, url, **kwargs)
    duration_ms = (time.perf_counter() - start) * 1000
    results.record_timing(endpoint_name, duration_ms)
    return response, duration_ms


async def test_endpoint_contracts(client: httpx.AsyncClient, token: str, results: TestResults):
    """Test 1: Verify all catalog GET endpoints return 200 and preserve response contracts."""
    print("\n" + "=" * 80)
    print("TEST 1: ENDPOINT CONTRACTS & STATUS CODES")
    print("=" * 80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test brands
    response, _ = await timed_request(
        client, "GET", f"{BASE_URL}/brands", results, "GET /brands", headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        if isinstance(data, list) and len(data) > 0 and "id" in data[0] and "name" in data[0]:
            results.pass_test("GET /brands returns 200 with correct shape")
        else:
            results.fail_test("GET /brands", f"Invalid response shape: {data}")
    else:
        results.fail_test("GET /brands", f"Status {response.status_code}")
    
    # Test categories
    response, _ = await timed_request(
        client, "GET", f"{BASE_URL}/categories", results, "GET /categories", headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            results.pass_test("GET /categories returns 200 with correct shape")
        else:
            results.fail_test("GET /categories", f"Invalid response shape")
    else:
        results.fail_test("GET /categories", f"Status {response.status_code}")
    
    # Test products with various parameters
    test_cases = [
        ("popular skip=0", {"sort": "popular", "limit": 60, "skip": 0}),
        ("popular skip=60", {"sort": "popular", "limit": 60, "skip": 60}),
        ("name sort", {"sort": "name", "limit": 60, "skip": 0}),
        ("price_asc", {"sort": "price_asc", "limit": 60, "skip": 0}),
        ("price_desc", {"sort": "price_desc", "limit": 60, "skip": 0}),
        ("recent", {"sort": "recent", "limit": 60, "skip": 0}),
        ("search basin", {"q": "basin", "limit": 60, "skip": 0}),
    ]
    
    for name, params in test_cases:
        response, _ = await timed_request(
            client, "GET", f"{BASE_URL}/products", results, f"GET /products {name}",
            headers=headers, params=params
        )
        if response.status_code == 200:
            data = response.json()
            if "total" in data and "items" in data and isinstance(data["items"], list):
                results.pass_test(f"GET /products {name} returns 200 with {{total, items}}")
            else:
                results.fail_test(f"GET /products {name}", f"Invalid response shape")
        else:
            results.fail_test(f"GET /products {name}", f"Status {response.status_code}")
    
    # Test hierarchy
    response, _ = await timed_request(
        client, "GET", f"{BASE_URL}/catalog/hierarchy", results, "GET /catalog/hierarchy",
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        if "tree" in data:
            results.pass_test("GET /catalog/hierarchy returns 200 with {tree}")
        else:
            results.fail_test("GET /catalog/hierarchy", "Missing 'tree' field")
    else:
        results.fail_test("GET /catalog/hierarchy", f"Status {response.status_code}")
    
    # Test families
    response, _ = await timed_request(
        client, "GET", f"{BASE_URL}/products/families", results, "GET /products/families",
        headers=headers, params={"limit": 60, "skip": 0}
    )
    if response.status_code == 200:
        data = response.json()
        if "total" in data and "items" in data:
            results.pass_test("GET /products/families returns 200 with {total, items}")
        else:
            results.fail_test("GET /products/families", "Invalid response shape")
    else:
        results.fail_test("GET /products/families", f"Status {response.status_code}")
    
    # Test facets
    response, _ = await timed_request(
        client, "GET", f"{BASE_URL}/catalog/facets", results, "GET /catalog/facets",
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        if "brands" in data and "categories" in data:
            results.pass_test("GET /catalog/facets returns 200 with facet buckets")
        else:
            results.fail_test("GET /catalog/facets", "Missing facet fields")
    else:
        results.fail_test("GET /catalog/facets", f"Status {response.status_code}")
    
    # Test search
    response, _ = await timed_request(
        client, "GET", f"{BASE_URL}/catalog/search", results, "GET /catalog/search",
        headers=headers, params={"q": "basin", "limit": 30}
    )
    if response.status_code == 200:
        data = response.json()
        if "query" in data and "total" in data and "items" in data:
            results.pass_test("GET /catalog/search returns 200 with {query, total, items}")
        else:
            results.fail_test("GET /catalog/search", "Invalid response shape")
    else:
        results.fail_test("GET /catalog/search", f"Status {response.status_code}")
    
    # Test recent/frequent
    response, _ = await timed_request(
        client, "GET", f"{BASE_URL}/products/recent", results, "GET /products/recent",
        headers=headers, params={"limit": 12}
    )
    if response.status_code == 200:
        results.pass_test("GET /products/recent returns 200")
    else:
        results.fail_test("GET /products/recent", f"Status {response.status_code}")
    
    response, _ = await timed_request(
        client, "GET", f"{BASE_URL}/products/frequent", results, "GET /products/frequent",
        headers=headers, params={"limit": 12}
    )
    if response.status_code == 200:
        results.pass_test("GET /products/frequent returns 200")
    else:
        results.fail_test("GET /products/frequent", f"Status {response.status_code}")


async def test_performance_targets(client: httpx.AsyncClient, token: str, results: TestResults):
    """Test 2: Measure warm medians for key endpoints (target <200ms)."""
    print("\n" + "=" * 80)
    print("TEST 2: PERFORMANCE TARGETS (warm medians, 5 repetitions)")
    print("=" * 80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Warm up cache with 2 requests
    for _ in range(2):
        await client.get(f"{BASE_URL}/products", headers=headers, params={"sort": "popular", "limit": 60, "skip": 0})
    
    # Measure key endpoints 5 times each
    test_cases = [
        ("products popular skip=0", "GET", f"{BASE_URL}/products", {"sort": "popular", "limit": 60, "skip": 0}),
        ("products popular skip=60", "GET", f"{BASE_URL}/products", {"sort": "popular", "limit": 60, "skip": 60}),
        ("products popular skip=2900", "GET", f"{BASE_URL}/products", {"sort": "popular", "limit": 60, "skip": 2900}),
        ("products name skip=0", "GET", f"{BASE_URL}/products", {"sort": "name", "limit": 60, "skip": 0}),
        ("products price_asc", "GET", f"{BASE_URL}/products", {"sort": "price_asc", "limit": 60, "skip": 0}),
        ("products price_desc", "GET", f"{BASE_URL}/products", {"sort": "price_desc", "limit": 60, "skip": 0}),
        ("products recent", "GET", f"{BASE_URL}/products", {"sort": "recent", "limit": 60, "skip": 0}),
        ("search basin", "GET", f"{BASE_URL}/catalog/search", {"q": "basin", "limit": 30}),
        ("families", "GET", f"{BASE_URL}/products/families", {"limit": 60, "skip": 0}),
        ("hierarchy", "GET", f"{BASE_URL}/catalog/hierarchy", {}),
        ("facets", "GET", f"{BASE_URL}/catalog/facets", {}),
        ("brands", "GET", f"{BASE_URL}/brands", {}),
        ("categories", "GET", f"{BASE_URL}/categories", {}),
    ]
    
    for name, method, url, params in test_cases:
        for _ in range(5):
            await timed_request(
                client, method, url, results, name,
                headers=headers, params=params
            )
    
    # Check if medians meet target
    for endpoint, times in results.timings.items():
        if times:
            median = sorted(times)[len(times) // 2]
            if median < TARGET_LATENCY_MS:
                results.pass_test(f"Performance: {endpoint} median {median:.1f}ms < {TARGET_LATENCY_MS}ms")
            else:
                results.warn_test(f"Performance: {endpoint} median {median:.1f}ms", f"Exceeds {TARGET_LATENCY_MS}ms target")


async def test_pagination_integrity(client: httpx.AsyncClient, token: str, results: TestResults):
    """Test 3: Exhaustively page popular results to prove 2966 unique IDs, no gaps/duplicates."""
    print("\n" + "=" * 80)
    print("TEST 3: PAGINATION INTEGRITY (exhaustive popular paging)")
    print("=" * 80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get first page to check total
    response = await client.get(
        f"{BASE_URL}/products",
        headers=headers,
        params={"sort": "popular", "limit": 60, "skip": 0}
    )
    data = response.json()
    total = data.get("total", 0)
    
    if total == EXPECTED_TOTAL_PRODUCTS:
        results.pass_test(f"Total products = {EXPECTED_TOTAL_PRODUCTS}")
    else:
        results.fail_test("Total products", f"Expected {EXPECTED_TOTAL_PRODUCTS}, got {total}")
    
    # Exhaustively page through all products
    all_ids: List[str] = []
    skip = 0
    limit = 60
    
    while skip < total:
        response = await client.get(
            f"{BASE_URL}/products",
            headers=headers,
            params={"sort": "popular", "limit": limit, "skip": skip}
        )
        data = response.json()
        items = data.get("items", [])
        
        if not items:
            break
        
        for item in items:
            all_ids.append(item["id"])
        
        skip += limit
    
    # Check counts
    if len(all_ids) == EXPECTED_TOTAL_PRODUCTS:
        results.pass_test(f"Exhaustive paging returned {EXPECTED_TOTAL_PRODUCTS} rows")
    else:
        results.fail_test("Exhaustive paging", f"Expected {EXPECTED_TOTAL_PRODUCTS} rows, got {len(all_ids)}")
    
    # Check for unique IDs
    unique_ids = set(all_ids)
    if len(unique_ids) == EXPECTED_TOTAL_PRODUCTS:
        results.pass_test(f"All {EXPECTED_TOTAL_PRODUCTS} IDs are unique")
    else:
        results.fail_test("Unique IDs", f"Expected {EXPECTED_TOTAL_PRODUCTS} unique, got {len(unique_ids)}")
    
    # Check for duplicates
    id_counts = Counter(all_ids)
    duplicates = {id_: count for id_, count in id_counts.items() if count > 1}
    if not duplicates:
        results.pass_test("No duplicate IDs found")
    else:
        results.fail_test("Duplicate IDs", f"Found {len(duplicates)} duplicates: {list(duplicates.keys())[:5]}")
    
    # Check last page
    last_skip = (total // limit) * limit
    response = await client.get(
        f"{BASE_URL}/products",
        headers=headers,
        params={"sort": "popular", "limit": limit, "skip": last_skip}
    )
    data = response.json()
    last_page_items = data.get("items", [])
    expected_last_page = total - last_skip
    
    if len(last_page_items) == expected_last_page:
        results.pass_test(f"Last page (skip={last_skip}) has {expected_last_page} items")
    else:
        results.fail_test("Last page", f"Expected {expected_last_page} items, got {len(last_page_items)}")


async def test_sort_filter_stability(client: httpx.AsyncClient, token: str, results: TestResults):
    """Test 4: Verify page ordering/filter parity for popular, recent, name, price_asc, price_desc, q=basin."""
    print("\n" + "=" * 80)
    print("TEST 4: SORT & FILTER STABILITY")
    print("=" * 80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test each sort mode
    sort_modes = ["popular", "recent", "name", "price_asc", "price_desc"]
    
    for sort_mode in sort_modes:
        # Get first page
        response = await client.get(
            f"{BASE_URL}/products",
            headers=headers,
            params={"sort": sort_mode, "limit": 60, "skip": 0}
        )
        data = response.json()
        first_page_ids = [item["id"] for item in data.get("items", [])]
        
        # Get first page again
        response = await client.get(
            f"{BASE_URL}/products",
            headers=headers,
            params={"sort": sort_mode, "limit": 60, "skip": 0}
        )
        data = response.json()
        second_page_ids = [item["id"] for item in data.get("items", [])]
        
        # Check stability
        if first_page_ids == second_page_ids:
            results.pass_test(f"Sort {sort_mode}: deterministic (same IDs in same order)")
        else:
            results.fail_test(f"Sort {sort_mode}", "Non-deterministic ordering")
    
    # Test search filter stability
    response = await client.get(
        f"{BASE_URL}/products",
        headers=headers,
        params={"q": "basin", "limit": 60, "skip": 0}
    )
    data1 = response.json()
    
    response = await client.get(
        f"{BASE_URL}/products",
        headers=headers,
        params={"q": "basin", "limit": 60, "skip": 0}
    )
    data2 = response.json()
    
    if data1.get("total") == data2.get("total"):
        results.pass_test(f"Search q=basin: deterministic total ({data1.get('total')} results)")
    else:
        results.fail_test("Search q=basin", f"Non-deterministic total: {data1.get('total')} vs {data2.get('total')}")
    
    ids1 = [item["id"] for item in data1.get("items", [])]
    ids2 = [item["id"] for item in data2.get("items", [])]
    
    if ids1 == ids2:
        results.pass_test("Search q=basin: deterministic ordering")
    else:
        results.fail_test("Search q=basin", "Non-deterministic ordering")


async def test_related_endpoints(client: httpx.AsyncClient, token: str, results: TestResults):
    """Test 5: Product detail, media, alternates, complete-set endpoints."""
    print("\n" + "=" * 80)
    print("TEST 5: PRODUCT DETAIL & RELATED ENDPOINTS")
    print("=" * 80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get a sample product ID
    response = await client.get(
        f"{BASE_URL}/products",
        headers=headers,
        params={"sort": "popular", "limit": 1, "skip": 0}
    )
    data = response.json()
    items = data.get("items", [])
    
    if not items:
        results.fail_test("Sample product", "No products found")
        return
    
    product_id = items[0]["id"]
    
    # Test product detail
    response, _ = await timed_request(
        client, "GET", f"{BASE_URL}/products/{product_id}", results, "GET /products/{id}",
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        if "id" in data and "name" in data:
            results.pass_test(f"GET /products/{{id}} returns product detail")
        else:
            results.fail_test("GET /products/{id}", "Invalid response shape")
    else:
        results.fail_test("GET /products/{id}", f"Status {response.status_code}")
    
    # Test alternates
    response, _ = await timed_request(
        client, "GET", f"{BASE_URL}/products/{product_id}/alternates", results, "GET /products/{id}/alternates",
        headers=headers, params={"limit": 12}
    )
    if response.status_code == 200:
        data = response.json()
        if "source_product_id" in data and "items" in data and "tiers" in data:
            results.pass_test("GET /products/{id}/alternates returns {source_product_id, items, tiers}")
        else:
            results.fail_test("GET /products/{id}/alternates", "Invalid response shape")
    else:
        results.fail_test("GET /products/{id}/alternates", f"Status {response.status_code}")
    
    # Test complete-the-set
    response, _ = await timed_request(
        client, "GET", f"{BASE_URL}/products/{product_id}/complete-the-set", results, "GET /products/{id}/complete-the-set",
        headers=headers, params={"limit": 12}
    )
    if response.status_code == 200:
        data = response.json()
        if "source_product_id" in data and "items" in data:
            results.pass_test("GET /products/{id}/complete-the-set returns {source_product_id, items}")
        else:
            results.fail_test("GET /products/{id}/complete-the-set", "Invalid response shape")
    else:
        results.fail_test("GET /products/{id}/complete-the-set", f"Status {response.status_code}")


async def test_bootstrap_indexes(results: TestResults):
    """Test 6: Bootstrap reports no missing indexes."""
    print("\n" + "=" * 80)
    print("TEST 6: BOOTSTRAP & INDEX VALIDATION")
    print("=" * 80)
    
    # Run bootstrap.py
    proc = await asyncio.create_subprocess_exec(
        "python", "/app/backend/bootstrap.py",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    
    if proc.returncode == 0:
        output = stdout.decode()
        try:
            data = json.loads(output)
            if data.get("healthy"):
                results.pass_test("Bootstrap reports healthy=true")
            else:
                results.fail_test("Bootstrap", "healthy=false")
            
            missing_indexes = data.get("missing_indexes", [])
            if not missing_indexes:
                results.pass_test("Bootstrap reports no missing indexes")
            else:
                results.fail_test("Bootstrap", f"Missing indexes: {missing_indexes}")
        except json.JSONDecodeError:
            results.fail_test("Bootstrap", f"Invalid JSON output: {output[:200]}")
    else:
        results.fail_test("Bootstrap", f"Exit code {proc.returncode}: {stderr.decode()[:200]}")


async def test_focused_regression(results: TestResults):
    """Test 7: Run focused backend regression tests."""
    print("\n" + "=" * 80)
    print("TEST 7: FOCUSED BACKEND REGRESSION")
    print("=" * 80)
    
    # Check if test file exists
    import os
    test_files = [
        "/app/backend/tests/test_catalog_service.py",
        "/app/backend/tests/test_auth_cache.py",
    ]
    
    found_tests = [f for f in test_files if os.path.exists(f)]
    
    if not found_tests:
        results.warn_test("Focused regression", "No test files found")
        return
    
    # Run pytest
    proc = await asyncio.create_subprocess_exec(
        "python", "-m", "pytest", "-xvs", *found_tests,
        cwd="/app/backend",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    
    output = stdout.decode() + stderr.decode()
    
    if proc.returncode == 0:
        # Count passed tests
        import re
        passed = len(re.findall(r"PASSED", output))
        results.pass_test(f"Focused regression: {passed} tests passed")
    else:
        results.fail_test("Focused regression", f"Exit code {proc.returncode}")
        print(output[:1000])


async def main():
    results = TestResults()
    
    print("=" * 80)
    print("PERFORMANCE SPRINT 2 — BACKEND CATALOG QUERY OPTIMIZATION")
    print("Testing backend catalog endpoints with direct localhost requests")
    print("=" * 80)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Login
            print("\n🔐 Logging in as owner@forge.app...")
            token = await login(client, **CREDENTIALS["owner"])
            print("✅ Login successful")
            
            # Run all tests
            await test_endpoint_contracts(client, token, results)
            await test_performance_targets(client, token, results)
            await test_pagination_integrity(client, token, results)
            await test_sort_filter_stability(client, token, results)
            await test_related_endpoints(client, token, results)
            
        except Exception as e:
            results.fail_test("Test execution", str(e))
            import traceback
            traceback.print_exc()
    
    # Run non-HTTP tests
    await test_bootstrap_indexes(results)
    await test_focused_regression(results)
    
    # Print summary
    results.print_summary()
    
    # Exit with appropriate code
    return 0 if results.failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
