# Production Roadmap — 23 Jul 2026

Supersedes `PRODUCTION_ROADMAP_2026-07-19.md`. That doc set the sequencing rule (app quality
before store submission) and tracked Phases 1–7. This doc re-verifies every phase's status against
current `main` (`19f7963`, includes the "27 findings" fix commit) and refines the sequencing rule
per an explicit 2026-07-23 decision — see below.

Status legend: ✅ done (verified in code) · 🟡 partial · ⬜ not started.

---

## Sequencing decision (2026-07-23, supersedes the 07-19 rule)

The 07-19 rule was strict: app quality (Phases 1–6) fully done, *then* start Phase 7. Today's
request pushes App Store / Play Store readiness back to the top. Reconciled as:

**Phase 7's groundwork starts now, in parallel with finishing Phases 1–6. Only the final
submission action stays gated behind Phases 3–6 being substantially done and both developer
accounts being active.** Nothing about the quality bar gets rushed — the prep work (policy docs,
build config, compliance manifests, remaining security items) doesn't depend on Phases 3–6 being
done, so there's no reason to leave it idle.

This also folds in two new workstreams the 07-19 doc didn't cover: **security hardening**
("harden everything," Section B below) and **legal/policy content** (Privacy Policy + Terms of
Service, Section C below) — both requested explicitly today, both prerequisites for Phase 7
regardless of sequencing.

---

## Immediate action items (start this week, no code dependencies)

1. **User:** start the Apple Developer Program and Google Play Console applications now. This is
   the longest lead-time item in the whole roadmap — a company Apple account needs a D-U-N-S
   number, which can take 1–2 weeks to issue. Neither account exists yet (confirmed 2026-07-23).
   Nothing else in Phase 7 blocks on this starting immediately.
2. Security hardening pass (Section B) — self-contained backend work, testable in isolation.
3. Draft Privacy Policy + Terms of Service with `[PLACEHOLDER]` markers for legal
   name/address/contact (user chose placeholders over blocking on real facts today). Not
   publishable until placeholders are filled in, but unblocks the rest of Phase 7 prep now.
4. Resume Phases 3–6 below — the actual quality gate.
5. Phase 7 groundwork (Section D) in parallel with 2–4. Submission itself waits on 4.

---

## Phase 1 — UI/UX polish across every module

🟡 Partial, meaningful progress since 07-19. The 27-findings commit (`19f7963`, 23 Jul) fixed:
Tile Orders card grid (fixed 340px → `useBp()`-driven column counts), row-control hit targets,
customer-name truncation, topbar button heights (34px → 44px), fallback text for missing names.
`AdminPage.tsx` phone-padding was separately fixed 18 Jul (predates this doc, the 07-19 snapshot
was stale on that one item).

Still open, unchanged from 07-19:
- ⬜ `src/design/tokens.ts` vs `src/theme/tokens.ts` duplication — two systems still coexist.
- ⬜ Sub-44px controls remain: `components/ui.tsx` Button "sm" / Chip still 34px.
- ⬜ Destructive `numberOfLines={1}` on business data — 183 occurrences app-wide, not addressed
  as a systemic pass (only specific instances fixed opportunistically).
- ⬜ No single breakpoint authority — `BuilderShell.tsx` (1180/820, deliberately container-width
  based) and `ProductModal.tsx` (480px raw window width) still diverge from each other and from
  `useBp()`. `TilesDocBuilder.tsx`'s divergence was reviewed 07-23 and recorded as a **deliberate**
  exception (pixel-faithful printed-document replica), not an oversight — leave it.

**Effort:** 1 week remaining for the shared-system pass; page-by-page sweep from the 07-19 list
still applies where not already covered by the Tiles-module fixes above.

---

## Phase 2 — Performance optimization

Not re-verified in this pass — carrying forward the 07-19 status unchanged. Revisit before
Phase 5 regression testing starts, since performance regressions are easiest to catch alongside
that pass.

⬜ Popular-products query still un-paginated server-side (473ms warm, full 2,966-row pool).
⬜ Catalog infinite-scroll (`initialNumToRender={120}`), bundle size (3.15MB uncompressed),
catalog image loading/caching, hierarchy aggregation caching — all still candidates, none started.

---

## Phase 3 — Backend validation (workflow integrity, floor isolation, data consistency)

✅ Newly confirmed fixed since 07-19: outbox-notifications-before-commit (`4c0a19e`, 22 Jul —
`notify()` now strictly awaited after transaction commit, atomic event-claiming). Chalan
over-release race and Godown/dispatch check-then-act race (Tiles module) fixed 23 Jul via CAS
guards — same bug class this codebase already fixed once for stock moves, now closed here too.

⬜ **Catalog floor-isolation is still not real isolation** — `routes/catalog_routes.py` never
calls `floor_query()`/`floor_for_write()`; Brand/Category models have no `floor_id` field; new
products default to `floor_id="first-floor"`. This has been explicitly deferred pending a product
decision (your own prior instruction: needs a brainstorming pass before implementation, not a
straight bug fix) since 07-17. Still true — resolve this before Phase 5 regression testing, since
you can't regression-test floor isolation that doesn't exist yet.

Still open, unchanged from 07-19:
- ⬜ Money as plain `float`, no `Decimal`/paise-integer precision.
- ⬜ Unbounded embedded arrays (`stage_history`, `Quotation.revisions`).
- ⬜ Media dedupe check-then-insert race; media replace/delete non-atomic.
- ⬜ Activity feed has no real per-event `floor_id` (containment fix only).
- ⬜ Multi-worker cache incoherence — `auth.py` principal cache and `catalog_service.py`'s
  in-memory snapshot are still process-local globals against `--workers 2`.
- ⬜ Duplicate SKU `26456000` (two Hansgrohe products) still blocks the `products_sku_brand_unique`
  index from auto-applying — needs your call on which record is correct.

**Effort:** 3–5 days for the remaining Medium items; the floor-isolation decision is the real
schedule risk — it's a product conversation, not an estimate.

---

## Phase 4 — Production operations

No evidence of movement since 07-19 — all items still open:

- ⬜ Backups: `scripts/backup_db.py` manual, non-scheduled, no cross-collection snapshot boundary.
- ⬜ Structured logging / request IDs.
- ⬜ Sentry/PostHog activation decision — still wired but inert (no DSN/API key, zero
  `captureEvent` call sites). Decide before Phase 5 starts; you'll want crash visibility during
  regression testing, not after.
- ⬜ External monitoring/alerting on `/api/health`.
- ⬜ FastAPI `@app.on_event` → lifespan handlers (deprecated API, low priority, cheap).

**Effort:** 3–4 days for backups + logging baseline.

---

## Phase 5 — Regression testing across First Floor and Ground Floor

⬜ Blocked on Phase 3's floor-isolation decision — can't regression-test isolation that isn't
implemented. Also still blocked on Ground Floor catalog data: confirmed 22 Jul the Tiles product
picker has zero real products (`floor_id="ground-floor"` catalog is empty), so end-to-end
two-floor smoke testing has nothing real to test against yet on that floor.

No change otherwise from the 07-19 plan (floor-isolation-specific regression tests per module,
full smoke pass per floor).

---

## Phase 6 — Mobile/tablet responsiveness + accessibility audit

🟡 Meaningful progress, not complete. 23 Jul commit added `accessibilityRole`/`accessibilityLabel`
to the shared Button/IconButton components, sidebar/tablet-rail/mobile-tab-bar nav, and dashboard
list rows — verified live via the accessibility tree at those specific surfaces.

⬜ **Still the single highest-leverage a11y gap**: pulling the live accessibility tree elsewhere
(list rows outside dashboard, nav items not yet covered) still shows unlabeled `generic` roles —
VoiceOver/TalkBack announce these as anonymous tappable regions. This is source-level partial
coverage, not yet a full pass.
⬜ Real-device VoiceOver/TalkBack pass, device matrix (320/375/390/430px + tablet + landscape),
Dynamic Type test, full state matrix (loading/empty/error/offline/disabled/validation/success) —
none of this has been done as a device pass; everything above was source-level or live-browser
verification at 1280/768/375px, not physical devices.

**Effort:** 3–4 days for the remaining source-level a11y sweep; 1 week for the real-device pass
(needs physical devices or a device farm — flag if unavailable).

---

## Section B — Security hardening ("every security thing enabled")

✅ Done 23 Jul: both `/auth/change-password` endpoints now rate-limited (previously only login
was — a stolen session token had unlimited password-guess attempts). FastAPI/Starlette/uvicorn/
motor/pymongo bumped off an early-2024 release train, verified via full test suite + live boot
against real Supabase/Mongo. npm critical (`tar`) and high (`undici`) advisories cleared via
`npm audit fix`.

Still open:
- ⬜ CORS is `allow_origins=["*"]` — deliberate and defensible today (Bearer-JWT auth, not
  cookie-based), but should lock to the production domain once one exists. Don't do this before
  a real domain is live, or you'll break local dev / preview builds.
- ⬜ No unique index on `customers.email`; `user_sessions`' documented required indexes are never
  created by any script in the repo (per `bootstrap.py`).
- ⬜ Automated dependency scanning in CI (Dependabot or equivalent) — the 23 Jul fix was a
  one-off `npm audit fix` pass, not a standing process. One moderate npm advisory remains, needs
  an Expo major-version bump (breaking) — deliberately deferred to a separate, device-tested
  upgrade, not done opportunistically here.
- ⬜ Duplicate-SKU index gap (see Phase 3) is security-adjacent — an unenforced unique constraint.
- ⬜ Multi-worker cache/rate-limit incoherence (see Phase 3) is also security-adjacent: with
  `--workers 2` and process-local rate-limit state, the *effective* rate limit on any endpoint
  not backed by the Redis-based limiter is 2x the configured value.
- ⬜ Standard pre-launch hardening not yet audited this pass: HSTS/CSP/X-Frame-Options headers,
  secure JWT cookie flags if any cookie-based flows exist, audit-log completeness for
  security-relevant actions (role changes, permission grants, credential resets).

Confirmed solid, no action needed: `.env` hygiene, Dockerfile non-root/no debug flags, declared
iOS/Android permissions match actual usage exactly, Redis-backed login rate limiting is real and
tested, SSRF guard on catalog-import (fixed 07-17, re-verified holding).

**Effort:** 2–3 days for the index/CI items; CORS lock and header hardening should happen right
before the prod domain goes live, not now.

---

## Section C — Legal & policy content

Two documents, neither currently usable for store submission:

- **Privacy Policy**: exists only as an in-app screen (`frontend/app/privacy.tsx`,
  `src/components/PrivacyPolicyContent.tsx`) with no hosted public URL. Both App Store Connect
  and Play Console require a URL at submission time, not an in-app view. Needs real content
  covering: customer PII collected, Sentry error tracking, PostHog analytics (once activated per
  Phase 4), staff account data, payment/order data, third-party processors (MongoDB Atlas,
  Supabase, Sentry, PostHog), data retention, and user rights.
- **Terms of Service**: does not exist anywhere in the repo (frontend or backend) — confirmed by
  search, zero hits. Needs acceptable-use terms, account terms (staff vs. customer distinction),
  liability, quotation/document content ownership, termination.

**Open assumption, needs your confirmation**: treating this as an Indian legal entity given ₹
pricing throughout the app. If correct, India's DPDP Act 2023 / IT Rules 2021 likely require a
named Grievance Officer contact in the Privacy Policy. Flag if this assumption is wrong.

Both documents will be drafted with `[LEGAL_ENTITY_NAME]` / `[REGISTERED_ADDRESS]` /
`[CONTACT_EMAIL]` placeholders (your choice today) — **not publishable to either store until
those are filled in with real facts.**

"Across all viewpoints" means linked from: staff login screen, customer portal, admin/staff
Settings (already has a `Privacy & data` entry — needs a Terms entry added alongside it), and
both store listings' required policy-URL fields.

**Effort:** draft is same-day once started; publishing depends entirely on you supplying real
business facts.

---

## Section D — App Store / Play Store submission groundwork

Prep only — see the sequencing decision above for why submission itself stays gated.

**Already resolved (carried over from 07-19, re-verified 23 Jul, no regressions):**
- ✅ Icon at 1024×1024, alpha flattened.
- ✅ ATS/cleartext guard (release build fails loud on a non-`https://` backend URL).
- ✅ Demo credentials rotated and hardened against live-DB writes.
- ✅ In-app privacy/data screen (`Settings → Privacy & data`, `/privacy` public route).
- ✅ No social login anywhere — Apple Guideline 4.8 (Sign in with Apple parity) is moot.

**Newly confirmed still open (verified directly this session, not just carried from memory):**
- ⬜ `eas.json`'s `submit.production` is `{}` — no submission credentials. Needs an App Store
  Connect API key and a Google Play service account JSON, both of which require your active
  developer accounts (see Immediate Action Items above) before they can even be generated.
- ⬜ `PrivacyInfo.xcprivacy` — confirmed missing (searched, zero hits). Apple requires this
  manifest for apps using any "required reason" API; needs adding regardless of what's in it.
- ⬜ Splash screen still a 336×729 poster image in a slot the plugin expects a small logo mark —
  needs a real design asset, not a code fix.
- ⬜ Terms of Service didn't exist as a distinct finding in the 07-19 audit — it does now (Section
  C). Both stores' listing forms ask for it separately from the privacy policy URL.
- ⬜ Build pipeline still contradictory: `PRODUCTION.md` says use "the Emergent publish button,"
  `eas.json` implies direct EAS submission. Needs your decision on which is authoritative before
  Section D can finish — whoever owns the resulting App Store Connect / Play Console records
  needs to be settled once, not discovered mid-submission.
- ⬜ No reviewer test account (Apple/Google review needs a scoped, non-internal login).
- ⬜ Store-listing assets: screenshots, description, age rating, Play Data Safety form (this one
  maps directly to Section C's Privacy Policy content — do Section C first), ads declaration.
- ⬜ Customer portal still has no privacy/deletion screen equivalent (staff Settings only).
- ⬜ Push notifications, offline handling (no NetInfo dependency), deep-linking beyond the now-dead
  OAuth-return scheme — still need an explicit v1 stance (build or explicitly skip) so store copy
  doesn't imply a capability that doesn't exist.

**Effort:** the config/manifest/doc work is small (2–3 days) once Section C content and your
developer-account credentials exist. The dev-account lead time (1–2 weeks) is the real critical
path — this is why it's Immediate Action Item #1, independent of everything else.

---

## What NOT to do

- Don't re-propose Google or Apple Sign-In — both explicitly and permanently rejected.
- Don't lock CORS to a production domain before that domain exists — would break current dev/
  preview access with nothing to point at yet.
- Don't treat "Phase 7 groundwork starts now" as license to submit early — the gate on actual
  submission (Phases 3–6 substantially done + dev accounts active) still holds. Groundwork ≠
  submission.
- Don't publish the Privacy Policy / Terms of Service with placeholders still in them.
- Don't attempt to create the Apple Developer Program or Google Play Console accounts, or click
  "Submit for Review" on your behalf — both require your identity/payment and are your action to
  take, not something to automate around.
- Don't re-run the floor-isolation P0 fixes from `PRODUCTION_READINESS_AUDIT.md` (Customers/
  Quotations/POs/Payments/Followups/Suppliers) — confirmed done; only catalog remains, and that's
  a deliberate deferral, not an oversight.
