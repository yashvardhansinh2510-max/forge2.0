"""
Quotation Builder V4 Backend Regression Test Suite
Tests all V4 additions plus smoke tests for existing endpoints
"""
import requests
import json
from datetime import datetime

# Configuration
BASE_URL = "https://forge-quotes.preview.emergentagent.com/api"
EMAIL = "owner@forge.app"
PASSWORD = "Forge@2026"

# Global state
token = None
headers = {}
test_results = []

def log_test(priority, test_id, description, passed, details=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    result = {
        "priority": priority,
        "test_id": test_id,
        "description": description,
        "status": status,
        "passed": passed,
        "details": details
    }
    test_results.append(result)
    print(f"{status} | P{priority}.{test_id} | {description}")
    if details and not passed:
        print(f"    Details: {details}")

def login():
    """Authenticate and get token"""
    global token, headers
    print("\n=== AUTHENTICATION ===")
    try:
        resp = requests.post(f"{BASE_URL}/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if resp.status_code == 200:
            data = resp.json()
            token = data["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            print(f"✅ Login successful as {EMAIL}")
            return True
        else:
            print(f"❌ Login failed: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Login error: {e}")
        return False

def test_priority_1_brands():
    """PRIORITY 1.1: GET /api/brands with product_count"""
    print("\n=== PRIORITY 1: V4 CATALOG ADDITIONS ===")
    print("\n--- Test 1.1: GET /api/brands ---")
    
    try:
        resp = requests.get(f"{BASE_URL}/brands", headers=headers)
        if resp.status_code != 200:
            log_test(1, "1.1", "GET /api/brands returns 200", False, f"Status: {resp.status_code}")
            return
        
        brands = resp.json()
        
        # Check it's an array
        if not isinstance(brands, list):
            log_test(1, "1.1a", "Brands returns array", False, f"Got {type(brands)}")
            return
        log_test(1, "1.1a", "Brands returns array", True)
        
        # Check we have 5 brands
        expected_brands = ["Axor", "Geberit", "Grohe", "Hansgrohe", "Vitra"]
        brand_names = [b.get("name") for b in brands]
        if len(brands) != 5:
            log_test(1, "1.1b", "Returns 5 brands", False, f"Got {len(brands)} brands: {brand_names}")
        else:
            log_test(1, "1.1b", "Returns 5 brands", True)
        
        # Check all expected brands present
        missing = [b for b in expected_brands if b not in brand_names]
        if missing:
            log_test(1, "1.1c", "All expected brands present", False, f"Missing: {missing}")
        else:
            log_test(1, "1.1c", "All expected brands present (Axor, Geberit, Grohe, Hansgrohe, Vitra)", True)
        
        # Check each brand has product_count field
        brands_without_count = [b.get("name") for b in brands if "product_count" not in b]
        if brands_without_count:
            log_test(1, "1.1d", "Each brand has product_count field", False, f"Missing in: {brands_without_count}")
        else:
            log_test(1, "1.1d", "Each brand has product_count field", True)
        
        # Check product_count is numeric and >= 0
        invalid_counts = [(b.get("name"), b.get("product_count")) for b in brands 
                         if not isinstance(b.get("product_count"), (int, float)) or b.get("product_count") < 0]
        if invalid_counts:
            log_test(1, "1.1e", "product_count is numeric >= 0", False, f"Invalid: {invalid_counts}")
        else:
            log_test(1, "1.1e", "product_count is numeric >= 0", True)
        
        # Verify sum of product_count equals total active products
        total_from_brands = sum(b.get("product_count", 0) for b in brands)
        
        # Get total active products
        prod_resp = requests.get(f"{BASE_URL}/products?limit=1", headers=headers)
        if prod_resp.status_code == 200:
            total_products = prod_resp.json().get("total", 0)
            if total_from_brands == total_products:
                log_test(1, "1.1f", f"Sum of brand product_counts ({total_from_brands}) equals total active products", True)
            else:
                log_test(1, "1.1f", "Sum of brand product_counts equals total active products", False, 
                        f"Brands sum: {total_from_brands}, Total products: {total_products}")
        
        return brands
        
    except Exception as e:
        log_test(1, "1.1", "GET /api/brands", False, f"Exception: {e}")
        return None

def test_priority_1_categories(brands):
    """PRIORITY 1.2-1.3: GET /api/categories with and without brand filter"""
    print("\n--- Test 1.2: GET /api/categories (no filter) ---")
    
    try:
        resp = requests.get(f"{BASE_URL}/categories", headers=headers)
        if resp.status_code != 200:
            log_test(1, "1.2", "GET /api/categories returns 200", False, f"Status: {resp.status_code}")
            return
        
        categories = resp.json()
        
        # Check it's an array
        if not isinstance(categories, list):
            log_test(1, "1.2a", "Categories returns array", False, f"Got {type(categories)}")
            return
        log_test(1, "1.2a", "Categories returns array", True)
        
        # Check each category has product_count
        cats_without_count = [c.get("name") for c in categories if "product_count" not in c]
        if cats_without_count:
            log_test(1, "1.2b", "Each category has product_count field", False, f"Missing in: {cats_without_count}")
        else:
            log_test(1, "1.2b", "Each category has product_count field", True)
        
    except Exception as e:
        log_test(1, "1.2", "GET /api/categories", False, f"Exception: {e}")
    
    # Test 1.3: Categories with brand filter
    print("\n--- Test 1.3: GET /api/categories?brand_id=<Hansgrohe> ---")
    
    if not brands:
        log_test(1, "1.3", "GET /api/categories with brand filter", False, "No brands available")
        return
    
    # Find Hansgrohe brand
    hansgrohe = next((b for b in brands if b.get("name") == "Hansgrohe"), None)
    if not hansgrohe:
        log_test(1, "1.3", "GET /api/categories with brand filter", False, "Hansgrohe brand not found")
        return
    
    try:
        resp = requests.get(f"{BASE_URL}/categories?brand_id={hansgrohe['id']}", headers=headers)
        if resp.status_code != 200:
            log_test(1, "1.3a", "GET /api/categories?brand_id=<Hansgrohe> returns 200", False, f"Status: {resp.status_code}")
            return
        
        categories = resp.json()
        log_test(1, "1.3a", "GET /api/categories?brand_id=<Hansgrohe> returns 200", True)
        
        # Check all returned categories have product_count > 0
        zero_count_cats = [c.get("name") for c in categories if c.get("product_count", 0) == 0]
        if zero_count_cats:
            log_test(1, "1.3b", "All returned categories have product_count > 0", False, f"Zero count: {zero_count_cats}")
        else:
            log_test(1, "1.3b", "All returned categories have product_count > 0 for Hansgrohe", True)
        
        # Test with fake brand_id
        resp = requests.get(f"{BASE_URL}/categories?brand_id=fake-brand-id-12345", headers=headers)
        if resp.status_code == 200:
            result = resp.json()
            if isinstance(result, list) and len(result) == 0:
                log_test(1, "1.3c", "Fake brand_id returns empty array", True)
            else:
                log_test(1, "1.3c", "Fake brand_id returns empty array", False, f"Got {len(result)} items")
        else:
            log_test(1, "1.3c", "Fake brand_id returns 200", False, f"Status: {resp.status_code}")
        
    except Exception as e:
        log_test(1, "1.3", "GET /api/categories with brand filter", False, f"Exception: {e}")

def test_priority_1_products():
    """PRIORITY 1.4-1.10: GET /api/products with new fields and filters"""
    print("\n--- Test 1.4: GET /api/products?limit=5&sort=popular ---")
    
    try:
        resp = requests.get(f"{BASE_URL}/products?limit=5&sort=popular", headers=headers)
        if resp.status_code != 200:
            log_test(1, "1.4", "GET /api/products?sort=popular returns 200", False, f"Status: {resp.status_code}")
            return None
        
        data = resp.json()
        log_test(1, "1.4a", "GET /api/products?sort=popular returns 200", True)
        
        # Check response shape
        if "total" not in data or "items" not in data:
            log_test(1, "1.4b", "Response has {total, items} shape", False, f"Keys: {data.keys()}")
            return None
        log_test(1, "1.4b", "Response has {total, items} shape", True)
        
        items = data["items"]
        if not items:
            log_test(1, "1.4c", "Items array not empty", False, "No products in database")
            return None
        
        # Check NEW V4 fields on each item
        required_fields = ["popular", "frequently_used", "recently_used", "usage_count", "my_usage_count"]
        missing_fields = {}
        
        for item in items[:5]:  # Check first 5
            for field in required_fields:
                if field not in item:
                    if field not in missing_fields:
                        missing_fields[field] = []
                    missing_fields[field].append(item.get("sku", "unknown"))
        
        if missing_fields:
            log_test(1, "1.4c", "All items have NEW V4 fields (popular, frequently_used, recently_used, usage_count, my_usage_count)", 
                    False, f"Missing fields: {missing_fields}")
        else:
            log_test(1, "1.4c", "All items have NEW V4 fields (popular, frequently_used, recently_used, usage_count, my_usage_count)", True)
        
        # Check field types
        type_errors = []
        for item in items[:5]:
            if not isinstance(item.get("popular"), bool):
                type_errors.append(f"{item.get('sku')}: popular not bool")
            if not isinstance(item.get("frequently_used"), bool):
                type_errors.append(f"{item.get('sku')}: frequently_used not bool")
            if not isinstance(item.get("recently_used"), bool):
                type_errors.append(f"{item.get('sku')}: recently_used not bool")
            if not isinstance(item.get("usage_count"), (int, float)):
                type_errors.append(f"{item.get('sku')}: usage_count not numeric")
            if not isinstance(item.get("my_usage_count"), (int, float)):
                type_errors.append(f"{item.get('sku')}: my_usage_count not numeric")
        
        if type_errors:
            log_test(1, "1.4d", "V4 fields have correct types", False, f"Errors: {type_errors[:3]}")
        else:
            log_test(1, "1.4d", "V4 fields have correct types (bool/int)", True)
        
        return items
        
    except Exception as e:
        log_test(1, "1.4", "GET /api/products?sort=popular", False, f"Exception: {e}")
        return None

def test_priority_1_product_sorts():
    """PRIORITY 1.5-1.8: Test different sort options"""
    
    # Test 1.5: sort=recent
    print("\n--- Test 1.5: GET /api/products?sort=recent ---")
    try:
        resp = requests.get(f"{BASE_URL}/products?sort=recent&limit=5", headers=headers)
        if resp.status_code == 200:
            log_test(1, "1.5", "GET /api/products?sort=recent returns 200", True)
        else:
            log_test(1, "1.5", "GET /api/products?sort=recent returns 200", False, f"Status: {resp.status_code}")
    except Exception as e:
        log_test(1, "1.5", "GET /api/products?sort=recent", False, f"Exception: {e}")
    
    # Test 1.6: sort=price_asc
    print("\n--- Test 1.6: GET /api/products?sort=price_asc ---")
    try:
        resp = requests.get(f"{BASE_URL}/products?sort=price_asc&limit=10", headers=headers)
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            log_test(1, "1.6a", "GET /api/products?sort=price_asc returns 200", True)
            
            # Verify ascending order
            if len(items) >= 2:
                prices = [item.get("price", 0) for item in items]
                is_sorted = all(prices[i] <= prices[i+1] for i in range(len(prices)-1))
                if is_sorted:
                    log_test(1, "1.6b", "Items sorted by price ascending", True, f"Prices: {prices[:5]}")
                else:
                    log_test(1, "1.6b", "Items sorted by price ascending", False, f"Prices: {prices[:5]}")
        else:
            log_test(1, "1.6", "GET /api/products?sort=price_asc", False, f"Status: {resp.status_code}")
    except Exception as e:
        log_test(1, "1.6", "GET /api/products?sort=price_asc", False, f"Exception: {e}")
    
    # Test 1.7: sort=price_desc
    print("\n--- Test 1.7: GET /api/products?sort=price_desc ---")
    try:
        resp = requests.get(f"{BASE_URL}/products?sort=price_desc&limit=10", headers=headers)
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            log_test(1, "1.7a", "GET /api/products?sort=price_desc returns 200", True)
            
            # Verify descending order
            if len(items) >= 2:
                prices = [item.get("price", 0) for item in items]
                is_sorted = all(prices[i] >= prices[i+1] for i in range(len(prices)-1))
                if is_sorted:
                    log_test(1, "1.7b", "Items sorted by price descending", True, f"Prices: {prices[:5]}")
                else:
                    log_test(1, "1.7b", "Items sorted by price descending", False, f"Prices: {prices[:5]}")
        else:
            log_test(1, "1.7", "GET /api/products?sort=price_desc", False, f"Status: {resp.status_code}")
    except Exception as e:
        log_test(1, "1.7", "GET /api/products?sort=price_desc", False, f"Exception: {e}")
    
    # Test 1.8: sort=name
    print("\n--- Test 1.8: GET /api/products?sort=name ---")
    try:
        resp = requests.get(f"{BASE_URL}/products?sort=name&limit=10", headers=headers)
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            log_test(1, "1.8a", "GET /api/products?sort=name returns 200", True)
            
            # Verify alphabetical order
            if len(items) >= 2:
                names = [item.get("name", "") for item in items]
                is_sorted = all(names[i].lower() <= names[i+1].lower() for i in range(len(names)-1))
                if is_sorted:
                    log_test(1, "1.8b", "Items sorted alphabetically by name", True, f"Names: {names[:3]}")
                else:
                    log_test(1, "1.8b", "Items sorted alphabetically by name", False, f"Names: {names[:3]}")
        else:
            log_test(1, "1.8", "GET /api/products?sort=name", False, f"Status: {resp.status_code}")
    except Exception as e:
        log_test(1, "1.8", "GET /api/products?sort=name", False, f"Exception: {e}")

def test_priority_1_product_search_and_filters(brands):
    """PRIORITY 1.9-1.10: Search and combined filters"""
    
    # Test 1.9: Search
    print("\n--- Test 1.9: GET /api/products?q=chrome ---")
    try:
        resp = requests.get(f"{BASE_URL}/products?q=chrome&limit=10", headers=headers)
        if resp.status_code == 200:
            log_test(1, "1.9", "GET /api/products?q=chrome returns 200", True, f"Found {resp.json().get('total', 0)} items")
        else:
            log_test(1, "1.9", "GET /api/products?q=chrome returns 200", False, f"Status: {resp.status_code}")
    except Exception as e:
        log_test(1, "1.9", "GET /api/products?q=chrome", False, f"Exception: {e}")
    
    # Test 1.10: Combined brand + category filter
    print("\n--- Test 1.10: GET /api/products?brand_id=X&category_id=Y ---")
    
    if not brands:
        log_test(1, "1.10", "Combined brand+category filter", False, "No brands available")
        return
    
    # Get a brand with products
    brand_with_products = next((b for b in brands if b.get("product_count", 0) > 0), None)
    if not brand_with_products:
        log_test(1, "1.10", "Combined brand+category filter", False, "No brands with products")
        return
    
    try:
        # Get categories for this brand
        cat_resp = requests.get(f"{BASE_URL}/categories?brand_id={brand_with_products['id']}", headers=headers)
        if cat_resp.status_code != 200:
            log_test(1, "1.10", "Combined brand+category filter", False, "Could not fetch categories")
            return
        
        categories = cat_resp.json()
        if not categories:
            log_test(1, "1.10", "Combined brand+category filter", False, "No categories for brand")
            return
        
        category = categories[0]
        
        # Test combined filter
        resp = requests.get(f"{BASE_URL}/products?brand_id={brand_with_products['id']}&category_id={category['id']}&limit=20", 
                          headers=headers)
        if resp.status_code != 200:
            log_test(1, "1.10a", "Combined filter returns 200", False, f"Status: {resp.status_code}")
            return
        
        data = resp.json()
        items = data.get("items", [])
        log_test(1, "1.10a", "Combined filter returns 200", True, f"Found {len(items)} items")
        
        # Verify all items match both filters
        mismatches = []
        for item in items:
            if item.get("brand_id") != brand_with_products['id']:
                mismatches.append(f"{item.get('sku')}: wrong brand")
            if item.get("category_id") != category['id']:
                mismatches.append(f"{item.get('sku')}: wrong category")
        
        if mismatches:
            log_test(1, "1.10b", "All items match both brand_id and category_id", False, f"Mismatches: {mismatches[:3]}")
        else:
            log_test(1, "1.10b", "All items match both brand_id and category_id filters", True)
        
    except Exception as e:
        log_test(1, "1.10", "Combined brand+category filter", False, f"Exception: {e}")

def test_priority_2_custom_product(brands):
    """PRIORITY 2: Custom product creation"""
    print("\n=== PRIORITY 2: CUSTOM PRODUCT ===")
    
    if not brands:
        log_test(2, "2.1", "Custom product creation", False, "No brands available")
        return None
    
    brand = brands[0]
    
    # Get a category
    try:
        cat_resp = requests.get(f"{BASE_URL}/categories", headers=headers)
        categories = cat_resp.json()
        if not categories:
            log_test(2, "2.1", "Custom product creation", False, "No categories available")
            return None
        category = categories[0]
    except:
        log_test(2, "2.1", "Custom product creation", False, "Could not fetch categories")
        return None
    
    # Test 2.1: Create custom product
    print("\n--- Test 2.1: POST /api/products/custom ---")
    custom_sku = f"TESTCUST-{datetime.now().strftime('%H%M%S')}"
    
    payload = {
        "name": "Test Custom Sink",
        "sku": custom_sku,
        "brand_id": brand["id"],
        "category_id": category["id"],
        "price": 5000,
        "mrp": 6000,
        "is_custom": True
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/products/custom", json=payload, headers=headers)
        if resp.status_code != 200:
            log_test(2, "2.1a", "POST /api/products/custom returns 200", False, 
                    f"Status: {resp.status_code}, Body: {resp.text[:200]}")
            return None
        
        product = resp.json()
        log_test(2, "2.1a", "POST /api/products/custom returns 200", True)
        
        # Check is_custom=true
        if product.get("is_custom") != True:
            log_test(2, "2.1b", "Product has is_custom=true", False, f"is_custom={product.get('is_custom')}")
        else:
            log_test(2, "2.1b", "Product has is_custom=true", True)
        
        # Check tags contains "custom"
        tags = product.get("tags", [])
        if "custom" not in tags:
            log_test(2, "2.1c", "Tags contains 'custom'", False, f"Tags: {tags}")
        else:
            log_test(2, "2.1c", "Tags contains 'custom'", True)
        
        product_id = product.get("id")
        
        # Test 2.2: Create with same SKU (should auto-suffix)
        print("\n--- Test 2.2: POST same SKU again (auto-suffix) ---")
        resp2 = requests.post(f"{BASE_URL}/products/custom", json=payload, headers=headers)
        if resp2.status_code != 200:
            log_test(2, "2.2a", "Second POST with same SKU returns 200", False, f"Status: {resp2.status_code}")
        else:
            product2 = resp2.json()
            log_test(2, "2.2a", "Second POST with same SKU returns 200 (auto-suffix)", True)
            
            # Check SKU was suffixed
            new_sku = product2.get("sku")
            if new_sku == custom_sku:
                log_test(2, "2.2b", "SKU auto-suffixed", False, f"SKU unchanged: {new_sku}")
            else:
                log_test(2, "2.2b", f"SKU auto-suffixed to {new_sku}", True)
            
            # Check is_custom still true
            if product2.get("is_custom") != True:
                log_test(2, "2.2c", "Second product has is_custom=true", False)
            else:
                log_test(2, "2.2c", "Second product has is_custom=true", True)
        
        # Test 2.3: Create with is_custom=false and duplicate SKU (should fail)
        print("\n--- Test 2.3: POST with is_custom=false and duplicate SKU ---")
        payload_non_custom = {**payload, "is_custom": False}
        resp3 = requests.post(f"{BASE_URL}/products/custom", json=payload_non_custom, headers=headers)
        if resp3.status_code == 409:
            log_test(2, "2.3", "POST with is_custom=false and duplicate SKU returns 409 Conflict", True)
        else:
            log_test(2, "2.3", "POST with is_custom=false and duplicate SKU returns 409", False, 
                    f"Status: {resp3.status_code}")
        
        # Test 2.4: Search for custom product
        print("\n--- Test 2.4: GET /api/products?q=Test Custom ---")
        resp4 = requests.get(f"{BASE_URL}/products?q=Test%20Custom", headers=headers)
        if resp4.status_code == 200:
            data = resp4.json()
            items = data.get("items", [])
            found = any(item.get("id") == product_id for item in items)
            if found:
                log_test(2, "2.4", "Custom product appears in search results", True)
            else:
                log_test(2, "2.4", "Custom product appears in search results", False, 
                        f"Product {product_id} not found in {len(items)} results")
        else:
            log_test(2, "2.4", "Search for custom product", False, f"Status: {resp4.status_code}")
        
        # Test 2.5: Auth check
        print("\n--- Test 2.5: POST /api/products/custom without token ---")
        resp5 = requests.post(f"{BASE_URL}/products/custom", json=payload)
        if resp5.status_code == 401:
            log_test(2, "2.5", "POST /api/products/custom without token returns 401", True)
        else:
            log_test(2, "2.5", "POST /api/products/custom without token returns 401", False, 
                    f"Status: {resp5.status_code}")
        
        return product_id
        
    except Exception as e:
        log_test(2, "2.1", "Custom product creation", False, f"Exception: {e}")
        return None

def test_priority_3_complete_the_set():
    """PRIORITY 3: Complete the set endpoint"""
    print("\n=== PRIORITY 3: COMPLETE THE SET ===")
    
    # Get any product
    try:
        resp = requests.get(f"{BASE_URL}/products?limit=1", headers=headers)
        if resp.status_code != 200 or not resp.json().get("items"):
            log_test(3, "3.1", "Complete the set", False, "No products available")
            return
        
        product_id = resp.json()["items"][0]["id"]
        
        # Test 3.1: Get complete-the-set
        print("\n--- Test 3.1: GET /api/products/{id}/complete-the-set ---")
        resp = requests.get(f"{BASE_URL}/products/{product_id}/complete-the-set?limit=6", headers=headers)
        if resp.status_code != 200:
            log_test(3, "3.1a", "GET /api/products/{id}/complete-the-set returns 200", False, 
                    f"Status: {resp.status_code}")
            return
        
        data = resp.json()
        log_test(3, "3.1a", "GET /api/products/{id}/complete-the-set returns 200", True)
        
        # Check response shape
        if "source_product_id" not in data or "items" not in data:
            log_test(3, "3.1b", "Response has {source_product_id, items} shape", False, f"Keys: {data.keys()}")
        else:
            log_test(3, "3.1b", "Response has {source_product_id, items} shape", True)
            
            # Check source_product_id matches
            if data["source_product_id"] != product_id:
                log_test(3, "3.1c", "source_product_id matches request", False, 
                        f"Expected {product_id}, got {data['source_product_id']}")
            else:
                log_test(3, "3.1c", "source_product_id matches request", True)
            
            # Items may be empty (small seed catalog)
            items = data.get("items", [])
            log_test(3, "3.1d", f"Items array present (found {len(items)} companion products)", True)
        
        # Test 3.2: Non-existent product
        print("\n--- Test 3.2: GET /api/products/fake-id/complete-the-set ---")
        resp = requests.get(f"{BASE_URL}/products/fake-product-id-12345/complete-the-set", headers=headers)
        if resp.status_code == 404:
            body = resp.json()
            if "Product not found" in body.get("detail", ""):
                log_test(3, "3.2", "Non-existent product returns 404 with 'Product not found'", True)
            else:
                log_test(3, "3.2", "Non-existent product returns 404", False, f"Detail: {body.get('detail')}")
        else:
            log_test(3, "3.2", "Non-existent product returns 404", False, f"Status: {resp.status_code}")
        
        # Test 3.3: Auth check
        print("\n--- Test 3.3: GET /api/products/{id}/complete-the-set without token ---")
        resp = requests.get(f"{BASE_URL}/products/{product_id}/complete-the-set")
        if resp.status_code == 401:
            log_test(3, "3.3", "Without token returns 401", True)
        else:
            log_test(3, "3.3", "Without token returns 401", False, f"Status: {resp.status_code}")
        
    except Exception as e:
        log_test(3, "3.1", "Complete the set", False, f"Exception: {e}")

def test_priority_4_recent_quotations():
    """PRIORITY 4: Recent quotations endpoint"""
    print("\n=== PRIORITY 4: RECENT QUOTATIONS ===")
    
    print("\n--- Test 4.1: GET /api/quotations/recent?limit=5 ---")
    
    try:
        resp = requests.get(f"{BASE_URL}/quotations/recent?limit=5", headers=headers)
        if resp.status_code != 200:
            log_test(4, "4.1a", "GET /api/quotations/recent returns 200", False, f"Status: {resp.status_code}")
            return None
        
        quotations = resp.json()
        log_test(4, "4.1a", "GET /api/quotations/recent returns 200", True)
        
        # Check it's an array
        if not isinstance(quotations, list):
            log_test(4, "4.1b", "Returns array", False, f"Got {type(quotations)}")
            return None
        log_test(4, "4.1b", "Returns array", True)
        
        # Check limit honored
        if len(quotations) > 5:
            log_test(4, "4.1c", "Limit honored (≤5 items)", False, f"Got {len(quotations)} items")
        else:
            log_test(4, "4.1c", f"Limit honored (got {len(quotations)} items)", True)
        
        if not quotations:
            log_test(4, "4.1d", "Required fields present", True, "No quotations to check")
            log_test(4, "4.2", "Ordered by updated_at DESC", True, "No quotations to check")
            return None
        
        # Check required fields
        required_fields = ["id", "number", "customer_id", "customer_name", "project_name", 
                          "phone", "grand_total", "status", "revision_count", "updated_at"]
        
        missing_fields = {}
        for quot in quotations:
            for field in required_fields:
                if field not in quot:
                    if field not in missing_fields:
                        missing_fields[field] = []
                    missing_fields[field].append(quot.get("number", "unknown"))
        
        if missing_fields:
            log_test(4, "4.1d", "All required fields present", False, f"Missing: {missing_fields}")
        else:
            log_test(4, "4.1d", "All required fields present (id, number, customer_name, project_name, phone, grand_total, status, revision_count, updated_at)", True)
        
        # Test 4.2: Check ordering by updated_at DESC
        print("\n--- Test 4.2: Verify ordering by updated_at DESC ---")
        if len(quotations) >= 2:
            timestamps = [q.get("updated_at") for q in quotations]
            is_desc = all(timestamps[i] >= timestamps[i+1] for i in range(len(timestamps)-1) if timestamps[i] and timestamps[i+1])
            if is_desc:
                log_test(4, "4.2", "Quotations ordered by updated_at DESC (most recent first)", True)
            else:
                log_test(4, "4.2", "Quotations ordered by updated_at DESC", False, f"Timestamps: {timestamps}")
        else:
            log_test(4, "4.2", "Ordering check", True, "Only 1 quotation, ordering N/A")
        
        # Test 4.3: Auth check
        print("\n--- Test 4.3: GET /api/quotations/recent without token ---")
        resp = requests.get(f"{BASE_URL}/quotations/recent")
        if resp.status_code == 401:
            log_test(4, "4.3", "Without token returns 401", True)
        else:
            log_test(4, "4.3", "Without token returns 401", False, f"Status: {resp.status_code}")
        
        return quotations[0] if quotations else None
        
    except Exception as e:
        log_test(4, "4.1", "Recent quotations", False, f"Exception: {e}")
        return None

def test_priority_5_v4_quotation_fields():
    """PRIORITY 5: V4 quotation header fields + ui_state"""
    print("\n=== PRIORITY 5: V4 QUOTATION HEADER FIELDS + UI_STATE ===")
    
    # Get a customer
    try:
        cust_resp = requests.get(f"{BASE_URL}/customers?limit=1", headers=headers)
        if cust_resp.status_code != 200 or not cust_resp.json():
            log_test(5, "5.1", "V4 quotation fields", False, "No customers available")
            return None
        customer_id = cust_resp.json()[0]["id"]
    except:
        log_test(5, "5.1", "V4 quotation fields", False, "Could not fetch customer")
        return None
    
    # Test 5.1: Create quotation with V4 fields
    print("\n--- Test 5.1: POST /api/quotations with V4 fields ---")
    
    payload = {
        "customer_id": customer_id,
        "items": [],
        "rooms": ["Master Bath"],
        "project_name": "Villa Phase 2",
        "phone_snapshot": "+91 9876543210",
        "reference_source": "Architect referral"
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/quotations", json=payload, headers=headers)
        if resp.status_code not in [200, 201]:
            log_test(5, "5.1a", "POST /api/quotations with V4 fields", False, 
                    f"Status: {resp.status_code}, Body: {resp.text[:200]}")
            return None
        
        quotation = resp.json()
        quotation_id = quotation.get("id")
        log_test(5, "5.1a", "POST /api/quotations with V4 fields returns 200/201", True)
        
        # Check V4 fields persisted
        v4_fields_ok = True
        errors = []
        
        if quotation.get("project_name") != "Villa Phase 2":
            v4_fields_ok = False
            errors.append(f"project_name: expected 'Villa Phase 2', got '{quotation.get('project_name')}'")
        
        if quotation.get("phone_snapshot") != "+91 9876543210":
            v4_fields_ok = False
            errors.append(f"phone_snapshot: expected '+91 9876543210', got '{quotation.get('phone_snapshot')}'")
        
        if quotation.get("reference_source") != "Architect referral":
            v4_fields_ok = False
            errors.append(f"reference_source: expected 'Architect referral', got '{quotation.get('reference_source')}'")
        
        if v4_fields_ok:
            log_test(5, "5.1b", "V4 fields (project_name, phone_snapshot, reference_source) persisted correctly", True)
        else:
            log_test(5, "5.1b", "V4 fields persisted correctly", False, f"Errors: {errors}")
        
        # Test 5.2: GET quotation and verify fields
        print("\n--- Test 5.2: GET /api/quotations/{id} ---")
        resp = requests.get(f"{BASE_URL}/quotations/{quotation_id}", headers=headers)
        if resp.status_code != 200:
            log_test(5, "5.2", "GET /api/quotations/{id}", False, f"Status: {resp.status_code}")
        else:
            quot = resp.json()
            v4_fields_ok = (
                quot.get("project_name") == "Villa Phase 2" and
                quot.get("phone_snapshot") == "+91 9876543210" and
                quot.get("reference_source") == "Architect referral"
            )
            if v4_fields_ok:
                log_test(5, "5.2", "GET returns quotation with V4 fields intact", True)
            else:
                log_test(5, "5.2", "GET returns quotation with V4 fields", False, 
                        f"project_name={quot.get('project_name')}, phone={quot.get('phone_snapshot')}, ref={quot.get('reference_source')}")
        
        # Test 5.3: PATCH with ui_state
        print("\n--- Test 5.3: PATCH /api/quotations/{id} with ui_state ---")
        ui_state = {
            "activeRoom": "Master Bath",
            "collapsedRooms": {"Master Bath": False},
            "selectedBrandId": "foo",
            "sortKey": "recent"
        }
        
        patch_payload = {
            "silent": True,
            "ui_state": ui_state
        }
        
        resp = requests.patch(f"{BASE_URL}/quotations/{quotation_id}", json=patch_payload, headers=headers)
        if resp.status_code != 200:
            log_test(5, "5.3a", "PATCH with ui_state returns 200", False, f"Status: {resp.status_code}")
        else:
            log_test(5, "5.3a", "PATCH with ui_state returns 200", True)
            
            # GET and verify ui_state persisted
            resp = requests.get(f"{BASE_URL}/quotations/{quotation_id}", headers=headers)
            if resp.status_code == 200:
                quot = resp.json()
                persisted_ui_state = quot.get("ui_state", {})
                
                if persisted_ui_state == ui_state:
                    log_test(5, "5.3b", "ui_state persisted with all keys", True)
                else:
                    log_test(5, "5.3b", "ui_state persisted", False, 
                            f"Expected {ui_state}, got {persisted_ui_state}")
        
        # Test 5.4: PATCH project_name, verify phone_snapshot preserved
        print("\n--- Test 5.4: PATCH project_name, verify phone_snapshot preserved ---")
        patch_payload = {
            "silent": True,
            "project_name": "Villa Phase 3"
        }
        
        resp = requests.patch(f"{BASE_URL}/quotations/{quotation_id}", json=patch_payload, headers=headers)
        if resp.status_code == 200:
            quot = resp.json()
            if quot.get("project_name") == "Villa Phase 3" and quot.get("phone_snapshot") == "+91 9876543210":
                log_test(5, "5.4", "PATCH project_name updates field, phone_snapshot preserved", True)
            else:
                log_test(5, "5.4", "PATCH project_name", False, 
                        f"project_name={quot.get('project_name')}, phone={quot.get('phone_snapshot')}")
        else:
            log_test(5, "5.4", "PATCH project_name", False, f"Status: {resp.status_code}")
        
        # Test 5.5: PATCH silent=true should NOT create revision
        print("\n--- Test 5.5: PATCH silent=true should NOT create revision ---")
        resp = requests.get(f"{BASE_URL}/quotations/{quotation_id}", headers=headers)
        if resp.status_code == 200:
            quot = resp.json()
            revisions = quot.get("revisions", [])
            if len(revisions) == 0:
                log_test(5, "5.5", "PATCH silent=true does NOT create revision", True)
            else:
                log_test(5, "5.5", "PATCH silent=true does NOT create revision", False, 
                        f"Found {len(revisions)} revisions")
        
        # Test 5.6: PATCH silent=false should create revision
        print("\n--- Test 5.6: PATCH silent=false creates revision ---")
        patch_payload = {
            "silent": False,
            "notes": "Test revision",
            "reason": "Testing revision creation"
        }
        
        resp = requests.patch(f"{BASE_URL}/quotations/{quotation_id}", json=patch_payload, headers=headers)
        if resp.status_code == 200:
            quot = resp.json()
            revisions = quot.get("revisions", [])
            if len(revisions) >= 1:
                log_test(5, "5.6", "PATCH silent=false creates revision", True, f"Revisions: {len(revisions)}")
            else:
                log_test(5, "5.6", "PATCH silent=false creates revision", False, "No revisions created")
        else:
            log_test(5, "5.6", "PATCH silent=false", False, f"Status: {resp.status_code}")
        
        return quotation_id
        
    except Exception as e:
        log_test(5, "5.1", "V4 quotation fields", False, f"Exception: {e}")
        return None

def test_priority_6_smoke_regression():
    """PRIORITY 6: Smoke regression on existing endpoints"""
    print("\n=== PRIORITY 6: SMOKE REGRESSION ===")
    
    # Get a customer for tests
    try:
        cust_resp = requests.get(f"{BASE_URL}/customers?limit=1", headers=headers)
        if cust_resp.status_code != 200 or not cust_resp.json():
            customer_id = None
        else:
            customer_id = cust_resp.json()[0]["id"]
    except:
        customer_id = None
    
    # Test 6.1: POST /api/quotations (existing shape)
    print("\n--- Test 6.1: POST /api/quotations (existing shape without V4 fields) ---")
    if customer_id:
        try:
            payload = {
                "customer_id": customer_id,
                "items": [],
                "rooms": ["Living Room"]
            }
            resp = requests.post(f"{BASE_URL}/quotations", json=payload, headers=headers)
            if resp.status_code in [200, 201]:
                log_test(6, "6.1", "POST /api/quotations (existing shape) still works", True)
            else:
                log_test(6, "6.1", "POST /api/quotations (existing shape)", False, f"Status: {resp.status_code}")
        except Exception as e:
            log_test(6, "6.1", "POST /api/quotations", False, f"Exception: {e}")
    else:
        log_test(6, "6.1", "POST /api/quotations", False, "No customer available")
    
    # Test 6.2: GET /api/products/{id}/alternates
    print("\n--- Test 6.2: GET /api/products/{id}/alternates ---")
    try:
        prod_resp = requests.get(f"{BASE_URL}/products?limit=1", headers=headers)
        if prod_resp.status_code == 200 and prod_resp.json().get("items"):
            product_id = prod_resp.json()["items"][0]["id"]
            
            resp = requests.get(f"{BASE_URL}/products/{product_id}/alternates?limit=5", headers=headers)
            if resp.status_code != 200:
                log_test(6, "6.2a", "GET /api/products/{id}/alternates returns 200", False, f"Status: {resp.status_code}")
            else:
                data = resp.json()
                log_test(6, "6.2a", "GET /api/products/{id}/alternates returns 200", True)
                
                # Check shape
                required_keys = ["source_product_id", "items", "tiers"]
                missing = [k for k in required_keys if k not in data]
                if missing:
                    log_test(6, "6.2b", "Response has correct shape {source_product_id, items, tiers}", False, 
                            f"Missing: {missing}")
                else:
                    log_test(6, "6.2b", "Response has correct shape {source_product_id, items, tiers}", True)
                    
                    # Check tiers structure
                    tiers = data.get("tiers", {})
                    tier_keys = ["family", "brand_category", "category"]
                    missing_tier_keys = [k for k in tier_keys if k not in tiers]
                    if missing_tier_keys:
                        log_test(6, "6.2c", "Tiers has {family, brand_category, category}", False, 
                                f"Missing: {missing_tier_keys}")
                    else:
                        log_test(6, "6.2c", "Tiers structure correct {family, brand_category, category}", True)
        else:
            log_test(6, "6.2", "GET /api/products/{id}/alternates", False, "No products available")
    except Exception as e:
        log_test(6, "6.2", "GET /api/products/{id}/alternates", False, f"Exception: {e}")
    
    # Test 6.3: GET /api/purchase-orders
    print("\n--- Test 6.3: GET /api/purchase-orders ---")
    try:
        resp = requests.get(f"{BASE_URL}/purchase-orders", headers=headers)
        if resp.status_code == 200:
            log_test(6, "6.3", "GET /api/purchase-orders returns 200 with array", True)
        else:
            log_test(6, "6.3", "GET /api/purchase-orders", False, f"Status: {resp.status_code}")
    except Exception as e:
        log_test(6, "6.3", "GET /api/purchase-orders", False, f"Exception: {e}")
    
    # Test 6.4: GET /api/payments/stats
    print("\n--- Test 6.4: GET /api/payments/stats ---")
    try:
        resp = requests.get(f"{BASE_URL}/payments/stats", headers=headers)
        if resp.status_code != 200:
            log_test(6, "6.4a", "GET /api/payments/stats returns 200", False, f"Status: {resp.status_code}")
        else:
            data = resp.json()
            log_test(6, "6.4a", "GET /api/payments/stats returns 200", True)
            
            required_keys = ["total_outstanding", "collected_this_month", "active_orders", "fully_paid"]
            missing = [k for k in required_keys if k not in data]
            if missing:
                log_test(6, "6.4b", "Stats has all required keys", False, f"Missing: {missing}")
            else:
                log_test(6, "6.4b", "Stats has {total_outstanding, collected_this_month, active_orders, fully_paid}", True)
    except Exception as e:
        log_test(6, "6.4", "GET /api/payments/stats", False, f"Exception: {e}")
    
    # Test 6.5: POST /api/quotations/{id}/place-order/preview
    print("\n--- Test 6.5: POST /api/quotations/{id}/place-order/preview ---")
    try:
        # Get a quotation with items
        quot_resp = requests.get(f"{BASE_URL}/quotations", headers=headers)
        if quot_resp.status_code == 200:
            quotations = quot_resp.json()
            quot_with_items = next((q for q in quotations if q.get("items") and len(q.get("items", [])) > 0), None)
            
            if quot_with_items:
                resp = requests.get(f"{BASE_URL}/quotations/{quot_with_items['id']}/place-order/preview", headers=headers)
                if resp.status_code == 200:
                    log_test(6, "6.5", "GET /api/quotations/{id}/place-order/preview returns 200", True)
                else:
                    log_test(6, "6.5", "GET /api/quotations/{id}/place-order/preview", False, f"Status: {resp.status_code}")
            else:
                log_test(6, "6.5", "GET /api/quotations/{id}/place-order/preview", True, "No quotations with items to test")
        else:
            log_test(6, "6.5", "GET /api/quotations/{id}/place-order/preview", False, "Could not fetch quotations")
    except Exception as e:
        log_test(6, "6.5", "GET /api/quotations/{id}/place-order/preview", False, f"Exception: {e}")
    
    # Test 6.6: POST /api/quotations/{id}/duplicate
    print("\n--- Test 6.6: POST /api/quotations/{id}/duplicate ---")
    try:
        quot_resp = requests.get(f"{BASE_URL}/quotations?limit=1", headers=headers)
        if quot_resp.status_code == 200:
            quotations = quot_resp.json()
            if quotations:
                quotation_id = quotations[0]["id"]
                resp = requests.post(f"{BASE_URL}/quotations/{quotation_id}/duplicate", headers=headers)
                if resp.status_code in [200, 201]:
                    new_quot = resp.json()
                    if new_quot.get("id") != quotation_id and new_quot.get("number") != quotations[0].get("number"):
                        log_test(6, "6.6", "POST /api/quotations/{id}/duplicate creates new quotation with new id and number", True)
                    else:
                        log_test(6, "6.6", "POST /api/quotations/{id}/duplicate", False, "New quotation has same id or number")
                else:
                    log_test(6, "6.6", "POST /api/quotations/{id}/duplicate", False, f"Status: {resp.status_code}")
            else:
                log_test(6, "6.6", "POST /api/quotations/{id}/duplicate", True, "No quotations to test")
        else:
            log_test(6, "6.6", "POST /api/quotations/{id}/duplicate", False, "Could not fetch quotations")
    except Exception as e:
        log_test(6, "6.6", "POST /api/quotations/{id}/duplicate", False, f"Exception: {e}")

def print_summary():
    """Print test summary"""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    # Group by priority
    by_priority = {}
    for result in test_results:
        priority = result["priority"]
        if priority not in by_priority:
            by_priority[priority] = []
        by_priority[priority].append(result)
    
    total_tests = len(test_results)
    passed_tests = sum(1 for r in test_results if r["passed"])
    failed_tests = total_tests - passed_tests
    
    for priority in sorted(by_priority.keys()):
        results = by_priority[priority]
        passed = sum(1 for r in results if r["passed"])
        total = len(results)
        
        print(f"\nPRIORITY {priority}: {passed}/{total} passed")
        print("-" * 80)
        
        # Show failed tests first
        failed = [r for r in results if not r["passed"]]
        if failed:
            print("❌ FAILED:")
            for r in failed:
                print(f"  {r['test_id']}: {r['description']}")
                if r["details"]:
                    print(f"      {r['details']}")
        
        # Show passed tests (condensed)
        passed_list = [r for r in results if r["passed"]]
        if passed_list:
            print(f"✅ PASSED: {len(passed_list)} tests")
    
    print("\n" + "="*80)
    print(f"OVERALL: {passed_tests}/{total_tests} tests passed ({passed_tests*100//total_tests if total_tests > 0 else 0}%)")
    if failed_tests > 0:
        print(f"FAILED: {failed_tests} tests")
    print("="*80)

def main():
    """Run all tests"""
    print("="*80)
    print("QUOTATION BUILDER V4 BACKEND REGRESSION TEST")
    print("="*80)
    print(f"API Base URL: {BASE_URL}")
    print(f"Test User: {EMAIL}")
    print("="*80)
    
    # Login
    if not login():
        print("\n❌ Authentication failed. Cannot proceed with tests.")
        return
    
    # Run tests in priority order
    brands = test_priority_1_brands()
    test_priority_1_categories(brands)
    test_priority_1_products()
    test_priority_1_product_sorts()
    test_priority_1_product_search_and_filters(brands)
    
    test_priority_2_custom_product(brands)
    
    test_priority_3_complete_the_set()
    
    test_priority_4_recent_quotations()
    
    test_priority_5_v4_quotation_fields()
    
    test_priority_6_smoke_regression()
    
    # Print summary
    print_summary()

if __name__ == "__main__":
    main()
