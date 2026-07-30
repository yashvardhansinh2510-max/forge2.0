"""Walk-ins CRM duplicate-rule regression checks for POST /api/walkins.

Modules/features covered:
- city/address medium-confidence duplicate blocking and resolvable matches
- high-confidence phone reuse linking to existing customer without overwrite
- email force-new conflict returns clean 409 (never 500)
"""

from __future__ import annotations

import os
import uuid

import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _phone() -> str:
    return "9" + str(uuid.uuid4().int)[:9]


@pytest.fixture(scope="module")
def session():
    if not BASE_URL:
        pytest.skip("EXPO_PUBLIC_BACKEND_URL is required for integration tests")
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=1.0, status_forcelist=[502, 503, 504], allowed_methods=None)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": "owner@forge.app", "password": "Forge@2026"}, timeout=90)
    assert r.status_code == 200, f"login failed: {r.text}"
    token = r.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def floor_id() -> str:
    return "ground-floor"


class TestWalkinDuplicateRules:
    """POST /api/walkins duplicate-handling behavior."""

    def test_name_city_medium_match_returns_409_with_matches(self, session, floor_id):
        name = f"TEST_MEDIUM_CITY_{uuid.uuid4().hex[:6]}"
        city = f"TEST_CITY_{uuid.uuid4().hex[:6]}"

        seed = session.post(
            f"{API}/walkins",
            json={
                "customer_name": name,
                "customer_phone": _phone(),
                "city": city,
                "floor_id": floor_id,
            },
            timeout=90,
        )
        assert seed.status_code == 200, seed.text

        attempt = session.post(
            f"{API}/walkins",
            json={
                "customer_name": name,
                "customer_phone": _phone(),
                "city": city,
                "floor_id": floor_id,
            },
            timeout=90,
        )
        assert attempt.status_code == 409, attempt.text
        detail = attempt.json().get("detail", {})
        assert "matches" in detail
        assert len(detail.get("matches", {}).get("medium", [])) >= 1

    def test_name_address_medium_match_returns_409_with_matches(self, session, floor_id):
        name = f"TEST_MEDIUM_ADDR_{uuid.uuid4().hex[:6]}"
        address = f"TEST_ADDR_{uuid.uuid4().hex[:10]}"

        seed = session.post(
            f"{API}/walkins",
            json={
                "customer_name": name,
                "customer_phone": _phone(),
                "address": address,
                "floor_id": floor_id,
            },
            timeout=90,
        )
        assert seed.status_code == 200, seed.text

        attempt = session.post(
            f"{API}/walkins",
            json={
                "customer_name": name,
                "customer_phone": _phone(),
                "address": address,
                "floor_id": floor_id,
            },
            timeout=90,
        )
        assert attempt.status_code == 409, attempt.text
        detail = attempt.json().get("detail", {})
        assert "matches" in detail
        assert len(detail.get("matches", {}).get("medium", [])) >= 1

    def test_high_phone_reuse_creates_new_walkin_links_same_customer_no_overwrite(self, session, floor_id):
        phone_digits = _phone()
        formatted = f"+91 {phone_digits[:5]} {phone_digits[5:]}"
        original_name = f"TEST_HIGH_REUSE_{uuid.uuid4().hex[:6]}"

        first = session.post(
            f"{API}/walkins",
            json={
                "customer_name": original_name,
                "customer_phone": formatted,
                "floor_id": floor_id,
            },
            timeout=90,
        )
        assert first.status_code == 200, first.text
        first_doc = first.json()

        second = session.post(
            f"{API}/walkins",
            json={
                "customer_name": f"TEST_SHOULD_NOT_OVERWRITE_{uuid.uuid4().hex[:6]}",
                "customer_phone": phone_digits,
                "floor_id": floor_id,
            },
            timeout=90,
        )
        assert second.status_code == 200, second.text
        second_doc = second.json()

        assert first_doc["id"] != second_doc["id"]
        assert first_doc["customer_id"] == second_doc["customer_id"]

        customer = session.get(f"{API}/customers/{first_doc['customer_id']}", timeout=90)
        assert customer.status_code == 200, customer.text
        assert customer.json().get("name") == original_name

    def test_email_force_new_conflict_returns_409_not_500(self, session, floor_id):
        email = f"test.email.conflict.{uuid.uuid4().hex[:8]}@example.com"

        seed = session.post(
            f"{API}/walkins",
            json={
                "customer_name": f"TEST_EMAIL_SEED_{uuid.uuid4().hex[:6]}",
                "customer_phone": _phone(),
                "email": email,
                "floor_id": floor_id,
            },
            timeout=90,
        )
        assert seed.status_code == 200, seed.text

        conflict = session.post(
            f"{API}/walkins",
            json={
                "customer_name": f"TEST_EMAIL_FORCE_NEW_{uuid.uuid4().hex[:6]}",
                "customer_phone": _phone(),
                "email": email,
                "force_new_customer": True,
                "floor_id": floor_id,
            },
            timeout=30,
        )

        assert conflict.status_code == 409, conflict.text
        assert conflict.status_code != 500
