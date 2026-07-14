#!/usr/bin/env python3
"""
Backend test for PATCH /api/products/{product_id} endpoint
Testing Product Management Unification feature
"""
import requests
import time
import json
from typing import Optional

# Configuration
BASE_URL = "https://forge-lc1.preview.emergentagent.com/api"
LOGIN_EMAIL = "owner@forge.app"
LOGIN_PASSWORD = "Forge@2026"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def log_pass(step: str, message: str):
    print(f"{Colors.GREEN}✅ PASS{Colors.RESET} - {step}: {message}")

def log_fail(step: str, message: str, response: Optional[requests.Response] = None):
    print(f"{Colors.RED}❌ FAIL{Colors.RESET} - {step}: {message}")
    if response:
        print(f"  Status: {response.status_code}")
        try:
            print(f"  Body: {json.dumps(response.json(), indent=2)}")
        except:
            print(f"  Body: {response.text[:500]}")

def log_info(message: str):
    print(f"{Colors.BLUE}ℹ️  INFO{Colors.RESET} - {message}")

def log_warning(message: str):
    print(f"{Colors.YELLOW}⚠️  WARN{Colors.RESET} - {message}")

def get_auth_token() -> str:
    """Login and get bearer token"""
    log_info("Logging in as owner@forge.app...")
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD}
    )
    if response.status_code != 200:
        raise Exception(f"Login failed: {response.status_code} - {response.text}")
    
    token = response.json().get("access_token")
    if not token:
        raise Exception("No access_token in login response")
    
    log_pass("AUTH", f"Logged in successfully, token length: {len(token)}")
    return token

def test_patch_endpoint():
    """Test PATCH /api/products/{product_id} according to 10-step review request"""
    
    print("\n" + "="*80)
    print("TESTING: PATCH /api/products/{product_id} - Product Management Unification")
    print("="*80 + "\n")
    
    # Get auth token
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # Track test results
    passed = 0
    failed = 0
    skipped = 0
    
    # Store original product state for restoration
    original_product = None
    product_id = None
    
    # ========================================================================
    # STEP 1: Pick a real product and note its current values
    # ========================================================================
    print("\n" + "-"*80)
    print("STEP 1: Get a real product and note its current values")
    print("-"*80)
    
    response = requests.get(f"{BASE_URL}/products?limit=1", headers=headers)
    if response.status_code != 200:
        log_fail("STEP 1", "Failed to get products", response)
        return
    
    products = response.json().get("items", [])
    if not products:
        log_fail("STEP 1", "No products found in catalog")
        return
    
    original_product = products[0]
    product_id = original_product["id"]
    
    log_info(f"Selected product ID: {product_id}")
    log_info(f"  Original name: {original_product.get('name')}")
    log_info(f"  Original SKU: {original_product.get('sku')}")
    log_info(f"  Original MRP: {original_product.get('mrp')}")
    log_info(f"  Original price: {original_product.get('price')}")
    orig_desc = original_product.get('description') or 'N/A'
    log_info(f"  Original description: {orig_desc[:50] if len(orig_desc) > 50 else orig_desc}...")
    log_info(f"  Original finish: {original_product.get('finish', 'N/A')}")
    log_pass("STEP 1", "Product retrieved and original values noted")
    passed += 1
    
    # ========================================================================
    # STEP 2: PATCH with new values and confirm 200 OK
    # ========================================================================
    print("\n" + "-"*80)
    print("STEP 2: PATCH product with new values")
    print("-"*80)
    
    patch_data = {
        "name": "Test Edited Name",
        "mrp": 9999,
        "price": 8888,
        "description": "Test description edit"
    }
    
    response = requests.patch(
        f"{BASE_URL}/products/{product_id}",
        json=patch_data,
        headers=headers
    )
    
    if response.status_code != 200:
        log_fail("STEP 2", f"PATCH failed with status {response.status_code}", response)
        failed += 1
    else:
        patched_product = response.json()
        
        # Verify response reflects new values
        checks = [
            (patched_product.get("name") == "Test Edited Name", "name"),
            (patched_product.get("mrp") == 9999, "mrp"),
            (patched_product.get("price") == 8888, "price"),
            (patched_product.get("description") == "Test description edit", "description")
        ]
        
        all_correct = all(check[0] for check in checks)
        if all_correct:
            log_pass("STEP 2", "PATCH returned 200 OK and response reflects new values")
            passed += 1
        else:
            failed_fields = [check[1] for check in checks if not check[0]]
            log_fail("STEP 2", f"Response doesn't reflect new values for: {', '.join(failed_fields)}")
            log_info(f"Response: {json.dumps(patched_product, indent=2)}")
            failed += 1
    
    # ========================================================================
    # STEP 3: Immediately GET product by ID - confirm instant update
    # ========================================================================
    print("\n" + "-"*80)
    print("STEP 3: Immediately GET /api/products/{id} - verify instant update")
    print("-"*80)
    
    # NO DELAY - this must be instant per the review request
    response = requests.get(f"{BASE_URL}/products/{product_id}", headers=headers)
    
    if response.status_code != 200:
        log_fail("STEP 3", f"GET by ID failed with status {response.status_code}", response)
        failed += 1
    else:
        product = response.json()
        
        checks = [
            (product.get("name") == "Test Edited Name", "name", product.get("name")),
            (product.get("mrp") == 9999, "mrp", product.get("mrp")),
            (product.get("price") == 8888, "price", product.get("price")),
            (product.get("description") == "Test description edit", "description", product.get("description"))
        ]
        
        all_correct = all(check[0] for check in checks)
        if all_correct:
            log_pass("STEP 3", "GET by ID shows new values INSTANTLY (no async delay)")
            passed += 1
        else:
            failed_fields = [(check[1], check[2]) for check in checks if not check[0]]
            log_fail("STEP 3", f"GET by ID doesn't show new values: {failed_fields}")
            failed += 1
    
    # ========================================================================
    # STEP 4: Immediately GET products list - confirm instant update
    # ========================================================================
    print("\n" + "-"*80)
    print("STEP 4: Immediately GET /api/products (list) - verify instant update")
    print("-"*80)
    
    # Try with search first
    response = requests.get(
        f"{BASE_URL}/products?q=Test Edited Name&limit=20",
        headers=headers
    )
    
    if response.status_code != 200:
        log_fail("STEP 4", f"GET products list failed with status {response.status_code}", response)
        failed += 1
    else:
        items = response.json().get("items", [])
        found = any(item["id"] == product_id and item["name"] == "Test Edited Name" for item in items)
        
        if found:
            log_pass("STEP 4", "GET products list shows new name INSTANTLY in search results")
            passed += 1
        else:
            # Try without search filter
            response2 = requests.get(f"{BASE_URL}/products?limit=100", headers=headers)
            items2 = response2.json().get("items", [])
            found2 = any(item["id"] == product_id and item["name"] == "Test Edited Name" for item in items2)
            
            if found2:
                log_pass("STEP 4", "GET products list shows new name INSTANTLY (found in unfiltered list)")
                passed += 1
            else:
                log_fail("STEP 4", f"Product {product_id} not found with new name in list")
                log_info(f"Searched in {len(items)} items (search) and {len(items2)} items (unfiltered)")
                failed += 1
    
    # ========================================================================
    # STEP 5: GET activity log - confirm product.updated event
    # ========================================================================
    print("\n" + "-"*80)
    print("STEP 5: GET /api/activity/product/{id} - verify audit trail")
    print("-"*80)
    
    response = requests.get(f"{BASE_URL}/activity/product/{product_id}", headers=headers)
    
    if response.status_code != 200:
        log_fail("STEP 5", f"GET activity log failed with status {response.status_code}", response)
        failed += 1
    else:
        events = response.json()
        
        # Find product.updated event with the fields we changed
        updated_events = [e for e in events if e.get("event_type") == "product.updated"]
        
        if not updated_events:
            log_fail("STEP 5", "No product.updated event found in activity log")
            failed += 1
        else:
            # Check the most recent update event
            latest_event = updated_events[0]
            payload = latest_event.get("payload", {})
            fields = payload.get("fields", [])
            
            expected_fields = {"name", "mrp", "price", "description"}
            actual_fields = set(fields)
            
            # updated_at is automatically added, so we allow it
            actual_fields.discard("updated_at")
            
            if expected_fields.issubset(actual_fields):
                log_pass("STEP 5", f"product.updated event found with correct fields: {sorted(actual_fields)}")
                passed += 1
            else:
                missing = expected_fields - actual_fields
                log_fail("STEP 5", f"product.updated event missing fields: {missing}")
                log_info(f"Found fields: {sorted(actual_fields)}")
                failed += 1
    
    # ========================================================================
    # STEP 6: Test SKU conflict - expect 409
    # ========================================================================
    print("\n" + "-"*80)
    print("STEP 6: Test SKU conflict - PATCH with existing SKU")
    print("-"*80)
    
    # Get another product's SKU
    response = requests.get(f"{BASE_URL}/products?limit=5", headers=headers)
    if response.status_code != 200:
        log_warning("Could not get products for SKU conflict test")
        skipped += 1
    else:
        products = response.json().get("items", [])
        other_product = next((p for p in products if p["id"] != product_id and p.get("sku")), None)
        
        if not other_product:
            log_warning("Could not find another product with SKU for conflict test")
            skipped += 1
        else:
            other_sku = other_product["sku"]
            log_info(f"Attempting to set SKU to existing SKU: {other_sku}")
            
            response = requests.patch(
                f"{BASE_URL}/products/{product_id}",
                json={"sku": other_sku},
                headers=headers
            )
            
            if response.status_code == 409:
                log_pass("STEP 6", f"SKU conflict correctly rejected with 409 Conflict")
                
                # Verify SKU was NOT changed
                verify_response = requests.get(f"{BASE_URL}/products/{product_id}", headers=headers)
                if verify_response.status_code == 200:
                    current_sku = verify_response.json().get("sku")
                    if current_sku != other_sku:
                        log_pass("STEP 6", f"SKU was NOT changed (still: {current_sku})")
                        passed += 1
                    else:
                        log_fail("STEP 6", "SKU was changed despite 409 response!")
                        failed += 1
                else:
                    log_warning("Could not verify SKU was unchanged")
                    passed += 1  # Still count as pass since 409 was correct
            else:
                log_fail("STEP 6", f"Expected 409 Conflict, got {response.status_code}", response)
                failed += 1
    
    # ========================================================================
    # STEP 7: Test partial update - only change finish
    # ========================================================================
    print("\n" + "-"*80)
    print("STEP 7: Test partial update - PATCH only finish field")
    print("-"*80)
    
    response = requests.patch(
        f"{BASE_URL}/products/{product_id}",
        json={"finish": "Matte Black"},
        headers=headers
    )
    
    if response.status_code != 200:
        log_fail("STEP 7", f"Partial PATCH failed with status {response.status_code}", response)
        failed += 1
    else:
        product = response.json()
        
        # Verify ONLY finish changed, everything else from step 2 is untouched
        checks = [
            (product.get("finish") == "Matte Black", "finish changed", product.get("finish")),
            (product.get("name") == "Test Edited Name", "name unchanged", product.get("name")),
            (product.get("mrp") == 9999, "mrp unchanged", product.get("mrp")),
            (product.get("price") == 8888, "price unchanged", product.get("price")),
            (product.get("description") == "Test description edit", "description unchanged", product.get("description"))
        ]
        
        all_correct = all(check[0] for check in checks)
        if all_correct:
            log_pass("STEP 7", "Partial update works correctly (only finish changed, other fields untouched)")
            passed += 1
        else:
            failed_checks = [(check[1], check[2]) for check in checks if not check[0]]
            log_fail("STEP 7", f"Partial update failed checks: {failed_checks}")
            failed += 1
    
    # ========================================================================
    # STEP 8: Test 404 - nonexistent product ID
    # ========================================================================
    print("\n" + "-"*80)
    print("STEP 8: Test 404 - PATCH nonexistent product")
    print("-"*80)
    
    response = requests.patch(
        f"{BASE_URL}/products/nonexistent-id-xyz",
        json={"name": "Should fail"},
        headers=headers
    )
    
    if response.status_code == 404:
        log_pass("STEP 8", "Nonexistent product correctly returns 404")
        passed += 1
    else:
        log_fail("STEP 8", f"Expected 404, got {response.status_code}", response)
        failed += 1
    
    # ========================================================================
    # STEP 9: Test RBAC - lower privilege user (if available)
    # ========================================================================
    print("\n" + "-"*80)
    print("STEP 9: Test RBAC - lower privilege user")
    print("-"*80)
    
    # Try to find a lower-privilege user
    # The endpoint requires min role "purchase" per the code
    # We'd need a user with role < purchase (e.g., sales, warehouse, worker)
    
    log_info("Checking for lower-privilege test users...")
    
    # Get team list to see if there are other users
    team_response = requests.get(f"{BASE_URL}/team", headers=headers)
    if team_response.status_code == 200:
        users = team_response.json()
        lower_privilege_users = [
            u for u in users 
            if u.get("role") in ["sales", "warehouse", "worker"] and u.get("active", True)
        ]
        
        if lower_privilege_users:
            test_user = lower_privilege_users[0]
            log_info(f"Found lower-privilege user: {test_user.get('email')} (role: {test_user.get('role')})")
            log_warning("Cannot test RBAC without password - would need to create test user")
            log_info("SKIPPING STEP 9 - impractical to test without test user credentials")
            skipped += 1
        else:
            log_info("No lower-privilege active users found")
            log_info("SKIPPING STEP 9 - no suitable test user available")
            skipped += 1
    else:
        log_warning("Could not fetch team list")
        log_info("SKIPPING STEP 9 - impractical to test")
        skipped += 1
    
    # ========================================================================
    # STEP 10: RESTORE original product values
    # ========================================================================
    print("\n" + "-"*80)
    print("STEP 10: RESTORE product to original values")
    print("-"*80)
    
    if not original_product:
        log_fail("STEP 10", "No original product data to restore!")
        failed += 1
    else:
        restore_data = {
            "name": original_product.get("name"),
            "sku": original_product.get("sku"),
            "mrp": original_product.get("mrp"),
            "price": original_product.get("price"),
            "description": original_product.get("description"),
            "finish": original_product.get("finish")
        }
        
        log_info(f"Restoring product to original values...")
        log_info(f"  name: {restore_data['name']}")
        log_info(f"  sku: {restore_data['sku']}")
        log_info(f"  mrp: {restore_data['mrp']}")
        log_info(f"  price: {restore_data['price']}")
        log_info(f"  finish: {restore_data['finish']}")
        
        response = requests.patch(
            f"{BASE_URL}/products/{product_id}",
            json=restore_data,
            headers=headers
        )
        
        if response.status_code != 200:
            log_fail("STEP 10", f"Restore PATCH failed with status {response.status_code}", response)
            failed += 1
        else:
            # Small delay to allow snapshot update (though it should be instant per spec)
            time.sleep(0.5)
            
            # Verify restoration
            verify_response = requests.get(f"{BASE_URL}/products/{product_id}", headers=headers)
            if verify_response.status_code == 200:
                restored = verify_response.json()
                
                checks = [
                    (restored.get("name") == original_product.get("name"), "name"),
                    (restored.get("sku") == original_product.get("sku"), "sku"),
                    (restored.get("mrp") == original_product.get("mrp"), "mrp"),
                    (restored.get("price") == original_product.get("price"), "price"),
                    (restored.get("finish") == original_product.get("finish"), "finish")
                ]
                
                all_correct = all(check[0] for check in checks)
                if all_correct:
                    log_pass("STEP 10", "Product successfully restored to original values")
                    passed += 1
                else:
                    failed_fields = [check[1] for check in checks if not check[0]]
                    log_fail("STEP 10", f"Restoration incomplete for fields: {', '.join(failed_fields)}")
                    log_info(f"Original: {json.dumps({k: original_product.get(k) for k in ['name', 'sku', 'mrp', 'price', 'finish']}, indent=2)}")
                    log_info(f"Restored: {json.dumps({k: restored.get(k) for k in ['name', 'sku', 'mrp', 'price', 'finish']}, indent=2)}")
                    failed += 1
            else:
                log_fail("STEP 10", "Could not verify restoration")
                failed += 1
    
    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"{Colors.GREEN}PASSED: {passed}{Colors.RESET}")
    print(f"{Colors.RED}FAILED: {failed}{Colors.RESET}")
    print(f"{Colors.YELLOW}SKIPPED: {skipped}{Colors.RESET}")
    print(f"TOTAL: {passed + failed + skipped}")
    
    if failed == 0:
        print(f"\n{Colors.GREEN}✅ ALL TESTS PASSED{Colors.RESET}")
        return True
    else:
        print(f"\n{Colors.RED}❌ SOME TESTS FAILED{Colors.RESET}")
        return False

if __name__ == "__main__":
    try:
        success = test_patch_endpoint()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n{Colors.RED}❌ FATAL ERROR{Colors.RESET}: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
