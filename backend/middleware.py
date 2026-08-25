"""Baseline security response headers, added to every response. Complements
CORSMiddleware in server.py (credential-less wildcard CORS, documented
there) rather than replacing any of it — these are defense-in-depth
headers browsers apply regardless of API-vs-page distinction, cheap to
add, no behavior change for any existing client."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in _STATIC_HEADERS.items():
            response.headers.setdefault(header, value)
        # HSTS only makes sense once a request actually arrived over HTTPS.
        # Check both request.url.scheme (direct HTTPS) and X-Forwarded-Proto
        # (for when the app sits behind a TLS-terminating reverse proxy, the
        # expected production topology). In local/http dev neither would be
        # true, which is correct — we don't set HSTS there. Trusting
        # X-Forwarded-Proto is safe: forging it can only affect whether this
        # one header is set, nothing else (no auth bypass, access control, etc).
        scheme_is_https = (
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto", "").lower() == "https"
        )
        if scheme_is_https:
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response
