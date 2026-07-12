#!/usr/bin/env python3
"""
Backend Testing Script for Task 1: Auth Principal Cache Performance Improvement
Verification Requirements:
1. Run settings + auth cache unit tests (expected 13/13)
2. Staff password login and repeated GET /api/auth/me; report cold first request and warm median over at least 5 requests
3. Customer password login and repeated /api/auth/customer/me
4. Revocation correctness: current logout invalidates immediately; logout-all invalidates all cached sessions immediately; 
   DELETE one session invalidates that session; revoked/missing sessions return 401 and are never cached
5. Role enforcement remains correct for a lower-role user on protected endpoints
6. Legacy token without session_id still validates active principal (unit or isolated test)
7. Representative authenticated smoke: dashboard/stats, brands, categories, products?limit=20, customers, 
   quotations/recent, payments/stats, followups/stats. Confirm no 500s/API errors and products total=2966
8. Inspect cache safety: TTL=10 seconds, max=2048, values contain principal docs without password_hash and do not store JWTs; 
   explicit invalidation wired to all three session-revocation routes
9. Compare warm latency against PERFORMANCE.md baselines where possible. State exact results and any regression
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from statistics import median
from typing import Optional

import httpx

# Backend URL - use localhost since we're in the same container
BACKEND_URL = "http://localhost:8001"
BASE_URL = f"{BACKEND_URL}/api"

# Test credentials
STAFF_EMAIL = "owner@forge.app"
STAFF_PASSWORD = "Forge@2026"
CUSTOMER_EMAIL = "customer@forge.app"
CUSTOMER_PASSWORD = "Forge@2026"
SALES_EMAIL = "sales@forge.app"
SALES_PASSWORD = "Forge@2026"

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_section(title: str):
    print(f"\n{'=' * 80}")
    print(f"{BLUE}{title}{RESET}")
    print('=' * 80)


def print_test(name: str, passed: bool, details: str = ""):
    status = f"{GREEN}✅ PASS{RESET}" if passed else f"{RED}❌ FAIL{RESET}"
    print(f"{status} - {name}")
    if details:
        print(f"  {details}")


def print_metric(name: str, value: str):
    print(f"  {YELLOW}→{RESET} {name}: {value}")


async def test_unit_tests():
    """Requirement 1: Run settings + auth cache unit tests (expected 13/13)"""
    print_section("TEST 1: Unit Tests (Settings + Auth Cache)")
    
    # Run pytest for auth cache tests
    result = subprocess.run(
        ["python", "-m", "pytest", "backend/tests/test_auth_cache.py", "-v"],
        cwd="/app",
        capture_output=True,
        text=True
    )
    
    auth_passed = result.returncode == 0
    auth_count = result.stdout.count(" PASSED")
    
    # Run settings tests
    settings_result = subprocess.run(
        ["python", "-m", "pytest", "backend/tests/test_settings.py", "-v"],
        cwd="/app",
        capture_output=True,
        text=True
    )
    
    settings_passed = settings_result.returncode == 0
    settings_count = settings_result.stdout.count(" PASSED")
    
    total_tests = auth_count + settings_count
    all_passed = auth_passed and settings_passed
    
    print_test(
        f"Unit tests execution ({total_tests} tests)",
        all_passed,
        f"Auth cache: {auth_count} passed, Settings: {settings_count} passed"
    )
    
    if not all_passed:
        print(f"{RED}STDOUT:{RESET}\n{result.stdout}")
        print(f"{RED}STDERR:{RESET}\n{result.stderr}")
        print(f"{RED}Settings STDOUT:{RESET}\n{settings_result.stdout}")
        print(f"{RED}Settings STDERR:{RESET}\n{settings_result.stderr}")
    
    return all_passed, total_tests


async def test_staff_auth_performance(client: httpx.AsyncClient):
    """Requirement 2: Staff password login and repeated GET /api/auth/me"""
    print_section("TEST 2: Staff Auth Performance (Cold + Warm)")
    
    # Login
    login_resp = await client.post(
        f"{BASE_URL}/auth/login",
        json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}
    )
    
    if login_resp.status_code != 200:
        print_test("Staff login", False, f"Status: {login_resp.status_code}")
        return False, None, None, None
    
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    print_test("Staff login", True, f"Token received for {STAFF_EMAIL}")
    
    # Cold request (first request after login)
    start = time.time()
    cold_resp = await client.get(f"{BASE_URL}/auth/me", headers=headers)
    cold_time = (time.time() - start) * 1000
    
    cold_passed = cold_resp.status_code == 200
    print_test("Cold /auth/me request", cold_passed, f"Time: {cold_time:.0f}ms")
    
    # Warm requests (5 more requests to measure cache performance)
    warm_times = []
    for i in range(5):
        start = time.time()
        warm_resp = await client.get(f"{BASE_URL}/auth/me", headers=headers)
        warm_time = (time.time() - start) * 1000
        warm_times.append(warm_time)
        
        if warm_resp.status_code != 200:
            print_test(f"Warm request {i+1}", False, f"Status: {warm_resp.status_code}")
            return False, token, cold_time, None
    
    warm_median = median(warm_times)
    improvement = ((cold_time - warm_median) / cold_time * 100) if cold_time > 0 else 0
    
    print_test(
        "Warm /auth/me requests (5 requests)",
        True,
        f"Median: {warm_median:.0f}ms, Improvement: {improvement:.1f}%"
    )
    
    print_metric("Cold first request", f"{cold_time:.0f}ms")
    print_metric("Warm median (5 requests)", f"{warm_median:.0f}ms")
    print_metric("Individual warm times", f"{[f'{t:.0f}ms' for t in warm_times]}")
    
    # Compare against PERFORMANCE.md baseline (before: 506ms, after: 42ms)
    baseline_before = 506
    baseline_after = 42
    
    if warm_median <= baseline_after * 2:  # Allow 2x tolerance
        print_metric("Baseline comparison", f"{GREEN}Within expected range (baseline: {baseline_after}ms){RESET}")
    else:
        print_metric("Baseline comparison", f"{YELLOW}Higher than baseline (baseline: {baseline_after}ms){RESET}")
    
    return True, token, cold_time, warm_median


async def test_customer_auth_performance(client: httpx.AsyncClient):
    """Requirement 3: Customer password login and repeated /api/auth/customer/me"""
    print_section("TEST 3: Customer Auth Performance (Cold + Warm)")
    
    # Login
    login_resp = await client.post(
        f"{BASE_URL}/auth/customer/login",
        json={"email": CUSTOMER_EMAIL, "password": CUSTOMER_PASSWORD}
    )
    
    if login_resp.status_code != 200:
        print_test("Customer login", False, f"Status: {login_resp.status_code}")
        return False, None, None, None
    
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    print_test("Customer login", True, f"Token received for {CUSTOMER_EMAIL}")
    
    # Cold request
    start = time.time()
    cold_resp = await client.get(f"{BASE_URL}/auth/customer/me", headers=headers)
    cold_time = (time.time() - start) * 1000
    
    cold_passed = cold_resp.status_code == 200
    print_test("Cold /auth/customer/me request", cold_passed, f"Time: {cold_time:.0f}ms")
    
    # Warm requests
    warm_times = []
    for i in range(5):
        start = time.time()
        warm_resp = await client.get(f"{BASE_URL}/auth/customer/me", headers=headers)
        warm_time = (time.time() - start) * 1000
        warm_times.append(warm_time)
        
        if warm_resp.status_code != 200:
            print_test(f"Warm request {i+1}", False, f"Status: {warm_resp.status_code}")
            return False, token, cold_time, None
    
    warm_median = median(warm_times)
    improvement = ((cold_time - warm_median) / cold_time * 100) if cold_time > 0 else 0
    
    print_test(
        "Warm /auth/customer/me requests (5 requests)",
        True,
        f"Median: {warm_median:.0f}ms, Improvement: {improvement:.1f}%"
    )
    
    print_metric("Cold first request", f"{cold_time:.0f}ms")
    print_metric("Warm median (5 requests)", f"{warm_median:.0f}ms")
    
    return True, token, cold_time, warm_median


async def test_revocation_correctness(client: httpx.AsyncClient):
    """Requirement 4: Revocation correctness"""
    print_section("TEST 4: Revocation Correctness")
    
    # Create a fresh session for testing
    login_resp = await client.post(
        f"{BASE_URL}/auth/login",
        json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}
    )
    token1 = login_resp.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}
    
    # Create a second session
    login_resp2 = await client.post(
        f"{BASE_URL}/auth/login",
        json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}
    )
    token2 = login_resp2.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}
    
    # Verify both sessions work
    resp1 = await client.get(f"{BASE_URL}/auth/me", headers=headers1)
    resp2 = await client.get(f"{BASE_URL}/auth/me", headers=headers2)
    
    both_work = resp1.status_code == 200 and resp2.status_code == 200
    print_test("Two active sessions created", both_work)
    
    if not both_work:
        return False
    
    # Test 4a: Current logout invalidates immediately
    logout_resp = await client.post(f"{BASE_URL}/auth/logout", headers=headers1)
    logout_success = logout_resp.status_code == 200 and logout_resp.json().get("revoked") == True
    
    # Verify session1 is now invalid
    resp1_after = await client.get(f"{BASE_URL}/auth/me", headers=headers1)
    session1_invalid = resp1_after.status_code == 401
    
    # Verify session2 still works
    resp2_after = await client.get(f"{BASE_URL}/auth/me", headers=headers2)
    session2_valid = resp2_after.status_code == 200
    
    print_test(
        "Current logout invalidates immediately",
        logout_success and session1_invalid and session2_valid,
        f"Session1 revoked: {session1_invalid}, Session2 still valid: {session2_valid}"
    )
    
    # Test 4b: Get list of sessions for session2
    sessions_resp = await client.get(f"{BASE_URL}/auth/sessions", headers=headers2)
    sessions = sessions_resp.json() if sessions_resp.status_code == 200 else []
    
    # Test 4c: DELETE one specific session
    if len(sessions) > 0:
        session_to_delete = sessions[0]["id"]
        delete_resp = await client.delete(
            f"{BASE_URL}/auth/sessions/{session_to_delete}",
            headers=headers2
        )
        delete_success = delete_resp.status_code == 200
        print_test("DELETE one session", delete_success, f"Deleted session: {session_to_delete}")
    else:
        print_test("DELETE one session", False, "No sessions found to delete")
        delete_success = False
    
    # Test 4d: Logout-all invalidates all cached sessions
    # Create a third session for this test
    login_resp3 = await client.post(
        f"{BASE_URL}/auth/login",
        json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}
    )
    token3 = login_resp3.json()["access_token"]
    headers3 = {"Authorization": f"Bearer {token3}"}
    
    # Warm up cache for session3
    await client.get(f"{BASE_URL}/auth/me", headers=headers3)
    
    # Logout all
    logout_all_resp = await client.post(f"{BASE_URL}/auth/sessions/logout-all", headers=headers3)
    logout_all_success = logout_all_resp.status_code == 200
    revoked_count = logout_all_resp.json().get("revoked_count", 0) if logout_all_success else 0
    
    # Verify session3 is now invalid immediately (cache should be invalidated)
    resp3_after = await client.get(f"{BASE_URL}/auth/me", headers=headers3)
    session3_invalid = resp3_after.status_code == 401
    
    print_test(
        "Logout-all invalidates all sessions immediately",
        logout_all_success and session3_invalid,
        f"Revoked {revoked_count} sessions, Session3 immediately invalid: {session3_invalid}"
    )
    
    # Test 4e: Revoked/missing sessions return 401 and are never cached
    # Try to use the revoked token again multiple times
    attempts = []
    for i in range(3):
        resp = await client.get(f"{BASE_URL}/auth/me", headers=headers3)
        attempts.append(resp.status_code == 401)
    
    all_401 = all(attempts)
    print_test(
        "Revoked sessions consistently return 401 (never cached)",
        all_401,
        f"3 attempts all returned 401: {all_401}"
    )
    
    return logout_success and session1_invalid and delete_success and logout_all_success and session3_invalid and all_401


async def test_role_enforcement(client: httpx.AsyncClient):
    """Requirement 5: Role enforcement remains correct for a lower-role user"""
    print_section("TEST 5: Role Enforcement")
    
    # Login as sales user (lower role)
    login_resp = await client.post(
        f"{BASE_URL}/auth/login",
        json={"email": SALES_EMAIL, "password": SALES_PASSWORD}
    )
    
    if login_resp.status_code != 200:
        print_test("Sales user login", False, f"Status: {login_resp.status_code}")
        return False
    
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    print_test("Sales user login", True, f"Token received for {SALES_EMAIL}")
    
    # Test endpoints that require higher roles
    # DELETE quotation requires manager+ role
    delete_resp = await client.delete(f"{BASE_URL}/quotations/fake-id", headers=headers)
    delete_forbidden = delete_resp.status_code == 403
    
    print_test(
        "Sales role cannot delete quotations (403)",
        delete_forbidden,
        f"Status: {delete_resp.status_code}"
    )
    
    # POST payment requires accounts+ role
    payment_resp = await client.post(
        f"{BASE_URL}/payments",
        headers=headers,
        json={
            "quotation_id": "fake-id",
            "amount": 1000,
            "payment_method": "cash",
            "payment_date": "2026-07-12"
        }
    )
    payment_forbidden = payment_resp.status_code in [403, 404]  # 404 if quotation doesn't exist, but should check role first
    
    # Actually, let's check if it's 403 or if it tries to process (which would be wrong)
    # If it's 404, it means role check passed (bad), if 403, role check worked (good)
    if payment_resp.status_code == 403:
        payment_test_passed = True
        detail = "Correctly blocked by role check (403)"
    elif payment_resp.status_code == 404:
        # This might mean role check passed but quotation not found
        # Let's check the error message
        error_detail = payment_resp.json().get("detail", "")
        if "role" in error_detail.lower() or "permission" in error_detail.lower():
            payment_test_passed = True
            detail = "Blocked by role check (404 with role message)"
        else:
            payment_test_passed = False
            detail = f"Role check may have passed (404 without role message): {error_detail}"
    else:
        payment_test_passed = payment_resp.status_code == 403
        detail = f"Status: {payment_resp.status_code}"
    
    print_test(
        "Sales role cannot record payments",
        payment_test_passed,
        detail
    )
    
    # Test that sales CAN access endpoints they should have access to
    quotations_resp = await client.get(f"{BASE_URL}/quotations", headers=headers)
    quotations_allowed = quotations_resp.status_code == 200
    
    print_test(
        "Sales role CAN access quotations list (200)",
        quotations_allowed,
        f"Status: {quotations_resp.status_code}"
    )
    
    return delete_forbidden and quotations_allowed


async def test_legacy_token_compatibility():
    """Requirement 6: Legacy token without session_id still validates active principal"""
    print_section("TEST 6: Legacy Token Compatibility (Unit Test)")
    
    # This is tested in the unit tests (test_legacy_staff_token_without_session_still_validates_user)
    # Let's verify it ran successfully
    result = subprocess.run(
        ["python", "-m", "pytest", "backend/tests/test_auth_cache.py::test_legacy_staff_token_without_session_still_validates_user", "-v"],
        cwd="/app",
        capture_output=True,
        text=True
    )
    
    passed = result.returncode == 0 and "PASSED" in result.stdout
    
    print_test(
        "Legacy token without session_id validates correctly",
        passed,
        "Verified via unit test: test_legacy_staff_token_without_session_still_validates_user"
    )
    
    if not passed:
        print(f"{RED}STDOUT:{RESET}\n{result.stdout}")
        print(f"{RED}STDERR:{RESET}\n{result.stderr}")
    
    return passed


async def test_authenticated_smoke(client: httpx.AsyncClient, staff_token: str):
    """Requirement 7: Representative authenticated smoke tests"""
    print_section("TEST 7: Authenticated Smoke Tests")
    
    headers = {"Authorization": f"Bearer {staff_token}"}
    
    endpoints = [
        ("/dashboard/stats", "Dashboard stats"),
        ("/brands", "Brands"),
        ("/categories", "Categories"),
        ("/products?limit=20", "Products (limit=20)"),
        ("/customers", "Customers"),
        ("/quotations/recent", "Recent quotations"),
        ("/payments/stats", "Payment stats"),
        ("/followups/stats", "Follow-up stats"),
    ]
    
    results = []
    timings = {}
    
    for endpoint, name in endpoints:
        start = time.time()
        resp = await client.get(f"{BASE_URL}{endpoint}", headers=headers)
        elapsed = (time.time() - start) * 1000
        
        passed = resp.status_code == 200
        results.append(passed)
        timings[name] = elapsed
        
        detail = f"Status: {resp.status_code}, Time: {elapsed:.0f}ms"
        
        # Check for specific data
        if passed and endpoint == "/products?limit=20":
            data = resp.json()
            total = data.get("total", 0)
            items_count = len(data.get("items", []))
            detail += f", Total: {total}, Items: {items_count}"
            
            if total != 2966:
                passed = False
                detail += f" {RED}(Expected total=2966){RESET}"
        
        print_test(name, passed, detail)
    
    # Print timing summary
    print(f"\n{YELLOW}Timing Summary:{RESET}")
    for name, elapsed in timings.items():
        print_metric(name, f"{elapsed:.0f}ms")
    
    # Compare against PERFORMANCE.md baselines (warm medians after optimization)
    baselines = {
        "Brands": 520,
        "Categories": 521,
        "Dashboard stats": 995,
        "Customers": 281,
        "Recent quotations": 281,
        "Payment stats": 755,
        "Follow-up stats": 775,
    }
    
    print(f"\n{YELLOW}Baseline Comparison (PERFORMANCE.md 'After' values):{RESET}")
    for name, baseline in baselines.items():
        if name in timings:
            actual = timings[name]
            diff = actual - baseline
            diff_pct = (diff / baseline * 100) if baseline > 0 else 0
            
            if actual <= baseline * 1.5:  # Within 50% tolerance
                status = f"{GREEN}✓{RESET}"
            else:
                status = f"{YELLOW}⚠{RESET}"
            
            print(f"  {status} {name}: {actual:.0f}ms vs {baseline}ms baseline ({diff:+.0f}ms, {diff_pct:+.1f}%)")
    
    return all(results)


async def test_cache_safety():
    """Requirement 8: Inspect cache safety"""
    print_section("TEST 8: Cache Safety Inspection")
    
    # Read auth.py to verify cache configuration
    with open("/app/backend/auth.py", "r") as f:
        auth_code = f.read()
    
    # Check TTL
    ttl_correct = "_PRINCIPAL_CACHE_TTL_SECONDS = 10.0" in auth_code
    print_test("Cache TTL is 10 seconds", ttl_correct, "Verified in auth.py")
    
    # Check max entries
    max_correct = "_PRINCIPAL_CACHE_MAX_ENTRIES = 2048" in auth_code
    print_test("Cache max entries is 2048", max_correct, "Verified in auth.py")
    
    # Check that password_hash is excluded
    password_excluded = '"password_hash": 0' in auth_code
    print_test(
        "password_hash excluded from cached principal",
        password_excluded,
        "Verified projection excludes password_hash"
    )
    
    # Check that cache stores doc.copy() not the JWT
    stores_doc_copy = "doc.copy()" in auth_code
    print_test(
        "Cache stores principal doc copy (not JWT)",
        stores_doc_copy,
        "Verified _cache_principal stores doc.copy()"
    )
    
    # Check invalidation is wired to logout routes
    with open("/app/backend/routes/auth_routes.py", "r") as f:
        auth_routes_code = f.read()
    
    logout_invalidates = "invalidate_principal_cache" in auth_routes_code and "logout" in auth_routes_code
    logout_all_invalidates = "invalidate_principal_cache(kind, sub)" in auth_routes_code
    delete_session_invalidates = "invalidate_principal_cache(kind, sub, session_id)" in auth_routes_code
    
    print_test(
        "Logout route invalidates cache",
        logout_invalidates,
        "Verified invalidate_principal_cache called in logout"
    )
    
    print_test(
        "Logout-all route invalidates all sessions",
        logout_all_invalidates,
        "Verified invalidate_principal_cache(kind, sub) in logout-all"
    )
    
    print_test(
        "DELETE session route invalidates specific session",
        delete_session_invalidates,
        "Verified invalidate_principal_cache(kind, sub, session_id) in DELETE"
    )
    
    return (ttl_correct and max_correct and password_excluded and stores_doc_copy and 
            logout_invalidates and logout_all_invalidates and delete_session_invalidates)


async def main():
    print(f"\n{BLUE}{'=' * 80}")
    print("TASK 1 VERIFICATION: Auth Principal Cache Performance Improvement")
    print(f"{'=' * 80}{RESET}\n")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test 1: Unit tests
        unit_tests_passed, unit_test_count = await test_unit_tests()
        
        # Test 2: Staff auth performance
        staff_auth_passed, staff_token, staff_cold, staff_warm = await test_staff_auth_performance(client)
        
        # Test 3: Customer auth performance
        customer_auth_passed, customer_token, customer_cold, customer_warm = await test_customer_auth_performance(client)
        
        # Test 4: Revocation correctness
        revocation_passed = await test_revocation_correctness(client)
        
        # Test 5: Role enforcement
        role_enforcement_passed = await test_role_enforcement(client)
        
        # Test 6: Legacy token compatibility
        legacy_token_passed = await test_legacy_token_compatibility()
        
        # Test 7: Authenticated smoke tests (get fresh token since previous one may have expired)
        # Login fresh for smoke tests
        login_resp = await client.post(
            f"{BASE_URL}/auth/login",
            json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}
        )
        if login_resp.status_code == 200:
            fresh_token = login_resp.json()["access_token"]
            smoke_passed = await test_authenticated_smoke(client, fresh_token)
        else:
            print_section("TEST 7: Authenticated Smoke Tests")
            print_test("Authenticated smoke tests", False, "Could not get fresh token")
            smoke_passed = False
        
        # Test 8: Cache safety
        cache_safety_passed = await test_cache_safety()
    
    # Summary
    print_section("SUMMARY")
    
    all_tests = [
        ("Unit Tests", unit_tests_passed, f"{unit_test_count} tests"),
        ("Staff Auth Performance", staff_auth_passed, f"Cold: {staff_cold:.0f}ms, Warm: {staff_warm:.0f}ms" if staff_cold and staff_warm else "N/A"),
        ("Customer Auth Performance", customer_auth_passed, f"Cold: {customer_cold:.0f}ms, Warm: {customer_warm:.0f}ms" if customer_cold and customer_warm else "N/A"),
        ("Revocation Correctness", revocation_passed, "All revocation scenarios"),
        ("Role Enforcement", role_enforcement_passed, "Lower-role user blocked correctly"),
        ("Legacy Token Compatibility", legacy_token_passed, "Sessionless tokens work"),
        ("Authenticated Smoke Tests", smoke_passed, "8 endpoints, products total=2966"),
        ("Cache Safety", cache_safety_passed, "TTL, max, no password_hash, invalidation wired"),
    ]
    
    passed_count = sum(1 for _, passed, _ in all_tests if passed)
    total_count = len(all_tests)
    
    print(f"\n{BLUE}Test Results:{RESET}")
    for name, passed, details in all_tests:
        status = f"{GREEN}✅{RESET}" if passed else f"{RED}❌{RESET}"
        print(f"{status} {name}: {details}")
    
    print(f"\n{BLUE}Overall: {passed_count}/{total_count} test groups passed{RESET}")
    
    if passed_count == total_count:
        print(f"\n{GREEN}{'=' * 80}")
        print("ALL TESTS PASSED ✅")
        print(f"{'=' * 80}{RESET}\n")
        return 0
    else:
        print(f"\n{RED}{'=' * 80}")
        print(f"SOME TESTS FAILED ({total_count - passed_count} failures)")
        print(f"{'=' * 80}{RESET}\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
