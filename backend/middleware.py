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
        # HSTS only makes sense once a request actually arrived over HTTPS —
        # forcing it in local/http dev would be actively wrong, not just inert.
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response
