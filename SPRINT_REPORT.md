# Sprint Report

## Verified milestones

### Configuration hardening

- **Problem:** backend entered a `KeyError` crash loop whenever ignored `.env` files vanished after preview-container recreation.
- **Root cause:** Emergent preview is ephemeral and does not persist/inject custom secrets; this is platform persistence-by-design, not Forge deleting files.
- **Fix:** centralized process-environment-first settings, optional non-overriding local fallback, descriptive fail-fast validation, and startup-gating `bootstrap.py` checks for Atlas, Supabase, buckets, collections, indexes, and health.
- **Verification:** backend testing agent passed all infrastructure checks; production DB `buildcon_house` reports 2,966 products and 2,970 media records.

### Task 1 first performance improvement

- **Problem:** navigation APIs were slow even over localhost; preview ingress added only ~0–40 ms.
- **Root cause:** every authenticated API request performed two sequential remote Atlas reads (session + principal), adding ~458 ms before endpoint work.
- **Fix:** concurrent first validation plus a bounded 10-second cache of successful active principals; all logout/revoke flows explicitly invalidate it.
- **Verification:** backend testing agent passed 8/8 groups. Staff/customer auth cold 280 ms → warm 42 ms (85%, 6.7× faster); RBAC, logout, logout-all, single-session revoke, legacy JWT, and eight smoke endpoints passed; catalog remains 2,966.
- **Benchmarks:** `PERFORMANCE.md` records endpoint before/after results, Mongo plans, preview separation, bundle size, image cache evidence, risks, and remaining bottlenecks.

## Remaining

- Task 1 still has measured catalog query/refetch and dashboard reconciliation bottlenecks, but sprint rules require stopping after this first verified improvement.
- Task 2 catalog accessibility is next after user approval.
