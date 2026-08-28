# Backend latency observability

`/api/*` responses now include a `Server-Timing: app;dur=<milliseconds>` header.
The duration covers the application middleware and endpoint execution in that
process; it is neither a network round-trip nor a claim of end-to-end latency.

The backend also keeps a bounded 512-request in-process latency window and
emits a structured `slow_request` warning when a request reaches the configured
threshold. Logs contain only HTTP method, matched route template, status, and
duration. They intentionally omit raw paths, query strings, headers, bodies,
and user identifiers.

Configuration (optional):

- `FORGE_REQUEST_TIMING=false` disables request timing in an emergency.
- `FORGE_SLOW_REQUEST_MS=1000` sets the warning threshold in milliseconds.

For deployment verification, sample the public, read-only `/api/health` route
from the intended region and record a distribution (at least min/median/max or
p50/p95). Treat a high first sample separately: it may include MongoDB and
connection warm-up. Use `Server-Timing` plus the slow-request logs to decide
whether a delay is application processing or network/edge transit.

This process-local window is diagnostic only. Configure Sentry/APM for durable,
cross-replica aggregation and alerting before horizontally scaling the API.
