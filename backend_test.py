#!/usr/bin/env python3
"""
GROHE Catalog Batch 3 (Additive) Verification Test Suite
Tests the 3rd additive Grohe catalog batch with special attention to duplicate-SKU incident.
Grohe should now be exactly 500 products (was 299 before this batch).
"""

import requests
import sys
from typing import Dict, List, Any
from collections import Counter

# Backend URL from frontend/.env
BASE_URL = "https://216d7dfd-ba32-495c-a1aa-c78b8d90fcbf.preview.emergentagent.com/api"

# Test credentials
EMAIL = "owner@forge.app"
PASSWORD = "Forge@2026"

# Expected values
EXPECTED_GROHE_COUNT = 500
EXPECTED_HANSGROHE_COUNT = 908
EXPECTED_AXOR_COUNT = 448
EXPECTED_VITRA_COUNT = 250
EXPECTED_GEBERIT_COUNT = 496
EXPECTED_TOTAL_PRODUCTS = 2602

# New categories from batch 3
NEW_CATEGORIES_BATCH3 = [
    "Wall Mounted",
    "Tall Body Basin Mixer",
    "Trigger & Tank",
    "Spout"
]

# Thermostat should now include Grohe products (previously only Hansgrohe+Axor)
THERMOSTAT_CATEGORY = "Thermostat"

# Previous categories from earlier batches that should still exist
PREVIOUS_CATEGORIES = [
    "RSH Aqua Tile Shower",
    "Plate",
    "Shower",
    "Single Lever",
    "Bau Line",
    "Body Jet",
    "Handshower",
    "Kitchen Tap",
    "Short Body Basin Mixer"
]

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.errors = []
        
    def pass_test(self, message: str):
        self.passed += 1
        print(f"✅ {message}")
        
    def fail_test(self, message: str):
        self.failed += 1
        self.errors.append(message)
        print(f"❌ {message}")
        
    def warn_test(self, message: str):
        self.warnings += 1
        print(f"⚠️  {message}")
        
    def print_summary(self):
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print(f"PASSED: {self.passed}")
        print(f"FAILED: {self.failed}")
        print(f"WARNINGS: {self.warnings}")
        
        if self.errors:
            print("\n🔴 CRITICAL FAILURES:")
            for error in self.errors:
                print(f"  • {error}")
        
        return self.failed == 0

def test_auth() -> str:
    """Test 1: Authentication"""
    print("\n" + "="*80)
    print("TEST 1: AUTHENTICATION")
    print("="*80)
    
    results = TestResults()
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            
            if token:
                results.pass_test(f"POST /api/auth/login {EMAIL}/{PASSWORD} -> 200 OK")
                results.pass_test(f"Valid JWT token received ({len(token)} chars)")
                results.pass_test(f"User: {user.get('email')}, Role: {user.get('role')}")
                return token
            else:
                results.fail_test("No access_token in response")
                return None
        else:
            results.fail_test(f"POST /api/auth/login -> {response.status_code} (expected 200)")
            return None
            
    except Exception as e:
        results.fail_test(f"Authentication failed: {str(e)}")
        return None

def test_brands(token: str) -> Dict[str, Any]:
    """Test 2: Brands verification - Grohe=500, others unchanged"""
    print("\n" + "="*80)
    print("TEST 2: BRANDS")
    print("="*80)
    
    results = TestResults()
    brands_map = {}
    
    try:
        response = requests.get(
            f"{BASE_URL}/brands",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            results.fail_test(f"GET /api/brands -> {response.status_code} (expected 200)")
            return brands_map
            
        brands = response.json()
        
        for brand in brands:
            name = brand.get("name")
            count = brand.get("product_count", 0)
            brands_map[name] = {
                "id": brand.get("id"),
                "count": count
            }
        
        # Check Grohe count (CRITICAL)
        grohe_count = brands_map.get("Grohe", {}).get("count", 0)
        if grohe_count == EXPECTED_GROHE_COUNT:
            results.pass_test(f"Grohe product_count={grohe_count} (expected {EXPECTED_GROHE_COUNT}) — CORRECT ✓")
        else:
            results.fail_test(f"Grohe product_count={grohe_count} (expected {EXPECTED_GROHE_COUNT}) — INCORRECT")
        
        # Check other brands unchanged
        checks = [
            ("Hansgrohe", EXPECTED_HANSGROHE_COUNT),
            ("Axor", EXPECTED_AXOR_COUNT),
            ("Vitra", EXPECTED_VITRA_COUNT),
            ("Geberit", EXPECTED_GEBERIT_COUNT)
        ]
        
        for brand_name, expected_count in checks:
            actual_count = brands_map.get(brand_name, {}).get("count", 0)
            if actual_count == expected_count:
                results.pass_test(f"{brand_name}={actual_count} (unchanged) — CORRECT ✓")
            else:
                results.fail_test(f"{brand_name}={actual_count} (expected {expected_count}) — INCORRECT")
        
        results.print_summary()
        return brands_map
        
    except Exception as e:
        results.fail_test(f"Brands test failed: {str(e)}")
        return brands_map

def test_duplicate_skus(token: str, grohe_id: str) -> bool:
    """Test 3: CRITICAL - Zero duplicate SKUs in Grohe products"""
    print("\n" + "="*80)
    print("TEST 3: CRITICAL - ZERO DUPLICATE SKUS")
    print("="*80)
    
    results = TestResults()
    
    try:
        # Fetch ALL Grohe products (limit=600 to ensure we get all 500)
        all_products = []
        limit = 600
        offset = 0
        
        while True:
            response = requests.get(
                f"{BASE_URL}/products",
                params={"brand_id": grohe_id, "limit": limit, "offset": offset},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            
            if response.status_code != 200:
                results.fail_test(f"GET /api/products?brand_id={grohe_id} -> {response.status_code}")
                return False
            
            data = response.json()
            products = data.get("items", [])
            
            if not products:
                break
                
            all_products.extend(products)
            
            # If we got fewer than limit, we've reached the end
            if len(products) < limit:
                break
                
            offset += limit
        
        total_count = len(all_products)
        results.pass_test(f"Retrieved {total_count} Grohe products")
        
        # Extract all SKUs
        skus = [p.get("sku") for p in all_products if p.get("sku")]
        
        # Count SKU occurrences
        sku_counts = Counter(skus)
        
        # Find duplicates
        duplicates = {sku: count for sku, count in sku_counts.items() if count > 1}
        
        if duplicates:
            results.fail_test(f"CRITICAL: Found {len(duplicates)} duplicate SKUs in Grohe products:")
            for sku, count in duplicates.items():
                results.fail_test(f"  • SKU '{sku}' appears {count} times")
            return False
        else:
            results.pass_test(f"ZERO duplicate SKUs found in {total_count} Grohe products — VERIFIED ✓")
            results.pass_test(f"All {len(skus)} SKUs are unique")
            return True
        
    except Exception as e:
        results.fail_test(f"Duplicate SKU check failed: {str(e)}")
        return False
    finally:
        results.print_summary()

def test_categories(token: str, brands_map: Dict[str, Any]) -> Dict[str, Any]:
    """Test 4: Categories verification"""
    print("\n" + "="*80)
    print("TEST 4: CATEGORIES")
    print("="*80)
    
    results = TestResults()
    categories_map = {}
    
    try:
        response = requests.get(
            f"{BASE_URL}/categories",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            results.fail_test(f"GET /api/categories -> {response.status_code}")
            return categories_map
        
        categories = response.json()
        
        for cat in categories:
            name = cat.get("name")
            categories_map[name] = {
                "id": cat.get("id"),
                "count": cat.get("product_count", 0)
            }
        
        # Check new categories from batch 3
        print("\n4 NEW CATEGORIES FROM BATCH 3 (all should exist with product_count > 0):")
        for cat_name in NEW_CATEGORIES_BATCH3:
            if cat_name in categories_map:
                count = categories_map[cat_name]["count"]
                if count > 0:
                    results.pass_test(f'"{cat_name}" — product_count={count}')
                else:
                    results.fail_test(f'"{cat_name}" — product_count={count} (expected > 0)')
            else:
                results.fail_test(f'"{cat_name}" — NOT FOUND')
        
        # Check Thermostat category (should now include Grohe)
        print("\nTHERMOSTAT CATEGORY (should now include Grohe products):")
        if THERMOSTAT_CATEGORY in categories_map:
            count = categories_map[THERMOSTAT_CATEGORY]["count"]
            results.pass_test(f'"{THERMOSTAT_CATEGORY}" — product_count={count}')
            # Note: We can't easily verify it includes Grohe without fetching products
            results.warn_test(f'"{THERMOSTAT_CATEGORY}" existence verified, but Grohe inclusion requires product fetch')
        else:
            results.fail_test(f'"{THERMOSTAT_CATEGORY}" — NOT FOUND')
        
        # Check "Spouts" (plural) - should be unchanged (Hansgrohe+Axor only)
        print("\nSPOUTS (plural) CATEGORY (should be unchanged, Hansgrohe+Axor only):")
        if "Spouts" in categories_map:
            count = categories_map["Spouts"]["count"]
            results.pass_test(f'"Spouts" (plural) — product_count={count} (exists)')
            results.warn_test(f'"Spouts" (plural) brand verification requires product fetch')
        else:
            results.warn_test('"Spouts" (plural) — NOT FOUND (may not exist in this catalog)')
        
        # Check previous categories from earlier batches
        print("\nPREVIOUS CATEGORIES FROM EARLIER BATCHES (should still exist):")
        for cat_name in PREVIOUS_CATEGORIES:
            if cat_name in categories_map:
                count = categories_map[cat_name]["count"]
                results.pass_test(f'"{cat_name}" — product_count={count}')
            else:
                results.fail_test(f'"{cat_name}" — NOT FOUND')
        
        results.print_summary()
        return categories_map
        
    except Exception as e:
        results.fail_test(f"Categories test failed: {str(e)}")
        return categories_map

def test_images(token: str, categories_map: Dict[str, Any], grohe_id: str):
    """Test 5: Images spot-check for new categories"""
    print("\n" + "="*80)
    print("TEST 5: IMAGES SPOT-CHECK")
    print("="*80)
    
    results = TestResults()
    
    # Categories to check (5 newest from batch 3)
    categories_to_check = NEW_CATEGORIES_BATCH3 + [THERMOSTAT_CATEGORY]
    
    try:
        for cat_name in categories_to_check:
            if cat_name not in categories_map:
                results.fail_test(f'Category "{cat_name}" not found, skipping image check')
                continue
            
            cat_id = categories_map[cat_name]["id"]
            
            print(f'\n"{cat_name}" (spot-checking 2-3 products):')
            
            # Fetch products from this category
            response = requests.get(
                f"{BASE_URL}/products",
                params={"category_id": cat_id, "brand_id": grohe_id, "limit": 3},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            
            if response.status_code != 200:
                results.fail_test(f"Failed to fetch products for {cat_name}: {response.status_code}")
                continue
            
            data = response.json()
            products = data.get("items", [])
            
            if not products:
                results.warn_test(f"No products found in {cat_name}")
                continue
            
            # Check 2-3 products
            for i, product in enumerate(products[:3], 1):
                sku = product.get("sku", "N/A")
                # Check both hero_image and hero_image_url fields
                hero_image = product.get("hero_image") or product.get("hero_image_url")
                
                if not hero_image:
                    results.fail_test(f"Product {i} (SKU={sku}): No hero_image or hero_image_url")
                    continue
                
                # Check if URL is from supabase.co
                if "supabase.co" not in hero_image:
                    results.fail_test(f"Product {i} (SKU={sku}): Hero image not from supabase.co: {hero_image}")
                    continue
                
                # Check if image URL returns HTTP 200
                try:
                    img_response = requests.head(hero_image, timeout=5)
                    if img_response.status_code == 200:
                        results.pass_test(f"Product {i}: SKU={sku}, Hero image URL valid (HTTP 200, supabase.co)")
                    else:
                        results.fail_test(f"Product {i} (SKU={sku}): Hero image returned HTTP {img_response.status_code}")
                except Exception as e:
                    results.fail_test(f"Product {i} (SKU={sku}): Failed to fetch hero image: {str(e)}")
        
        results.print_summary()
        
    except Exception as e:
        results.fail_test(f"Images test failed: {str(e)}")
        results.print_summary()

def test_earlier_batch_products(token: str, grohe_id: str):
    """Test 6: Confirm products from earlier batches still present"""
    print("\n" + "="*80)
    print("TEST 6: EARLIER BATCH PRODUCTS PRESERVED")
    print("="*80)
    
    results = TestResults()
    
    # Sample SKUs from earlier batches (from test_result.md history)
    # Batch 1 SKUs
    batch1_skus = [
        "104992DL00",  # RSH Aqua Tile Shower
        "1068690000",  # Plate
        "26565000",    # Shower
        "33963000"     # Single Lever
    ]
    
    # Batch 2 SKUs
    batch2_skus = [
        "24274001",    # Bau Line
        "26801A00",    # Body Jet
        "27573ALC",    # Handshower
        "2201600M"     # Kitchen Tap
    ]
    
    all_test_skus = batch1_skus + batch2_skus
    
    try:
        for sku in all_test_skus:
            response = requests.get(
                f"{BASE_URL}/products",
                params={"brand_id": grohe_id, "sku": sku, "limit": 1},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            
            if response.status_code != 200:
                results.fail_test(f"Failed to search for SKU {sku}: {response.status_code}")
                continue
            
            data = response.json()
            products = data.get("items", [])
            
            if products:
                product = products[0]
                results.pass_test(f"SKU {sku} — Still present (name: {product.get('name', 'N/A')[:50]}...)")
            else:
                results.fail_test(f"SKU {sku} — NOT FOUND (should be present from earlier batch)")
        
        results.print_summary()
        
    except Exception as e:
        results.fail_test(f"Earlier batch products test failed: {str(e)}")
        results.print_summary()

def test_general_regression(token: str):
    """Test 7: General regression tests"""
    print("\n" + "="*80)
    print("TEST 7: GENERAL REGRESSION")
    print("="*80)
    
    results = TestResults()
    
    endpoints = [
        ("GET /api/quotations", f"{BASE_URL}/quotations"),
        ("GET /api/purchase-orders", f"{BASE_URL}/purchase-orders"),
        ("GET /api/payments/stats", f"{BASE_URL}/payments/stats"),
        ("GET /api/followups/stats", f"{BASE_URL}/followups/stats"),
        ("GET /api/customers", f"{BASE_URL}/customers"),
    ]
    
    try:
        # Test basic endpoints
        for name, url in endpoints:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            
            if response.status_code == 200:
                results.pass_test(f"{name} → 200 OK")
            else:
                results.fail_test(f"{name} → {response.status_code} (expected 200)")
        
        # Test PDF export (get first quotation and export it)
        print("\nPDF EXPORT TEST:")
        response = requests.get(
            f"{BASE_URL}/quotations",
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": 1},
            timeout=10
        )
        
        if response.status_code == 200:
            quotations = response.json()
            if quotations and len(quotations) > 0:
                quotation_id = quotations[0].get("id")
                
                pdf_response = requests.get(
                    f"{BASE_URL}/quotations/{quotation_id}/pdf",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15
                )
                
                if pdf_response.status_code == 200:
                    if pdf_response.content[:4] == b'%PDF':
                        results.pass_test(f"GET /api/quotations/{quotation_id}/pdf → 200 OK (valid PDF)")
                    else:
                        results.fail_test(f"PDF export returned 200 but not a valid PDF")
                else:
                    results.fail_test(f"GET /api/quotations/{quotation_id}/pdf → {pdf_response.status_code}")
            else:
                results.warn_test("No quotations available for PDF export test")
        
        # Test health/system
        print("\nHEALTH CHECK:")
        response = requests.get(f"{BASE_URL}/health/system", timeout=10)
        
        if response.status_code == 200:
            health = response.json()
            
            if health.get("healthy") == True:
                results.pass_test("GET /api/health/system → healthy=true")
            else:
                results.fail_test(f"GET /api/health/system → healthy={health.get('healthy')} (expected true)")
            
            counts = health.get("counts", {})
            product_count = counts.get("products", 0)
            
            if product_count == EXPECTED_TOTAL_PRODUCTS:
                results.pass_test(f"counts.products={product_count} (expected {EXPECTED_TOTAL_PRODUCTS})")
            else:
                results.fail_test(f"counts.products={product_count} (expected {EXPECTED_TOTAL_PRODUCTS})")
        else:
            results.fail_test(f"GET /api/health/system → {response.status_code}")
        
        results.print_summary()
        
    except Exception as e:
        results.fail_test(f"General regression test failed: {str(e)}")
        results.print_summary()

def test_other_brands_smoke(token: str, brands_map: Dict[str, Any]):
    """Test 8: Smoke-check other brands"""
    print("\n" + "="*80)
    print("TEST 8: OTHER BRANDS SMOKE CHECK")
    print("="*80)
    
    results = TestResults()
    
    brands_to_check = ["Hansgrohe", "Axor", "Geberit", "Vitra"]
    
    try:
        for brand_name in brands_to_check:
            if brand_name not in brands_map:
                results.fail_test(f"{brand_name} — NOT FOUND in brands")
                continue
            
            brand_id = brands_map[brand_name]["id"]
            
            response = requests.get(
                f"{BASE_URL}/products",
                params={"brand_id": brand_id, "limit": 3},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                products = data.get("items", [])
                
                if len(products) >= 2:
                    results.pass_test(f"{brand_name} — Retrieved {len(products)} products successfully")
                else:
                    results.warn_test(f"{brand_name} — Only {len(products)} products retrieved (expected 2-3)")
            else:
                results.fail_test(f"{brand_name} — Failed to retrieve products: {response.status_code}")
        
        results.print_summary()
        
    except Exception as e:
        results.fail_test(f"Other brands smoke check failed: {str(e)}")
        results.print_summary()

def main():
    print("="*80)
    print("GROHE CATALOG BATCH 3 (ADDITIVE) VERIFICATION TEST SUITE")
    print("="*80)
    print(f"Backend URL: {BASE_URL}")
    print(f"Test User: {EMAIL}")
    print()
    
    # Test 1: Authentication
    token = test_auth()
    if not token:
        print("\n❌ CRITICAL: Authentication failed. Cannot proceed with other tests.")
        sys.exit(1)
    
    # Test 2: Brands
    brands_map = test_brands(token)
    if not brands_map:
        print("\n❌ CRITICAL: Failed to retrieve brands. Cannot proceed with other tests.")
        sys.exit(1)
    
    grohe_id = brands_map.get("Grohe", {}).get("id")
    if not grohe_id:
        print("\n❌ CRITICAL: Grohe brand not found. Cannot proceed with Grohe-specific tests.")
        sys.exit(1)
    
    # Test 3: CRITICAL - Duplicate SKUs
    duplicate_check_passed = test_duplicate_skus(token, grohe_id)
    if not duplicate_check_passed:
        print("\n🔴 CRITICAL: DUPLICATE SKU CHECK FAILED!")
    
    # Test 4: Categories
    categories_map = test_categories(token, brands_map)
    
    # Test 5: Images
    test_images(token, categories_map, grohe_id)
    
    # Test 6: Earlier batch products
    test_earlier_batch_products(token, grohe_id)
    
    # Test 7: General regression
    test_general_regression(token)
    
    # Test 8: Other brands smoke check
    test_other_brands_smoke(token, brands_map)
    
    print("\n" + "="*80)
    print("ALL TESTS COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()
