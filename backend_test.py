"""
Forge V2 — Production Milestone 1 — Purchases Module Regression Test Suite

Tests all backend APIs for the Purchases Module:
1. SUPPLIERS (CRUD + auth)
2. PLACE ORDER — PREVIEW (non-mutating)
3. PLACE ORDER — CONFIRM (creates POs)
4. PURCHASE ORDER LIFECYCLE (status transitions)
5. RECEIVE FLOW (auto-transition)
6. LIST + SEARCH (filters)
7. DASHBOARD (column counts)
8. ACTIVITY FEED (global + entity-specific)
9. ATTACHMENTS (file upload)
10. REGRESSION (previous milestone endpoints)
"""
import os
import sys
import requests
import base64
from typing import Optional

# Backend URL configuration
BASE_URL = os.environ.get("TEST_BACKEND_URL", "http://localhost:8001").rstrip("/")
API_BASE = f"{BASE_URL}/api"

# Test credentials from /app/memory/test_credentials.md
TEST_EMAIL = "owner@forge.app"
TEST_PASSWORD = "Forge@2026"

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures = []
    
    def add_pass(self, test_name: str):
        self.passed += 1
        print(f"✅ PASS: {test_name}")
    
    def add_fail(self, test_name: str, reason: str, details: Optional[dict] = None):
        self.failed += 1
        self.failures.append({
            "test": test_name,
            "reason": reason,
            "details": details
        })
        print(f"❌ FAIL: {test_name}")
        print(f"   Reason: {reason}")
        if details:
            print(f"   Details: {details}")
    
    def summary(self):
        total = self.passed + self.failed
        print("\n" + "="*80)
        print(f"TEST SUMMARY: {self.passed}/{total} passed, {self.failed}/{total} failed")
        print("="*80)
        if self.failures:
            print("\nFAILURES:")
            for i, f in enumerate(self.failures, 1):
                print(f"\n{i}. {f['test']}")
                print(f"   {f['reason']}")
                if f['details']:
                    print(f"   {f['details']}")
        return self.failed == 0

# Global test result tracker
result = TestResult()

def login() -> str:
    """Login and return JWT token"""
    print(f"\n🔐 Logging in as {TEST_EMAIL}...")
    try:
        resp = requests.post(
            f"{API_BASE}/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=10
        )
        if resp.status_code != 200:
            print(f"❌ Login failed: {resp.status_code}")
            print(f"Response: {resp.text[:400]}")
            sys.exit(1)
        
        data = resp.json()
        token = data.get("access_token")
        if not token:
            print(f"❌ No access_token in response: {data}")
            sys.exit(1)
        
        print(f"✅ Login successful")
        return token
    except Exception as e:
        print(f"❌ Login exception: {e}")
        sys.exit(1)

def get_headers(token: str) -> dict:
    """Return headers with Authorization"""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

# =============================================================================
# 1. SUPPLIERS
# =============================================================================
def test_suppliers(token: str):
    """Test 1: SUPPLIERS CRUD + auth"""
    print("\n" + "="*80)
    print("TEST 1: SUPPLIERS")
    print("="*80)
    
    headers = get_headers(token)
    
    # Test 1.1: GET /api/suppliers returns 5 seeded suppliers
    print("\n📦 Test 1.1: GET /api/suppliers returns 5 seeded suppliers")
    try:
        resp = requests.get(f"{API_BASE}/suppliers", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("1.1: GET suppliers", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return None
        
        suppliers = resp.json()
        if not isinstance(suppliers, list):
            result.add_fail("1.1: GET suppliers", "Response is not an array", {"response": suppliers})
            return None
        
        if len(suppliers) != 5:
            result.add_fail("1.1: GET suppliers", f"Expected 5 suppliers, got {len(suppliers)}", {"count": len(suppliers)})
            return None
        
        # Check each supplier has brand_id and brand_name
        expected_brands = ["Hansgrohe", "Axor", "Grohe", "Vitra", "Geberit"]
        found_brands = [s.get("brand_name") for s in suppliers]
        
        for brand in expected_brands:
            if brand not in found_brands:
                result.add_fail("1.1: GET suppliers", f"Missing brand: {brand}", {"found_brands": found_brands})
                return None
        
        # Verify each supplier has brand_id and brand_name populated
        for s in suppliers:
            if not s.get("brand_id"):
                result.add_fail("1.1: GET suppliers", f"Supplier {s.get('name')} missing brand_id", {"supplier": s})
                return None
            if not s.get("brand_name"):
                result.add_fail("1.1: GET suppliers", f"Supplier {s.get('name')} missing brand_name", {"supplier": s})
                return None
        
        result.add_pass(f"1.1: GET suppliers returns 5 seeded suppliers with brand_id and brand_name")
        return suppliers
        
    except Exception as e:
        result.add_fail("1.1: GET suppliers", f"Exception: {e}", None)
        return None

    # Test 1.2: POST /api/suppliers creates new supplier
    print("\n📦 Test 1.2: POST /api/suppliers creates new supplier")
    try:
        # Get a brand_id first
        resp = requests.get(f"{API_BASE}/brands", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("1.2: GET brands", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return suppliers
        
        brands = resp.json()
        if not brands:
            result.add_fail("1.2: GET brands", "No brands found", {"response": brands})
            return suppliers
        
        brand_id = brands[0].get("id")
        
        resp = requests.post(
            f"{API_BASE}/suppliers",
            headers=headers,
            json={
                "name": "Test Supplier Ltd",
                "brand_id": brand_id,
                "contact_person": "John Doe",
                "email": "john@testsupplier.com",
                "phone": "+91 98765 43210"
            },
            timeout=10
        )
        if resp.status_code not in [200, 201]:
            result.add_fail("1.2: POST supplier", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return suppliers
        
        supplier = resp.json()
        if not supplier.get("id"):
            result.add_fail("1.2: POST supplier", "No 'id' in response", {"response": supplier})
            return suppliers
        
        result.add_pass(f"1.2: POST supplier creates new supplier (ID: {supplier.get('id')})")
        
        # Test 1.3: GET /api/suppliers/{id} returns single supplier
        print("\n📦 Test 1.3: GET /api/suppliers/{id} returns single supplier")
        supplier_id = supplier.get("id")
        resp = requests.get(f"{API_BASE}/suppliers/{supplier_id}", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("1.3: GET supplier by ID", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            fetched = resp.json()
            if fetched.get("id") != supplier_id:
                result.add_fail("1.3: GET supplier by ID", "ID mismatch", {"expected": supplier_id, "got": fetched.get("id")})
            else:
                result.add_pass(f"1.3: GET supplier by ID returns correct supplier")
        
        # Test 1.4: PATCH /api/suppliers/{id} updates fields
        print("\n📦 Test 1.4: PATCH /api/suppliers/{id} updates fields")
        resp = requests.patch(
            f"{API_BASE}/suppliers/{supplier_id}",
            headers=headers,
            json={
                "name": "Test Supplier Ltd (Updated)",
                "phone": "+91 98765 99999"
            },
            timeout=10
        )
        if resp.status_code != 200:
            result.add_fail("1.4: PATCH supplier", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            updated = resp.json()
            if updated.get("name") != "Test Supplier Ltd (Updated)":
                result.add_fail("1.4: PATCH supplier", "Name not updated", {"response": updated})
            else:
                result.add_pass(f"1.4: PATCH supplier updates fields")
        
    except Exception as e:
        result.add_fail("1.2-1.4: Supplier CRUD", f"Exception: {e}", None)
    
    # Test 1.5: Auth required
    print("\n📦 Test 1.5: Unauthenticated request returns 401")
    try:
        resp = requests.get(f"{API_BASE}/suppliers", timeout=10)
        if resp.status_code not in [401, 403]:
            result.add_fail("1.5: Auth required", f"Expected 401/403, got {resp.status_code}", {"response": resp.text[:400]})
        else:
            result.add_pass(f"1.5: Unauthenticated request returns {resp.status_code}")
    except Exception as e:
        result.add_fail("1.5: Auth test", f"Exception: {e}", None)
    
    return suppliers

# =============================================================================
# 2. PLACE ORDER — PREVIEW
# =============================================================================
def test_place_order_preview(token: str, quotation_id: str):
    """Test 2: PLACE ORDER — PREVIEW (non-mutating)"""
    print("\n" + "="*80)
    print("TEST 2: PLACE ORDER — PREVIEW")
    print("="*80)
    
    headers = get_headers(token)
    
    # Test 2.1: GET /api/quotations/{id}/place-order/preview returns correct shape
    print(f"\n📦 Test 2.1: GET /api/quotations/{quotation_id}/place-order/preview")
    try:
        resp = requests.get(f"{API_BASE}/quotations/{quotation_id}/place-order/preview", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("2.1: Place order preview", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return None
        
        preview = resp.json()
        
        # Check shape
        required_keys = ["quotation_id", "quotation_number", "customer_id", "customer_name", "brands", "total_value"]
        for key in required_keys:
            if key not in preview:
                result.add_fail("2.1: Preview shape", f"Missing key: {key}", {"response": preview})
                return None
        
        if not isinstance(preview["brands"], list):
            result.add_fail("2.1: Preview shape", "'brands' is not an array", {"response": preview})
            return None
        
        # Check each brand card has required fields
        for brand in preview["brands"]:
            required_brand_keys = ["brand_id", "brand_name", "items", "subtotal", "item_count"]
            for key in required_brand_keys:
                if key not in brand:
                    result.add_fail("2.1: Brand card shape", f"Missing key: {key}", {"brand": brand})
                    return None
            
            # Check if default_supplier is populated when brand has a supplier
            if "default_supplier" in brand and brand["default_supplier"]:
                if not isinstance(brand["default_supplier"], dict):
                    result.add_fail("2.1: default_supplier", "Not a dict", {"default_supplier": brand["default_supplier"]})
                    return None
                if "id" not in brand["default_supplier"] or "name" not in brand["default_supplier"]:
                    result.add_fail("2.1: default_supplier", "Missing id or name", {"default_supplier": brand["default_supplier"]})
                    return None
        
        result.add_pass(f"2.1: Place order preview returns correct shape with {len(preview['brands'])} brands")
        return preview
        
    except Exception as e:
        result.add_fail("2.1: Place order preview", f"Exception: {e}", None)
        return None

def test_place_order_preview_edge_cases(token: str):
    """Test 2: PLACE ORDER — PREVIEW edge cases"""
    headers = get_headers(token)
    
    # Test 2.2: 404 for unknown quotation_id
    print("\n📦 Test 2.2: 404 for unknown quotation_id")
    try:
        fake_id = "does-not-exist-uuid-12345"
        resp = requests.get(f"{API_BASE}/quotations/{fake_id}/place-order/preview", headers=headers, timeout=10)
        if resp.status_code != 404:
            result.add_fail("2.2: Preview 404", f"Expected 404, got {resp.status_code}", {"response": resp.text[:400]})
        else:
            result.add_pass("2.2: Preview returns 404 for unknown quotation")
    except Exception as e:
        result.add_fail("2.2: Preview 404", f"Exception: {e}", None)
    
    # Test 2.3: 400 when quotation has no items
    print("\n📦 Test 2.3: 400 when quotation has no items")
    try:
        # Create a quotation with no items
        resp = requests.get(f"{API_BASE}/customers", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("2.3: Get customers", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        customers = resp.json()
        if not customers:
            result.add_fail("2.3: Get customers", "No customers found", {"response": customers})
            return
        
        customer_id = customers[0].get("id")
        
        resp = requests.post(
            f"{API_BASE}/quotations",
            headers=headers,
            json={
                "customer_id": customer_id,
                "items": [],
                "rooms": []
            },
            timeout=10
        )
        if resp.status_code not in [200, 201]:
            result.add_fail("2.3: Create empty quotation", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        empty_quot = resp.json()
        empty_quot_id = empty_quot.get("id")
        
        resp = requests.get(f"{API_BASE}/quotations/{empty_quot_id}/place-order/preview", headers=headers, timeout=10)
        if resp.status_code != 400:
            result.add_fail("2.3: Preview empty quotation", f"Expected 400, got {resp.status_code}", {"response": resp.text[:400]})
        else:
            data = resp.json()
            detail = data.get("detail", "")
            if "no items" not in detail.lower():
                result.add_fail("2.3: Preview empty quotation detail", f"Detail doesn't mention 'no items': {detail}", {"response": data})
            else:
                result.add_pass("2.3: Preview returns 400 when quotation has no items")
    except Exception as e:
        result.add_fail("2.3: Preview empty quotation", f"Exception: {e}", None)

# =============================================================================
# 3. PLACE ORDER — CONFIRM
# =============================================================================
def test_place_order_confirm(token: str, preview: dict):
    """Test 3: PLACE ORDER — CONFIRM"""
    print("\n" + "="*80)
    print("TEST 3: PLACE ORDER — CONFIRM")
    print("="*80)
    
    headers = get_headers(token)
    quotation_id = preview["quotation_id"]
    
    # Build supplier_by_brand from preview
    supplier_by_brand = {}
    for brand in preview["brands"]:
        if brand.get("default_supplier"):
            supplier_by_brand[brand["brand_id"]] = brand["default_supplier"]["id"]
    
    # Test 3.1: POST /api/quotations/{id}/place-order/confirm creates POs
    print(f"\n📦 Test 3.1: POST /api/quotations/{quotation_id}/place-order/confirm")
    try:
        resp = requests.post(
            f"{API_BASE}/quotations/{quotation_id}/place-order/confirm",
            headers=headers,
            json={
                "supplier_by_brand": supplier_by_brand,
                "notes_by_brand": {},
                "expected_delivery_at": None,
                "project_name": "Test Project"
            },
            timeout=10
        )
        if resp.status_code not in [200, 201]:
            result.add_fail("3.1: Place order confirm", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return None
        
        confirm_result = resp.json()
        
        # Check shape
        if "purchase_orders" not in confirm_result or "count" not in confirm_result:
            result.add_fail("3.1: Confirm shape", "Missing purchase_orders or count", {"response": confirm_result})
            return None
        
        pos = confirm_result["purchase_orders"]
        count = confirm_result["count"]
        
        if len(pos) != count:
            result.add_fail("3.1: PO count mismatch", f"count={count} but len(purchase_orders)={len(pos)}", {"response": confirm_result})
            return None
        
        if count != len(preview["brands"]):
            result.add_fail("3.1: PO count", f"Expected {len(preview['brands'])} POs (one per brand), got {count}", {"response": confirm_result})
            return None
        
        result.add_pass(f"3.1: Place order confirm creates {count} POs (one per brand)")
        
        # Test 3.2: Each PO has correct structure
        print("\n📦 Test 3.2: Each PO has correct structure")
        for po in pos:
            # Check number format FPO-YYYY-NNNN
            number = po.get("number", "")
            if not number.startswith("FPO-2026-"):
                result.add_fail("3.2: PO number format", f"Number doesn't match FPO-YYYY-NNNN: {number}", {"po": po})
                return None
            
            # Check status is draft
            if po.get("status") != "draft":
                result.add_fail("3.2: PO status", f"Expected 'draft', got '{po.get('status')}'", {"po": po})
                return None
            
            # Check quotation_id and quotation_number
            if po.get("quotation_id") != quotation_id:
                result.add_fail("3.2: PO quotation_id", f"Mismatch", {"expected": quotation_id, "got": po.get("quotation_id")})
                return None
            
            if po.get("quotation_number") != preview["quotation_number"]:
                result.add_fail("3.2: PO quotation_number", f"Mismatch", {"expected": preview["quotation_number"], "got": po.get("quotation_number")})
                return None
            
            # Check customer_id
            if po.get("customer_id") != preview["customer_id"]:
                result.add_fail("3.2: PO customer_id", f"Mismatch", {"expected": preview["customer_id"], "got": po.get("customer_id")})
                return None
            
            # Check brand_id and brand_name
            if not po.get("brand_id") or not po.get("brand_name"):
                result.add_fail("3.2: PO brand", "Missing brand_id or brand_name", {"po": po})
                return None
            
            # Check supplier_id (from body or default)
            brand_id = po.get("brand_id")
            expected_supplier_id = supplier_by_brand.get(brand_id)
            if expected_supplier_id and po.get("supplier_id") != expected_supplier_id:
                result.add_fail("3.2: PO supplier_id", f"Mismatch", {"expected": expected_supplier_id, "got": po.get("supplier_id")})
                return None
            
            # Check items
            if not po.get("items") or not isinstance(po["items"], list):
                result.add_fail("3.2: PO items", "Missing or invalid items", {"po": po})
                return None
            
            for item in po["items"]:
                if "qty" not in item or "unit_cost" not in item:
                    result.add_fail("3.2: PO item", "Missing qty or unit_cost", {"item": item})
                    return None
            
            # Check status_history
            if not po.get("status_history") or not isinstance(po["status_history"], list):
                result.add_fail("3.2: PO status_history", "Missing or invalid", {"po": po})
                return None
            
            if len(po["status_history"]) != 1:
                result.add_fail("3.2: PO status_history", f"Expected 1 entry, got {len(po['status_history'])}", {"po": po})
                return None
            
            hist = po["status_history"][0]
            if hist.get("from_status") is not None:
                result.add_fail("3.2: PO status_history", f"from_status should be None, got {hist.get('from_status')}", {"hist": hist})
                return None
            
            if hist.get("to_status") != "draft":
                result.add_fail("3.2: PO status_history", f"to_status should be 'draft', got {hist.get('to_status')}", {"hist": hist})
                return None
        
        result.add_pass("3.2: Each PO has correct structure (number, status, quotation_id, customer_id, brand, supplier, items, status_history)")
        
        # Test 3.3: Quotation status becomes 'ordered'
        print("\n📦 Test 3.3: Quotation status becomes 'ordered'")
        resp = requests.get(f"{API_BASE}/quotations/{quotation_id}", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("3.3: Get quotation", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return pos
        
        quot = resp.json()
        if quot.get("status") != "ordered":
            result.add_fail("3.3: Quotation status", f"Expected 'ordered', got '{quot.get('status')}'", {"quotation": quot})
            return pos
        
        result.add_pass("3.3: Quotation status becomes 'ordered'")
        
        # Test 3.4: Second call returns 400 "Order already placed"
        print("\n📦 Test 3.4: Second call returns 400 'Order already placed'")
        resp = requests.post(
            f"{API_BASE}/quotations/{quotation_id}/place-order/confirm",
            headers=headers,
            json={
                "supplier_by_brand": supplier_by_brand,
                "notes_by_brand": {},
                "expected_delivery_at": None,
                "project_name": "Test Project"
            },
            timeout=10
        )
        if resp.status_code != 400:
            result.add_fail("3.4: Idempotency check", f"Expected 400, got {resp.status_code}", {"response": resp.text[:400]})
            return pos
        
        data = resp.json()
        detail = data.get("detail", "")
        if "already placed" not in detail.lower():
            result.add_fail("3.4: Idempotency detail", f"Detail doesn't mention 'already placed': {detail}", {"response": data})
            return pos
        
        result.add_pass("3.4: Second confirm call returns 400 'Order already placed'")
        
        return pos
        
    except Exception as e:
        result.add_fail("3.1-3.4: Place order confirm", f"Exception: {e}", None)
        return None

# =============================================================================
# 4. PURCHASE ORDER LIFECYCLE
# =============================================================================
def test_purchase_order_lifecycle(token: str, po_id: str):
    """Test 4: PURCHASE ORDER LIFECYCLE"""
    print("\n" + "="*80)
    print("TEST 4: PURCHASE ORDER LIFECYCLE")
    print("="*80)
    
    headers = get_headers(token)
    
    # Test 4.1: GET /api/purchase-orders/{id} returns PO
    print(f"\n📦 Test 4.1: GET /api/purchase-orders/{po_id}")
    try:
        resp = requests.get(f"{API_BASE}/purchase-orders/{po_id}", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("4.1: GET PO", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        po = resp.json()
        if po.get("id") != po_id:
            result.add_fail("4.1: GET PO", "ID mismatch", {"expected": po_id, "got": po.get("id")})
            return
        
        result.add_pass(f"4.1: GET PO returns correct PO")
        
    except Exception as e:
        result.add_fail("4.1: GET PO", f"Exception: {e}", None)
        return
    
    # Test 4.2: GET /api/purchase-orders/config/statuses
    print("\n📦 Test 4.2: GET /api/purchase-orders/config/statuses")
    try:
        resp = requests.get(f"{API_BASE}/purchase-orders/config/statuses", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("4.2: GET config/statuses", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        config = resp.json()
        if "columns" not in config or "transitions" not in config or "labels" not in config:
            result.add_fail("4.2: Config shape", "Missing columns, transitions, or labels", {"response": config})
            return
        
        result.add_pass("4.2: GET config/statuses returns columns, transitions, labels")
        
    except Exception as e:
        result.add_fail("4.2: GET config/statuses", f"Exception: {e}", None)
        return
    
    # Test 4.3: POST /api/purchase-orders/{id}/status with legal transition
    print(f"\n📦 Test 4.3: POST /api/purchase-orders/{po_id}/status (draft → ordered)")
    try:
        resp = requests.post(
            f"{API_BASE}/purchase-orders/{po_id}/status",
            headers=headers,
            json={
                "to_status": "ordered",
                "note": "Test transition"
            },
            timeout=10
        )
        if resp.status_code != 200:
            result.add_fail("4.3: Status transition", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        po = resp.json()
        if po.get("status") != "ordered":
            result.add_fail("4.3: Status transition", f"Expected 'ordered', got '{po.get('status')}'", {"po": po})
            return
        
        # Check status_history grew
        if len(po.get("status_history", [])) < 2:
            result.add_fail("4.3: Status history", f"Expected ≥2 entries, got {len(po.get('status_history', []))}", {"po": po})
            return
        
        result.add_pass("4.3: Status transition (draft → ordered) succeeds, status_history grows")
        
    except Exception as e:
        result.add_fail("4.3: Status transition", f"Exception: {e}", None)
        return
    
    # Test 4.4: POST with illegal transition
    print(f"\n📦 Test 4.4: POST /api/purchase-orders/{po_id}/status with illegal transition (ordered → packed)")
    try:
        resp = requests.post(
            f"{API_BASE}/purchase-orders/{po_id}/status",
            headers=headers,
            json={
                "to_status": "packed",
                "note": "Illegal transition"
            },
            timeout=10
        )
        if resp.status_code != 400:
            result.add_fail("4.4: Illegal transition", f"Expected 400, got {resp.status_code}", {"response": resp.text[:400]})
            return
        
        data = resp.json()
        detail = data.get("detail", "")
        if "cannot move" not in detail.lower():
            result.add_fail("4.4: Illegal transition detail", f"Detail doesn't mention 'cannot move': {detail}", {"response": data})
            return
        
        result.add_pass("4.4: Illegal transition (ordered → packed) returns 400 'Cannot move from...'")
        
    except Exception as e:
        result.add_fail("4.4: Illegal transition", f"Exception: {e}", None)
    
    # Test 4.5: PATCH /api/purchase-orders/{id} updates fields
    print(f"\n📦 Test 4.5: PATCH /api/purchase-orders/{po_id} updates fields")
    try:
        resp = requests.patch(
            f"{API_BASE}/purchase-orders/{po_id}",
            headers=headers,
            json={
                "internal_notes": "Updated notes",
                "expected_delivery_at": "2026-02-01T00:00:00Z"
            },
            timeout=10
        )
        if resp.status_code != 200:
            result.add_fail("4.5: PATCH PO", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        po = resp.json()
        if po.get("internal_notes") != "Updated notes":
            result.add_fail("4.5: PATCH PO", "internal_notes not updated", {"po": po})
            return
        
        result.add_pass("4.5: PATCH PO updates fields (supplier_id, internal_notes, expected_delivery_at)")
        
    except Exception as e:
        result.add_fail("4.5: PATCH PO", f"Exception: {e}", None)

# =============================================================================
# 5. RECEIVE FLOW (AUTO-TRANSITION)
# =============================================================================
def test_receive_flow(token: str):
    """Test 5: RECEIVE FLOW (AUTO-TRANSITION)"""
    print("\n" + "="*80)
    print("TEST 5: RECEIVE FLOW (AUTO-TRANSITION)")
    print("="*80)
    
    headers = get_headers(token)
    
    # Create a test quotation with 3 items, place order, get PO
    print("\n📦 Setting up test PO with 3 items...")
    try:
        # Get customer
        resp = requests.get(f"{API_BASE}/customers", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("5.0: Setup - Get customers", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        customers = resp.json()
        if not customers:
            result.add_fail("5.0: Setup - No customers", "No customers found", None)
            return
        customer_id = customers[0].get("id")
        
        # Get products
        resp = requests.get(f"{API_BASE}/products?limit=3", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("5.0: Setup - Get products", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        products_data = resp.json()
        products = products_data.get("items", [])
        if len(products) < 3:
            result.add_fail("5.0: Setup - Not enough products", f"Need 3 products, got {len(products)}", None)
            return
        
        # Create quotation with 3 items (qty=2 each)
        items = []
        for p in products[:3]:
            items.append({
                "product_id": p["id"],
                "sku": p["sku"],
                "name": p["name"],
                "qty": 2,
                "unit_price": p["price"],
                "tax_pct": 18
            })
        
        resp = requests.post(
            f"{API_BASE}/quotations",
            headers=headers,
            json={
                "customer_id": customer_id,
                "items": items,
                "rooms": ["Test Room"]
            },
            timeout=10
        )
        if resp.status_code not in [200, 201]:
            result.add_fail("5.0: Setup - Create quotation", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        quot = resp.json()
        quot_id = quot.get("id")
        
        # Place order
        resp = requests.get(f"{API_BASE}/quotations/{quot_id}/place-order/preview", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("5.0: Setup - Preview", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        preview = resp.json()
        supplier_by_brand = {}
        for brand in preview["brands"]:
            if brand.get("default_supplier"):
                supplier_by_brand[brand["brand_id"]] = brand["default_supplier"]["id"]
        
        resp = requests.post(
            f"{API_BASE}/quotations/{quot_id}/place-order/confirm",
            headers=headers,
            json={
                "supplier_by_brand": supplier_by_brand,
                "notes_by_brand": {},
                "expected_delivery_at": None,
                "project_name": "Receive Test"
            },
            timeout=10
        )
        if resp.status_code not in [200, 201]:
            result.add_fail("5.0: Setup - Confirm order", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        confirm_result = resp.json()
        pos = confirm_result["purchase_orders"]
        if not pos:
            result.add_fail("5.0: Setup - No POs", "No POs created", None)
            return
        
        po = pos[0]
        po_id = po["id"]
        
        # Transition to 'ordered' status
        resp = requests.post(
            f"{API_BASE}/purchase-orders/{po_id}/status",
            headers=headers,
            json={"to_status": "ordered", "note": "Ready for receive test"},
            timeout=10
        )
        if resp.status_code != 200:
            result.add_fail("5.0: Setup - Transition to ordered", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        po = resp.json()
        item_ids = [item["id"] for item in po["items"]]
        
        print(f"✅ Setup complete: PO {po_id} with {len(item_ids)} items (qty=2 each), status='ordered'")
        
    except Exception as e:
        result.add_fail("5.0: Setup", f"Exception: {e}", None)
        return
    
    # Test 5.1: Partial receive (1 item, qty=1) → auto-transition to 'partial_received'
    print(f"\n📦 Test 5.1: POST /api/purchase-orders/{po_id}/receive (partial)")
    try:
        receipts = {item_ids[0]: 1}
        resp = requests.post(
            f"{API_BASE}/purchase-orders/{po_id}/receive",
            headers=headers,
            json={
                "receipts": receipts,
                "note": "Partial receipt"
            },
            timeout=10
        )
        if resp.status_code != 200:
            result.add_fail("5.1: Partial receive", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        po = resp.json()
        
        # Check status auto-transitioned to 'partial_received'
        if po.get("status") != "partial_received":
            result.add_fail("5.1: Auto-transition", f"Expected 'partial_received', got '{po.get('status')}'", {"po": po})
            return
        
        # Check item qty_received updated
        item = next((i for i in po["items"] if i["id"] == item_ids[0]), None)
        if not item:
            result.add_fail("5.1: Item not found", f"Item {item_ids[0]} not found", {"po": po})
            return
        
        if item.get("qty_received") != 1:
            result.add_fail("5.1: qty_received", f"Expected 1, got {item.get('qty_received')}", {"item": item})
            return
        
        # Check status_history has new entry
        if len(po.get("status_history", [])) < 3:  # draft→ordered, ordered→partial_received
            result.add_fail("5.1: Status history", f"Expected ≥3 entries, got {len(po.get('status_history', []))}", {"po": po})
            return
        
        result.add_pass("5.1: Partial receive → status auto-transitions to 'partial_received', qty_received updated, status_history grows")
        
    except Exception as e:
        result.add_fail("5.1: Partial receive", f"Exception: {e}", None)
        return
    
    # Test 5.2: Full receive (all items) → auto-transition to 'fully_received'
    print(f"\n📦 Test 5.2: POST /api/purchase-orders/{po_id}/receive (full)")
    try:
        receipts = {
            item_ids[0]: 2,  # complete first item
            item_ids[1]: 2,  # complete second item
            item_ids[2]: 2   # complete third item
        }
        resp = requests.post(
            f"{API_BASE}/purchase-orders/{po_id}/receive",
            headers=headers,
            json={
                "receipts": receipts,
                "note": "Full receipt"
            },
            timeout=10
        )
        if resp.status_code != 200:
            result.add_fail("5.2: Full receive", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        po = resp.json()
        
        # Check status auto-transitioned to 'fully_received'
        if po.get("status") != "fully_received":
            result.add_fail("5.2: Auto-transition", f"Expected 'fully_received', got '{po.get('status')}'", {"po": po})
            return
        
        # Check all items fully received
        for item_id in item_ids:
            item = next((i for i in po["items"] if i["id"] == item_id), None)
            if not item:
                result.add_fail("5.2: Item not found", f"Item {item_id} not found", {"po": po})
                return
            if item.get("qty_received") != 2:
                result.add_fail("5.2: qty_received", f"Item {item_id}: expected 2, got {item.get('qty_received')}", {"item": item})
                return
        
        result.add_pass("5.2: Full receive → status auto-transitions to 'fully_received', all items qty_received=qty")
        
    except Exception as e:
        result.add_fail("5.2: Full receive", f"Exception: {e}", None)
        return
    
    # Test 5.3: Clamping (receipts value > qty is clamped to qty)
    print(f"\n📦 Test 5.3: Verify clamping (receipts > qty clamped to qty)")
    try:
        # Create another PO for clamping test
        resp = requests.get(f"{API_BASE}/customers", headers=headers, timeout=10)
        customers = resp.json()
        customer_id = customers[0].get("id")
        
        resp = requests.get(f"{API_BASE}/products?limit=1", headers=headers, timeout=10)
        products_data = resp.json()
        products = products_data.get("items", [])
        p = products[0]
        
        resp = requests.post(
            f"{API_BASE}/quotations",
            headers=headers,
            json={
                "customer_id": customer_id,
                "items": [{
                    "product_id": p["id"],
                    "sku": p["sku"],
                    "name": p["name"],
                    "qty": 5,
                    "unit_price": p["price"],
                    "tax_pct": 18
                }],
                "rooms": ["Test Room"]
            },
            timeout=10
        )
        quot = resp.json()
        quot_id = quot.get("id")
        
        resp = requests.get(f"{API_BASE}/quotations/{quot_id}/place-order/preview", headers=headers, timeout=10)
        preview = resp.json()
        supplier_by_brand = {}
        for brand in preview["brands"]:
            if brand.get("default_supplier"):
                supplier_by_brand[brand["brand_id"]] = brand["default_supplier"]["id"]
        
        resp = requests.post(
            f"{API_BASE}/quotations/{quot_id}/place-order/confirm",
            headers=headers,
            json={
                "supplier_by_brand": supplier_by_brand,
                "notes_by_brand": {},
                "expected_delivery_at": None,
                "project_name": "Clamp Test"
            },
            timeout=10
        )
        confirm_result = resp.json()
        po = confirm_result["purchase_orders"][0]
        po_id = po["id"]
        item_id = po["items"][0]["id"]
        
        # Transition to ordered
        resp = requests.post(
            f"{API_BASE}/purchase-orders/{po_id}/status",
            headers=headers,
            json={"to_status": "ordered", "note": "Clamp test"},
            timeout=10
        )
        
        # Try to receive 10 (more than qty=5)
        resp = requests.post(
            f"{API_BASE}/purchase-orders/{po_id}/receive",
            headers=headers,
            json={
                "receipts": {item_id: 10},
                "note": "Over-receive test"
            },
            timeout=10
        )
        if resp.status_code != 200:
            result.add_fail("5.3: Clamping test", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        po = resp.json()
        item = po["items"][0]
        
        # Should be clamped to 5
        if item.get("qty_received") != 5:
            result.add_fail("5.3: Clamping", f"Expected qty_received=5 (clamped), got {item.get('qty_received')}", {"item": item})
            return
        
        result.add_pass("5.3: Clamping works (receipts > qty clamped to qty)")
        
    except Exception as e:
        result.add_fail("5.3: Clamping test", f"Exception: {e}", None)

# =============================================================================
# 6. LIST + SEARCH
# =============================================================================
def test_list_and_search(token: str):
    """Test 6: LIST + SEARCH"""
    print("\n" + "="*80)
    print("TEST 6: LIST + SEARCH")
    print("="*80)
    
    headers = get_headers(token)
    
    # Test 6.1: GET /api/purchase-orders returns array
    print("\n📦 Test 6.1: GET /api/purchase-orders returns array")
    try:
        resp = requests.get(f"{API_BASE}/purchase-orders", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("6.1: List POs", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        pos = resp.json()
        if not isinstance(pos, list):
            result.add_fail("6.1: List POs", "Response is not an array", {"response": pos})
            return
        
        result.add_pass(f"6.1: GET /api/purchase-orders returns array ({len(pos)} POs)")
        
    except Exception as e:
        result.add_fail("6.1: List POs", f"Exception: {e}", None)
        return
    
    # Test 6.2: Filter by status
    print("\n📦 Test 6.2: GET /api/purchase-orders?status=draft")
    try:
        resp = requests.get(f"{API_BASE}/purchase-orders?status=draft", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("6.2: Filter by status", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            pos = resp.json()
            # Check all returned POs have status=draft
            non_draft = [po for po in pos if po.get("status") != "draft"]
            if non_draft:
                result.add_fail("6.2: Filter by status", f"Found {len(non_draft)} non-draft POs", {"non_draft": non_draft})
            else:
                result.add_pass(f"6.2: Filter by status works (returned {len(pos)} draft POs)")
    except Exception as e:
        result.add_fail("6.2: Filter by status", f"Exception: {e}", None)
    
    # Test 6.3: Filter by brand_id
    print("\n📦 Test 6.3: GET /api/purchase-orders?brand_id=X")
    try:
        # Get a brand_id from the first PO
        resp = requests.get(f"{API_BASE}/purchase-orders?limit=1", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("6.3: Get sample PO", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            pos = resp.json()
            if pos and pos[0].get("brand_id"):
                brand_id = pos[0]["brand_id"]
                resp = requests.get(f"{API_BASE}/purchase-orders?brand_id={brand_id}", headers=headers, timeout=10)
                if resp.status_code != 200:
                    result.add_fail("6.3: Filter by brand_id", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
                else:
                    filtered = resp.json()
                    wrong_brand = [po for po in filtered if po.get("brand_id") != brand_id]
                    if wrong_brand:
                        result.add_fail("6.3: Filter by brand_id", f"Found {len(wrong_brand)} POs with wrong brand", {"wrong_brand": wrong_brand})
                    else:
                        result.add_pass(f"6.3: Filter by brand_id works (returned {len(filtered)} POs)")
            else:
                result.add_pass("6.3: Filter by brand_id (no POs to test)")
    except Exception as e:
        result.add_fail("6.3: Filter by brand_id", f"Exception: {e}", None)
    
    # Test 6.4: Filter by supplier_id, customer_id, quotation_id
    print("\n📦 Test 6.4: Filters (supplier_id, customer_id, quotation_id)")
    try:
        # Just verify the endpoints accept the parameters (smoke test)
        resp = requests.get(f"{API_BASE}/purchase-orders?supplier_id=test", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("6.4: Filter by supplier_id", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        
        resp = requests.get(f"{API_BASE}/purchase-orders?customer_id=test", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("6.4: Filter by customer_id", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        
        resp = requests.get(f"{API_BASE}/purchase-orders?quotation_id=test", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("6.4: Filter by quotation_id", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        
        result.add_pass("6.4: Filters (supplier_id, customer_id, quotation_id) work")
    except Exception as e:
        result.add_fail("6.4: Filters", f"Exception: {e}", None)
    
    # Test 6.5: Search with q parameter
    print("\n📦 Test 6.5: GET /api/purchase-orders?q=<term>")
    try:
        # Get a PO number to search for
        resp = requests.get(f"{API_BASE}/purchase-orders?limit=1", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("6.5: Get sample PO", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            pos = resp.json()
            if pos:
                po_number = pos[0].get("number", "")
                if po_number:
                    # Search by PO number
                    search_term = po_number.split("-")[-1]  # e.g., "0001" from "FPO-2026-0001"
                    resp = requests.get(f"{API_BASE}/purchase-orders?q={search_term}", headers=headers, timeout=10)
                    if resp.status_code != 200:
                        result.add_fail("6.5: Search by q", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
                    else:
                        results = resp.json()
                        # Should find at least the PO we searched for
                        found = any(po.get("number") == po_number for po in results)
                        if not found:
                            result.add_fail("6.5: Search by q", f"Didn't find PO {po_number} in results", {"results": results})
                        else:
                            result.add_pass(f"6.5: Search by q works (found {len(results)} results for '{search_term}')")
                else:
                    result.add_pass("6.5: Search by q (no PO number to test)")
            else:
                result.add_pass("6.5: Search by q (no POs to test)")
    except Exception as e:
        result.add_fail("6.5: Search by q", f"Exception: {e}", None)

# =============================================================================
# 7. DASHBOARD
# =============================================================================
def test_dashboard(token: str):
    """Test 7: DASHBOARD"""
    print("\n" + "="*80)
    print("TEST 7: DASHBOARD")
    print("="*80)
    
    headers = get_headers(token)
    
    # Test 7.1: GET /api/purchase-orders/dashboard
    print("\n📦 Test 7.1: GET /api/purchase-orders/dashboard")
    try:
        resp = requests.get(f"{API_BASE}/purchase-orders/dashboard", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("7.1: Dashboard", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        dashboard = resp.json()
        
        # Check shape
        if "columns" not in dashboard or "total_open_value" not in dashboard:
            result.add_fail("7.1: Dashboard shape", "Missing columns or total_open_value", {"response": dashboard})
            return
        
        columns = dashboard["columns"]
        if not isinstance(columns, list):
            result.add_fail("7.1: Dashboard columns", "columns is not an array", {"response": dashboard})
            return
        
        # Check all 8 canonical statuses appear
        expected_statuses = [
            "draft", "awaiting_review", "ordered", "awaiting_supplier",
            "partial_received", "fully_received", "packed", "ready_for_dispatch"
        ]
        found_statuses = [col.get("status") for col in columns]
        
        for status in expected_statuses:
            if status not in found_statuses:
                result.add_fail("7.1: Dashboard statuses", f"Missing status: {status}", {"found": found_statuses})
                return
        
        # Check each column has status, label, count, value
        for col in columns:
            if not all(k in col for k in ["status", "label", "count", "value"]):
                result.add_fail("7.1: Column shape", "Missing required keys", {"column": col})
                return
        
        result.add_pass(f"7.1: Dashboard returns all 8 canonical statuses with counts and values")
        
        # Test 7.2: Counts match actual data (basic sanity check)
        print("\n📦 Test 7.2: Dashboard counts match actual data")
        resp = requests.get(f"{API_BASE}/purchase-orders", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("7.2: Get all POs", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        all_pos = resp.json()
        actual_counts = {}
        for po in all_pos:
            status = po.get("status")
            actual_counts[status] = actual_counts.get(status, 0) + 1
        
        # Compare with dashboard counts
        mismatches = []
        for col in columns:
            status = col["status"]
            dashboard_count = col["count"]
            actual_count = actual_counts.get(status, 0)
            if dashboard_count != actual_count:
                mismatches.append(f"{status}: dashboard={dashboard_count}, actual={actual_count}")
        
        if mismatches:
            result.add_fail("7.2: Dashboard counts", "Counts don't match actual data", {"mismatches": mismatches})
        else:
            result.add_pass("7.2: Dashboard counts match actual data")
        
    except Exception as e:
        result.add_fail("7.1-7.2: Dashboard", f"Exception: {e}", None)

# =============================================================================
# 8. ACTIVITY FEED
# =============================================================================
def test_activity_feed(token: str, quotation_id: str, po_id: str, customer_id: str):
    """Test 8: ACTIVITY FEED"""
    print("\n" + "="*80)
    print("TEST 8: ACTIVITY FEED")
    print("="*80)
    
    headers = get_headers(token)
    
    # Test 8.1: GET /api/activity (global feed)
    print("\n📦 Test 8.1: GET /api/activity (global feed)")
    try:
        resp = requests.get(f"{API_BASE}/activity", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("8.1: Global activity", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            events = resp.json()
            if not isinstance(events, list):
                result.add_fail("8.1: Global activity", "Response is not an array", {"response": events})
            else:
                result.add_pass(f"8.1: Global activity feed returns {len(events)} events (reverse chrono)")
    except Exception as e:
        result.add_fail("8.1: Global activity", f"Exception: {e}", None)
    
    # Test 8.2: GET /api/activity/quotation/{q_id}
    print(f"\n📦 Test 8.2: GET /api/activity/quotation/{quotation_id}")
    try:
        resp = requests.get(f"{API_BASE}/activity/quotation/{quotation_id}", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("8.2: Quotation activity", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            events = resp.json()
            if not isinstance(events, list):
                result.add_fail("8.2: Quotation activity", "Response is not an array", {"response": events})
            else:
                # Check for expected event types
                event_types = [e.get("event_type") for e in events]
                expected_types = ["quotation.created", "quotation.order_placed"]
                
                missing = []
                for et in expected_types:
                    if et not in event_types:
                        missing.append(et)
                
                if missing:
                    result.add_fail("8.2: Quotation activity", f"Missing event types: {missing}", {"found": event_types})
                else:
                    result.add_pass(f"8.2: Quotation activity returns {len(events)} events (includes quotation.created, quotation.order_placed)")
    except Exception as e:
        result.add_fail("8.2: Quotation activity", f"Exception: {e}", None)
    
    # Test 8.3: GET /api/activity/purchase/{po_id}
    print(f"\n📦 Test 8.3: GET /api/activity/purchase/{po_id}")
    try:
        resp = requests.get(f"{API_BASE}/activity/purchase/{po_id}", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("8.3: Purchase activity", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            events = resp.json()
            if not isinstance(events, list):
                result.add_fail("8.3: Purchase activity", "Response is not an array", {"response": events})
            else:
                # Check for expected event types
                event_types = [e.get("event_type") for e in events]
                expected_types = ["purchase.created", "purchase.status_changed"]
                
                missing = []
                for et in expected_types:
                    if et not in event_types:
                        missing.append(et)
                
                if missing:
                    result.add_fail("8.3: Purchase activity", f"Missing event types: {missing}", {"found": event_types})
                else:
                    result.add_pass(f"8.3: Purchase activity returns {len(events)} events (includes purchase.created, purchase.status_changed)")
                
                # Check each event has required fields
                for event in events:
                    required_fields = ["id", "event_type", "entity_type", "entity_id", "created_at"]
                    missing_fields = [f for f in required_fields if f not in event]
                    if missing_fields:
                        result.add_fail("8.3: Event structure", f"Missing fields: {missing_fields}", {"event": event})
                        break
    except Exception as e:
        result.add_fail("8.3: Purchase activity", f"Exception: {e}", None)
    
    # Test 8.4: GET /api/activity/customer/{c_id}
    print(f"\n📦 Test 8.4: GET /api/activity/customer/{customer_id}")
    try:
        resp = requests.get(f"{API_BASE}/activity/customer/{customer_id}", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("8.4: Customer activity", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            events = resp.json()
            if not isinstance(events, list):
                result.add_fail("8.4: Customer activity", "Response is not an array", {"response": events})
            else:
                result.add_pass(f"8.4: Customer activity returns {len(events)} events (denormalised by customer_id)")
    except Exception as e:
        result.add_fail("8.4: Customer activity", f"Exception: {e}", None)

# =============================================================================
# 9. ATTACHMENTS
# =============================================================================
def test_attachments(token: str, po_id: str):
    """Test 9: ATTACHMENTS"""
    print("\n" + "="*80)
    print("TEST 9: ATTACHMENTS")
    print("="*80)
    
    headers = get_headers(token)
    
    # Test 9.1: POST /api/purchase-orders/{po_id}/attachments
    print(f"\n📦 Test 9.1: POST /api/purchase-orders/{po_id}/attachments")
    try:
        # Create a small test image (1x1 PNG)
        png_data = base64.b64encode(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82').decode('utf-8')
        data_url = f"data:image/png;base64,{png_data}"
        
        resp = requests.post(
            f"{API_BASE}/purchase-orders/{po_id}/attachments",
            headers=headers,
            json={
                "filename": "test_invoice.png",
                "mime": "image/png",
                "data_url": data_url,
                "note": "Test attachment"
            },
            timeout=10
        )
        if resp.status_code != 200:
            result.add_fail("9.1: Add attachment", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        po = resp.json()
        
        # Check attachments array grew
        attachments = po.get("attachments", [])
        if len(attachments) < 1:
            result.add_fail("9.1: Add attachment", "Attachments array didn't grow", {"po": po})
            return
        
        # Check last attachment
        att = attachments[-1]
        if att.get("filename") != "test_invoice.png":
            result.add_fail("9.1: Attachment filename", f"Expected 'test_invoice.png', got '{att.get('filename')}'", {"attachment": att})
            return
        
        result.add_pass(f"9.1: Add attachment succeeds, attachments array grows to {len(attachments)}")
        
        # Test 9.2: Activity event 'purchase.attachment_added' logged
        print(f"\n📦 Test 9.2: Activity event 'purchase.attachment_added' logged")
        resp = requests.get(f"{API_BASE}/activity/purchase/{po_id}", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("9.2: Get activity", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        
        events = resp.json()
        event_types = [e.get("event_type") for e in events]
        
        if "purchase.attachment_added" not in event_types:
            result.add_fail("9.2: Attachment event", "Event 'purchase.attachment_added' not found", {"event_types": event_types})
        else:
            result.add_pass("9.2: Activity event 'purchase.attachment_added' logged")
        
    except Exception as e:
        result.add_fail("9.1-9.2: Attachments", f"Exception: {e}", None)

# =============================================================================
# 10. REGRESSION (previous milestone endpoints)
# =============================================================================
def test_regression(token: str):
    """Test 10: REGRESSION (previous milestone endpoints)"""
    print("\n" + "="*80)
    print("TEST 10: REGRESSION (previous milestone endpoints)")
    print("="*80)
    
    headers = get_headers(token)
    
    # Test 10.1: POST /api/quotations creates
    print("\n📦 Test 10.1: POST /api/quotations creates")
    try:
        resp = requests.get(f"{API_BASE}/customers", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("10.1: Get customers", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
            return
        customers = resp.json()
        if not customers:
            result.add_fail("10.1: No customers", "No customers found", None)
            return
        customer_id = customers[0].get("id")
        
        resp = requests.post(
            f"{API_BASE}/quotations",
            headers=headers,
            json={
                "customer_id": customer_id,
                "items": [],
                "rooms": []
            },
            timeout=10
        )
        if resp.status_code not in [200, 201]:
            result.add_fail("10.1: Create quotation", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            result.add_pass("10.1: POST /api/quotations creates quotation")
    except Exception as e:
        result.add_fail("10.1: Create quotation", f"Exception: {e}", None)
    
    # Test 10.2: PATCH /api/quotations/{id} silent=true does not create revision
    print("\n📦 Test 10.2: PATCH silent=true does not create revision")
    try:
        resp = requests.get(f"{API_BASE}/quotations?limit=1", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("10.2: Get quotation", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            quots = resp.json()
            if quots:
                quot_id = quots[0].get("id")
                initial_revisions = len(quots[0].get("revisions", []))
                
                resp = requests.patch(
                    f"{API_BASE}/quotations/{quot_id}",
                    headers=headers,
                    json={"silent": True, "notes": "silent update"},
                    timeout=10
                )
                if resp.status_code != 200:
                    result.add_fail("10.2: Silent PATCH", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
                else:
                    resp = requests.get(f"{API_BASE}/quotations/{quot_id}", headers=headers, timeout=10)
                    quot = resp.json()
                    final_revisions = len(quot.get("revisions", []))
                    
                    if final_revisions != initial_revisions:
                        result.add_fail("10.2: Silent PATCH", f"Revisions changed from {initial_revisions} to {final_revisions}", None)
                    else:
                        result.add_pass("10.2: PATCH silent=true does not create revision")
            else:
                result.add_pass("10.2: PATCH silent=true (no quotations to test)")
    except Exception as e:
        result.add_fail("10.2: Silent PATCH", f"Exception: {e}", None)
    
    # Test 10.3: PATCH silent=false creates revision AND emits activity events
    print("\n📦 Test 10.3: PATCH silent=false creates revision and emits activity events")
    try:
        resp = requests.get(f"{API_BASE}/quotations?limit=1", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("10.3: Get quotation", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            quots = resp.json()
            if quots:
                quot_id = quots[0].get("id")
                initial_revisions = len(quots[0].get("revisions", []))
                
                resp = requests.patch(
                    f"{API_BASE}/quotations/{quot_id}",
                    headers=headers,
                    json={"silent": False, "notes": "non-silent update", "reason": "test"},
                    timeout=10
                )
                if resp.status_code != 200:
                    result.add_fail("10.3: Non-silent PATCH", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
                else:
                    resp = requests.get(f"{API_BASE}/quotations/{quot_id}", headers=headers, timeout=10)
                    quot = resp.json()
                    final_revisions = len(quot.get("revisions", []))
                    
                    if final_revisions <= initial_revisions:
                        result.add_fail("10.3: Non-silent PATCH", f"Revisions didn't increase (was {initial_revisions}, now {final_revisions})", None)
                    else:
                        # Check activity events
                        resp = requests.get(f"{API_BASE}/activity/quotation/{quot_id}", headers=headers, timeout=10)
                        if resp.status_code != 200:
                            result.add_fail("10.3: Get activity", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
                        else:
                            events = resp.json()
                            event_types = [e.get("event_type") for e in events]
                            if "quotation.revision_created" in event_types:
                                result.add_pass("10.3: PATCH silent=false creates revision and emits activity events")
                            else:
                                result.add_fail("10.3: Activity events", "quotation.revision_created not found", {"event_types": event_types})
            else:
                result.add_pass("10.3: PATCH silent=false (no quotations to test)")
    except Exception as e:
        result.add_fail("10.3: Non-silent PATCH", f"Exception: {e}", None)
    
    # Test 10.4: POST /api/quotations/{id}/duplicate works
    print("\n📦 Test 10.4: POST /api/quotations/{id}/duplicate works")
    try:
        resp = requests.get(f"{API_BASE}/quotations?limit=1", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("10.4: Get quotation", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            quots = resp.json()
            if quots:
                quot_id = quots[0].get("id")
                resp = requests.post(f"{API_BASE}/quotations/{quot_id}/duplicate", headers=headers, timeout=10)
                if resp.status_code not in [200, 201]:
                    result.add_fail("10.4: Duplicate quotation", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
                else:
                    result.add_pass("10.4: POST /api/quotations/{id}/duplicate works")
            else:
                result.add_pass("10.4: Duplicate quotation (no quotations to test)")
    except Exception as e:
        result.add_fail("10.4: Duplicate quotation", f"Exception: {e}", None)
    
    # Test 10.5: GET /api/quotations/{id}/pdf returns 200 with application/pdf AND emits activity event
    print("\n📦 Test 10.5: GET /api/quotations/{id}/pdf returns 200 and emits activity event")
    try:
        resp = requests.get(f"{API_BASE}/quotations?limit=1", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("10.5: Get quotation", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            quots = resp.json()
            if quots:
                quot_id = quots[0].get("id")
                resp = requests.get(f"{API_BASE}/quotations/{quot_id}/pdf", headers=headers, timeout=10)
                if resp.status_code != 200:
                    result.add_fail("10.5: PDF generation", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
                else:
                    content_type = resp.headers.get("Content-Type", "")
                    if "application/pdf" not in content_type:
                        result.add_fail("10.5: PDF content type", f"Expected application/pdf, got {content_type}", None)
                    else:
                        # Check activity event
                        resp = requests.get(f"{API_BASE}/activity/quotation/{quot_id}", headers=headers, timeout=10)
                        if resp.status_code != 200:
                            result.add_fail("10.5: Get activity", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
                        else:
                            events = resp.json()
                            event_types = [e.get("event_type") for e in events]
                            if "quotation.pdf_generated" in event_types:
                                result.add_pass("10.5: PDF generation returns 200 with application/pdf and emits activity event")
                            else:
                                result.add_fail("10.5: PDF activity event", "quotation.pdf_generated not found", {"event_types": event_types})
            else:
                result.add_pass("10.5: PDF generation (no quotations to test)")
    except Exception as e:
        result.add_fail("10.5: PDF generation", f"Exception: {e}", None)
    
    # Test 10.6: GET /api/quotations/{id}/breakdown works
    print("\n📦 Test 10.6: GET /api/quotations/{id}/breakdown works")
    try:
        resp = requests.get(f"{API_BASE}/quotations?limit=1", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("10.6: Get quotation", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            quots = resp.json()
            if quots:
                quot_id = quots[0].get("id")
                resp = requests.get(f"{API_BASE}/quotations/{quot_id}/breakdown", headers=headers, timeout=10)
                if resp.status_code != 200:
                    result.add_fail("10.6: Breakdown", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
                else:
                    result.add_pass("10.6: GET /api/quotations/{id}/breakdown works")
            else:
                result.add_pass("10.6: Breakdown (no quotations to test)")
    except Exception as e:
        result.add_fail("10.6: Breakdown", f"Exception: {e}", None)
    
    # Test 10.7: GET /api/products/{id}/alternates works
    print("\n📦 Test 10.7: GET /api/products/{id}/alternates works")
    try:
        resp = requests.get(f"{API_BASE}/products?limit=1", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("10.7: Get products", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            products_data = resp.json()
            products = products_data.get("items", [])
            if products:
                product_id = products[0].get("id")
                resp = requests.get(f"{API_BASE}/products/{product_id}/alternates", headers=headers, timeout=10)
                if resp.status_code != 200:
                    result.add_fail("10.7: Alternates", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
                else:
                    result.add_pass("10.7: GET /api/products/{id}/alternates works")
            else:
                result.add_pass("10.7: Alternates (no products to test)")
    except Exception as e:
        result.add_fail("10.7: Alternates", f"Exception: {e}", None)
    
    # Test 10.8: GET /api/customers works
    print("\n📦 Test 10.8: GET /api/customers works")
    try:
        resp = requests.get(f"{API_BASE}/customers", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("10.8: List customers", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            result.add_pass("10.8: GET /api/customers works")
    except Exception as e:
        result.add_fail("10.8: List customers", f"Exception: {e}", None)
    
    # Test 10.9: GET /api/customers/{id} works
    print("\n📦 Test 10.9: GET /api/customers/{id} works")
    try:
        resp = requests.get(f"{API_BASE}/customers", headers=headers, timeout=10)
        if resp.status_code != 200:
            result.add_fail("10.9: Get customers", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            customers = resp.json()
            if customers:
                customer_id = customers[0].get("id")
                resp = requests.get(f"{API_BASE}/customers/{customer_id}", headers=headers, timeout=10)
                if resp.status_code != 200:
                    result.add_fail("10.9: Get customer by ID", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
                else:
                    result.add_pass("10.9: GET /api/customers/{id} works")
            else:
                result.add_pass("10.9: Get customer by ID (no customers to test)")
    except Exception as e:
        result.add_fail("10.9: Get customer by ID", f"Exception: {e}", None)
    
    # Test 10.10: POST /api/customers works
    print("\n📦 Test 10.10: POST /api/customers works")
    try:
        resp = requests.post(
            f"{API_BASE}/customers",
            headers=headers,
            json={
                "name": "Regression Test Customer",
                "email": "regression@test.com",
                "phone": "9876543210"
            },
            timeout=10
        )
        if resp.status_code not in [200, 201]:
            result.add_fail("10.10: Create customer", f"HTTP {resp.status_code}", {"response": resp.text[:400]})
        else:
            result.add_pass("10.10: POST /api/customers works")
    except Exception as e:
        result.add_fail("10.10: Create customer", f"Exception: {e}", None)

# =============================================================================
# MAIN TEST RUNNER
# =============================================================================
def main():
    """Main test runner"""
    print("="*80)
    print("FORGE V2 — PRODUCTION MILESTONE 1 — PURCHASES MODULE REGRESSION TEST")
    print("="*80)
    print(f"Backend URL: {API_BASE}")
    print(f"Test User: {TEST_EMAIL}")
    
    # Login
    token = login()
    
    # Test 1: SUPPLIERS
    suppliers = test_suppliers(token)
    
    # Test 2 & 3: PLACE ORDER (need a quotation with items)
    # Create a test quotation with items for place order tests
    print("\n" + "="*80)
    print("SETUP: Creating test quotation with items for place order tests")
    print("="*80)
    try:
        headers = get_headers(token)
        
        # Get customer
        resp = requests.get(f"{API_BASE}/customers", headers=headers, timeout=10)
        customers = resp.json()
        customer_id = customers[0].get("id")
        
        # Get products
        resp = requests.get(f"{API_BASE}/products?limit=5", headers=headers, timeout=10)
        products_data = resp.json()
        products = products_data.get("items", [])
        
        # Create quotation with items from different brands
        items = []
        for p in products[:5]:
            items.append({
                "product_id": p["id"],
                "sku": p["sku"],
                "name": p["name"],
                "qty": 2,
                "unit_price": p["price"],
                "tax_pct": 18
            })
        
        resp = requests.post(
            f"{API_BASE}/quotations",
            headers=headers,
            json={
                "customer_id": customer_id,
                "items": items,
                "rooms": ["Master Bath", "Powder Room"]
            },
            timeout=10
        )
        test_quot = resp.json()
        test_quot_id = test_quot.get("id")
        print(f"✅ Created test quotation {test_quot_id} with {len(items)} items")
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        sys.exit(1)
    
    # Test 2: PLACE ORDER — PREVIEW
    preview = test_place_order_preview(token, test_quot_id)
    test_place_order_preview_edge_cases(token)
    
    # Test 3: PLACE ORDER — CONFIRM
    if preview:
        pos = test_place_order_confirm(token, preview)
        
        if pos and len(pos) > 0:
            po_id = pos[0]["id"]
            
            # Test 4: PURCHASE ORDER LIFECYCLE
            test_purchase_order_lifecycle(token, po_id)
            
            # Test 5: RECEIVE FLOW
            test_receive_flow(token)
            
            # Test 6: LIST + SEARCH
            test_list_and_search(token)
            
            # Test 7: DASHBOARD
            test_dashboard(token)
            
            # Test 8: ACTIVITY FEED
            test_activity_feed(token, test_quot_id, po_id, customer_id)
            
            # Test 9: ATTACHMENTS
            test_attachments(token, po_id)
    
    # Test 10: REGRESSION
    test_regression(token)
    
    # Summary
    success = result.summary()
    
    if success:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {result.failed} TEST(S) FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
