# Current State

- Production architecture remains FastAPI + Expo/React Native Web + MongoDB Atlas + Supabase Storage.
- Catalog baseline from the last verified persistent environment is 2,966 products and 2,970 media records.
- The current preview container lost ignored `.env` files during recreation; this is an ephemeral-preview persistence limitation.
- Infrastructure hardening is complete and backend-testing-agent verified: process environment is authoritative, local `.env` is fallback-only, and startup is gated by a green preflight.
- Task 1 first performance improvement is complete and backend-testing-agent verified: repeated authenticated principal validation fell from ~280 ms cold to ~42 ms warm, with revocation and RBAC regressions passing.
- `PERFORMANCE.md` contains direct-vs-preview timings, Mongo plans, bundle/image findings, before/after benchmarks, and remaining bottlenecks.
