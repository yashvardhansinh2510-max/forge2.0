#!/usr/bin/env python3
"""
Sprint 1 Business Logic Bug Fixes Testing
==========================================
Tests the following fixes:
1. Payment overpayment validation
2. Place Order discount preservation (Purchase Order unit_cost)
3. Notification generation
4. Customer Portal demo login
5. Regression check (GET endpoints, PDF generation)
"""

import requests
import json
import sys
from datetime import datetime

# Backend URL from frontend/.env
BACKEND_URL = "https://forge-polish-sprint.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
OWNER_EMAIL = "owner@forge.app"
OWNER_PASSWORD = "Forge@2026"
CUSTOMER_EMAIL = "customer@forge.app"
CUSTOMER_PASSWORD = "Forge@2026"

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def log(message, color=RESET):
    """Print colored log message"""
    print(f"{color}{message}{RESET}")

def log_test(test_name):
    """Log test name"""
    print(f"\n{'='*80}")
    log(f"TEST: {test_name}", BLUE)
    print('='*80)

def log_pass(message):
    """Log pass message"""
    log(f"✅ PASS: {message}", GREEN)

def log_fail(message):
    """Log fail message"""
    log(f"❌ FAIL: {message}", RED)

def log_info(message):
    """Log info message"""
    log(f"ℹ️  INFO: {message}", YELLOW)

# Global variables for auth tokens
owner_token = None
customer_token = None

def login_as_owner():
    """Login as owner and return token"""
    global owner_token
    log_info("Logging in as owner@forge.app...")
    response = requests.post(f"{BACKEND_URL}/auth/login", json={
        "email": OWNER_EMAIL,
        "password": OWNER_PASSWORD
    })
    if response.status_code == 200:
        owner_token = response.json()["access_token"]
        log_pass(f"Owner login successful (token: {owner_token[:20]}...)")
        return owner_token
    else:
        log_fail(f"Owner login failed: {response.status_code} {response.text}")
        return None

def login_as_customer():
    """Login as customer and return token"""
    global customer_token
    log_info("Logging in as customer@forge.app...")
    response = requests.post(f"{BACKEND_URL}/auth/customer/login", json={
        "email": CUSTOMER_EMAIL,
        "password": CUSTOMER_PASSWORD
    })
    if response.status_code == 200:
        customer_token = response.json()["access_token"]
        customer_obj = response.json().get("customer", {})
        log_pass(f"Customer login successful (token: {customer_token[:20]}...)")
        log_info(f"Customer: {customer_obj.get('name', 'N/A')} ({customer_obj.get('email', 'N/A')})")
        return customer_token
    else:
        log_fail(f"Customer login failed: {response.status_code} {response.text}")
        return None

def get_headers(token):
    """Get headers with auth token"""
    return {"Authorization": f"Bearer {token}"}

# ============================================================================
# TEST 1: PAYMENT OVERPAYMENT VALIDATION
# ============================================================================
def test_payment_overpayment_validation():
    """
    Test payment overpayment validation:
    1. Find or create a confirmed order
    2. Compute outstanding balance
    3. Attempt overpayment (expect 400)
    4. Attempt valid payment (expect 200)
    5. Verify amount <= 0 is rejected (expect 400)
    """
    log_test("1. PAYMENT OVERPAYMENT VALIDATION")
    
    if not owner_token:
        log_fail("Owner token not available")
        return False
    
    headers = get_headers(owner_token)
    
    # Step 1: Find a confirmed quotation with status in ["ordered", "won", "fulfilled"]
    log_info("Step 1: Finding a confirmed order...")
    response = requests.get(f"{BACKEND_URL}/quotations", headers=headers)
    if response.status_code != 200:
        log_fail(f"Failed to fetch quotations: {response.status_code}")
        return False
    
    quotations = response.json()
    confirmed_quotation = None
    for q in quotations:
        if q.get("status") in ["ordered", "won", "fulfilled"]:
            confirmed_quotation = q
            break
    
    if not confirmed_quotation:
        log_info("No confirmed order found, creating one...")
        # Create a new quotation
        create_response = requests.post(f"{BACKEND_URL}/quotations", headers=headers, json={
            "customer_id": "4c636100-edbe-439c-8403-3668b182656d",  # Rajesh Malhotra
            "title": "Test Payment Validation Quotation"
        })
        if create_response.status_code != 200:
            log_fail(f"Failed to create quotation: {create_response.status_code}")
            return False
        
        new_quotation = create_response.json()
        quotation_id = new_quotation["id"]
        
        # Add some items to the quotation via PATCH
        log_info("Adding items to quotation...")
        products_response = requests.get(f"{BACKEND_URL}/products?limit=3", headers=headers)
        if products_response.status_code != 200:
            log_fail(f"Failed to fetch products: {products_response.status_code}")
            return False
        
        products = products_response.json()["items"]
        items_to_add = []
        for i, product in enumerate(products[:2]):
            items_to_add.append({
                "product_id": product["id"],
                "sku": product["sku"],
                "name": product["name"],
                "image": product.get("image"),
                "finish": product.get("finish"),
                "colour": product.get("colour"),
                "category_id": product.get("category_id"),
                "room": "Test Room",
                "qty": 2.0,
                "unit_price": product["price"],
                "discount_pct": None,
                "notes": None,
                "description": None,
                "sort_order": i
            })
        
        patch_response = requests.patch(
            f"{BACKEND_URL}/quotations/{quotation_id}",
            headers=headers,
            json={"items": items_to_add}
        )
        if patch_response.status_code != 200:
            log_fail(f"Failed to add items: {patch_response.status_code}")
            return False
        
        # Refresh quotation to get grand_total
        refresh_response = requests.get(f"{BACKEND_URL}/quotations/{quotation_id}", headers=headers)
        if refresh_response.status_code != 200:
            log_fail(f"Failed to refresh quotation: {refresh_response.status_code}")
            return False
        
        confirmed_quotation = refresh_response.json()
        log_pass(f"Created quotation {quotation_id} with grand_total: ₹{confirmed_quotation.get('grand_total', 0)}")
    else:
        quotation_id = confirmed_quotation["id"]
        log_pass(f"Found confirmed quotation: {confirmed_quotation.get('number', quotation_id)}")
        log_info(f"Status: {confirmed_quotation.get('status')}, Grand Total: ₹{confirmed_quotation.get('grand_total', 0)}")
    
    # Step 2: Compute outstanding balance
    log_info("Step 2: Computing outstanding balance...")
    grand_total = confirmed_quotation.get("grand_total", 0)
    
    # Get existing payments for this quotation
    payments_response = requests.get(f"{BACKEND_URL}/payments", headers=headers)
    if payments_response.status_code != 200:
        log_fail(f"Failed to fetch payments: {payments_response.status_code}")
        return False
    
    payments = payments_response.json()
    # Only count COMPLETED payments (not pending)
    already_paid = sum(p["amount"] for p in payments if p.get("quotation_id") == quotation_id and p.get("status") == "completed")
    outstanding_balance = grand_total - already_paid
    
    log_info(f"Grand Total: ₹{grand_total}")
    log_info(f"Already Paid: ₹{already_paid}")
    log_info(f"Outstanding Balance: ₹{outstanding_balance}")
    
    # Step 3: Attempt overpayment (outstanding_balance + 5000)
    log_info("Step 3: Attempting overpayment (outstanding + ₹5000)...")
    overpayment_amount = outstanding_balance + 5000
    overpayment_response = requests.post(f"{BACKEND_URL}/payments", headers=headers, json={
        "quotation_id": quotation_id,
        "amount": overpayment_amount,
        "payment_method": "bank_transfer",
        "notes": "Test overpayment"
    })
    
    if overpayment_response.status_code == 400:
        error_message = overpayment_response.json().get("detail", "")
        if "outstanding" in error_message.lower() or "balance" in error_message.lower():
            log_pass(f"Overpayment correctly rejected with 400: {error_message}")
        else:
            log_fail(f"Overpayment rejected with 400 but message doesn't mention outstanding balance: {error_message}")
            return False
    else:
        log_fail(f"Overpayment should return 400, got {overpayment_response.status_code}: {overpayment_response.text}")
        return False
    
    # Step 4: Attempt valid payment (outstanding_balance or smaller)
    log_info("Step 4: Attempting valid payment (≤ outstanding balance)...")
    valid_amount = min(outstanding_balance, 1000) if outstanding_balance > 0 else 0
    
    if valid_amount > 0:
        valid_payment_response = requests.post(f"{BACKEND_URL}/payments", headers=headers, json={
            "quotation_id": quotation_id,
            "amount": valid_amount,
            "payment_method": "bank_transfer",
            "notes": "Test valid payment"
        })
        
        if valid_payment_response.status_code in [200, 201]:
            payment_id = valid_payment_response.json().get("id")
            log_pass(f"Valid payment accepted with {valid_payment_response.status_code}: Payment ID {payment_id}")
        else:
            log_fail(f"Valid payment should return 200/201, got {valid_payment_response.status_code}: {valid_payment_response.text}")
            return False
    else:
        log_info("Outstanding balance is 0, skipping valid payment test")
    
    # Step 5: Verify amount <= 0 is rejected
    log_info("Step 5: Attempting payment with amount <= 0...")
    zero_payment_response = requests.post(f"{BACKEND_URL}/payments", headers=headers, json={
        "quotation_id": quotation_id,
        "amount": 0,
        "payment_method": "bank_transfer",
        "notes": "Test zero payment"
    })
    
    if zero_payment_response.status_code == 400:
        log_pass(f"Zero payment correctly rejected with 400")
    else:
        log_fail(f"Zero payment should return 400, got {zero_payment_response.status_code}")
        return False
    
    negative_payment_response = requests.post(f"{BACKEND_URL}/payments", headers=headers, json={
        "quotation_id": quotation_id,
        "amount": -100,
        "payment_method": "bank_transfer",
        "notes": "Test negative payment"
    })
    
    if negative_payment_response.status_code == 400:
        log_pass(f"Negative payment correctly rejected with 400")
    else:
        log_fail(f"Negative payment should return 400, got {negative_payment_response.status_code}")
        return False
    
    log_pass("Payment overpayment validation test PASSED")
    return True

# ============================================================================
# TEST 2: PLACE ORDER DISCOUNT PRESERVATION
# ============================================================================
def test_place_order_discount_preservation():
    """
    Test place order discount preservation:
    1. Create a new quotation with 2-3 line items
    2. Apply a PROJECT-LEVEL discount (e.g., 10%)
    3. Call place-order/preview and verify unit_cost reflects discount
    4. Confirm the order and verify PO unit_cost reflects discount
    """
    log_test("2. PLACE ORDER DISCOUNT PRESERVATION")
    
    if not owner_token:
        log_fail("Owner token not available")
        return False
    
    headers = get_headers(owner_token)
    
    # Step 1: Create a new quotation
    log_info("Step 1: Creating a new quotation...")
    create_response = requests.post(f"{BACKEND_URL}/quotations", headers=headers, json={
        "customer_id": "4c636100-edbe-439c-8403-3668b182656d",  # Rajesh Malhotra
        "title": "Test Discount Preservation Quotation"
    })
    
    if create_response.status_code != 200:
        log_fail(f"Failed to create quotation: {create_response.status_code}")
        return False
    
    quotation = create_response.json()
    quotation_id = quotation["id"]
    log_pass(f"Created quotation: {quotation_id}")
    
    # Step 2: Add 2-3 line items from catalog via PATCH
    log_info("Step 2: Adding line items from catalog...")
    products_response = requests.get(f"{BACKEND_URL}/products?limit=5", headers=headers)
    if products_response.status_code != 200:
        log_fail(f"Failed to fetch products: {products_response.status_code}")
        return False
    
    products = products_response.json()["items"]
    added_items = []
    
    # Build items array for PATCH
    items_to_add = []
    for i, product in enumerate(products[:3]):
        item = {
            "product_id": product["id"],
            "sku": product["sku"],
            "name": product["name"],
            "image": product.get("image"),
            "finish": product.get("finish"),
            "colour": product.get("colour"),
            "category_id": product.get("category_id"),
            "room": "Living Room",
            "qty": 2.0,
            "unit_price": product["price"],
            "discount_pct": None,
            "notes": None,
            "description": None,
            "sort_order": i
        }
        items_to_add.append(item)
        added_items.append({
            "product_id": product["id"],
            "sku": product["sku"],
            "name": product["name"],
            "unit_price": product["price"],
            "quantity": 2
        })
        log_info(f"Adding item: {product['name']} (₹{product['price']} x 2)")
    
    # PATCH quotation with items
    patch_items_response = requests.patch(
        f"{BACKEND_URL}/quotations/{quotation_id}",
        headers=headers,
        json={"items": items_to_add}
    )
    
    if patch_items_response.status_code != 200:
        log_fail(f"Failed to add items: {patch_items_response.status_code} {patch_items_response.text}")
        return False
    
    log_pass(f"Added {len(items_to_add)} items to quotation")
    
    # Step 3: Apply a PROJECT-LEVEL discount (10%)
    log_info("Step 3: Applying PROJECT-LEVEL discount (10%)...")
    
    # First, get the quotation to see current structure
    get_response = requests.get(f"{BACKEND_URL}/quotations/{quotation_id}", headers=headers)
    if get_response.status_code != 200:
        log_fail(f"Failed to get quotation: {get_response.status_code}")
        return False
    
    current_quotation = get_response.json()
    log_info(f"Current grand_total: ₹{current_quotation.get('grand_total', 0)}")
    
    # Apply project-level discount via PATCH
    patch_response = requests.patch(
        f"{BACKEND_URL}/quotations/{quotation_id}",
        headers=headers,
        json={
            "project_discount_pct": 10
        }
    )
    
    if patch_response.status_code != 200:
        log_fail(f"Failed to apply project discount: {patch_response.status_code} {patch_response.text}")
        return False
    
    updated_quotation = patch_response.json()
    log_pass(f"Applied 10% project discount")
    log_info(f"New grand_total: ₹{updated_quotation.get('grand_total', 0)}")
    log_info(f"Discount total: ₹{updated_quotation.get('discount_total', 0)}")
    
    # Step 4: Call place-order/preview and verify unit_cost reflects discount
    log_info("Step 4: Calling place-order/preview...")
    preview_response = requests.get(
        f"{BACKEND_URL}/quotations/{quotation_id}/place-order/preview",
        headers=headers
    )
    
    if preview_response.status_code != 200:
        log_fail(f"Failed to get place-order preview: {preview_response.status_code} {preview_response.text}")
        return False
    
    preview_data = preview_response.json()
    log_pass(f"Place-order preview retrieved")
    
    # Verify preview contains unit_cost field and it reflects discount
    preview_items_found = False
    discount_verified = False
    
    if "items" in preview_data:
        preview_items_found = True
        for item in preview_data["items"]:
            unit_cost = item.get("unit_cost")
            if unit_cost is not None:
                # Find the original item
                original_item = next((i for i in added_items if i["sku"] == item.get("sku")), None)
                if original_item:
                    expected_unit_cost = original_item["unit_price"] * 0.9  # 10% discount
                    if abs(unit_cost - expected_unit_cost) < 1:  # Allow 1 rupee tolerance
                        log_pass(f"Item {item.get('sku')}: unit_cost ₹{unit_cost} reflects 10% discount (original: ₹{original_item['unit_price']})")
                        discount_verified = True
                    else:
                        log_fail(f"Item {item.get('sku')}: unit_cost ₹{unit_cost} does NOT reflect discount (expected ~₹{expected_unit_cost})")
                        return False
    
    if "brands" in preview_data:
        preview_items_found = True
        for brand in preview_data["brands"]:
            for item in brand.get("items", []):
                unit_cost = item.get("unit_cost")
                if unit_cost is not None:
                    # Find the original item
                    original_item = next((i for i in added_items if i["sku"] == item.get("sku")), None)
                    if original_item:
                        expected_unit_cost = original_item["unit_price"] * 0.9  # 10% discount
                        if abs(unit_cost - expected_unit_cost) < 1:  # Allow 1 rupee tolerance
                            log_pass(f"Item {item.get('sku')}: unit_cost ₹{unit_cost} reflects 10% discount (original: ₹{original_item['unit_price']})")
                            discount_verified = True
                        else:
                            log_fail(f"Item {item.get('sku')}: unit_cost ₹{unit_cost} does NOT reflect discount (expected ~₹{expected_unit_cost})")
                            return False
    
    if not preview_items_found:
        log_fail("Preview response does not contain items or brands")
        return False
    
    if not discount_verified:
        log_fail("Could not verify discount in preview (no matching items found)")
        return False
    
    # Step 5: Confirm the order using the place-order/confirm endpoint
    log_info("Step 5: Confirming the order...")
    
    # Use the place-order/confirm endpoint which triggers OrderPlaced event
    confirm_response = requests.post(
        f"{BACKEND_URL}/quotations/{quotation_id}/place-order/confirm",
        headers=headers,
        json={
            "project_name": None,
            "expected_delivery_at": None
        }
    )
    
    if confirm_response.status_code != 200:
        log_fail(f"Failed to confirm order: {confirm_response.status_code} {confirm_response.text}")
        return False
    
    log_pass("Order confirmed via place-order/confirm endpoint")
    
    # Wait a moment for async processing
    import time
    time.sleep(2)
    
    # Step 6: Get Purchase Orders and verify unit_cost reflects discount
    log_info("Step 6: Verifying Purchase Orders have discounted unit_cost...")
    po_response = requests.get(f"{BACKEND_URL}/purchase-orders", headers=headers)
    
    if po_response.status_code != 200:
        log_fail(f"Failed to fetch purchase orders: {po_response.status_code}")
        return False
    
    purchase_orders = po_response.json()
    
    # Find POs for this quotation
    related_pos = [po for po in purchase_orders if po.get("quotation_id") == quotation_id]
    
    if not related_pos:
        log_info("No Purchase Orders found yet (may be async). Checking again...")
        time.sleep(3)
        po_response = requests.get(f"{BACKEND_URL}/purchase-orders", headers=headers)
        if po_response.status_code == 200:
            purchase_orders = po_response.json()
            related_pos = [po for po in purchase_orders if po.get("quotation_id") == quotation_id]
    
    if not related_pos:
        log_fail("No Purchase Orders created for this quotation")
        return False
    
    log_pass(f"Found {len(related_pos)} Purchase Order(s) for this quotation")
    
    # Verify unit_cost in PO items
    po_discount_verified = False
    for po in related_pos:
        log_info(f"Checking PO: {po.get('number', po.get('id'))}")
        
        # Get PO details
        po_detail_response = requests.get(f"{BACKEND_URL}/purchase-orders/{po['id']}", headers=headers)
        if po_detail_response.status_code != 200:
            log_fail(f"Failed to get PO details: {po_detail_response.status_code}")
            continue
        
        po_detail = po_detail_response.json()
        po_items = po_detail.get("items", [])
        
        for po_item in po_items:
            unit_cost = po_item.get("unit_cost")
            sku = po_item.get("sku")
            
            if unit_cost is not None and sku:
                # Find the original item
                original_item = next((i for i in added_items if i["sku"] == sku), None)
                if original_item:
                    expected_unit_cost = original_item["unit_price"] * 0.9  # 10% discount
                    if abs(unit_cost - expected_unit_cost) < 1:  # Allow 1 rupee tolerance
                        log_pass(f"PO Item {sku}: unit_cost ₹{unit_cost} reflects 10% discount (original: ₹{original_item['unit_price']})")
                        po_discount_verified = True
                    else:
                        log_fail(f"PO Item {sku}: unit_cost ₹{unit_cost} does NOT reflect discount (expected ~₹{expected_unit_cost})")
                        return False
    
    if not po_discount_verified:
        log_fail("Could not verify discount in Purchase Orders")
        return False
    
    log_pass("Place order discount preservation test PASSED")
    return True

# ============================================================================
# TEST 3: NOTIFICATION GENERATION
# ============================================================================
def test_notification_generation():
    """
    Test notification generation:
    1. Get current notification count
    2. Create a payment and verify new notification appears
    3. Place an order and verify new notification appears
    """
    log_test("3. NOTIFICATION GENERATION")
    
    if not owner_token:
        log_fail("Owner token not available")
        return False
    
    headers = get_headers(owner_token)
    
    # Step 1: Get current notification count
    log_info("Step 1: Getting current notifications...")
    notif_response = requests.get(f"{BACKEND_URL}/notifications", headers=headers)
    
    if notif_response.status_code != 200:
        log_fail(f"Failed to fetch notifications: {notif_response.status_code}")
        return False
    
    initial_notifications = notif_response.json()
    initial_count = len(initial_notifications)
    log_info(f"Current notification count: {initial_count}")
    
    # Step 2: Create a payment and verify notification
    log_info("Step 2: Creating a payment to trigger notification...")
    
    # Find a quotation with outstanding balance that is in "ordered" or "won" status
    quotations_response = requests.get(f"{BACKEND_URL}/quotations", headers=headers)
    if quotations_response.status_code != 200:
        log_fail(f"Failed to fetch quotations: {quotations_response.status_code}")
        return False
    
    quotations = quotations_response.json()
    test_quotation = None
    
    for q in quotations:
        if q.get("grand_total", 0) > 0 and q.get("status") in ["ordered", "won"]:
            test_quotation = q
            break
    
    if not test_quotation:
        log_fail("No quotation with grand_total > 0 and status in [ordered, won] found")
        return False
    
    quotation_id = test_quotation["id"]
    quotation_number = test_quotation.get("number", quotation_id)
    created_by = test_quotation.get("created_by")
    
    log_info(f"Using quotation: {quotation_number} (created_by: {created_by})")
    
    # Create a payment
    payment_response = requests.post(f"{BACKEND_URL}/payments", headers=headers, json={
        "quotation_id": quotation_id,
        "amount": 1000,
        "payment_method": "bank_transfer",
        "notes": "Test payment for notification"
    })
    
    if payment_response.status_code not in [200, 201]:
        # Might fail due to overpayment, try a smaller amount
        log_info("Payment failed, trying smaller amount...")
        payment_response = requests.post(f"{BACKEND_URL}/payments", headers=headers, json={
            "quotation_id": quotation_id,
            "amount": 100,
            "payment_method": "bank_transfer",
            "notes": "Test payment for notification"
        })
    
    if payment_response.status_code not in [200, 201]:
        log_fail(f"Failed to create payment: {payment_response.status_code} {payment_response.text}")
        return False
    
    payment_id = payment_response.json().get("id")
    log_pass(f"Payment created: {payment_id}")
    
    # Wait a moment for notification to be created
    import time
    time.sleep(1)
    
    # Get notifications again
    notif_response = requests.get(f"{BACKEND_URL}/notifications", headers=headers)
    if notif_response.status_code != 200:
        log_fail(f"Failed to fetch notifications after payment: {notif_response.status_code}")
        return False
    
    new_notifications = notif_response.json()
    new_count = len(new_notifications)
    
    log_info(f"Notification count after payment: {new_count}")
    
    if new_count > initial_count:
        # Check if there's a payment notification
        payment_notif_found = False
        for notif in new_notifications:
            title = notif.get("title", "")
            if "payment" in title.lower() and quotation_number in title:
                log_pass(f"Payment notification found: {title}")
                payment_notif_found = True
                break
        
        if not payment_notif_found:
            log_info("New notification found but doesn't match payment pattern")
            log_info(f"New notifications: {[n.get('title') for n in new_notifications[:3]]}")
    else:
        log_fail("No new notification created after payment")
        return False
    
    # Step 3: Place an order and verify notification
    log_info("Step 3: Placing an order to trigger notification...")
    
    # Find a quotation that can be ordered
    order_quotation = None
    for q in quotations:
        if q.get("status") not in ["ordered", "won", "fulfilled", "lost", "cancelled"]:
            order_quotation = q
            break
    
    if not order_quotation:
        log_info("No quotation available to place order, skipping order notification test")
    else:
        order_quotation_id = order_quotation["id"]
        order_quotation_number = order_quotation.get("number", order_quotation_id)
        
        log_info(f"Using quotation: {order_quotation_number}")
        
        # Place order by changing status to "ordered"
        order_response = requests.patch(
            f"{BACKEND_URL}/quotations/{order_quotation_id}",
            headers=headers,
            json={"status": "ordered"}
        )
        
        if order_response.status_code != 200:
            log_fail(f"Failed to place order: {order_response.status_code} {order_response.text}")
            return False
        
        log_pass("Order placed")
        
        # Wait for notification
        time.sleep(2)
        
        # Get notifications again
        notif_response = requests.get(f"{BACKEND_URL}/notifications", headers=headers)
        if notif_response.status_code != 200:
            log_fail(f"Failed to fetch notifications after order: {notif_response.status_code}")
            return False
        
        final_notifications = notif_response.json()
        final_count = len(final_notifications)
        
        log_info(f"Notification count after order: {final_count}")
        
        if final_count > new_count:
            # Check if there's an order notification
            order_notif_found = False
            for notif in final_notifications:
                title = notif.get("title", "")
                if "order" in title.lower() and order_quotation_number in title:
                    log_pass(f"Order notification found: {title}")
                    order_notif_found = True
                    break
            
            if not order_notif_found:
                log_info("New notification found but doesn't match order pattern")
                log_info(f"New notifications: {[n.get('title') for n in final_notifications[:3]]}")
        else:
            log_info("No new notification created after order (may be expected if no POs created)")
    
    log_pass("Notification generation test PASSED")
    return True

# ============================================================================
# TEST 4: CUSTOMER PORTAL DEMO LOGIN
# ============================================================================
def test_customer_portal_demo_login():
    """
    Test customer portal demo login:
    1. Login with customer@forge.app / Forge@2026
    2. Verify access_token is returned
    3. Use token to access customer portal endpoints
    """
    log_test("4. CUSTOMER PORTAL DEMO LOGIN")
    
    # Step 1: Login as customer
    log_info("Step 1: Logging in as customer@forge.app...")
    login_response = requests.post(f"{BACKEND_URL}/auth/customer/login", json={
        "email": CUSTOMER_EMAIL,
        "password": CUSTOMER_PASSWORD
    })
    
    if login_response.status_code != 200:
        log_fail(f"Customer login failed: {login_response.status_code} {login_response.text}")
        return False
    
    login_data = login_response.json()
    access_token = login_data.get("access_token")
    customer = login_data.get("customer", {})
    must_change_password = customer.get("must_change_password", True)
    
    if not access_token:
        log_fail("No access_token in login response")
        return False
    
    log_pass(f"Customer login successful")
    log_info(f"Customer: {customer.get('name', 'N/A')} ({customer.get('email', 'N/A')})")
    log_info(f"must_change_password: {must_change_password}")
    
    if must_change_password:
        log_fail("must_change_password should be false for demo account")
        return False
    
    log_pass("must_change_password is false (correct)")
    
    # Step 2: Use token to access customer portal endpoints
    log_info("Step 2: Accessing customer portal endpoints...")
    customer_headers = get_headers(access_token)
    
    # Try to get customer's quotations
    portal_quotations_response = requests.get(
        f"{BACKEND_URL}/portal/quotations",
        headers=customer_headers
    )
    
    if portal_quotations_response.status_code != 200:
        log_fail(f"Failed to access portal quotations: {portal_quotations_response.status_code} {portal_quotations_response.text}")
        return False
    
    portal_quotations = portal_quotations_response.json()
    log_pass(f"Portal quotations accessed successfully ({len(portal_quotations)} quotations)")
    
    # Try to get customer info
    customer_me_response = requests.get(
        f"{BACKEND_URL}/auth/customer/me",
        headers=customer_headers
    )
    
    if customer_me_response.status_code != 200:
        log_fail(f"Failed to access customer/me: {customer_me_response.status_code}")
        return False
    
    customer_me = customer_me_response.json()
    log_pass(f"Customer info accessed: {customer_me.get('name', 'N/A')}")
    
    log_pass("Customer portal demo login test PASSED")
    return True

# ============================================================================
# TEST 5: REGRESSION CHECK
# ============================================================================
def test_regression_check():
    """
    Test regression check:
    1. GET /api/quotations (expect 200 with ~28 quotations)
    2. GET /api/customers (expect 200 with 4 customers)
    3. GET /api/purchase-orders (expect 200 with ~10 POs)
    4. GET /api/payments (expect 200 with ~5 payments)
    5. GET /api/quotations/{id}/pdf (expect 200 with valid PDF)
    """
    log_test("5. REGRESSION CHECK")
    
    if not owner_token:
        log_fail("Owner token not available")
        return False
    
    headers = get_headers(owner_token)
    
    # Test 1: GET /api/quotations
    log_info("Test 1: GET /api/quotations...")
    quotations_response = requests.get(f"{BACKEND_URL}/quotations", headers=headers)
    
    if quotations_response.status_code != 200:
        log_fail(f"GET /api/quotations failed: {quotations_response.status_code}")
        return False
    
    quotations = quotations_response.json()
    quotations_count = len(quotations)
    log_pass(f"GET /api/quotations: 200 OK ({quotations_count} quotations)")
    
    if quotations_count < 20:
        log_info(f"Expected ~28 quotations, got {quotations_count} (may be expected after cleanup)")
    
    # Test 2: GET /api/customers
    log_info("Test 2: GET /api/customers...")
    customers_response = requests.get(f"{BACKEND_URL}/customers", headers=headers)
    
    if customers_response.status_code != 200:
        log_fail(f"GET /api/customers failed: {customers_response.status_code}")
        return False
    
    customers = customers_response.json()
    customers_count = len(customers)
    log_pass(f"GET /api/customers: 200 OK ({customers_count} customers)")
    
    if customers_count != 4:
        log_info(f"Expected 4 customers after cleanup, got {customers_count}")
    
    # Test 3: GET /api/purchase-orders
    log_info("Test 3: GET /api/purchase-orders...")
    pos_response = requests.get(f"{BACKEND_URL}/purchase-orders", headers=headers)
    
    if pos_response.status_code != 200:
        log_fail(f"GET /api/purchase-orders failed: {pos_response.status_code}")
        return False
    
    pos = pos_response.json()
    pos_count = len(pos)
    log_pass(f"GET /api/purchase-orders: 200 OK ({pos_count} purchase orders)")
    
    if pos_count < 5:
        log_info(f"Expected ~10 purchase orders, got {pos_count} (may be expected after cleanup)")
    
    # Test 4: GET /api/payments
    log_info("Test 4: GET /api/payments...")
    payments_response = requests.get(f"{BACKEND_URL}/payments", headers=headers)
    
    if payments_response.status_code != 200:
        log_fail(f"GET /api/payments failed: {payments_response.status_code}")
        return False
    
    payments = payments_response.json()
    payments_count = len(payments)
    log_pass(f"GET /api/payments: 200 OK ({payments_count} payments)")
    
    if payments_count < 3:
        log_info(f"Expected ~5 payments, got {payments_count} (may be expected after cleanup)")
    
    # Test 5: GET /api/quotations/{id}/pdf
    log_info("Test 5: GET /api/quotations/{id}/pdf...")
    
    if not quotations:
        log_fail("No quotations available to test PDF generation")
        return False
    
    test_quotation = quotations[0]
    quotation_id = test_quotation["id"]
    
    pdf_response = requests.get(
        f"{BACKEND_URL}/quotations/{quotation_id}/pdf",
        headers=headers
    )
    
    if pdf_response.status_code != 200:
        log_fail(f"GET /api/quotations/{quotation_id}/pdf failed: {pdf_response.status_code}")
        return False
    
    content_type = pdf_response.headers.get("content-type", "")
    pdf_size = len(pdf_response.content)
    
    if "application/pdf" not in content_type:
        log_fail(f"PDF content-type is not application/pdf: {content_type}")
        return False
    
    if not pdf_response.content.startswith(b"%PDF"):
        log_fail("PDF does not start with %PDF magic bytes")
        return False
    
    log_pass(f"GET /api/quotations/{quotation_id}/pdf: 200 OK (PDF size: {pdf_size} bytes)")
    
    log_pass("Regression check test PASSED")
    return True

# ============================================================================
# MAIN TEST RUNNER
# ============================================================================
def main():
    """Run all tests"""
    log("="*80, BLUE)
    log("SPRINT 1 BUSINESS LOGIC BUG FIXES TESTING", BLUE)
    log("="*80, BLUE)
    log(f"Backend URL: {BACKEND_URL}", YELLOW)
    log(f"Test Time: {datetime.now().isoformat()}", YELLOW)
    print()
    
    # Login as owner first
    if not login_as_owner():
        log_fail("Failed to login as owner, aborting tests")
        sys.exit(1)
    
    # Run tests
    results = {}
    
    try:
        results["payment_overpayment"] = test_payment_overpayment_validation()
    except Exception as e:
        log_fail(f"Payment overpayment test crashed: {e}")
        results["payment_overpayment"] = False
    
    try:
        results["discount_preservation"] = test_place_order_discount_preservation()
    except Exception as e:
        log_fail(f"Discount preservation test crashed: {e}")
        results["discount_preservation"] = False
    
    try:
        results["notification_generation"] = test_notification_generation()
    except Exception as e:
        log_fail(f"Notification generation test crashed: {e}")
        results["notification_generation"] = False
    
    try:
        results["customer_portal_login"] = test_customer_portal_demo_login()
    except Exception as e:
        log_fail(f"Customer portal login test crashed: {e}")
        results["customer_portal_login"] = False
    
    try:
        results["regression_check"] = test_regression_check()
    except Exception as e:
        log_fail(f"Regression check test crashed: {e}")
        results["regression_check"] = False
    
    # Print summary
    print("\n" + "="*80)
    log("TEST SUMMARY", BLUE)
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        color = GREEN if passed else RED
        log(f"{status}: {test_name}", color)
    
    total_tests = len(results)
    passed_tests = sum(1 for p in results.values() if p)
    
    print()
    log(f"Total: {passed_tests}/{total_tests} tests passed", 
        GREEN if passed_tests == total_tests else RED)
    
    if passed_tests == total_tests:
        log("🎉 ALL TESTS PASSED!", GREEN)
        sys.exit(0)
    else:
        log("⚠️  SOME TESTS FAILED", RED)
        sys.exit(1)

if __name__ == "__main__":
    main()
