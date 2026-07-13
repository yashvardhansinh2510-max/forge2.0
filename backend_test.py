#!/usr/bin/env python3
"""
Backend Testing for Team Management + Customer Portal Account Management
Final pre-launch Administration session testing
"""

import requests
import json
import time
from datetime import datetime, timedelta

# Configuration
BASE_URL = "https://ff330064-dcc2-4b25-b59c-dadba81bd1d4.preview.emergentagent.com/api"
OWNER_EMAIL = "owner@forge.app"
OWNER_PASSWORD = "Forge@2026"

# Test state
test_results = []
owner_token = None
owner_user_id = None
test_staff_id = None
test_customer_id = None
test_customer_email = None
test_customer_temp_password = None
test_staff_temp_password = None


def log_test(test_name, passed, details=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    test_results.append({
        "test": test_name,
        "passed": passed,
        "details": details
    })
    print(f"{status}: {test_name}")
    if details:
        print(f"   {details}")


def login_as_owner():
    """Login as owner and get JWT token"""
    global owner_token, owner_user_id
    print("\n" + "="*80)
    print("AUTHENTICATION - Login as Owner")
    print("="*80)
    
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    
    if response.status_code == 200:
        data = response.json()
        owner_token = data.get("access_token")
        owner_user_id = data.get("user", {}).get("id")
        log_test("Owner login", True, f"Token received, User ID: {owner_user_id}")
        return True
    else:
        log_test("Owner login", False, f"Status: {response.status_code}, Response: {response.text}")
        return False


def get_headers(token=None):
    """Get headers with authorization"""
    if token is None:
        token = owner_token
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def test_get_roles():
    """Test 1: GET /api/roles"""
    print("\n" + "="*80)
    print("TEST 1: GET /api/roles")
    print("="*80)
    
    # Test without auth (should fail)
    response = requests.get(f"{BASE_URL}/roles")
    log_test("1.1 GET /api/roles without auth returns 401", 
             response.status_code == 401,
             f"Status: {response.status_code}")
    
    # Test with auth
    response = requests.get(f"{BASE_URL}/roles", headers=get_headers())
    
    if response.status_code == 200:
        roles = response.json()
        
        # Check it's a list
        is_list = isinstance(roles, list)
        log_test("1.2 GET /api/roles returns a list", is_list)
        
        if is_list:
            # Check we have 8 roles
            has_8_roles = len(roles) == 8
            log_test("1.3 Returns exactly 8 roles", has_8_roles, f"Count: {len(roles)}")
            
            # Check each role has required fields
            all_have_fields = all(
                "role" in r and "label" in r and "level" in r and "capabilities" in r
                for r in roles
            )
            log_test("1.4 Each role has role/label/level/capabilities", all_have_fields)
            
            # Check sorted by descending level (owner first, worker last)
            if len(roles) > 0:
                is_sorted = all(
                    roles[i]["level"] >= roles[i+1]["level"] 
                    for i in range(len(roles)-1)
                )
                log_test("1.5 Roles sorted by descending level", is_sorted,
                        f"First: {roles[0].get('role')} (level {roles[0].get('level')}), Last: {roles[-1].get('role')} (level {roles[-1].get('level')})")
                
                # Check owner is first, worker is last
                owner_first = roles[0].get("role") == "owner"
                worker_last = roles[-1].get("role") == "worker"
                log_test("1.6 Owner first, worker last", owner_first and worker_last)
    else:
        log_test("1.2 GET /api/roles with auth", False, 
                f"Status: {response.status_code}, Response: {response.text}")


def test_team_management():
    """Test 2: Team Management"""
    global test_staff_id, test_staff_temp_password
    
    print("\n" + "="*80)
    print("TEST 2: TEAM MANAGEMENT")
    print("="*80)
    
    # 2.1 Create a disposable staff member
    timestamp = int(time.time())
    test_staff_email = f"test.staff.{timestamp}@forge.app"
    test_staff_password = "TestPass123!"
    
    response = requests.post(
        f"{BASE_URL}/team",
        headers=get_headers(),
        json={
            "full_name": "Test Staff Member",
            "email": test_staff_email,
            "phone": "+91 98765 43210",
            "role": "worker",
            "password": test_staff_password
        }
    )
    
    if response.status_code == 200:
        staff_data = response.json()
        test_staff_id = staff_data.get("id")
        
        # Check must_change_password is true
        must_change = staff_data.get("must_change_password") == True
        log_test("2.1 POST /api/team creates staff with must_change_password=true", 
                must_change,
                f"must_change_password: {staff_data.get('must_change_password')}")
        
        # Check temp_password_expires_at is ~72h in future
        expires_at = staff_data.get("temp_password_expires_at")
        if expires_at:
            # Parse ISO timestamp
            try:
                expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                now = datetime.now(expires_dt.tzinfo)
                hours_until_expiry = (expires_dt - now).total_seconds() / 3600
                is_72h = 71 <= hours_until_expiry <= 73
                log_test("2.2 temp_password_expires_at is ~72h in future", is_72h,
                        f"Hours until expiry: {hours_until_expiry:.1f}")
            except Exception as e:
                log_test("2.2 temp_password_expires_at parsing", False, str(e))
        else:
            log_test("2.2 temp_password_expires_at present", False, "Field missing")
        
        # 2.3 Login as the new staff member
        login_response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": test_staff_email, "password": test_staff_password}
        )
        
        if login_response.status_code == 200:
            login_data = login_response.json()
            staff_token = login_data.get("access_token")
            user_obj = login_data.get("user", {})
            
            log_test("2.3 Login as new staff member succeeds", True,
                    f"Token received, must_change_password: {user_obj.get('must_change_password')}")
            
            # Verify must_change_password in login response
            must_change_in_login = user_obj.get("must_change_password") == True
            log_test("2.4 Login response shows must_change_password=true", must_change_in_login)
        else:
            log_test("2.3 Login as new staff member", False,
                    f"Status: {login_response.status_code}")
        
        # 2.5 Reset password for that staff member
        reset_response = requests.post(
            f"{BASE_URL}/team/{test_staff_id}/reset-password",
            headers=get_headers()
        )
        
        if reset_response.status_code == 200:
            reset_data = reset_response.json()
            
            # Check response shape
            has_fields = all(k in reset_data for k in ["delivery_method", "temporary_password", "expires_at", "message"])
            log_test("2.5 POST /api/team/{id}/reset-password returns correct shape", has_fields,
                    f"Keys: {list(reset_data.keys())}")
            
            if has_fields:
                delivery_method = reset_data.get("delivery_method")
                test_staff_temp_password = reset_data.get("temporary_password")
                
                log_test("2.6 delivery_method is 'manual'", delivery_method == "manual",
                        f"delivery_method: {delivery_method}")
                
                log_test("2.7 temporary_password is 12 chars", len(test_staff_temp_password) == 12,
                        f"Length: {len(test_staff_temp_password)}")
                
                # 2.8 Login with NEW temp password
                new_login_response = requests.post(
                    f"{BASE_URL}/auth/login",
                    json={"email": test_staff_email, "password": test_staff_temp_password}
                )
                
                log_test("2.8 Login with NEW temp password succeeds", 
                        new_login_response.status_code == 200,
                        f"Status: {new_login_response.status_code}")
        else:
            log_test("2.5 POST /api/team/{id}/reset-password", False,
                    f"Status: {reset_response.status_code}, Response: {reset_response.text}")
        
        # 2.9 Self-protection: try to reset own password
        self_reset_response = requests.post(
            f"{BASE_URL}/team/{owner_user_id}/reset-password",
            headers=get_headers()
        )
        
        log_test("2.9 Self-protection: Cannot reset own password (400)", 
                self_reset_response.status_code == 400,
                f"Status: {self_reset_response.status_code}")
        
        # 2.10 Deactivate the test staff member
        deactivate_response = requests.patch(
            f"{BASE_URL}/team/{test_staff_id}",
            headers=get_headers(),
            json={"active": False}
        )
        
        log_test("2.10 PATCH /api/team/{id} to deactivate succeeds", 
                deactivate_response.status_code == 200,
                f"Status: {deactivate_response.status_code}")
        
        # 2.11 Try to login as deactivated user (use the temp password from reset)
        if deactivate_response.status_code == 200:
            deactivated_login = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": test_staff_email, "password": test_staff_temp_password}
            )
            
            log_test("2.11 Deactivated user login fails with 403", 
                    deactivated_login.status_code == 403,
                    f"Status: {deactivated_login.status_code}")
        
        # 2.12 Self-protection: try to deactivate self
        self_deactivate = requests.patch(
            f"{BASE_URL}/team/{owner_user_id}",
            headers=get_headers(),
            json={"active": False}
        )
        
        log_test("2.12 Self-protection: Cannot deactivate self (400)", 
                self_deactivate.status_code == 400,
                f"Status: {self_deactivate.status_code}")
        
        # 2.13 Self-protection: try to change own role
        self_role_change = requests.patch(
            f"{BASE_URL}/team/{owner_user_id}",
            headers=get_headers(),
            json={"role": "admin"}
        )
        
        log_test("2.13 Self-protection: Cannot change own role (400)", 
                self_role_change.status_code == 400,
                f"Status: {self_role_change.status_code}")
        
        # 2.14 Check activity log for audit events
        activity_response = requests.get(
            f"{BASE_URL}/activity?limit=20",
            headers=get_headers()
        )
        
        if activity_response.status_code == 200:
            events = activity_response.json()
            
            # Look for user.created, user.password_reset, user.disabled events
            user_created = any(e.get("event_type") == "user.created" and 
                             e.get("summary") == "Staff Account Created" and
                             e.get("actor_name") == "Aarav Kapoor"
                             for e in events)
            
            user_password_reset = any(e.get("event_type") == "user.password_reset" and 
                                     e.get("summary") == "Staff Password Reset" and
                                     e.get("actor_name") == "Aarav Kapoor"
                                     for e in events)
            
            user_disabled = any(e.get("event_type") == "user.disabled" and 
                               e.get("summary") == "Staff Account Disabled" and
                               e.get("actor_name") == "Aarav Kapoor"
                               for e in events)
            
            log_test("2.14 Activity log contains 'user.created' event", user_created)
            log_test("2.15 Activity log contains 'user.password_reset' event", user_password_reset)
            log_test("2.16 Activity log contains 'user.disabled' event", user_disabled)
        else:
            log_test("2.14 GET /api/activity", False,
                    f"Status: {activity_response.status_code}")
    else:
        log_test("2.1 POST /api/team", False,
                f"Status: {response.status_code}, Response: {response.text}")


def test_customer_portal():
    """Test 3: Customer Portal Account Management"""
    global test_customer_id, test_customer_email, test_customer_temp_password
    
    print("\n" + "="*80)
    print("TEST 3: CUSTOMER PORTAL ACCOUNT MANAGEMENT")
    print("="*80)
    
    # 3.1 Create a test customer (name only, no email)
    timestamp = int(time.time())
    customer_name = f"Test Customer {timestamp}"
    
    response = requests.post(
        f"{BASE_URL}/customers",
        headers=get_headers(),
        json={"name": customer_name}
    )
    
    if response.status_code == 200:
        customer_data = response.json()
        test_customer_id = customer_data.get("id")
        
        log_test("3.1 POST /api/customers creates customer", True,
                f"Customer ID: {test_customer_id}")
        
        # 3.2 Try to send invite without email
        invite_no_email = requests.post(
            f"{BASE_URL}/customers/{test_customer_id}/send-invite",
            headers=get_headers()
        )
        
        is_400 = invite_no_email.status_code == 400
        has_message = "email" in invite_no_email.text.lower() if is_400 else False
        
        log_test("3.2 POST send-invite without email returns 400", is_400 and has_message,
                f"Status: {invite_no_email.status_code}, Message: {invite_no_email.text[:100]}")
        
        # 3.3 Try to enable portal without email
        enable_no_email = requests.patch(
            f"{BASE_URL}/customers/{test_customer_id}",
            headers=get_headers(),
            json={"portal_enabled": True}
        )
        
        is_400 = enable_no_email.status_code == 400
        has_message = "email" in enable_no_email.text.lower() if is_400 else False
        
        log_test("3.3 PATCH portal_enabled=true without email returns 400", is_400 and has_message,
                f"Status: {enable_no_email.status_code}")
        
        # 3.4 Add email and enable portal
        test_customer_email = f"test.customer.{timestamp}@example.com"
        
        update_response = requests.patch(
            f"{BASE_URL}/customers/{test_customer_id}",
            headers=get_headers(),
            json={
                "email": test_customer_email,
                "portal_enabled": True
            }
        )
        
        if update_response.status_code == 200:
            updated_data = update_response.json()
            portal_enabled = updated_data.get("portal_enabled") == True
            
            log_test("3.4 PATCH with email + portal_enabled=true succeeds", portal_enabled,
                    f"portal_enabled: {updated_data.get('portal_enabled')}")
            
            # 3.5 Try to use duplicate email
            # First create another customer
            another_customer = requests.post(
                f"{BASE_URL}/customers",
                headers=get_headers(),
                json={"name": "Another Customer"}
            )
            
            if another_customer.status_code == 200:
                another_id = another_customer.json().get("id")
                
                # Try to set the same email
                duplicate_email = requests.patch(
                    f"{BASE_URL}/customers/{another_id}",
                    headers=get_headers(),
                    json={"email": test_customer_email}
                )
                
                log_test("3.5 PATCH with duplicate email returns 409", 
                        duplicate_email.status_code == 409,
                        f"Status: {duplicate_email.status_code}")
            
            # 3.6 Send invite (should work now)
            invite_response = requests.post(
                f"{BASE_URL}/customers/{test_customer_id}/send-invite",
                headers=get_headers()
            )
            
            if invite_response.status_code == 200:
                invite_data = invite_response.json()
                
                has_fields = all(k in invite_data for k in ["delivery_method", "temporary_password", "expires_at", "message"])
                log_test("3.6 POST send-invite succeeds with correct shape", has_fields,
                        f"Keys: {list(invite_data.keys())}")
                
                if has_fields:
                    test_customer_temp_password = invite_data.get("temporary_password")
                    
                    log_test("3.7 delivery_method is 'manual'", 
                            invite_data.get("delivery_method") == "manual")
                    
                    log_test("3.8 temporary_password is 12 chars", 
                            len(test_customer_temp_password) == 12,
                            f"Length: {len(test_customer_temp_password)}")
                    
                    # 3.9 Login as customer with temp password
                    customer_login = requests.post(
                        f"{BASE_URL}/auth/customer/login",
                        json={
                            "email": test_customer_email,
                            "password": test_customer_temp_password
                        }
                    )
                    
                    if customer_login.status_code == 200:
                        customer_login_data = customer_login.json()
                        customer_token = customer_login_data.get("access_token")
                        customer_obj = customer_login_data.get("customer", {})
                        
                        portal_enabled_in_login = customer_obj.get("portal_enabled") == True
                        must_change = customer_obj.get("must_change_password") == True
                        
                        log_test("3.9 Customer login with temp password succeeds", True,
                                f"Token received")
                        
                        log_test("3.10 Login response shows portal_enabled=true", portal_enabled_in_login)
                        log_test("3.11 Login response shows must_change_password=true", must_change)
                        
                        # 3.12 GET /api/auth/customer/me
                        me_response = requests.get(
                            f"{BASE_URL}/auth/customer/me",
                            headers={"Authorization": f"Bearer {customer_token}"}
                        )
                        
                        if me_response.status_code == 200:
                            me_data = me_response.json()
                            must_change_persists = me_data.get("must_change_password") == True
                            
                            log_test("3.12 GET /auth/customer/me shows must_change_password=true", 
                                    must_change_persists)
                            
                            # 3.13 Change password
                            new_password = "NewCustomerPass123!"
                            
                            change_pw_response = requests.post(
                                f"{BASE_URL}/auth/customer/change-password",
                                headers={"Authorization": f"Bearer {customer_token}"},
                                json={
                                    "current_password": test_customer_temp_password,
                                    "new_password": new_password
                                }
                            )
                            
                            if change_pw_response.status_code == 200:
                                change_data = change_pw_response.json()
                                
                                log_test("3.13 POST /auth/customer/change-password succeeds", 
                                        change_data.get("changed") == True,
                                        f"Response: {change_data}")
                                
                                # 3.14 Verify must_change_password is now false
                                me_after_change = requests.get(
                                    f"{BASE_URL}/auth/customer/me",
                                    headers={"Authorization": f"Bearer {customer_token}"}
                                )
                                
                                if me_after_change.status_code == 200:
                                    me_after_data = me_after_change.json()
                                    must_change_cleared = me_after_data.get("must_change_password") == False
                                    temp_expires_cleared = me_after_data.get("temp_password_expires_at") is None
                                    
                                    log_test("3.14 After change, must_change_password=false", must_change_cleared)
                                    log_test("3.15 After change, temp_password_expires_at=null", temp_expires_cleared)
                                    
                                    # 3.16 Disable portal
                                    disable_portal = requests.patch(
                                        f"{BASE_URL}/customers/{test_customer_id}",
                                        headers=get_headers(),
                                        json={"portal_enabled": False}
                                    )
                                    
                                    if disable_portal.status_code == 200:
                                        log_test("3.16 PATCH portal_enabled=false succeeds", True)
                                        
                                        # 3.17 Try to login with portal disabled
                                        disabled_login = requests.post(
                                            f"{BASE_URL}/auth/customer/login",
                                            json={
                                                "email": test_customer_email,
                                                "password": new_password
                                            }
                                        )
                                        
                                        is_403 = disabled_login.status_code == 403
                                        has_message = "portal" in disabled_login.text.lower() and "disabled" in disabled_login.text.lower()
                                        
                                        log_test("3.17 Login with portal_enabled=false returns 403", 
                                                is_403 and has_message,
                                                f"Status: {disabled_login.status_code}, Message: {disabled_login.text[:100]}")
                                        
                                        # 3.18 Re-enable portal
                                        reenable_portal = requests.patch(
                                            f"{BASE_URL}/customers/{test_customer_id}",
                                            headers=get_headers(),
                                            json={"portal_enabled": True}
                                        )
                                        
                                        log_test("3.18 Re-enable portal succeeds", 
                                                reenable_portal.status_code == 200)
                                        
                                        # 3.19 Reset password
                                        reset_pw_response = requests.post(
                                            f"{BASE_URL}/customers/{test_customer_id}/reset-password",
                                            headers=get_headers()
                                        )
                                        
                                        if reset_pw_response.status_code == 200:
                                            reset_data = reset_pw_response.json()
                                            new_temp_password = reset_data.get("temporary_password")
                                            
                                            log_test("3.19 POST reset-password succeeds", True,
                                                    f"New temp password received")
                                            
                                            # 3.20 Verify old password no longer works
                                            old_pw_login = requests.post(
                                                f"{BASE_URL}/auth/customer/login",
                                                json={
                                                    "email": test_customer_email,
                                                    "password": new_password
                                                }
                                            )
                                            
                                            log_test("3.20 Old password no longer works", 
                                                    old_pw_login.status_code == 401,
                                                    f"Status: {old_pw_login.status_code}")
                                            
                                            # 3.21 Verify new temp password works
                                            new_temp_login = requests.post(
                                                f"{BASE_URL}/auth/customer/login",
                                                json={
                                                    "email": test_customer_email,
                                                    "password": new_temp_password
                                                }
                                            )
                                            
                                            log_test("3.21 New temp password works", 
                                                    new_temp_login.status_code == 200,
                                                    f"Status: {new_temp_login.status_code}")
                                            
                                            # 3.22 Check activity log
                                            activity_response = requests.get(
                                                f"{BASE_URL}/activity/customer/{test_customer_id}",
                                                headers=get_headers()
                                            )
                                            
                                            if activity_response.status_code == 200:
                                                events = activity_response.json()
                                                
                                                # Look for specific events
                                                portal_invite = any(
                                                    e.get("summary") == "Customer Portal Invite Generated"
                                                    for e in events
                                                )
                                                
                                                password_reset = any(
                                                    e.get("summary") == "Customer Password Reset"
                                                    for e in events
                                                )
                                                
                                                portal_enabled = any(
                                                    e.get("summary") == "Customer Portal Enabled"
                                                    for e in events
                                                )
                                                
                                                portal_disabled = any(
                                                    e.get("summary") == "Customer Portal Disabled"
                                                    for e in events
                                                )
                                                
                                                portal_login = any(
                                                    e.get("summary") == "Customer Portal Login"
                                                    for e in events
                                                )
                                                
                                                log_test("3.22 Activity: 'Customer Portal Invite Generated'", portal_invite)
                                                log_test("3.23 Activity: 'Customer Password Reset'", password_reset)
                                                log_test("3.24 Activity: 'Customer Portal Enabled'", portal_enabled)
                                                log_test("3.25 Activity: 'Customer Portal Disabled'", portal_disabled)
                                                log_test("3.26 Activity: 'Customer Portal Login'", portal_login)
                                            else:
                                                log_test("3.22 GET /api/activity/customer/{id}", False,
                                                        f"Status: {activity_response.status_code}")
                                        else:
                                            log_test("3.19 POST reset-password", False,
                                                    f"Status: {reset_pw_response.status_code}")
                                    else:
                                        log_test("3.16 PATCH portal_enabled=false", False,
                                                f"Status: {disable_portal.status_code}")
                            else:
                                log_test("3.13 POST /auth/customer/change-password", False,
                                        f"Status: {change_pw_response.status_code}, Response: {change_pw_response.text}")
                        else:
                            log_test("3.12 GET /auth/customer/me", False,
                                    f"Status: {me_response.status_code}")
                    else:
                        log_test("3.9 Customer login with temp password", False,
                                f"Status: {customer_login.status_code}, Response: {customer_login.text}")
            else:
                log_test("3.6 POST send-invite", False,
                        f"Status: {invite_response.status_code}, Response: {invite_response.text}")
        else:
            log_test("3.4 PATCH with email + portal_enabled", False,
                    f"Status: {update_response.status_code}, Response: {update_response.text}")
    else:
        log_test("3.1 POST /api/customers", False,
                f"Status: {response.status_code}, Response: {response.text}")


def test_regression():
    """Test 4: Regression sweep"""
    print("\n" + "="*80)
    print("TEST 4: REGRESSION SWEEP")
    print("="*80)
    
    # 4.1 Health check
    health_response = requests.get(f"{BASE_URL}/health/system")
    
    if health_response.status_code == 200:
        health_data = health_response.json()
        
        is_healthy = health_data.get("healthy") == True
        mongo_connected = health_data.get("mongo", {}).get("connected") == True
        mongo_not_local = health_data.get("mongo", {}).get("is_local") == False
        supabase_connected = health_data.get("supabase", {}).get("connected") == True
        products_count = health_data.get("counts", {}).get("products", 0)
        
        log_test("4.1 GET /api/health/system - healthy=true", is_healthy)
        log_test("4.2 Mongo connected (not local)", mongo_connected and mongo_not_local,
                f"connected: {mongo_connected}, is_local: {health_data.get('mongo', {}).get('is_local')}")
        log_test("4.3 Supabase connected", supabase_connected)
        log_test("4.4 Products count ~2966", 2900 <= products_count <= 3000,
                f"Count: {products_count}")
    else:
        log_test("4.1 GET /api/health/system", False,
                f"Status: {health_response.status_code}")
    
    # 4.2 Test authenticated endpoints
    endpoints = [
        ("GET /api/customers", "get", f"{BASE_URL}/customers"),
        ("GET /api/quotations", "get", f"{BASE_URL}/quotations"),
        ("GET /api/purchase-orders", "get", f"{BASE_URL}/purchase-orders"),
        ("GET /api/payments/stats", "get", f"{BASE_URL}/payments/stats"),
        ("GET /api/followups/stats", "get", f"{BASE_URL}/followups/stats"),
    ]
    
    for name, method, url in endpoints:
        # Test without auth (should be 401)
        response = requests.request(method, url)
        log_test(f"4.5 {name} without auth returns 401", 
                response.status_code == 401,
                f"Status: {response.status_code}")
        
        # Test with auth (should be 200)
        response = requests.request(method, url, headers=get_headers())
        log_test(f"4.6 {name} with auth returns 200", 
                response.status_code == 200,
                f"Status: {response.status_code}")
    
    # 4.3 Test owner login still works
    owner_login = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    
    if owner_login.status_code == 200:
        owner_data = owner_login.json()
        user_obj = owner_data.get("user", {})
        
        # Owner should NOT have must_change_password (it's an old account)
        must_change = user_obj.get("must_change_password")
        
        log_test("4.7 Owner login still works", True)
        log_test("4.8 Owner account has no must_change_password flag", 
                must_change is None or must_change == False,
                f"must_change_password: {must_change}")
    else:
        log_test("4.7 Owner login", False,
                f"Status: {owner_login.status_code}")


def print_summary():
    """Print test summary"""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for t in test_results if t["passed"])
    failed = sum(1 for t in test_results if not t["passed"])
    total = len(test_results)
    
    print(f"\nTotal Tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Success Rate: {(passed/total*100):.1f}%")
    
    if failed > 0:
        print("\n" + "="*80)
        print("FAILED TESTS")
        print("="*80)
        for t in test_results:
            if not t["passed"]:
                print(f"\n❌ {t['test']}")
                if t["details"]:
                    print(f"   {t['details']}")
    
    print("\n" + "="*80)
    print("DETAILED RESULTS BY CATEGORY")
    print("="*80)
    
    # Group by test category
    categories = {
        "1. GET /api/roles": [],
        "2. Team Management": [],
        "3. Customer Portal": [],
        "4. Regression": []
    }
    
    for t in test_results:
        test_name = t["test"]
        if test_name.startswith("1."):
            categories["1. GET /api/roles"].append(t)
        elif test_name.startswith("2."):
            categories["2. Team Management"].append(t)
        elif test_name.startswith("3."):
            categories["3. Customer Portal"].append(t)
        elif test_name.startswith("4."):
            categories["4. Regression"].append(t)
    
    for category, tests in categories.items():
        if tests:
            passed_in_cat = sum(1 for t in tests if t["passed"])
            total_in_cat = len(tests)
            print(f"\n{category}: {passed_in_cat}/{total_in_cat} passed")
            for t in tests:
                status = "✅" if t["passed"] else "❌"
                print(f"  {status} {t['test']}")


def main():
    """Main test execution"""
    print("="*80)
    print("BACKEND TESTING: Team Management + Customer Portal Account Management")
    print("Final pre-launch Administration session")
    print("="*80)
    
    # Login first
    if not login_as_owner():
        print("\n❌ CRITICAL: Owner login failed. Cannot proceed with tests.")
        return
    
    # Run all tests
    test_get_roles()
    test_team_management()
    test_customer_portal()
    test_regression()
    
    # Print summary
    print_summary()


if __name__ == "__main__":
    main()
