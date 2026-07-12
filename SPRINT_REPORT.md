# Sprint Report

## Verified milestone: configuration hardening

- **Problem:** backend entered a `KeyError` crash loop whenever ignored `.env` files vanished after preview-container recreation.
- **Root cause:** Emergent preview is ephemeral and does not persist/inject custom secrets; this is platform persistence-by-design, not Forge deleting files.
- **Fix:** centralized process-environment-first settings, optional non-overriding local fallback, descriptive fail-fast validation, and startup-gating `bootstrap.py` checks for Atlas, Supabase, buckets, collections, indexes, and health.
- **Safety:** startup preflight runs before seed/reconciliation writes and reports missing indexes without silently creating them.
- **Recovery:** placeholder-only tracked templates plus `RECOVERY.md` and `STARTUP_CHECK.md`.
- **Verification:** backend testing agent passed all 7 areas; 10/10 settings tests pass; bootstrap and post-start health are green; production DB `buildcon_house` reports 2,966 products and 2,970 media records.
- **Platform boundary:** only deployment environment settings can persist custom secrets. Application code cannot persist preview-only secrets across container recreation.
- Performance profiling and catalog fixes remain paused pending user approval to resume Task 1.
