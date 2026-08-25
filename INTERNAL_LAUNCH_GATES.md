# Controlled Internal Launch Gates

Do not open the staff application to normal use until every required item has
an owner and dated evidence. Code checks are necessary but cannot prove live
provider policy, secrets, or recovery capability.

## Required before deployment

- Rotate the historical `owner@forge.app` password with
  `python -m scripts.rotate_demo_credentials --apply`, invalidate its active
  sessions, and verify `/api/health` is no longer degraded.
- Run `python scripts/run_migrations.py --dry-run` using the exact deployment
  environment, then run `python bootstrap.py`; both must succeed before a
  release is restarted. The application now acquires a Mongo migration lease,
  but deployments should still use one replica for this controlled launch.
- Confirm Atlas backup/PITR is enabled, take a named pre-release snapshot, and
  record a tested restore owner and rollback decision path.
- Verify Supabase bucket policy with non-service credentials: `forge-products`
  may expose only intended product media; `forge-private` must deny anonymous
  listing/direct reads and only accept expiring signed links.
- Configure `SENTRY_DSN`, verify a non-production `/sentry-debug` event, and
  assign an alert recipient for API readiness failures and outbox dead letters.

## Post-deployment smoke test

- `/api/health/ready` returns 200 only when MongoDB and Supabase buckets are
  reachable; admin `/api/health/system` reports healthy.
- Authenticate as staff, read catalog data, upload/download representative
  media, and complete one order/payment/outbox workflow in staging.
- Check authenticated `/api/ops/outbox`: no `dead_letter` events and no
  unexpected pending backlog.
- Keep one application replica until shared Redis rate limiting and edge/WAF
  limits are configured and tested for a multi-replica deployment.

## Rollback

- Stop traffic and retain the failed deployment logs/Sentry event ID.
- Roll back application code only when its database migrations are backward
  compatible; migrations are forward-only and must not be rolled back by
  deleting migration records.
- Restore data only into an isolated environment first, validate counts and
  authentication, then obtain the release owner's approval before production
  restoration.
