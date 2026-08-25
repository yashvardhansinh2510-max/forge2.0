# Sanitary Bathroom Media & Quotation Stabilization Verification

## Automated evidence

- `cd backend && .venv/bin/pytest tests/unit/test_pdf_generator_media.py -q` — 4 passed.
- `cd backend && .venv/bin/pytest tests/unit/test_catalog_tiles_image_dedup_guard.py tests/unit/test_pdf_generator_media.py -q` — 8 passed after the family-identity media contract change.
- `cd backend && .venv/bin/pytest tests/unit -q` — 843 passed, 238 pre-existing deprecation warnings.
- `cd frontend && npm run test:quotation-media` — 7 assertions passed, including family-safe quality ordering.
- `cd frontend && npx tsc --noEmit` — exit 0.
- `cd frontend && npm run lint` — exit 0; 0 errors and 13 repository warnings, none from the stabilization implementation.
- `cd frontend && npx eslint 'app/(admin)/_layout.tsx' 'src/components/ProductImage.tsx' 'src/components/quotation/catalog/ProductExplorer.tsx' 'src/components/quotation/helpers/responsive.ts' 'src/components/quotation/layout/BuilderShell.tsx'` — 0 errors, 0 new warnings after cleanup.
- `cd frontend && EXPO_PUBLIC_BACKEND_URL=https://example.invalid npx expo export --clear --platform web --output-dir /tmp/forge2-web-stabilization-family-safe` — exit 0; Metro bundled 2,079 modules.
- Temporary isolated Playwright audit against a production web export — 8 viewport sizes (1280, 1440, 1920, 768, 1024, 375, 390, 430); public login route reached at every size with 0 console errors and `scrollWidth === clientWidth`.
- Live local-stack Playwright audit against MongoDB/Supabase-backed API — fresh login plus `/quotations/new` at all 8 viewport sizes; direct links selected `The Sanitary Bathroom`, desktop catalog rendered real products, and every viewport had `scrollWidth === clientWidth` after the mobile topbar fix.
- Live interaction audit — 48 product cards rendered at 1920px in a two-column grid; sidebar and brand rail collapse state survived reload; no non-library console errors.
- Live media metrics — cards used `object-fit: scale-down`; high-resolution sources filled the normalized frame, while 165–188px `poor` sources remained centered at native size instead of being upscaled.
- Live media metadata audit — SKU `109.791.00.1` exposed a 103×162 `poor` primary Omega image plus a 365×547 `acceptable` Sigma-family image attached to the same record; the renderer correctly retained the matching Omega image and does not substitute a higher-quality mismatched family image.
- Live builder media audit — searching SKU `109.791.00.1` at 1920px rendered the Omega Supabase URL at native 103×162 with `object-fit: scale-down`; no console errors were observed.
- Fresh single-context responsive matrix — `/quotations/new` at 1280, 1440, 1920, 768, 1024, 375, 390, and 430px had exact `scrollWidth === clientWidth`; desktop routes showed Sanitary Bathroom, compact phone layouts kept the floor label hidden by design, and no console errors were observed.
- Live quotation artifact — added one real sanitary product through the builder, captured the editor, generated `/tmp/forge-quotation-live.pdf`, rendered both PDF pages with `pdftoppm`, and deleted the temporary quotation after inspection; the product image remained upright, centered, and aspect-preserving.
- `git diff --check` — exit 0.

## PDF artifact evidence

Generated `/tmp/sanitary-stabilization.pdf` through `build_quotation_pdf` with a portrait 60×120 source and rendered page 2 using `pdftoppm` to `/tmp/sanitary-stabilization-render/page-2.png`.

Visual inspection confirmed the portrait source remains upright, centered, and aspect-preserving in the product-image cell. `pdfinfo` reported A4 size and 2 pages.

## Root-cause checks

- No product-image path still calls `_landscape_bytes()`.
- `ProductImage` defaults to `scale-down` with equal design-system inset; explicit `contain`/`cover` remain available to intentional callers.
- Candidate ordering prefers matching `family_key`, then existing quality/dimensions, while retaining primary preference for tied candidates.
- Quotation grid policy returns at most two columns and is driven by measured explorer width.
- Desktop sidebar and quotation brand rail store separate collapse preferences.
- Direct floor-gated quotation links update the shared floor-selection store, keeping the admin shell and request scope on Sanitary Bathroom.
- Low-resolution source assets are not fabricated larger by the shared product renderer.

## Verification limitation

The full `npm run lint` command now initializes after restoring the missing optional resolver packages and exits with no errors; its 13 remaining warnings are outside the stabilization implementation. The optional-package repair updated `frontend/package-lock.json`; no application dependency or runtime code was added. The live dev browser emits one known React 19 compatibility warning from `react-native-web`'s `TouchableWithoutFeedback` implementation (`element.ref`); production exports do not emit it. The authenticated editor/PDF artifact check confirms matching media orientation, aspect ratio, centering, and padding policy; the page composition is necessarily different because the PDF is generated by the separate ReportLab document renderer.
