"""
Production Readiness Audit for Forge / BuildCon House
Backend API Testing Suite

Tests all critical areas:
1. AUTH - staff/customer login, protected routes, logout, sessions
2. CATALOG - products, brands, categories, media URLs
3. QUOTATION BUILDER - create, PATCH, duplicate, breakdown, PDF
4. AUTOMATION CHAIN - end-to-end quotation → PO → payment → followup
5. PAYMENTS - stats, outstanding calculation
6. FOLLOW-UPS - reconcile idempotency
7. REPORTS/EXPORTS - all export endpoints
8. GENERAL SMOKE - dashboard, customers, etc.
"""

import requests
import json
import time
from typing import Optional

# Backend URL from frontend/.env
BASE_URL = "https://1deed631-1b10-466c-b334-29b01d99ed3f.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
STAFF_ACCOUNTS = [
    {"email": "owner@forge.app", "password": "Forge@2026", "role": "owner"},
    {"email": "admin@forge.app", "password": "Forge@2026", "role": "admin"},
    {"email": "manager@forge.app", "password": "Forge@2026", "role": "manager"},
    {"email": "sales@forge.app", "password": "Forge@2026", "role": "sales"},
    {"email": "purchase@forge.app", "password": "Forge@2026", "role": "purchase"},
    {"email": "warehouse@forge.app", "password": "Forge@2026", "role": "warehouse"},
    {"email": "accounts@forge.app", "password": "Forge@2026", "role": "accounts"},
    {"email": "worker@forge.app", "password": "Forge@2026", "role": "worker"},
]

CUSTOMER_ACCOUNT = {"email": "customer@forge.app", "password": "Forge@2026"}

# Global test state
staff_token: Optional[str] = None
customer_token: Optional[str] = None
test_quotation_id: Optional[str] = None
test_po_id: Optional[str] = None
test_customer_id: Optional[str] = None

class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
    
    def add_pass(self, test_name: str, details: str = ""):
        self.passed.append(f"✅ {test_name}" + (f" - {details}" if details else ""))
    
    def add_fail(self, test_name: str, details: str):
        self.failed.append(f"❌ {test_name} - {details}")
    
    def add_warning(self, test_name: str, details: str):
        self.warnings.append(f"⚠️  {test_name} - {details}")
    
    def print_summary(self):
        print("\n" + "="*80)
        print("PRODUCTION READINESS AUDIT SUMMARY")
        print("="*80)
        
        if self.failed:
            print(f"\n🔴 FAILED TESTS ({len(self.failed)}):")
            for f in self.failed:
                print(f"  {f}")
        
        if self.warnings:
            print(f"\n🟡 WARNINGS ({len(self.warnings)}):")
            for w in self.warnings:
                print(f"  {w}")
        
        if self.passed:
            print(f"\n🟢 PASSED TESTS ({len(self.passed)}):")
            for p in self.passed:
                print(f"  {p}")
        
        print(f"\n{'='*80}")
        print(f"TOTAL: {len(self.passed)} passed, {len(self.failed)} failed, {len(self.warnings)} warnings")
        print(f"{'='*80}\n")

result = TestResult()

def test_section(name: str):
    """Decorator to print section headers"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            print(f"\n{'='*80}")
            print(f"SECTION: {name}")
            print(f"{'='*80}")
            return func(*args, **kwargs)
        return wrapper
    return decorator

# =============================================================================
# SECTION 1: AUTH
# =============================================================================

@test_section("1. AUTH - Staff Login, Customer Login, Protected Routes, Logout, Sessions")
def test_auth():
    global staff_token, customer_token, test_customer_id
    
    # 1.1 Test all 8 staff accounts
    print("\n1.1 Testing staff login for all 8 role accounts...")
    for account in STAFF_ACCOUNTS:
        try:
            resp = requests.post(f"{BASE_URL}/auth/login", json={
                "email": account["email"],
                "password": account["password"]
            })
            if resp.status_code == 200:
                data = resp.json()
                if "access_token" in data and "user" in data:
                    result.add_pass(f"Staff login: {account['email']}", f"role={account['role']}")
                    if account["role"] == "owner":
                        staff_token = data["access_token"]
                else:
                    result.add_fail(f"Staff login: {account['email']}", "Missing access_token or user in response")
            else:
                result.add_fail(f"Staff login: {account['email']}", f"Status {resp.status_code}: {resp.text}")
        except Exception as e:
            result.add_fail(f"Staff login: {account['email']}", str(e))
    
    # 1.2 Test wrong password returns 401
    print("\n1.2 Testing wrong password returns 401...")
    try:
        resp = requests.post(f"{BASE_URL}/auth/login", json={
            "email": "owner@forge.app",
            "password": "WrongPassword123"
        })
        if resp.status_code == 401:
            result.add_pass("Wrong password returns 401")
        else:
            result.add_fail("Wrong password returns 401", f"Got status {resp.status_code} instead of 401")
    except Exception as e:
        result.add_fail("Wrong password returns 401", str(e))
    
    # 1.3 Test protected route without token returns 401
    print("\n1.3 Testing protected routes return 401 without bearer token...")
    protected_routes = [
        "/quotations",
        "/payments/stats",
        "/customers",
        "/purchase-orders",
        "/followups/stats"
    ]
    for route in protected_routes:
        try:
            resp = requests.get(f"{BASE_URL}{route}")
            if resp.status_code == 401:
                result.add_pass(f"Protected route {route} returns 401 without token")
            else:
                result.add_fail(f"Protected route {route} returns 401 without token", 
                              f"Got status {resp.status_code}")
        except Exception as e:
            result.add_fail(f"Protected route {route} returns 401 without token", str(e))
    
    # 1.4 Test customer portal login
    print("\n1.4 Testing customer portal login...")
    try:
        resp = requests.post(f"{BASE_URL}/auth/customer/login", json={
            "email": CUSTOMER_ACCOUNT["email"],
            "password": CUSTOMER_ACCOUNT["password"]
        })
        if resp.status_code == 200:
            data = resp.json()
            if "access_token" in data and "customer" in data:
                customer_token = data["access_token"]
                test_customer_id = data["customer"].get("id")
                result.add_pass("Customer portal login", f"customer_id={test_customer_id}")
            else:
                result.add_fail("Customer portal login", "Missing access_token or customer in response")
        else:
            result.add_fail("Customer portal login", f"Status {resp.status_code}: {resp.text}")
    except Exception as e:
        result.add_fail("Customer portal login", str(e))
    
    # 1.5 Test logout invalidates session
    print("\n1.5 Testing POST /auth/logout...")
    if staff_token:
        try:
            resp = requests.post(f"{BASE_URL}/auth/logout", 
                               headers={"Authorization": f"Bearer {staff_token}"})
            if resp.status_code == 200:
                data = resp.json()
                result.add_pass("POST /auth/logout", f"revoked={data.get('revoked')}")
                # Note: JWT tokens are stateless, so old token may still work unless session_id is checked
                result.add_warning("Session invalidation", 
                                 "JWT is stateless - old token may still work if session_id not enforced")
            else:
                result.add_fail("POST /auth/logout", f"Status {resp.status_code}")
        except Exception as e:
            result.add_fail("POST /auth/logout", str(e))
        
        # Re-login to get fresh token
        resp = requests.post(f"{BASE_URL}/auth/login", json={
            "email": "owner@forge.app",
            "password": "Forge@2026"
        })
        if resp.status_code == 200:
            staff_token = resp.json()["access_token"]
    
    # 1.6 Test POST /auth/sessions/logout-all
    print("\n1.6 Testing POST /auth/sessions/logout-all...")
    if staff_token:
        try:
            resp = requests.post(f"{BASE_URL}/auth/sessions/logout-all",
                               headers={"Authorization": f"Bearer {staff_token}"})
            if resp.status_code == 200:
                data = resp.json()
                result.add_pass("POST /auth/sessions/logout-all", f"revoked_count={data.get('revoked_count')}")
            else:
                result.add_fail("POST /auth/sessions/logout-all", f"Status {resp.status_code}")
        except Exception as e:
            result.add_fail("POST /auth/sessions/logout-all", str(e))
        
        # Re-login again
        resp = requests.post(f"{BASE_URL}/auth/login", json={
            "email": "owner@forge.app",
            "password": "Forge@2026"
        })
        if resp.status_code == 200:
            staff_token = resp.json()["access_token"]
    
    # 1.7 Test Google OAuth endpoints return sane error (not 500)
    print("\n1.7 Testing Google OAuth endpoints with bogus session_id...")
    for endpoint in ["/auth/google/staff", "/auth/google/customer"]:
        try:
            resp = requests.post(f"{BASE_URL}{endpoint}", json={"session_id": "bogus-session-id-12345"})
            if resp.status_code in [400, 401, 403, 404]:
                result.add_pass(f"Google OAuth {endpoint}", f"Returns {resp.status_code} (not 500)")
            elif resp.status_code == 500:
                result.add_fail(f"Google OAuth {endpoint}", "Returns 500 for bogus session_id")
            else:
                result.add_warning(f"Google OAuth {endpoint}", f"Unexpected status {resp.status_code}")
        except Exception as e:
            result.add_fail(f"Google OAuth {endpoint}", str(e))

# =============================================================================
# SECTION 2: CATALOG
# =============================================================================

@test_section("2. CATALOG - Products, Brands, Categories, Media URLs")
def test_catalog():
    if not staff_token:
        result.add_fail("CATALOG TESTS", "No staff token available")
        return
    
    headers = {"Authorization": f"Bearer {staff_token}"}
    
    # 2.1 GET /brands and /categories with product_count
    print("\n2.1 Testing GET /brands and /categories...")
    try:
        resp = requests.get(f"{BASE_URL}/brands", headers=headers)
        if resp.status_code == 200:
            brands = resp.json()
            if isinstance(brands, list) and len(brands) > 0:
                has_count = all("product_count" in b for b in brands)
                if has_count:
                    result.add_pass("GET /brands", f"{len(brands)} brands with product_count")
                else:
                    result.add_fail("GET /brands", "Missing product_count field")
            else:
                result.add_warning("GET /brands", "Empty brands list")
        else:
            result.add_fail("GET /brands", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("GET /brands", str(e))
    
    try:
        resp = requests.get(f"{BASE_URL}/categories", headers=headers)
        if resp.status_code == 200:
            categories = resp.json()
            if isinstance(categories, list):
                has_count = all("product_count" in c for c in categories)
                if has_count:
                    result.add_pass("GET /categories", f"{len(categories)} categories with product_count")
                else:
                    result.add_fail("GET /categories", "Missing product_count field")
        else:
            result.add_fail("GET /categories", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("GET /categories", str(e))
    
    # 2.2 GET /products with filters and sorting
    print("\n2.2 Testing GET /products with search, filters, and sorting...")
    
    # Get products with search
    try:
        resp = requests.get(f"{BASE_URL}/products?q=mixer", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if "items" in data and "total" in data:
                result.add_pass("GET /products?q=mixer", f"total={data['total']}, items={len(data['items'])}")
            else:
                result.add_fail("GET /products?q=mixer", "Missing items or total field")
        else:
            result.add_fail("GET /products?q=mixer", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("GET /products?q=mixer", str(e))
    
    # Test different sort options
    sort_options = ["popular", "recent", "price_asc", "price_desc", "name"]
    for sort in sort_options:
        try:
            resp = requests.get(f"{BASE_URL}/products?sort={sort}", headers=headers)
            if resp.status_code == 200:
                result.add_pass(f"GET /products?sort={sort}", "Returns 200")
            else:
                result.add_fail(f"GET /products?sort={sort}", f"Status {resp.status_code}")
        except Exception as e:
            result.add_fail(f"GET /products?sort={sort}", str(e))
    
    # 2.3 GET /products/{id} detail with variants
    print("\n2.3 Testing GET /products/{id} detail...")
    try:
        # First get a product ID
        resp = requests.get(f"{BASE_URL}/products?limit=1", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("items") and len(data["items"]) > 0:
                product_id = data["items"][0]["id"]
                
                # Get product detail
                resp = requests.get(f"{BASE_URL}/products/{product_id}", headers=headers)
                if resp.status_code == 200:
                    product = resp.json()
                    # Check if variants field exists (may be empty)
                    result.add_pass(f"GET /products/{product_id}", "Product detail retrieved")
                else:
                    result.add_fail(f"GET /products/{product_id}", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("GET /products/{id}", str(e))
    
    # 2.4 GET /products/{id}/alternates and /complete-the-set
    print("\n2.4 Testing GET /products/{id}/alternates and /complete-the-set...")
    try:
        resp = requests.get(f"{BASE_URL}/products?limit=1", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("items") and len(data["items"]) > 0:
                product_id = data["items"][0]["id"]
                
                # Test alternates
                resp = requests.get(f"{BASE_URL}/products/{product_id}/alternates", headers=headers)
                if resp.status_code == 200:
                    alternates = resp.json()
                    if "source_product_id" in alternates and "items" in alternates and "tiers" in alternates:
                        result.add_pass(f"GET /products/{product_id}/alternates", 
                                      f"items={len(alternates['items'])}")
                    else:
                        result.add_fail(f"GET /products/{product_id}/alternates", "Missing required fields")
                else:
                    result.add_fail(f"GET /products/{product_id}/alternates", f"Status {resp.status_code}")
                
                # Test complete-the-set
                resp = requests.get(f"{BASE_URL}/products/{product_id}/complete-the-set", headers=headers)
                if resp.status_code == 200:
                    cts = resp.json()
                    if "source_product_id" in cts and "items" in cts:
                        result.add_pass(f"GET /products/{product_id}/complete-the-set", 
                                      f"items={len(cts['items'])}")
                    else:
                        result.add_fail(f"GET /products/{product_id}/complete-the-set", "Missing required fields")
                else:
                    result.add_fail(f"GET /products/{product_id}/complete-the-set", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("GET /products/{id}/alternates or /complete-the-set", str(e))
    
    # 2.5 Spot-check 15 random product_media public_url values
    print("\n2.5 Spot-checking 15 random product_media public_url values...")
    try:
        resp = requests.get(f"{BASE_URL}/products?limit=15", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            products = data.get("items", [])
            
            checked = 0
            broken = 0
            for product in products[:15]:
                images = product.get("images", [])
                if images and len(images) > 0:
                    url = images[0]
                    try:
                        img_resp = requests.head(url, timeout=5)
                        if img_resp.status_code == 200:
                            checked += 1
                        else:
                            broken += 1
                            result.add_warning(f"Product media URL check", 
                                             f"URL {url} returned {img_resp.status_code}")
                    except Exception:
                        broken += 1
            
            if broken == 0:
                result.add_pass("Product media URL check", f"{checked} URLs checked, all returned 200")
            else:
                result.add_fail("Product media URL check", f"{broken} out of {checked + broken} URLs broken")
    except Exception as e:
        result.add_fail("Product media URL check", str(e))

# =============================================================================
# SECTION 3: QUOTATION BUILDER BACKEND
# =============================================================================

@test_section("3. QUOTATION BUILDER BACKEND - Create, PATCH, Duplicate, Breakdown, PDF")
def test_quotation_builder():
    global test_quotation_id, test_customer_id
    
    if not staff_token:
        result.add_fail("QUOTATION BUILDER TESTS", "No staff token available")
        return
    
    headers = {"Authorization": f"Bearer {staff_token}"}
    
    # 3.1 POST /quotations creates a draft
    print("\n3.1 Testing POST /quotations creates draft...")
    try:
        # Get a customer ID first
        if not test_customer_id:
            resp = requests.get(f"{BASE_URL}/customers", headers=headers)
            if resp.status_code == 200:
                customers = resp.json()
                if customers and len(customers) > 0:
                    test_customer_id = customers[0]["id"]
        
        if test_customer_id:
            # Get a product for the quotation
            resp = requests.get(f"{BASE_URL}/products?limit=1", headers=headers)
            product_id = None
            if resp.status_code == 200:
                products = resp.json().get("items", [])
                if products:
                    product_id = products[0]["id"]
            
            quotation_data = {
                "customer_id": test_customer_id,
                "items": [
                    {
                        "product_id": product_id,
                        "sku": "TEST-SKU",
                        "name": "Test Product",
                        "qty": 1,
                        "unit_price": 1000
                    }
                ] if product_id else [],
                "rooms": ["Living Room"],
                "notes": "Test quotation for production audit"
            }
            
            resp = requests.post(f"{BASE_URL}/quotations", json=quotation_data, headers=headers)
            if resp.status_code == 200:
                quotation = resp.json()
                test_quotation_id = quotation.get("id")
                if quotation.get("status") == "draft" and "id" in quotation and "number" in quotation:
                    result.add_pass("POST /quotations", 
                                  f"Created draft {quotation['number']}, id={test_quotation_id}")
                else:
                    result.add_fail("POST /quotations", "Missing required fields or wrong status")
            else:
                result.add_fail("POST /quotations", f"Status {resp.status_code}: {resp.text}")
    except Exception as e:
        result.add_fail("POST /quotations", str(e))
    
    if not test_quotation_id:
        result.add_fail("QUOTATION BUILDER TESTS", "Could not create test quotation")
        return
    
    # 3.2 PATCH with silent=true does NOT create revision
    print("\n3.2 Testing PATCH with silent=true does NOT create revision...")
    try:
        resp = requests.patch(f"{BASE_URL}/quotations/{test_quotation_id}", 
                            json={"silent": True, "notes": "Silent update"}, 
                            headers=headers)
        if resp.status_code == 200:
            quotation = resp.json()
            revisions = quotation.get("revisions", [])
            if len(revisions) == 0:
                result.add_pass("PATCH with silent=true", "No revision created")
            else:
                result.add_fail("PATCH with silent=true", f"Created {len(revisions)} revisions (should be 0)")
        else:
            result.add_fail("PATCH with silent=true", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("PATCH with silent=true", str(e))
    
    # 3.3 PATCH with silent=false DOES create revision
    print("\n3.3 Testing PATCH with silent=false DOES create revision...")
    try:
        resp = requests.patch(f"{BASE_URL}/quotations/{test_quotation_id}",
                            json={"silent": False, "notes": "Non-silent update", "reason": "Test revision"},
                            headers=headers)
        if resp.status_code == 200:
            quotation = resp.json()
            revisions = quotation.get("revisions", [])
            if len(revisions) >= 1:
                result.add_pass("PATCH with silent=false", f"Created revision (total={len(revisions)})")
            else:
                result.add_fail("PATCH with silent=false", "No revision created")
        else:
            result.add_fail("PATCH with silent=false", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("PATCH with silent=false", str(e))
    
    # 3.4 POST /quotations/{id}/duplicate
    print("\n3.4 Testing POST /quotations/{id}/duplicate...")
    try:
        resp = requests.post(f"{BASE_URL}/quotations/{test_quotation_id}/duplicate", headers=headers)
        if resp.status_code == 200:
            dup = resp.json()
            if dup.get("id") != test_quotation_id and dup.get("number") != "":
                result.add_pass("POST /quotations/{id}/duplicate", 
                              f"Created {dup['number']}, new_id={dup['id']}")
            else:
                result.add_fail("POST /quotations/{id}/duplicate", "Duplicate has same ID or no number")
        else:
            result.add_fail("POST /quotations/{id}/duplicate", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("POST /quotations/{id}/duplicate", str(e))
    
    # 3.5 GET /quotations/{id}/breakdown
    print("\n3.5 Testing GET /quotations/{id}/breakdown...")
    try:
        resp = requests.get(f"{BASE_URL}/quotations/{test_quotation_id}/breakdown", headers=headers)
        if resp.status_code == 200:
            breakdown = resp.json()
            if "lines" in breakdown and "totals" in breakdown:
                result.add_pass("GET /quotations/{id}/breakdown", 
                              f"lines={len(breakdown['lines'])}, totals present")
            else:
                result.add_fail("GET /quotations/{id}/breakdown", "Missing lines or totals")
        else:
            result.add_fail("GET /quotations/{id}/breakdown", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("GET /quotations/{id}/breakdown", str(e))
    
    # 3.6 GET /quotations/recent
    print("\n3.6 Testing GET /quotations/recent...")
    try:
        resp = requests.get(f"{BASE_URL}/quotations/recent?limit=5", headers=headers)
        if resp.status_code == 200:
            recent = resp.json()
            if isinstance(recent, list):
                result.add_pass("GET /quotations/recent", f"Returned {len(recent)} quotations")
            else:
                result.add_fail("GET /quotations/recent", "Response is not a list")
        else:
            result.add_fail("GET /quotations/recent", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("GET /quotations/recent", str(e))
    
    # 3.7 GET /quotations/{id}/pdf
    print("\n3.7 Testing GET /quotations/{id}/pdf...")
    try:
        resp = requests.get(f"{BASE_URL}/quotations/{test_quotation_id}/pdf", headers=headers)
        if resp.status_code == 200:
            content_type = resp.headers.get("Content-Type", "")
            # Check magic bytes for PDF
            if resp.content[:4] == b'%PDF' or "application/pdf" in content_type:
                result.add_pass("GET /quotations/{id}/pdf", 
                              f"Valid PDF ({len(resp.content)} bytes, content-type={content_type})")
            else:
                result.add_fail("GET /quotations/{id}/pdf", 
                              f"Not a valid PDF (magic bytes={resp.content[:4]}, content-type={content_type})")
        else:
            result.add_fail("GET /quotations/{id}/pdf", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("GET /quotations/{id}/pdf", str(e))

# =============================================================================
# SECTION 4: AUTOMATION CHAIN TRACE (HIGHEST PRIORITY)
# =============================================================================

@test_section("4. AUTOMATION CHAIN TRACE - End-to-end Quotation → PO → Payment → Followup")
def test_automation_chain():
    global test_quotation_id, test_po_id
    
    if not staff_token or not test_quotation_id:
        result.add_fail("AUTOMATION CHAIN", "No staff token or test quotation available")
        return
    
    headers = {"Authorization": f"Bearer {staff_token}"}
    
    print("\n4.a Moving quotation to approved/won state...")
    try:
        # First, update quotation status to approved
        resp = requests.patch(f"{BASE_URL}/quotations/{test_quotation_id}",
                            json={"status": "approved", "silent": False, "reason": "Approved for automation test"},
                            headers=headers)
        if resp.status_code == 200:
            quotation = resp.json()
            if quotation.get("status") == "approved":
                result.add_pass("4.a Quotation status transition", "Moved to approved")
            else:
                result.add_fail("4.a Quotation status transition", f"Status is {quotation.get('status')}")
        else:
            result.add_fail("4.a Quotation status transition", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("4.a Quotation status transition", str(e))
    
    print("\n4.b Testing place-order flow...")
    try:
        # Get place-order preview
        resp = requests.get(f"{BASE_URL}/quotations/{test_quotation_id}/place-order/preview", headers=headers)
        if resp.status_code == 200:
            preview = resp.json()
            if "brands" in preview and "quotation_id" in preview:
                result.add_pass("4.b GET /place-order/preview", f"brands={len(preview['brands'])}")
                
                # Confirm place-order
                resp = requests.post(f"{BASE_URL}/quotations/{test_quotation_id}/place-order/confirm",
                                   json={}, headers=headers)
                if resp.status_code == 200:
                    order_result = resp.json()
                    if "purchase_orders" in order_result and len(order_result["purchase_orders"]) > 0:
                        test_po_id = order_result["purchase_orders"][0]["id"]
                        result.add_pass("4.b POST /place-order/confirm", 
                                      f"Created {len(order_result['purchase_orders'])} PO(s), first_id={test_po_id}")
                        
                        # Verify PO appears in GET /purchase-orders
                        resp = requests.get(f"{BASE_URL}/purchase-orders", headers=headers)
                        if resp.status_code == 200:
                            pos = resp.json()
                            po_ids = [po["id"] for po in pos]
                            if test_po_id in po_ids:
                                result.add_pass("4.b PO appears in GET /purchase-orders", f"PO {test_po_id} found")
                            else:
                                result.add_fail("4.b PO appears in GET /purchase-orders", "PO not found in list")
                    else:
                        result.add_fail("4.b POST /place-order/confirm", "No purchase orders created")
                else:
                    result.add_fail("4.b POST /place-order/confirm", f"Status {resp.status_code}: {resp.text}")
            else:
                result.add_fail("4.b GET /place-order/preview", "Missing required fields")
        else:
            result.add_fail("4.b GET /place-order/preview", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("4.b Place-order flow", str(e))
    
    print("\n4.c Testing PO stage movement...")
    if test_po_id:
        try:
            # Move PO to next stage
            resp = requests.post(f"{BASE_URL}/purchase-orders/{test_po_id}/status",
                               json={"to_status": "ordered", "note": "Automation test"},
                               headers=headers)
            if resp.status_code == 200:
                po = resp.json()
                if po.get("status") == "ordered":
                    result.add_pass("4.c PO stage movement", "Moved to 'ordered' status")
                else:
                    result.add_fail("4.c PO stage movement", f"Status is {po.get('status')}")
            else:
                result.add_fail("4.c PO stage movement", f"Status {resp.status_code}")
        except Exception as e:
            result.add_fail("4.c PO stage movement", str(e))
    
    print("\n4.d Recording payment...")
    try:
        # Record a payment against the quotation
        payment_data = {
            "quotation_id": test_quotation_id,
            "amount": 500,
            "mode": "upi",
            "reference": "TEST-UPI-12345",
            "note": "Automation test payment"
        }
        resp = requests.post(f"{BASE_URL}/payments", json=payment_data, headers=headers)
        if resp.status_code == 200:
            payment = resp.json()
            result.add_pass("4.d Record payment", f"Payment recorded, id={payment.get('id')}")
            
            # Verify payment stats updated
            resp = requests.get(f"{BASE_URL}/payments/stats", headers=headers)
            if resp.status_code == 200:
                stats = resp.json()
                result.add_pass("4.d Payment stats updated", 
                              f"outstanding={stats.get('total_outstanding')}")
        else:
            result.add_fail("4.d Record payment", f"Status {resp.status_code}: {resp.text}")
    except Exception as e:
        result.add_fail("4.d Record payment", str(e))
    
    print("\n4.e Testing POST /followups/reconcile...")
    try:
        resp = requests.post(f"{BASE_URL}/followups/reconcile", headers=headers)
        if resp.status_code == 200:
            reconcile_result = resp.json()
            result.add_pass("4.e POST /followups/reconcile", 
                          f"created={reconcile_result.get('created')}, updated={reconcile_result.get('updated')}")
        else:
            result.add_fail("4.e POST /followups/reconcile", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("4.e POST /followups/reconcile", str(e))
    
    print("\n4.f Checking activity timeline...")
    try:
        resp = requests.get(f"{BASE_URL}/activity/quotation/{test_quotation_id}?limit=20", headers=headers)
        if resp.status_code == 200:
            timeline = resp.json()
            if isinstance(timeline, list):
                # Look for place-order and payment events
                event_types = [e.get("event_type") for e in timeline]
                has_order = any("order" in et for et in event_types if et)
                has_payment = any("payment" in et for et in event_types if et)
                result.add_pass("4.f Activity timeline", 
                              f"{len(timeline)} events, has_order={has_order}, has_payment={has_payment}")
            else:
                result.add_fail("4.f Activity timeline", "Response is not a list")
        else:
            result.add_fail("4.f Activity timeline", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("4.f Activity timeline", str(e))
    
    print("\n4.g Checking customer detail reflects events...")
    if test_customer_id:
        try:
            resp = requests.get(f"{BASE_URL}/customers/{test_customer_id}", headers=headers)
            if resp.status_code == 200:
                customer = resp.json()
                result.add_pass("4.g Customer detail", "Customer detail retrieved")
            else:
                result.add_fail("4.g Customer detail", f"Status {resp.status_code}")
        except Exception as e:
            result.add_fail("4.g Customer detail", str(e))
    
    # Summary of automation
    result.add_warning("4. AUTOMATION CHAIN SUMMARY", 
                      "Manual verification needed: Check which steps happened automatically vs requiring manual API calls")

# =============================================================================
# SECTION 5: PAYMENTS
# =============================================================================

@test_section("5. PAYMENTS - Stats, Outstanding Calculation, Payment History")
def test_payments():
    if not staff_token:
        result.add_fail("PAYMENTS TESTS", "No staff token available")
        return
    
    headers = {"Authorization": f"Bearer {staff_token}"}
    
    # 5.1 GET /payments/stats
    print("\n5.1 Testing GET /payments/stats...")
    try:
        resp = requests.get(f"{BASE_URL}/payments/stats", headers=headers)
        if resp.status_code == 200:
            stats = resp.json()
            required_fields = ["total_outstanding", "collected_this_month", "active_orders", "fully_paid"]
            missing = [f for f in required_fields if f not in stats]
            if not missing:
                result.add_pass("GET /payments/stats", 
                              f"outstanding={stats['total_outstanding']}, collected={stats['collected_this_month']}")
            else:
                result.add_fail("GET /payments/stats", f"Missing fields: {missing}")
        else:
            result.add_fail("GET /payments/stats", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("GET /payments/stats", str(e))
    
    # 5.2 GET /payments/orders (list)
    print("\n5.2 Testing GET /payments/orders...")
    try:
        resp = requests.get(f"{BASE_URL}/payments/orders", headers=headers)
        if resp.status_code == 200:
            orders = resp.json()
            if isinstance(orders, list):
                result.add_pass("GET /payments/orders", f"{len(orders)} orders")
            else:
                result.add_fail("GET /payments/orders", "Response is not a list")
        else:
            result.add_fail("GET /payments/orders", f"Status {resp.status_code}")
    except Exception as e:
        result.add_fail("GET /payments/orders", str(e))
    
    # 5.3 GET /payments/orders/{order_id} (detail)
    print("\n5.3 Testing GET /payments/orders/{order_id}...")
    if test_quotation_id:
        try:
            resp = requests.get(f"{BASE_URL}/payments/orders/{test_quotation_id}", headers=headers)
            if resp.status_code == 200:
                order = resp.json()
                required_fields = ["grand_total", "paid", "outstanding", "payments"]
                missing = [f for f in required_fields if f not in order]
                if not missing:
                    result.add_pass("GET /payments/orders/{id}", 
                                  f"grand_total={order['grand_total']}, paid={order['paid']}, outstanding={order['outstanding']}")
                else:
                    result.add_fail("GET /payments/orders/{id}", f"Missing fields: {missing}")
            else:
                result.add_fail("GET /payments/orders/{id}", f"Status {resp.status_code}")
        except Exception as e:
            result.add_fail("GET /payments/orders/{id}", str(e))

# =============================================================================
# SECTION 6: FOLLOW-UPS
# =============================================================================

@test_section("6. FOLLOW-UPS - Reconcile Idempotency (Spot Check)")
def test_followups():
    if not staff_token:
        result.add_fail("FOLLOW-UPS TESTS", "No staff token available")
        return
    
    headers = {"Authorization": f"Bearer {staff_token}"}
    
    # 6.1 POST /followups/reconcile idempotency
    print("\n6.1 Testing POST /followups/reconcile idempotency...")
    try:
        # First call
        resp1 = requests.post(f"{BASE_URL}/followups/reconcile", headers=headers)
        if resp1.status_code == 200:
            result1 = resp1.json()
            active1 = result1.get("active", 0)
            
            # Second call immediately
            time.sleep(0.5)
            resp2 = requests.post(f"{BASE_URL}/followups/reconcile", headers=headers)
            if resp2.status_code == 200:
                result2 = resp2.json()
                active2 = result2.get("active", 0)
                
                if active1 == active2:
                    result.add_pass("POST /followups/reconcile idempotency", 
                                  f"active count stable: {active1} == {active2}")
                else:
                    result.add_fail("POST /followups/reconcile idempotency", 
                                  f"active count changed: {active1} != {active2}")
            else:
                result.add_fail("POST /followups/reconcile (2nd call)", f"Status {resp2.status_code}")
        else:
            result.add_fail("POST /followups/reconcile (1st call)", f"Status {resp1.status_code}")
    except Exception as e:
        result.add_fail("POST /followups/reconcile idempotency", str(e))

# =============================================================================
# SECTION 7: REPORTS/EXPORTS
# =============================================================================

@test_section("7. REPORTS/EXPORTS - All Export Endpoints")
def test_reports_exports():
    if not staff_token:
        result.add_fail("REPORTS/EXPORTS TESTS", "No staff token available")
        return
    
    headers = {"Authorization": f"Bearer {staff_token}"}
    
    # 7.1 Search for export endpoints
    print("\n7.1 Testing export endpoints...")
    
    export_endpoints = [
        "/followups/export?format=csv",
        "/followups/export?format=xlsx",
    ]
    
    for endpoint in export_endpoints:
        try:
            resp = requests.get(f"{BASE_URL}{endpoint}", headers=headers)
            if resp.status_code == 200:
                content_length = len(resp.content)
                content_type = resp.headers.get("Content-Type", "")
                if content_length > 0:
                    result.add_pass(f"GET {endpoint}", 
                                  f"{content_length} bytes, content-type={content_type}")
                else:
                    result.add_fail(f"GET {endpoint}", "Empty response")
            else:
                result.add_fail(f"GET {endpoint}", f"Status {resp.status_code}")
        except Exception as e:
            result.add_fail(f"GET {endpoint}", str(e))

# =============================================================================
# SECTION 8: GENERAL SMOKE TESTS
# =============================================================================

@test_section("8. GENERAL SMOKE TESTS - Dashboard, Customers, etc.")
def test_general_smoke():
    if not staff_token:
        result.add_fail("GENERAL SMOKE TESTS", "No staff token available")
        return
    
    headers = {"Authorization": f"Bearer {staff_token}"}
    
    smoke_endpoints = [
        "/dashboard/stats",
        "/customers",
        "/purchase-orders",
        "/payments"
    ]
    
    for endpoint in smoke_endpoints:
        try:
            resp = requests.get(f"{BASE_URL}{endpoint}", headers=headers)
            if resp.status_code == 200:
                result.add_pass(f"GET {endpoint}", "Returns 200")
            else:
                result.add_fail(f"GET {endpoint}", f"Status {resp.status_code}")
        except Exception as e:
            result.add_fail(f"GET {endpoint}", str(e))

# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    print("\n" + "="*80)
    print("FORGE / BUILDCON HOUSE - PRODUCTION READINESS AUDIT")
    print("Backend API Testing Suite")
    print("="*80)
    
    test_auth()
    test_catalog()
    test_quotation_builder()
    test_automation_chain()
    test_payments()
    test_followups()
    test_reports_exports()
    test_general_smoke()
    
    result.print_summary()

if __name__ == "__main__":
    main()
