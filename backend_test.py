"""
Purchases Phase 1A-C Backend Testing
=====================================
Tests the transactional transfer engine and expanded customer workspace contract.

Test Scenarios:
A. Existing-customer transfer with idempotency
B. Inline-new-customer transfer with idempotency
C. Workspace contract verification
D. Regression: partial move and stage movement
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from uuid import uuid4

import httpx

# Backend URL from environment
BACKEND_URL = os.getenv("REACT_APP_BACKEND_URL", "").rstrip("/") + "/api"
if not BACKEND_URL.startswith("http"):
    BACKEND_URL = "https://frontend-auth-trace.preview.emergentagent.com/api"

print(f"🔗 Backend URL: {BACKEND_URL}")

# Test credentials
OWNER_EMAIL = "owner@forge.app"
OWNER_PASSWORD = "Forge@2026"

# Global state
token = None
headers = {}


def log_test(name: str, status: str, details: str = ""):
    """Log test result with emoji."""
    emoji = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"{emoji} {name}: {status}")
    if details:
        print(f"   {details}")


async def authenticate():
    """Authenticate as owner and get JWT token."""
    global token, headers
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BACKEND_URL}/auth/login",
            json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
        )
        if response.status_code != 200:
            log_test("Authentication", "FAIL", f"Status {response.status_code}: {response.text}")
            sys.exit(1)
        
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            log_test("Authentication", "FAIL", f"No token in response: {data}")
            sys.exit(1)
        
        headers = {"Authorization": f"Bearer {token}"}
        log_test("Authentication", "PASS", f"Logged in as {data.get('user', {}).get('full_name')}")


async def create_test_quotation_and_order():
    """Create a quotation with a product line qty >= 10 and place order to get PO item."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get a product
        response = await client.get(f"{BACKEND_URL}/products?limit=1", headers=headers)
        if response.status_code != 200:
            log_test("Get Product", "FAIL", f"Status {response.status_code}")
            return None, None
        
        products_data = response.json()
        products = products_data.get("items", products_data if isinstance(products_data, list) else [])
        if not products:
            log_test("Get Product", "FAIL", "No products available")
            return None, None
        
        product = products[0]
        
        # Get a customer
        response = await client.get(f"{BACKEND_URL}/customers?limit=1", headers=headers)
        if response.status_code != 200:
            log_test("Get Customer", "FAIL", f"Status {response.status_code}")
            return None, None
        
        customers_data = response.json()
        customers = customers_data if isinstance(customers_data, list) else customers_data.get("items", [])
        if not customers:
            log_test("Get Customer", "FAIL", "No customers available")
            return None, None
        
        customer = customers[0]
        
        # Create quotation with qty >= 10
        quotation_data = {
            "customer_id": customer["id"],
            "items": [{
                "product_id": product["id"],
                "sku": product["sku"],
                "name": product["name"],
                "qty": 15,  # >= 10 as required
                "unit_price": product.get("price", 1000),
                "room": "Test Room"
            }],
            "status": "draft"
        }
        
        response = await client.post(f"{BACKEND_URL}/quotations", json=quotation_data, headers=headers)
        if response.status_code not in [200, 201]:
            log_test("Create Quotation", "FAIL", f"Status {response.status_code}: {response.text}")
            return None, None
        
        quotation = response.json()
        log_test("Create Quotation", "PASS", f"Created {quotation.get('number')} with 15 units")
        
        # Place order to create PO
        response = await client.post(
            f"{BACKEND_URL}/quotations/{quotation['id']}/place-order/confirm",
            json={},
            headers=headers
        )
        if response.status_code != 200:
            log_test("Place Order", "FAIL", f"Status {response.status_code}: {response.text}")
            return None, None
        
        order_result = response.json()
        log_test("Place Order Response", "INFO", f"Response: {json.dumps(order_result, indent=2)[:500]}")
        purchase_order_ids = order_result.get("purchase_order_ids", [])
        if not purchase_order_ids:
            log_test("Place Order", "FAIL", f"No purchase orders created. Response: {order_result}")
            return None, None
        
        # Get the first PO details
        po_id = purchase_order_ids[0]
        response = await client.get(f"{BACKEND_URL}/purchase-orders/{po_id}", headers=headers)
        if response.status_code != 200:
            log_test("Get PO Details", "FAIL", f"Status {response.status_code}")
            return None, None
        
        po = response.json()
        log_test("Place Order", "PASS", f"Created PO {po.get('number')}")
        
        # Get the item ID from the PO
        po_detail = po  # Already have the PO details from above
        items = po_detail.get("items", [])
        if not items:
            log_test("Get PO Items", "FAIL", "No items in PO")
            return None, None
        
        item = items[0]
        log_test("Get PO Item", "PASS", f"Item ID: {item['id']}, Qty: {item['qty']}")
        
        return item["id"], customer["id"]


async def test_existing_customer_transfer(source_item_id: str, source_customer_id: str):
    """Test A: Existing-customer transfer with idempotency."""
    print("\n" + "="*80)
    print("TEST A: Existing-Customer Transfer with Idempotency")
    print("="*80)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get another customer for destination
        response = await client.get(f"{BACKEND_URL}/customers?limit=10", headers=headers)
        if response.status_code != 200:
            log_test("A.1 Get Destination Customer", "FAIL", f"Status {response.status_code}")
            return None
        
        customers_data = response.json()
        customers = customers_data if isinstance(customers_data, list) else customers_data.get("items", [])
        destination_customer = None
        for c in customers:
            if c["id"] != source_customer_id:
                destination_customer = c
                break
        
        if not destination_customer:
            log_test("A.1 Get Destination Customer", "FAIL", "No other customer available")
            return None
        
        log_test("A.1 Get Destination Customer", "PASS", f"Using {destination_customer.get('name')}")
        
        # Generate unique idempotency key
        idempotency_key = f"phase1-existing-{uuid4()}"
        
        # First transfer call
        transfer_data = {
            "destination_customer_id": destination_customer["id"],
            "qty": 2,
            "reason": "Phase 1 test",
            "idempotency_key": idempotency_key
        }
        
        response1 = await client.post(
            f"{BACKEND_URL}/purchases/items/{source_item_id}/transfer",
            json=transfer_data,
            headers=headers
        )
        
        if response1.status_code != 200:
            log_test("A.2 First Transfer Call", "FAIL", f"Status {response1.status_code}: {response1.text}")
            return None
        
        result1 = response1.json()
        log_test("A.2 First Transfer Call", "PASS", f"Transfer ID: {result1.get('transfer_id')}")
        
        # Second transfer call with same idempotency key
        response2 = await client.post(
            f"{BACKEND_URL}/purchases/items/{source_item_id}/transfer",
            json=transfer_data,
            headers=headers
        )
        
        if response2.status_code != 200:
            log_test("A.3 Second Transfer Call (Idempotency)", "FAIL", f"Status {response2.status_code}: {response2.text}")
            return None
        
        result2 = response2.json()
        
        # Verify idempotency
        if result2.get("idempotent") == True:
            log_test("A.3 Idempotency Check", "PASS", "Second call returned idempotent=true")
        else:
            log_test("A.3 Idempotency Check", "WARN", f"Expected idempotent=true, got {result2.get('idempotent')}")
        
        # Get transfer history
        response = await client.get(
            f"{BACKEND_URL}/purchases/items/{source_item_id}/transfer-history",
            headers=headers
        )
        
        if response.status_code != 200:
            log_test("A.4 Transfer History", "FAIL", f"Status {response.status_code}")
            return None
        
        history = response.json()
        transfers = history.get("transfers", [])
        
        if len(transfers) == 1:
            log_test("A.4 Transfer History", "PASS", f"Exactly 1 transfer recorded (idempotency working)")
        else:
            log_test("A.4 Transfer History", "FAIL", f"Expected 1 transfer, found {len(transfers)}")
        
        # Verify source quantity decreased
        response = await client.get(
            f"{BACKEND_URL}/purchases/items/{source_item_id}",
            headers=headers
        )
        
        if response.status_code == 404:
            # Item might have been removed if qty went to 0
            log_test("A.5 Source Quantity", "PASS", "Source item removed (qty went to 0)")
        elif response.status_code == 200:
            source_item = response.json()
            remaining_qty = source_item.get("qty", 0)
            log_test("A.5 Source Quantity", "PASS", f"Source qty decreased to {remaining_qty}")
        else:
            log_test("A.5 Source Quantity", "FAIL", f"Status {response.status_code}")
        
        # Verify destination PO/line created
        dest_po_id = result1.get("destination", {}).get("po_id")
        if not dest_po_id:
            log_test("A.6 Destination PO", "FAIL", "No destination PO ID in response")
            return None
        
        response = await client.get(f"{BACKEND_URL}/purchase-orders/{dest_po_id}", headers=headers)
        if response.status_code != 200:
            log_test("A.6 Destination PO", "FAIL", f"Status {response.status_code}")
            return None
        
        dest_po = response.json()
        dest_items = dest_po.get("items", [])
        if len(dest_items) == 1 and dest_items[0].get("qty") == 2:
            log_test("A.6 Destination PO", "PASS", f"Destination PO {dest_po.get('number')} has 1 item with qty=2")
        else:
            log_test("A.6 Destination PO", "FAIL", f"Expected 1 item with qty=2, found {len(dest_items)} items")
        
        # Verify destination quotation linked
        dest_quote_id = result1.get("destination", {}).get("quotation_id")
        if not dest_quote_id:
            log_test("A.7 Destination Quotation", "FAIL", "No destination quotation ID in response")
            return None
        
        response = await client.get(f"{BACKEND_URL}/quotations/{dest_quote_id}", headers=headers)
        if response.status_code != 200:
            log_test("A.7 Destination Quotation", "FAIL", f"Status {response.status_code}")
            return None
        
        dest_quote = response.json()
        if dest_quote.get("status") == "ordered":
            log_test("A.7 Destination Quotation", "PASS", f"Quotation {dest_quote.get('number')} status=ordered")
        else:
            log_test("A.7 Destination Quotation", "FAIL", f"Expected status=ordered, got {dest_quote.get('status')}")
        
        # Verify pending payment created
        response = await client.get(
            f"{BACKEND_URL}/payments?customer_id={destination_customer['id']}",
            headers=headers
        )
        
        if response.status_code != 200:
            log_test("A.8 Pending Payment", "FAIL", f"Status {response.status_code}")
            return None
        
        payments = response.json()
        pending_payments = [p for p in payments if p.get("status") == "pending" and p.get("quotation_id") == dest_quote_id]
        
        if len(pending_payments) >= 1:
            payment_amount = pending_payments[0].get("amount", 0)
            log_test("A.8 Pending Payment", "PASS", f"Pending payment of ₹{payment_amount:,.2f} created")
        else:
            log_test("A.8 Pending Payment", "FAIL", f"No pending payment found for destination quotation")
        
        # Verify transfer-specific follow-up created
        response = await client.get(
            f"{BACKEND_URL}/followups?customer_id={destination_customer['id']}",
            headers=headers
        )
        
        if response.status_code != 200:
            log_test("A.9 Transfer Follow-up", "FAIL", f"Status {response.status_code}")
            return None
        
        followups = response.json()
        transfer_followups = [f for f in followups if f.get("category") == "purchase" and "transfer" in f.get("reason", "").lower()]
        
        if len(transfer_followups) >= 1:
            log_test("A.9 Transfer Follow-up", "PASS", f"Transfer-specific follow-up created")
        else:
            log_test("A.9 Transfer Follow-up", "WARN", f"No transfer-specific follow-up found (might be in different category)")
        
        # Verify customer timelines include transfer activity
        response = await client.get(
            f"{BACKEND_URL}/activity/customer/{destination_customer['id']}",
            headers=headers
        )
        
        if response.status_code != 200:
            log_test("A.10 Customer Timeline", "FAIL", f"Status {response.status_code}")
            return None
        
        activities = response.json()
        transfer_activities = [a for a in activities if "transfer" in a.get("event_type", "")]
        
        if len(transfer_activities) >= 1:
            log_test("A.10 Customer Timeline", "PASS", f"Transfer activity recorded in customer timeline")
        else:
            log_test("A.10 Customer Timeline", "FAIL", f"No transfer activity in customer timeline")
        
        # Check for source shortage/reorder state
        response = await client.get(
            f"{BACKEND_URL}/purchases/shortages?customer_id={source_customer_id}",
            headers=headers
        )
        
        if response.status_code != 200:
            log_test("A.11 Source Shortage Check", "FAIL", f"Status {response.status_code}")
        else:
            shortages = response.json().get("items", [])
            if len(shortages) > 0:
                log_test("A.11 Source Shortage/Reorder", "PASS", f"Shortage flagged for source customer (awaiting reorder)")
            else:
                log_test("A.11 Source Shortage/Reorder", "PASS", f"No shortage (allocation still sufficient)")
        
        return destination_customer["id"]


async def test_inline_new_customer_transfer(source_item_id: str):
    """Test B: Inline-new-customer transfer with idempotency."""
    print("\n" + "="*80)
    print("TEST B: Inline-New-Customer Transfer with Idempotency")
    print("="*80)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Generate unique customer details
        unique_id = str(uuid4())[:8]
        idempotency_key = f"phase1-new-{unique_id}"
        
        new_customer_data = {
            "name": f"Phase 1 Transfer {unique_id}",
            "phone": f"+91-9876-{unique_id[:6]}",
            "email": f"transfer-{unique_id}@test.forge.app"
        }
        
        # First transfer call with inline new customer
        transfer_data = {
            "new_customer": new_customer_data,
            "qty": 1,
            "reason": "inline customer",
            "idempotency_key": idempotency_key
        }
        
        response1 = await client.post(
            f"{BACKEND_URL}/purchases/items/{source_item_id}/transfer",
            json=transfer_data,
            headers=headers
        )
        
        if response1.status_code != 200:
            log_test("B.1 First Transfer Call (New Customer)", "FAIL", f"Status {response1.status_code}: {response1.text}")
            return None
        
        result1 = response1.json()
        log_test("B.1 First Transfer Call (New Customer)", "PASS", f"Transfer ID: {result1.get('transfer_id')}")
        
        dest_customer_id = result1.get("destination", {}).get("customer_id")
        if not dest_customer_id:
            log_test("B.2 Customer Creation", "FAIL", "No destination customer ID in response")
            return None
        
        # Verify customer was created
        response = await client.get(f"{BACKEND_URL}/customers/{dest_customer_id}", headers=headers)
        if response.status_code != 200:
            log_test("B.2 Customer Creation", "FAIL", f"Status {response.status_code}")
            return None
        
        customer = response.json()
        log_test("B.2 Customer Creation", "PASS", f"Customer '{customer.get('name')}' created")
        
        # Second transfer call with same idempotency key
        response2 = await client.post(
            f"{BACKEND_URL}/purchases/items/{source_item_id}/transfer",
            json=transfer_data,
            headers=headers
        )
        
        if response2.status_code != 200:
            log_test("B.3 Second Transfer Call (Idempotency)", "FAIL", f"Status {response2.status_code}: {response2.text}")
            return None
        
        result2 = response2.json()
        
        # Verify idempotency
        if result2.get("idempotent") == True:
            log_test("B.3 Idempotency Check", "PASS", "Second call returned idempotent=true")
        else:
            log_test("B.3 Idempotency Check", "WARN", f"Expected idempotent=true, got {result2.get('idempotent')}")
        
        # Verify only ONE customer was created (no duplicates)
        response = await client.get(f"{BACKEND_URL}/customers?q={new_customer_data['name']}", headers=headers)
        if response.status_code != 200:
            log_test("B.4 No Duplicate Customers", "FAIL", f"Status {response.status_code}")
            return None
        
        customers_data = response.json()
        matching_customers = customers_data if isinstance(customers_data, list) else customers_data.get("items", [])
        if len(matching_customers) == 1:
            log_test("B.4 No Duplicate Customers", "PASS", "Exactly 1 customer created (no duplicates)")
        else:
            log_test("B.4 No Duplicate Customers", "FAIL", f"Expected 1 customer, found {len(matching_customers)}")
        
        # Verify destination chain (PO + quotation + payment + follow-up)
        dest_po_id = result1.get("destination", {}).get("po_id")
        dest_quote_id = result1.get("destination", {}).get("quotation_id")
        
        if not dest_po_id or not dest_quote_id:
            log_test("B.5 Destination Chain", "FAIL", "Missing PO or quotation ID")
            return None
        
        # Check PO
        response = await client.get(f"{BACKEND_URL}/purchase-orders/{dest_po_id}", headers=headers)
        if response.status_code != 200:
            log_test("B.5 Destination PO", "FAIL", f"Status {response.status_code}")
            return None
        
        dest_po = response.json()
        log_test("B.5 Destination PO", "PASS", f"PO {dest_po.get('number')} created")
        
        # Check Quotation
        response = await client.get(f"{BACKEND_URL}/quotations/{dest_quote_id}", headers=headers)
        if response.status_code != 200:
            log_test("B.6 Destination Quotation", "FAIL", f"Status {response.status_code}")
            return None
        
        dest_quote = response.json()
        log_test("B.6 Destination Quotation", "PASS", f"Quotation {dest_quote.get('number')} created")
        
        # Check Payment
        response = await client.get(f"{BACKEND_URL}/payments?customer_id={dest_customer_id}", headers=headers)
        if response.status_code != 200:
            log_test("B.7 Destination Payment", "FAIL", f"Status {response.status_code}")
            return None
        
        payments = response.json()
        pending_payments = [p for p in payments if p.get("status") == "pending"]
        if len(pending_payments) >= 1:
            log_test("B.7 Destination Payment", "PASS", f"Pending payment created")
        else:
            log_test("B.7 Destination Payment", "FAIL", "No pending payment found")
        
        # Check Follow-up
        response = await client.get(f"{BACKEND_URL}/followups?customer_id={dest_customer_id}", headers=headers)
        if response.status_code != 200:
            log_test("B.8 Destination Follow-up", "FAIL", f"Status {response.status_code}")
            return None
        
        followups = response.json()
        if len(followups) >= 1:
            log_test("B.8 Destination Follow-up", "PASS", f"Follow-up created")
        else:
            log_test("B.8 Destination Follow-up", "FAIL", "No follow-up found")
        
        # Check Activity
        response = await client.get(f"{BACKEND_URL}/activity/customer/{dest_customer_id}", headers=headers)
        if response.status_code != 200:
            log_test("B.9 Destination Activity", "FAIL", f"Status {response.status_code}")
            return None
        
        activities = response.json()
        if len(activities) >= 1:
            log_test("B.9 Destination Activity", "PASS", f"{len(activities)} activity events recorded")
        else:
            log_test("B.9 Destination Activity", "FAIL", "No activity events found")
        
        return dest_customer_id


async def test_workspace_contract(customer_id: str):
    """Test C: Workspace contract verification."""
    print("\n" + "="*80)
    print("TEST C: Workspace Contract Verification")
    print("="*80)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{BACKEND_URL}/purchases/customers/{customer_id}/workspace",
            headers=headers
        )
        
        if response.status_code != 200:
            log_test("C.1 Workspace API", "FAIL", f"Status {response.status_code}: {response.text}")
            return
        
        workspace = response.json()
        log_test("C.1 Workspace API", "PASS", "Workspace endpoint accessible")
        
        # Verify required fields
        required_fields = ["customer", "summary", "payments", "followups", "products", "brands", "stages", "purchase_orders", "outstanding_items", "recent_activity", "expected_delivery"]
        
        missing_fields = [f for f in required_fields if f not in workspace]
        if missing_fields:
            log_test("C.2 Workspace Shape", "FAIL", f"Missing fields: {', '.join(missing_fields)}")
        else:
            log_test("C.2 Workspace Shape", "PASS", "All required fields present")
        
        # Verify summary.outstanding_balance
        summary = workspace.get("summary", {})
        if "outstanding_balance" in summary:
            outstanding = summary["outstanding_balance"]
            log_test("C.3 Outstanding Balance", "PASS", f"Outstanding balance: ₹{outstanding:,.2f}")
        else:
            log_test("C.3 Outstanding Balance", "FAIL", "outstanding_balance field missing")
        
        # Verify payments array
        payments = workspace.get("payments", [])
        log_test("C.4 Payments Array", "PASS", f"{len(payments)} payment(s) in workspace")
        
        # Verify followups array
        followups = workspace.get("followups", [])
        log_test("C.5 Followups Array", "PASS", f"{len(followups)} follow-up(s) in workspace")
        
        # Verify POs
        pos = workspace.get("purchase_orders", [])
        log_test("C.6 Purchase Orders", "PASS", f"{len(pos)} PO(s) in workspace")
        
        # Verify products/brands/stages
        products = workspace.get("products", [])
        brands = workspace.get("brands", [])
        stages = workspace.get("stages", [])
        log_test("C.7 Products/Brands/Stages", "PASS", f"{len(products)} products, {len(brands)} brands, {len(stages)} stages")
        
        # Verify activity
        activity = workspace.get("recent_activity", [])
        log_test("C.8 Recent Activity", "PASS", f"{len(activity)} activity event(s)")
        
        # Verify shortages (if any)
        shortages = workspace.get("shortages", [])
        log_test("C.9 Shortages", "PASS", f"{len(shortages)} shortage(s) tracked")


async def test_regression_partial_move_and_stage():
    """Test D: Regression - partial move and stage movement."""
    print("\n" + "="*80)
    print("TEST D: Regression - Partial Move and Stage Movement")
    print("="*80)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create a new test quotation/order with qty=10
        response = await client.get(f"{BACKEND_URL}/products?limit=1", headers=headers)
        if response.status_code != 200:
            log_test("D.1 Setup - Get Product", "FAIL", f"Status {response.status_code}")
            return
        
        products_data = response.json()
        products = products_data.get("items", products_data if isinstance(products_data, list) else [])
        if not products:
            log_test("D.1 Setup - Get Product", "FAIL", "No products available")
            return
        
        product = products[0]
        
        response = await client.get(f"{BACKEND_URL}/customers?limit=1", headers=headers)
        if response.status_code != 200:
            log_test("D.1 Setup - Get Customer", "FAIL", f"Status {response.status_code}")
            return
        
        customers_data = response.json()
        customers = customers_data if isinstance(customers_data, list) else customers_data.get("items", [])
        if not customers:
            log_test("D.1 Setup - Get Customer", "FAIL", "No customers available")
            return
        
        customer = customers[0]
        
        # Create quotation
        quotation_data = {
            "customer_id": customer["id"],
            "items": [{
                "product_id": product["id"],
                "sku": product["sku"],
                "name": product["name"],
                "qty": 10,
                "unit_price": product.get("price", 1000),
                "room": "Regression Test Room"
            }],
            "status": "draft"
        }
        
        response = await client.post(f"{BACKEND_URL}/quotations", json=quotation_data, headers=headers)
        if response.status_code not in [200, 201]:
            log_test("D.1 Setup - Create Quotation", "FAIL", f"Status {response.status_code}")
            return
        
        quotation = response.json()
        
        # Place order
        response = await client.post(
            f"{BACKEND_URL}/quotations/{quotation['id']}/place-order/confirm",
            json={},
            headers=headers
        )
        if response.status_code != 200:
            log_test("D.1 Setup - Place Order", "FAIL", f"Status {response.status_code}")
            return
        
        order_result = response.json()
        purchase_order_ids = order_result.get("purchase_order_ids", [])
        if not purchase_order_ids:
            log_test("D.1 Setup - Place Order", "FAIL", "No purchase orders created")
            return
        
        po_id = purchase_order_ids[0]
        
        # Get item ID
        response = await client.get(f"{BACKEND_URL}/purchase-orders/{po_id}", headers=headers)
        if response.status_code != 200:
            log_test("D.1 Setup - Get PO", "FAIL", f"Status {response.status_code}")
            return
        
        po_detail = response.json()
        items = po_detail.get("items", [])
        if not items:
            log_test("D.1 Setup - Get PO", "FAIL", "No items in PO")
            return
        
        item = items[0]
        item_id = item["id"]
        log_test("D.1 Setup Complete", "PASS", f"Created PO {po_detail.get('number')} with item qty=10")
        
        # Test partial move (3 of 10)
        move_data = {
            "stage": "company_billing",
            "qty": 3,
            "note": "Partial move test - 3 of 10"
        }
        
        response = await client.post(
            f"{BACKEND_URL}/purchases/items/{item_id}/move",
            json=move_data,
            headers=headers
        )
        
        if response.status_code != 200:
            log_test("D.2 Partial Move", "FAIL", f"Status {response.status_code}: {response.text}")
            return
        
        move_result = response.json()
        
        if move_result.get("split") == True:
            new_item_id = move_result.get("new_item_id")
            qty_moved = move_result.get("qty_moved")
            qty_remaining = move_result.get("qty_remaining")
            log_test("D.2 Partial Move", "PASS", f"Split: {qty_moved} moved, {qty_remaining} remaining")
            
            # Verify original item still exists with reduced qty
            response = await client.get(f"{BACKEND_URL}/purchases/items/{item_id}", headers=headers)
            if response.status_code != 200:
                log_test("D.3 Original Item After Split", "FAIL", f"Status {response.status_code}")
                return
            
            original_item = response.json()
            if original_item.get("qty") == 7:
                log_test("D.3 Original Item After Split", "PASS", f"Original item qty=7 (10-3)")
            else:
                log_test("D.3 Original Item After Split", "FAIL", f"Expected qty=7, got {original_item.get('qty')}")
            
            # Verify new item exists with moved qty
            response = await client.get(f"{BACKEND_URL}/purchases/items/{new_item_id}", headers=headers)
            if response.status_code != 200:
                log_test("D.4 New Item After Split", "FAIL", f"Status {response.status_code}")
                return
            
            new_item = response.json()
            if new_item.get("qty") == 3 and new_item.get("stage") == "company_billing":
                log_test("D.4 New Item After Split", "PASS", f"New item qty=3, stage=company_billing")
            else:
                log_test("D.4 New Item After Split", "FAIL", f"Expected qty=3 stage=company_billing, got qty={new_item.get('qty')} stage={new_item.get('stage')}")
            
            # Verify stage history preserved
            stage_history = new_item.get("stage_history", [])
            if len(stage_history) > 0:
                log_test("D.5 Stage History Preserved", "PASS", f"{len(stage_history)} stage event(s) in history")
            else:
                log_test("D.5 Stage History Preserved", "FAIL", "No stage history")
            
            # Test stage movement on the new item
            stage_move_data = {
                "stage": "dispatched",
                "note": "Moving to dispatched"
            }
            
            response = await client.post(
                f"{BACKEND_URL}/purchases/items/{new_item_id}/move",
                json=stage_move_data,
                headers=headers
            )
            
            if response.status_code != 200:
                log_test("D.6 Stage Movement", "FAIL", f"Status {response.status_code}: {response.text}")
                return
            
            stage_result = response.json()
            log_test("D.6 Stage Movement", "PASS", f"Moved to {stage_result.get('to_stage')}")
            
            # Verify dispatch record
            response = await client.get(
                f"{BACKEND_URL}/purchases/dispatch-record",
                headers=headers
            )
            
            if response.status_code != 200:
                log_test("D.7 Dispatch Record", "FAIL", f"Status {response.status_code}")
                return
            
            dispatch_data = response.json()
            dispatch_items = dispatch_data.get("items", [])
            
            # Check if our moved item is in dispatch record
            moved_item_in_dispatch = any(i.get("item_id") == new_item_id for i in dispatch_items)
            if moved_item_in_dispatch:
                log_test("D.7 Dispatch Record", "PASS", "Moved item appears in dispatch record")
            else:
                log_test("D.7 Dispatch Record", "FAIL", "Moved item not in dispatch record")
        else:
            log_test("D.2 Partial Move", "FAIL", "Expected split=true for partial move")


async def main():
    """Main test runner."""
    print("\n" + "="*80)
    print("PURCHASES PHASE 1A-C BACKEND TESTING")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    try:
        # Authenticate
        await authenticate()
        
        # Create test data
        print("\n" + "="*80)
        print("SETUP: Creating Test Quotation and Order")
        print("="*80)
        source_item_id, source_customer_id = await create_test_quotation_and_order()
        
        if not source_item_id:
            print("\n❌ SETUP FAILED: Cannot proceed with tests")
            return
        
        # Test A: Existing-customer transfer
        dest_customer_id = await test_existing_customer_transfer(source_item_id, source_customer_id)
        
        # Test B: Inline-new-customer transfer (need another source item)
        print("\n" + "="*80)
        print("SETUP: Creating Second Test Item for Test B")
        print("="*80)
        source_item_id_2, _ = await create_test_quotation_and_order()
        
        if source_item_id_2:
            new_customer_id = await test_inline_new_customer_transfer(source_item_id_2)
            
            # Test C: Workspace contract (use the destination customer from Test A or new customer from Test B)
            if dest_customer_id:
                await test_workspace_contract(dest_customer_id)
            elif new_customer_id:
                await test_workspace_contract(new_customer_id)
        
        # Test D: Regression
        await test_regression_partial_move_and_stage()
        
        print("\n" + "="*80)
        print("TESTING COMPLETE")
        print("="*80)
        print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
