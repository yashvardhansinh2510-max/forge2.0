# Security Hardening + Legal/Policy Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the concrete, unblocked open items from `PRODUCTION_ROADMAP_2026-07-23.md` Sections B (security hardening) and C (legal/policy content) — the two workstreams explicitly agreed to go first because neither depends on the still-open product decisions (catalog floor-isolation, duplicate SKU) or the user's pending Apple/Google developer accounts.

**Architecture:** Six independent tasks, three backend (Python/FastAPI/Mongo) and three frontend (Expo Router/React Native Web). Backend tasks follow this repo's existing versioned-migration convention (`backend/migrations/NNNN_*.py`, tolerant `create_index` pattern) and existing CI structure. Frontend tasks follow the existing Privacy Policy pattern exactly (a shared content component rendered at both a public unauthenticated route and an in-app Settings route) and extend it to a second document (Terms of Service) rather than inventing a new pattern.

**Tech Stack:** FastAPI, Motor (async MongoDB driver), pytest, GitHub Actions, Expo Router, React Native Web, TypeScript.

## Global Constraints

- Migrations are forward-only, must define async `up(db)`, and must be idempotent — see `backend/migrations/runner.py`'s module docstring. Every new migration in this plan follows the exact `_create_index_tolerant`/`_INDEX_CONFLICT_CODE` pattern already duplicated per-file in `0002`/`0003`/`0005`/`0007`/`0009` (this repo's deliberate convention — do not refactor it into a shared helper as part of this plan).
- Backend verification is `pytest tests/unit -v` from `backend/`, matching `.github/workflows/ci.yml`.
- **Frontend has no test runner** (confirmed: no `jest`/`testing-library` in `frontend/package.json`, zero `*.test.tsx` files repo-wide). Frontend task verification is `npx tsc --noEmit` + `npx expo lint -- --max-warnings 200` (exactly what CI runs) plus a live check via the browser preview tool — not automated tests. Do not introduce a new test framework as part of this plan; that's out of scope.
- `[LEGAL_ENTITY_NAME]`, `[REGISTERED_ADDRESS]`, `[CONTACT_EMAIL]`, `[EFFECTIVE_DATE]`, `[RETENTION_PERIOD]`, `[GRIEVANCE_OFFICER_NAME]`, `[GRIEVANCE_OFFICER_CONTACT]`, `[GOVERNING_LAW_JURISDICTION]` are intentional literal placeholder tokens in the policy content tasks (C1/C2) — the user explicitly chose placeholders over supplying real facts today. Do not invent values for these. Neither document is publishable/submission-ready until a human fills them in.
- Live-data check already performed 2026-07-23 against the real `buildcon_house` Atlas database (read-only): 6 customers, zero duplicate emails (case-insensitive). Task B1's migration is safe to write as a normal, unconditional migration — this is not a case requiring a blocking human decision the way the duplicate-SKU issue was.
- The shared backend at `:8010` does **not** auto-reload and is commonly shared with another concurrent session — do not restart it as part of this plan. Migration 0010 (Task B1) applies automatically the next time that process is legitimately restarted; do not force that restart here.

---

### Task B1: `customers.email` unique index migration

**Files:**
- Create: `backend/migrations/0010_add_customers_email_unique_index.py`
- Test: `backend/tests/unit/test_migration_0010.py`

**Interfaces:**
- Produces: `migrations.0010_add_customers_email_unique_index.up(db) -> None` (async), discovered automatically by `migrations/runner.py`'s `_discover()` — no other task depends on this.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_migration_0010.py
"""Migration 0010 must create a unique index on customers.email — the same
index scripts/ensure_indexes.py has always created manually, now given a
versioned migration path (matching 0005/0007's treatment of
categories.slug/brands.slug) so a fresh database gets it without relying on
someone running that script. Re-verified 2026-07-23 against the live
buildcon_house database (read-only aggregate check): 6 customers, zero
duplicate emails case-insensitive, so this applies cleanly today."""
from __future__ import annotations

import asyncio
import importlib

migration = importlib.import_module("migrations.0010_add_customers_email_unique_index")


class _FakeCustomers:
    def __init__(self):
        self.create_index_calls: list[tuple[object, dict]] = []

    async def create_index(self, keys, **kwargs):
        self.create_index_calls.append((keys, kwargs))


class _FakeDb:
    def __init__(self):
        self.customers = _FakeCustomers()


def test_migration_creates_unique_index_on_customers_email():
    fake_db = _FakeDb()
    asyncio.run(migration.up(fake_db))

    assert len(fake_db.customers.create_index_calls) == 1
    keys, kwargs = fake_db.customers.create_index_calls[0]
    assert keys == "email"
    assert kwargs["unique"] is True
    assert kwargs["sparse"] is True
    assert kwargs["name"] == "customers_email_unique"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_migration_0010.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'migrations.0010_add_customers_email_unique_index'`

- [ ] **Step 3: Write the migration**

```python
# backend/migrations/0010_add_customers_email_unique_index.py
"""customers.email had a check-then-insert race with nothing backing it at
the DB layer (BACKEND_AUDIT_2026-07-17.md High #14). scripts/ensure_indexes.py
has created this index manually since 07-17, but "manual" means it only
exists on a database someone remembered to run that script against — a
fresh environment gets nothing. Same treatment as 0005/0007
(categories.slug/brands.slug): move it into the auto-run migration path.
Re-verified 2026-07-23 against the live buildcon_house database: 6
customers, zero duplicate emails (case-insensitive), so a unique index
applies cleanly today."""
from __future__ import annotations

from pymongo.errors import OperationFailure

_INDEX_CONFLICT_CODE = 85


async def _create_index_tolerant(collection, keys, **kwargs) -> None:
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as e:
        if e.code != _INDEX_CONFLICT_CODE:
            raise


async def up(db) -> None:
    await _create_index_tolerant(db.customers, "email", unique=True, sparse=True, name="customers_email_unique")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_migration_0010.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full unit suite to check for regressions**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -v`
Expected: All tests pass (46 passed — 45 pre-existing + this new one)

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/0010_add_customers_email_unique_index.py backend/tests/unit/test_migration_0010.py
git commit -m "fix: add customers.email unique index to the auto-run migration path

scripts/ensure_indexes.py has created this manually since 07-17, but a
fresh environment never gets it unless someone remembers to run that
script by hand. Moves it into migrations/ (same treatment as 0005/0007
for categories.slug/brands.slug) so it applies automatically on every
boot instead. Re-verified against live data first: 6 customers, zero
duplicate emails."
```

---

### Task B2: CI dependency-vulnerability scanning + Dependabot

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `.github/dependabot.yml`

**Interfaces:** None — CI/config only, no code consumed or produced for other tasks.

- [ ] **Step 1: Add a pip-audit step to the backend CI job**

In `.github/workflows/ci.yml`, insert a new step between "Install runtime dependencies" and "Lint (pyflakes)":

```yaml
      - name: Dependency vulnerability scan (pip-audit)
        run: |
          pip install pip-audit
          pip-audit -r requirements-prod.txt
```

- [ ] **Step 2: Add an npm audit step to the frontend CI job**

In `.github/workflows/ci.yml`, insert a new step between "Install dependencies" and "TypeScript check":

```yaml
      - name: Dependency vulnerability scan (npm audit)
        run: npm audit --audit-level=high
```

`--audit-level=high` is deliberate: a moderate-severity npm advisory is already known and deliberately deferred (needs an Expo major-version bump per the 23 Jul commit message) — gating CI on `moderate` would make it permanently red for a known, tracked issue. `high` still catches anything newly introduced at high/critical.

- [ ] **Step 3: Verify both commands pass locally against the current lockfiles**

Run: `cd backend && .venv/bin/pip install pip-audit -q && .venv/bin/pip-audit -r requirements-prod.txt`
Expected: `No known vulnerabilities found` (already confirmed 2026-07-23)

Run: `cd frontend && npm audit --audit-level=high`
Expected: exit code 0 (16 vulnerabilities present, but 2 low + 14 moderate, 0 high/critical — already confirmed 2026-07-23)

- [ ] **Step 4: Add Dependabot config for both ecosystems plus GitHub Actions**

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/backend"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5

  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

- [ ] **Step 5: Validate the workflow YAML parses**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); yaml.safe_load(open('.github/dependabot.yml')); print('valid')"`
Expected: `valid`

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml .github/dependabot.yml
git commit -m "ci: add dependency vulnerability scanning + Dependabot

npm audit / pip-audit were previously run as one-off manual passes (see
the 23 Jul hardening commit) with no standing process to catch new
advisories. CI now gates on pip-audit (any severity, backend prod deps
currently clean) and npm audit at --audit-level=high (frontend
currently has 0 high/critical; the 1 known moderate advisory is
deliberately deferred pending an Expo major-version bump, so it's not
gated on). Dependabot opens weekly PRs for both ecosystems plus GitHub
Actions versions."
```

---

### Task B3: Baseline security response headers middleware

**Files:**
- Create: `backend/middleware.py`
- Modify: `backend/server.py:1-127` (add import + `app.add_middleware` call before the existing `CORSMiddleware` registration)
- Test: `backend/tests/unit/test_security_headers_middleware.py`

**Interfaces:**
- Produces: `middleware.SecurityHeadersMiddleware` (a `starlette.middleware.base.BaseHTTPMiddleware` subclass) — consumed only by `server.py`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_security_headers_middleware.py
"""SecurityHeadersMiddleware adds baseline defense-in-depth response headers
to every request, complementing the CORS reasoning already documented in
server.py rather than replacing any of it. Tested against a minimal
isolated app rather than the full server, which requires live Mongo/
Supabase at startup (see tests/INTEGRATION_TESTING_STRATEGY.md) — this is
pure ASGI-layer behavior, independent of server.py's startup event."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware import SecurityHeadersMiddleware

_app = FastAPI()
_app.add_middleware(SecurityHeadersMiddleware)


@_app.get("/ping")
def _ping():
    return {"ok": True}


client = TestClient(_app)


def test_static_headers_present_on_every_response():
    response = client.get("/ping")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"


def test_hsts_absent_over_http():
    response = client.get("/ping")
    assert "strict-transport-security" not in response.headers


def test_hsts_present_when_request_scheme_is_https():
    https_client = TestClient(_app, base_url="https://testserver")
    response = https_client.get("/ping")
    assert response.headers["strict-transport-security"] == "max-age=63072000; includeSubDomains"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_security_headers_middleware.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'middleware'`

- [ ] **Step 3: Write the middleware**

```python
# backend/middleware.py
"""Baseline security response headers, added to every response. Complements
CORSMiddleware in server.py (credential-less wildcard CORS, documented
there) rather than replacing any of it — these are defense-in-depth
headers browsers apply regardless of API-vs-page distinction, cheap to
add, no behavior change for any existing client."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in _STATIC_HEADERS.items():
            response.headers.setdefault(header, value)
        # HSTS only makes sense once a request actually arrived over HTTPS —
        # forcing it in local/http dev would be actively wrong, not just inert.
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_security_headers_middleware.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Wire the middleware into `server.py`**

In `backend/server.py`, add the import alongside the existing `starlette` import (near line 9):

```python
from starlette.middleware.cors import CORSMiddleware

from middleware import SecurityHeadersMiddleware
```

Then, immediately **before** the existing `app.add_middleware(CORSMiddleware, ...)` block (around line 121), add:

```python
# Security headers (defense-in-depth, no behavior change for existing
# clients) — registered before CORSMiddleware so CORS stays the outermost
# middleware, unchanged from its current behavior.
app.add_middleware(SecurityHeadersMiddleware)
```

- [ ] **Step 6: Run the full unit suite to check for regressions**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -v`
Expected: All tests pass (49 passed — 45 pre-existing + 1 from Task B1 + 3 from this task)

- [ ] **Step 7: Commit**

```bash
git add backend/middleware.py backend/server.py backend/tests/unit/test_security_headers_middleware.py
git commit -m "feat: add baseline security response headers middleware

X-Content-Type-Options, X-Frame-Options, Referrer-Policy,
Permissions-Policy on every response; Strict-Transport-Security added
only when a request actually arrives over https (forcing it in http
local dev would be wrong, not just inert). Defense-in-depth only — no
behavior change for any existing client, complements rather than
replaces the CORS reasoning already documented in server.py."
```

---

### Task C1: Shared legal-doc layout + Privacy Policy content upgrade

**Files:**
- Create: `frontend/src/components/LegalDocContent.tsx`
- Modify: `frontend/src/components/PrivacyPolicyContent.tsx`

**Interfaces:**
- Produces: `LegalDocContent.Section({ title: string, children: React.ReactNode })` and `LegalDocContent.P({ children: React.ReactNode })` — consumed by `PrivacyPolicyContent.tsx` (this task) and `TermsOfServiceContent.tsx` (Task C2).

- [ ] **Step 1: Extract the shared `Section`/`P` layout atoms**

```tsx
// frontend/src/components/LegalDocContent.tsx
// Shared layout atoms for legal/policy documents (Privacy Policy, Terms of
// Service) — kept separate so both documents render with identical
// typography without duplicating the same two components twice.
import { Text, View } from "react-native";

import { color, font } from "@/src/design/tokens";

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={{ gap: 8 }}>
      <Text style={{ fontFamily: font.medium, fontSize: 17, color: color.ink }}>{title}</Text>
      {children}
    </View>
  );
}

export function P({ children }: { children: React.ReactNode }) {
  return (
    <Text style={{ fontFamily: font.regular, fontSize: 14, lineHeight: 21, color: color.inkSoft }}>
      {children}
    </Text>
  );
}
```

- [ ] **Step 2: Rewrite `PrivacyPolicyContent.tsx` to import the shared atoms and add the missing legal-register sections**

```tsx
// frontend/src/components/PrivacyPolicyContent.tsx
// Privacy & Data policy copy — single source of truth.
// Rendered both in-app (app/(admin)/settings-privacy.tsx, behind staff auth)
// and on the public, unauthenticated /privacy route (app/privacy.tsx) that
// App Store Connect / Google Play Console require a hosted URL for. Keep
// both call sites importing this component rather than duplicating copy —
// the two are required to say the same thing.
//
// [LEGAL_ENTITY_NAME] / [REGISTERED_ADDRESS] / [CONTACT_EMAIL] /
// [EFFECTIVE_DATE] / [RETENTION_PERIOD] / [GRIEVANCE_OFFICER_NAME] /
// [GRIEVANCE_OFFICER_CONTACT] are placeholders — fill in with real business
// facts before this page is used for an App Store / Play Console
// submission or otherwise published.
import { View } from "react-native";

import { brand, space } from "@/src/design/tokens";
import { P, Section } from "@/src/components/LegalDocContent";

export function PrivacyPolicyContent() {
  return (
    <View style={{ gap: space.x6 }}>
      <Section title="What this covers">
        <P>
          {brand.name} is a workspace for staff to manage quotations, orders, and payments, and a
          portal customers use to view their own orders. This page describes what data the app
          collects, where it is stored, and how to exercise your rights over it.
        </P>
        <P>Effective date: [EFFECTIVE_DATE].</P>
      </Section>

      <Section title="Who operates this app">
        <P>
          {brand.name} is operated by [LEGAL_ENTITY_NAME], [REGISTERED_ADDRESS]. For any privacy
          question or request, contact [CONTACT_EMAIL].
        </P>
      </Section>

      <Section title="Data we collect">
        <P>Staff accounts: name, email, phone (optional), a hashed password, and role/floor
          assignment.</P>
        <P>Customer records (entered by staff, not by the customer): name, company, email, phone,
          address, city, and tax ID (GSTIN) where applicable. If customer portal access is enabled,
          the customer also gets a hashed password.</P>
        <P>Business records: quotations, purchase orders, payments, and an audit trail of changes
          made to them (who changed what, and when) — this is core to how the app functions and is
          retained as a business record, not discretionary tracking.</P>
      </Section>

      <Section title="Third-party processors">
        <P>Database records are hosted on MongoDB Atlas. Product photos, company logos, and
          document attachments are stored on Supabase. Both are third-party infrastructure
          providers processing data on our behalf, not independent data users.</P>
        <P>If enabled by your administrator, crash reports are sent to Sentry and product usage
          analytics to PostHog — both are off by default and only active if the relevant service
          credentials have been configured for this deployment.</P>
      </Section>

      <Section title="Data retention">
        <P>
          Staff and customer account records are retained for as long as the account is active.
          Quotations, purchase orders, and payment records are retained as business records for
          [RETENTION_PERIOD] after the underlying transaction completes, or as required by
          applicable tax/accounting law, whichever is longer — this applies even after the
          associated account is deactivated.
        </P>
      </Section>

      <Section title="Your rights">
        <P>
          You can request a copy of the personal data this app holds about you, ask that
          inaccurate data be corrected, or request deletion of your account (see "Requesting
          deletion" below). Some records may be retained after a deletion request where retention
          is required for financial record-keeping or to resolve an open business transaction.
        </P>
      </Section>

      <Section title="Requesting deletion">
        <P>
          Staff and customer accounts in this app are created by an administrator, not
          self-registered — to request that your account or personal data be deleted, contact the
          owner or manager who set up your access, or write to [CONTACT_EMAIL]. They can
          deactivate or remove the record; historical quotation/payment records tied to completed
          business transactions may be retained as required for financial record-keeping even
          after an account is deactivated.
        </P>
      </Section>

      <Section title="Grievance Officer">
        <P>
          If required in your jurisdiction: [GRIEVANCE_OFFICER_NAME] is the designated Grievance
          Officer for privacy-related complaints, reachable at [GRIEVANCE_OFFICER_CONTACT]. Remove
          this section if not applicable to where {brand.name} operates.
        </P>
      </Section>

      <Section title="Changes to this policy">
        <P>
          If this policy changes, the updated version will be posted at this same location with a
          new effective date above. Continued use of the app after a change takes effect means you
          accept the updated policy.
        </P>
      </Section>
    </View>
  );
}
```

- [ ] **Step 3: Type-check and lint**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

Run: `cd frontend && npx expo lint -- --max-warnings 200`
Expected: no new warnings/errors

- [ ] **Step 4: Live-verify both render call sites**

Start the frontend dev server (`.claude/launch.json`'s `"frontend"` config, per project convention — check `curl 127.0.0.1:8010/api/health` first for the backend, it's commonly already running). In the browser preview: navigate to `/privacy` (public, no login needed) and confirm all 9 sections render with the new placeholder tokens visible as literal bracketed text (not blank/crashed). Then sign in as staff and navigate to Settings → Privacy & data, confirm identical content.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/LegalDocContent.tsx frontend/src/components/PrivacyPolicyContent.tsx
git commit -m "feat: expand Privacy Policy to submission-ready content with placeholders

Existing copy was accurate but explicitly self-disclaimed as 'not a
substitute for a formally published privacy policy' — adds the missing
legal-register sections (operator identity, retention, rights,
Grievance Officer, changes-to-policy) with [PLACEHOLDER] tokens for the
real business facts the user chose to supply later. Extracts the
Section/P layout atoms into LegalDocContent.tsx so Terms of Service
(next commit) can reuse them without duplicating the same two
components."
```

---

### Task C2: Terms of Service — content, public route, in-app route, navigation

**Files:**
- Create: `frontend/src/components/TermsOfServiceContent.tsx`
- Create: `frontend/app/terms.tsx`
- Create: `frontend/app/(admin)/settings-terms.tsx`
- Modify: `frontend/app/_layout.tsx:38-41`
- Modify: `frontend/app/(admin)/settings.tsx:91-100`

**Interfaces:**
- Consumes: `LegalDocContent.Section`, `LegalDocContent.P` (from Task C1).
- Produces: `TermsOfServiceContent.TermsOfServiceContent()` component, consumed by `app/terms.tsx` and `app/(admin)/settings-terms.tsx` (both this task) and by Task C3's login/portal links (route paths `/terms` only, not the component directly).

- [ ] **Step 1: Write the Terms of Service content component**

```tsx
// frontend/src/components/TermsOfServiceContent.tsx
// Terms of Service copy — single source of truth.
// Rendered both in-app (app/(admin)/settings-terms.tsx, behind staff auth)
// and on the public, unauthenticated /terms route (app/terms.tsx) that
// App Store Connect / Google Play Console require a hosted URL for,
// mirroring how app/privacy.tsx and PrivacyPolicyContent.tsx are split.
//
// [LEGAL_ENTITY_NAME] / [REGISTERED_ADDRESS] / [CONTACT_EMAIL] /
// [EFFECTIVE_DATE] / [GOVERNING_LAW_JURISDICTION] are placeholders — fill
// in with real business facts before this page is used for an App Store /
// Play Console submission or otherwise published.
import { View } from "react-native";

import { brand, space } from "@/src/design/tokens";
import { P, Section } from "@/src/components/LegalDocContent";

export function TermsOfServiceContent() {
  return (
    <View style={{ gap: space.x6 }}>
      <Section title="Agreement">
        <P>
          These Terms of Service govern access to and use of {brand.name}, operated by
          [LEGAL_ENTITY_NAME], [REGISTERED_ADDRESS] ("we", "us"). By signing in, you agree to
          these terms. Effective date: [EFFECTIVE_DATE].
        </P>
      </Section>

      <Section title="Who this applies to">
        <P>
          Staff accounts are created and assigned by an administrator, scoped to a role and one or
          more floors/departments — you may not use a staff account outside the access your
          administrator has granted. Customer accounts are created by staff on your behalf and
          give you read-only access to your own quotations, orders, and payment status — you may
          not use a customer account to access another customer's records.
        </P>
      </Section>

      <Section title="Account responsibilities">
        <P>
          You're responsible for keeping your login credentials confidential and for all activity
          under your account. Tell your administrator immediately if you suspect unauthorized
          access. Temporary passwords issued by an administrator must be changed on first sign-in
          and expire if unused.
        </P>
      </Section>

      <Section title="Acceptable use">
        <P>
          Use {brand.name} only for its intended purpose: managing and viewing quotations,
          purchase orders, payments, and related business records. Don't attempt to access data
          outside your assigned role/floor scope, interfere with the app's operation, or use it to
          store or transmit unlawful content.
        </P>
      </Section>

      <Section title="Content and ownership">
        <P>
          Quotations, purchase orders, and other documents you create or view through the app
          remain the business records of {brand.name} and the customer they relate to. The app's
          software, design, and branding are the property of [LEGAL_ENTITY_NAME] and may not be
          copied or redistributed outside normal use of the app.
        </P>
      </Section>

      <Section title="Disclaimers and liability">
        <P>
          The app is provided "as is." While we take reasonable care to keep quotation, order, and
          payment data accurate, you should confirm pricing and order details through your normal
          business process before relying on them for a transaction. To the extent permitted by
          law, [LEGAL_ENTITY_NAME] is not liable for indirect or consequential loss arising from
          use of the app.
        </P>
      </Section>

      <Section title="Termination">
        <P>
          An administrator may deactivate any staff or customer account at any time, including on
          request. We may suspend access to the app for maintenance, security, or if these terms
          are violated.
        </P>
      </Section>

      <Section title="Governing law">
        <P>
          These terms are governed by the laws of [GOVERNING_LAW_JURISDICTION], without regard to
          conflict-of-law principles.
        </P>
      </Section>

      <Section title="Changes to these terms">
        <P>
          If these terms change, the updated version will be posted at this same location with a
          new effective date above. Continued use of the app after a change takes effect means you
          accept the updated terms.
        </P>
      </Section>

      <Section title="Contact">
        <P>Questions about these terms: [CONTACT_EMAIL].</P>
      </Section>
    </View>
  );
}
```

- [ ] **Step 2: Add the public `/terms` route (mirrors `app/privacy.tsx` exactly)**

```tsx
// frontend/app/terms.tsx
// Public, unauthenticated Terms of Service — the hosted-URL half of the
// store-submission requirement, mirroring app/privacy.tsx exactly.
// App Store Connect / Google Play Console both require a stable URL to this
// content in their submission forms; app/(admin)/settings-terms.tsx is the
// in-app half, behind staff auth. Both render TermsOfServiceContent so the
// copy can't drift.
//
// Lives outside every route group ((auth)/(admin)/(customer)) on purpose —
// AuthGate (app/_layout.tsx) redirects any unauthenticated visitor to
// /(auth)/login by default, with an explicit carve-out for this route's
// top-level "terms" segment so it stays reachable without signing in.
import { useRouter } from "expo-router";
import { Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { BuildConLogo } from "@/src/design/BrandLogo";
import { Txt } from "@/src/design/components";
import { useBp } from "@/src/design/responsive";
import { color, font, space } from "@/src/design/tokens";
import { TermsOfServiceContent } from "@/src/components/TermsOfServiceContent";

export default function PublicTermsOfService() {
  const router = useRouter();
  const { isPhone, gutter } = useBp();
  const insets = useSafeAreaInsets();

  return (
    <View style={{ flex: 1, backgroundColor: color.canvas }}>
      <ScrollView
        contentContainerStyle={{
          paddingHorizontal: gutter,
          paddingTop: Math.max(24, insets.top + 16),
          paddingBottom: Math.max(32, insets.bottom + 24),
        }}
        showsVerticalScrollIndicator={false}
      >
        <View style={{ width: "100%", maxWidth: 640, alignSelf: "center", gap: space.x6 }}>
          <View style={{ gap: 8 }}>
            <BuildConLogo height={isPhone ? 28 : 32} />
            <Txt v="display" style={isPhone ? { fontSize: 26, lineHeight: 32 } : { fontSize: 30, lineHeight: 38 }}>
              Terms of Service
            </Txt>
            <Txt v="bodyMid">The terms that govern using this app.</Txt>
          </View>

          <TermsOfServiceContent />

          <Pressable onPress={() => router.push("/(auth)/login")} hitSlop={8}>
            <Text style={{ fontFamily: font.medium, fontSize: 13, color: color.brassDeep }}>← Back to sign in</Text>
          </Pressable>
        </View>
      </ScrollView>
    </View>
  );
}
```

- [ ] **Step 3: Add the in-app Settings route (mirrors `app/(admin)/settings-privacy.tsx` exactly)**

```tsx
// frontend/app/(admin)/settings-terms.tsx
// BuildCon House · Terms of Service
// In-app half of the Terms of Service requirement; app/terms.tsx is the
// public, unauthenticated hosted-URL half App Store Connect / Google Play
// Console require in their submission forms. Both render
// TermsOfServiceContent so the copy can't drift between them.
import { AdminPage } from "@/src/components/AdminPage";
import { TermsOfServiceContent } from "@/src/components/TermsOfServiceContent";

export default function SettingsTerms() {
  return (
    <AdminPage title="Terms of Service" subtitle="The terms that govern using this app">
      <TermsOfServiceContent />
    </AdminPage>
  );
}
```

- [ ] **Step 4: Add the AuthGate carve-out for the new public route**

In `frontend/app/_layout.tsx`, find:

```tsx
    // Public route, reachable with or without a session — App Store Connect /
    // Google Play Console both require a hosted privacy-policy URL a
    // reviewer (or anyone) can open with no account. See app/privacy.tsx.
    if (segments[0] === "privacy") return;
```

Replace with:

```tsx
    // Public routes, reachable with or without a session — App Store
    // Connect / Google Play Console both require hosted privacy-policy and
    // terms-of-service URLs a reviewer (or anyone) can open with no
    // account. See app/privacy.tsx and app/terms.tsx.
    if (segments[0] === "privacy" || segments[0] === "terms") return;
```

- [ ] **Step 5: Add the Settings navigation entry**

In `frontend/app/(admin)/settings.tsx`, find the `workspaceRows` array entry:

```tsx
    { icon: "file-text", label: "Privacy & data", hint: "What we collect, deletion requests", href: "/(admin)/settings-privacy", testId: "settings-nav-privacy" },
  ];
```

Replace with:

```tsx
    { icon: "file-text", label: "Privacy & data", hint: "What we collect, deletion requests", href: "/(admin)/settings-privacy", testId: "settings-nav-privacy" },
    { icon: "file-text", label: "Terms of service", hint: "Usage terms & account terms", href: "/(admin)/settings-terms", testId: "settings-nav-terms" },
  ];
```

- [ ] **Step 6: Type-check and lint**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

Run: `cd frontend && npx expo lint -- --max-warnings 200`
Expected: no new warnings/errors

- [ ] **Step 7: Live-verify all three surfaces**

In the browser preview: (a) navigate directly to `/terms` while signed out — confirm it renders without redirecting to login; (b) sign in as staff, go to Settings, confirm a new "Terms of service" row appears below "Privacy & data" and navigates to the same content in-app; (c) confirm `/privacy` still works unchanged (regression check on the AuthGate edit).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/TermsOfServiceContent.tsx frontend/app/terms.tsx "frontend/app/(admin)/settings-terms.tsx" frontend/app/_layout.tsx "frontend/app/(admin)/settings.tsx"
git commit -m "feat: add Terms of Service (public route, in-app route, nav entry)

Repo previously had zero Terms of Service anywhere (confirmed by
search) — both App Store Connect and Play Console ask for one
separately from the privacy policy URL at submission time. Mirrors the
existing Privacy Policy split exactly: TermsOfServiceContent.tsx is the
single source of truth, rendered at the public unauthenticated /terms
route (App Store/Play Console's hosted-URL requirement) and in-app
under Settings, behind staff auth. [PLACEHOLDER] tokens for legal
facts, same as the Privacy Policy update."
```

---

### Task C3: Link Privacy + Terms from login and the customer portal

**Files:**
- Modify: `frontend/app/(auth)/login.tsx:1-18` (imports), `:24-38` (hooks), `:108-124` (`form` JSX)
- Modify: `frontend/app/(customer)/home.tsx:1-17` (imports already include `useRouter`/`router`), `:138-150` (footer JSX)

**Interfaces:** None — leaf UI changes, nothing else depends on these.

- [ ] **Step 1: Add router + footer links to the login screen**

In `frontend/app/(auth)/login.tsx`, add `useRouter` to the existing `expo-router`... there is no existing `expo-router` import in this file (verified: only `expo-image`, `expo-linear-gradient`, `react`, `react-native`, `react-native-safe-area-context`, and local `@/src/*` imports). Add a new import line after the `react-native-safe-area-context` import:

```tsx
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
```

In the component body, add the router hook alongside the existing ones (find `const insets = useSafeAreaInsets();` and add right after it):

```tsx
  const insets = useSafeAreaInsets();
  const router = useRouter();
```

In the `form` JSX, find the closing of the demo-account/customer-portal-toggle row:

```tsx
          <Text style={{ fontFamily: font.medium, fontSize: 13, color: color.brassDeep }}>
            {mode === "staff" ? "Customer portal →" : "← Staff sign-in"}
          </Text>
        </Pressable>
      </View>
    </View>
  );
```

Replace with (adds a new centered footer row before `form`'s closing `</View>`):

```tsx
          <Text style={{ fontFamily: font.medium, fontSize: 13, color: color.brassDeep }}>
            {mode === "staff" ? "Customer portal →" : "← Staff sign-in"}
          </Text>
        </Pressable>
      </View>

      <View style={{ flexDirection: "row", justifyContent: "center", gap: space.x4 }}>
        <Pressable testID="login-privacy-link" onPress={() => router.push("/privacy")} hitSlop={8}>
          <Text style={{ fontFamily: font.regular, fontSize: 12, color: color.inkSoft }}>Privacy</Text>
        </Pressable>
        <Pressable testID="login-terms-link" onPress={() => router.push("/terms")} hitSlop={8}>
          <Text style={{ fontFamily: font.regular, fontSize: 12, color: color.inkSoft }}>Terms</Text>
        </Pressable>
      </View>
    </View>
  );
```

- [ ] **Step 2: Add footer links to the customer portal home screen**

In `frontend/app/(customer)/home.tsx`, find the end of the "Contact support floating card" and the closing of the content `View`:

```tsx
            <Pressable testID="portal-support-btn" onPress={() => Linking.openURL("mailto:support@forge.app")} style={styles.supportBtnPrimary}>
              <Feather name="message-circle" size={14} color={colors.brand} />
              <Text style={{ color: colors.brand, fontSize: 13, fontWeight: "700" }}>Contact</Text>
            </Pressable>
          </Card>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
```

Replace with (adds a centered footer row after the support card, still inside the content `View`):

```tsx
            <Pressable testID="portal-support-btn" onPress={() => Linking.openURL("mailto:support@forge.app")} style={styles.supportBtnPrimary}>
              <Feather name="message-circle" size={14} color={colors.brand} />
              <Text style={{ color: colors.brand, fontSize: 13, fontWeight: "700" }}>Contact</Text>
            </Pressable>
          </Card>

          <View style={{ flexDirection: "row", justifyContent: "center", gap: spacing.lg, paddingTop: spacing.sm }}>
            <Pressable testID="portal-privacy-link" onPress={() => router.push("/privacy")} hitSlop={8}>
              <Text style={{ fontSize: 12, color: colors.onSurfaceMuted }}>Privacy</Text>
            </Pressable>
            <Pressable testID="portal-terms-link" onPress={() => router.push("/terms")} hitSlop={8}>
              <Text style={{ fontSize: 12, color: colors.onSurfaceMuted }}>Terms</Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
```

(`router` is already defined in this file via `const router = useRouter();` at the top of `CustomerDashboard` — no new hook needed here, unlike login.tsx.)

- [ ] **Step 3: Type-check and lint**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

Run: `cd frontend && npx expo lint -- --max-warnings 200`
Expected: no new warnings/errors

- [ ] **Step 4: Live-verify both screens**

In the browser preview: (a) load `/(auth)/login`, confirm a "Privacy · Terms" row appears below the staff/customer-portal toggle on both phone width (375px) and desktop width, and both links navigate correctly and back-navigate via each page's "← Back to sign in" link; (b) sign in as a customer, confirm the same row appears at the bottom of the portal home screen below "Need help?", and both links navigate correctly.

- [ ] **Step 5: Commit**

```bash
git add "frontend/app/(auth)/login.tsx" "frontend/app/(customer)/home.tsx"
git commit -m "feat: link Privacy Policy + Terms of Service from login and customer portal

Closes the last two 'across all viewpoints' surfaces that had no link
to either document at all — login (both staff and customer entry
points share this screen) and the customer portal, which previously
had no privacy/deletion link equivalent to the staff Settings entry."
```

---

## Self-Review Notes

- **Spec coverage**: All of Section B's concretely-actionable items (customers.email index, dependency scanning, security headers) and all of Section C (Privacy Policy content, Terms of Service, cross-linking) are covered. Section B's remaining items (CORS domain lock, multi-worker cache incoherence, duplicate-SKU index) are correctly *not* in this plan — the roadmap itself defers CORS until a prod domain exists and flags the other two as needing a human product decision, not implementation.
- **Placeholder scan**: The only bracketed `[TOKENS]` are intentional literal content inside the policy text (Global Constraints explains why) — no `TBD`/`TODO` in any step or file path.
- **Type consistency**: `Section`/`P` signatures match between their definition (Task C1, Step 1) and both consumers (`PrivacyPolicyContent.tsx` Task C1 Step 2, `TermsOfServiceContent.tsx` Task C2 Step 1). Route paths (`/privacy`, `/terms`) match between the AuthGate carve-out (Task C2 Step 4), the settings nav `href` (Task C2 Step 5), and the login/portal links (Task C3).
