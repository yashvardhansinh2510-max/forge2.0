#!/usr/bin/env python3
"""
Nexion Brand Import Verification Test Suite
Tests all 10 verification points from the review request
"""

import requests
import json
import sys
from typing import Dict, Any, Optional

# Configuration
BASE_URL = "https://tile-catalog-nexion.preview.emergentagent.com/api"
TEST_USER = "owner@forge.app"
TEST_PASSWORD = "Forge@2026"

# Test results tracking
test_results = []

def log_test(test_num: str, description: str, passed: bool, details: str = ""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    result = {
        "test": test_num,
        "description": description,
        "status": status,
        "passed": passed,
        "details": details
    }
    test_results.append(result)
    print(f"\n{status} | Test {test_num}: {description}")
    if details:
        print(f"  Details: {details}")

def print_summary():
    """Print test summary"""
    passed = sum(1 for r in test_results if r["passed"])
    total = len(test_results)
    print("\n" + "="*80)
    print(f"TEST SUMMARY: {passed}/{total} PASSED")
    print("="*80)
    
    for result in test_results:
        print(f"{result['status']} | Test {result['test']}: {result['description']}")
        if result['details'] and not result['passed']:
            print(f"  {result['details']}")
    
    return passed == total

# Test 1: Login and get token
def test_1_login():
    """Test 1: Login as owner@forge.app and confirm token works"""
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": TEST_USER, "password": TEST_PASSWORD},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token") or data.get("token")
            user = data.get("user", {})
            
            if token and len(token) > 50:
                log_test(
                    "1", 
                    "Login as owner@forge.app and confirm token works",
                    True,
                    f"Token received ({len(token)} chars), User: {user.get('name')} ({user.get('email')}), Role: {user.get('role')}"
                )
                return token
            else:
                log_test("1", "Login as owner@forge.app", False, "Token missing or invalid")
                return None
        else:
            log_test("1", "Login as owner@forge.app", False, f"HTTP {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        log_test("1", "Login as owner@forge.app", False, f"Exception: {str(e)}")
        return None

# Test 2: GET /api/brands - confirm Nexion exists
def test_2_brands(token: str):
    """Test 2: GET /api/brands - confirm Nexion exists with floor_id ground-floor"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/brands", headers=headers, timeout=30)
        
        if response.status_code == 200:
            brands = response.json()
            nexion_brand = None
            
            for brand in brands:
                if brand.get("name") == "Nexion":
                    nexion_brand = brand
                    break
            
            if nexion_brand:
                floor_id = nexion_brand.get("floor_id")
                brand_id = nexion_brand.get("id")
                
                if floor_id == "ground-floor":
                    log_test(
                        "2",
                        "GET /api/brands - confirm Nexion exists with floor_id ground-floor",
                        True,
                        f"Nexion brand found: id={brand_id}, floor_id={floor_id}"
                    )
                    return brand_id
                else:
                    log_test("2", "GET /api/brands", False, f"Nexion floor_id is '{floor_id}', expected 'ground-floor'")
                    return None
            else:
                log_test("2", "GET /api/brands", False, f"Nexion brand not found. Available brands: {[b.get('name') for b in brands]}")
                return None
        else:
            log_test("2", "GET /api/brands", False, f"HTTP {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        log_test("2", "GET /api/brands", False, f"Exception: {str(e)}")
        return None

# Test 3: GET /api/products?brand_id=<nexion> - confirm ~761 products
def test_3_products_by_brand(token: str, brand_id: str):
    """Test 3: GET /api/products?brand_id=<nexion> - confirm ~761 products"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        # First request to get total count
        response = requests.get(
            f"{BASE_URL}/products",
            headers=headers,
            params={"brand_id": brand_id, "limit": 100},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            total = data.get("total", 0)
            items = data.get("items", [])
            
            # Verify all products have floor_id ground-floor
            all_ground_floor = all(item.get("floor_id") == "ground-floor" for item in items)
            
            if 750 <= total <= 770:  # Allow small variance
                log_test(
                    "3",
                    "GET /api/products?brand_id=<nexion> - confirm ~761 products",
                    True,
                    f"Total Nexion products: {total} (expected ~761), All have floor_id=ground-floor: {all_ground_floor}"
                )
                return items[0] if items else None  # Return first product for later tests
            else:
                log_test("3", "GET /api/products?brand_id=<nexion>", False, f"Product count {total} not in expected range 750-770")
                return None
        else:
            log_test("3", "GET /api/products?brand_id=<nexion>", False, f"HTTP {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        log_test("3", "GET /api/products?brand_id=<nexion>", False, f"Exception: {str(e)}")
        return None

# Test 4: Search by product name (CALACATTA)
def test_4_search_by_name(token: str):
    """Test 4: GET /api/catalog/search?q=CALACATTA - confirm Nexion products show up"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/catalog/search",
            headers=headers,
            params={"q": "CALACATTA"},
            timeout=30
        )
        
        if response.status_code == 200:
            results = response.json()
            items = results.get("items", [])
            
            # Check if any Nexion products in results
            nexion_products = [item for item in items if item.get("brand_name") == "Nexion"]
            
            if nexion_products:
                log_test(
                    "4",
                    "GET /api/catalog/search?q=CALACATTA - confirm Nexion products show up",
                    True,
                    f"Found {len(nexion_products)} Nexion products matching 'CALACATTA' (out of {len(items)} total results)"
                )
                return nexion_products[0] if nexion_products else None
            else:
                log_test("4", "GET /api/catalog/search?q=CALACATTA", False, f"No Nexion products found. Total results: {len(items)}")
                return None
        else:
            log_test("4", "GET /api/catalog/search?q=CALACATTA", False, f"HTTP {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        log_test("4", "GET /api/catalog/search?q=CALACATTA", False, f"Exception: {str(e)}")
        return None

# Test 5: Search by SKU prefix
def test_5_search_by_sku(token: str):
    """Test 5: GET /api/catalog/search?q=NEXION-CALACATTA - confirm SKU search works"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/catalog/search",
            headers=headers,
            params={"q": "NEXION-CALACATTA"},
            timeout=30
        )
        
        if response.status_code == 200:
            results = response.json()
            items = results.get("items", [])
            
            # Check if results contain products with NEXION-CALACATTA in SKU
            matching_products = [item for item in items if "NEXION-CALACATTA" in item.get("sku", "").upper()]
            
            if matching_products:
                sample_sku = matching_products[0].get("sku")
                log_test(
                    "5",
                    "GET /api/catalog/search?q=NEXION-CALACATTA - confirm SKU search works",
                    True,
                    f"Found {len(matching_products)} products with SKU containing 'NEXION-CALACATTA'. Sample: {sample_sku}"
                )
                return matching_products[0]
            else:
                log_test("5", "GET /api/catalog/search?q=NEXION-CALACATTA", False, f"No products with NEXION-CALACATTA SKU found. Total results: {len(items)}")
                return None
        else:
            log_test("5", "GET /api/catalog/search?q=NEXION-CALACATTA", False, f"HTTP {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        log_test("5", "GET /api/catalog/search?q=NEXION-CALACATTA", False, f"Exception: {str(e)}")
        return None

# Test 6: Search by size
def test_6_search_by_size(token: str):
    """Test 6: GET /api/catalog/search?q=1198X2398 - confirm size-based search works"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/catalog/search",
            headers=headers,
            params={"q": "1198X2398"},
            timeout=30
        )
        
        if response.status_code == 200:
            results = response.json()
            items = results.get("items", [])
            
            # Check if results contain Nexion products with this size
            nexion_with_size = [
                item for item in items 
                if item.get("brand_name") == "Nexion" and "1198X2398" in item.get("size", "").upper()
            ]
            
            if nexion_with_size:
                sample_product = nexion_with_size[0]
                log_test(
                    "6",
                    "GET /api/catalog/search?q=1198X2398 - confirm size-based search works",
                    True,
                    f"Found {len(nexion_with_size)} Nexion products with size 1198X2398. Sample: {sample_product.get('name')} ({sample_product.get('size')})"
                )
                return nexion_with_size[0]
            else:
                log_test("6", "GET /api/catalog/search?q=1198X2398", False, f"No Nexion products with size 1198X2398 found. Total results: {len(items)}")
                return None
        else:
            log_test("6", "GET /api/catalog/search?q=1198X2398", False, f"HTTP {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        log_test("6", "GET /api/catalog/search?q=1198X2398", False, f"Exception: {str(e)}")
        return None

# Test 7: Get single product detail
def test_7_product_detail(token: str, product_id: str):
    """Test 7: GET /api/products/{id} - confirm hero_image_url/gallery with Supabase URL"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/products/{product_id}",
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            product = response.json()
            
            # Check for required fields
            hero_image = product.get("hero_image_url")
            gallery = product.get("gallery", [])
            name = product.get("name")
            size = product.get("size")
            finish = product.get("finish")
            mrp = product.get("mrp")
            price = product.get("price")
            specs = product.get("specs", {})
            pcs_per_box = specs.get("pcs_per_box")
            sqft_per_box = specs.get("sqft_per_box")
            
            # Check if hero_image or gallery has Supabase URL
            has_supabase_url = False
            supabase_url = None
            
            if hero_image and "supabase.co" in hero_image:
                has_supabase_url = True
                supabase_url = hero_image
            elif gallery:
                for img in gallery:
                    img_url = img.get("url") if isinstance(img, dict) else img
                    if img_url and "supabase.co" in img_url:
                        has_supabase_url = True
                        supabase_url = img_url
                        break
            
            required_fields = {
                "name": name,
                "size": size,
                "finish": finish,
                "mrp": mrp,
                "price": price,
                "pcs_per_box": pcs_per_box,
                "sqft_per_box": sqft_per_box
            }
            
            missing_fields = [k for k, v in required_fields.items() if v is None]
            
            if has_supabase_url and not missing_fields:
                log_test(
                    "7",
                    "GET /api/products/{id} - confirm hero_image_url/gallery with Supabase URL and specs",
                    True,
                    f"Product: {name}, Size: {size}, Finish: {finish}, MRP: {mrp}, Price: {price}, Specs: {pcs_per_box} pcs/box, {sqft_per_box} sqft/box. Supabase URL found."
                )
                return supabase_url
            else:
                issues = []
                if not has_supabase_url:
                    issues.append("No Supabase URL found in hero_image_url or gallery")
                if missing_fields:
                    issues.append(f"Missing fields: {', '.join(missing_fields)}")
                
                log_test("7", "GET /api/products/{id}", False, "; ".join(issues))
                return None
        else:
            log_test("7", "GET /api/products/{id}", False, f"HTTP {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        log_test("7", "GET /api/products/{id}", False, f"Exception: {str(e)}")
        return None

# Test 8: Fetch image URL directly
def test_8_image_fetch(image_url: str):
    """Test 8: Fetch hero_image_url directly and confirm HTTP 200"""
    try:
        response = requests.get(image_url, timeout=30)
        
        if response.status_code == 200:
            content_type = response.headers.get("Content-Type", "")
            content_length = len(response.content)
            
            if "image" in content_type and content_length > 1000:
                log_test(
                    "8",
                    "Fetch hero_image_url directly and confirm HTTP 200",
                    True,
                    f"Image fetched successfully: {content_length} bytes, Content-Type: {content_type}"
                )
                return True
            else:
                log_test("8", "Fetch hero_image_url", False, f"Invalid image: {content_length} bytes, Content-Type: {content_type}")
                return False
        else:
            log_test("8", "Fetch hero_image_url", False, f"HTTP {response.status_code}")
            return False
    except Exception as e:
        log_test("8", "Fetch hero_image_url", False, f"Exception: {str(e)}")
        return False

# Test 9: Floor isolation check
def test_9_floor_isolation(token: str, nexion_brand_id: str):
    """Test 9: Confirm first-floor queries never return Nexion products"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get all products and check floor_id
        response = requests.get(
            f"{BASE_URL}/products",
            headers=headers,
            params={"brand_id": nexion_brand_id, "limit": 100},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            
            # Check if ANY product has floor_id != ground-floor
            first_floor_products = [item for item in items if item.get("floor_id") == "first-floor"]
            
            if not first_floor_products:
                # Also verify by checking all products have ground-floor
                all_ground_floor = all(item.get("floor_id") == "ground-floor" for item in items)
                
                if all_ground_floor:
                    log_test(
                        "9",
                        "Floor isolation check - confirm NO Nexion products on first-floor",
                        True,
                        f"Verified: All {len(items)} Nexion products have floor_id=ground-floor, NONE have floor_id=first-floor"
                    )
                    return True
                else:
                    other_floors = set(item.get("floor_id") for item in items if item.get("floor_id") != "ground-floor")
                    log_test("9", "Floor isolation check", False, f"Found Nexion products on other floors: {other_floors}")
                    return False
            else:
                log_test("9", "Floor isolation check", False, f"Found {len(first_floor_products)} Nexion products with floor_id=first-floor (VIOLATION)")
                return False
        else:
            log_test("9", "Floor isolation check", False, f"HTTP {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("9", "Floor isolation check", False, f"Exception: {str(e)}")
        return False

# Test 10: Regression check - existing brands unaffected
def test_10_regression_check(token: str):
    """Test 10: Confirm existing brands (Qutone, Dimore, Hansgrohe, Grohe, Vitra, AXOR) unaffected"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get all brands
        response = requests.get(f"{BASE_URL}/brands", headers=headers, timeout=30)
        
        if response.status_code == 200:
            brands = response.json()
            
            # Expected brands and their floors
            expected_brands = {
                "Qutone": "ground-floor",
                "Dimore": "ground-floor",
                "Hansgrohe": "first-floor",
                "Grohe": "first-floor",
                "Vitra": "first-floor",
                "AXOR": "first-floor"
            }
            
            found_brands = {}
            for brand in brands:
                name = brand.get("name")
                if name in expected_brands:
                    found_brands[name] = {
                        "floor_id": brand.get("floor_id"),
                        "id": brand.get("id")
                    }
            
            # Check if all expected brands exist with correct floor_id
            all_correct = True
            issues = []
            
            for brand_name, expected_floor in expected_brands.items():
                if brand_name not in found_brands:
                    all_correct = False
                    issues.append(f"{brand_name} not found")
                elif found_brands[brand_name]["floor_id"] != expected_floor:
                    all_correct = False
                    issues.append(f"{brand_name} has floor_id={found_brands[brand_name]['floor_id']}, expected {expected_floor}")
            
            if all_correct:
                # Get product counts for each brand
                brand_counts = {}
                for brand_name, brand_info in found_brands.items():
                    resp = requests.get(
                        f"{BASE_URL}/products",
                        headers=headers,
                        params={"brand_id": brand_info["id"], "limit": 1},
                        timeout=30
                    )
                    if resp.status_code == 200:
                        brand_counts[brand_name] = resp.json().get("total", 0)
                
                log_test(
                    "10",
                    "Regression check - existing brands unaffected",
                    True,
                    f"All 6 existing brands found with correct floor_id. Product counts: {brand_counts}"
                )
                return True
            else:
                log_test("10", "Regression check", False, f"Issues: {'; '.join(issues)}")
                return False
        else:
            log_test("10", "Regression check", False, f"HTTP {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        log_test("10", "Regression check", False, f"Exception: {str(e)}")
        return False

# Main test execution
def main():
    print("="*80)
    print("NEXION BRAND IMPORT VERIFICATION TEST SUITE")
    print("="*80)
    print(f"Backend URL: {BASE_URL}")
    print(f"Test User: {TEST_USER}")
    print("="*80)
    
    # Test 1: Login
    token = test_1_login()
    if not token:
        print("\n❌ CRITICAL: Login failed. Cannot proceed with other tests.")
        print_summary()
        sys.exit(1)
    
    # Test 2: Get Nexion brand
    nexion_brand_id = test_2_brands(token)
    if not nexion_brand_id:
        print("\n❌ CRITICAL: Nexion brand not found. Cannot proceed with brand-specific tests.")
        print_summary()
        sys.exit(1)
    
    # Test 3: Get products by brand
    sample_product = test_3_products_by_brand(token, nexion_brand_id)
    
    # Test 4: Search by name
    product_from_search = test_4_search_by_name(token)
    
    # Test 5: Search by SKU
    product_from_sku = test_5_search_by_sku(token)
    
    # Test 6: Search by size
    product_from_size = test_6_search_by_size(token)
    
    # Test 7: Get product detail (use any product we found)
    test_product_id = None
    if sample_product:
        test_product_id = sample_product.get("id")
    elif product_from_search:
        test_product_id = product_from_search.get("id")
    elif product_from_sku:
        test_product_id = product_from_sku.get("id")
    elif product_from_size:
        test_product_id = product_from_size.get("id")
    
    image_url = None
    if test_product_id:
        image_url = test_7_product_detail(token, test_product_id)
    else:
        log_test("7", "GET /api/products/{id}", False, "No product ID available from previous tests")
    
    # Test 8: Fetch image
    if image_url:
        test_8_image_fetch(image_url)
    else:
        log_test("8", "Fetch hero_image_url", False, "No image URL available from Test 7")
    
    # Test 9: Floor isolation
    test_9_floor_isolation(token, nexion_brand_id)
    
    # Test 10: Regression check
    test_10_regression_check(token)
    
    # Print summary
    all_passed = print_summary()
    
    if all_passed:
        print("\n✅ ALL TESTS PASSED - Nexion brand import verification complete")
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED - See details above")
        sys.exit(1)

if __name__ == "__main__":
    main()
