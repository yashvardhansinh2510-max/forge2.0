# Forge — P1/P2 Recovery Report (Product Images + Missing Products)

**Date:** 2026-07-04
**Iteration:** 5
**Scope:** Priority 1 (product images), Priority 2 (missing products investigation),
Priority 3 (Quotation Builder integration verification post-swap), deployment env review.

---

## 1. Root Cause Analysis

### P1 — Product Images: **stock URLs hardcoded in seed.py**
- `/app/backend/seed.py` (pre-patch) hardcoded 5 Unsplash / Pexels URLs and
  reused them across all 20 seed products.
- The `catalog_pipeline/image_extractor.py` (which extracts real supplier
  images from PDF pages and WDP-formatted XLSX embeds, converts them to
  base64 PNGs, and dedupes) is fully implemented but **has never been
  executed against real supplier data** on this environment.
- Evidence: `db.catalog_imports.count_documents({})` returned 0 before the
  fix; every product's `images` field contained an `images.unsplash.com` or
  `images.pexels.com` URL.

### P2 — Missing GEBERIT / VITRA / GROHE products: **catalog import was never run**
- Product count in `forge.products`: **20** (4 per brand × 5 brands).
- PRD claims: 881 GROHE + 555 GEBERIT + 264 VITRA (~1,700). These figures
  were achieved against **user-uploaded 2026 pricelists** which did not
  exist on this container.
- `find / -iname "*grohe*.pdf"` etc. — returns only the Python adapter files,
  not a single supplier PDF/XLSX.
- User has now uploaded 3 of the 5 required files (GEBERIT PDF, GROHE PDF,
  VITRA XLSX). HANSGROHE and AXOR pricelists still pending.

### P3 — Quotation Builder 2.0
Already certified at 19/19 UX matrix in `/app/memory/phase1a_verification.md`.
No regressions detected by the backend regression pass (21/21 today).

### Deployment env — **`.env` files missing on this container**
- `/app/backend/server.py` and `/app/backend/db.py` both call
  `load_dotenv(Path(__file__).parent / ".env")` and then `os.environ["MONGO_URL"]`
  with **no default**. If the `.env` file doesn't exist, backend crashes on
  startup with `KeyError: 'MONGO_URL'`.
- `/app/frontend/src/api/client.ts` reads `process.env.EXPO_PUBLIC_BACKEND_URL`
  which is baked in at Metro build time. If `/app/frontend/.env` doesn't
  exist, every request becomes `undefined/api/...` and fails.
- Both files were missing on this container until iteration 4 recreated
  them. This is a **deployment prerequisite** that must be documented.

---

## 2. Fixes Applied

### A. `ProductImage` component (new)
`/app/frontend/src/components/ProductImage.tsx` — a production-ready renderer:

- **expo-image** backend with `cachePolicy: memory-disk` — first render is
  network, subsequent renders come from RAM or disk cache.
- **Skeleton loader** — animated 0.35↔0.7 opacity shimmer during the first
  paint. Kept small to avoid list jank.
- **BlurHash placeholder** so the layout doesn't shift while decoding.
- **Ordered fallback candidates** — accepts either a single URL/data-URL
  or an array; on `onError` it advances to the next candidate before
  giving up. Handy for supplier catalogs that ship multiple image
  candidates per SKU.
- **`FallbackGlyph`** — soft `feather-image` icon plus the product SKU in
  small caps when no candidate resolves. Deliberately understated so it
  reads as "waiting for asset", not "broken".
- **`recyclingKey`** set to the current candidate URI so `expo-image`
  reuses its GPU texture when scrolling long lists.
- **Responsive** — the caller supplies dimensions via `style`. No hard-coded
  sizes inside the component.
- **Accessibility** — `role="image"` with a sensible default label.

### B. Every product-image call site swapped to `ProductImage`
| File                                          | Was                              | Now                                    |
|-----------------------------------------------|----------------------------------|----------------------------------------|
| `app/(admin)/dashboard.tsx`                   | `<Image source={{ uri: p.image }} />` | `<ProductImage source={p.image} fallbackLabel={p.sku} />` |
| `app/(admin)/catalog/index.tsx`               | `<Image source={{ uri: p.images[0] }} />` | `<ProductImage source={p.images} fallbackLabel={p.sku} />` |
| `app/(admin)/catalog/[id].tsx`                | `<Image source={{ uri: p.images[0] }} />` | `<ProductImage source={p.images} fallbackLabel={p.sku} />` |
| `app/(admin)/quotations/new.tsx` picker row   | `<Image source={{ uri: item.images[0] }} />` | `<ProductImage source={item.images} fallbackLabel={item.sku} />` |
| `app/(admin)/quotations/new.tsx` line row     | `<Image source={{ uri: l.image }} />` | `<ProductImage source={l.image} fallbackLabel={l.sku} />` |
| `app/(admin)/quotations/new.tsx` swap sheet row | `<Image source={{ uri: p.images[0] }} />` | `<ProductImage source={p.images} fallbackLabel={p.sku} />` |

Direct `expo-image` imports removed from these files; only `ProductImage`
touches `expo-image` now.

### C. Removed stock-photo URLs from `seed.py`
- `PRODUCT_SEEDS` tuple no longer carries an image URL column.
- Every seed inserts `images=[]` and tag `demo`.
- Live DB was migrated (`update_many` cleared 20 products; variants on
  HAN-FAU-001 / HAN-FAU-002 preserved).
- Zero references to `unsplash.com` or `pexels.com` remain anywhere in the
  codebase.

### D. Pipeline health confirmed
```
grohe        -> GroheAdapter
hansgrohe    -> GroheAdapter    (aliased)
axor         -> GroheAdapter    (aliased)
vitra        -> VitraAdapter
geberit      -> GeberitAdapter
```
All adapter modules, the certifier, and the image extractor import cleanly.
`GET /api/catalog/imports/config/brands` lists all 5. `GET /api/catalog/imports`
returns an empty array (no jobs have been run yet — this is expected).

### E. Deployment prerequisites documented
- `/app/backend/.env` — must contain `MONGO_URL`, `DB_NAME`, `JWT_SECRET`.
- `/app/frontend/.env` — must contain `EXPO_PUBLIC_BACKEND_URL`
  (empty for same-origin deploys behind the k8s ingress that routes `/api/*`;
  set to `http://localhost:8001` for local dev only).

---

## 3. Verification Report

### 3.1 Backend regression — via `deep_testing_backend_v2`
**21/21 tests PASSED, 100 % success rate.**

- **Product catalog (11/11)** — 20 items, no unsplash/pexels URLs anywhere,
  search filter works, brand filter works, category filter works, product
  detail returns variants (HAN-FAU-001 has 3, HAN-FAU-002 has 2), 5 brands,
  7 categories, recent/frequent endpoints healthy, alternates endpoint
  intact.
- **Catalog import pipeline smoke (3/3)** — brands config, imports list,
  auth enforcement.
- **Quotation regression (4/4)** — POST creates 201, silent PATCH persists
  notes without a revision, null-image quotations don't crash, alternates
  work when `images: []`.
- **Pipeline importability** — every adapter + certifier + image_extractor
  imports cleanly.

### 3.2 Frontend visual — `mcp_screenshot_tool`
- `/app/test_reports/phase1a/catalog_with_fallback.jpg` — 20-tile catalog
  grid; every tile shows a uniform fallback with brand badge and SKU label.
- `/app/test_reports/phase1a/builder_with_fallback.jpg` — quotation builder
  picker rows and line-row thumbnails render the fallback consistently.
  Variant chips still show swatch + finish + price delta correctly.

---

## 4. Remaining Issues

1. **Real supplier data not yet ingested.**
   User has uploaded 3 of 5 required files (GEBERIT, GROHE, VITRA).
   HANSGROHE and AXOR pricelists pending. Do not run the production import
   until all 5 are available (per user instruction — "wait for the
   supplier catalogs before beginning the production import").

2. **DnD gestures on `react-native-draggable-flatlist` are visual-only under
   headless Playwright** — same caveat from iteration 4, not a bug.

3. **Deploy env parity** — needs a bootstrap script or Kubernetes ConfigMap
   to guarantee `/app/backend/.env` and `/app/frontend/.env` exist on every
   redeploy. Currently a manual step. Handoff to the deploy_agent when the
   user runs the deploy button.

---

## 5. Recommendation for the next phase

Once you upload HANSGROHE and AXOR pricelists, the highest-impact next
phase is **Phase 1.5 — Real Catalog Ingestion**, in this order:

1. Run `POST /api/catalog/imports/from-url` for each of the 5 supplier
   files. Each import runs Extract → Normalize → Validate → Certification
   (score `overall_score`).
2. Review each certification report; approve if `overall_score ≥ 0.85`;
   otherwise iterate on the adapter.
3. Approved products replace the 20 demo entries (or the demo tag is used
   to phase them out gradually).
4. Once the catalog is real, delete `seed.py` PRODUCT_SEEDS (retain only
   brands + categories seeding) and remove the `demo` tag support code.
5. **Only then** proceed to Phase 1B — the smart-mix ranking + popularity
   + category ordering features you gated for later.

Reasoning: every feature in Phase 1B (smart-mix ranking, popularity, family
ordering) is meaningless without real product data. Ingest first, then
build ranking on top of a real corpus.

---

## 6. Awaiting user action

- [ ] Upload HANSGROHE 2026 pricelist.
- [ ] Upload AXOR 2026 pricelist.
- [ ] Once all 5 files are attached, authorise the production import
      (I will run the 5 imports sequentially, produce a certification report
      for each, and pause for your approval on each score before writing to
      the products collection).
