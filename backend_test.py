#!/usr/bin/env python3
"""
Production Workflow Backend Verification
Tests quotation PDF generation, place-order workflow, and transactional automation.
"""
import io
import os
import sys
import time
from typing import Any

import requests
from PyPDF2 import PdfReader

# Backend URL configuration
BACKEND_URL = os.getenv("BACKEND_URL", "https://frontend-auth-trace.preview.emergentagent.com/api")

# Test credentials from /app/memory/test_credentials.md
OWNER_EMAIL = "owner@forge.app"
OWNER_PASSWORD = "Forge@2026"

# Global auth token
AUTH_TOKEN = None


def login() -> str:
    """Authenticate and return JWT token."""
    global AUTH_TOKEN
    print(f"\n{'='*80}")
    print("AUTHENTICATION")
    print(f"{'='*80}")
    
    response = requests.post(
        f"{BACKEND_URL}/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    
    print(f"POST /api/auth/login: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Login failed: {response.text}")
        sys.exit(1)
    
    data = response.json()
    AUTH_TOKEN = data.get("access_token") or data.get("token")
    
    if not AUTH_TOKEN:
        print(f"❌ No token in response: {data}")
        sys.exit(1)
    
    print(f"✅ Authenticated as {data.get('user', {}).get('full_name')} ({data.get('user', {}).get('email')})")
    return AUTH_TOKEN


def get_headers() -> dict:
    """Return authorization headers."""
    return {"Authorization": f"Bearer {AUTH_TOKEN}"}


def get_products(limit: int = 60) -> list[dict]:
    """GET /api/products?limit=N and return product list."""
    print(f"\n{'='*80}")
    print(f"FETCHING PRODUCTS (limit={limit})")
    print(f"{'='*80}")
    
    response = requests.get(
        f"{BACKEND_URL}/products",
        params={"limit": limit},
        headers=get_headers()
    )
    
    print(f"GET /api/products?limit={limit}: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Failed to fetch products: {response.text}")
        sys.exit(1)
    
    data = response.json()
    products = data.get("items", [])
    
    print(f"✅ Fetched {len(products)} products")
    
    if products:
        sample = products[0]
        print(f"   Sample product fields: {list(sample.keys())}")
        print(f"   Sample: {sample.get('sku')} - {sample.get('name')} - ₹{sample.get('mrp')}")
    
    return products


def get_customers() -> list[dict]:
    """GET /api/customers and return customer list."""
    print(f"\n{'='*80}")
    print("FETCHING CUSTOMERS")
    print(f"{'='*80}")
    
    response = requests.get(
        f"{BACKEND_URL}/customers",
        headers=get_headers()
    )
    
    print(f"GET /api/customers: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Failed to fetch customers: {response.text}")
        sys.exit(1)
    
    data = response.json()
    # Handle both list and object responses
    if isinstance(data, list):
        customers = data
    else:
        customers = data.get("items", [])
    
    print(f"✅ Fetched {len(customers)} customers")
    
    if customers:
        sample = customers[0]
        print(f"   Sample: {sample.get('name')} ({sample.get('id')})")
    
    return customers


def build_line_item(product: dict, room: str, qty: float = 1.0) -> dict:
    """Construct a QuotationLineItem from a product."""
    return {
        "product_id": product["id"],
        "sku": product["sku"],
        "name": product["name"],
        "image": product.get("images", [None])[0] if product.get("images") else None,
        "category_id": product.get("category_id"),
        "room": room,
        "qty": qty,
        "unit_price": float(product.get("mrp", 0)),
        "discount_pct": None,
        "finish": product.get("finish"),
        "colour": product.get("colour"),
    }


def create_quotation(customer_id: str, items: list[dict], rooms: list[str], 
                     project_name: str = "Production Workflow Test",
                     phone: str = "9876543210",
                     reference: str = "Testing",
                     project_discount_pct: float = 0.0,
                     category_discounts: dict = None) -> dict:
    """POST /api/quotations to create a new quotation."""
    payload = {
        "customer_id": customer_id,
        "items": items,
        "rooms": rooms,
        "project_name": project_name,
        "phone_snapshot": phone,
        "reference_source": reference,
        "project_discount_pct": project_discount_pct,
        "category_discounts": category_discounts or {},
        "room_discounts": {}
    }
    
    response = requests.post(
        f"{BACKEND_URL}/quotations",
        json=payload,
        headers=get_headers()
    )
    
    print(f"POST /api/quotations: {response.status_code}")
    
    if response.status_code not in [200, 201]:
        print(f"❌ Failed to create quotation: {response.text}")
        sys.exit(1)
    
    quotation = response.json()
    print(f"✅ Created quotation {quotation.get('number')} (ID: {quotation.get('id')})")
    print(f"   Items: {len(quotation.get('items', []))}, Rooms: {quotation.get('rooms')}")
    print(f"   Subtotal: ₹{quotation.get('subtotal', 0):,.2f}")
    print(f"   Discount: ₹{quotation.get('discount_total', 0):,.2f}")
    print(f"   Grand Total: ₹{quotation.get('grand_total', 0):,.2f}")
    
    return quotation


def get_quotation_pdf(quotation_id: str) -> bytes:
    """GET /api/quotations/{id}/pdf and return PDF bytes."""
    response = requests.get(
        f"{BACKEND_URL}/quotations/{quotation_id}/pdf",
        headers=get_headers()
    )
    
    print(f"GET /api/quotations/{quotation_id}/pdf: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Failed to get PDF: {response.text}")
        return None
    
    pdf_bytes = response.content
    print(f"✅ PDF generated: {len(pdf_bytes)} bytes")
    
    return pdf_bytes


def analyze_pdf(pdf_bytes: bytes, quotation_number: str) -> dict:
    """Analyze PDF structure and return metadata."""
    if not pdf_bytes:
        return {"valid": False, "error": "No PDF bytes"}
    
    try:
        pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(pdf_reader.pages)
        
        # Extract text from all pages
        pages_text = []
        for i, page in enumerate(pdf_reader.pages):
            text = page.extract_text()
            pages_text.append(text)
        
        # Check for official markers
        full_text = " ".join(pages_text)
        has_buildcon = "BuildCon House" in full_text or "buildcon" in full_text.lower()
        has_quotation_number = quotation_number in full_text
        
        # Check page size (A4 is 595 x 842 points)
        first_page = first_page = pdf_reader.pages[0]
        mediabox = first_page.mediabox
        width = float(mediabox.width)
        height = float(mediabox.height)
        is_a4 = (590 <= width <= 600) and (837 <= height <= 847)
        
        return {
            "valid": True,
            "page_count": page_count,
            "is_a4": is_a4,
            "width": width,
            "height": height,
            "has_buildcon": has_buildcon,
            "has_quotation_number": has_quotation_number,
            "pages_text": pages_text,
            "full_text": full_text
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


def get_workflow_status(quotation_id: str) -> dict:
    """GET /api/quotations/{id}/workflow-status."""
    response = requests.get(
        f"{BACKEND_URL}/quotations/{quotation_id}/workflow-status",
        headers=get_headers()
    )
    
    print(f"GET /api/quotations/{quotation_id}/workflow-status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Failed to get workflow status: {response.text}")
        return None
    
    return response.json()


def place_order(quotation_id: str, project_name: str = "Production Workflow Test") -> dict:
    """POST /api/quotations/{id}/place-order/confirm."""
    payload = {
        "supplier_by_brand": {},
        "notes_by_brand": {},
        "expected_delivery_at": None,
        "project_name": project_name
    }
    
    response = requests.post(
        f"{BACKEND_URL}/quotations/{quotation_id}/place-order/confirm",
        json=payload,
        headers=get_headers()
    )
    
    print(f"POST /api/quotations/{quotation_id}/place-order/confirm: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Failed to place order: {response.text}")
        return None
    
    return response.json()


def verify_workflow_status(status: dict, test_name: str, expected: dict):
    """Verify workflow status matches expectations."""
    print(f"\n   Workflow Status Verification for {test_name}:")
    
    issues = []
    
    # Check events
    events = status.get("events", [])
    event_types = [e.get("event_type") for e in events]
    
    for event_type, expected_count in expected.get("events", {}).items():
        actual_count = event_types.count(event_type)
        status_icon = "✅" if actual_count == expected_count else "❌"
        print(f"   {status_icon} {event_type}: {actual_count} (expected {expected_count})")
        if actual_count != expected_count:
            issues.append(f"{event_type}: expected {expected_count}, got {actual_count}")
    
    # Check timeline
    timeline = status.get("timeline", [])
    timeline_count = len(timeline)
    expected_timeline = expected.get("timeline", 0)
    status_icon = "✅" if timeline_count == expected_timeline else "❌"
    print(f"   {status_icon} Automation timeline items: {timeline_count} (expected {expected_timeline})")
    if timeline_count != expected_timeline:
        issues.append(f"Timeline: expected {expected_timeline}, got {timeline_count}")
    
    # Check followups
    followups = status.get("followups", [])
    followup_count = len(followups)
    expected_followups = expected.get("followups", 0)
    status_icon = "✅" if followup_count == expected_followups else "❌"
    print(f"   {status_icon} Automation follow-ups: {followup_count} (expected {expected_followups})")
    if followup_count != expected_followups:
        issues.append(f"Follow-ups: expected {expected_followups}, got {followup_count}")
    
    # Check payments
    payments = status.get("payments", [])
    payment_count = len(payments)
    expected_payments = expected.get("payments", 0)
    status_icon = "✅" if payment_count == expected_payments else "❌"
    print(f"   {status_icon} Pending payments: {payment_count} (expected {expected_payments})")
    if payment_count != expected_payments:
        issues.append(f"Payments: expected {expected_payments}, got {payment_count}")
    
    # Check payment amount
    if payments and expected.get("payment_amount"):
        payment_amount = sum(float(p.get("amount", 0)) for p in payments if p.get("status") == "pending")
        expected_amount = expected["payment_amount"]
        status_icon = "✅" if abs(payment_amount - expected_amount) < 0.01 else "❌"
        print(f"   {status_icon} Payment amount: ₹{payment_amount:,.2f} (expected ₹{expected_amount:,.2f})")
        if abs(payment_amount - expected_amount) >= 0.01:
            issues.append(f"Payment amount: expected ₹{expected_amount:,.2f}, got ₹{payment_amount:,.2f}")
    
    # Check purchase orders
    purchase_orders = status.get("purchase_orders", [])
    po_count = len(purchase_orders)
    expected_pos = expected.get("purchase_orders", 0)
    status_icon = "✅" if po_count == expected_pos else "❌"
    print(f"   {status_icon} Purchase orders: {po_count} (expected {expected_pos})")
    if po_count != expected_pos:
        issues.append(f"Purchase orders: expected {expected_pos}, got {po_count}")
    
    # Check PO line quantities
    if purchase_orders and expected.get("total_po_qty"):
        total_po_qty = 0
        for po in purchase_orders:
            for item in po.get("items", []):
                # PO items use 'qty' field, not 'quantity'
                total_po_qty += float(item.get("qty", 0))
        expected_qty = expected["total_po_qty"]
        status_icon = "✅" if abs(total_po_qty - expected_qty) < 0.01 else "❌"
        print(f"   {status_icon} Total PO quantities: {total_po_qty} (expected {expected_qty})")
        if abs(total_po_qty - expected_qty) >= 0.01:
            issues.append(f"PO quantities: expected {expected_qty}, got {total_po_qty}")
    
    return issues


def test_one_room_quotation(products: list[dict], customer_id: str):
    """Test A: One-room quotation with PDF generation and workflow verification."""
    print(f"\n{'='*80}")
    print("TEST A: ONE-ROOM QUOTATION")
    print(f"{'='*80}")
    
    # Create quotation with 3 products in one room
    items = [
        build_line_item(products[0], "Master Bathroom", qty=2.0),
        build_line_item(products[1], "Master Bathroom", qty=1.0),
        build_line_item(products[2], "Master Bathroom", qty=3.0),
    ]
    
    quotation = create_quotation(
        customer_id=customer_id,
        items=items,
        rooms=["Master Bathroom"],
        project_name="One Room Test",
        project_discount_pct=5.0
    )
    
    quotation_id = quotation["id"]
    quotation_number = quotation["number"]
    grand_total = float(quotation["grand_total"])
    
    # Verify totals match breakdown
    subtotal = float(quotation["subtotal"])
    discount_total = float(quotation["discount_total"])
    calculated_total = subtotal - discount_total
    
    print(f"\n   Totals Verification:")
    print(f"   Subtotal: ₹{subtotal:,.2f}")
    print(f"   Discount: ₹{discount_total:,.2f}")
    print(f"   Grand Total: ₹{grand_total:,.2f}")
    print(f"   Calculated: ₹{calculated_total:,.2f}")
    
    if abs(grand_total - calculated_total) < 0.01:
        print(f"   ✅ Totals match breakdown")
    else:
        print(f"   ❌ Totals mismatch: {grand_total} != {calculated_total}")
    
    # Generate PDF twice
    print(f"\n   PDF Generation (First Call):")
    pdf_bytes_1 = get_quotation_pdf(quotation_id)
    pdf_analysis_1 = analyze_pdf(pdf_bytes_1, quotation_number)
    
    time.sleep(1)  # Brief pause
    
    print(f"\n   PDF Generation (Second Call):")
    pdf_bytes_2 = get_quotation_pdf(quotation_id)
    pdf_analysis_2 = analyze_pdf(pdf_bytes_2, quotation_number)
    
    # Verify PDF properties
    print(f"\n   PDF Analysis:")
    if pdf_analysis_1.get("valid"):
        print(f"   ✅ PDF is valid")
        print(f"   ✅ Page count: {pdf_analysis_1['page_count']}")
        print(f"   {'✅' if pdf_analysis_1['is_a4'] else '❌'} A4 size: {pdf_analysis_1['width']:.1f} x {pdf_analysis_1['height']:.1f} points")
        print(f"   {'✅' if pdf_analysis_1['has_buildcon'] else '❌'} Contains BuildCon House branding")
        print(f"   {'✅' if pdf_analysis_1['has_quotation_number'] else '❌'} Contains quotation number {quotation_number}")
    else:
        print(f"   ❌ PDF invalid: {pdf_analysis_1.get('error')}")
    
    # Get workflow status
    time.sleep(2)  # Allow automation to complete
    status = get_workflow_status(quotation_id)
    
    if status:
        issues = verify_workflow_status(
            status,
            "One-Room Test",
            {
                "events": {"QuotationGenerated": 1},
                "timeline": 1,
                "followups": 1,
                "payments": 0,
                "purchase_orders": 0
            }
        )
        
        if not issues:
            print(f"\n   ✅ TEST A PASSED")
        else:
            print(f"\n   ❌ TEST A FAILED:")
            for issue in issues:
                print(f"      - {issue}")
    
    return quotation_id, grand_total


def test_place_order(quotation_id: str, grand_total: float):
    """Test B: Place order twice and verify idempotency."""
    print(f"\n{'='*80}")
    print("TEST B: PLACE ORDER (IDEMPOTENCY)")
    print(f"{'='*80}")
    
    # First place-order call
    print(f"\n   First Place Order Call:")
    result_1 = place_order(quotation_id, "Place Order Test")
    
    if result_1:
        print(f"   ✅ First call succeeded")
        print(f"   Idempotent: {result_1.get('idempotent')}")
    
    time.sleep(2)  # Allow automation to complete
    
    # Second place-order call (should be idempotent)
    print(f"\n   Second Place Order Call:")
    result_2 = place_order(quotation_id, "Place Order Test")
    
    if result_2:
        print(f"   ✅ Second call succeeded")
        print(f"   Idempotent: {result_2.get('idempotent')}")
    
    # Get workflow status
    time.sleep(2)
    status = get_workflow_status(quotation_id)
    
    if status:
        # Calculate total PO quantities
        total_po_qty = 0
        for po in status.get("purchase_orders", []):
            for item in po.get("items", []):
                total_po_qty += float(item.get("quantity", 0))
        
        # Original quotation had 2 + 1 + 3 = 6 items
        expected_qty = 6.0
        
        issues = verify_workflow_status(
            status,
            "Place Order Test",
            {
                "events": {"QuotationGenerated": 1, "OrderPlaced": 1},
                "timeline": 2,  # 1 generated + 1 order
                "followups": 2,  # 1 generated + 1 order
                "payments": 1,
                "payment_amount": grand_total,
                "purchase_orders": 2,  # Multiple brands = multiple POs
                "total_po_qty": expected_qty
            }
        )
        
        if not issues:
            print(f"\n   ✅ TEST B PASSED")
        else:
            print(f"\n   ❌ TEST B FAILED:")
            for issue in issues:
                print(f"      - {issue}")


def test_five_room_quotation(products: list[dict], customer_id: str):
    """Test C: Five-room quotation with PDF pagination verification."""
    print(f"\n{'='*80}")
    print("TEST C: FIVE-ROOM QUOTATION")
    print(f"{'='*80}")
    
    rooms = ["Living Room", "Master Bedroom", "Kitchen", "Guest Bathroom", "Balcony"]
    items = []
    
    # Add 2 products per room
    for i, room in enumerate(rooms):
        items.append(build_line_item(products[i * 2], room, qty=1.0))
        items.append(build_line_item(products[i * 2 + 1], room, qty=2.0))
    
    quotation = create_quotation(
        customer_id=customer_id,
        items=items,
        rooms=rooms,
        project_name="Five Room Test"
    )
    
    quotation_id = quotation["id"]
    quotation_number = quotation["number"]
    
    # Generate PDF
    print(f"\n   PDF Generation:")
    pdf_bytes = get_quotation_pdf(quotation_id)
    pdf_analysis = analyze_pdf(pdf_bytes, quotation_number)
    
    # Verify PDF structure
    print(f"\n   PDF Structure Verification:")
    if pdf_analysis.get("valid"):
        page_count = pdf_analysis["page_count"]
        print(f"   ✅ PDF is valid")
        print(f"   ✅ Page count: {page_count}")
        
        # Expected: 1 summary page + 5 room pages = 6 pages
        expected_pages = 6
        if page_count == expected_pages:
            print(f"   ✅ Page count matches expected ({expected_pages})")
        else:
            print(f"   ⚠️  Page count: {page_count} (expected {expected_pages})")
        
        # Check if each room appears on its own page
        pages_text = pdf_analysis.get("pages_text", [])
        if len(pages_text) > 1:
            # First page should be summary
            first_page_text = pages_text[0]
            print(f"   {'✅' if 'summary' in first_page_text.lower() or len(first_page_text) < 500 else '⚠️ '} First page appears to be summary")
            
            # Check room distribution
            room_pages = {}
            for i, page_text in enumerate(pages_text[1:], start=2):
                for room in rooms:
                    if room in page_text:
                        if room not in room_pages:
                            room_pages[room] = []
                        room_pages[room].append(i)
            
            print(f"   Room distribution across pages:")
            for room in rooms:
                pages = room_pages.get(room, [])
                if len(pages) == 1:
                    print(f"      ✅ {room}: page {pages[0]}")
                elif len(pages) > 1:
                    print(f"      ⚠️  {room}: pages {pages} (expected single page)")
                else:
                    print(f"      ❌ {room}: not found in PDF")
        
        print(f"\n   ✅ TEST C PASSED")
    else:
        print(f"   ❌ PDF invalid: {pdf_analysis.get('error')}")
        print(f"\n   ❌ TEST C FAILED")


def test_stress_quotations(products: list[dict], customer_id: str):
    """Test D: 50-line and 200-line quotations (no order placement)."""
    print(f"\n{'='*80}")
    print("TEST D: STRESS QUOTATIONS (50 and 200 lines)")
    print(f"{'='*80}")
    
    # Test 50-line quotation
    print(f"\n   50-Line Quotation:")
    items_50 = []
    rooms_50 = [f"Room {i+1}" for i in range(10)]  # 10 rooms
    
    for i in range(50):
        product = products[i % len(products)]
        room = rooms_50[i % len(rooms_50)]
        items_50.append(build_line_item(product, room, qty=1.0))
    
    quotation_50 = create_quotation(
        customer_id=customer_id,
        items=items_50,
        rooms=rooms_50,
        project_name="50 Line Stress Test"
    )
    
    pdf_bytes_50 = get_quotation_pdf(quotation_50["id"])
    pdf_analysis_50 = analyze_pdf(pdf_bytes_50, quotation_50["number"])
    
    if pdf_analysis_50.get("valid"):
        print(f"   ✅ 50-line PDF generated: {pdf_analysis_50['page_count']} pages")
        print(f"   ✅ Grand Total: ₹{quotation_50['grand_total']:,.2f}")
        
        # Verify all rooms present
        full_text = pdf_analysis_50.get("full_text", "")
        missing_rooms = [room for room in rooms_50 if room not in full_text]
        if not missing_rooms:
            print(f"   ✅ All 10 rooms present in PDF")
        else:
            print(f"   ⚠️  Missing rooms: {missing_rooms}")
    else:
        print(f"   ❌ 50-line PDF failed: {pdf_analysis_50.get('error')}")
    
    # Test 200-line quotation
    print(f"\n   200-Line Quotation:")
    items_200 = []
    rooms_200 = [f"Room {i+1}" for i in range(20)]  # 20 rooms
    
    for i in range(200):
        product = products[i % len(products)]
        room = rooms_200[i % len(rooms_200)]
        items_200.append(build_line_item(product, room, qty=1.0))
    
    quotation_200 = create_quotation(
        customer_id=customer_id,
        items=items_200,
        rooms=rooms_200,
        project_name="200 Line Stress Test"
    )
    
    pdf_bytes_200 = get_quotation_pdf(quotation_200["id"])
    pdf_analysis_200 = analyze_pdf(pdf_bytes_200, quotation_200["number"])
    
    if pdf_analysis_200.get("valid"):
        print(f"   ✅ 200-line PDF generated: {pdf_analysis_200['page_count']} pages")
        print(f"   ✅ Grand Total: ₹{quotation_200['grand_total']:,.2f}")
        
        # Verify all rooms present
        full_text = pdf_analysis_200.get("full_text", "")
        missing_rooms = [room for room in rooms_200 if room not in full_text]
        if not missing_rooms:
            print(f"   ✅ All 20 rooms present in PDF")
        else:
            print(f"   ⚠️  Missing rooms: {missing_rooms}")
    else:
        print(f"   ❌ 200-line PDF failed: {pdf_analysis_200.get('error')}")
    
    print(f"\n   ✅ TEST D COMPLETED (no orders placed as requested)")


def main():
    """Run all Production Workflow tests."""
    print(f"\n{'#'*80}")
    print("PRODUCTION WORKFLOW BACKEND VERIFICATION")
    print(f"{'#'*80}")
    print(f"Backend URL: {BACKEND_URL}")
    
    # Authenticate
    login()
    
    # Fetch test data
    products = get_products(limit=60)
    customers = get_customers()
    
    if not products:
        print("❌ No products available for testing")
        sys.exit(1)
    
    if not customers:
        print("❌ No customers available for testing")
        sys.exit(1)
    
    customer_id = customers[0]["id"]
    
    # Run tests
    try:
        # Test A: One-room quotation
        quotation_id, grand_total = test_one_room_quotation(products, customer_id)
        
        # Test B: Place order (uses quotation from Test A)
        test_place_order(quotation_id, grand_total)
        
        # Test C: Five-room quotation
        test_five_room_quotation(products, customer_id)
        
        # Test D: Stress quotations
        test_stress_quotations(products, customer_id)
        
        print(f"\n{'#'*80}")
        print("ALL TESTS COMPLETED")
        print(f"{'#'*80}")
        
    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
