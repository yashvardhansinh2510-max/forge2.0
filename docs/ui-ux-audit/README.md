# BuildCon House UI/UX Audit

Date: 2026-08-19  
Scope: `frontend/` Expo Router app (read-only review)  
Baseline: implemented product and WCAG 2.2 AA. No Figma, approved screenshots, or other design source was found.

## How this audit was performed

- Repository discovery: routes, shell, responsive tokens, shared components, and UI state handling.
- Static UI/accessibility review of shared primitives and critical flows.
- Existing checks: `yarn tsc --noEmit`, quotation-media, quotation-contract, notebook, and web-budget checks passed. `npm run lint` had 0 errors and 1 warning.
- No live backend was started, production data/credentials were not used, and no authenticated browser session was available.

## Artifacts

- [summary.md](summary.md) — release view and priorities.
- [coverage-matrix.md](coverage-matrix.md) — route, viewport, and state coverage.
- [findings.md](findings.md) — complete deduplicated register.
- [ticket-backlog.md](ticket-backlog.md) — ticket-ready S1/S2 work.
- [remediation-plan.md](remediation-plan.md) — non-breaking implementation sequence.
- [verification-log.md](verification-log.md) — commands, evidence, and limitations.

## Reproduction baseline

Run checks from `frontend/`. For runtime verification, use a non-production backend, a representative staff account, and seeded records; test every cited route at the viewport/state named in its finding. Do not treat this audit as accessibility conformance certification: screen-reader, keyboard, actual-device, visual, zoom, and network checks requiring an authenticated app session remain unverified.

## Source integrity

Only this audit folder was created. No application source, manifests, lockfiles, configuration, migrations, environment files, or existing workspace changes were modified.
