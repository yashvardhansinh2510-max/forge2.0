"""
Comprehensive backend testing for Tile Orders redesign (Ground Floor Tiles module).
Tests the new workflow: Brand/Supplier page Release action + BuildCon Customer page
Move to Godown and Dispatch actions.
"""
import requests
import json
from typing import Optional

# Configuration
BASE_URL = "https://a8dd3b56-185f-4c7c-9980-087ebbbcdd31.preview.emergentagent.com/api"
LOGIN_EMAIL = "owner@forge.app"
LOGIN_PASSWORD = "Forge@2026"

# Global state
token = None
test_po_id = None
test_po_item_id = None
test_brand_id = None
test_customer_id = None
test_chalan_id = None

def login():
    """Authenticate and get JWT token"""
    global token
    print("\n" + "="*80)
    print("AUTHENTICATION")
    print("="*80)
    
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD}
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data.get("token") or data.get("access_token")
        print(f"✅ Login successful: {LOGIN_EMAIL}")
        if token:
            print(f"   Token: {token[:50]}...")
        else:
            print(f"   Warning: No token in response")
        return True
    else:
        print(f"❌ Login failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

def get_headers():
    """Get authorization headers"""
    return {"Authorization": f"Bearer {token}"}

def test_1_get_brands():
    """TEST 1: GET /api/tile-orders/brands - should return brands grouped by brand_id/brand_name"""
    global test_brand_id
    print("\n" + "="*80)
    print("TEST 1: GET /api/tile-orders/brands")
    print("="*80)
    
    response = requests.get(f"{BASE_URL}/tile-orders/brands", headers=get_headers())
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        brands = data.get("brands", [])
        print(f"✅ Brands endpoint working")
        print(f"   Total brands: {len(brands)}")
        
        if brands:
            # Verify shape
            first_brand = brands[0]
            required_keys = ["brand_id", "brand_name", "active_orders", "max_supplier_silent_days"]
            missing_keys = [k for k in required_keys if k not in first_brand]
            
            if missing_keys:
                print(f"❌ Missing keys in brand object: {missing_keys}")
            else:
                print(f"✅ Brand object shape correct")
            
            # Print sample brands
            for brand in brands[:5]:
                print(f"   - {brand.get('brand_name')}: {brand.get('active_orders')} active orders")
                if not test_brand_id and brand.get('active_orders', 0) > 0:
                    test_brand_id = brand.get('brand_id')
            
            if test_brand_id:
                print(f"\n   Selected test brand_id: {test_brand_id}")
        else:
            print("⚠️  No brands found")
        
        return True
    else:
        print(f"❌ Failed: {response.text}")
        return False

def test_2_get_brand_orders():
    """TEST 2: GET /api/tile-orders/brands/{brand_id}/orders - verify response shape"""
    global test_po_id, test_po_item_id
    print("\n" + "="*80)
    print(f"TEST 2: GET /api/tile-orders/brands/{test_brand_id}/orders")
    print("="*80)
    
    if not test_brand_id:
        print("⚠️  Skipping: No test_brand_id available")
        return False
    
    response = requests.get(
        f"{BASE_URL}/tile-orders/brands/{test_brand_id}/orders",
        headers=get_headers()
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Brand orders endpoint working")
        
        # Verify kpi exists
        if "kpi" in data:
            print(f"✅ KPI object present")
            kpi = data["kpi"]
            print(f"   Orders: {kpi.get('orders')}, Pending: {kpi.get('pending')}, Ready: {kpi.get('ready')}")
        else:
            print(f"❌ Missing 'kpi' in response")
        
        # Verify orders array
        orders = data.get("orders", [])
        print(f"   Total orders: {len(orders)}")
        
        if orders:
            first_order = orders[0]
            required_fields = ["boxes_released", "boxes_remaining", "arrival_date"]
            missing_fields = [f for f in required_fields if f not in first_order]
            
            if missing_fields:
                print(f"❌ Missing fields in order: {missing_fields}")
            else:
                print(f"✅ Order row has required fields")
            
            # Find a PO with boxes_pending > 0 for testing
            for order in orders:
                if order.get("boxes_remaining", 0) > 0:
                    test_po_id = order.get("po_id")
                    print(f"\n   Selected test PO: {order.get('po_number')} (boxes_remaining: {order.get('boxes_remaining')})")
                    break
        
        return True
    else:
        print(f"❌ Failed: {response.text}")
        return False

def test_3_get_purchase_order():
    """TEST 3: GET /api/tile-orders/purchase-orders/{po_id} - verify boxes_godown field"""
    global test_po_item_id, test_customer_id
    print("\n" + "="*80)
    print(f"TEST 3: GET /api/tile-orders/purchase-orders/{test_po_id}")
    print("="*80)
    
    if not test_po_id:
        print("⚠️  Skipping: No test_po_id available")
        return False
    
    response = requests.get(
        f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}",
        headers=get_headers()
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Purchase order endpoint working")
        print(f"   PO Number: {data.get('number')}")
        print(f"   Customer: {data.get('customer_name')}")
        print(f"   Brand: {data.get('brand_name')} (ID: {data.get('brand_id')})")
        
        # Get customer_id from customer orders list
        co_list_response = requests.get(
            f"{BASE_URL}/tile-orders/customer-orders",
            headers=get_headers()
        )
        if co_list_response.status_code == 200:
            orders = co_list_response.json().get("orders", [])
            if orders:
                test_customer_id = orders[0].get("id")  # Use first customer order's ID as customer_id
        
        # Verify brand_id and brand_name at top level
        if "brand_id" in data and "brand_name" in data:
            print(f"✅ brand_id and brand_name present at top level")
        else:
            print(f"❌ Missing brand_id or brand_name at top level")
        
        # Verify items have boxes_godown
        items = data.get("items", [])
        print(f"   Total items: {len(items)}")
        
        if items:
            first_item = items[0]
            if "boxes_godown" in first_item:
                print(f"✅ boxes_godown field present in items")
            else:
                print(f"❌ boxes_godown field missing in items")
            
            # Find an item with boxes_pending > 0 for release testing
            for item in items:
                if item.get("boxes_pending", 0) > 0:
                    test_po_item_id = item.get("id")
                    print(f"\n   Selected test item: {item.get('name')}")
                    print(f"   - boxes_pending: {item.get('boxes_pending')}")
                    print(f"   - boxes_ready: {item.get('boxes_ready')}")
                    print(f"   - boxes_godown: {item.get('boxes_godown')}")
                    print(f"   - boxes_dispatched: {item.get('boxes_dispatched')}")
                    break
        
        return True
    else:
        print(f"❌ Failed: {response.text}")
        return False

def test_4_mark_ready():
    """TEST 4: POST /api/tile-orders/purchase-orders/{po_id}/ready - Release action"""
    print("\n" + "="*80)
    print(f"TEST 4: POST /api/tile-orders/purchase-orders/{test_po_id}/ready")
    print("="*80)
    
    if not test_po_id or not test_po_item_id:
        print("⚠️  Skipping: No test_po_id or test_po_item_id available")
        return False
    
    # Get current state
    po_response = requests.get(
        f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}",
        headers=get_headers()
    )
    
    if po_response.status_code != 200:
        print(f"❌ Failed to get PO: {po_response.text}")
        return False
    
    po_data = po_response.json()
    item = next((i for i in po_data.get("items", []) if i["id"] == test_po_item_id), None)
    
    if not item:
        print(f"❌ Item not found in PO")
        return False
    
    boxes_pending_before = item.get("boxes_pending", 0)
    boxes_ready_before = item.get("boxes_ready", 0)
    
    if boxes_pending_before <= 0:
        print(f"⚠️  No boxes pending for this item, skipping release test")
        return False
    
    # Release 1 box (or less if only partial available)
    qty_to_release = min(1.0, boxes_pending_before)
    
    print(f"   Releasing {qty_to_release} boxes")
    print(f"   Before: boxes_pending={boxes_pending_before}, boxes_ready={boxes_ready_before}")
    
    response = requests.post(
        f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}/ready",
        headers=get_headers(),
        json={"items": [{"po_item_id": test_po_item_id, "qty": qty_to_release}]}
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Release successful")
        print(f"   Ready batches created: {len(data.get('ready_batches', []))}")
        
        # Verify state change
        po_response_after = requests.get(
            f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}",
            headers=get_headers()
        )
        
        if po_response_after.status_code == 200:
            po_data_after = po_response_after.json()
            item_after = next((i for i in po_data_after.get("items", []) if i["id"] == test_po_item_id), None)
            
            if item_after:
                boxes_pending_after = item_after.get("boxes_pending", 0)
                boxes_ready_after = item_after.get("boxes_ready", 0)
                
                print(f"   After: boxes_pending={boxes_pending_after}, boxes_ready={boxes_ready_after}")
                
                # Verify the math
                expected_pending = boxes_pending_before - qty_to_release
                expected_ready = boxes_ready_before + qty_to_release
                
                if abs(boxes_pending_after - expected_pending) < 0.01:
                    print(f"✅ boxes_pending decreased correctly")
                else:
                    print(f"❌ boxes_pending mismatch: expected {expected_pending}, got {boxes_pending_after}")
                
                if abs(boxes_ready_after - expected_ready) < 0.01:
                    print(f"✅ boxes_ready increased correctly")
                else:
                    print(f"❌ boxes_ready mismatch: expected {expected_ready}, got {boxes_ready_after}")
        
        # Check Material Movement Register
        print("\n   Checking Material Movement Register...")
        movements_response = requests.get(
            f"{BASE_URL}/tile-orders/movements?movement_type=release",
            headers=get_headers()
        )
        
        if movements_response.status_code == 200:
            movements_data = movements_response.json()
            rows = movements_data.get("rows", [])
            
            if rows:
                latest_movement = rows[0]  # Should be sorted by created_at desc
                print(f"✅ Movement register entry found")
                print(f"   - movement_type: {latest_movement.get('movement_type')}")
                print(f"   - customer_name: {latest_movement.get('customer_name')}")
                print(f"   - brand_name: {latest_movement.get('brand_name')}")
                print(f"   - tile_name: {latest_movement.get('tile_name')}")
                print(f"   - boxes: {latest_movement.get('boxes')}")
            else:
                print(f"⚠️  No movement entries found")
        
        return True
    else:
        print(f"❌ Failed: {response.text}")
        return False

def test_5_move_to_godown():
    """TEST 5: POST /api/tile-orders/purchase-orders/{po_id}/items/move-to-godown"""
    print("\n" + "="*80)
    print(f"TEST 5: POST /api/tile-orders/purchase-orders/{test_po_id}/items/move-to-godown")
    print("="*80)
    
    if not test_po_id or not test_po_item_id:
        print("⚠️  Skipping: No test_po_id or test_po_item_id available")
        return False
    
    # Get current state
    po_response = requests.get(
        f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}",
        headers=get_headers()
    )
    
    if po_response.status_code != 200:
        print(f"❌ Failed to get PO: {po_response.text}")
        return False
    
    po_data = po_response.json()
    item = next((i for i in po_data.get("items", []) if i["id"] == test_po_item_id), None)
    
    if not item:
        print(f"❌ Item not found in PO")
        return False
    
    boxes_ready_before = item.get("boxes_ready", 0)
    boxes_godown_before = item.get("boxes_godown", 0)
    
    if boxes_ready_before <= 0:
        print(f"⚠️  No boxes ready for this item, skipping move-to-godown test")
        return False
    
    # Move 0.5 boxes to godown (or less if only partial available)
    qty_to_move = min(0.5, boxes_ready_before)
    
    print(f"   Moving {qty_to_move} boxes to godown")
    print(f"   Before: boxes_ready={boxes_ready_before}, boxes_godown={boxes_godown_before}")
    
    response = requests.post(
        f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}/items/move-to-godown",
        headers=get_headers(),
        json={"items": [{"po_item_id": test_po_item_id, "qty": qty_to_move}]}
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Move to godown successful")
        print(f"   Moved items: {len(data.get('moved', []))}")
        
        # Verify state change
        po_response_after = requests.get(
            f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}",
            headers=get_headers()
        )
        
        if po_response_after.status_code == 200:
            po_data_after = po_response_after.json()
            item_after = next((i for i in po_data_after.get("items", []) if i["id"] == test_po_item_id), None)
            
            if item_after:
                boxes_ready_after = item_after.get("boxes_ready", 0)
                boxes_godown_after = item_after.get("boxes_godown", 0)
                
                print(f"   After: boxes_ready={boxes_ready_after}, boxes_godown={boxes_godown_after}")
                
                # Verify the math
                expected_ready = boxes_ready_before - qty_to_move
                expected_godown = boxes_godown_before + qty_to_move
                
                if abs(boxes_ready_after - expected_ready) < 0.01:
                    print(f"✅ boxes_ready decreased correctly")
                else:
                    print(f"❌ boxes_ready mismatch: expected {expected_ready}, got {boxes_ready_after}")
                
                if abs(boxes_godown_after - expected_godown) < 0.01:
                    print(f"✅ boxes_godown increased correctly")
                else:
                    print(f"❌ boxes_godown mismatch: expected {expected_godown}, got {boxes_godown_after}")
        
        # Verify NO chalan/dispatch was created
        print("\n   Verifying no chalan/dispatch created...")
        movements_response = requests.get(
            f"{BASE_URL}/tile-orders/movements?movement_type=move_to_godown",
            headers=get_headers()
        )
        
        if movements_response.status_code == 200:
            movements_data = movements_response.json()
            rows = movements_data.get("rows", [])
            
            if rows:
                latest_movement = rows[0]
                chalan_number = latest_movement.get("chalan_number")
                dispatch_number = latest_movement.get("dispatch_number")
                
                if not chalan_number and not dispatch_number:
                    print(f"✅ No chalan/dispatch created (as expected)")
                else:
                    print(f"❌ Unexpected chalan/dispatch: chalan={chalan_number}, dispatch={dispatch_number}")
            else:
                print(f"⚠️  No movement entries found")
        
        # Test error path: try to move more than available
        print("\n   Testing error path: move more than available...")
        error_response = requests.post(
            f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}/items/move-to-godown",
            headers=get_headers(),
            json={"items": [{"po_item_id": test_po_item_id, "qty": 9999}]}
        )
        
        if error_response.status_code == 400:
            print(f"✅ Error path working: 400 returned for excessive qty")
        else:
            print(f"❌ Error path failed: expected 400, got {error_response.status_code}")
        
        return True
    else:
        print(f"❌ Failed: {response.text}")
        return False

def test_6_dispatch_from_released():
    """TEST 6: POST /api/tile-orders/purchase-orders/{po_id}/dispatch-from-released"""
    global test_chalan_id
    print("\n" + "="*80)
    print(f"TEST 6: POST /api/tile-orders/purchase-orders/{test_po_id}/dispatch-from-released")
    print("="*80)
    
    if not test_po_id or not test_po_item_id:
        print("⚠️  Skipping: No test_po_id or test_po_item_id available")
        return False
    
    # Get current state
    po_response = requests.get(
        f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}",
        headers=get_headers()
    )
    
    if po_response.status_code != 200:
        print(f"❌ Failed to get PO: {po_response.text}")
        return False
    
    po_data = po_response.json()
    item = next((i for i in po_data.get("items", []) if i["id"] == test_po_item_id), None)
    
    if not item:
        print(f"❌ Item not found in PO")
        return False
    
    boxes_ready_before = item.get("boxes_ready", 0)
    boxes_dispatched_before = item.get("boxes_dispatched", 0)
    
    if boxes_ready_before <= 0:
        print(f"⚠️  No boxes ready for this item, skipping dispatch-from-released test")
        return False
    
    # Dispatch 0.5 boxes from released (or less if only partial available)
    qty_to_dispatch = min(0.5, boxes_ready_before)
    
    print(f"   Dispatching {qty_to_dispatch} boxes from released")
    print(f"   Before: boxes_ready={boxes_ready_before}, boxes_dispatched={boxes_dispatched_before}")
    
    response = requests.post(
        f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}/dispatch-from-released",
        headers=get_headers(),
        json={"items": [{"po_item_id": test_po_item_id, "qty": qty_to_dispatch}]}
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Dispatch from released successful")
        
        dispatch = data.get("dispatch", {})
        chalan = data.get("chalan", {})
        
        print(f"   Dispatch number: {dispatch.get('dispatch_number')}")
        print(f"   Chalan number: {chalan.get('number')}")
        
        test_chalan_id = chalan.get("id")
        
        # Verify state change
        po_response_after = requests.get(
            f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}",
            headers=get_headers()
        )
        
        if po_response_after.status_code == 200:
            po_data_after = po_response_after.json()
            item_after = next((i for i in po_data_after.get("items", []) if i["id"] == test_po_item_id), None)
            
            if item_after:
                boxes_ready_after = item_after.get("boxes_ready", 0)
                boxes_dispatched_after = item_after.get("boxes_dispatched", 0)
                
                print(f"   After: boxes_ready={boxes_ready_after}, boxes_dispatched={boxes_dispatched_after}")
                
                # Verify the math
                expected_ready = boxes_ready_before - qty_to_dispatch
                expected_dispatched = boxes_dispatched_before + qty_to_dispatch
                
                if abs(boxes_ready_after - expected_ready) < 0.01:
                    print(f"✅ boxes_ready decreased correctly")
                else:
                    print(f"❌ boxes_ready mismatch: expected {expected_ready}, got {boxes_ready_after}")
                
                if abs(boxes_dispatched_after - expected_dispatched) < 0.01:
                    print(f"✅ boxes_dispatched increased correctly")
                else:
                    print(f"❌ boxes_dispatched mismatch: expected {expected_dispatched}, got {boxes_dispatched_after}")
        
        # Test PDF generation
        if test_chalan_id:
            print(f"\n   Testing PDF generation for chalan {test_chalan_id}...")
            pdf_response = requests.get(
                f"{BASE_URL}/tile-orders/chalans/{test_chalan_id}/pdf",
                headers=get_headers()
            )
            
            if pdf_response.status_code == 200:
                content_type = pdf_response.headers.get("Content-Type", "")
                if "application/pdf" in content_type:
                    print(f"✅ PDF generated successfully (Content-Type: {content_type})")
                else:
                    print(f"❌ Wrong content type: {content_type}")
            else:
                print(f"❌ PDF generation failed: {pdf_response.status_code}")
        
        # Verify movement register
        print("\n   Checking Material Movement Register...")
        movements_response = requests.get(
            f"{BASE_URL}/tile-orders/movements?movement_type=dispatch_from_released",
            headers=get_headers()
        )
        
        if movements_response.status_code == 200:
            movements_data = movements_response.json()
            rows = movements_data.get("rows", [])
            
            if rows:
                latest_movement = rows[0]
                chalan_number = latest_movement.get("chalan_number")
                dispatch_number = latest_movement.get("dispatch_number")
                
                if chalan_number and dispatch_number:
                    print(f"✅ Movement register entry has chalan and dispatch numbers")
                    print(f"   - chalan_number: {chalan_number}")
                    print(f"   - dispatch_number: {dispatch_number}")
                else:
                    print(f"❌ Missing chalan or dispatch number in movement")
            else:
                print(f"⚠️  No movement entries found")
        
        # Test error path: dispatch more than available
        print("\n   Testing error path: dispatch more than available...")
        error_response = requests.post(
            f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}/dispatch-from-released",
            headers=get_headers(),
            json={"items": [{"po_item_id": test_po_item_id, "qty": 9999}]}
        )
        
        if error_response.status_code == 400:
            print(f"✅ Error path working: 400 returned for excessive qty")
        else:
            print(f"❌ Error path failed: expected 400, got {error_response.status_code}")
        
        return True
    else:
        print(f"❌ Failed: {response.text}")
        return False

def test_7_dispatch_from_godown():
    """TEST 7: POST /api/tile-orders/purchase-orders/{po_id}/dispatch-from-godown"""
    print("\n" + "="*80)
    print(f"TEST 7: POST /api/tile-orders/purchase-orders/{test_po_id}/dispatch-from-godown")
    print("="*80)
    
    if not test_po_id or not test_po_item_id:
        print("⚠️  Skipping: No test_po_id or test_po_item_id available")
        return False
    
    # Get current state
    po_response = requests.get(
        f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}",
        headers=get_headers()
    )
    
    if po_response.status_code != 200:
        print(f"❌ Failed to get PO: {po_response.text}")
        return False
    
    po_data = po_response.json()
    item = next((i for i in po_data.get("items", []) if i["id"] == test_po_item_id), None)
    
    if not item:
        print(f"❌ Item not found in PO")
        return False
    
    boxes_godown_before = item.get("boxes_godown", 0)
    boxes_dispatched_before = item.get("boxes_dispatched", 0)
    
    if boxes_godown_before <= 0:
        print(f"⚠️  No boxes in godown for this item, skipping dispatch-from-godown test")
        return False
    
    # Dispatch all boxes from godown
    qty_to_dispatch = boxes_godown_before
    
    print(f"   Dispatching {qty_to_dispatch} boxes from godown")
    print(f"   Before: boxes_godown={boxes_godown_before}, boxes_dispatched={boxes_dispatched_before}")
    
    response = requests.post(
        f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}/dispatch-from-godown",
        headers=get_headers(),
        json={"items": [{"po_item_id": test_po_item_id, "qty": qty_to_dispatch}]}
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Dispatch from godown successful")
        
        dispatch = data.get("dispatch", {})
        chalan = data.get("chalan", {})
        
        print(f"   Dispatch number: {dispatch.get('dispatch_number')}")
        print(f"   Chalan number: {chalan.get('number')}")
        print(f"   Source: {dispatch.get('source')}")
        
        # Verify state change
        po_response_after = requests.get(
            f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}",
            headers=get_headers()
        )
        
        if po_response_after.status_code == 200:
            po_data_after = po_response_after.json()
            item_after = next((i for i in po_data_after.get("items", []) if i["id"] == test_po_item_id), None)
            
            if item_after:
                boxes_godown_after = item_after.get("boxes_godown", 0)
                boxes_dispatched_after = item_after.get("boxes_dispatched", 0)
                
                print(f"   After: boxes_godown={boxes_godown_after}, boxes_dispatched={boxes_dispatched_after}")
                
                # Verify the math
                expected_godown = boxes_godown_before - qty_to_dispatch
                expected_dispatched = boxes_dispatched_before + qty_to_dispatch
                
                if abs(boxes_godown_after - expected_godown) < 0.01:
                    print(f"✅ boxes_godown decreased correctly")
                else:
                    print(f"❌ boxes_godown mismatch: expected {expected_godown}, got {boxes_godown_after}")
                
                if abs(boxes_dispatched_after - expected_dispatched) < 0.01:
                    print(f"✅ boxes_dispatched increased correctly")
                else:
                    print(f"❌ boxes_dispatched mismatch: expected {expected_dispatched}, got {boxes_dispatched_after}")
        
        # Verify PDF works
        chalan_id = chalan.get("id")
        if chalan_id:
            print(f"\n   Testing PDF generation for chalan {chalan_id}...")
            pdf_response = requests.get(
                f"{BASE_URL}/tile-orders/chalans/{chalan_id}/pdf",
                headers=get_headers()
            )
            
            if pdf_response.status_code == 200:
                content_type = pdf_response.headers.get("Content-Type", "")
                if "application/pdf" in content_type:
                    print(f"✅ PDF generated successfully")
                else:
                    print(f"❌ Wrong content type: {content_type}")
            else:
                print(f"❌ PDF generation failed: {pdf_response.status_code}")
        
        # Verify movement register
        print("\n   Checking Material Movement Register...")
        movements_response = requests.get(
            f"{BASE_URL}/tile-orders/movements?movement_type=dispatch_from_godown",
            headers=get_headers()
        )
        
        if movements_response.status_code == 200:
            movements_data = movements_response.json()
            rows = movements_data.get("rows", [])
            
            if rows:
                latest_movement = rows[0]
                print(f"✅ Movement register entry found")
                print(f"   - chalan_number: {latest_movement.get('chalan_number')}")
                print(f"   - dispatch_number: {latest_movement.get('dispatch_number')}")
            else:
                print(f"⚠️  No movement entries found")
        
        # Test error path: dispatch from empty godown
        print("\n   Testing error path: dispatch from empty godown...")
        error_response = requests.post(
            f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}/dispatch-from-godown",
            headers=get_headers(),
            json={"items": [{"po_item_id": test_po_item_id, "qty": 1}]}
        )
        
        if error_response.status_code == 400:
            print(f"✅ Error path working: 400 returned for empty godown")
        else:
            print(f"❌ Error path failed: expected 400, got {error_response.status_code}")
        
        return True
    else:
        print(f"❌ Failed: {response.text}")
        return False

def test_8_verify_invariant():
    """TEST 8: Verify invariant: qty == boxes_ready + boxes_godown + boxes_dispatched + boxes_pending"""
    print("\n" + "="*80)
    print("TEST 8: Verify invariant for touched item")
    print("="*80)
    
    if not test_po_id or not test_po_item_id:
        print("⚠️  Skipping: No test_po_id or test_po_item_id available")
        return False
    
    po_response = requests.get(
        f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}",
        headers=get_headers()
    )
    
    if po_response.status_code != 200:
        print(f"❌ Failed to get PO: {po_response.text}")
        return False
    
    po_data = po_response.json()
    item = next((i for i in po_data.get("items", []) if i["id"] == test_po_item_id), None)
    
    if not item:
        print(f"❌ Item not found in PO")
        return False
    
    qty = item.get("qty", 0)
    boxes_ready = item.get("boxes_ready", 0)
    boxes_godown = item.get("boxes_godown", 0)
    boxes_dispatched = item.get("boxes_dispatched", 0)
    boxes_pending = item.get("boxes_pending", 0)
    
    print(f"   Item: {item.get('name')}")
    print(f"   qty (ordered): {qty}")
    print(f"   boxes_ready: {boxes_ready}")
    print(f"   boxes_godown: {boxes_godown}")
    print(f"   boxes_dispatched: {boxes_dispatched}")
    print(f"   boxes_pending: {boxes_pending}")
    
    total = boxes_ready + boxes_godown + boxes_dispatched + boxes_pending
    print(f"   Sum: {total}")
    
    # Float-tolerant comparison
    if abs(qty - total) < 0.01:
        print(f"✅ Invariant holds: qty == boxes_ready + boxes_godown + boxes_dispatched + boxes_pending")
        return True
    else:
        print(f"❌ Invariant violated: qty ({qty}) != sum ({total}), diff = {abs(qty - total)}")
        return False

def test_9_customer_order_detail():
    """TEST 9: GET /api/tile-orders/customer-orders/{id} - verify brand_id/brand_name and boxes_godown"""
    print("\n" + "="*80)
    print("TEST 9: GET /api/tile-orders/customer-orders/{id}")
    print("="*80)
    
    if not test_po_id:
        print("⚠️  Skipping: No test_po_id available")
        return False
    
    # First get the PO to find the customer_order_id
    po_response = requests.get(
        f"{BASE_URL}/tile-orders/purchase-orders/{test_po_id}",
        headers=get_headers()
    )
    
    if po_response.status_code != 200:
        print(f"❌ Failed to get PO: {po_response.text}")
        return False
    
    po_data = po_response.json()
    
    # Get customer orders list to find one
    co_list_response = requests.get(
        f"{BASE_URL}/tile-orders/customer-orders",
        headers=get_headers()
    )
    
    if co_list_response.status_code != 200:
        print(f"❌ Failed to get customer orders list: {co_list_response.text}")
        return False
    
    co_list_data = co_list_response.json()
    orders = co_list_data.get("orders", [])
    
    if not orders:
        print(f"⚠️  No customer orders found")
        return False
    
    co_id = orders[0].get("id")
    
    print(f"   Testing customer order: {orders[0].get('number')}")
    
    response = requests.get(
        f"{BASE_URL}/tile-orders/customer-orders/{co_id}",
        headers=get_headers()
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Customer order detail endpoint working")
        
        suppliers = data.get("suppliers", [])
        print(f"   Suppliers/brands: {len(suppliers)}")
        
        if suppliers:
            first_supplier = suppliers[0]
            
            # Verify brand_id and brand_name
            if "brand_id" in first_supplier and "brand_name" in first_supplier:
                print(f"✅ brand_id and brand_name present in supplier group")
                print(f"   - brand_id: {first_supplier.get('brand_id')}")
                print(f"   - brand_name: {first_supplier.get('brand_name')}")
            else:
                print(f"❌ Missing brand_id or brand_name in supplier group")
            
            # Verify items have boxes_godown
            items = first_supplier.get("items", [])
            if items:
                first_item = items[0]
                if "boxes_godown" in first_item:
                    print(f"✅ boxes_godown field present in items")
                    print(f"   - boxes_godown: {first_item.get('boxes_godown')}")
                else:
                    print(f"❌ boxes_godown field missing in items")
        
        return True
    else:
        print(f"❌ Failed: {response.text}")
        return False

def test_10_movements_filtering():
    """TEST 10: GET /api/tile-orders/movements with brand_id and customer_id filters"""
    print("\n" + "="*80)
    print("TEST 10: GET /api/tile-orders/movements with filters")
    print("="*80)
    
    # Get test_customer_id from recent movements if not set
    global test_customer_id
    if not test_customer_id:
        movements_response = requests.get(
            f"{BASE_URL}/tile-orders/movements",
            headers=get_headers()
        )
        if movements_response.status_code == 200:
            rows = movements_response.json().get("rows", [])
            if rows:
                test_customer_id = rows[0].get("customer_id")
    
    if not test_brand_id:
        print(f"⚠️  Skipping: No test_brand_id available")
        return False
    
    # Test brand_id filter
    print(f"\n   Testing brand_id filter: {test_brand_id}")
    brand_response = requests.get(
        f"{BASE_URL}/tile-orders/movements?brand_id={test_brand_id}",
        headers=get_headers()
    )
    
    if brand_response.status_code == 200:
        brand_data = brand_response.json()
        rows = brand_data.get("rows", [])
        print(f"✅ Brand filter working: {len(rows)} movements found")
        
        # Verify all rows have the correct brand_id
        if rows:
            wrong_brand = [r for r in rows if r.get("brand_id") != test_brand_id]
            if wrong_brand:
                print(f"❌ Found {len(wrong_brand)} rows with wrong brand_id")
            else:
                print(f"✅ All rows have correct brand_id")
    else:
        print(f"❌ Brand filter failed: {brand_response.status_code}")
    
    # Test customer_id filter
    print(f"\n   Testing customer_id filter: {test_customer_id}")
    customer_response = requests.get(
        f"{BASE_URL}/tile-orders/movements?customer_id={test_customer_id}",
        headers=get_headers()
    )
    
    if customer_response.status_code == 200:
        customer_data = customer_response.json()
        rows = customer_data.get("rows", [])
        print(f"✅ Customer filter working: {len(rows)} movements found")
        
        # Verify all rows have the correct customer_id
        if rows:
            wrong_customer = [r for r in rows if r.get("customer_id") != test_customer_id]
            if wrong_customer:
                print(f"❌ Found {len(wrong_customer)} rows with wrong customer_id")
            else:
                print(f"✅ All rows have correct customer_id")
    else:
        print(f"❌ Customer filter failed: {customer_response.status_code}")
    
    return True

def test_11_regression_check():
    """TEST 11: Sanity-check pre-existing endpoints"""
    print("\n" + "="*80)
    print("TEST 11: Regression check on pre-existing endpoints")
    print("="*80)
    
    endpoints = [
        "/tile-orders/dashboard",
        "/tile-orders/customer-orders",
        "/tile-orders/suppliers"
    ]
    
    all_passed = True
    
    for endpoint in endpoints:
        response = requests.get(f"{BASE_URL}{endpoint}", headers=get_headers())
        
        if response.status_code == 200:
            print(f"✅ {endpoint}: 200 OK")
        else:
            print(f"❌ {endpoint}: {response.status_code}")
            all_passed = False
    
    return all_passed

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("TILE ORDERS BACKEND TESTING - WORKFLOW REDESIGN")
    print("BuildCon House - Ground Floor Tiles Module")
    print("="*80)
    
    if not login():
        print("\n❌ Authentication failed, cannot proceed with tests")
        return
    
    results = {
        "TEST 1: GET /api/tile-orders/brands": test_1_get_brands(),
        "TEST 2: GET /api/tile-orders/brands/{brand_id}/orders": test_2_get_brand_orders(),
        "TEST 3: GET /api/tile-orders/purchase-orders/{po_id}": test_3_get_purchase_order(),
        "TEST 4: POST /api/tile-orders/purchase-orders/{po_id}/ready": test_4_mark_ready(),
        "TEST 5: POST /api/tile-orders/purchase-orders/{po_id}/items/move-to-godown": test_5_move_to_godown(),
        "TEST 6: POST /api/tile-orders/purchase-orders/{po_id}/dispatch-from-released": test_6_dispatch_from_released(),
        "TEST 7: POST /api/tile-orders/purchase-orders/{po_id}/dispatch-from-godown": test_7_dispatch_from_godown(),
        "TEST 8: Verify invariant": test_8_verify_invariant(),
        "TEST 9: GET /api/tile-orders/customer-orders/{id}": test_9_customer_order_detail(),
        "TEST 10: GET /api/tile-orders/movements with filters": test_10_movements_filtering(),
        "TEST 11: Regression check": test_11_regression_check(),
    }
    
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\n{passed}/{total} tests passed ({passed*100//total}%)")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")

if __name__ == "__main__":
    main()
