"""SecurityHeadersMiddleware adds baseline defense-in-depth response headers
to every request, complementing the CORS reasoning already documented in
server.py rather than replacing any of it. Tested against a minimal
isolated app rather than the full server, which requires live Mongo/
Supabase at startup (see tests/INTEGRATION_TESTING_STRATEGY.md) — this is
pure ASGI-layer behavior, independent of server.py's startup event."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware import SecurityHeadersMiddleware

_app = FastAPI()
_app.add_middleware(SecurityHeadersMiddleware)


@_app.get("/ping")
def _ping():
    return {"ok": True}


client = TestClient(_app)


def test_static_headers_present_on_every_response():
    response = client.get("/ping")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"


def test_hsts_absent_over_http():
    response = client.get("/ping")
    assert "strict-transport-security" not in response.headers


def test_hsts_present_when_request_scheme_is_https():
    https_client = TestClient(_app, base_url="https://testserver")
    response = https_client.get("/ping")
    assert response.headers["strict-transport-security"] == "max-age=63072000; includeSubDomains"


def test_hsts_present_when_x_forwarded_proto_is_https():
    response = client.get("/ping", headers={"X-Forwarded-Proto": "https"})
    assert response.headers["strict-transport-security"] == "max-age=63072000; includeSubDomains"


def test_hsts_absent_with_non_https_forwarded_proto():
    response = client.get("/ping", headers={"X-Forwarded-Proto": "http"})
    assert "strict-transport-security" not in response.headers
