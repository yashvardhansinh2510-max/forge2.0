from access_profiles import (
    GROUND_PAYMENTS_DISPATCHES,
    GROUND_TILE_QUOTATIONS_FOLLOWUPS,
    SANITARY_PURCHASES,
    SANITARY_QUOTATIONS_FOLLOWUPS,
    profile_allows_request,
)


def test_tile_quotation_profile_is_limited_to_its_workflow():
    assert profile_allows_request(GROUND_TILE_QUOTATIONS_FOLLOWUPS, "POST", "/api/quotations")
    assert profile_allows_request(GROUND_TILE_QUOTATIONS_FOLLOWUPS, "PATCH", "/api/followups/123")
    assert profile_allows_request(GROUND_TILE_QUOTATIONS_FOLLOWUPS, "GET", "/api/products")
    assert profile_allows_request(GROUND_TILE_QUOTATIONS_FOLLOWUPS, "PATCH", "/api/customers/c-1")
    assert not profile_allows_request(GROUND_TILE_QUOTATIONS_FOLLOWUPS, "DELETE", "/api/customers/c-1")
    assert not profile_allows_request(GROUND_TILE_QUOTATIONS_FOLLOWUPS, "GET", "/api/payments")
    assert not profile_allows_request(GROUND_TILE_QUOTATIONS_FOLLOWUPS, "GET", "/api/purchases/items")


def test_payment_dispatch_profile_cannot_release_or_move_stock():
    assert profile_allows_request(GROUND_PAYMENTS_DISPATCHES, "POST", "/api/payments")
    assert profile_allows_request(GROUND_PAYMENTS_DISPATCHES, "POST", "/api/downloads/token")
    assert profile_allows_request(GROUND_PAYMENTS_DISPATCHES, "POST", "/api/tile-orders/purchase-orders/po-1/dispatch-from-released")
    assert profile_allows_request(GROUND_PAYMENTS_DISPATCHES, "PATCH", "/api/tile-orders/dispatches/d-1/transport")
    assert profile_allows_request(GROUND_PAYMENTS_DISPATCHES, "GET", "/api/tile-orders/history/export")
    assert not profile_allows_request(GROUND_PAYMENTS_DISPATCHES, "POST", "/api/tile-orders/purchase-orders/po-1/ready")
    assert not profile_allows_request(GROUND_PAYMENTS_DISPATCHES, "POST", "/api/tile-orders/purchase-orders/po-1/items/move-to-godown")


def test_sanitary_profiles_are_separated():
    assert profile_allows_request(SANITARY_QUOTATIONS_FOLLOWUPS, "GET", "/api/quotations")
    assert not profile_allows_request(SANITARY_QUOTATIONS_FOLLOWUPS, "GET", "/api/purchases/items")
    assert profile_allows_request(SANITARY_PURCHASES, "GET", "/api/purchases/customers/c-1/workspace")
    assert profile_allows_request(SANITARY_PURCHASES, "GET", "/api/customers")
    assert not profile_allows_request(SANITARY_PURCHASES, "GET", "/api/customers/c-1")
    assert not profile_allows_request(SANITARY_PURCHASES, "GET", "/api/payments/history")
