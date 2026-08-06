# Kitchen/Furniture notebook verification

Date: 2026-08-06
Commit: pending final verification commit (migration applied to the configured database)

## Automated checks

- Backend unit suite: `904 passed`.
- Notebook backend/migration focused tests: `15 passed`.
- Frontend notebook model: `11 assertions passed`.
- Frontend TypeScript: `npx tsc --noEmit` passed.
- Web production export: `npx expo export --platform web` bundled successfully.
- Backend compile check: routes, services, models, and migration compiled successfully.
- Production migration: `0015_migrate_project_followups_to_notebook` applied; a
  subsequent dry-run reported no pending migrations.
- Customer identity diagnostic: 107 normalized phone keys scanned, with zero
  floor-scoped duplicates; the resulting phone index is unique for non-empty
  normalized values.

## Implemented behavior

- Kitchen Floor and Furniture Floor use the existing `second-floor` and
  `third-floor` IDs with notebook-only navigation entries.
- The feature uses the shared `followups` collection, activity/timeline path,
  permissions, notifications, and floor scoping.
- The prototype `project_followups` route/model path is removed from runtime;
  migration `0015_migrate_project_followups_to_notebook` is idempotent and
  leaves the source collection untouched.
- Follow-up and Quotation Follow-up are two filtered views of one row.
- Mobile-based customer reuse and floor-scoped notebook identity are enforced.
- Lost requires Notes server-side and is disabled in the status controls until
  Notes exists. Won is confirmed and locks Follow-up fields.
- Field edits are autosaved through optimistic `updated_at` patches with
  Saving/Saved/Error/Changed states.
- Search is limited to customer name, mobile, address, architect/interior
  designer, referrer, and notes; quotation fields are excluded.
- Desktop has resizable/sticky notebook structure; tablet/phone use horizontal
  scrolling and a phone-only New Follow-up bottom sheet.
- The grid uses virtualized rendering and cursor pagination.

## Worktree note

The repository contained pre-existing unrelated edits and untracked artifacts
before this milestone. Notebook-specific files are committed and clean; those
unrelated changes were deliberately not staged or altered.
