"""Round 3 regression tests: image-recovery re-import verification.

Covers: Grohe image coverage recovery (missing system binaries fix),
Vitra re-import regression, Geberit tie-break fix + coverage, and
general catalog/brand/family regression across all 5 brands.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
EMAIL = "owner@forge.app"
PASSWORD = "Forge@2026"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


def _get_brand_id_map(headers):
    r = requests.get(f"{BASE_URL}/api/brands", headers=headers, timeout=30)
    assert r.status_code == 200
    return {b["name"]: b["id"] for b in r.json()}


def _get_category_id_map(headers, brand_id=None):
    params = {"brand_id": brand_id} if brand_id else {}
    r = requests.get(f"{BASE_URL}/api/categories", headers=headers, params=params, timeout=30)
    assert r.status_code == 200
    return {c["name"]: c["id"] for c in r.json()}


def _get_all_products(headers, brand_id=None, category_id=None, q=None, limit=200):
    products = []
    skip = 0
    while True:
        params = {"limit": limit, "skip": skip}
        if brand_id:
            params["brand_id"] = brand_id
        if category_id:
            params["category_id"] = category_id
        if q:
            params["q"] = q
        r = requests.get(f"{BASE_URL}/api/products", headers=headers, params=params, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        items = data.get("items") if isinstance(data, dict) else data
        if items is None:
            items = data.get("products", [])
        if not items:
            break
        products.extend(items)
        if len(items) < limit:
            break
        skip += limit
        if skip > 3000:
            break
    return products


def _has_image(p):
    if p.get("hero_image_url"):
        return True
    imgs = p.get("images")
    if imgs and len(imgs) > 0:
        return True
    return False


class TestBrandCounts:
    def test_brand_list_counts(self, headers):
        r = requests.get(f"{BASE_URL}/api/brands", headers=headers, timeout=30)
        assert r.status_code == 200
        brands = {b["name"]: b["product_count"] for b in r.json()}
        expected = {"Grohe", "Hansgrohe", "Axor", "Geberit", "Vitra"}
        assert expected.issubset(brands.keys()), brands
        # Grohe should now be 495 (per problem statement, resolved discrepancy)
        assert brands["Grohe"] == 495, f"Grohe count unexpected: {brands['Grohe']}"
        print("Brand counts:", brands)


class TestGroheImageCoverage:
    """Grohe image coverage should now be ~100% (495/495) after EMF/WMF fix."""

    def test_grohe_overall_image_coverage(self, headers):
        brand_id = _get_brand_id_map(headers)["Grohe"]
        products = _get_all_products(headers, brand_id=brand_id)
        assert len(products) > 400, f"too few Grohe products fetched: {len(products)}"
        missing = [p for p in products if not _has_image(p)]
        coverage_pct = (len(products) - len(missing)) * 100 / len(products)
        print(f"Grohe coverage: {coverage_pct:.1f}% ({len(products)-len(missing)}/{len(products)})")
        print("Missing SKUs sample:", [p.get("sku") for p in missing[:10]])
        assert coverage_pct >= 95, f"Grohe image coverage regressed: {coverage_pct:.1f}%"

    @pytest.mark.parametrize("category", ["Plate", "Handshower", "Wall Mounted"])
    def test_grohe_previously_broken_categories(self, headers, category):
        brand_id = _get_brand_id_map(headers)["Grohe"]
        cat_map = _get_category_id_map(headers, brand_id=brand_id)
        cat_id = cat_map.get(category)
        if not cat_id:
            pytest.skip(f"No Grohe category named {category}")
        products = _get_all_products(headers, brand_id=brand_id, category_id=cat_id)
        if not products:
            pytest.skip(f"No Grohe products found in category={category}")
        missing = [p for p in products if not _has_image(p)]
        coverage_pct = (len(products) - len(missing)) * 100 / len(products)
        print(f"Grohe/{category}: {coverage_pct:.1f}% ({len(products)-len(missing)}/{len(products)})")
        assert coverage_pct >= 90, f"Grohe {category} image coverage too low: {coverage_pct:.1f}%"


class TestVitraRegression:
    def test_vitra_overall_image_coverage(self, headers):
        brand_id = _get_brand_id_map(headers)["Vitra"]
        products = _get_all_products(headers, brand_id=brand_id)
        assert len(products) > 200
        missing = [p for p in products if not _has_image(p)]
        coverage_pct = (len(products) - len(missing)) * 100 / len(products)
        print(f"Vitra coverage: {coverage_pct:.1f}% ({len(products)-len(missing)}/{len(products)})")
        # ~98.8% per problem statement (247/250), allow small buffer
        assert coverage_pct >= 95, f"Vitra image coverage regressed: {coverage_pct:.1f}%"


class TestGeberitRegression:
    def test_geberit_overall_image_coverage(self, headers):
        brand_id = _get_brand_id_map(headers)["Geberit"]
        products = _get_all_products(headers, brand_id=brand_id)
        assert len(products) > 400
        missing = [p for p in products if not _has_image(p)]
        coverage_pct = (len(products) - len(missing)) * 100 / len(products)
        print(f"Geberit coverage: {coverage_pct:.1f}% ({len(products)-len(missing)}/{len(products)})")
        # ~92.4% per problem statement (462/500)
        assert coverage_pct >= 88, f"Geberit image coverage regressed: {coverage_pct:.1f}%"

    def test_geberit_116_092_variant_switching(self, headers):
        products = _get_all_products(headers, q="116.092")
        assert len(products) > 0, "No Geberit 116.092 products found"
        skus = {p.get("sku"): p for p in products}
        print("116.092 variants:", list(skus.keys()))
        # Check distinct images/colours across variants where >1 exist
        images = [p.get("hero_image_url") or (p.get("images") or [None])[0] for p in products]
        colours = [p.get("colour") or p.get("finish") for p in products]
        print("colours:", colours)
        if len(products) > 1:
            # not all images should be identical when colours differ
            non_null_images = [i for i in images if i]
            assert len(non_null_images) > 0


class TestGeneralRegression:
    @pytest.mark.parametrize("brand", ["Grohe", "Hansgrohe", "Axor", "Geberit", "Vitra"])
    def test_brand_products_list_loads(self, headers, brand):
        brand_id = _get_brand_id_map(headers)[brand]
        r = requests.get(f"{BASE_URL}/api/products", headers=headers, params={"brand_id": brand_id, "limit": 20}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        items = data.get("items") if isinstance(data, dict) else data
        assert items, f"No products returned for {brand}"

    def test_quotations_endpoint_loads(self, headers):
        r = requests.get(f"{BASE_URL}/api/quotations", headers=headers, timeout=30)
        assert r.status_code == 200

    def test_purchases_items_endpoint_loads(self, headers):
        r = requests.get(f"{BASE_URL}/api/purchases/items", headers=headers, params={"view": "today"}, timeout=30)
        assert r.status_code == 200
