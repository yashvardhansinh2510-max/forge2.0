"""Least-privilege API profiles for narrowly-scoped staff accounts."""
from __future__ import annotations

from re import fullmatch

GROUND_TILE_QUOTATIONS_FOLLOWUPS = "ground_tile_quotations_followups"
GROUND_PAYMENTS_DISPATCHES = "ground_payments_dispatches"
SANITARY_QUOTATIONS_FOLLOWUPS = "sanitary_quotations_followups"
SANITARY_PURCHASES = "sanitary_purchases"

PROFILE_MODULES = {
    GROUND_TILE_QUOTATIONS_FOLLOWUPS: {"tiles", "followups"},
    GROUND_PAYMENTS_DISPATCHES: {"payments", "orders"},
    SANITARY_QUOTATIONS_FOLLOWUPS: {"quotations", "followups"},
    SANITARY_PURCHASES: {"purchases"},
}

# Account/session functions and the single assigned-floor selector. No
# business records are exposed by these endpoints.
_COMMON = {
    ("GET", "/api/auth/me"), ("POST", "/api/auth/change-password"),
    ("POST", "/api/auth/logout"), ("GET", "/api/auth/sessions"),
    ("POST", "/api/auth/sessions/logout-all"),
    ("GET", "/api/settings/floor-access"), ("GET", "/api/settings/floors"),
    ("GET", "/api/settings/permission-matrix"), ("GET", "/api/roles"),
}


def _catalog_read(method: str, path: str) -> bool:
    return method == "GET" and (
        path.startswith("/api/products") or path.startswith("/api/catalog/")
        or fullmatch(r"/api/families/[^/]+", path) is not None
        or fullmatch(r"/api/products/[^/]+/media", path) is not None
    )


def _customer_for_quotation(method: str, path: str) -> bool:
    """Lookup/create/update a quote's customer, never use CRM-only actions."""
    if path == "/api/customers":
        return method in {"GET", "POST"}
    return bool(fullmatch(r"/api/customers/[^/]+", path) and method in {"GET", "PATCH"})


def _dispatch_surface(method: str, path: str) -> bool:
    """Dispatch operations only — expressly excludes release and godown moves."""
    if path in {"/api/tile-orders/dispatches", "/api/tile-orders/movements"}:
        return method == "GET"
    if fullmatch(r"/api/tile-orders/dispatches/[^/]+/(godown-received|delivered)", path):
        return method == "POST"
    if fullmatch(r"/api/tile-orders/dispatches/[^/]+/transport", path):
        return method == "PATCH"
    if fullmatch(r"/api/tile-orders/dispatches/[^/]+", path):
        return method in {"GET", "PATCH"}
    if fullmatch(r"/api/tile-orders/chalans/[^/]+(?:/pdf)?", path):
        return method == "GET"
    if fullmatch(r"/api/tile-orders/customer-orders(?:/[^/]+(?:/timeline)?)?", path):
        return method == "GET"
    if fullmatch(r"/api/tile-orders/purchase-orders/[^/]+", path):
        return method == "GET"
    return bool(fullmatch(r"/api/tile-orders/purchase-orders/[^/]+/dispatch-from-(released|godown)", path) and method == "POST")


def profile_allows_request(profile: str | None, method: str, path: str) -> bool:
    """Fail-closed API allow-list. No profile preserves existing staff access."""
    if not profile:
        return True
    method = method.upper()
    if (method, path) in _COMMON or (method == "DELETE" and fullmatch(r"/api/auth/sessions/[^/]+", path)):
        return True
    if profile in {GROUND_TILE_QUOTATIONS_FOLLOWUPS, SANITARY_QUOTATIONS_FOLLOWUPS}:
        return (path.startswith("/api/quotations") or path.startswith("/api/followups")
                or _customer_for_quotation(method, path) or _catalog_read(method, path)
                or (method == "POST" and path == "/api/downloads/token"))
    if profile == GROUND_PAYMENTS_DISPATCHES:
        return path.startswith("/api/payments") or _dispatch_surface(method, path)
    if profile == SANITARY_PURCHASES:
        return (path.startswith("/api/purchases") or path.startswith("/api/purchase-orders")
                or path.startswith("/api/suppliers")
                or (method == "GET" and path.startswith("/api/activity/purchase/"))
                or (method == "GET" and path == "/api/customers")
                or (method == "POST" and path == "/api/downloads/token"))
    return False
