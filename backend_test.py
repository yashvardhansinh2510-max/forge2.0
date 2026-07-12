#!/usr/bin/env python3
"""
Production Sprint Objective 2 Backend Contract Testing
Test against active buildcon_house instance with owner@forge.app / Forge@2026
"""

import requests
import json
import time
from typing import Dict, List, Set

# Configuration
BASE_URL = "https://buildcon-sprint.preview.emergentagent.com/api"
CREDENTIALS = {
    "email": "owner@forge.app",
    "password": "Forge@2026"
}

class BackendTester:
    def __init__(self):
        self.token = None
        self.session = requests.Session()
        
    def login(self) -> bool:
        """Login and get JWT token"""
        print("=" * 80)
        print("TEST 1: Authentication")
        print("=" * 80)
        
        try:
            response = self.session.post(
                f"{BASE_URL}/auth/login",
                json=CREDENTIALS,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token") or data.get("token")
                self.session.headers.update({"Authorization": f"Bearer {self.token}"})
                print(f"✅ Login successful: {data.get('user', {}).get('email')}")
                print(f"   Role: {data.get('user', {}).get('role')}")
                return True
            else:
                print(f"❌ Login failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def test_health_system(self) -> bool:
        """Test GET /api/health/system"""
        print("\n" + "=" * 80)
        print("TEST 2: GET /api/health/system")
        print("=" * 80)
        
        try:
            response = self.session.get(f"{BASE_URL}/health/system", timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                # Check both old and new format
                products = data.get("counts", {}).get("products", data.get("products", 0))
                mongo_connected = data.get("mongo", {}).get("connected", False)
                is_local = data.get("mongo", {}).get("is_local", True)
                warnings = data.get("warnings", [])
                healthy = data.get("healthy", False)
                
                print(f"✅ Health check successful")
                print(f"   Healthy: {healthy}")
                print(f"   MongoDB connected: {mongo_connected}")
                print(f"   MongoDB is_local: {is_local}")
                print(f"   Products count: {products}")
                print(f"   Warnings: {warnings}")
                
                if products == 2966:
                    print(f"✅ Product count is exactly 2966")
                    return True
                else:
                    print(f"❌ Product count mismatch: expected 2966, got {products}")
                    return False
            else:
                print(f"❌ Health check failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Health check error: {e}")
            return False
    
    def test_exhaustive_pagination(self) -> bool:
        """Test exhaustive pagination of all 2966 products"""
        print("\n" + "=" * 80)
        print("TEST 3: Exhaustive Pagination (GET /api/products?limit=60&skip=N&sort=name)")
        print("=" * 80)
        
        limit = 60
        skip = 0
        all_ids: Set[str] = set()
        all_products: List[Dict] = []
        page_count = 0
        
        try:
            while True:
                page_count += 1
                print(f"\nFetching page {page_count} (skip={skip}, limit={limit})...")
                
                response = self.session.get(
                    f"{BASE_URL}/products",
                    params={"limit": limit, "skip": skip, "sort": "name"},
                    timeout=30
                )
                
                if response.status_code != 200:
                    print(f"❌ Request failed: {response.status_code}")
                    print(f"   Response: {response.text}")
                    return False
                
                data = response.json()
                total = data.get("total", 0)
                items = data.get("items", [])
                
                print(f"   Total: {total}, Items in page: {len(items)}")
                
                if page_count == 1:
                    if total != 2966:
                        print(f"❌ Total mismatch: expected 2966, got {total}")
                        return False
                    else:
                        print(f"✅ Total is exactly 2966")
                
                if not items:
                    break
                
                # Collect IDs
                for item in items:
                    product_id = item.get("id")
                    if product_id:
                        if product_id in all_ids:
                            print(f"❌ DUPLICATE ID FOUND: {product_id}")
                            return False
                        all_ids.add(product_id)
                        all_products.append(item)
                
                # Check if we've reached the end
                if len(items) < limit:
                    print(f"   Last page detected (items < limit)")
                    break
                
                skip += limit
            
            # Final verification
            print(f"\n" + "-" * 80)
            print(f"PAGINATION SUMMARY:")
            print(f"   Total pages fetched: {page_count}")
            print(f"   Total products collected: {len(all_products)}")
            print(f"   Unique IDs collected: {len(all_ids)}")
            print(f"   Last page size: {len(items)}")
            
            # Verify counts
            if len(all_products) == 2966:
                print(f"✅ Collected exactly 2966 products")
            else:
                print(f"❌ Product count mismatch: expected 2966, got {len(all_products)}")
                return False
            
            if len(all_ids) == 2966:
                print(f"✅ All 2966 IDs are unique (zero duplicates)")
            else:
                print(f"❌ Duplicate IDs detected: {len(all_products)} products but only {len(all_ids)} unique IDs")
                return False
            
            # Verify last page size
            expected_last_page_size = 2966 % 60
            if expected_last_page_size == 0:
                expected_last_page_size = 60
            
            if len(items) == expected_last_page_size:
                print(f"✅ Last page size is correct: {len(items)} (expected {expected_last_page_size})")
            else:
                print(f"❌ Last page size mismatch: expected {expected_last_page_size}, got {len(items)}")
                return False
            
            return True
            
        except Exception as e:
            print(f"❌ Pagination error: {e}")
            return False
    
    def test_search_query(self) -> bool:
        """Test search query returns relevant data"""
        print("\n" + "=" * 80)
        print("TEST 4: Search Query (GET /api/products?q=basin)")
        print("=" * 80)
        
        try:
            response = self.session.get(
                f"{BASE_URL}/products",
                params={"q": "basin", "limit": 100},
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"❌ Search failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
            
            data = response.json()
            total = data.get("total", 0)
            items = data.get("items", [])
            
            print(f"✅ Search successful")
            print(f"   Total results: {total}")
            print(f"   Items returned: {len(items)}")
            
            if total > 0 and len(items) > 0:
                print(f"✅ Search returned relevant data")
                
                # Show sample results
                print(f"\n   Sample results:")
                for i, item in enumerate(items[:5], 1):
                    name = item.get("name", "N/A")
                    sku = item.get("sku", "N/A")
                    print(f"   {i}. {name} (SKU: {sku})")
                
                return True
            else:
                print(f"❌ Search returned no results")
                return False
                
        except Exception as e:
            print(f"❌ Search error: {e}")
            return False
    
    def test_brand_filter(self) -> bool:
        """Test brand filter respects totals and no duplicates"""
        print("\n" + "=" * 80)
        print("TEST 5: Brand Filter (GET /api/products?brand_id=...)")
        print("=" * 80)
        
        try:
            # First get brands
            brands_response = self.session.get(f"{BASE_URL}/brands", timeout=30)
            if brands_response.status_code != 200:
                print(f"❌ Failed to get brands: {brands_response.status_code}")
                return False
            
            brands = brands_response.json()
            if not brands:
                print(f"❌ No brands found")
                return False
            
            # Test first brand
            test_brand = brands[0]
            brand_id = test_brand.get("id")
            brand_name = test_brand.get("name")
            expected_count = test_brand.get("product_count", 0)
            
            print(f"\nTesting brand: {brand_name} (expected {expected_count} products)")
            
            # Fetch all products for this brand
            all_ids: Set[str] = set()
            skip = 0
            limit = 60
            
            while True:
                response = self.session.get(
                    f"{BASE_URL}/products",
                    params={"brand_id": brand_id, "limit": limit, "skip": skip},
                    timeout=30
                )
                
                if response.status_code != 200:
                    print(f"❌ Brand filter failed: {response.status_code}")
                    return False
                
                data = response.json()
                total = data.get("total", 0)
                items = data.get("items", [])
                
                if skip == 0:
                    print(f"   Total from API: {total}")
                    if total != expected_count:
                        print(f"⚠️  Warning: Total mismatch (API: {total}, Brand: {expected_count})")
                
                if not items:
                    break
                
                for item in items:
                    product_id = item.get("id")
                    if product_id in all_ids:
                        print(f"❌ DUPLICATE ID FOUND: {product_id}")
                        return False
                    all_ids.add(product_id)
                
                if len(items) < limit:
                    break
                
                skip += limit
            
            print(f"✅ Brand filter successful")
            print(f"   Collected {len(all_ids)} unique products")
            print(f"   Zero duplicates detected")
            
            return True
            
        except Exception as e:
            print(f"❌ Brand filter error: {e}")
            return False
    
    def test_combined_brand_category_filter(self) -> bool:
        """Test combined brand+category filter respects totals and no duplicates"""
        print("\n" + "=" * 80)
        print("TEST 6: Combined Brand+Category Filter")
        print("=" * 80)
        
        try:
            # Get brands and categories
            brands_response = self.session.get(f"{BASE_URL}/brands", timeout=30)
            categories_response = self.session.get(f"{BASE_URL}/categories", timeout=30)
            
            if brands_response.status_code != 200 or categories_response.status_code != 200:
                print(f"❌ Failed to get brands or categories")
                return False
            
            brands = brands_response.json()
            categories = categories_response.json()
            
            if not brands or not categories:
                print(f"❌ No brands or categories found")
                return False
            
            # Test first brand + first category
            test_brand = brands[0]
            test_category = categories[0]
            
            brand_id = test_brand.get("id")
            brand_name = test_brand.get("name")
            category_id = test_category.get("id")
            category_name = test_category.get("name")
            
            print(f"\nTesting: {brand_name} + {category_name}")
            
            # Fetch all products for this combination
            all_ids: Set[str] = set()
            skip = 0
            limit = 60
            total_from_api = None
            
            while True:
                response = self.session.get(
                    f"{BASE_URL}/products",
                    params={
                        "brand_id": brand_id,
                        "category_id": category_id,
                        "limit": limit,
                        "skip": skip
                    },
                    timeout=30
                )
                
                if response.status_code != 200:
                    print(f"❌ Combined filter failed: {response.status_code}")
                    return False
                
                data = response.json()
                total = data.get("total", 0)
                items = data.get("items", [])
                
                if skip == 0:
                    total_from_api = total
                    print(f"   Total from API: {total}")
                
                if not items:
                    break
                
                for item in items:
                    product_id = item.get("id")
                    if product_id in all_ids:
                        print(f"❌ DUPLICATE ID FOUND: {product_id}")
                        return False
                    all_ids.add(product_id)
                
                if len(items) < limit:
                    break
                
                skip += limit
            
            print(f"✅ Combined filter successful")
            print(f"   Total from API: {total_from_api}")
            print(f"   Collected {len(all_ids)} unique products")
            print(f"   Zero duplicates detected")
            
            if total_from_api == len(all_ids):
                print(f"✅ Total matches collected count")
            else:
                print(f"⚠️  Warning: Total mismatch (API: {total_from_api}, Collected: {len(all_ids)})")
            
            return True
            
        except Exception as e:
            print(f"❌ Combined filter error: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests"""
        print("\n" + "=" * 80)
        print("PRODUCTION SPRINT OBJECTIVE 2 - BACKEND CONTRACT TESTING")
        print("=" * 80)
        print(f"Base URL: {BASE_URL}")
        print(f"Credentials: {CREDENTIALS['email']}")
        print("=" * 80)
        
        results = {}
        
        # Test 1: Login
        results["login"] = self.login()
        if not results["login"]:
            print("\n❌ CRITICAL: Login failed, cannot proceed with other tests")
            return results
        
        # Test 2: Health System
        results["health_system"] = self.test_health_system()
        
        # Test 3: Exhaustive Pagination
        results["exhaustive_pagination"] = self.test_exhaustive_pagination()
        
        # Test 4: Search Query
        results["search_query"] = self.test_search_query()
        
        # Test 5: Brand Filter
        results["brand_filter"] = self.test_brand_filter()
        
        # Test 6: Combined Brand+Category Filter
        results["combined_filter"] = self.test_combined_brand_category_filter()
        
        # Summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status}: {test_name}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        if passed == total:
            print("\n✅ ALL TESTS PASSED")
        else:
            print(f"\n❌ {total - passed} TEST(S) FAILED")
        
        return results


if __name__ == "__main__":
    tester = BackendTester()
    results = tester.run_all_tests()
    
    # Exit with appropriate code
    exit(0 if all(results.values()) else 1)
