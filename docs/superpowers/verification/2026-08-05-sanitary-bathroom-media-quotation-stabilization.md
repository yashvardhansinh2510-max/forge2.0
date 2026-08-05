# Sanitary Bathroom Media & Quotation Stabilization Verification

## Automated evidence

- `cd backend && .venv/bin/pytest tests/unit/test_pdf_generator_media.py -q` — 4 passed.
- `cd backend && .venv/bin/pytest tests/unit -q` — 842 passed, 238 pre-existing deprecation warnings.
- `cd frontend && npm run test:quotation-media` — 5 assertions passed.
- `cd frontend && npx tsc --noEmit` — exit 0.
- `cd frontend && npx expo export --platform web --output-dir /tmp/forge2-web-stabilization` — exit 0; Metro bundled 2,004 modules.
- `git diff --check` — exit 0.

## PDF artifact evidence

Generated `/tmp/sanitary-stabilization.pdf` through `build_quotation_pdf` with a portrait 60×120 source and rendered page 2 using `pdftoppm` to `/tmp/sanitary-stabilization-render/page-2.png`.

Visual inspection confirmed the portrait source remains upright, centered, and aspect-preserving in the product-image cell. `pdfinfo` reported A4 size and 2 pages.

## Root-cause checks

- No product-image path still calls `_landscape_bytes()`.
- `ProductImage` defaults to `contain` with equal design-system inset; explicit `cover` remains available only to intentional crop callers.
- Quotation grid policy returns at most two columns and is driven by measured explorer width.
- Desktop sidebar and quotation brand rail store separate collapse preferences.

## Verification limitation

The full `npm run lint` command could not initialize because the existing `frontend/node_modules` installation has no `unrs-resolver` native binding; ESLint aborts before reporting source diagnostics. This was independently reproduced with `npm ls unrs-resolver` showing an empty tree. The web export and TypeScript checks still complete successfully. Live authenticated browser checks against Supabase/MongoDB were not run in this environment, so the requested viewport matrix remains an artifact/static-build verification gap rather than an asserted pass.
