"""Iteration 2: Quotation Builder 2.0 backend tests.

Covers multi-level discounts (product/category/project), autosave/silent PATCH,
duplicate, breakdown, recent/frequent products, collapsed_rooms persistence,
and regression of iteration-1 endpoints.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://forge-lc1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
PASSWORD = "Forge@2026"
OWNER_EMAIL = "owner@forge.app"
SALES_EMAIL = "sales@forge.app"
CUSTOMER_EMAIL = "customer@forge.app"


# ------------------ fixtures ------------------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(session, email, path="/auth/login"):
    r = session.post(f"{API}{path}", json={"email": email, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def owner_token(session):
    return _login(session, OWNER_EMAIL)


@pytest.fixture(scope="module")
def sales_token(session):
    return _login(session, SALES_EMAIL)


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def catalog(session, owner_token):
    prods = session.get(f"{API}/products", headers=_h(owner_token), timeout=15).json()["items"]
    cats = session.get(f"{API}/categories", headers=_h(owner_token), timeout=15).json()
    customers = session.get(f"{API}/customers", headers=_h(owner_token), timeout=15).json()
    # Pick two products with DIFFERENT categories if possible
    p1 = prods[0]
    p2 = next((p for p in prods[1:] if p["category_id"] != p1["category_id"]), prods[1])
    target = next((c for c in customers if c["email"] == CUSTOMER_EMAIL), customers[0])
    return {"p1": p1, "p2": p2, "cats": cats, "customer": target, "all_products": prods}


def _line(p, qty=1, disc=None, room=None):
    return {
        "product_id": p["id"],
        "sku": p["sku"],
        "name": p["name"],
        "image": (p.get("images") or [None])[0],
        "category_id": p.get("category_id"),
        "room": room,
        "qty": qty,
        "unit_price": p["price"],
        "discount_pct": disc,
    }


# ---------- multi-level discounts on create ----------
class TestDiscountCreate:
    def test_create_with_project_and_category_discounts(self, session, sales_token, catalog):
        p1, p2 = catalog["p1"], catalog["p2"]
        # p1 line has product override 15, p2 line inherits (None)
        items = [_line(p1, 2, 15), _line(p2, 1, None)]
        cat_map = {p2["category_id"]: 10}  # p2 gets category 10%
        payload = {
            "customer_id": catalog["customer"]["id"],
            "items": items,
            "rooms": ["Master Bath"],
            "notes": "TEST_discount_priority",
            "project_discount_pct": 5,
            "category_discounts": cat_map,
        }
        r = session.post(f"{API}/quotations", json=payload, headers=_h(sales_token), timeout=20)
        assert r.status_code == 200, r.text
        q = r.json()

        # manual recompute
        g1 = 2 * p1["price"]
        g2 = 1 * p2["price"]
        d1 = g1 * 15 / 100  # product override
        d2 = g2 * 10 / 100  # category override (project=5 ignored because category matches)
        expected_subtotal = round(g1 + g2, 2)
        expected_discount = round(d1 + d2, 2)
        expected_tax = round((g1 - d1) * 0.18 + (g2 - d2) * 0.18, 2)
        expected_grand = round(expected_subtotal - expected_discount + expected_tax, 2)

        assert abs(q["subtotal"] - expected_subtotal) < 0.05, (q["subtotal"], expected_subtotal)
        assert abs(q["discount_total"] - expected_discount) < 0.05, (q["discount_total"], expected_discount)
        assert abs(q["grand_total"] - expected_grand) < 0.05, (q["grand_total"], expected_grand)
        pytest.qid = q["id"]  # stash


# ---------- breakdown ----------
class TestBreakdown:
    def test_breakdown_sources(self, session, owner_token):
        qid = getattr(pytest, "qid", None)
        assert qid, "prev test must have created quotation"
        r = session.get(f"{API}/quotations/{qid}/breakdown", headers=_h(owner_token), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["project_discount_pct"] == 5
        assert len(d["lines"]) == 2
        # line 1 uses product override 15
        l1 = d["lines"][0]
        assert l1["discount_pct"] == 15
        assert l1["discount_source"] == "product"
        # line 2 uses category 10
        l2 = d["lines"][1]
        assert l2["discount_pct"] == 10
        assert l2["discount_source"] == "category"
        # totals sanity
        assert d["totals"]["grand_total"] > 0


# ---------- silent (autosave) vs default PATCH ----------
class TestAutosave:
    def test_silent_does_not_add_revision(self, session, sales_token):
        qid = pytest.qid
        # baseline: default patch adds revision
        r0 = session.patch(
            f"{API}/quotations/{qid}",
            json={"notes": "TEST_default_patch", "reason": "manual edit"},
            headers=_h(sales_token), timeout=15,
        )
        assert r0.status_code == 200
        base_rev = len(r0.json().get("revisions", []))
        assert base_rev >= 1

        # silent PATCH — should NOT append
        r1 = session.patch(
            f"{API}/quotations/{qid}",
            json={"notes": "TEST_silent_1", "silent": True},
            headers=_h(sales_token), timeout=15,
        )
        assert r1.status_code == 200
        assert len(r1.json().get("revisions", [])) == base_rev

        # default silent=false via omission — appends
        r2 = session.patch(
            f"{API}/quotations/{qid}",
            json={"notes": "TEST_loud", "reason": "loud edit"},
            headers=_h(sales_token), timeout=15,
        )
        assert r2.status_code == 200
        assert len(r2.json().get("revisions", [])) == base_rev + 1


# ---------- discount priority via PATCH ----------
class TestDiscountPriority:
    def test_line_override_beats_category_beats_project(self, session, sales_token, catalog):
        # Create a fresh quotation with two lines
        p1 = catalog["p1"]
        p3 = catalog["p2"]
        items = [_line(p1, 1, 15), _line(p3, 1, None)]
        cat_map = {p3["category_id"]: 10}
        payload = {
            "customer_id": catalog["customer"]["id"],
            "items": items,
            "rooms": [],
            "notes": "TEST_priority",
            "project_discount_pct": 5,
            "category_discounts": cat_map,
        }
        r = session.post(f"{API}/quotations", json=payload, headers=_h(sales_token), timeout=20)
        assert r.status_code == 200
        qid = r.json()["id"]
        b = session.get(f"{API}/quotations/{qid}/breakdown", headers=_h(sales_token), timeout=15).json()
        # p1 line = product override 15
        assert b["lines"][0]["discount_pct"] == 15 and b["lines"][0]["discount_source"] == "product"
        # p3 line = category 10
        assert b["lines"][1]["discount_pct"] == 10 and b["lines"][1]["discount_source"] == "category"

    def test_no_category_falls_back_to_project(self, session, sales_token, catalog):
        p1 = catalog["p1"]
        items = [_line(p1, 1, None)]
        payload = {
            "customer_id": catalog["customer"]["id"],
            "items": items,
            "rooms": [],
            "notes": "TEST_project_inherit",
            "project_discount_pct": 7,
            "category_discounts": {},  # no cat map -> falls to project
        }
        r = session.post(f"{API}/quotations", json=payload, headers=_h(sales_token), timeout=20)
        assert r.status_code == 200
        qid = r.json()["id"]
        b = session.get(f"{API}/quotations/{qid}/breakdown", headers=_h(sales_token), timeout=15).json()
        assert b["lines"][0]["discount_pct"] == 7
        assert b["lines"][0]["discount_source"] == "project"


# ---------- collapsed rooms persistence ----------
class TestCollapsedRooms:
    def test_collapsed_rooms_persist(self, session, sales_token):
        qid = pytest.qid
        r = session.patch(
            f"{API}/quotations/{qid}",
            json={"collapsed_rooms": ["Master Bath"], "silent": True},
            headers=_h(sales_token), timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["collapsed_rooms"] == ["Master Bath"]
        # verify persisted via GET
        r2 = session.get(f"{API}/quotations/{qid}", headers=_h(sales_token), timeout=15)
        assert r2.json()["collapsed_rooms"] == ["Master Bath"]


# ---------- duplicate ----------
class TestDuplicate:
    def test_duplicate_creates_new_with_same_items(self, session, sales_token):
        qid = pytest.qid
        orig = session.get(f"{API}/quotations/{qid}", headers=_h(sales_token), timeout=15).json()
        r = session.post(f"{API}/quotations/{qid}/duplicate", headers=_h(sales_token), timeout=20)
        assert r.status_code == 200, r.text
        dup = r.json()
        assert dup["id"] != orig["id"]
        assert dup["number"] != orig["number"]
        assert dup["number"].startswith("FQ-")
        assert len(dup["items"]) == len(orig["items"])
        # SKUs preserved
        assert [i["sku"] for i in dup["items"]] == [i["sku"] for i in orig["items"]]
        # line ids should be regenerated
        orig_ids = {i["id"] for i in orig["items"]}
        dup_ids = {i["id"] for i in dup["items"]}
        assert orig_ids.isdisjoint(dup_ids)


# ---------- recent / frequent products ----------
class TestRecentFrequent:
    def test_recent_returns_used_products(self, session, sales_token, catalog):
        r = session.get(f"{API}/products/recent", headers=_h(sales_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # should include products we just used
        ids = {p["id"] for p in data}
        assert catalog["p1"]["id"] in ids or catalog["p2"]["id"] in ids
        assert len(data) <= 12

    def test_frequent_ordered_by_count(self, session, sales_token):
        r = session.get(f"{API}/products/frequent", headers=_h(sales_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert len(data) <= 12


# ---------- Regression: iteration-1 endpoints ----------
class TestRegression:
    def test_dashboard_stats(self, session, owner_token):
        r = session.get(f"{API}/dashboard/stats", headers=_h(owner_token), timeout=15)
        assert r.status_code == 200
        assert "recent_activity" in r.json()

    def test_products_list(self, session, owner_token):
        r = session.get(f"{API}/products", headers=_h(owner_token), timeout=15)
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_customers_list(self, session, owner_token):
        r = session.get(f"{API}/customers", headers=_h(owner_token), timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_quotations_list(self, session, owner_token):
        r = session.get(f"{API}/quotations", headers=_h(owner_token), timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_pdf_still_works(self, session, owner_token):
        qid = pytest.qid
        r = session.get(f"{API}/quotations/{qid}/pdf", headers=_h(owner_token), timeout=30)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
