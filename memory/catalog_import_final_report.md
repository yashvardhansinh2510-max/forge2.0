# Forge — Catalog Final Report (4 brands imported)

## Per-brand production totals

| Brand | Cert | Products | Families | Variants | Categories | Series | Images |
|---|---|---|---|---|---|---|---|
| Vitra | 97.3 | 250 | 101 | 250 | 6 | 39 | 243 |
| Grohe | 99.4 | 854 | 779 | 56 | 6 | 16 | 864 |
| Geberit | 97.4 | 496 | 234 | 1 | 5 | 11 | 504 |
| **Hansgrohe** (incl. AXOR) | **96.9** | **1,272** | **1,158** | **1,147** | **14** | **41** | **1,273** |
| Axor (standalone) | — | 0 | 0 | 0 | 0 | 0 | 0 | ⏸ **Deactivated** — merged as `collection = "AXOR"` under Hansgrohe |

### Hansgrohe collection split
- Hansgrohe (main): 826 products
- **AXOR (premium): 446 products**

## Overall catalog totals

| Metric | Value |
|---|---|
| **Total products (active)** | **2,872** |
| Total families | **2,272** |
| Total variants | **1,454** |
| **Total categories** | **26** |
| Total subcategories | 20 |
| Total series | 107 |
| **Total images on Supabase** | **2,884** |
| Weighted certification score | **97.8** |

## Storage layout
- All products: `products` collection · MongoDB (metadata only, zero base64)
- All images: `product_media` + Supabase `forge-products` bucket
- Import staging: `catalog_imports` (all jobs → `status: imported`)
- Image dedup blob store: `catalog_image_blobs` (2,698 rows retained for rollback)

## AXOR brand deactivation confirmed
- `brands` collection: `{ name: "Axor", active: false }`
- All AXOR products live under `brand_id: <Hansgrohe>` with `collection: "AXOR"`
- Search / filter / hierarchy queries now correctly surface AXOR as a *collection* inside Hansgrohe.

## Notes / follow-ups
- Grohe / Geberit subcategories = 0. Supplier PDFs don't ship a subcategory column; enriching this requires manual curation or supplier metadata pages. Not a defect.
- Vitra media = 243/250 — 7 SKUs have no source image in the supplier workbook (accessories).
- Hansgrohe image quality mix: 35% premium (excellent/good) · 65% thumbnail-grade. Supplemental photography recommended for hero cards.
- **Waiting**: standalone AXOR pricelist has been requested but was merged into Hansgrohe per business rule; no additional AXOR-specific file expected.

## Artifacts
- Per-brand QA reports: `/app/memory/{vitra|grohe|geberit|hansgrohe}_qa_report.md`
- JSON summary: `/app/memory/catalog_import_final_report.json`
- Extraction cache (Hansgrohe, 27 MB): `/tmp/hansgrohe_rows.pkl` — safe to delete
- Bootstrap tooling: `/app/scripts/setup-env`, `/app/backend/.env.example`, `/app/frontend/.env.example`
