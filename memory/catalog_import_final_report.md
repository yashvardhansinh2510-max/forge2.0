# Forge — Catalog Import Final Report

## Per-brand results

| Brand | Cert Score | Products | Families | Variants | Subcategories | Series | Images (media) | Status |
|---|---|---|---|---|---|---|---|---|
| **Vitra** | 97.3 | 250 | 101 | 250 | 19 | 39 | 243 | ✅ Imported |
| **Grohe** | 99.4 | 864 | 788 | 56 | 0 | 16 | 864 | ✅ Imported |
| **Geberit** | 97.4 | 496 | 234 | 1 | 0 | 11 | 504 | ✅ Imported |
| Hansgrohe | — | 0 | 0 | 0 | 0 | 0 | 0 | ⏸ Waiting for Supplier Source Files |
| Axor | — | 0 | 0 | 0 | 0 | 0 | 0 | ⏸ Waiting for Supplier Source Files |

## Overall totals

| Metric | Value |
|---|---|
| Total products (active) | **1,610** |
| Total families | **1,123** |
| Total variants (products with a variant label) | **307** |
| Total categories | **11** |
| Total subcategories | **19** |
| Total series | **66** |
| Total images uploaded to Supabase | **1,611** |
| Weighted certification score (products-weighted) | **98.4** |

Per-brand certification scores: Vitra 97.3 · Grohe 99.4 · Geberit 97.4.

## Data quality notes

- **Grohe/Geberit low subcategory counts** — supplier PDFs do not carry a dedicated subcategory column; the adapter falls back to category-only. Enriching these requires either supplier metadata pages or manual curation.
- **Grohe variants = 56** — most Grohe SKUs are unique products; only 56 rows are labeled as variants of a parent family. This is a supplier-data reality, not a pipeline issue.
- **Vitra media = 243/250** — 7 rows had no associated image in the source workbook (accessories, rim-only pieces). Confirmed against the source XLSX.
- **Geberit media = 504** vs. 496 products — 8 products carry gallery images in addition to the hero.
- **Image quality distribution (from certification reports):**
  - Vitra: 12% excellent · 11% good · 21% acceptable · 56% poor (supplier ships thumbnails)
  - Grohe: predominantly acceptable-to-good (WMF/EMF rasterized at 2048px)
  - Geberit: predominantly acceptable
- **Storage layer:** all 1,611 images live in Supabase `forge-products` bucket at `/{brand}/…`. Product docs carry `hero_image_url` only — zero base64 in Mongo.

## Blockers / awaiting

1. **Hansgrohe** — no supplier PDF available. Provide URL or upload the 2026 pricelist to `/app/backend/temp/hansgrohe.pdf` (or POST to `/api/catalog/imports/from-url`) to unblock.
2. **Axor** — same as Hansgrohe.

## Artifacts

- Per-brand QA reports: `/app/memory/{vitra|grohe|geberit}_qa_report.md`
- Final tally JSON: `/app/memory/import_final_tally.json`
- Bootstrap tooling for future sessions: `/app/backend/.env.example`, `/app/frontend/.env.example`, `/app/scripts/setup-env`
