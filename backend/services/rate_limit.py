"""In-memory login rate limiting — brute-force protection for staff/customer
authentication endpoints.

Production readiness audit (2026-08): login endpoints had NO rate limiting at
all — any actor could attempt unlimited password guesses against a known
email. This is a real gap fixed here with the smallest safe mechanism that
matches the app's existing style (see auth.py's `_principal_cache`, also a
deliberate in-memory cache): a sliding window keyed by (ip, identifier).

Scope/limits of this approach (documented, not hidden): state is per-process
and resets on restart/deploy, and does not share state across multiple
backend replicas. That is an acceptable trade-off for a single-instance
launch and is dramatically better than no limiting at all. If Forge is ever
horizontally scaled behind a load balancer, replace `_attempts` with a
shared store (Redis `INCR`+`EXPIRE` is the standard swap) — the
`check_rate_limit()` call site does not need to change.

Load-balancer note (found during the Phase 9 audit's own testing): behind a
reverse proxy/k8s ingress, `request.client.host` can report the proxy's
internal per-pod IP rather than a stable client IP, so a single attacker can
appear to come from a small rotating set of IPs and partially dilute the
per-(ip,email) bucket. To close that gap without depending on IP at all, an
IP-INDEPENDENT per-email ceiling is enforced as well (`_PER_EMAIL_LIMIT`) —
an attacker cannot exceed this no matter how many source IPs they present.
"""
from __future__ import annotations

from time import monotonic

from fastapi import HTTPException

# 8 failed attempts per (ip, email) per 15 minutes, and a broader 40/15min per
# IP across any email, to blunt both targeted guessing and distributed spray.
# 8 failed attempts per (ip, email) per 15 minutes, and a broader 40/15min per
# IP across any email, to blunt both targeted guessing and distributed spray.
# PLUS a 15/15min ceiling keyed on email ALONE (no IP) — closes the gap where
# a proxy/load balancer presents a rotating set of source IPs for the same
# attacker (see module docstring).
_PER_KEY_LIMIT = 8
_PER_IP_LIMIT = 40
_PER_EMAIL_LIMIT = 15
_WINDOW_SECONDS = 15 * 60
_MAX_TRACKED_KEYS = 20_000

_attempts: dict[str, list[float]] = {}


def _prune(key: str, now: float) -> list[float]:
    window_start = now - _WINDOW_SECONDS
    hits = [t for t in _attempts.get(key, []) if t > window_start]
    _attempts[key] = hits
    return hits


def _register_failure(key: str, now: float) -> None:
    if len(_attempts) >= _MAX_TRACKED_KEYS:
        # Cheap bound on unbounded growth from a distributed spray attack —
        # drop the oldest-looking entries rather than tracking forever.
        stale = [k for k, hits in _attempts.items() if not hits or hits[-1] < now - _WINDOW_SECONDS]
        for k in stale[: len(stale) // 2 or 1]:
            _attempts.pop(k, None)
    _attempts.setdefault(key, []).append(now)


def check_login_rate_limit(ip: str | None, identifier: str) -> None:
    """Call BEFORE attempting a password check. Raises 429 if the
    per-(ip,identifier), per-ip, OR the IP-independent per-email ceiling is
    already exhausted. Does NOT record an attempt itself — call
    `record_login_failure` after a failed password check so successful
    logins never count against the limit."""
    ip = ip or "unknown"
    now = monotonic()
    key_hits = _prune(f"k:{ip}:{identifier.lower()}", now)
    ip_hits = _prune(f"ip:{ip}", now)
    email_hits = _prune(f"email:{identifier.lower()}", now)
    if len(key_hits) >= _PER_KEY_LIMIT or len(ip_hits) >= _PER_IP_LIMIT or len(email_hits) >= _PER_EMAIL_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please wait a few minutes and try again.",
        )


def record_login_failure(ip: str | None, identifier: str) -> None:
    ip = ip or "unknown"
    now = monotonic()
    _register_failure(f"k:{ip}:{identifier.lower()}", now)
    _register_failure(f"ip:{ip}", now)
    _register_failure(f"email:{identifier.lower()}", now)


def clear_login_attempts(ip: str | None, identifier: str) -> None:
    """Call after a SUCCESSFUL login so a legitimate user who mistyped their
    password a few times isn't stuck waiting once they get it right."""
    ip = ip or "unknown"
    _attempts.pop(f"k:{ip}:{identifier.lower()}", None)
    _attempts.pop(f"email:{identifier.lower()}", None)
