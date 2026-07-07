#!/usr/bin/env python3
"""
STABILIZATION SPRINT - Comprehensive Backend Audit
Tests all 6 focus areas in order with detailed request/response evidence.
"""
import requests
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Configuration
BASE_URL = "https://persist-arch.preview.emergentagent.com/api"
PRIMARY_EMAIL = "owner@forge.app"
PRIMARY_PASSWORD = "Forge@2026"
SALES_EMAIL = "sales@forge.app"
SALES_PASSWORD = "Forge@2026"
ACCOUNTS_EMAIL = "accounts@forge.app"
ACCOUNTS_PASSWORD = "Forge@2026"
MANAGER_EMAIL = "manager@forge.app"
MANAGER_PASSWORD = "Forge@2026"

# Global state
auth_token = None
sales_token = None
accounts_token = None
manager_token = None
test_results = {
    "environment_recovery": [],
    "quotation_module": [],
    "purchases_module": [],
    "payments_module": [],
    "followups_v2": [],
    "cross_module_e2e": []
}

def log_test(category: str, test_name: str, passed: bool, details: str = "", evidence: Dict = None):
    """Log test result with evidence"""
    result = {
        "test": test_name,
        "passed": passed,
        "details": details,
        "evidence": evidence or {},
        "timestamp": datetime.now().isoformat()
    }
    test_results[category].append(result)
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {test_name}")
    if details:
        print(f"  Details: {details}")
    if not passed and evidence:
        print(f"  Evidence: {json.dumps(evidence, indent=2)[:500]}")

def login(email: str, password: str) -> Optional[str]:
    """Login and return auth token"""
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": email, "password": password},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
        else:
            print(f"Login failed for {email}: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Login exception for {email}: {e}")
        return None

def get_headers(token: str = None) -> Dict[str, str]:
    """Get request headers with optional auth token"""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

# ============================================================================
# TASK 1: Environment Recovery
# ============================================================================
def test_environment_recovery():
    """Quick sanity check: login works, auth required for quotations"""
    global auth_token
    print("\n" + "="*80)
    print("TASK 1: ENVIRONMENT RECOVERY")
    print("="*80)
    
    # Test 1.1: Login with owner@forge.app
    auth_token = login(PRIMARY_EMAIL, PRIMARY_PASSWORD)
    log_test(
        "environment_recovery",
        "Login with owner@forge.app",
        auth_token is not None,
        f"Token received: {auth_token[:20]}..." if auth_token else "No token",
        {"email": PRIMARY_EMAIL, "token_length": len(auth_token) if auth_token else 0}
    )
    
    if not auth_token:
        print("❌ CRITICAL: Cannot proceed without auth token")
        return False
    
    # Test 1.2: GET /api/quotations without auth returns 401
    try:
        response = requests.get(f"{BASE_URL}/quotations", timeout=10)
        passed = response.status_code == 401
        log_test(
            "environment_recovery",
            "GET /api/quotations without auth returns 401",
            passed,
            f"Status: {response.status_code}",
            {"status_code": response.status_code, "response": response.text[:200]}
        )
    except Exception as e:
        log_test("environment_recovery", "GET /api/quotations without auth", False, str(e))
    
    # Test 1.3: GET /api/quotations with auth returns 200
    try:
        response = requests.get(
            f"{BASE_URL}/quotations",
            headers=get_headers(auth_token),
            timeout=10
        )
        passed = response.status_code == 200
        data = response.json() if passed else {}
        log_test(
            "environment_recovery",
            "GET /api/quotations with auth returns 200",
            passed,
            f"Status: {response.status_code}, Count: {len(data) if isinstance(data, list) else 'N/A'}",
            {"status_code": response.status_code, "count": len(data) if isinstance(data, list) else 0}
        )
    except Exception as e:
        log_test("environment_recovery", "GET /api/quotations with auth", False, str(e))
    
    return True

# ============================================================================
# Main Execution - Placeholder for remaining tasks
# ============================================================================
def main():
    print("\n" + "="*80)
    print("STABILIZATION SPRINT - COMPREHENSIVE BACKEND AUDIT")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Primary user: {PRIMARY_EMAIL}")
    print("="*80)
    
    # Execute task 1
    test_environment_recovery()
    
    print("\n✅ Task 1 complete. Remaining tasks will be added incrementally.")
    
    # Save results to file
    with open("/app/backend_test_results.json", "w") as f:
        json.dump(test_results, f, indent=2)
    
    print("\nResults saved to: /app/backend_test_results.json")

if __name__ == "__main__":
    main()
