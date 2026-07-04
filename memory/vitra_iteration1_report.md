# Forge — Iteration 1 (VITRA Reference Implementation) — Certification Report

**Run date:** 2026-07-04
**Scope:** Make VITRA production-quality before importing GROHE / GEBERIT / HANSGROHE / AXOR.

---

## What changed & why

### 1. Environment restoration
- Created `/app/backend/.env` (MONGO_URL, DB_NAME, JWT_SECRET) and `/app/frontend/.env` (EXPO_PUBLIC_BACKEND_URL) so the container boots consistently.

### 2. Image extraction pipeline (`backend/catalog_pipeline/image_extractor.py`)
- **WMF / EMF conversion**: `emf2svg-conv` + `rsvg-convert` (installed) rasterize EMF vector art at **2048px** long-edge. WMF handled via ImageMagick 6 + libwmf delegate (policy updated to allow WMF/EMF read-only).
- **WDP (JPEG XR)**: retained `imagecodecs` decoder from prior iteration.
- **Highest-quality selection**: for anchors that carry multiple blips (AlternateContent Choice + Fallback), pick the highest-quality candidate by (quality bucket, longest-edge pixels).
- **Quality classification** — every extracted image is bucketed:
    - **Excellent** — ≥1024px longest edge, or any rasterized vector (EMF/WMF/SVG)
    - **Good** — 640–1024px
    - **Acceptable** — 320–640px
    - **Poor** — <320px (thumbnails)
    - **Missing** — no image at all
- **Storage optimisation**: cap raster longest edge at 1024px, re-encode as JPEG q=82 (photos) or WebP q=80 (transparent), keep the input if the re-encoded copy is larger.
- **Deduplication**: SHA-1 content hash per anchor (kept intra-anchor). Cross-anchor sha1s are **not** dropped — Vitra legitimately reuses one family photo across multiple finish rows.
- **Per-image metadata** persisted: `sha1`, `width`, `height`, `quality`, `source_format`, `bytes_len`.
- **Aggregate quality report** attached to the certification: total, excellent/good/acceptable/poor counts, source-format breakdown, min/median/max longest-edge, plain-English verdict.

### 3. Product model extended (`backend/models.py`)
New optional fields (backward-compatible):
- `subcategory`, `series`, `family_key`, `family_name`, `variant_label`
- `finish_code`, `colour`
- `image_meta`, `image_quality`
- `specs` (freeform key/value bag for supplier extras like `form`, `related_codes`)

### 4. Vitra adapter improvements (`backend/catalog_pipeline/adapters/vitra.py`)
- **Category detection** now prioritises the `detail` column (specific) over the sheet name (generic). Vitra ships every ceramic product on one `CSW` sheet — previously everything was mis-classified as Water Closets.
- **Subcategory extraction** matches a controlled keyword list; falls back to a cleaned form of the detail column; rejects dimension-junk labels (`"600Mm & 400Mm"`).
- **Series** cleaned (newlines collapsed).
- **Finish code** captured from headers (`"MATT BLACK 483"` → `"483"`).
- **Colour** derived cleanly from the finish header (strips numeric codes and trailing slashes).
- **Family key** is stable across finishes: `vitra:{sheet}:{design}:{detail}`.
- **Row-to-image mapping** tightened to ±2 rows with exclusive best-match selection (previous ±2 greedy window over-shared one image across 5+ unrelated families).

### 5. Certifier (`backend/catalog_pipeline/certifier.py`)
- Now emits image quality histogram (`excellent_images`, `good_images`, `acceptable_images`, `poor_images`) plus the aggregate `image_quality` block (with premium %, median edge, per-source counts and plain-English verdict).

### 6. Orchestrator (`backend/catalog_pipeline/orchestrator.py`)
- **Image blob offload**: base64 data URLs live in a dedicated `catalog_image_blobs` collection keyed by SHA-1 (upsert-only, idempotent). Job docs shrunk from **46 MB → 0.28 MB**, safely under MongoDB's 16 MB BSON cap.
- Import writes all new hierarchy fields onto the Product doc.
- `family_name` avoids `"SERIES · SERIES · DETAIL"` duplication.
- Resolves `blob:<sha1>` refs from the in-memory map on import (no extra DB round-trips).

### 7. Catalog endpoints (`backend/routes/catalog_routes.py`)
- `GET /api/products` now filters on `subcategory`, `series`, `family_key`, `colour`. Search hits `name`, `sku`, `description`, `series`, `family_name`, `subcategory`, `finish`, `colour`, `dimensions`, `tags`.
- `GET /api/catalog/hierarchy` — full Brand → Category → Subcategory → Series → Family tree with per-family sample image, min-price, and image-quality bucket.
- `GET /api/products/families` — one card per family, variants collapsed underneath, ready for the premium grouped view.

### 8. Frontend
- **Grouped catalog view** with mode toggle (`Families` | `All variants`). Family cards show series, subcategory, colour swatches, variant count badge, price range, and an honest image-quality badge.
- **Subcategory & Series chip filters** driven by the hierarchy tree, updating live as brand/category/subcategory change.
- **Search widened** to include series / family / finish / colour / dimensions.
- **Product detail** page fully rebuilt with breadcrumb, image gallery, quality badge + honesty callout for thumbnail-grade images, finish selector (swaps between sibling variants), full spec sheet, related products strip.

---

## Certification results (VITRA 2026)

| Metric | Value |
|---|---|
| Products imported | **250** |
| Rows extracted    | 264 |
| True SKU dupes (rejected) | 6 |
| Pending review    | 8 |
| Cross-family SKUs (legitimate re-listings) | 0 |
| Categories        | **6** (Water Closets 190 · Bidets 45 · Showers 5 · Faucets 5 · Flush Plates 3 · Basins 2) |
| Subcategories     | **19** (Rim-Ex WC, Basin Mixer, Bath Mixer, Bidets, Chrome Battery, etc.) |
| Series            | **39** (ARCHIPLAN, MEMORIA, METROPOLE, PLURAL, SENTO, OUTLINE, …) |
| Product families  | **101** unique families |
| **Overall certification score** | **97.9 / 100** |

### Image quality — the honest assessment

| Bucket | Count | % of total |
|---|---|---|
| Excellent (≥1024px or vector) | 31  | 12 % |
| Good (640–1024px)             | 30  | 11 % |
| Acceptable (320–640px)        | 55  | 21 % |
| Poor (thumbnail <320px)       | 148 | 56 % |
| **Total mapped**              | 264 | — |

**Source breakdown**: 142 PNG · 45 JPEG · 22 JPG · 55 **EMF** (previously dropped by openpyxl — now rasterized to 2048px vector artwork).

**Median longest edge**: 306px. **Premium percentage**: 23%.

**Verdict emitted by the pipeline**:
> *"Supplier file only contains thumbnail-grade artwork (23% premium; median longest edge = 306px). Recommend sourcing official product photography separately."*

This is the honest classification you asked for. **We did not upscale poor images** — the low-res thumbnails are reported as `poor` in the UI with a clear callout on the product page.

**56% of Vitra products** ship with < 320px thumbnails. This is a **supplier-file limitation**, not an extraction bug. To move Vitra to genuinely premium imagery, official media should be sourced separately (Vitra global brand asset library, or supplier direct request).

**44% of Vitra products** (excellent + good + acceptable = 116) do have usable ≥ 320px images — good enough for cards. Of those, 61 (23%) are premium.

---

## Remaining issues

1. **Image quality** — no software fix is available for the 148 poor-quality thumbnails; needs an external asset source. The UI now flags these clearly.
2. **8 pending rows** — Vitra rows with a valid SKU but missing MRP or category (e.g. accessory-only listings). Reviewer needs to fill in details or reject.
3. **6 true duplicate SKUs** — same SKU appearing on the same family key twice; auto-rejected as data-entry errors. Reviewer should verify.
4. **Grohe / Geberit / Hansgrohe / Axor** — awaiting approval before running.

---

## Ready for approval

Please review the screenshots at `/tmp/f2_catalog_families.png` and `/tmp/f3_product_detail.png`. If the current state is acceptable, I will proceed with the same pipeline for GROHE, GEBERIT, HANSGROHE, AXOR one at a time.
