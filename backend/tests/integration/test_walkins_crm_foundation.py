"""CRM Foundation pass (2026-08) — Walk-ins full customer capture, salesperson
reassignment, confidence-tiered duplicate detection, and the Order Confirmed
-> Operations handoff Follow-up.

Covers the NEW features layered on top of the already-verified Walk-ins base
(Walk-in -> Customer -> Selection -> Quotation -> Order -> Dispatch ->
Payment pipeline). See review_request for the full feature list.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://walkin-crm.preview.emergentagent.com"

API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    resp = s.post(f"{API}/auth/login", json={"email": "owner@forge.app", "password": "Forge@2026"})
    assert resp.status_code == 200, f"login failed: {resp.text}"
    token = resp.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def floor_id(session):
    # No standalone /api/floors listing route exists; ground-floor is the
    # known seeded id used throughout the existing test suite/customers.
    return "ground-floor"


@pytest.fixture(scope="module")
def salespeople(session):
    r = session.get(f"{API}/followups/config/assignees")
    assert r.status_code == 200
    return r.json()


def _unique_phone() -> str:
    # 10-digit, always starts 9 to look like a real Indian mobile number
    return "9" + str(uuid.uuid4().int)[:9]


class TestFullCustomerCapture:
    """POST /api/walkins with brand-new phone -> address/city/state/pincode
    persist on CUSTOMER; reference_contact/architect/builder persist on WALKIN;
    distinct from `source`."""

    def test_full_capture_splits_customer_and_walkin_fields(self, session, floor_id):
        phone = _unique_phone()
        payload = {
            "customer_name": "TEST_CRM Full Capture",
            "customer_phone": phone,
            "email": f"test.crm.{uuid.uuid4().hex[:8]}@example.com",
            "address": "12 TEST Lotus Apartments",
            "city": "TEST City",
            "state": "TEST State",
            "pincode": "123456",
            "source": "Reference",
            "reference_contact": "TEST Mr. Sharma",
            "architect": "TEST Architect Studio",
            "builder": "TEST Builder Co",
            "floor_id": floor_id,
        }
        r = session.post(f"{API}/walkins", json=payload)
        assert r.status_code == 200, r.text
        walkin = r.json()
        walkin_id = walkin["id"]
        customer_id = walkin["customer_id"]

        # Distinct from source
        assert walkin["source"] == "Reference"
        assert walkin["reference_contact"] == "TEST Mr. Sharma"
        assert walkin["architect"] == "TEST Architect Studio"
        assert walkin["builder"] == "TEST Builder Co"

        # WALK-IN record carries reference/architect/builder
        r_w = session.get(f"{API}/walkins/{walkin_id}")
        assert r_w.status_code == 200
        wdoc = r_w.json()
        assert wdoc["reference_contact"] == "TEST Mr. Sharma"
        assert wdoc["architect"] == "TEST Architect Studio"
        assert wdoc["builder"] == "TEST Builder Co"

        # CUSTOMER record carries address/city/state/pincode (NOT walkin)
        r_c = session.get(f"{API}/customers/{customer_id}")
        assert r_c.status_code == 200
        cdoc = r_c.json()
        assert cdoc["address"] == "12 TEST Lotus Apartments"
        assert cdoc["city"] == "TEST City"
        assert cdoc["state"] == "TEST State"
        assert cdoc["pincode"] == "123456"
        # Customer doc has no reference_contact/architect/builder fields
        assert "reference_contact" not in cdoc
        assert "architect" not in cdoc
        assert "builder" not in cdoc


class TestDuplicateDetection:
    """Confidence-tiered duplicate detection — HIGH (fuzzy phone), MEDIUM
    (email / name+city / name+address), LOW (name only, non-blocking)."""

    def test_high_confidence_matches_formatted_phone(self, session, floor_id):
        raw_digits = _unique_phone()
        formatted_phone = f"+91 {raw_digits[:5]} {raw_digits[5:]}"  # e.g. "+91 98200 12345"
        payload = {
            "customer_name": "TEST_CRM Formatted Phone",
            "customer_phone": formatted_phone,
            "floor_id": floor_id,
        }
        r = session.post(f"{API}/walkins", json=payload)
        assert r.status_code == 200, r.text

        # check-duplicate with the same digits, no formatting
        r2 = session.get(f"{API}/walkins/check-duplicate", params={"phone": raw_digits})
        assert r2.status_code == 200
        matches = r2.json()
        high_names = [m["name"] for m in matches["high"]]
        assert "TEST_CRM Formatted Phone" in high_names, f"formatted-phone HIGH match regression: {matches}"

    def test_email_match_is_medium_not_high(self, session, floor_id):
        email = f"test.crm.medium.{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "customer_name": "TEST_CRM Email Owner",
            "customer_phone": _unique_phone(),
            "email": email,
            "floor_id": floor_id,
        }
        r = session.post(f"{API}/walkins", json=payload)
        assert r.status_code == 200, r.text

        # Different name/phone, same email -> should be MEDIUM only
        r2 = session.get(
            f"{API}/walkins/check-duplicate",
            params={"email": email, "name": "TEST_CRM Totally Different Name", "phone": _unique_phone()},
        )
        assert r2.status_code == 200
        matches = r2.json()
        medium_emails = [m.get("email") for m in matches["medium"]]
        high_emails = [m.get("email") for m in matches["high"]]
        assert email in medium_emails, f"email match not surfaced as MEDIUM: {matches}"
        assert email not in high_emails, f"email match wrongly surfaced as HIGH: {matches}"

    def test_email_only_walkin_create_returns_409_then_force_new_conflicts_cleanly(self, session, floor_id):
        email = f"test.crm.conflict.{uuid.uuid4().hex[:8]}@example.com"
        seed_payload = {
            "customer_name": "TEST_CRM Conflict Seed",
            "customer_phone": _unique_phone(),
            "email": email,
            "floor_id": floor_id,
        }
        r = session.post(f"{API}/walkins", json=seed_payload)
        assert r.status_code == 200, r.text

        # New walk-in, same email, different name/phone, no resolution flags -> 409
        attempt_payload = {
            "customer_name": "TEST_CRM Conflict Attempt",
            "customer_phone": _unique_phone(),
            "email": email,
            "floor_id": floor_id,
        }
        r2 = session.post(f"{API}/walkins", json=attempt_payload)
        assert r2.status_code == 409, r2.text
        body = r2.json()
        detail = body.get("detail")
        assert detail is not None
        assert "matches" in detail, f"409 body missing 'matches' key: {body}"

        # Retry with force_new_customer=True -> email already taken by
        # another customer -> expect a CLEAN 409 (not a 500)
        attempt_payload["force_new_customer"] = True
        r3 = session.post(f"{API}/walkins", json=attempt_payload)
        assert r3.status_code == 409, f"expected clean 409 on email conflict, got {r3.status_code}: {r3.text}"
        assert r3.status_code != 500

    def test_email_only_walkin_force_new_succeeds_when_email_unique(self, session, floor_id):
        # Sanity counterpart: force_new_customer succeeds (200) when the
        # email genuinely isn't taken by anyone else.
        email = f"test.crm.uniqueforce.{uuid.uuid4().hex[:8]}@example.com"
        seed_payload = {
            "customer_name": "TEST_CRM Medium Seed",
            "customer_phone": _unique_phone(),
            "customer_name_city_seed": None,
            "floor_id": floor_id,
        }
        del seed_payload["customer_name_city_seed"]
        seed_payload["city"] = "TEST Vadodara"
        r = session.post(f"{API}/walkins", json=seed_payload)
        assert r.status_code == 200, r.text

        # Trigger a name+city MEDIUM match (not email) so force_new_customer
        # creates a brand-new, non-conflicting customer.
        attempt_payload = {
            "customer_name": "TEST_CRM Medium Seed",
            "customer_phone": _unique_phone(),
            "city": "TEST Vadodara",
            "email": email,
            "floor_id": floor_id,
        }
        r2 = session.post(f"{API}/walkins", json=attempt_payload)
        assert r2.status_code == 409, r2.text

        attempt_payload["force_new_customer"] = True
        r3 = session.post(f"{API}/walkins", json=attempt_payload)
        assert r3.status_code == 200, f"force_new_customer with unique email should succeed: {r3.text}"


class TestSalespersonReassign:
    def test_reassign_updates_walkin_and_its_own_followup(self, session, floor_id, salespeople):
        payload = {
            "customer_name": "TEST_CRM Reassign Target",
            "customer_phone": _unique_phone(),
            "floor_id": floor_id,
        }
        r = session.post(f"{API}/walkins", json=payload)
        assert r.status_code == 200, r.text
        walkin = r.json()
        walkin_id = walkin["id"]
        original_sp_id = walkin["salesperson_id"]

        candidate = next((s for s in salespeople if s["id"] != original_sp_id), None)
        assert candidate, "need at least 2 staff accounts to test reassignment"

        r2 = session.patch(f"{API}/walkins/{walkin_id}/reassign", json={"salesperson_id": candidate["id"]})
        assert r2.status_code == 200, r2.text
        updated = r2.json()
        assert updated["salesperson_id"] == candidate["id"]
        assert updated["salesperson_name"] == candidate["full_name"], "reassign did not return the NEW person's real name"

        # The walk-in's own automated Follow-up must be reassigned too.
        # reconcile() first so the walk_in_new:{id} card exists.
        session.post(f"{API}/followups/reconcile")
        time.sleep(1)
        r3 = session.get(f"{API}/followups", params={"q": walkin["customer_name"]})
        assert r3.status_code == 200
        own_followups = [f for f in r3.json() if f.get("source_key") == f"walk_in_new:{walkin_id}"]
        if own_followups:
            assert own_followups[0]["assigned_to"] == candidate["id"], (
                f"walk_in_new followup not reassigned: {own_followups[0]}"
            )


class TestWorkflowTransitionsConfig:
    def test_get_and_put_order_confirmed_transition(self, session):
        r = session.get(f"{API}/followups/config/workflow-transitions")
        assert r.status_code == 200
        transitions = r.json()
        oc = next((t for t in transitions if t["key"] == "order_confirmed"), None)
        assert oc is not None, "order_confirmed transition missing"
        assert "{customer_name}" in oc["message_template"]
        assert "{quotation_number}" in oc["message_template"]
        original_template = oc["message_template"]

        try:
            new_template = "TEST_ {customer_name}'s order {quotation_number} is now confirmed for ops."
            r2 = session.put(
                f"{API}/followups/config/workflow-transitions/order_confirmed",
                json={"message_template": new_template},
            )
            assert r2.status_code == 200, r2.text
            assert r2.json()["message_template"] == new_template

            r3 = session.get(f"{API}/followups/config/workflow-transitions")
            oc2 = next((t for t in r3.json() if t["key"] == "order_confirmed"), None)
            assert oc2["message_template"] == new_template
        finally:
            session.put(
                f"{API}/followups/config/workflow-transitions/order_confirmed",
                json={"message_template": original_template},
            )


class TestOrderConfirmedOpsFollowup:
    def test_existing_order_confirmed_ops_followup_matches_template_and_timeline(self, session):
        r = session.post(f"{API}/followups/reconcile")
        assert r.status_code == 200

        r2 = session.get(f"{API}/followups", params={"category": "operations", "limit": 50})
        assert r2.status_code == 200
        ops_followups = [f for f in r2.json() if f.get("rule_type") == "order_confirmed_ops"]
        assert ops_followups, "no order_confirmed_ops follow-ups found — verify at least one ordered quotation exists without a release-material PO"
        target = ops_followups[0]

        r3 = session.get(f"{API}/followups/config/workflow-transitions")
        oc = next(t for t in r3.json() if t["key"] == "order_confirmed")
        expected_reason = oc["message_template"].format(
            customer_name=target["customer_name"], quotation_number=target["quotation_number"],
        )
        assert target["reason"] == expected_reason, f"reason text does not match configured template: {target['reason']!r} vs {expected_reason!r}"

        # Timeline event for that customer
        r4 = session.get(f"{API}/followups/{target['id']}")
        assert r4.status_code == 200
        timeline = r4.json().get("timeline", [])
        matches = [
            e for e in timeline
            if e.get("event_type") == "quotation.order_confirmed_followup_created"
            and e.get("quotation_id") == target["quotation_id"]
        ]
        assert matches, "quotation.order_confirmed_followup_created timeline event missing for this customer/quotation"


class TestBackendRegression:
    @pytest.mark.parametrize("path", [
        "/followups/stats", "/quotations", "/customers", "/purchase-orders",
        "/payments/stats", "/tile-orders",
    ])
    def test_endpoint_still_200(self, session, path):
        r = session.get(f"{API}{path}")
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:300]}"
