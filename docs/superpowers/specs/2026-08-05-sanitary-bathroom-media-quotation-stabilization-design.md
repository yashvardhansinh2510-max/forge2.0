# Sanitary Bathroom Media & Quotation Stabilization Design

## Goal

Make the Sanitary Bathroom quotation workflow production-ready by normalizing product-media presentation in the existing shared renderer, enlarging responsive quotation imagery, adding a persistent desktop sidebar collapse, and making PDF image placement preserve the editor's orientation and aspect ratio.

## Scope and constraints

- Applies to the existing first-floor Sanitary Bathroom quotation flow and its shared product-media consumers: catalog, quotation builder, customer preview, and quotation PDF.
- Reuses `Product`, `product_media`, Supabase Storage, MongoDB, the existing media service, cache, quotation builder, and ReportLab renderer.
- Does not create a new image collection, alter historical quotations, manually edit catalog assets, or redesign the quotation model.
- Phone navigation remains the existing bottom-bar experience; desktop-only sidebar collapse is added to the admin shell.
- The renderer must preserve source aspect ratio, never stretch or crop important product content, center the image, and apply identical internal padding.

## Root causes confirmed

1. `frontend/src/components/ProductImage.tsx` defaults to `contentFit="cover"`, so different source aspect ratios are cropped differently and the visual scale changes by product.
2. `frontend/src/components/quotation/helpers/responsive.ts` derives three product columns from window width, while `BuilderShell` already switches on measured container width. The two contracts disagree at tablet and desktop shell widths.
3. `backend/pdf_generator.py` calls `_landscape_bytes()` and rotates every portrait source image by 90 degrees before ReportLab placement. This is the direct cause of rotated/flipped portrait product images in generated PDFs.
4. PDF placement is proportional but uses a separate fixed image-cell contract from the editor, so visual proportions and padding do not match even when the bytes are correct.
5. The admin desktop sidebar is fixed at the design-token width and has no persisted collapsed state; the quotation's internal brand rail collapse is separate and currently ephemeral.

## Design

### Shared media contract

Add a pure media presentation helper next to the existing quotation media helper. It will expose:

- ordered candidate resolution using the existing `hero_image_url`, `gallery`, and legacy `images` fields;
- source-size-aware fit geometry for a normalized frame;
- a shared `contain` presentation default with equal inset on all sides;
- no transform/rotation in either React Native or PDF rendering.

The existing `ProductImage` remains the only UI image component. It will use the normalized contract by default, keep `cover` available only for explicitly intentional crops, and continue to use expo-image memory/disk caching, lazy loading, skeletons, and fallbacks. No source asset will be enlarged to fabricate detail; when a higher-resolution candidate is already available it remains first in the existing ordered list.

### Quotation layout

Change quotation explorer column selection to accept measured pane width rather than global window width. The desktop explorer will use two product cards when the available pane is wide enough for readable cards, and one card when it is not. The picker sheet will retain its own compact responsive behavior. Product image frames will use a design-token aspect ratio and inset rather than per-component pixel dimensions.

### Sidebar

Add a desktop-only persisted collapse state to `frontend/app/(admin)/_layout.tsx`, backed by the existing storage utility and scoped to the admin shell. Expanded and collapsed widths will use existing `layout.sidebar`/`layout.rail` tokens. The shell will animate the web width transition, preserve the existing tablet rail and phone bar behavior, and expose a keyboard/screen-reader accessible toggle.

### PDF parity

Delete the forced landscape rotation path. Decode image bytes without changing orientation, then use the same normalized contain-fit geometry as the editor to draw a centered image inside the PDF cell. The implementation will use native pixel dimensions when available to avoid unnecessary interpolation, retain the existing remote-image cache, and fall back to the current placeholder if a URL cannot be loaded.

## Error handling and compatibility

- Invalid or failed candidates continue through the existing fallback order; no product card may crash because media is missing.
- Data URLs remain supported in the shared UI renderer; PDF remote fetching remains limited to existing HTTP(S) behavior.
- Historical quotations continue to use their persisted line-item image values and pricing; only presentation changes.
- Supabase and MongoDB schemas remain unchanged.

## Verification

- Frontend: focused unit tests for candidate ordering, fit geometry, and responsive columns; lint and TypeScript/build checks available in the project.
- Backend: focused unit tests for orientation-preserving PDF image flow and contain-fit geometry, then the existing backend unit suite and quotation PDF smoke tests.
- Browser: exercise builder/editor at 1280, 1440, 1920, 768, 1024, 375, 390, and 430 widths; inspect tiles, taps, basins, showers, and accessories for no crop/stretch/overflow and compare generated PDF pages to the editor.
- Record any unavailable live-browser or production-storage verification explicitly instead of treating code inspection as visual proof.
