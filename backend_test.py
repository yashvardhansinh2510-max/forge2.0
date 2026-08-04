#!/usr/bin/env python3
"""
Backend Testing Script for BuildCon House - MODULO Catalog Import Verification
Tests the 4th Ground Floor Tiles brand (Modulo) with floor-scoped catalog reads via X-Floor-Id header.
"""

import requests
import json
import sys
from typing import Dict, Any, Optional

# Backend URL from frontend/.env
BASE_URL = "https://buildcon-preview.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
TEST_EMAIL = "owner@forge.app"
TEST_PASSWORD = "Forge@2026"

# ANSI color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures = []
    
    def pass_test(self, test_name: str):
        self.passed += 1
        print(f"{GREEN}✅ PASS{RESET}: {test_name}")
    
    def fail_test(self, test_name: str, reason: str):
        self.failed += 1
        self.failures.append(f"{test_name}: {reason}")
        print(f"{RED}❌ FAIL{RESET}: {test_name}")
        print(f"   Reason: {reason}")
    
    def print_summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*80}")
        print(f"TEST SUMMARY")
        print(f"{'='*80}")
        print(f"Total Tests: {total}")
        print(f"{GREEN}Passed: {self.passed}{RESET}")
        print(f"{RED}Failed: {self.failed}{RESET}")
        
        if self.failures:
            print(f"\n{RED}FAILED TESTS:{RESET}")
            for i, failure in enumerate(self.failures, 1):
                print(f"{i}. {failure}")
        
        return self.failed == 0


def login() -> Optional[str]:
    """Login and return JWT token"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}AUTHENTICATION{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
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
            print(f"{GREEN}✅ Login successful{RESET}")
            print(f"   User: {user.get('full_name')} ({user.get('email')})")
            print(f"   Role: {user.get('role')}")
            return token
        else:
            print(f"{RED}❌ Login failed: {response.status_code}{RESET}")
            print(f"   Response: {response.text}")
            return None
    except Exception as e:
        print(f"{RED}❌ Login error: {str(e)}{RESET}")
        return None


def test_brands_ground_floor(token: str, result: TestResult):
    """Test 1: GET /api/brands with X-Floor-Id: ground-floor"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST 1: GET /api/brands (X-Floor-Id: ground-floor){RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    try:
        response = requests.get(
            f"{BASE_URL}/brands",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Floor-Id": "ground-floor"
            },
            timeout=10
        )
        
        if response.status_code != 200:
            result.fail_test("GET /api/brands (ground-floor)", f"Status {response.status_code}: {response.text}")
            return
        
        brands = response.json()
        brand_names = [b.get("name") for b in brands]
        
        print(f"   Found {len(brands)} brands: {', '.join(brand_names)}")
        
        # Must include all 4 tile brands
        required_brands = ["Modulo", "Dimore", "Nexion", "Qutone"]
        missing = [b for b in required_brands if b not in brand_names]
        
        if missing:
            result.fail_test("GET /api/brands (ground-floor)", f"Missing brands: {', '.join(missing)}")
        else:
            result.pass_test("GET /api/brands (ground-floor) - includes Modulo, Dimore, Nexion, Qutone")
        
    except Exception as e:
        result.fail_test("GET /api/brands (ground-floor)", f"Exception: {str(e)}")


def test_brands_first_floor(token: str, result: TestResult):
    """Test 2: GET /api/brands with X-Floor-Id: first-floor (floor isolation)"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST 2: GET /api/brands (X-Floor-Id: first-floor) - Floor Isolation{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    try:
        response = requests.get(
            f"{BASE_URL}/brands",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Floor-Id": "first-floor"
            },
            timeout=10
        )
        
        if response.status_code != 200:
            result.fail_test("GET /api/brands (first-floor)", f"Status {response.status_code}: {response.text}")
            return
        
        brands = response.json()
        brand_names = [b.get("name") for b in brands]
        
        print(f"   Found {len(brands)} brands: {', '.join(brand_names)}")
        
        # Must include sanitary brands
        required_sanitary = ["Vitra", "Hansgrohe", "Grohe", "Axor", "Geberit", "Oyster"]
        missing_sanitary = [b for b in required_sanitary if b not in brand_names]
        
        # Must NOT include tile brands
        tile_brands = ["Modulo", "Dimore", "Nexion", "Qutone"]
        leaked_tiles = [b for b in tile_brands if b in brand_names]
        
        if missing_sanitary:
            result.fail_test("GET /api/brands (first-floor) - sanitary brands", f"Missing: {', '.join(missing_sanitary)}")
        else:
            result.pass_test("GET /api/brands (first-floor) - includes all 6 sanitary brands")
        
        if leaked_tiles:
            result.fail_test("GET /api/brands (first-floor) - floor isolation", f"Tile brands leaked: {', '.join(leaked_tiles)}")
        else:
            result.pass_test("GET /api/brands (first-floor) - NO tile brands (floor isolation working)")
        
    except Exception as e:
        result.fail_test("GET /api/brands (first-floor)", f"Exception: {str(e)}")


def test_products_modulo_ground_floor(token: str, result: TestResult) -> Optional[str]:
    """Test 3: GET /api/products?q=modulo with X-Floor-Id: ground-floor"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST 3: GET /api/products?q=modulo (X-Floor-Id: ground-floor){RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    sample_product_id = None
    
    # First get Modulo's brand_id
    modulo_brand_id = None
    try:
        brands_response = requests.get(
            f"{BASE_URL}/brands",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Floor-Id": "ground-floor"
            },
            timeout=10
        )
        if brands_response.status_code == 200:
            brands = brands_response.json()
            for brand in brands:
                if brand.get("name") == "Modulo":
                    modulo_brand_id = brand.get("id")
                    break
    except Exception as e:
        print(f"   Warning: Could not fetch Modulo brand_id: {e}")
    
    try:
        response = requests.get(
            f"{BASE_URL}/products",
            params={"q": "modulo"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Floor-Id": "ground-floor"
            },
            timeout=10
        )
        
        if response.status_code != 200:
            result.fail_test("GET /api/products?q=modulo (ground-floor)", f"Status {response.status_code}: {response.text}")
            return None
        
        data = response.json()
        total = data.get("total", 0)
        items = data.get("items", [])
        
        print(f"   Total: {total}")
        print(f"   Items returned: {len(items)}")
        
        # Must be exactly 73 products
        if total != 73:
            result.fail_test("GET /api/products?q=modulo (ground-floor) - count", f"Expected 73, got {total}")
        else:
            result.pass_test("GET /api/products?q=modulo (ground-floor) - total=73")
        
        # Check all items are brand=Modulo (by brand_id)
        if modulo_brand_id:
            non_modulo = [p for p in items if p.get("brand_id") != modulo_brand_id]
            if non_modulo:
                result.fail_test("GET /api/products?q=modulo (ground-floor) - brand", f"{len(non_modulo)} items not Modulo brand")
            else:
                result.pass_test("GET /api/products?q=modulo (ground-floor) - all items brand=Modulo")
        else:
            print(f"   {YELLOW}⚠ Skipping brand check (could not determine Modulo brand_id){RESET}")
        
        # Check hero_image_url (Supabase URL)
        missing_images = [p for p in items if not p.get("hero_image_url") or "supabase" not in p.get("hero_image_url", "")]
        if missing_images:
            result.fail_test("GET /api/products?q=modulo (ground-floor) - images", f"{len(missing_images)} items missing valid Supabase hero_image_url")
        else:
            result.pass_test("GET /api/products?q=modulo (ground-floor) - all items have valid Supabase hero_image_url")
        
        # Check price=100
        wrong_price = [p for p in items if p.get("price") != 100]
        if wrong_price:
            result.fail_test("GET /api/products?q=modulo (ground-floor) - price", f"{len(wrong_price)} items have price != 100")
        else:
            result.pass_test("GET /api/products?q=modulo (ground-floor) - all items price=100")
        
        # Get a sample product ID for next test
        if items:
            sample_product_id = items[0].get("id")
            print(f"   Sample product ID for detail test: {sample_product_id}")
        
        return sample_product_id
        
    except Exception as e:
        result.fail_test("GET /api/products?q=modulo (ground-floor)", f"Exception: {str(e)}")
        return None


def test_products_modulo_first_floor(token: str, result: TestResult):
    """Test 4: GET /api/products?q=modulo with X-Floor-Id: first-floor (must be 0)"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST 4: GET /api/products?q=modulo (X-Floor-Id: first-floor) - Floor Isolation{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    try:
        response = requests.get(
            f"{BASE_URL}/products",
            params={"q": "modulo"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Floor-Id": "first-floor"
            },
            timeout=10
        )
        
        if response.status_code != 200:
            result.fail_test("GET /api/products?q=modulo (first-floor)", f"Status {response.status_code}: {response.text}")
            return
        
        data = response.json()
        total = data.get("total", 0)
        
        print(f"   Total: {total}")
        
        if total != 0:
            result.fail_test("GET /api/products?q=modulo (first-floor) - floor isolation", f"Expected 0, got {total} (Modulo leaked into Sanitary Bathroom)")
        else:
            result.pass_test("GET /api/products?q=modulo (first-floor) - total=0 (floor isolation working)")
        
    except Exception as e:
        result.fail_test("GET /api/products?q=modulo (first-floor)", f"Exception: {str(e)}")


def test_product_detail(token: str, product_id: str, result: TestResult):
    """Test 5: GET /api/products/{id} for one Modulo product"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST 5: GET /api/products/{product_id} (Product Detail){RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    if not product_id:
        result.fail_test("GET /api/products/{id}", "No product ID available from previous test")
        return
    
    try:
        response = requests.get(
            f"{BASE_URL}/products/{product_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Floor-Id": "ground-floor"
            },
            timeout=10
        )
        
        if response.status_code != 200:
            result.fail_test("GET /api/products/{id}", f"Status {response.status_code}: {response.text}")
            return
        
        product = response.json()
        
        # Check required fields
        required_fields = ["name", "sku", "price", "mrp", "hero_image_url"]
        missing_fields = [f for f in required_fields if f not in product or product[f] is None]
        
        if missing_fields:
            result.fail_test("GET /api/products/{id} - required fields", f"Missing: {', '.join(missing_fields)}")
        else:
            result.pass_test("GET /api/products/{id} - has name, sku, price, mrp, hero_image_url")
        
        # Check images/gallery
        if "images" not in product or not isinstance(product.get("images"), list):
            result.fail_test("GET /api/products/{id} - images", "Missing or invalid images array")
        else:
            result.pass_test("GET /api/products/{id} - has images/gallery array")
        
        # Check specs
        if "specs" not in product:
            result.fail_test("GET /api/products/{id} - specs", "Missing specs field")
        else:
            result.pass_test("GET /api/products/{id} - has specs field")
        
        print(f"   Product: {product.get('name')}")
        print(f"   SKU: {product.get('sku')}")
        print(f"   Brand: {product.get('brand_name')}")
        print(f"   Price: {product.get('price')}")
        
    except Exception as e:
        result.fail_test("GET /api/products/{id}", f"Exception: {str(e)}")


def test_catalog_search(token: str, result: TestResult):
    """Test 6: GET /api/catalog/search?q=MODULO with X-Floor-Id: ground-floor"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST 6: GET /api/catalog/search?q=MODULO (X-Floor-Id: ground-floor){RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    try:
        response = requests.get(
            f"{BASE_URL}/catalog/search",
            params={"q": "MODULO"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Floor-Id": "ground-floor"
            },
            timeout=10
        )
        
        if response.status_code != 200:
            result.fail_test("GET /api/catalog/search?q=MODULO", f"Status {response.status_code}: {response.text}")
            return
        
        data = response.json()
        
        # Check for results grouped by family_key
        # Expected structure: {query, total, grouped, items: [{family_key, variants, ...}]}
        if "items" in data and isinstance(data.get("items"), list):
            result.pass_test("GET /api/catalog/search?q=MODULO - returns grouped results, no errors")
            print(f"   Response structure: query={data.get('query')}, total={data.get('total')}, grouped={data.get('grouped')}")
            print(f"   Items (families): {len(data.get('items', []))}")
        else:
            result.fail_test("GET /api/catalog/search?q=MODULO", f"Missing or invalid 'items' field in response")
        
    except Exception as e:
        result.fail_test("GET /api/catalog/search?q=MODULO", f"Exception: {str(e)}")


def test_catalog_facets(token: str, result: TestResult):
    """Test 7: GET /api/catalog/facets with X-Floor-Id: ground-floor"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST 7: GET /api/catalog/facets (X-Floor-Id: ground-floor){RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    try:
        response = requests.get(
            f"{BASE_URL}/catalog/facets",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Floor-Id": "ground-floor"
            },
            timeout=10
        )
        
        if response.status_code != 200:
            result.fail_test("GET /api/catalog/facets", f"Status {response.status_code}: {response.text}")
            return
        
        data = response.json()
        
        # Check for reasonable facet data
        if isinstance(data, dict) and len(data) > 0:
            result.pass_test("GET /api/catalog/facets - returns facet data, no errors")
            print(f"   Facet keys: {list(data.keys())}")
        else:
            result.fail_test("GET /api/catalog/facets", f"Empty or invalid facet data: {data}")
        
    except Exception as e:
        result.fail_test("GET /api/catalog/facets", f"Exception: {str(e)}")


def test_regression_smoke(token: str, result: TestResult):
    """Test 8: Regression smoke tests on quotations, customers, payments/stats, purchase-orders"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST 8: Regression Smoke Tests{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    endpoints = [
        ("/quotations", "ground-floor"),
        ("/quotations", "first-floor"),
        ("/customers", "ground-floor"),
        ("/customers", "first-floor"),
        ("/payments/stats", "ground-floor"),
        ("/payments/stats", "first-floor"),
        ("/purchase-orders", "ground-floor"),
        ("/purchase-orders", "first-floor"),
    ]
    
    for endpoint, floor_id in endpoints:
        try:
            response = requests.get(
                f"{BASE_URL}{endpoint}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Floor-Id": floor_id
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result.pass_test(f"GET /api{endpoint} (X-Floor-Id: {floor_id}) - 200 OK")
            else:
                result.fail_test(f"GET /api{endpoint} (X-Floor-Id: {floor_id})", f"Status {response.status_code}")
        
        except Exception as e:
            result.fail_test(f"GET /api{endpoint} (X-Floor-Id: {floor_id})", f"Exception: {str(e)}")


def test_health_system(token: str, result: TestResult):
    """Test 9: GET /api/health/system"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST 9: GET /api/health/system{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    try:
        # Health endpoint is typically public, but include token just in case
        response = requests.get(
            f"{BASE_URL}/health/system",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            result.fail_test("GET /api/health/system", f"Status {response.status_code}: {response.text}")
            return
        
        data = response.json()
        
        # Check healthy=true
        if data.get("healthy") != True:
            result.fail_test("GET /api/health/system - healthy", f"healthy={data.get('healthy')}, expected True")
        else:
            result.pass_test("GET /api/health/system - healthy=true")
        
        # Check warnings=0
        warnings = data.get("warnings", [])
        if len(warnings) > 0:
            result.fail_test("GET /api/health/system - warnings", f"Found {len(warnings)} warnings: {warnings}")
        else:
            result.pass_test("GET /api/health/system - 0 warnings")
        
        # Check products count around 4363
        counts = data.get("counts", {})
        products_count = counts.get("products", 0)
        
        print(f"   Products count: {products_count}")
        
        # Allow some variance (4290-4400 range based on test_credentials.md showing 4290)
        if 4200 <= products_count <= 4500:
            result.pass_test(f"GET /api/health/system - products count in expected range ({products_count})")
        else:
            result.fail_test("GET /api/health/system - products count", f"Expected ~4363, got {products_count}")
        
        print(f"   Full counts: {counts}")
        
    except Exception as e:
        result.fail_test("GET /api/health/system", f"Exception: {str(e)}")


def main():
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}BuildCon House - MODULO Catalog Import Backend Testing{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    print(f"Backend URL: {BASE_URL}")
    print(f"Test User: {TEST_EMAIL}")
    
    result = TestResult()
    
    # Step 1: Login
    token = login()
    if not token:
        print(f"\n{RED}FATAL: Cannot proceed without authentication token{RESET}")
        sys.exit(1)
    
    # Step 2: Run all tests
    test_brands_ground_floor(token, result)
    test_brands_first_floor(token, result)
    sample_product_id = test_products_modulo_ground_floor(token, result)
    test_products_modulo_first_floor(token, result)
    test_product_detail(token, sample_product_id, result)
    test_catalog_search(token, result)
    test_catalog_facets(token, result)
    test_regression_smoke(token, result)
    test_health_system(token, result)
    
    # Step 3: Print summary
    success = result.print_summary()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
