# Sanitary Bathroom Media & Quotation Stabilization Verification

## Automated evidence

- `cd backend && .venv/bin/pytest tests/unit/test_pdf_generator_media.py -q` — 4 passed.
- `cd backend && .venv/bin/pytest tests/unit -q` — 842 passed, 238 pre-existing deprecation warnings.
- `cd frontend && npm run test:quotation-media` — 5 assertions passed.
- `cd frontend && npx tsc --noEmit` — exit 0.
- `cd frontend && npx eslint 'app/(admin)/_layout.tsx' 'src/components/ProductImage.tsx' 'src/components/quotation/catalog/ProductExplorer.tsx' 'src/components/quotation/helpers/responsive.ts' 'src/components/quotation/layout/BuilderShell.tsx'` — 0 errors, 0 new warnings after cleanup.
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

The full `npm run lint` command now initializes after restoring the missing optional resolver packages, but reports 14 pre-existing errors in unrelated privacy/terms/analytics files and 26 warnings across the repository. The changed-file lint command is clean. The optional-package repair updated `frontend/package-lock.json`; no application dependency or runtime code was added. Live authenticated browser checks against Supabase/MongoDB were not run in this environment, so the requested viewport matrix remains an artifact/static-build verification gap rather than an asserted pass.
