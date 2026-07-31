"""Phase 4 lifecycle regression: Walk-in -> Selection -> Quotation -> Order ->
Release -> operational follow-up auto-resolution.

Focused on CRM journey linkage/idempotency/timeline proof for TEST_ data.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests


BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
TEST_STAFF_EMAIL = os.environ.get("TEST_STAFF_EMAIL", "")
TEST_STAFF_PASSWORD = os.environ.get("TEST_STAFF_PASSWORD", "")


def _pick_rows(payload):
    if isinstance(payload, list):
        return payload
    for key in ("items", "rows", "products", "data"):
        if isinstance(payload, dict) and isinstance(payload.get(key), list):
            return payload[key]
    return []


def _choose_ground_floor_product(session: requests.Session) -> dict:
    """Prefer a ground-floor product if exposed; otherwise first available."""
    resp = session.get(f"{API}/products", params={"limit": 200}, timeout=90)
    assert resp.status_code == 200, resp.text
    rows = _pick_rows(resp.json())
    assert rows, "No products available for lifecycle test"
    ground = [p for p in rows if p.get("floor_id") == "ground-floor"]
    return ground[0] if ground else rows[0]


def _followup_by_source_key(followups: list[dict], source_key: str) -> list[dict]:
    return [f for f in followups if f.get("source_key") == source_key]


def _wait_for_followup_source_key(
    session: requests.Session,
    source_key: str,
    *,
    category: str | None = None,
    attempts: int = 20,
    sleep_s: float = 2.0,
) -> list[dict]:
    for _ in range(attempts):
        session.post(f"{API}/followups/reconcile", timeout=120)
        resp = session.get(
            f"{API}/followups",
            params={"limit": 3000, **({"category": category} if category else {})},
            timeout=90,
        )
        if resp.status_code == 200:
            rows = _followup_by_source_key(resp.json(), source_key)
            if rows:
                return rows
        time.sleep(sleep_s)
    return []


def _wait_for_followup_status(
    session: requests.Session,
    source_key: str,
    target_status: str,
    *,
    category: str | None = None,
    attempts: int = 20,
    sleep_s: float = 2.0,
) -> list[dict]:
    rows: list[dict] = []
    for _ in range(attempts):
        rows = _wait_for_followup_source_key(
            session,
            source_key,
            category=category,
            attempts=1,
            sleep_s=0.1,
        )
        if rows and rows[0].get("status") == target_status:
            return rows
        time.sleep(sleep_s)
    return rows


@pytest.fixture(scope="module")
def session() -> requests.Session:
    # Auth/environment gate for this end-to-end lifecycle test module
    if not BASE_URL or not TEST_STAFF_EMAIL or not TEST_STAFF_PASSWORD:
        pytest.skip("EXPO_PUBLIC_BACKEND_URL, TEST_STAFF_EMAIL, TEST_STAFF_PASSWORD are required")

    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    login = s.post(
        f"{API}/auth/login",
        json={"email": TEST_STAFF_EMAIL, "password": TEST_STAFF_PASSWORD},
        timeout=90,
    )
    assert login.status_code == 200, f"login failed: {login.status_code} {login.text}"
    token = login.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


class TestWalkinLifecyclePhase4:
    """Walk-ins + quotations + tile orders + followups journey assertions."""

    def test_full_journey_and_ops_followup_reconciliation(self, session: requests.Session):
        uniq = uuid.uuid4().hex[:8]
        phone = "9" + str(uuid.uuid4().int)[:9]
        customer_name = f"TEST_LC4_{uniq}"

        # 1) Walk-in create -> customer persisted + walk-in timeline event
        walkin_payload = {
            "customer_name": customer_name,
            "customer_phone": phone,
            "source": "Walk-in",
            "floor_id": "ground-floor",
            "visited_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            "city": f"TEST_CITY_{uniq}",
            "address": f"TEST_ADDRESS_{uniq}",
            "interested_products": ["Tiles"],
            "notes": "TEST lifecycle seed",
        }
        w_create = session.post(f"{API}/walkins", json=walkin_payload, timeout=90)
        assert w_create.status_code == 200, w_create.text
        walkin = w_create.json()
        assert walkin["customer_name"] == customer_name

        customer_id = walkin["customer_id"]
        walkin_id = walkin["id"]

        c_get = session.get(f"{API}/customers/{customer_id}", timeout=90)
        assert c_get.status_code == 200, c_get.text
        customer = c_get.json()
        assert customer.get("id") == customer_id
        assert customer.get("name") == customer_name

        w_timeline = session.get(f"{API}/walkins/{walkin_id}/timeline", timeout=90)
        assert w_timeline.status_code == 200, w_timeline.text
        w_events = w_timeline.json() or []
        assert any((e.get("event_type") == "walkin.created") for e in w_events), w_events

        walkin_source = f"walk_in_new:{walkin_id}"
        walkin_followups = _wait_for_followup_source_key(session, walkin_source, category="walk_in")
        assert walkin_followups, f"Expected walk-in follow-up {walkin_source}"
        assert walkin_followups[0].get("status") in ("open", "snoozed")

        # 2) Selection creation (same customer link), walk-in follow-up resolves
        product = _choose_ground_floor_product(session)
        line = {
            "product_id": product["id"],
            "sku": product.get("sku") or f"TESTSKU-{uniq}",
            "name": product.get("name") or "TEST Tile",
            "qty": 2,
            "unit_price": float(product.get("price") or 100),
        }
        q_create = session.post(
            f"{API}/quotations",
            json={
                "customer_id": customer_id,
                "doc_type": "tiles_selection",
                "project_name": f"TEST_PROJECT_{uniq}",
                "items": [line],
            },
            timeout=90,
        )
        assert q_create.status_code == 200, q_create.text
        selection = q_create.json()
        assert selection.get("customer_id") == customer_id
        assert selection.get("doc_type") == "tiles_selection"

        quotation_id = selection["id"]

        time.sleep(1)
        fl_after_selection = session.get(f"{API}/followups", params={"q": customer_name, "limit": 500}, timeout=90)
        assert fl_after_selection.status_code == 200
        walkin_rows = _wait_for_followup_status(session, walkin_source, "done", category="walk_in")
        assert walkin_rows, "Walk-in follow-up row missing after selection transition"
        walkin_resolved_after_selection = (
            walkin_rows[0].get("status") == "done"
            and walkin_rows[0].get("auto_resolved") is True
        )

        selection_rows = _wait_for_followup_source_key(
            session, f"selection_waiting:{quotation_id}", category="selection",
        )
        assert len(selection_rows) == 1, "Selection follow-up must begin immediately at handoff"
        assert selection_rows[0].get("status") in ("open", "snoozed")

        # 3) Selection -> Quotation -> Confirmed order
        s_to_pending = session.patch(
            f"{API}/quotations/{quotation_id}",
            json={"status": "pending_approval", "silent": False, "reason": "TEST submit selection"},
            timeout=90,
        )
        assert s_to_pending.status_code == 200, s_to_pending.text
        s_to_approved = session.patch(
            f"{API}/quotations/{quotation_id}",
            json={"status": "approved", "silent": False, "reason": "TEST approve selection"},
            timeout=90,
        )
        assert s_to_approved.status_code == 200, s_to_approved.text

        moved = session.post(f"{API}/quotations/{quotation_id}/move-to-quotation", timeout=90)
        assert moved.status_code == 200, moved.text
        assert moved.json().get("doc_type") == "tiles_quotation"

        q_to_pending = session.patch(
            f"{API}/quotations/{quotation_id}",
            json={"status": "pending_approval", "silent": False, "reason": "TEST submit quotation"},
            timeout=90,
        )
        assert q_to_pending.status_code == 200, q_to_pending.text
        q_to_approved = session.patch(
            f"{API}/quotations/{quotation_id}",
            json={"status": "approved", "silent": False, "reason": "TEST confirm quotation"},
            timeout=90,
        )
        assert q_to_approved.status_code == 200, q_to_approved.text

        place = session.post(f"{API}/quotations/{quotation_id}/place-order/confirm", json={}, timeout=120)
        assert place.status_code == 200, place.text

        # Reconcile twice to validate idempotent source_key behavior
        assert session.post(f"{API}/followups/reconcile", timeout=120).status_code == 200
        assert session.post(f"{API}/followups/reconcile", timeout=120).status_code == 200
        time.sleep(1)

        transitions = session.get(f"{API}/followups/config/workflow-transitions", timeout=90)
        assert transitions.status_code == 200, transitions.text
        order_cfg = next((r for r in transitions.json() if r.get("key") == "order_confirmed"), None)
        assert order_cfg is not None
        assert order_cfg.get("is_active", True) is True

        source_key = f"order_confirmed_ops:{quotation_id}"
        ops_rows = _wait_for_followup_source_key(session, source_key, category="operations")
        assert len(ops_rows) == 1, f"Expected exactly one ops follow-up row for {source_key}, got {len(ops_rows)}"
        ops = ops_rows[0]
        assert ops.get("status") in ("open", "snoozed")
        assert ops.get("assigned_to") == selection.get("created_by")

        expected_reason = (order_cfg.get("message_template") or "").format(
            customer_name=ops.get("customer_name") or customer_name,
            quotation_number=ops.get("quotation_number") or "",
        )
        assert ops.get("reason") == expected_reason

        # Unified customer timeline must carry the operational follow-up creation event
        f_detail = session.get(f"{API}/followups/{ops['id']}", timeout=90)
        assert f_detail.status_code == 200, f_detail.text
        timeline = f_detail.json().get("timeline", [])
        assert any(
            (e.get("event_type") == "quotation.order_confirmed_followup_created")
            and (e.get("quotation_id") == quotation_id)
            for e in timeline
        ), timeline

        # 4) Reconciliation trigger: first Release Material action resolves operational follow-up
        wf = session.get(f"{API}/quotations/{quotation_id}/workflow-status", timeout=120)
        assert wf.status_code == 200, wf.text
        po_rows = wf.json().get("purchase_orders") or []
        assert po_rows, "No purchase order generated from order confirmation"

        po_id = po_rows[0]["id"]
        po_detail = session.get(f"{API}/tile-orders/purchase-orders/{po_id}", timeout=90)
        assert po_detail.status_code == 200, po_detail.text
        po = po_detail.json()
        assert po.get("items"), "PO has no items to release"

        candidate = next((i for i in po["items"] if float(i.get("boxes_pending") or 0) > 0), po["items"][0])
        qty = min(1.0, float(candidate.get("boxes_pending") or 1.0))
        if qty <= 0:
            qty = 1.0

        release = session.post(
            f"{API}/tile-orders/purchase-orders/{po_id}/ready",
            json={"items": [{"po_item_id": candidate["id"], "qty": qty}]},
            timeout=120,
        )
        assert release.status_code == 200, release.text

        # Reconcile and verify operational follow-up now auto-resolved
        assert session.post(f"{API}/followups/reconcile", timeout=120).status_code == 200
        time.sleep(1)

        fl_after_release = session.get(f"{API}/followups", params={"q": customer_name, "limit": 500}, timeout=90)
        assert fl_after_release.status_code == 200, fl_after_release.text
        post_rows = _followup_by_source_key(fl_after_release.json(), source_key)
        assert post_rows, "Operational follow-up row missing after release"
        assert post_rows[0].get("status") == "done", post_rows[0]
        assert post_rows[0].get("auto_resolved") is True

        # Primary lifecycle blocker check kept at the end so downstream
        # operational follow-up checks are still exercised in the same run.
        assert walkin_resolved_after_selection, (
            "Walk-in follow-up did not auto-resolve when Selection was created. "
            f"Current row: {walkin_rows[0]}"
        )

    def test_module_regression_smoke_endpoints(self, session: requests.Session):
        # Quick no-regression smoke across critical modules touched in this lifecycle
        paths = [
            "/customers",
            "/quotations?doc_type=tiles_selection",
            "/quotations?doc_type=tiles_quotation",
            "/tile-orders/customer-orders",
            "/followups/stats",
            "/payments/stats",
        ]
        for path in paths:
            resp = session.get(f"{API}{path}", timeout=90)
            assert resp.status_code == 200, f"{path} -> {resp.status_code}: {resp.text[:300]}"
