# Iteration 2A — Certification Report

**Date:** 2026-07-04
**Scope:** Media architecture, search + indexing, import framework, migration.
**Status:** ✅ **PASSED** — ready for user verification.

---

## 1. Executive Summary

Iteration 2A shipped the foundation the rest of the catalog rebuild sits on.
No visible UI overhaul yet (that is 2B). What changed under the hood:

* **Media is no longer coupled to product data.** A provider-agnostic
  `MediaStorage` layer lives at `/app/backend/media_storage/`. The current
  driver is `SupabaseStorageDriver`. Swapping to R2, S3 or a local disk is a
  ~30-line file, no changes elsewhere.
* **All 250 VITRA supplier images migrated to Supabase.**
  Legacy `products.images` and `products.image_meta` are now empty across
  the whole catalogue. MongoDB stores metadata only.
* **Search understands SKU, name, family, series, finish, colour, dimensions
  and specs**, ranks results, and groups variants by family so a single
  product with 6 finishes is one card, not six.
* **Reusable import framework** (`catalog_pipeline/framework.py`) with
  shared category / subcategory / finish resolvers and a declarative
  `SupplierManifest` pattern. VITRA's manifest is registered as the
  reference implementation for future brands.

Nothing is mocked. Every image URL above comes from Supabase.
Every search hit is served by a real MongoDB text index. No dual-storage.

---

## 2. What was built

### 2.1 MediaStorage abstraction (`/app/backend/media_storage/`)

| File | Purpose |
| --- | --- |
| `base.py`             | `MediaStorage` ABC + `StoredObject` dataclass. Zero provider details leak. |
| `supabase_driver.py`  | Only file that talks to Supabase Storage REST API. Supports both classic JWT keys and the new `sb_secret_...` / `sb_publishable_...` format. |
| `factory.py`          | Reads `MEDIA_STORAGE_DRIVER` env var, returns the right driver. Public/private bucket helpers. |

Operations exposed:

```
upload(bucket, key, data, content_type, upsert, cache_control) -> StoredObject
replace(bucket, key, data, content_type) -> StoredObject
delete(bucket, key)
exists(bucket, key) -> bool
get_public_url(bucket, key) -> str
get_signed_url(bucket, key, expires_in=3600) -> str
```

Verified end-to-end with a live upload → GET public → DELETE round trip.

### 2.2 `product_media` collection + service (`/app/backend/services/media_service.py`)

Every image now lives in a Mongo document with:

```
{ id, product_id, family_key, brand_id, source_type, role,
  bucket, storage_key, public_url,
  width, height, quality, sha1, mime, size_bytes,
  is_primary, sort_order, uploaded_by, notes,
  created_at, updated_at }
```

`source_type ∈ {supplier, manufacturer, internal}` — this is the exact
requirement you asked for: swap supplier thumbnails for official
manufacturer media *later* without touching SKUs or pricing.

Service functions (used by routes AND the migration script):

* `upload_and_register(...)` — content-addressed upload + dedupe via SHA-1
* `list_media_for_product(product_id, family_key)` — ordered by priority
  `internal > manufacturer > supplier`, then `is_primary`, then `sort_order`
* `hydrate_product_media(product)` — attaches `hero_image_url`, `gallery`
  and `media_summary` to any product dict. Falls back to legacy embedded
  images so pre-migration data still renders during a rolling deploy.
* `delete_media(media_id)` — removes both storage object + metadata

### 2.3 Endpoints (`/app/backend/routes/media_routes.py`)

| Method | Route | Notes |
| --- | --- | --- |
| GET  | `/api/products/{id}/media`      | List media for a product (falls through to family) |
| POST | `/api/products/{id}/media`      | Upload manufacturer / internal image (multipart) |
| POST | `/api/families/{key}/media`     | Attach media at the family level (shared by all variants) |
| PATCH| `/api/media/{id}`               | Toggle `is_primary`, change `role`, `sort_order`, `notes`, `source_type` |
| DELETE|`/api/media/{id}`               | Remove storage object + metadata |

Every upload goes through the `MediaStorage` interface — routes never
import the Supabase driver.

### 2.4 Search + facets (`/api/catalog/search`, `/api/catalog/facets`)

`/api/catalog/search?q=basin&limit=5`

Ranking priority (highest first, matches your spec):

1. Exact SKU / SKU prefix
2. Product name / family name (Mongo text score)
3. Series / subcategory / finish / colour
4. Dimensions / description

Grouped by `family_key` by default. `group=false` returns flat variants.

`/api/catalog/facets` returns brand / category / subcategory / series /
finish / colour / material buckets + price min/max — the datasource for
the multi-facet filter drawer that lands in 2B.

### 2.5 Family-first page endpoint (`/api/families/{key}`)

Returns everything a Shopify-style family page needs in one call:

```
{ family_key, family_name, brand, category, subcategory, series,
  description, min_price, max_price, variant_count,
  variants: [...],           # per-variant fields for the switcher
  gallery: [...],            # ordered media list from product_media
  hero_image_url, specs_union, downloads: [],
  compatible_ids, accessory_ids, related_ids }
```

### 2.6 Reusable import framework (`/app/backend/catalog_pipeline/framework.py`)

* `classify_category(detail, section, extra_rules)` — shared category classifier
* `extract_subcategory(...)` — subcategory keyword matching, no fabrication
* `resolve_finish(raw)` — normalises supplier finish labels into
  `(label, colour, code)`. Comes with 20 curated finish aliases.
* `make_family_key(*parts)` — deterministic slugified key
* `SupplierManifest` — declarative brand config; `SUPPLIER_MANIFESTS`
  registry. VITRA's manifest is already registered.

Adding GROHE / GEBERIT / HANSGROHE / AXOR now = 1 manifest + a slim
file-format-specific adapter that reuses these resolvers.

### 2.7 Orchestrator writes to Supabase (`/app/backend/catalog_pipeline/orchestrator.py`)

Every future import now:

1. Decodes supplier images to bytes.
2. Uploads via `media_service.upload_and_register(source_type="supplier")`.
3. Stores an empty `images: []` on the product doc.

The product document is now a **metadata-only** record. Zero base64
inside Mongo.

### 2.8 MongoDB indexes (`/app/backend/scripts/ensure_indexes.py`)

| Collection      | Index | Purpose |
| --- | --- | --- |
| products        | text (name, sku, family_name, series, subcategory, finish, colour, dimensions, tags, description) with weighted scores | ranked search |
| products        | `id` unique, `sku`, `family_key`, `(brand_id, category_id, subcategory, series)`, `(active, brand_id)` | facet + hierarchy queries |
| product_media   | `id` unique, `product_id`, `family_key`, `(sha1, product_id, source_type)`, `(is_primary desc, sort_order asc)` | media lookups + dedupe |
| brands / categories | `id` unique, `slug` unique | referential integrity |
| catalog_image_blobs | `sha1` unique | legacy fallback dedupe |

---

## 3. Migration Report

Script: `/app/backend/scripts/migrate_media_to_supabase.py`
Report: `/app/memory/media_migration_20260704_202102.json`

| Metric | Value |
| --- | --- |
| Brand filter        | all |
| Candidate products  | **250** |
| Images migrated     | **250** ✅ |
| Duplicates skipped  | 0 |
| Failed              | **0** |
| Products cleaned (legacy fields cleared) | **250** ✅ |
| Total bytes uploaded | 2,062,793 B (**1.97 MB**) |
| Dry-run re-check    | 0 remaining candidates (idempotent) |

Verified independently after the run:

```
Products: 250, still-with-legacy: 0, product_media rows: 250
```

**Integrity guarantee:** every image was SHA-1 verified *after* upload
(`obj.sha1 == expected_sha1`) before its legacy blob was allowed to be
cleared from `products.images`. A mismatch would have rolled back the
upload and kept the legacy fallback in place — zero data loss possible.

**Idempotency guarantee:** re-running the script emits `Candidates: 0`
because there is nothing left to migrate. Adding a new brand later
(e.g. GROHE) picks up only its own products.

---

## 4. Verification checks

### 4.1 Product listing (`GET /api/products`)

```
7231B403H6216 :: hero=https://vburaxruvbnbahegtbya.supabase.co/... :: quality=acceptable
5674B403H6194 :: hero=https://vburaxruvbnbahegtbya.supabase.co/... :: quality=acceptable
5885B403H0101 :: hero=https://vburaxruvbnbahegtbya.supabase.co/... :: quality=poor
```

### 4.2 Legacy image fields (MUST be empty)

```
7231B403H6216: images_len=0 meta_len=0
5674B403H6194: images_len=0 meta_len=0
5885B403H0101: images_len=0 meta_len=0
```

### 4.3 Ranked search (`/api/catalog/search?q=basin&limit=5`)

```
grouped: True total: 4
 - MEMORIA · BASIN MIXER            | 1 variants  | hero: True
 - SOLID S · BASIN MIXER            | 1 variants  | hero: True
 - ISTANBUL · SHOWER SYSTEMS ...    | 5 variants  | hero: True
```

### 4.4 Facets (`/api/catalog/facets`)

```
brands: 1  |  categories: 6  |  series: 39
finishes: 5  |  price: {min: 6360, max: 520180}
```

### 4.5 Family endpoint (`/api/families/vitra:csw:archiplan:rectangle-600x380mm`)

```
name: ARCHIPLAN · RECTANGLE 600x380mm
variants: 3   gallery: 6   hero_url: (Supabase URL)
```

### 4.6 Frontend catalog screenshot

Attached separately. Confirms 60 families render with Supabase-hosted
imagery, variant swatches, honest quality badges (THUMB / EXCELLENT),
and the family-grouped view is the primary experience.

---

## 5. Honest image quality reporting

Nothing was upscaled or fabricated. The VITRA supplier file continues to
ship mostly thumbnail-grade sources. That reality is now recorded per-image
in `product_media.quality` and surfaced in the catalog UI as a badge:

| Quality    | Threshold (min longest edge) | UI badge |
| --- | --- | --- |
| excellent  | vector, or ≥ 1024 px | green EXCELLENT |
| good       | 640 – 1023 px | blue GOOD |
| acceptable | 320 – 639 px  | amber OK |
| poor       | < 320 px      | red THUMB |
| missing    | no image        | grey NO IMAGE |

Migrating official manufacturer images later is a one-line upload via
`POST /api/families/{key}/media?source_type=manufacturer` — the product
priority ordering (`internal > manufacturer > supplier`) means the new
image automatically becomes hero, no product records change.

---

## 6. Environment additions

`/app/backend/.env`:

```
MEDIA_STORAGE_DRIVER=supabase
SUPABASE_URL=https://vburaxruvbnbahegtbya.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<redacted>
SUPABASE_ANON_KEY=<redacted>
SUPABASE_PUBLIC_BUCKET=forge-products
SUPABASE_PRIVATE_BUCKET=forge-private
```

Bucket configuration verified live:

* `forge-products` — **Public**  (product images, family images, thumbnails)
* `forge-private` — **Private** (supplier PDFs, technical drawings, CAD files, internal docs)

No Supabase reference exists anywhere outside `/app/backend/media_storage/*`.

---

## 7. Known non-issues (called out honestly)

1. **VITRA image quality is still mostly `acceptable` / `poor`.** This is
   the source data reality. Phase 2C will ship the admin media manager so
   you can upload official manufacturer images per family and instantly
   upgrade every variant in that family. No re-import needed.
2. **Old customers using the app during migration would have seen
   Supabase URLs served from the new `hero_image_url` field.** The
   frontend still reads legacy `images[]` as a fallback, so nothing
   would have gone blank at any point.
3. **Search recall on GROHE-style very-long SKUs** hasn't been stress
   tested yet — will validate during the GROHE onboarding.

---

## 8. Ready-for-2B checklist

* [x] MediaStorage abstraction with SupabaseStorageDriver
* [x] product_media metadata collection
* [x] Migration script (idempotent, SHA-1 verified, report)
* [x] All 250 VITRA images live on Supabase
* [x] Legacy embedded blobs cleared
* [x] Ranked catalog search endpoint
* [x] Multi-facet endpoint
* [x] Family-first backend endpoint
* [x] MongoDB indexes (text + hierarchy + media)
* [x] Reusable import framework helpers + manifest pattern
* [x] Orchestrator writes to Supabase for future imports
* [x] Zero base64 blobs in product docs
* [x] Frontend rendering verified via screenshot

---

**Requesting approval to proceed with Phase 2B (world-class catalog UI +
family-first product page).**
