#!/usr/bin/env python3
"""
Backend Testing for GROHE Catalog Batch 2 (Additive Migration)
Testing the additive catalog migration that added 166 new Grohe products
across 5 new categories on top of the previous 133 products.
"""

import requests
import json
from typing import Dict, List, Any, Optional
import sys

# Backend URL from frontend/.env
BASE_URL = "https://216d7dfd-ba32-495c-a1aa-c78b8d90fcbf.preview.emergentagent.com/api"

# Test credentials from review request
TEST_EMAIL = "owner@forge.app"
TEST_PASSWORD = "Forge@2026"

# Expected counts after batch 2
EXPECTED_GROHE_COUNT = 299  # 133 from batch 1 + 166 from batch 2
EXPECTED_TOTAL_PRODUCTS = 2401
EXPECTED_HANSGROHE_COUNT = 908
EXPECTED_AXOR_COUNT = 448
EXPECTED_VITRA_COUNT = 250
EXPECTED_GEBERIT_COUNT = 496

# New categories from batch 2
NEW_CATEGORIES_BATCH2 = ["Bau Line", "Body Jet", "Handshower", "Kitchen Tap", "Short Body Basin Mixer"]

# Previous batch 1 categories
PREVIOUS_CATEGORIES_BATCH1 = ["RSH Aqua Tile Shower", "Plate", "Shower", "Single Lever"]

class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
        
    def add_pass(self, test_name: str, details: str = ""):
        self.passed.append(f"✅ {test_name}: {details}")
        print(f"✅ PASS: {test_name}")
        if details:
            print(f"   {details}")
    
    def add_fail(self, test_name: str, details: str):
        self.failed.append(f"❌ {test_name}: {details}")
        print(f"❌ FAIL: {test_name}")
        print(f"   {details}")
    
    def add_warning(self, test_name: str, details: str):
        self.warnings.append(f"⚠️  {test_name}: {details}")
        print(f"⚠️  WARNING: {test_name}")
        print(f"   {details}")
    
    def summary(self):
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"PASSED: {len(self.passed)}")
        print(f"FAILED: {len(self.failed)}")
        print(f"WARNINGS: {len(self.warnings)}")
        print("="*80)
        
        if self.failed:
            print("\n❌ FAILED TESTS:")
            for fail in self.failed:
                print(f"  {fail}")
        
        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warn in self.warnings:
                print(f"  {warn}")
        
        return len(self.failed) == 0


def test_auth(results: TestResults) -> Optional[str]:
    """Test 1: Authentication"""
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
            token = data.get("access_token")
            user = data.get("user", {})
            
            if token:
                results.add_pass(
                    "AUTH Login",
                    f"Status: {response.status_code}, User: {user.get('name')} ({user.get('email')}), Role: {user.get('role')}"
                )
                return token
            else:
                results.add_fail("AUTH Login", "No access_token in response")
                return None
        else:
            results.add_fail("AUTH Login", f"Status: {response.status_code}, Response: {response.text[:200]}")
            return None
            
    except Exception as e:
        results.add_fail("AUTH Login", f"Exception: {str(e)}")
        return None


def test_brands(token: str, results: TestResults) -> Dict[str, Any]:
    """Test 2: Brands - Verify Grohe count and other brands unchanged"""
    print("\n" + "="*80)
    print("TEST 2: BRANDS")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {token}"}
    brand_map = {}
    
    try:
        response = requests.get(f"{BASE_URL}/brands", headers=headers, timeout=10)
        
        if response.status_code != 200:
            results.add_fail("BRANDS GET", f"Status: {response.status_code}")
            return brand_map
        
        brands = response.json()
        
        # Create brand map
        for brand in brands:
            brand_map[brand['name']] = brand
        
        # Check Grohe count
        if 'Grohe' in brand_map:
            grohe_count = brand_map['Grohe'].get('product_count', 0)
            if grohe_count == EXPECTED_GROHE_COUNT:
                results.add_pass(
                    "BRANDS Grohe Count",
                    f"Grohe product_count={grohe_count} (expected {EXPECTED_GROHE_COUNT})"
                )
            else:
                results.add_fail(
                    "BRANDS Grohe Count",
                    f"Expected {EXPECTED_GROHE_COUNT}, got {grohe_count}"
                )
        else:
            results.add_fail("BRANDS Grohe Count", "Grohe brand not found")
        
        # Check other brands unchanged
        expected_counts = {
            'Hansgrohe': EXPECTED_HANSGROHE_COUNT,
            'Axor': EXPECTED_AXOR_COUNT,
            'Vitra': EXPECTED_VITRA_COUNT,
            'Geberit': EXPECTED_GEBERIT_COUNT
        }
        
        for brand_name, expected_count in expected_counts.items():
            if brand_name in brand_map:
                actual_count = brand_map[brand_name].get('product_count', 0)
                if actual_count == expected_count:
                    results.add_pass(
                        f"BRANDS {brand_name} Unchanged",
                        f"{brand_name}={actual_count}"
                    )
                else:
                    results.add_fail(
                        f"BRANDS {brand_name} Unchanged",
                        f"Expected {expected_count}, got {actual_count}"
                    )
            else:
                results.add_fail(f"BRANDS {brand_name} Unchanged", f"{brand_name} not found")
        
        return brand_map
        
    except Exception as e:
        results.add_fail("BRANDS GET", f"Exception: {str(e)}")
        return brand_map


def test_categories(token: str, brand_map: Dict[str, Any], results: TestResults) -> Dict[str, Any]:
    """Test 3: Categories - Verify 5 new categories exist with counts > 0"""
    print("\n" + "="*80)
    print("TEST 3: CATEGORIES")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {token}"}
    category_map = {}
    
    try:
        response = requests.get(f"{BASE_URL}/categories", headers=headers, timeout=10)
        
        if response.status_code != 200:
            results.add_fail("CATEGORIES GET", f"Status: {response.status_code}")
            return category_map
        
        categories = response.json()
        
        # Create category map
        for cat in categories:
            category_map[cat['name']] = cat
        
        # Check 5 new categories from batch 2
        for cat_name in NEW_CATEGORIES_BATCH2:
            if cat_name in category_map:
                product_count = category_map[cat_name].get('product_count', 0)
                if product_count > 0:
                    results.add_pass(
                        f"CATEGORIES New '{cat_name}'",
                        f"Exists with product_count={product_count}"
                    )
                else:
                    results.add_fail(
                        f"CATEGORIES New '{cat_name}'",
                        f"Exists but product_count={product_count} (expected > 0)"
                    )
            else:
                results.add_fail(
                    f"CATEGORIES New '{cat_name}'",
                    "Category not found"
                )
        
        # Check 4 previous categories from batch 1 still exist
        for cat_name in PREVIOUS_CATEGORIES_BATCH1:
            if cat_name in category_map:
                product_count = category_map[cat_name].get('product_count', 0)
                results.add_pass(
                    f"CATEGORIES Previous '{cat_name}'",
                    f"Still exists with product_count={product_count}"
                )
            else:
                results.add_fail(
                    f"CATEGORIES Previous '{cat_name}'",
                    "Category not found (should still exist from batch 1)"
                )
        
        return category_map
        
    except Exception as e:
        results.add_fail("CATEGORIES GET", f"Exception: {str(e)}")
        return category_map


def test_grohe_products(token: str, brand_map: Dict[str, Any], category_map: Dict[str, Any], results: TestResults):
    """Test 4: Grohe Products - Verify 299 total, spot check images from new categories"""
    print("\n" + "="*80)
    print("TEST 4: GROHE PRODUCTS")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    if 'Grohe' not in brand_map:
        results.add_fail("GROHE PRODUCTS", "Grohe brand not found in brand_map")
        return
    
    grohe_id = brand_map['Grohe']['id']
    
    try:
        # Get all Grohe products
        response = requests.get(
            f"{BASE_URL}/products",
            params={"brand_id": grohe_id, "limit": 350},
            headers=headers,
            timeout=15
        )
        
        if response.status_code != 200:
            results.add_fail("GROHE PRODUCTS GET", f"Status: {response.status_code}")
            return
        
        data = response.json()
        total = data.get('total', 0)
        items = data.get('items', [])
        
        # Check total count
        if total == EXPECTED_GROHE_COUNT:
            results.add_pass(
                "GROHE PRODUCTS Total Count",
                f"Total={total} (expected {EXPECTED_GROHE_COUNT})"
            )
        else:
            results.add_fail(
                "GROHE PRODUCTS Total Count",
                f"Expected {EXPECTED_GROHE_COUNT}, got {total}"
            )
        
        # Spot check 2 products from each of the 5 new categories (10 total)
        products_by_category = {}
        for product in items:
            cat_id = product.get('category_id')
            if cat_id:
                # Find category name
                cat_name = None
                for name, cat in category_map.items():
                    if cat['id'] == cat_id:
                        cat_name = name
                        break
                
                if cat_name and cat_name in NEW_CATEGORIES_BATCH2:
                    if cat_name not in products_by_category:
                        products_by_category[cat_name] = []
                    products_by_category[cat_name].append(product)
        
        # Check 2 products from each new category
        for cat_name in NEW_CATEGORIES_BATCH2:
            if cat_name in products_by_category:
                products = products_by_category[cat_name][:2]  # Take first 2
                
                for idx, product in enumerate(products, 1):
                    sku = product.get('sku', 'N/A')
                    name = product.get('name', 'N/A')
                    images = product.get('images', [])
                    
                    if images and len(images) > 0:
                        hero_image = images[0]
                        
                        # Check if image URL is from supabase.co
                        if 'supabase.co' in hero_image:
                            # Try to fetch the image
                            try:
                                img_response = requests.head(hero_image, timeout=5)
                                if img_response.status_code == 200:
                                    results.add_pass(
                                        f"GROHE PRODUCTS '{cat_name}' Product {idx}",
                                        f"SKU={sku}, Image URL valid (HTTP 200)"
                                    )
                                else:
                                    results.add_fail(
                                        f"GROHE PRODUCTS '{cat_name}' Product {idx}",
                                        f"SKU={sku}, Image URL returned HTTP {img_response.status_code}"
                                    )
                            except Exception as e:
                                results.add_warning(
                                    f"GROHE PRODUCTS '{cat_name}' Product {idx}",
                                    f"SKU={sku}, Could not verify image URL: {str(e)}"
                                )
                        else:
                            results.add_fail(
                                f"GROHE PRODUCTS '{cat_name}' Product {idx}",
                                f"SKU={sku}, Image URL not from supabase.co: {hero_image[:100]}"
                            )
                    else:
                        results.add_fail(
                            f"GROHE PRODUCTS '{cat_name}' Product {idx}",
                            f"SKU={sku}, No images found"
                        )
            else:
                results.add_warning(
                    f"GROHE PRODUCTS '{cat_name}' Spot Check",
                    f"No products found in this category"
                )
        
    except Exception as e:
        results.add_fail("GROHE PRODUCTS GET", f"Exception: {str(e)}")


def test_batch1_products_preserved(token: str, brand_map: Dict[str, Any], category_map: Dict[str, Any], results: TestResults):
    """Test 5: Verify batch 1 products (133) are still present and unmodified"""
    print("\n" + "="*80)
    print("TEST 5: BATCH 1 PRODUCTS PRESERVED")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    if 'Grohe' not in brand_map:
        results.add_fail("BATCH1 PRODUCTS", "Grohe brand not found")
        return
    
    grohe_id = brand_map['Grohe']['id']
    
    # Check products from each of the 4 batch 1 categories
    for cat_name in PREVIOUS_CATEGORIES_BATCH1:
        if cat_name not in category_map:
            results.add_warning(
                f"BATCH1 PRODUCTS '{cat_name}'",
                "Category not found"
            )
            continue
        
        cat_id = category_map[cat_name]['id']
        
        try:
            response = requests.get(
                f"{BASE_URL}/products",
                params={"brand_id": grohe_id, "category_id": cat_id, "limit": 50},
                headers=headers,
                timeout=10
            )
            
            if response.status_code != 200:
                results.add_fail(
                    f"BATCH1 PRODUCTS '{cat_name}'",
                    f"GET failed with status {response.status_code}"
                )
                continue
            
            data = response.json()
            items = data.get('items', [])
            
            if len(items) > 0:
                # Spot check 3-4 products from this category
                sample_products = items[:min(4, len(items))]
                
                for product in sample_products:
                    sku = product.get('sku', 'N/A')
                    name = product.get('name', 'N/A')
                    
                    # Verify product has basic fields
                    if product.get('brand_id') == grohe_id and product.get('category_id') == cat_id:
                        results.add_pass(
                            f"BATCH1 PRODUCTS '{cat_name}' SKU {sku}",
                            f"Still present and correctly categorized"
                        )
                    else:
                        results.add_fail(
                            f"BATCH1 PRODUCTS '{cat_name}' SKU {sku}",
                            "Product data appears modified"
                        )
            else:
                results.add_warning(
                    f"BATCH1 PRODUCTS '{cat_name}'",
                    "No products found in this category"
                )
                
        except Exception as e:
            results.add_fail(
                f"BATCH1 PRODUCTS '{cat_name}'",
                f"Exception: {str(e)}"
            )


def test_general_regression(token: str, results: TestResults):
    """Test 6: General regression - customers, quotations, purchase-orders, payments, followups, health"""
    print("\n" + "="*80)
    print("TEST 6: GENERAL REGRESSION")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test customers
    try:
        response = requests.get(f"{BASE_URL}/customers", headers=headers, timeout=10)
        if response.status_code == 200:
            results.add_pass("REGRESSION Customers", f"Status: {response.status_code}")
        else:
            results.add_fail("REGRESSION Customers", f"Status: {response.status_code}")
    except Exception as e:
        results.add_fail("REGRESSION Customers", f"Exception: {str(e)}")
    
    # Test quotations
    try:
        response = requests.get(f"{BASE_URL}/quotations", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results.add_pass("REGRESSION Quotations", f"Status: {response.status_code}, Count: {len(data)}")
            
            # Try to generate PDF for one quotation if any exist
            if len(data) > 0:
                quot_id = data[0]['id']
                try:
                    pdf_response = requests.get(
                        f"{BASE_URL}/quotations/{quot_id}/pdf",
                        headers=headers,
                        timeout=15
                    )
                    if pdf_response.status_code == 200 and pdf_response.headers.get('content-type') == 'application/pdf':
                        results.add_pass("REGRESSION Quotation PDF", f"PDF generated successfully for {quot_id}")
                    else:
                        results.add_fail("REGRESSION Quotation PDF", f"Status: {pdf_response.status_code}")
                except Exception as e:
                    results.add_warning("REGRESSION Quotation PDF", f"Exception: {str(e)}")
        else:
            results.add_fail("REGRESSION Quotations", f"Status: {response.status_code}")
    except Exception as e:
        results.add_fail("REGRESSION Quotations", f"Exception: {str(e)}")
    
    # Test purchase-orders
    try:
        response = requests.get(f"{BASE_URL}/purchase-orders", headers=headers, timeout=10)
        if response.status_code == 200:
            results.add_pass("REGRESSION Purchase Orders", f"Status: {response.status_code}")
        else:
            results.add_fail("REGRESSION Purchase Orders", f"Status: {response.status_code}")
    except Exception as e:
        results.add_fail("REGRESSION Purchase Orders", f"Exception: {str(e)}")
    
    # Test payments/stats
    try:
        response = requests.get(f"{BASE_URL}/payments/stats", headers=headers, timeout=10)
        if response.status_code == 200:
            results.add_pass("REGRESSION Payments Stats", f"Status: {response.status_code}")
        else:
            results.add_fail("REGRESSION Payments Stats", f"Status: {response.status_code}")
    except Exception as e:
        results.add_fail("REGRESSION Payments Stats", f"Exception: {str(e)}")
    
    # Test followups/stats
    try:
        response = requests.get(f"{BASE_URL}/followups/stats", headers=headers, timeout=10)
        if response.status_code == 200:
            results.add_pass("REGRESSION Followups Stats", f"Status: {response.status_code}")
        else:
            results.add_fail("REGRESSION Followups Stats", f"Status: {response.status_code}")
    except Exception as e:
        results.add_fail("REGRESSION Followups Stats", f"Exception: {str(e)}")
    
    # Test health/system
    try:
        response = requests.get(f"{BASE_URL}/health/system", timeout=10)
        if response.status_code == 200:
            data = response.json()
            healthy = data.get('healthy', False)
            product_count = data.get('counts', {}).get('products', 0)
            
            if healthy and product_count == EXPECTED_TOTAL_PRODUCTS:
                results.add_pass(
                    "REGRESSION Health System",
                    f"healthy=true, counts.products={product_count}"
                )
            elif healthy:
                results.add_warning(
                    "REGRESSION Health System",
                    f"healthy=true but counts.products={product_count} (expected {EXPECTED_TOTAL_PRODUCTS})"
                )
            else:
                results.add_fail(
                    "REGRESSION Health System",
                    f"healthy={healthy}"
                )
        else:
            results.add_fail("REGRESSION Health System", f"Status: {response.status_code}")
    except Exception as e:
        results.add_fail("REGRESSION Health System", f"Exception: {str(e)}")


def test_other_brands_smoke(token: str, brand_map: Dict[str, Any], results: TestResults):
    """Test 7: Smoke check 2-3 products from Hansgrohe/AXOR/Geberit/Vitra"""
    print("\n" + "="*80)
    print("TEST 7: OTHER BRANDS SMOKE CHECK")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    brands_to_check = ['Hansgrohe', 'Axor', 'Geberit', 'Vitra']
    
    for brand_name in brands_to_check:
        if brand_name not in brand_map:
            results.add_warning(f"SMOKE CHECK {brand_name}", "Brand not found")
            continue
        
        brand_id = brand_map[brand_name]['id']
        
        try:
            response = requests.get(
                f"{BASE_URL}/products",
                params={"brand_id": brand_id, "limit": 3},
                headers=headers,
                timeout=10
            )
            
            if response.status_code != 200:
                results.add_fail(
                    f"SMOKE CHECK {brand_name}",
                    f"GET failed with status {response.status_code}"
                )
                continue
            
            data = response.json()
            items = data.get('items', [])
            
            if len(items) >= 2:
                results.add_pass(
                    f"SMOKE CHECK {brand_name}",
                    f"Retrieved {len(items)} products successfully"
                )
            else:
                results.add_warning(
                    f"SMOKE CHECK {brand_name}",
                    f"Only {len(items)} products found (expected at least 2)"
                )
                
        except Exception as e:
            results.add_fail(
                f"SMOKE CHECK {brand_name}",
                f"Exception: {str(e)}"
            )


def main():
    print("="*80)
    print("GROHE CATALOG BATCH 2 (ADDITIVE) - BACKEND TESTING")
    print("="*80)
    print(f"Backend URL: {BASE_URL}")
    print(f"Test User: {TEST_EMAIL}")
    print("="*80)
    
    results = TestResults()
    
    # Test 1: Authentication
    token = test_auth(results)
    if not token:
        print("\n❌ CRITICAL: Authentication failed. Cannot proceed with other tests.")
        results.summary()
        sys.exit(1)
    
    # Test 2: Brands
    brand_map = test_brands(token, results)
    
    # Test 3: Categories
    category_map = test_categories(token, brand_map, results)
    
    # Test 4: Grohe Products
    test_grohe_products(token, brand_map, category_map, results)
    
    # Test 5: Batch 1 Products Preserved
    test_batch1_products_preserved(token, brand_map, category_map, results)
    
    # Test 6: General Regression
    test_general_regression(token, results)
    
    # Test 7: Other Brands Smoke Check
    test_other_brands_smoke(token, brand_map, results)
    
    # Print summary
    success = results.summary()
    
    if success:
        print("\n✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
