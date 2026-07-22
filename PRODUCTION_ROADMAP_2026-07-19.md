# Production Roadmap — 19 Jul 2026

Sequencing per explicit user decision: **ship an enterprise-grade ERP first, submit to app
stores last.** Store submission is Phase 7, not Phase 1. This doc replaces "next steps" guessing
with a concrete, source-grounded backlog — every item below was verified against current code on
2026-07-19, not copied from a stale audit.

Auth note: Google Sign-In and Apple Sign-In are both explicitly out of scope, permanently. Login
is email/password only. This also closes the Apple Guideline 4.8 blocker that `APP_STORE_PLAY_STORE_AUDIT.md`
flagged (written before Google Sign-In was removed) — no social login means no Sign-in-with-Apple
requirement.

Status legend: ✅ done (verified in code) · 🟡 partial · ⬜ not started.

---

## Phase 1 — UI/UX polish across every module

Source: `MOBILE_UX_AUDIT.md` (2026-07-16, page-by-page findings, not yet re-verified as fixed).

**Shared system fixes first — these block every page-level fix below, do them once:**

1. ⬜ Consolidate `src/design/tokens.ts` vs `src/theme/tokens.ts` — two typography/spacing systems
   currently coexist; screens mix both. Pick one, delete the other.
2. ⬜ Make `AdminPage.tsx:45-66` phone-aware — it always applies tablet padding, so every
   settings/admin page inherits the wrong rhythm on a phone.
3. ⬜ Enforce 44×44 minimum touch targets — `design/components.tsx:112-195` and `components/ui.tsx:75-178`
   still expose 30–40px controls.
4. ⬜ Remove destructive `numberOfLines={1}` from business data (customer names, SKU, prices,
   pipeline labels) — needs wrapping or two-line layout instead.
5. ⬜ Pick one breakpoint authority — code currently mixes 640/768/900/1024 and ad-hoc local
   width checks (`followups.tsx`, `payments.tsx`, `purchases.tsx`, `BuilderShell.tsx`,
   `ProductModal.tsx`).

**Then, page-by-page** (full list with exact file:line evidence in `MOBILE_UX_AUDIT.md`):

- Quotation Builder (highest risk — sheet-driven flow, modal nesting, keyboard/safe-area overlap)
- Catalog (filter header eats vertical space, card title truncation, `initialNumToRender={120}` not phone-safe)
- Purchases tracker (header actions wrap badly, 18px checkboxes / 30px move buttons)
- Customers, Payments, Follow-ups, Settings hub + sub-pages, Customer portal
- Dashboard KPI grid (cramped 2-column wrap at 320–375px)
- Reports route (minimal/unfinished-looking — needs a real empty state or removal from nav)

Already fixed (2026-07-16, confirmed via memory + git-adjacent docs): `PageHeader` truncation,
`StatTile` money-truncation on Customers, Purchases/`Followups` missing `alignItems:"stretch"`
flexbox trap, doubled ₹ symbol bug. Don't re-do these — verify they still hold, then move to the
list above.

**Effort:** 1–2 weeks for the shared pass, 2–3 weeks for page-by-page, assuming no new features
land concurrently.

---

## Phase 2 — Performance optimization

Source: `PERFORMANCE.md` (baseline 2026-07-12), `SPRINT_REPORT.md`.

✅ Task 1 done and verified: auth tax fixed (concurrent session+principal validation, 10s cache) —
`/auth/me` and friends went from ~458ms fixed tax to near-zero warm.

⬜ Task 2 (next, per `NEXT_SPRINT.md`): the popular-products query still downloads a full
2,966-row ranking pool per page load (~473ms warm) — needs server-side ranking/pagination instead
of client-side slicing of the whole pool.

⬜ Task 3+ candidates, not yet started:
- Verified infinite scroll on the Catalog screen (currently `initialNumToRender={120}`, flagged
  in both `PERFORMANCE.md` and `MOBILE_UX_AUDIT.md` as not phone-safe)
- Dashboard reconciliation bottleneck (mentioned in `SPRINT_REPORT.md` as measured but deferred)
- Bundle size (3.15MB uncompressed production JS bundle — not yet profiled for reduction)
- Image loading/caching strategy for catalog media (2,970 records)
- Hierarchy aggregation query (508ms warm, returns 2,447 grouped rows) — candidate for caching

**Effort:** 1–2 weeks, sequential (each task needs its own before/after verification per the
project's established measurement discipline — don't skip that for these).

---

## Phase 3 — Backend validation (workflow integrity, floor isolation, data consistency)

Source: `BACKEND_AUDIT_2026-07-17.md` + `PRODUCTION_FIXES_2026-07-17.md`, re-verified 2026-07-19.

✅ **Floor isolation — confirmed complete**, not partial: `floor_query`/`floor_for_write` now
guard catalog (products, brands, categories — brands/categories gained a real `floor_id` field,
previously had none), media, purchases_tracker, suppliers. This closes the P0 items the earlier
`PRODUCTION_READINESS_AUDIT.md` flagged.

✅ All 5 Critical + all 13 High findings from `BACKEND_AUDIT_2026-07-17.md` fixed (demo creds,
SSRF redirect-revalidation, catalog-import rollback, inventory race via optimistic concurrency,
CI running real tests).

Remaining Medium-priority items, not yet done:
- ⬜ Money is still plain `float` (bounds added via `Field(ge=0)`, but no `Decimal`/integer-paise
  precision) — rounding drift risk across quotations/POs/payments at ₹10–50L order values.
- ⬜ Unbounded embedded arrays (`PurchaseOrderItem.stage_history`, `Quotation.revisions`) — no
  archival strategy, trending toward MongoDB's 16MB document limit on long-lived records.
- ⬜ Media dedupe check-then-insert race (no unique index on `(sha1, product_id, source_type)`).
- ⬜ Media replace/delete are non-atomic two-step operations — a crash mid-operation can orphan
  storage objects or leave stale + new images both live.
- ⬜ Global activity feed still has no real per-event `floor_id` (containment fix applied —
  restricted staff get an empty feed rather than cross-floor data — but the real fix needs
  `services/activity_log.log_event` updated at 30+ call sites).
- ⬜ Outbox notifications can fire from a transaction that later aborts (`domain_outbox.py:222-228`
  schedules `notify()` via `asyncio.create_task` before the surrounding transaction commits).
- ⬜ Multi-worker cache incoherence only partially addressed — Redis-backed login rate limiting
  landed, but `auth.py`'s principal cache and `catalog_service.py`'s in-memory snapshot are still
  process-local globals with no cross-worker coordination (`Dockerfile` runs `--workers 2`).

**Effort:** 3–5 days — this phase is mostly closing out a known, already-scoped list, not new
discovery.

---

## Phase 4 — Production operations

Source: `BACKEND_AUDIT_2026-07-17.md` Medium/Low findings, `PRODUCTION.md`.

- ⬜ **Backups**: `scripts/backup_db.py` is manual, non-scheduled, and not cross-collection
  consistent (dumps each collection independently with no snapshot boundary). No cron invokes it.
  Needs: scheduled run + restore-drill verification.
- ⬜ **Structured logging / request IDs** — not present per prior audits.
- ⬜ **Crash reporting / analytics activation decision** — Sentry/PostHog are wired but inert (no
  DSN/API key, zero `captureEvent` call sites). Decide before Phase 6 regression testing starts,
  since you'll want crash visibility during that pass, not after.
- ⬜ **Health checks / monitoring dashboards** — `/api/health` exists and reports `degraded` state
  for demo-credential drift; no external monitoring/alerting wired to it yet.
- ⬜ Migrate FastAPI `@app.on_event` startup/shutdown to lifespan handlers (deprecated API, Low
  priority but cheap).

**Effort:** 3–4 days for backups + logging baseline; monitoring/alerting can extend post-launch.

---

## Phase 5 — Regression testing across First Floor and Ground Floor

- ⬜ Backend: `pytest tests/unit` currently passes (45 tests) but coverage is concentrated on the
  2026-07-17 hardening set — needs floor-isolation-specific regression tests for every module and
  mutation route per the original roadmap's Phase 1 recommendation (catalog, media, purchases,
  customers, follow-ups — confirm cross-floor access is actually rejected, not just scoped).
- ⬜ Ground Floor currently has no real distinct catalog data (per project memory: "Ground-floor's
  real 'all-tile' catalog is still queued, user will supply real tile product data later") — full
  two-floor regression needs that data in place first, or a synthetic equivalent for test purposes.
- ⬜ End-to-end smoke pass repeated per floor: login, catalog browse, quotation build → PDF,
  purchase order flow, payment recording, follow-ups — once per floor, confirming no cross-floor
  leakage anywhere in the UI (not just the API).

**Effort:** depends on Ground Floor data availability — flag this dependency early, don't let it
block the rest of the phase silently.

---

## Phase 6 — Mobile/tablet responsiveness + accessibility audit

This is a **real device pass**, distinct from Phase 1's source-level UI fixes. `MOBILE_UX_AUDIT.md`
explicitly notes its findings are static source evidence, not device-verified (backend wasn't
running during that audit).

- ⬜ VoiceOver (iOS) and TalkBack (Android) passes against the touch-target/truncation issues from
  Phase 1.
- ⬜ Device matrix: 320px, 375px, 390px, 430px widths; landscape phone; iPad/tablet.
- ⬜ Dynamic Type / large-text test — confirm no essential label disappears.
- ⬜ Loading/empty/error/offline/disabled/selected/validation/success states, verified per data
  page, not assumed from source.
- ⬜ Confirm no hover-only actions remain on touch (audit flagged `dashboard.tsx:86` as a concrete
  example).

**Effort:** 1 week, requires physical devices or a device farm — flag if unavailable, since static
review can't substitute for this phase per the audit's own caveat.

---

## Phase 7 — App Store / Play Store submission

Deferred until Phases 1–6 are substantially done. Full existing checklist in
`APP_STORE_PLAY_STORE_AUDIT.md` — re-verified 2026-07-19, updated status:

**Already resolved:**
- ✅ Icon regenerated to 1024×1024, alpha flattened.
- ✅ ATS/cleartext guard added — release build fails loud instead of booting network-dead if
  `EXPO_PUBLIC_BACKEND_URL` isn't `https://`.
- ✅ Demo credentials rotated.
- ✅ In-app privacy/data screen added (`Settings → Privacy & data`, `/privacy` public route).
- ✅ **Sign in with Apple requirement is moot** — no social login exists anymore.

**Still open when this phase starts:**
- ⬜ Privacy policy needs a separately hosted, stable URL on a real domain — the in-app screen
  doesn't satisfy App Store Connect/Play Console's URL field requirement by itself.
- ⬜ `eas.json`'s `submit.production` is still `{}` — no submission credentials wired.
- ⬜ Canonical build pipeline still undecided — `PRODUCTION.md` says use "Emergent publish
  button," `eas.json` implies direct EAS. Pick one, confirm who owns the resulting App Store
  Connect / Play Console records.
- ⬜ Store-listing assets: screenshots, description, age rating, Data Safety form, ads
  declaration — none exist in-repo.
- ⬜ Fresh, scoped reviewer account (not any internal credential).
- ⬜ Push notifications, offline handling (no NetInfo dependency), deep-linking beyond OAuth
  return — decide v1 stance for each; if skipping, make sure no store-listing copy implies
  otherwise.
- ⬜ `PrivacyInfo.xcprivacy` manifest — unverified, likely needs adding.
- ⬜ Splash screen aspect ratio (336×729 poster image used where the plugin expects a small logo
  mark) — needs a new design asset.
- ⬜ Customer portal has no privacy/deletion screen equivalent (staff Settings only).

**Effort:** 1–1.5 weeks once started, plus review-cycle latency (Apple/Google review time is
outside your control — budget days, not hours, per submission).

---

## What NOT to do

- Don't re-propose Google or Apple Sign-In — both explicitly rejected.
- Don't start Phase 7 work opportunistically "since it's quick" — the whole point of this
  sequencing is that store submission timing follows app quality, not the reverse.
- Don't re-run the floor-isolation P0 fixes from `PRODUCTION_READINESS_AUDIT.md` — confirmed done
  in Phase 3 above; that doc is now stale on those specific items.
