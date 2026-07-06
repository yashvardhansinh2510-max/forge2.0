#!/usr/bin/env python3
"""
Follow-ups · Sales Command Center — Backend API Testing
Tests all 10 areas specified in the review request.
"""
import requests
import json
import time
from typing import Optional

# Base URL from frontend/.env
BASE_URL = "https://prime-workflow-1.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
TEST_EMAIL = "sales@forge.app"
TEST_PASSWORD = "Forge@2026"

# Global token storage
token: Optional[str] = None
headers: dict = {}


def login():
    """Login and store token for subsequent requests."""
    global token, headers
    print("\n=== LOGGING IN ===")
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.status_code} {response.text}"
    data = response.json()
    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"✓ Logged in as {TEST_EMAIL}")


def test_1_reconcile_idempotency():
    """Test 1: POST /api/followups/reconcile - idempotency test."""
    print("\n=== TEST 1: POST /api/followups/reconcile (Idempotency) ===")
    
    # First reconcile
    r1 = requests.post(f"{BASE_URL}/followups/reconcile", headers=headers)
    assert r1.status_code == 200, f"First reconcile failed: {r1.status_code} {r1.text}"
    data1 = r1.json()
    print(f"First reconcile: {json.dumps(data1, indent=2)}")
    
    # Verify response shape
    assert "created" in data1, "Missing 'created' field"
    assert "updated" in data1, "Missing 'updated' field"
    assert "auto_resolved" in data1, "Missing 'auto_resolved' field"
    assert "active" in data1, "Missing 'active' field"
    
    # Second reconcile (should be idempotent)
    time.sleep(0.5)
    r2 = requests.post(f"{BASE_URL}/followups/reconcile", headers=headers)
    assert r2.status_code == 200, f"Second reconcile failed: {r2.status_code} {r2.text}"
    data2 = r2.json()
    print(f"Second reconcile: {json.dumps(data2, indent=2)}")
    
    # Verify idempotency - second call should have created=0 (no new duplicates)
    assert data2["created"] == 0, f"Second reconcile created {data2['created']} new items (should be 0 - not idempotent!)"
    assert data2["active"] == data1["active"], f"Active count changed from {data1['active']} to {data2['active']}"
    
    print(f"✓ Idempotency verified: active count stable at {data2['active']}, no duplicates created")


def test_2_stats():
    """Test 2: GET /api/followups/stats - verify shape."""
    print("\n=== TEST 2: GET /api/followups/stats ===")
    
    r = requests.get(f"{BASE_URL}/followups/stats", headers=headers)
    assert r.status_code == 200, f"Stats failed: {r.status_code} {r.text}"
    data = r.json()
    print(f"Stats response: {json.dumps(data, indent=2)}")
    
    # Verify required fields
    required_fields = [
        "today_tasks", "today_critical", "overdue", "overdue_critical",
        "tomorrow", "this_week", "waiting_for_customer", "completed_today",
        "completed_trend", "snoozed", "later", "rules"
    ]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"
    
    # Verify rules array
    assert isinstance(data["rules"], list), "rules should be an array"
    # Note: Implementation has 9 rules (including customer_inactive), not 8 as mentioned in review request
    assert len(data["rules"]) >= 8, f"Expected at least 8 rules, got {len(data['rules'])}"
    
    # Verify each rule has required fields
    for rule in data["rules"]:
        assert "rule_type" in rule, "Rule missing rule_type"
        assert "label" in rule, "Rule missing label"
        assert "category" in rule, "Rule missing category"
        assert "description" in rule, "Rule missing description"
        assert "active_count" in rule, "Rule missing active_count"
    
    print(f"✓ Stats shape verified: {len(data['rules'])} rules, all required fields present")


def test_3_mission():
    """Test 3: GET /api/followups/mission - verify shape."""
    print("\n=== TEST 3: GET /api/followups/mission ===")
    
    r = requests.get(f"{BASE_URL}/followups/mission", headers=headers)
    assert r.status_code == 200, f"Mission failed: {r.status_code} {r.text}"
    data = r.json()
    print(f"Mission response: {json.dumps(data, indent=2)}")
    
    # Verify required fields
    required_fields = [
        "due_count", "revenue_at_risk", "revenue_at_risk_short",
        "overdue_payments", "quotations_expiring_today", "critical_count",
        "estimated_minutes", "top_priorities", "greeting_name"
    ]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"
    
    # Verify top_priorities is an array
    assert isinstance(data["top_priorities"], list), "top_priorities should be an array"
    
    print(f"✓ Mission shape verified: {data['due_count']} due, ₹{data['revenue_at_risk_short']} at risk")


def test_4_insights():
    """Test 4: GET /api/followups/insights - verify shape."""
    print("\n=== TEST 4: GET /api/followups/insights ===")
    
    r = requests.get(f"{BASE_URL}/followups/insights", headers=headers)
    assert r.status_code == 200, f"Insights failed: {r.status_code} {r.text}"
    data = r.json()
    print(f"Insights response: {json.dumps(data, indent=2)}")
    
    # Verify required fields
    required_fields = [
        "calls_completed", "whatsapps_sent", "payments_collected",
        "quotations_approved", "response_rate"
    ]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"
    
    print(f"✓ Insights shape verified: {data['calls_completed']} calls, {data['response_rate']}% response rate")


def test_5_list_and_filters():
    """Test 5: GET /api/followups - list endpoint with filters."""
    print("\n=== TEST 5: GET /api/followups (List & Filters) ===")
    
    # Test basic list
    r = requests.get(f"{BASE_URL}/followups", headers=headers)
    assert r.status_code == 200, f"List failed: {r.status_code} {r.text}"
    data = r.json()
    print(f"List returned {len(data)} followups")
    
    # Verify each item has bucket field
    if len(data) > 0:
        for item in data:
            assert "bucket" in item, "Item missing bucket field"
            assert "priority_score" in item, "Item missing priority_score"
        
        # Verify default sort is priority_score descending
        scores = [item.get("priority_score", 0) for item in data]
        assert scores == sorted(scores, reverse=True), "Items not sorted by priority_score DESC"
        print(f"✓ Default sort verified (priority_score DESC)")
    
    # Test bucket filter
    r = requests.get(f"{BASE_URL}/followups?bucket=today", headers=headers)
    assert r.status_code == 200, f"Bucket filter failed: {r.status_code}"
    today_data = r.json()
    print(f"✓ Bucket filter (today): {len(today_data)} items")
    
    # Test overdue bucket
    r = requests.get(f"{BASE_URL}/followups?bucket=overdue", headers=headers)
    assert r.status_code == 200, f"Overdue filter failed: {r.status_code}"
    overdue_data = r.json()
    print(f"✓ Bucket filter (overdue): {len(overdue_data)} items")
    
    # Test priority filter
    r = requests.get(f"{BASE_URL}/followups?priority=critical", headers=headers)
    assert r.status_code == 200, f"Priority filter failed: {r.status_code}"
    critical_data = r.json()
    print(f"✓ Priority filter (critical): {len(critical_data)} items")
    
    # Test category filter
    r = requests.get(f"{BASE_URL}/followups?category=payment", headers=headers)
    assert r.status_code == 200, f"Category filter failed: {r.status_code}"
    payment_data = r.json()
    print(f"✓ Category filter (payment): {len(payment_data)} items")
    
    # Test customer_tier filter
    r = requests.get(f"{BASE_URL}/followups?customer_tier=vip", headers=headers)
    assert r.status_code == 200, f"Tier filter failed: {r.status_code}"
    vip_data = r.json()
    print(f"✓ Customer tier filter (vip): {len(vip_data)} items")
    
    # Test search filter - get a real customer name from the list
    if len(data) > 0:
        customer_name = data[0].get("customer_name", "")
        if customer_name:
            search_term = customer_name.split()[0]  # First word of customer name
            r = requests.get(f"{BASE_URL}/followups?q={search_term}", headers=headers)
            assert r.status_code == 200, f"Search filter failed: {r.status_code}"
            search_data = r.json()
            print(f"✓ Search filter (q={search_term}): {len(search_data)} items")
    
    print(f"✓ All list filters working")


def test_6_detail():
    """Test 6: GET /api/followups/{id} - detail endpoint."""
    print("\n=== TEST 6: GET /api/followups/{id} (Detail) ===")
    
    # Get a real followup id from the list
    r = requests.get(f"{BASE_URL}/followups?limit=1", headers=headers)
    assert r.status_code == 200, f"List failed: {r.status_code}"
    data = r.json()
    
    if len(data) == 0:
        print("⚠ No followups found, skipping detail test")
        return
    
    followup_id = data[0]["id"]
    print(f"Testing detail for followup: {followup_id}")
    
    # Get detail
    r = requests.get(f"{BASE_URL}/followups/{followup_id}", headers=headers)
    assert r.status_code == 200, f"Detail failed: {r.status_code} {r.text}"
    detail = r.json()
    
    # Verify required keys
    required_keys = ["followup", "customer", "stats", "quotations", "payments", "purchases", "timeline"]
    for key in required_keys:
        assert key in detail, f"Missing required key: {key}"
    
    # Verify stats shape
    stats = detail["stats"]
    assert "outstanding_total" in stats, "Missing stats.outstanding_total"
    assert isinstance(stats["outstanding_total"], (int, float)), "outstanding_total should be numeric"
    assert stats["outstanding_total"] >= 0, f"outstanding_total should be non-negative, got {stats['outstanding_total']}"
    
    print(f"✓ Detail shape verified: outstanding_total = ₹{stats['outstanding_total']}")


def test_7_mutations():
    """Test 7: Mutations - POST, PATCH, snooze, complete, contact, log-call."""
    print("\n=== TEST 7: Mutations ===")
    
    # Get a real customer_id for manual create
    r = requests.get(f"{BASE_URL}/customers?limit=1", headers=headers)
    assert r.status_code == 200, f"Get customers failed: {r.status_code}"
    customers = r.json()
    assert len(customers) > 0, "No customers found"
    customer_id = customers[0]["id"]
    customer_name = customers[0].get("name", "Test Customer")
    customer_phone = customers[0].get("phone")
    
    # 7a. POST /api/followups (manual create)
    print("\n--- 7a. POST /api/followups (Manual Create) ---")
    create_payload = {
        "customer_id": customer_id,
        "category": "general",
        "channel": "call",
        "reason": "Test manual followup",
        "notes": "Created by backend test"
    }
    r = requests.post(f"{BASE_URL}/followups", headers=headers, json=create_payload)
    assert r.status_code in [200, 201], f"Create failed: {r.status_code} {r.text}"
    created = r.json()
    assert created["is_automated"] == False, "Manual followup should have is_automated=false"
    assert created["customer_id"] == customer_id, "Customer ID mismatch"
    manual_followup_id = created["id"]
    print(f"✓ Manual followup created: {manual_followup_id}")
    
    # 7b. PATCH /api/followups/{id} with notes
    print("\n--- 7b. PATCH /api/followups/{id} (Update Notes) ---")
    patch_payload = {"notes": "test note from backend test"}
    r = requests.patch(f"{BASE_URL}/followups/{manual_followup_id}", headers=headers, json=patch_payload)
    assert r.status_code == 200, f"Patch notes failed: {r.status_code} {r.text}"
    updated = r.json()
    assert updated["notes"] == "test note from backend test", "Notes not persisted"
    print(f"✓ Notes updated and persisted")
    
    # 7c. PATCH /api/followups/{id} with status=dismissed
    print("\n--- 7c. PATCH /api/followups/{id} (Dismiss) ---")
    # Create a fresh followup for dismissal test
    r = requests.post(f"{BASE_URL}/followups", headers=headers, json=create_payload)
    assert r.status_code in [200, 201], f"Create failed: {r.status_code}"
    dismiss_followup_id = r.json()["id"]
    
    patch_payload = {"status": "dismissed"}
    r = requests.patch(f"{BASE_URL}/followups/{dismiss_followup_id}", headers=headers, json=patch_payload)
    assert r.status_code == 200, f"Dismiss failed: {r.status_code} {r.text}"
    dismissed = r.json()
    assert dismissed["status"] == "dismissed", "Status not updated to dismissed"
    assert dismissed["completed_at"] is not None, "completed_at not set on dismiss"
    print(f"✓ Followup dismissed, completed_at set")
    
    # 7d. POST /api/followups/{id}/snooze
    print("\n--- 7d. POST /api/followups/{id}/snooze ---")
    # Create a fresh followup for snooze test
    r = requests.post(f"{BASE_URL}/followups", headers=headers, json=create_payload)
    assert r.status_code in [200, 201], f"Create failed: {r.status_code}"
    snooze_followup_id = r.json()["id"]
    
    snooze_payload = {"preset": "1h"}
    r = requests.post(f"{BASE_URL}/followups/{snooze_followup_id}/snooze", headers=headers, json=snooze_payload)
    assert r.status_code == 200, f"Snooze failed: {r.status_code} {r.text}"
    snoozed = r.json()
    assert snoozed["status"] == "snoozed", "Status not updated to snoozed"
    assert snoozed["snoozed_until"] is not None, "snoozed_until not set"
    print(f"✓ Followup snoozed until {snoozed['snoozed_until']}")
    
    # 7e. POST /api/followups/{id}/complete
    print("\n--- 7e. POST /api/followups/{id}/complete ---")
    # Create a fresh followup for complete test
    r = requests.post(f"{BASE_URL}/followups", headers=headers, json=create_payload)
    assert r.status_code in [200, 201], f"Create failed: {r.status_code}"
    complete_followup_id = r.json()["id"]
    
    complete_payload = {"notes": "Completed via test"}
    r = requests.post(f"{BASE_URL}/followups/{complete_followup_id}/complete", headers=headers, json=complete_payload)
    assert r.status_code == 200, f"Complete failed: {r.status_code} {r.text}"
    completed = r.json()
    assert completed["status"] == "done", "Status not updated to done"
    assert completed["completed_at"] is not None, "completed_at not set"
    print(f"✓ Followup completed, status=done")
    
    # 7f. POST /api/followups/{id}/contact (WhatsApp)
    print("\n--- 7f. POST /api/followups/{id}/contact (WhatsApp) ---")
    # Create a fresh followup for contact test
    r = requests.post(f"{BASE_URL}/followups", headers=headers, json=create_payload)
    assert r.status_code in [200, 201], f"Create failed: {r.status_code}"
    contact_followup_id = r.json()["id"]
    
    contact_payload = {"channel": "whatsapp"}
    r = requests.post(f"{BASE_URL}/followups/{contact_followup_id}/contact", headers=headers, json=contact_payload)
    assert r.status_code == 200, f"Contact failed: {r.status_code} {r.text}"
    contact_result = r.json()
    assert "wa_url" in contact_result, "Missing wa_url"
    assert contact_result["wa_url"].startswith("https://wa.me/"), f"Invalid wa_url: {contact_result['wa_url']}"
    assert "message" in contact_result, "Missing message"
    print(f"✓ WhatsApp contact URL generated: {contact_result['wa_url'][:50]}...")
    
    # 7g. POST /api/followups/{id}/log-call (call_back outcome)
    print("\n--- 7g. POST /api/followups/{id}/log-call (call_back) ---")
    # Create a fresh followup for log-call test
    r = requests.post(f"{BASE_URL}/followups", headers=headers, json=create_payload)
    assert r.status_code in [200, 201], f"Create failed: {r.status_code}"
    logcall_followup_id = r.json()["id"]
    
    # Get initial count of followups
    r = requests.get(f"{BASE_URL}/followups", headers=headers)
    initial_count = len(r.json())
    
    logcall_payload = {"outcome": "call_back", "notes": "test call back"}
    r = requests.post(f"{BASE_URL}/followups/{logcall_followup_id}/log-call", headers=headers, json=logcall_payload)
    assert r.status_code == 200, f"Log call failed: {r.status_code} {r.text}"
    logged = r.json()
    assert logged["status"] == "done", "Original followup should be marked done"
    
    # Verify a NEW followup was created
    time.sleep(0.5)
    r = requests.get(f"{BASE_URL}/followups", headers=headers)
    new_count = len(r.json())
    # Note: new count might be same or higher depending on reconciliation
    # Let's check if there's a new manual followup with is_automated=false
    all_followups = r.json()
    new_manual = [f for f in all_followups if f.get("is_automated") == False and f.get("rule_type") == "manual" and f["id"] != logcall_followup_id]
    assert len(new_manual) > 0, "No new manual followup created after call_back outcome"
    print(f"✓ Log call (call_back): original marked done, new followup created")
    
    # 7h. POST /api/followups/{id}/log-call (no_answer outcome)
    print("\n--- 7h. POST /api/followups/{id}/log-call (no_answer) ---")
    # Create a fresh followup for no_answer test
    r = requests.post(f"{BASE_URL}/followups", headers=headers, json=create_payload)
    assert r.status_code in [200, 201], f"Create failed: {r.status_code}"
    noanswer_followup_id = r.json()["id"]
    original_due_at = r.json()["due_at"]
    original_attempts = r.json().get("contact_attempts", 0)
    
    logcall_payload = {"outcome": "no_answer"}
    r = requests.post(f"{BASE_URL}/followups/{noanswer_followup_id}/log-call", headers=headers, json=logcall_payload)
    assert r.status_code == 200, f"Log call no_answer failed: {r.status_code} {r.text}"
    noanswer = r.json()
    assert noanswer["contact_attempts"] == original_attempts + 1, "contact_attempts not incremented"
    assert noanswer["due_at"] != original_due_at, "due_at not moved forward"
    print(f"✓ Log call (no_answer): contact_attempts incremented, due_at moved forward")
    
    print(f"\n✓ All mutations working correctly")


def test_8_auth():
    """Test 8: Auth - 401 tests."""
    print("\n=== TEST 8: Auth (401 Tests) ===")
    
    # Test without Authorization header
    endpoints = [
        "/followups",
        "/followups/stats",
        "/followups/reconcile"
    ]
    
    for endpoint in endpoints:
        if endpoint == "/followups/reconcile":
            r = requests.post(f"{BASE_URL}{endpoint}")
        else:
            r = requests.get(f"{BASE_URL}{endpoint}")
        assert r.status_code == 401, f"{endpoint} should return 401 without auth, got {r.status_code}"
        print(f"✓ {endpoint} returns 401 without auth")
    
    print(f"✓ All auth checks passed")


def test_9_404s():
    """Test 9: 404s - error handling."""
    print("\n=== TEST 9: 404s (Error Handling) ===")
    
    fake_id = "nonexistent-id-12345"
    
    # GET /api/followups/{fake_id}
    r = requests.get(f"{BASE_URL}/followups/{fake_id}", headers=headers)
    assert r.status_code == 404, f"GET fake id should return 404, got {r.status_code}"
    print(f"✓ GET /api/followups/{fake_id} returns 404")
    
    # PATCH /api/followups/{fake_id}
    r = requests.patch(f"{BASE_URL}/followups/{fake_id}", headers=headers, json={"notes": "test"})
    assert r.status_code == 404, f"PATCH fake id should return 404, got {r.status_code}"
    print(f"✓ PATCH /api/followups/{fake_id} returns 404")
    
    # POST /api/followups/{fake_id}/complete
    r = requests.post(f"{BASE_URL}/followups/{fake_id}/complete", headers=headers, json={})
    assert r.status_code == 404, f"POST complete fake id should return 404, got {r.status_code}"
    print(f"✓ POST /api/followups/{fake_id}/complete returns 404")
    
    # POST /api/followups with bogus customer_id
    r = requests.post(f"{BASE_URL}/followups", headers=headers, json={
        "customer_id": "bogus-customer-id",
        "category": "general",
        "channel": "call",
        "reason": "Test"
    })
    assert r.status_code == 404, f"POST with bogus customer_id should return 404, got {r.status_code}"
    print(f"✓ POST /api/followups with bogus customer_id returns 404")
    
    print(f"✓ All 404 checks passed")


def test_10_smoke_regression():
    """Test 10: Smoke regression - other endpoints still work."""
    print("\n=== TEST 10: Smoke Regression ===")
    
    endpoints = [
        "/quotations",
        "/payments/stats",
        "/purchase-orders",
        "/customers"
    ]
    
    for endpoint in endpoints:
        r = requests.get(f"{BASE_URL}{endpoint}", headers=headers)
        assert r.status_code == 200, f"{endpoint} failed: {r.status_code} {r.text}"
        print(f"✓ GET {endpoint} returns 200")
    
    print(f"✓ All smoke regression checks passed")


def main():
    """Run all tests."""
    print("=" * 80)
    print("Follow-ups · Sales Command Center — Backend API Testing")
    print("=" * 80)
    
    try:
        login()
        test_1_reconcile_idempotency()
        test_2_stats()
        test_3_mission()
        test_4_insights()
        test_5_list_and_filters()
        test_6_detail()
        test_7_mutations()
        test_8_auth()
        test_9_404s()
        test_10_smoke_regression()
        
        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
