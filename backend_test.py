#!/usr/bin/env python3
"""
VITRA Catalog Audit & Repair Verification Test Suite
Backend-only validation as per review request.
"""

import requests
import sys
from typing import Dict, List, Any, Optional

# Backend URL from frontend/.env
BASE_URL = "https://product-media-hub-2.preview.emergentagent.com/api"

# Test credentials from review request
TEST_EMAIL = "owner@forge.app"
TEST_PASSWORD = "Forge@2026"

# Global auth token
AUTH_TOKEN = None

# Test results tracking
test_results = {
    "passed": [],
    "failed": [],
    "warnings": []
}


def log_pass(test_name: str, details: str = ""):
    """Log a passed test"""
    msg = f"✅ PASS: {test_name}"
    if details:
        msg += f" - {details}"
    print(msg)
    test_results["passed"].append(test_name)


def log_fail(test_name: str, details: str):
    """Log a failed test"""
    msg = f"❌ FAIL: {test_name} - {details}"
    print(msg)
    test_results["failed"].append(f"{test_name}: {details}")


def log_warning(test_name: str, details: str):
    """Log a warning"""
    msg = f"⚠️  WARNING: {test_name} - {details}"
    print(msg)
    test_results["warnings"].append(f"{test_name}: {details}")


def get_headers() -> Dict[str, str]:
    """Get headers with auth token"""
    headers = {"Content-Type": "application/json"}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    return headers


def test_1_auth_login():
    """TEST 1: Authentication - POST /api/auth/login"""
    global AUTH_TOKEN
    print("\n" + "="*80)
    print("TEST 1: AUTHENTICATION")
    print("="*80)
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            AUTH_TOKEN = data.get("access_token") or data.get("token")
            user = data.get("user", {})
            
            if AUTH_TOKEN:
                log_pass("Auth Login", f"User: {user.get('full_name')} ({user.get('email')}), Role: {user.get('role')}")
                return True
            else:
                log_fail("Auth Login", "No token in response")
                return False
        else:
            log_fail("Auth Login", f"Status {response.status_code}: {response.text[:200]}")
            return False
            
    except Exception as e:
        log_fail("Auth Login", f"Exception: {str(e)}")
        return False


def get_vitra_brand_id() -> Optional[str]:
    """Get Vitra brand ID"""
    try:
        response = requests.get(f"{BASE_URL}/brands", headers=get_headers(), timeout=10)
        if response.status_code == 200:
            brands = response.json()
            for brand in brands:
                if brand.get("name", "").lower() == "vitra":
                    return brand.get("id")
        return None
    except Exception as e:
        print(f"Error getting Vitra brand ID: {e}")
        return None


def test_2_repair_1_price_correction():
    """TEST 2: REPAIR #1 - Price correction for SKU 7426B420H0001"""
    print("\n" + "="*80)
    print("TEST 2: REPAIR #1 - PRICE CORRECTION (SKU 7426B420H0001)")
    print("="*80)
    
    vitra_id = get_vitra_brand_id()
    if not vitra_id:
        log_fail("Repair #1 - Get Vitra Brand", "Could not find Vitra brand")
        return False
    
    try:
        # Search for the specific SKU
        response = requests.get(
            f"{BASE_URL}/products",
            params={"q": "7426B420H0001"},
            headers=get_headers(),
            timeout=10
        )
        
        if response.status_code != 200:
            log_fail("Repair #1 - Search Product", f"Status {response.status_code}")
            return False
        
        data = response.json()
        items = data.get("items", [])
        
        # Filter to exact SKU match
        product = None
        for item in items:
            if item.get("sku") == "7426B420H0001":
                product = item
                break
        
        if not product:
            log_fail("Repair #1 - Find Product", "SKU 7426B420H0001 not found")
            return False
        sku = product.get("sku")
        mrp = product.get("mrp")
        price = product.get("price")
        name = product.get("name", "")
        
        print(f"Found product: {name}")
        print(f"  SKU: {sku}")
        print(f"  MRP: {mrp}")
        print(f"  Price: {price}")
        
        # Verify both mrp and price are 30680
        if mrp == 30680 and price == 30680:
            log_pass("Repair #1 - Price Correction", f"SKU {sku}: mrp={mrp}, price={price} (correct)")
            return True
        else:
            log_fail("Repair #1 - Price Correction", 
                    f"SKU {sku}: Expected mrp=30680, price=30680, Got mrp={mrp}, price={price}")
            return False
            
    except Exception as e:
        log_fail("Repair #1 - Exception", str(e))
        return False


def test_3_repair_2_broken_image_removed():
    """TEST 3: REPAIR #2 - Broken image removed for SKU 7041B003H0090"""
    print("\n" + "="*80)
    print("TEST 3: REPAIR #2 - BROKEN IMAGE REMOVED (SKU 7041B003H0090)")
    print("="*80)
    
    vitra_id = get_vitra_brand_id()
    if not vitra_id:
        log_fail("Repair #2 - Get Vitra Brand", "Could not find Vitra brand")
        return False
    
    try:
        # Search for the specific SKU
        response = requests.get(
            f"{BASE_URL}/products",
            params={"q": "7041B003H0090"},
            headers=get_headers(),
            timeout=10
        )
        
        if response.status_code != 200:
            log_fail("Repair #2 - Search Product", f"Status {response.status_code}")
            return False
        
        data = response.json()
        items = data.get("items", [])
        
        # Filter to exact SKU match
        product = None
        for item in items:
            if item.get("sku") == "7041B003H0090":
                product = item
                break
        
        if not product:
            log_fail("Repair #2 - Find Product", "SKU 7041B003H0090 not found")
            return False
        sku = product.get("sku")
        name = product.get("name", "")
        gallery = product.get("gallery", [])
        
        print(f"Found product: {name}")
        print(f"  SKU: {sku}")
        print(f"  Gallery count: {len(gallery)}")
        
        # Check for gallery images (role=gallery should be removed)
        gallery_images = [m for m in gallery if m.get("role") == "gallery"]
        hero_images = [m for m in gallery if m.get("role") == "hero"]
        
        print(f"  Hero images: {len(hero_images)}")
        print(f"  Gallery images: {len(gallery_images)}")
        
        # Verify NO gallery images exist (the broken gallery image was removed)
        if gallery_images:
            log_fail("Repair #2 - Gallery Images", 
                    f"Expected 0 gallery images, found {len(gallery_images)}")
            return False
        
        # Verify at least one hero image exists
        if not hero_images:
            log_fail("Repair #2 - Hero Image", "No hero image found")
            return False
        
        # Check the first hero image
        hero = hero_images[0]
        role = hero.get("role")
        url = hero.get("url")
        
        print(f"  Primary hero role: {role}")
        print(f"  Primary hero URL: {url}")
        
        # Verify it's a supabase.co URL
        if "supabase.co" not in url:
            log_fail("Repair #2 - Media URL", f"Expected supabase.co URL, got: {url}")
            return False
        
        # Verify the URL returns HTTP 200
        try:
            img_response = requests.head(url, timeout=10)
            if img_response.status_code == 200:
                log_pass("Repair #2 - Broken Image Removed", 
                        f"SKU {sku}: No gallery images (broken one removed), hero image URL returns HTTP 200")
                return True
            else:
                log_fail("Repair #2 - Image URL Check", 
                        f"Image URL returned status {img_response.status_code}")
                return False
        except Exception as e:
            log_fail("Repair #2 - Image URL Check", f"Failed to check image URL: {e}")
            return False
            
    except Exception as e:
        log_fail("Repair #2 - Exception", str(e))
        return False


def test_4_brand_count_unchanged():
    """TEST 4: Brand counts unchanged (Vitra=250, others unchanged)"""
    print("\n" + "="*80)
    print("TEST 4: BRAND COUNT UNCHANGED")
    print("="*80)
    
    expected_counts = {
        "vitra": 250,
        "hansgrohe": 908,
        "axor": 448,
        "grohe": 508,
        "geberit": 496
    }
    
    try:
        response = requests.get(f"{BASE_URL}/brands", headers=get_headers(), timeout=10)
        
        if response.status_code != 200:
            log_fail("Brand Count - API Call", f"Status {response.status_code}")
            return False
        
        brands = response.json()
        all_correct = True
        
        print("\nBrand counts:")
        for brand in brands:
            name = brand.get("name", "").lower()
            count = brand.get("product_count", 0)
            expected = expected_counts.get(name)
            
            if expected is not None:
                status = "✓" if count == expected else "✗"
                print(f"  {status} {brand.get('name')}: {count} (expected {expected})")
                
                if count != expected:
                    log_fail(f"Brand Count - {brand.get('name')}", 
                            f"Expected {expected}, got {count}")
                    all_correct = False
        
        if all_correct:
            log_pass("Brand Count Unchanged", "All brand counts match expected values")
            return True
        else:
            return False
            
    except Exception as e:
        log_fail("Brand Count - Exception", str(e))
        return False


def test_5_spot_check_untouched_vitra_products():
    """TEST 5: Spot check 5 random Vitra products (not the 2 repaired ones)"""
    print("\n" + "="*80)
    print("TEST 5: SPOT CHECK UNTOUCHED VITRA PRODUCTS")
    print("="*80)
    
    vitra_id = get_vitra_brand_id()
    if not vitra_id:
        log_fail("Spot Check - Get Vitra Brand", "Could not find Vitra brand")
        return False
    
    excluded_skus = ["7426B420H0001", "7041B003H0090"]
    
    try:
        # Get Vitra products
        response = requests.get(
            f"{BASE_URL}/products",
            params={"brand_id": vitra_id, "limit": 20},
            headers=get_headers(),
            timeout=10
        )
        
        if response.status_code != 200:
            log_fail("Spot Check - Get Products", f"Status {response.status_code}")
            return False
        
        data = response.json()
        items = data.get("items", [])
        
        # Filter out the repaired products
        untouched = [p for p in items if p.get("sku") not in excluded_skus]
        
        if len(untouched) < 5:
            log_warning("Spot Check", f"Only {len(untouched)} untouched products available")
        
        # Check first 5 untouched products
        check_count = min(5, len(untouched))
        all_ok = True
        
        print(f"\nChecking {check_count} untouched Vitra products:")
        
        for i, product in enumerate(untouched[:check_count], 1):
            sku = product.get("sku")
            name = product.get("name", "")
            price = product.get("price")
            category = product.get("category_name", "")
            media = product.get("media", [])
            
            print(f"\n  {i}. SKU: {sku}")
            print(f"     Name: {name}")
            print(f"     Price: {price}")
            print(f"     Category: {category}")
            print(f"     Media count: {len(media)}")
            
            # Basic validation
            if not sku or not name:
                log_fail(f"Spot Check - Product {i}", "Missing SKU or name")
                all_ok = False
                continue
            
            if price is None or price < 0:
                log_fail(f"Spot Check - Product {i}", f"Invalid price: {price}")
                all_ok = False
                continue
            
            # Check images if present
            if media:
                for media_entry in media[:1]:  # Check first image
                    url = media_entry.get("url")
                    if url:
                        try:
                            img_response = requests.head(url, timeout=5)
                            if img_response.status_code == 200:
                                print(f"     Image: HTTP 200 ✓")
                            else:
                                log_warning(f"Spot Check - Product {i} Image", 
                                          f"Image returned status {img_response.status_code}")
                        except Exception as e:
                            log_warning(f"Spot Check - Product {i} Image", 
                                      f"Failed to check image: {e}")
        
        if all_ok:
            log_pass("Spot Check Untouched Products", 
                    f"Checked {check_count} products - all have valid data")
            return True
        else:
            return False
            
    except Exception as e:
        log_fail("Spot Check - Exception", str(e))
        return False


def test_6_search_functionality():
    """TEST 6: Search functionality for Vitra products"""
    print("\n" + "="*80)
    print("TEST 6: SEARCH FUNCTIONALITY")
    print("="*80)
    
    search_tests = [
        ("vitra", "Brand name search"),
        ("memoria", "Product name search"),
        ("integra", "Product name search"),
        ("7426B420H0001", "Exact SKU search")
    ]
    
    all_ok = True
    
    for query, description in search_tests:
        try:
            response = requests.get(
                f"{BASE_URL}/products",
                params={"q": query},
                headers=get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                total = data.get("total", 0)
                
                if items:
                    print(f"  ✓ Search '{query}' ({description}): {total} results")
                    log_pass(f"Search - {description}", f"Query '{query}' returned {total} results")
                else:
                    log_warning(f"Search - {description}", f"Query '{query}' returned 0 results")
            else:
                log_fail(f"Search - {description}", 
                        f"Query '{query}' returned status {response.status_code}")
                all_ok = False
                
        except Exception as e:
            log_fail(f"Search - {description}", f"Query '{query}' exception: {e}")
            all_ok = False
    
    return all_ok


def test_7_quotations_check():
    """TEST 7: Check quotations referencing repaired SKUs"""
    print("\n" + "="*80)
    print("TEST 7: QUOTATIONS CHECK")
    print("="*80)
    
    repaired_skus = ["7426B420H0001", "7041B003H0090"]
    
    try:
        # Get all quotations
        response = requests.get(
            f"{BASE_URL}/quotations",
            headers=get_headers(),
            timeout=10
        )
        
        if response.status_code != 200:
            log_fail("Quotations Check - Get Quotations", f"Status {response.status_code}")
            return False
        
        quotations = response.json()
        print(f"Total quotations: {len(quotations)}")
        
        # Check if any quotation references the repaired SKUs
        found_quotations = []
        
        for quot in quotations:
            quot_id = quot.get("id")
            quot_number = quot.get("number")
            line_items = quot.get("line_items", [])
            
            for item in line_items:
                if item.get("sku") in repaired_skus:
                    found_quotations.append({
                        "id": quot_id,
                        "number": quot_number,
                        "sku": item.get("sku")
                    })
        
        if not found_quotations:
            print("  No quotations found referencing repaired SKUs (expected/OK)")
            log_pass("Quotations Check", "No quotations reference repaired SKUs")
            return True
        
        print(f"\nFound {len(found_quotations)} quotation(s) referencing repaired SKUs:")
        
        # Check each quotation in detail
        all_ok = True
        for quot_info in found_quotations:
            quot_id = quot_info["id"]
            quot_number = quot_info["number"]
            sku = quot_info["sku"]
            
            print(f"\n  Quotation {quot_number} (ID: {quot_id}) references SKU {sku}")
            
            # Get full quotation details
            try:
                detail_response = requests.get(
                    f"{BASE_URL}/quotations/{quot_id}",
                    headers=get_headers(),
                    timeout=10
                )
                
                if detail_response.status_code == 200:
                    print(f"    ✓ GET /api/quotations/{quot_id}: 200 OK")
                    
                    # Try to generate PDF
                    try:
                        pdf_response = requests.get(
                            f"{BASE_URL}/quotations/{quot_id}/pdf",
                            headers=get_headers(),
                            timeout=30
                        )
                        
                        if pdf_response.status_code == 200:
                            print(f"    ✓ PDF generation: 200 OK ({len(pdf_response.content)} bytes)")
                            log_pass(f"Quotations Check - {quot_number}", 
                                   f"Quotation with SKU {sku} still works, PDF generates")
                        else:
                            log_fail(f"Quotations Check - {quot_number} PDF", 
                                   f"PDF generation failed: status {pdf_response.status_code}")
                            all_ok = False
                    except Exception as e:
                        log_fail(f"Quotations Check - {quot_number} PDF", 
                               f"PDF generation exception: {e}")
                        all_ok = False
                else:
                    log_fail(f"Quotations Check - {quot_number}", 
                           f"GET failed: status {detail_response.status_code}")
                    all_ok = False
                    
            except Exception as e:
                log_fail(f"Quotations Check - {quot_number}", f"Exception: {e}")
                all_ok = False
        
        return all_ok
        
    except Exception as e:
        log_fail("Quotations Check - Exception", str(e))
        return False


def test_8_general_regression():
    """TEST 8: General regression checks"""
    print("\n" + "="*80)
    print("TEST 8: GENERAL REGRESSION")
    print("="*80)
    
    all_ok = True
    
    # 8a. Health check
    try:
        response = requests.get(f"{BASE_URL}/health/system", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            healthy = data.get("healthy")
            product_count = data.get("counts", {}).get("products")
            
            print(f"  Health check: healthy={healthy}, products={product_count}")
            
            if healthy and product_count == 2610:
                log_pass("General Regression - Health", 
                        f"healthy=true, counts.products=2610")
            else:
                log_fail("General Regression - Health", 
                        f"Expected healthy=true and products=2610, got healthy={healthy}, products={product_count}")
                all_ok = False
        else:
            log_fail("General Regression - Health", f"Status {response.status_code}")
            all_ok = False
    except Exception as e:
        log_fail("General Regression - Health", str(e))
        all_ok = False
    
    # 8b. Other endpoints
    endpoints = [
        ("/customers", "Customers"),
        ("/purchase-orders", "Purchase Orders"),
        ("/payments/stats", "Payments Stats")
    ]
    
    for endpoint, name in endpoints:
        try:
            response = requests.get(f"{BASE_URL}{endpoint}", headers=get_headers(), timeout=10)
            
            if response.status_code == 200:
                print(f"  ✓ GET {endpoint}: 200 OK")
            else:
                log_fail(f"General Regression - {name}", f"Status {response.status_code}")
                all_ok = False
        except Exception as e:
            log_fail(f"General Regression - {name}", str(e))
            all_ok = False
    
    if all_ok:
        log_pass("General Regression", "All endpoints working correctly")
    
    return all_ok


def test_9_smoke_check_other_brands():
    """TEST 9: Smoke check 2 products each from other brands"""
    print("\n" + "="*80)
    print("TEST 9: SMOKE CHECK OTHER BRANDS")
    print("="*80)
    
    brands_to_check = ["Hansgrohe", "Axor", "Geberit", "Grohe"]
    all_ok = True
    
    try:
        # Get all brands
        response = requests.get(f"{BASE_URL}/brands", headers=get_headers(), timeout=10)
        
        if response.status_code != 200:
            log_fail("Smoke Check - Get Brands", f"Status {response.status_code}")
            return False
        
        brands = response.json()
        brand_map = {b.get("name"): b.get("id") for b in brands}
        
        for brand_name in brands_to_check:
            brand_id = brand_map.get(brand_name)
            
            if not brand_id:
                log_warning("Smoke Check", f"Brand {brand_name} not found")
                continue
            
            print(f"\n  Checking {brand_name}:")
            
            # Get 2 products from this brand
            response = requests.get(
                f"{BASE_URL}/products",
                params={"brand_id": brand_id, "limit": 2},
                headers=get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                log_fail(f"Smoke Check - {brand_name}", f"Status {response.status_code}")
                all_ok = False
                continue
            
            data = response.json()
            items = data.get("items", [])
            
            if len(items) < 2:
                log_warning(f"Smoke Check - {brand_name}", f"Only {len(items)} products available")
            
            for i, product in enumerate(items[:2], 1):
                sku = product.get("sku")
                name = product.get("name", "")[:50]
                
                print(f"    {i}. {sku}: {name}...")
                
                # Check if product loads fine
                if not sku or not name:
                    log_fail(f"Smoke Check - {brand_name} Product {i}", "Missing SKU or name")
                    all_ok = False
        
        if all_ok:
            log_pass("Smoke Check Other Brands", "All brands load fine")
        
        return all_ok
        
    except Exception as e:
        log_fail("Smoke Check - Exception", str(e))
        return False


def print_summary():
    """Print test summary"""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    total = len(test_results["passed"]) + len(test_results["failed"])
    passed = len(test_results["passed"])
    failed = len(test_results["failed"])
    warnings = len(test_results["warnings"])
    
    print(f"\nTotal Tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⚠️  Warnings: {warnings}")
    
    if test_results["failed"]:
        print("\n" + "="*80)
        print("FAILED TESTS:")
        print("="*80)
        for failure in test_results["failed"]:
            print(f"  ❌ {failure}")
    
    if test_results["warnings"]:
        print("\n" + "="*80)
        print("WARNINGS:")
        print("="*80)
        for warning in test_results["warnings"]:
            print(f"  ⚠️  {warning}")
    
    print("\n" + "="*80)
    
    return failed == 0


def main():
    """Main test runner"""
    print("="*80)
    print("VITRA CATALOG AUDIT & REPAIR VERIFICATION")
    print("Backend-only validation")
    print("="*80)
    
    # Run all tests in sequence
    tests = [
        test_1_auth_login,
        test_2_repair_1_price_correction,
        test_3_repair_2_broken_image_removed,
        test_4_brand_count_unchanged,
        test_5_spot_check_untouched_vitra_products,
        test_6_search_functionality,
        test_7_quotations_check,
        test_8_general_regression,
        test_9_smoke_check_other_brands
    ]
    
    for test_func in tests:
        try:
            test_func()
        except Exception as e:
            print(f"\n❌ CRITICAL ERROR in {test_func.__name__}: {e}")
            test_results["failed"].append(f"{test_func.__name__}: Critical exception - {e}")
    
    # Print summary
    success = print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
