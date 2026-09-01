"""Safe, bounded loading of server-owned images for PDF rendering.

PDF generation is synchronous, so this module deliberately exposes a
thread-safe synchronous API.  Its executor, connection pool and cache are
process-wide: a burst of quotation requests cannot create a new set of
network workers for each PDF.
"""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
import ipaddress
import os
import socket
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Callable, Iterable
from urllib.parse import urljoin, urlparse

import httpx

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_CACHE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_DIMENSION = 8_000
MAX_REDIRECTS = 3
CACHE_TTL_SECONDS = 15 * 60
MAX_CONCURRENT_FETCHES = 6
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


@dataclass
class _CacheEntry:
    data: bytes
    expires_at: float


_cache: OrderedDict[str, _CacheEntry] = OrderedDict()
_cache_bytes = 0
_cache_lock = Lock()
_fetch_slots = BoundedSemaphore(MAX_CONCURRENT_FETCHES)
_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_FETCHES, thread_name_prefix="pdf-image")
_client = httpx.Client(timeout=httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=2.0), follow_redirects=False)
_metrics = {"requests": 0, "cache_hits": 0, "failures": 0, "image_bytes": 0, "queue_ms": 0.0, "duration_ms": 0.0}
_metrics_lock = Lock()


def _allowed_hosts() -> set[str]:
    """Return configured storage/CDN hosts without importing application settings.

    Keeping this environment-only avoids pulling database configuration into
    report-generation unit tests.  SUPABASE_URL is required by runtime config;
    PDF_IMAGE_ALLOWED_HOSTS is an optional comma-separated CDN extension.
    """
    hosts: set[str] = set()
    for raw in (os.environ.get("SUPABASE_URL", ""), *os.environ.get("PDF_IMAGE_ALLOWED_HOSTS", "").split(",")):
        candidate = raw.strip()
        if not candidate:
            continue
        parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
        if parsed.hostname:
            hosts.add(parsed.hostname.lower().rstrip("."))
    return hosts


def _is_public_address(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


def validate_image_url(url: str, *, allowed_hosts: set[str] | None = None, resolver=socket.getaddrinfo) -> bool:
    """Accept only configured HTTPS hosts resolving solely to public IPs."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        return False
    if host not in (allowed_hosts if allowed_hosts is not None else _allowed_hosts()):
        return False
    try:
        records = resolver(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except (OSError, ValueError):
        return False
    addresses = {record[4][0] for record in records}
    return bool(addresses) and all(_is_public_address(address) for address in addresses)


def _cache_get(url: str) -> bytes | None:
    now = monotonic()
    with _cache_lock:
        entry = _cache.get(url)
        if entry is None:
            return None
        if entry.expires_at <= now:
            _cache.pop(url)
            global _cache_bytes
            _cache_bytes -= len(entry.data)
            return None
        _cache.move_to_end(url)
        return entry.data


def _cache_put(url: str, data: bytes) -> None:
    global _cache_bytes
    if len(data) > MAX_CACHE_BYTES:
        return
    with _cache_lock:
        previous = _cache.pop(url, None)
        if previous:
            _cache_bytes -= len(previous.data)
        _cache[url] = _CacheEntry(data=data, expires_at=monotonic() + CACHE_TTL_SECONDS)
        _cache_bytes += len(data)
        while _cache and _cache_bytes > MAX_CACHE_BYTES:
            _, evicted = _cache.popitem(last=False)
            _cache_bytes -= len(evicted.data)


def _valid_image(data: bytes, content_type: str) -> bool:
    if content_type.split(";", 1)[0].strip().lower() not in ALLOWED_IMAGE_MIME_TYPES:
        return False
    try:
        from PIL import Image
        from PIL import Image as PILImage
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
        with PILImage.open(__import__("io").BytesIO(data)) as image:
            if (image.format or "").upper() == "GIF" or getattr(image, "n_frames", 1) != 1:
                return False
            width, height = image.size
            if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION or width * height > MAX_IMAGE_PIXELS:
                return False
            image.verify()
        return True
    except Exception:
        return False


def _fetch_uncached(url: str) -> bytes | None:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        if not validate_image_url(current):
            return None
        try:
            with _client.stream("GET", current, headers={"Accept": "image/jpeg,image/png,image/webp"}) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        return None
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    return None
                declared_size = response.headers.get("content-length")
                if declared_size and int(declared_size) > MAX_IMAGE_BYTES:
                    return None
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        return None
                    chunks.append(chunk)
                data = b"".join(chunks)
                if not data or not _valid_image(data, response.headers.get("content-type", "")):
                    return None
                return data
        except (httpx.HTTPError, OSError, ValueError):
            return None
    return None


def remote_image_bytes(url: str) -> bytes | None:
    """Fetch one eligible image with TTL/byte-aware caching and metrics."""
    started = monotonic()
    cached = _cache_get(url)
    with _metrics_lock:
        _metrics["requests"] += 1
    if cached is not None:
        with _metrics_lock:
            _metrics["cache_hits"] += 1
            _metrics["duration_ms"] += (monotonic() - started) * 1000
        return cached
    # This is also called synchronously by a cold `_img` lookup after a
    # prefetch timeout.  Own the process-wide slot here (rather than only in
    # prefetch_urls) so *every* network path shares the same global budget.
    queued = monotonic()
    with _fetch_slots:
        with _metrics_lock:
            _metrics["queue_ms"] += (monotonic() - queued) * 1000
        data = _fetch_uncached(url)
    with _metrics_lock:
        _metrics["duration_ms"] += (monotonic() - started) * 1000
        if data is None:
            _metrics["failures"] += 1
        else:
            _metrics["image_bytes"] += len(data)
    if data is not None:
        _cache_put(url, data)
    return data


def prefetch_urls(urls: Iterable[str], fetch: Callable[[str], bytes | None] = remote_image_bytes, *, workers: int = MAX_CONCURRENT_FETCHES, timeout: float = 8.0) -> None:
    """Use the global worker pool, with a per-PDF concurrency budget."""
    unique = list(dict.fromkeys(urls))
    if not unique:
        return
    budget = BoundedSemaphore(max(1, min(workers, MAX_CONCURRENT_FETCHES)))

    def run(url: str) -> bytes | None:
        with budget:
            return fetch(url)

    futures = [_executor.submit(run, url) for url in unique]
    _, pending = wait(futures, timeout=max(0.1, timeout))
    for future in pending:
        future.cancel()


def image_loader_metrics() -> dict[str, float | int]:
    """Return PII-free counters suitable for structured PDF instrumentation."""
    with _metrics_lock, _cache_lock:
        return {**_metrics, "cache_entries": len(_cache), "cache_bytes": _cache_bytes, "max_concurrency": MAX_CONCURRENT_FETCHES}
