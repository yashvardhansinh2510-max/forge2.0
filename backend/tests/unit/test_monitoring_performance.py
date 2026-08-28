"""Regression coverage for bounded, PII-safe request latency instrumentation."""
from __future__ import annotations

import logging
import asyncio
from time import monotonic

import httpx

import services.monitoring as monitoring
import server


def test_latency_tracker_is_bounded_and_calculates_percentiles():
    tracker = monitoring.RequestLatencyTracker(max_samples=3)
    for duration in (10, 20, 30, 40):
        tracker.record(duration)

    assert tracker.snapshot() == {
        "count": 3,
        "p50_ms": 30,
        "p95_ms": 40,
        "max_ms": 40,
    }


def test_slow_request_log_uses_route_template_not_raw_url(caplog, monkeypatch):
    monkeypatch.setenv("FORGE_SLOW_REQUEST_MS", "1")
    caplog.set_level(logging.WARNING, logger="forge.monitoring")

    monitoring.record_request_timing(
        method="GET",
        path="/api/products/{product_id}",
        status_code=200,
        started_at=monotonic() - 0.01,
    )

    assert "route=/api/products/{product_id}" in caplog.text
    assert "product-actual-id" not in caplog.text


def test_request_timing_returns_duration_and_updates_tracker(monkeypatch):
    tracker = monitoring.RequestLatencyTracker()
    monkeypatch.setattr(monitoring, "request_latency", tracker)

    duration_ms = monitoring.record_request_timing(
        method="GET",
        path="/api/health",
        status_code=200,
        started_at=monotonic() - 0.002,
    )

    assert duration_ms >= 2
    assert tracker.snapshot()["count"] == 1


def test_api_timing_middleware_adds_server_timing_without_startup(monkeypatch):
    tracker = monitoring.RequestLatencyTracker()
    monkeypatch.setattr(monitoring, "request_latency", tracker)

    async def request_root():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/")

    response = asyncio.run(request_root())

    assert response.status_code == 200
    assert response.headers["server-timing"].startswith("app;dur=")
    assert tracker.snapshot()["count"] == 1
