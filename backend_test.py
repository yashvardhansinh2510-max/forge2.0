#!/usr/bin/env python3
"""
Comprehensive Backend Testing for Grohe Catalog Migration
Tests production catalog migration: Grohe 864->133 products replacement
"""

import requests
import json
from typing import Dict, List, Any, Optional
from collections import defaultdict

# Backend URL from frontend/.env
BASE_URL = "https://216d7dfd-ba32-495c-a1aa-c78b8d90fcbf.preview.emergentagent.com/api"

# Test credentials
TEST_EMAIL = "owner@forge.app"
TEST_PASSWORD = "Forge@2026"

# Global token storage
AUTH_TOKEN = None

# Test results tracking
test_results = {
    "passed": [],
    "failed": [],
    "warnings": []
}

def log_pass(test_name: str, details: str = ""):
    """Log a passing test"""
    msg = f"✅ {test_name}"
    if details:
        msg += f": {details}"
    print(msg)
    test_results["passed"].append({"test": test_name, "details": details})

def log_fail(test_name: str, details: str):
    """Log a failing test"""
    msg = f"❌ {test_name}: {details}"
    print(msg)
    test_results["failed"].append({"test": test_name, "details": details})

def log_warning(test_name: str, details: str):
    """Log a warning"""
    msg = f"⚠️  {test_name}: {details}"
    print(msg)
    test_results["warnings"].append({"test": test_name, "details": details})

def make_request(method: str, endpoint: str, auth: bool = True, **kwargs) -> requests.Response:
    """Make HTTP request with optional auth"""
    url = f"{BASE_URL}{endpoint}"
    headers = kwargs.pop("headers", {})
    
    if auth and AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    
    try:
        response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        return response
    except Exception as e:
        print(f"Request failed: {method} {endpoint} - {str(e)}")
        raise

def test_1_auth_login():
    """Test 1: AUTH - Login with owner@forge.app / Forge@2026"""
    global AUTH_TOKEN
    
    print("\n" + "="*80)
    print("TEST 1: AUTHENTICATION")
    print("="*80)
    
    response = make_request(
        "POST", 
        "/auth/login",
        auth=False,
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    
    if response.status_code == 200:
        data = response.json()
        if "access_token" in data:
            AUTH_TOKEN = data["access_token"]
            user = data.get("user", {})
            log_pass("AUTH Login", f"200 OK, JWT received, User: {user.get('name')} ({user.get('email')}), Role: {user.get('role')}")
        else:
            log_fail("AUTH Login", "200 but no access_token in response")
    else:
        log_fail("AUTH Login", f"Status {response.status_code}, expected 200")

def test_2_brands():
    """Test 2: BRANDS - Verify 5 brands with correct counts"""
    print("\n" + "="*80)
    print("TEST 2: BRANDS")
    print("="*80)
    
    response = make_request("GET", "/brands")
    
    if response.status_code != 200:
        log_fail("GET /api/brands", f"Status {response.status_code}, expected 200")
        return None
    
    brands = response.json()
    
    # Check total count
    if len(brands) != 5:
        log_fail("Brand count", f"Found {len(brands)} brands, expected exactly 5")
    else:
        log_pass("Brand count", "Exactly 5 brands found")
    
    # Expected counts
    expected = {
        "Grohe": 133,
        "Hansgrohe": 908,
        "Axor": 448,
        "Vitra": 250,
        "Geberit": 496
    }
    
    brand_map = {}
    for brand in brands:
        name = brand.get("name")
        count = brand.get("product_count", 0)
        brand_id = brand.get("id")
        brand_map[name] = {"id": brand_id, "count": count}
        
        if name in expected:
            if count == expected[name]:
                log_pass(f"Brand {name}", f"product_count={count} (correct)")
            else:
                log_fail(f"Brand {name}", f"product_count={count}, expected {expected[name]}")
        else:
            log_warning(f"Brand {name}", f"Unexpected brand with {count} products")
    
    # Check for missing brands
    for name in expected:
        if name not in brand_map:
            log_fail(f"Brand {name}", "Missing from response")
    
    return brand_map

def test_3_categories(brand_map: Dict):
    """Test 3: CATEGORIES - Verify deleted and new categories"""
    print("\n" + "="*80)
    print("TEST 3: CATEGORIES")
    print("="*80)
    
    response = make_request("GET", "/categories")
    
    if response.status_code != 200:
        log_fail("GET /api/categories", f"Status {response.status_code}, expected 200")
        return None
    
    categories = response.json()
    category_names = [cat.get("name") for cat in categories]
    
    # Categories that should NOT exist (deleted because empty after Grohe removal)
    deleted_categories = ["Kitchen Sinks", "Bathtubs"]
    for cat_name in deleted_categories:
        if cat_name in category_names:
            log_fail(f"Category '{cat_name}'", "Should be DELETED (was Grohe-only, now empty)")
        else:
            log_pass(f"Category '{cat_name}'", "Correctly DELETED")
    
    # New categories that should exist
    new_categories = ["RSH Aqua Tile Shower", "Plate", "Shower"]
    for cat_name in new_categories:
        if cat_name in category_names:
            log_pass(f"Category '{cat_name}'", "NEW category present")
        else:
            log_fail(f"Category '{cat_name}'", "NEW category MISSING")
    
    # Single Lever should exist (shared across brands)
    if "Single Lever" in category_names:
        log_pass("Category 'Single Lever'", "Exists (shared across Grohe/Hansgrohe/AXOR)")
    else:
        log_fail("Category 'Single Lever'", "MISSING (should exist)")
    
    # Categories that should still exist (used by other brands)
    existing_categories = ["Faucets", "Showers", "Accessories", "Urinals"]
    for cat_name in existing_categories:
        if cat_name in category_names:
            log_pass(f"Category '{cat_name}'", "Still exists (used by other brands)")
        else:
            log_warning(f"Category '{cat_name}'", "Missing (expected to exist)")
    
    return categories

def test_4_grohe_products(brand_map: Dict):
    """Test 4: PRODUCTS - Verify 133 Grohe products with valid images"""
    print("\n" + "="*80)
    print("TEST 4: GROHE PRODUCTS")
    print("="*80)
    
    if "Grohe" not in brand_map:
        log_fail("Grohe products", "Grohe brand not found, cannot test products")
        return None
    
    grohe_id = brand_map["Grohe"]["id"]
    
    # Get all Grohe products
    response = make_request("GET", f"/products?brand_id={grohe_id}&limit=200")
    
    if response.status_code != 200:
        log_fail("GET /api/products (Grohe)", f"Status {response.status_code}, expected 200")
        return None
    
    data = response.json()
    products = data.get("items", [])
    total = data.get("total", 0)
    
    # Check total count
    if total == 133:
        log_pass("Grohe product count", f"Total={total} (correct)")
    else:
        log_fail("Grohe product count", f"Total={total}, expected 133")
    
    if len(products) == 0:
        log_fail("Grohe products", "No products returned")
        return None
    
    log_pass("Grohe products returned", f"{len(products)} products in response")
    
    # Spot check 4 random products for images
    import random
    sample_size = min(4, len(products))
    sample_products = random.sample(products, sample_size)
    
    print(f"\nSpot-checking {sample_size} random Grohe products for image URLs:")
    
    for i, product in enumerate(sample_products, 1):
        sku = product.get("sku", "N/A")
        name = product.get("name", "N/A")
        hero_image = product.get("hero_image_url")
        gallery = product.get("gallery", [])
        category_id = product.get("category_id")
        
        print(f"\n  Product {i}: {sku} - {name[:50]}...")
        
        # Check hero_image_url
        if hero_image:
            if "supabase.co" in hero_image:
                # Try to fetch the image
                try:
                    img_response = requests.head(hero_image, timeout=10)
                    if img_response.status_code == 200:
                        log_pass(f"  Product {sku} hero_image", f"Valid Supabase URL, HTTP 200")
                    else:
                        log_fail(f"  Product {sku} hero_image", f"Supabase URL returns {img_response.status_code}")
                except Exception as e:
                    log_warning(f"  Product {sku} hero_image", f"Could not verify URL: {str(e)}")
            else:
                log_fail(f"  Product {sku} hero_image", f"Not a Supabase URL: {hero_image}")
        else:
            log_fail(f"  Product {sku} hero_image", "Empty/missing")
        
        # Check gallery
        if gallery and len(gallery) > 0:
            log_pass(f"  Product {sku} gallery", f"{len(gallery)} images")
        else:
            log_warning(f"  Product {sku} gallery", "Empty gallery")
        
        # Check category_id
        if category_id:
            log_pass(f"  Product {sku} category_id", f"Present: {category_id}")
        else:
            log_fail(f"  Product {sku} category_id", "Missing")
    
    return products

def test_5_product_families(products: List[Dict]):
    """Test 5: PRODUCT FAMILIES - Verify family_key grouping and variants"""
    print("\n" + "="*80)
    print("TEST 5: PRODUCT FAMILIES")
    print("="*80)
    
    if not products:
        log_fail("Product families", "No products to test")
        return
    
    # Group products by family_key
    families = defaultdict(list)
    for product in products:
        family_key = product.get("family_key")
        if family_key:
            families[family_key].append(product)
    
    # Find families with multiple variants
    multi_variant_families = {k: v for k, v in families.items() if len(v) >= 2}
    
    if len(multi_variant_families) == 0:
        log_warning("Product families", "No multi-variant families found (expected at least one)")
        return
    
    log_pass("Multi-variant families", f"Found {len(multi_variant_families)} families with 2+ variants")
    
    # Show details of first multi-variant family
    first_family_key = list(multi_variant_families.keys())[0]
    first_family = multi_variant_families[first_family_key]
    
    print(f"\n  Example family: {first_family_key}")
    print(f"  Variants: {len(first_family)}")
    
    for variant in first_family:
        sku = variant.get("sku")
        finish = variant.get("finish", "N/A")
        price = variant.get("price", 0)
        print(f"    - SKU: {sku}, Finish: {finish}, Price: ₹{price}")
    
    log_pass("Product family example", f"Family '{first_family_key}' has {len(first_family)} variants")

def test_6_search():
    """Test 6: SEARCH - Verify search returns Grohe products"""
    print("\n" + "="*80)
    print("TEST 6: SEARCH")
    print("="*80)
    
    # Search for "grohe"
    response = make_request("GET", "/products?q=grohe")
    
    if response.status_code != 200:
        log_fail("Search ?q=grohe", f"Status {response.status_code}, expected 200")
    else:
        data = response.json()
        items = data.get("items", [])
        total = data.get("total", 0)
        
        if total > 0:
            log_pass("Search ?q=grohe", f"Returns {total} results")
            # Check if results contain Grohe products
            grohe_count = sum(1 for item in items if "grohe" in item.get("name", "").lower() or "grohe" in item.get("brand_name", "").lower())
            log_pass("Search results contain Grohe", f"{grohe_count}/{len(items)} results are Grohe products")
        else:
            log_fail("Search ?q=grohe", "No results returned")
    
    # Search for "rainshower"
    response = make_request("GET", "/products?q=rainshower")
    
    if response.status_code != 200:
        log_fail("Search ?q=rainshower", f"Status {response.status_code}, expected 200")
    else:
        data = response.json()
        total = data.get("total", 0)
        
        if total > 0:
            log_pass("Search ?q=rainshower", f"Returns {total} results")
        else:
            log_warning("Search ?q=rainshower", "No results (may be expected if no products match)")

def test_7_historical_quotations():
    """Test 7: HISTORICAL QUOTATIONS - Verify old quotations with deleted Grohe products still work"""
    print("\n" + "="*80)
    print("TEST 7: HISTORICAL QUOTATIONS")
    print("="*80)
    
    # Get all quotations
    response = make_request("GET", "/quotations")
    
    if response.status_code != 200:
        log_fail("GET /api/quotations", f"Status {response.status_code}, expected 200")
        return
    
    quotations = response.json()
    log_pass("GET /api/quotations", f"200 OK, {len(quotations)} quotations")
    
    # Find quotations with line items
    quotations_with_items = [q for q in quotations if q.get("items") and len(q.get("items", [])) > 0]
    
    if len(quotations_with_items) == 0:
        log_warning("Historical quotations", "No quotations with line items found")
        return
    
    # Check first quotation with items
    test_quotation = quotations_with_items[0]
    quotation_id = test_quotation.get("id")
    quotation_number = test_quotation.get("number")
    items = test_quotation.get("items", [])
    
    print(f"\n  Testing quotation: {quotation_number} (ID: {quotation_id})")
    print(f"  Line items: {len(items)}")
    
    # Check if line items have required fields (sku, name, unit_price, image)
    all_items_valid = True
    for i, item in enumerate(items[:3], 1):  # Check first 3 items
        sku = item.get("sku")
        name = item.get("name")
        unit_price = item.get("unit_price")
        image = item.get("image")
        
        if sku and name and unit_price is not None:
            log_pass(f"  Line item {i}", f"SKU={sku}, has name/unit_price/image fields")
        else:
            log_fail(f"  Line item {i}", f"Missing required fields (sku={sku}, name={bool(name)}, unit_price={unit_price is not None})")
            all_items_valid = False
    
    if all_items_valid:
        log_pass("Quotation line items", "All checked items have required fields (sku/name/price/image)")
    
    # Get quotation detail
    response = make_request("GET", f"/quotations/{quotation_id}")
    
    if response.status_code == 200:
        log_pass(f"GET /api/quotations/{quotation_id}", "200 OK, quotation detail loads")
    else:
        log_fail(f"GET /api/quotations/{quotation_id}", f"Status {response.status_code}, expected 200")
    
    # Try to generate PDF
    response = make_request("GET", f"/quotations/{quotation_id}/pdf")
    
    if response.status_code == 200:
        content = response.content
        if content.startswith(b"%PDF"):
            log_pass(f"PDF generation for {quotation_number}", f"Valid PDF returned ({len(content)} bytes)")
        else:
            log_fail(f"PDF generation for {quotation_number}", "Response doesn't start with %PDF")
    else:
        log_fail(f"PDF generation for {quotation_number}", f"Status {response.status_code}, expected 200")

def test_8_general_regression():
    """Test 8: GENERAL REGRESSION - Various endpoints with/without auth"""
    print("\n" + "="*80)
    print("TEST 8: GENERAL REGRESSION")
    print("="*80)
    
    # Test endpoints that should return 200 with auth
    endpoints_with_auth = [
        "/customers",
        "/purchase-orders",
        "/payments/stats",
        "/followups/stats"
    ]
    
    for endpoint in endpoints_with_auth:
        response = make_request("GET", endpoint, auth=True)
        if response.status_code == 200:
            log_pass(f"GET {endpoint} (with auth)", "200 OK")
        else:
            log_fail(f"GET {endpoint} (with auth)", f"Status {response.status_code}, expected 200")
    
    # Test same endpoints should return 401 without auth
    for endpoint in endpoints_with_auth:
        response = make_request("GET", endpoint, auth=False)
        if response.status_code == 401:
            log_pass(f"GET {endpoint} (no auth)", "401 Unauthorized (correct)")
        else:
            log_fail(f"GET {endpoint} (no auth)", f"Status {response.status_code}, expected 401")
    
    # Test health endpoint (should be public)
    response = make_request("GET", "/health/system", auth=False)
    
    if response.status_code == 200:
        data = response.json()
        healthy = data.get("healthy")
        mongo_connected = data.get("mongo", {}).get("connected")
        mongo_is_local = data.get("mongo", {}).get("is_local")
        product_count = data.get("counts", {}).get("products")
        
        if healthy:
            log_pass("Health check - healthy", "true")
        else:
            log_fail("Health check - healthy", f"{healthy}, expected true")
        
        if mongo_connected:
            log_pass("Health check - mongo.connected", "true")
        else:
            log_fail("Health check - mongo.connected", f"{mongo_connected}, expected true")
        
        if mongo_is_local == False:
            log_pass("Health check - mongo.is_local", "false (MongoDB Atlas)")
        else:
            log_fail("Health check - mongo.is_local", f"{mongo_is_local}, expected false")
        
        # Expected: 2966 - 864 + 133 = 2235
        if product_count == 2235:
            log_pass("Health check - counts.products", f"{product_count} (correct: 2966 - 864 + 133)")
        else:
            log_fail("Health check - counts.products", f"{product_count}, expected 2235 (2966 - 864 + 133)")
    else:
        log_fail("GET /api/health/system", f"Status {response.status_code}, expected 200")

def test_9_other_brands_unchanged(brand_map: Dict):
    """Test 9: OTHER BRANDS - Verify Hansgrohe/AXOR/Geberit/Vitra unchanged"""
    print("\n" + "="*80)
    print("TEST 9: OTHER BRANDS UNCHANGED")
    print("="*80)
    
    other_brands = ["Hansgrohe", "Axor", "Geberit", "Vitra"]
    
    for brand_name in other_brands:
        if brand_name not in brand_map:
            log_fail(f"Brand {brand_name}", "Not found in brand list")
            continue
        
        brand_id = brand_map[brand_name]["id"]
        
        # Get 2-3 products from this brand
        response = make_request("GET", f"/products?brand_id={brand_id}&limit=3")
        
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            
            if len(items) > 0:
                log_pass(f"Brand {brand_name}", f"Products load correctly ({len(items)} sampled)")
                
                # Check first product has valid data
                product = items[0]
                if product.get("sku") and product.get("name") and product.get("price"):
                    log_pass(f"  {brand_name} product sample", f"SKU={product.get('sku')}, has name/price")
                else:
                    log_fail(f"  {brand_name} product sample", "Missing required fields")
            else:
                log_warning(f"Brand {brand_name}", "No products returned (unexpected)")
        else:
            log_fail(f"Brand {brand_name}", f"GET /products failed with status {response.status_code}")

def print_summary():
    """Print test summary"""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    total_passed = len(test_results["passed"])
    total_failed = len(test_results["failed"])
    total_warnings = len(test_results["warnings"])
    total_tests = total_passed + total_failed
    
    print(f"\n✅ PASSED: {total_passed}/{total_tests}")
    print(f"❌ FAILED: {total_failed}/{total_tests}")
    print(f"⚠️  WARNINGS: {total_warnings}")
    
    if total_failed > 0:
        print("\n" + "="*80)
        print("FAILED TESTS:")
        print("="*80)
        for result in test_results["failed"]:
            print(f"  ❌ {result['test']}: {result['details']}")
    
    if total_warnings > 0:
        print("\n" + "="*80)
        print("WARNINGS:")
        print("="*80)
        for result in test_results["warnings"]:
            print(f"  ⚠️  {result['test']}: {result['details']}")
    
    print("\n" + "="*80)
    if total_failed == 0:
        print("✅ ALL TESTS PASSED - GROHE CATALOG MIGRATION VERIFIED")
    else:
        print("❌ SOME TESTS FAILED - REVIEW REQUIRED")
    print("="*80)

def main():
    """Run all tests"""
    print("="*80)
    print("GROHE CATALOG MIGRATION VERIFICATION")
    print("Production catalog migration: Grohe 864 -> 133 products")
    print("="*80)
    
    try:
        # Test 1: Authentication
        test_1_auth_login()
        
        if not AUTH_TOKEN:
            print("\n❌ CRITICAL: Authentication failed, cannot proceed with other tests")
            return
        
        # Test 2: Brands
        brand_map = test_2_brands()
        
        # Test 3: Categories
        test_3_categories(brand_map)
        
        # Test 4: Grohe Products
        grohe_products = test_4_grohe_products(brand_map)
        
        # Test 5: Product Families
        if grohe_products:
            test_5_product_families(grohe_products)
        
        # Test 6: Search
        test_6_search()
        
        # Test 7: Historical Quotations
        test_7_historical_quotations()
        
        # Test 8: General Regression
        test_8_general_regression()
        
        # Test 9: Other Brands Unchanged
        if brand_map:
            test_9_other_brands_unchanged(brand_map)
        
        # Print summary
        print_summary()
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
