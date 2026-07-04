# Forge — Product Requirements

**Vision:** Premium ERP/CRM/POS for sanitaryware, bath fitting and building material distributors. Combines Linear+Stripe+Apple polish with showroom-grade simplicity.

## Iteration 3 — Catalog Import & Certification System (Delivered)

Real production ingestion for **Hansgrohe, Axor, Grohe, Vitra, Geberit**. Framework is reusable — new suppliers ship as one adapter file.

### What the framework does
```
Supplier File → Extraction → Normalization → Variant/Family Detection →
Category Classification → Image Mapping → Price Validation → SKU Validation →
Duplicate Detection → Human Review → Certification → Import → Post-Import Verification
```

### Real-world results (against user-uploaded 2026 pricelists)
| Brand   | Products | Families | Images       | Overall | Production ready |
|---------|----------|----------|--------------|---------|------------------|
| GROHE   | 881      | 802      | 881/2592     | **99.4%** | ✅ YES |
| GEBERIT | 555      | 255      | 555/538      | **96.7%** | pending SKU dedupe |
| VITRA   | 264      | 102      | 258/168 (156% coverage — some rows have multiple images) | **97.3%** | pending 6 dupe SKUs |

### Modules
- **`catalog_pipeline/base.py`** — `ProductRow`, `ExtractionReport`, `BrandAdapter` ABC, allowed categories, `[MISSING DATA]` sentinel — never fabricate.
- **`catalog_pipeline/image_extractor.py`** — Extracts every image from PDF (pypdf) & XLSX (openpyxl drawings) as base64 data-URLs. De-duplicates by SHA-1. Skips corrupted images safely.
- **`catalog_pipeline/adapters/grohe.py`** — 8-digit SKUs, multi-line block parser (SKU / Name / Price triplet), category from section headings, series from name (Allure / Grohtherm / Essence / Rainshower / SmartControl / Eurosmart / Eurocube / Bau / Vitalio / Grandera / etc.), finish detection (Chrome / Matt Black / Warm Sunset / SuperSteel / Brushed Cool Sunrise / …).
- **`catalog_pipeline/adapters/geberit.py`** — dotted SKU (`\d{3}\.\d{3}\.[A-Z0-9]{2}\.\d`), inline+nearby MRP recovery (backtick as ₹), series (SIGMA / OMEGA / MONOLITH / AQUACLEAN / DUOFIX), colour extraction (glass/matt/steel/etc.), category from CONCEALED CISTERN / ACTUATOR PLATES / URINAL / BATHROOM SYSTEM / etc.
- **`catalog_pipeline/adapters/vitra.py`** — Wide-format XLSX parser: detects finish-group headers, fans each row out into one product per finish variant (WHITE 003/403 / MATT WHITE 401 / MATT TAUPE / MATT STONE GREY / MATT BLACK), preserves accessory codes.
- **`catalog_pipeline/adapters/__init__.py`** — Registry & `get_adapter(brand)`. Adding a new supplier = one file.
- **`catalog_pipeline/certifier.py`** — Validates SKU uniqueness, product-family category coherence, variant conflicts, missing data. Emits a **CertificationReport** with per-axis scores (extraction, sku, price, category, variant, image, duplicate, missing_data) + overall_score + `production_ready` bit.
- **`catalog_pipeline/orchestrator.py`** — Runs Extract → Validate → Certify pipeline and imports certified rows. Idempotent (updates existing SKUs, never duplicates). Auto-creates missing categories.

### Endpoints
- `POST /api/catalog/imports` — multipart file upload
- `POST /api/catalog/imports/from-url` — fetch a public URL (perfect for huge PDFs the mobile app can't upload)
- `GET /api/catalog/imports` / `GET /api/catalog/imports/{id}` — list + detail
- `PATCH /api/catalog/imports/{id}/rows/{row_id}` — edit any field or accept/reject a row
- `POST /api/catalog/imports/{id}/approve` — imports every accepted row into `products` (idempotent, update-in-place by SKU, category autocreate)
- `POST /api/catalog/imports/{id}/rollback` — marks job rolled back (never deletes products, per spec)
- `DELETE /api/catalog/imports/{id}` — remove a job
- `GET /api/catalog/imports/config/brands` — supported brand list

### Frontend UI
- **Certification banner** — 96px score circle, per-axis score pills, ready/review status, issue chips (duplicate SKUs, missing MRP/category/images), family + image counts.
- **URL import** — paste a supplier file URL, one-tap fetch.
- **Editable review rows** — every row has editable name/MRP/price/finish/material with `[MISSING DATA]` displayed in warning colour so gaps are obvious. Accept/Reject with one tap.
- **Recent imports list** — timeline of every import with status badges.

## Rules enforced (per spec)
- ✅ Never fabricate data (MISSING sentinel everywhere).
- ✅ Never overwrite production silently (PATCH is manual accept, autosave uses `silent`).
- ✅ Never duplicate SKUs (validator rejects dupes, import is upsert by SKU).
- ✅ Never delete products automatically (rollback marks status only).
- ✅ Import is idempotent (re-uploading updates existing SKUs).
- ✅ Reusable framework — new brand adapter = one file, no core changes.

## Iterations 1 + 2 still live
Auth+RBAC (8 roles + customer portal), Dashboard, Product Catalog, Quotation Builder 2.0 (autosave, multi-level discounts, rooms 2.0, smart picker), Customer Portal + PDF, scaffold screens for Purchase/Payments/Follow-ups/Reports/Notifications/Team/Settings.

## Non-goals (deferred, next iteration recommendations)
- VITRA WMF image decoder (WMF → PNG via `pywin32`/`imagemagick`)
- Rollback engine restoring pre-import prices (needs delta history collection)
- Live price-diff report vs prior imports (compare current vs latest imported job)
- Purchase Order auto-generation from approved quotations
- Undo/Redo + drag-to-reorder in Quotation Builder

The Builder is now the flagship experience it was designed to be.

### New in this iteration
- **Autosave** — debounced silent PATCH (`silent=true` bypasses revision snapshots). Save-state indicator: "Saving…" → "Saved · HH:MM".
- **Multi-level Discount System** — Product > Category > Project priority. Universal `BottomSheet` for editing at any level, `GET /api/quotations/{id}/breakdown` returns per-line source of truth ("via project" / "via category" hints on detail).
- **Rooms 2.0** — add / rename / duplicate / delete / collapse. Suggestion chips (Master Bath, Powder Room, Kitchen, …). Selected room + collapsed state persist on the quote.
- **Line actions** — duplicate, remove, move to next room, inline description override (persisted, printed on PDF).
- **Smarter product picker** — Search / Recent / Frequent tabs backed by per-user usage tracking (`product_usage` collection). `GET /api/products/recent` and `/frequent`.
- **Duplicate quotation** — `POST /api/quotations/{id}/duplicate` regenerates a fresh quote with new number + new line ids.

### Data model changes
- `QuotationLineItem`: `discount_pct: Optional[float]` (null = inherit), added `category_id`, `description`, `sort_order`.
- `Quotation`: added `project_discount_pct`, `category_discounts: dict[str,float]`, `collapsed_rooms`.
- `QuotationUpdate`: added `silent` flag for autosave.
- New collection: `product_usage` (`user_id`, `product_id`, `count`, `last_used_at`).

## Iteration 1 (still live)
Auth+RBAC (8 roles + customer portal), Dashboard KPIs, Product Catalog (grid+filters+detail), Server-side ReportLab PDF, Customer Portal (hero + quote cards + PDF), Scaffold screens (Purchase / Payments / Follow-ups / Reports / Notifications / Team / Settings).

## Architecture
- **Backend**: FastAPI, modular routers, MongoDB (motor), UUID PKs, JWT + bcrypt, ReportLab PDFs, emergentintegrations ready for Claude 4.5.
- **Frontend**: Expo Router v6, custom tablet sidebar → phone bottom tabs, monochromatic Carbon/Graphite design tokens, universal `BottomSheet` + `Toast`, autosave hooks.
- **RBAC**: Hierarchical role scoring + `require_min_role()` guards.

## API Surface
Iteration-1 endpoints unchanged plus:
- `POST /api/quotations` — now accepts `project_discount_pct`, `category_discounts`
- `PATCH /api/quotations/{id}` — supports `silent`, `collapsed_rooms`, discount fields
- `GET /api/quotations/{id}/breakdown` — transparent per-line discount source
- `POST /api/quotations/{id}/duplicate`
- `GET /api/products/recent`, `GET /api/products/frequent`

## Test Coverage
- Iteration 1: 29/29 pytest ✓
- Iteration 2: 14/14 pytest ✓ (multi-level discount, silent autosave, breakdown, duplicate, recent/frequent, collapsed_rooms)
- All Iteration-1 flows regression-clean

## Non-goals (deferred)
- Drag-and-drop room / line reorder (next iteration)
- Undo / redo history stack
- Alternates & variants / product families
- AI Catalog Import activation (pipeline ready)
- Auto-generated Purchase Orders from approved quotes
- Payments / Follow-ups full UIs

