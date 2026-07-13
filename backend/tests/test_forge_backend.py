"""Forge backend integration tests (iteration 1).

Covers: health, staff+customer auth, dashboard, catalog (brands, categories,
products with search + filter), customers, quotations CRUD + PDF, RBAC,
scaffold endpoints.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://forge-ui-audit.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
PASSWORD = "Forge@2026"
OWNER_EMAIL = "owner@forge.app"
WORKER_EMAIL = "worker@forge.app"
SALES_EMAIL = "sales@forge.app"
CUSTOMER_EMAIL = "customer@forge.app"


# ----------- fixtures -----------
@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(session, email, password=PASSWORD, path="/auth/login"):
    r = session.post(f"{API}{path}", json={"email": email, "password": password}, timeout=20)
    return r


@pytest.fixture(scope="session")
def owner_token(session):
    r = _login(session, OWNER_EMAIL)
    assert r.status_code == 200, f"Owner login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def sales_token(session):
    r = _login(session, SALES_EMAIL)
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def worker_token(session):
    r = _login(session, WORKER_EMAIL)
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def customer_token(session):
    r = _login(session, CUSTOMER_EMAIL, path="/auth/customer/login")
    assert r.status_code == 200, f"Customer login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ============== HEALTH ==============
class TestHealth:
    def test_health_ok(self, session):
        r = session.get(f"{API}/health", timeout=10)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"


# ============== AUTH ==============
class TestAuth:
    def test_staff_login_success(self, session):
        r = _login(session, OWNER_EMAIL)
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["user"]["role"] == "owner"
        assert data["user"]["email"] == OWNER_EMAIL

    def test_staff_login_invalid_password(self, session):
        r = _login(session, OWNER_EMAIL, password="wrong-pass")
        assert r.status_code == 401

    def test_staff_me(self, session, owner_token):
        r = session.get(f"{API}/auth/me", headers=_auth(owner_token), timeout=10)
        assert r.status_code == 200
        assert r.json()["email"] == OWNER_EMAIL

    def test_customer_login(self, session):
        r = _login(session, CUSTOMER_EMAIL, path="/auth/customer/login")
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["customer"]["email"] == CUSTOMER_EMAIL


# ============== DASHBOARD ==============
class TestDashboard:
    def test_dashboard_stats(self, session, owner_token):
        r = session.get(f"{API}/dashboard/stats", headers=_auth(owner_token), timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("revenue_month", "open_pipeline", "pending_approval",
                  "quotes_this_month", "customers", "products",
                  "followups_due", "recent_activity", "top_products"):
            assert k in d, f"Missing {k}"
        assert isinstance(d["recent_activity"], list)
        assert isinstance(d["top_products"], list)
        assert isinstance(d["customers"], int)
        assert isinstance(d["products"], int)


# ============== CATALOG ==============
class TestCatalog:
    def test_brands(self, session, owner_token):
        r = session.get(f"{API}/brands", headers=_auth(owner_token), timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_categories(self, session, owner_token):
        r = session.get(f"{API}/categories", headers=_auth(owner_token), timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_products_list(self, session, owner_token):
        r = session.get(f"{API}/products", headers=_auth(owner_token), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "total" in d and "items" in d
        assert d["total"] >= 16, f"Expected >=16 products; got {d['total']}"
        assert len(d["items"]) >= 1

    def test_products_search(self, session, owner_token):
        r_all = session.get(f"{API}/products", headers=_auth(owner_token), timeout=15).json()
        r = session.get(f"{API}/products", params={"q": "faucet"}, headers=_auth(owner_token), timeout=15)
        assert r.status_code == 200
        narrowed = r.json()
        assert narrowed["total"] <= r_all["total"]
        # ensure hits actually contain "faucet"
        for item in narrowed["items"]:
            haystack = " ".join([
                item.get("name", ""), item.get("sku", ""),
                item.get("description") or "", " ".join(item.get("tags", []) or [])
            ]).lower()
            assert "faucet" in haystack

    def test_products_brand_filter(self, session, owner_token):
        brands = session.get(f"{API}/brands", headers=_auth(owner_token), timeout=15).json()
        assert brands
        brand_id = brands[0]["id"]
        r = session.get(f"{API}/products", params={"brand_id": brand_id}, headers=_auth(owner_token), timeout=15)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["brand_id"] == brand_id

    def test_get_single_product(self, session, owner_token):
        items = session.get(f"{API}/products", headers=_auth(owner_token), timeout=15).json()["items"]
        pid = items[0]["id"]
        r = session.get(f"{API}/products/{pid}", headers=_auth(owner_token), timeout=15)
        assert r.status_code == 200
        assert r.json()["id"] == pid


# ============== CUSTOMERS ==============
class TestCustomers:
    def test_list_customers(self, session, owner_token):
        r = session.get(f"{API}/customers", headers=_auth(owner_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 4, f"Expected >=4 seeded customers; got {len(data)}"


# ============== QUOTATIONS ==============
@pytest.fixture(scope="session")
def created_quotation(session, sales_token, owner_token):
    customers = session.get(f"{API}/customers", headers=_auth(owner_token), timeout=15).json()
    products = session.get(f"{API}/products", headers=_auth(owner_token), timeout=15).json()["items"]
    assert customers and len(products) >= 2

    # Ensure we pick the "customer@forge.app" so portal tests work
    target = next((c for c in customers if c["email"] == CUSTOMER_EMAIL), customers[0])
    p1, p2 = products[0], products[1]

    def line(p, qty, disc):
        base = qty * p["price"]
        tax = round(base * (1 - disc / 100) * (p.get("gst_pct", 18) / 100), 2)
        return {
            "product_id": p["id"],
            "sku": p["sku"],
            "name": p["name"],
            "image": (p.get("images") or [None])[0],
            "qty": qty,
            "unit_price": p["price"],
            "discount_pct": disc,
            "tax": tax,
            "room": None,
            "notes": None,
        }

    items = [line(p1, 2, 5), line(p2, 1, 0)]
    payload = {"customer_id": target["id"], "items": items, "rooms": [], "notes": "TEST_quotation"}
    r = session.post(f"{API}/quotations", json=payload, headers=_auth(sales_token), timeout=20)
    assert r.status_code == 200, f"Create quotation failed: {r.status_code} {r.text}"
    return r.json()


class TestQuotations:
    def test_create_quotation_totals(self, created_quotation):
        q = created_quotation
        assert q["id"] and q["number"].startswith("FQ-")
        # Validate: grand_total == subtotal - discount_total + tax_total (as computed by API)
        gt_check = round(q["subtotal"] - q["discount_total"] + q["tax_total"], 2)
        assert abs(q["grand_total"] - gt_check) < 0.05, (
            f"grand_total mismatch: {q['grand_total']} vs subtotal-discount+tax={gt_check}"
        )
        assert q["grand_total"] > 0
        assert len(q["items"]) == 2

    def test_list_quotations(self, session, owner_token, created_quotation):
        r = session.get(f"{API}/quotations", headers=_auth(owner_token), timeout=15)
        assert r.status_code == 200
        ids = [q["id"] for q in r.json()]
        assert created_quotation["id"] in ids

    def test_get_quotation(self, session, owner_token, created_quotation):
        r = session.get(f"{API}/quotations/{created_quotation['id']}", headers=_auth(owner_token), timeout=15)
        assert r.status_code == 200
        assert r.json()["id"] == created_quotation["id"]

    def test_update_quotation_status(self, session, sales_token, created_quotation):
        r = session.patch(
            f"{API}/quotations/{created_quotation['id']}",
            json={"status": "sent", "reason": "TEST_send"},
            headers=_auth(sales_token), timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "sent"
        assert len(d.get("revisions", [])) >= 1

    def test_quotation_pdf_staff(self, session, owner_token, created_quotation):
        r = session.get(f"{API}/quotations/{created_quotation['id']}/pdf",
                        headers=_auth(owner_token), timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"


# ============== RBAC ==============
class TestRBAC:
    def test_worker_cannot_create_quotation(self, session, worker_token, owner_token):
        customers = session.get(f"{API}/customers", headers=_auth(owner_token), timeout=15).json()
        r = session.post(
            f"{API}/quotations",
            json={"customer_id": customers[0]["id"], "items": [], "rooms": []},
            headers=_auth(worker_token), timeout=15,
        )
        assert r.status_code == 403, f"Worker should get 403, got {r.status_code}"

    def test_sales_can_create_quotation(self, created_quotation):
        # already created via sales_token in fixture
        assert created_quotation["id"]

    def test_worker_cannot_list_team(self, session, worker_token):
        r = session.get(f"{API}/team", headers=_auth(worker_token), timeout=15)
        assert r.status_code == 403


# ============== CUSTOMER PORTAL ==============
class TestCustomerPortal:
    def test_portal_quotations_scoped(self, session, customer_token, created_quotation):
        r = session.get(f"{API}/portal/quotations", headers=_auth(customer_token), timeout=15)
        assert r.status_code == 200
        docs = r.json()
        # created quotation was for CUSTOMER_EMAIL customer
        assert any(q["id"] == created_quotation["id"] for q in docs)
        # all quotations must be for this customer
        cust_ids = {q["customer_id"] for q in docs}
        assert len(cust_ids) <= 1

    def test_portal_pdf(self, session, customer_token, created_quotation):
        r = session.get(
            f"{API}/quotations/{created_quotation['id']}/portal-pdf",
            headers=_auth(customer_token), timeout=30,
        )
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"


# ============== SCAFFOLD ENDPOINTS ==============
class TestScaffold:
    @pytest.mark.parametrize("path", [
        "/purchase-orders", "/payments", "/followups",
        "/notifications", "/reports/overview",
    ])
    def test_authorised_scaffolds(self, session, owner_token, path):
        r = session.get(f"{API}{path}", headers=_auth(owner_token), timeout=15)
        assert r.status_code == 200

    def test_team_manager_plus(self, session, owner_token):
        r = session.get(f"{API}/team", headers=_auth(owner_token), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list) and len(r.json()) >= 1
