# BuildCon House (formerly Forge) — Product Requirements

**Vision:** Premium ERP/CRM/POS for sanitaryware, bath fitting and building material distributors. Combines Linear+Stripe+Apple polish with showroom-grade simplicity.

**Brand:** BuildCon House · Tagline: *"Let you live better"* · Renamed from Forge in Feb 2026.

## Iteration 5 — Follow-ups V2: Sales Command Center Redesign (Feb 2026, DELIVERED)

Built on top of Follow-ups V1 (deterministic Priority Score + Next Best Action + idempotent reconciliation engine — no LLM, no cron, tested 100% previously). This iteration closed a live-screenshot UX audit (`/app/memory/followups_ux_audit_and_redesign.md`) approved by the user.

**Backend (`followup_routes.py`, `quotation_routes.py`, `payment_routes.py`, `purchases_tracker.py`, `models.py`):**
- Event-triggered reconciliation — `asyncio.create_task(reconcile_followups())` fired after quotation status change, quotation→order confirm, payment recorded, and purchase item stage move to dispatched/in_transit/delivered. Removes the "nobody opened the workspace" freshness lag WITHOUT reintroducing a cron job.
- No-answer call escalation — 2nd consecutive `no_answer` outcome skips the same-day 4h retry, schedules for tomorrow 09:30, and bumps `priority_score` +10 (capped 100).
- `GET /followups/stats` — added `overdue_payments_count/amount`, `expiring_quotations_count` (previously blended into one generic "Overdue" number).
- `GET /followups/{id}` detail `stats` — added `conversion_rate`, `average_order_value`, `preferred_salesperson`, `risk_level` (low/medium/high) — all deterministic, derived from existing quotations/payments.
- `GET /followups/export?format=xlsx|csv` — styled Excel (openpyxl) or CSV, respects all list filters.
- `/followups/saved-views` — full CRUD, per-user scoped persisted filter configs. New model `FollowupSavedView`.

**Frontend (`app/(admin)/followups.tsx`):**
- Auto-selects the #1 priority open card on load (desktop) — Context Panel is never an empty placeholder.
- Filter panel progressive disclosure — Priority + search always visible, Type/Tier/Owner behind "More filters".
- KPI strip split into 6 tiles including dedicated "Payments Overdue" (₹) and "Expiring Soon".
- Card redesign — 4px left-edge priority color bar, bulk-select checkbox, rank chip (#1/#2/#3), dedicated ₹ value chip, promoted Snooze/Assign icon-menu buttons (new local `IconMenuButton`).
- Bulk Action Bar (Snooze/Assign/Complete/Clear) on multi-select.
- Context Panel enriched with Conversion Rate, Avg. Order Value, Risk Level badge, Preferred Salesperson.
- Keyboard Shortcuts help sheet (`?` key / icon) — makes pre-existing shortcuts discoverable.
- Saved Views sheet (save/apply/delete) and real Export (xlsx/csv download) — no longer stubbed.
- `PRIORITY_TONE.medium` moved off brand-blue to neutral gray (was diluting brand/action color meaning).

**Bug found + fixed during testing:** `PageHeader` (`ui.tsx`) had no `position:relative`/`zIndex`, so any `Dropdown` menu placed in its `actions` slot rendered behind later ScrollView content — fixed with `zIndex:20` on the header container. This is a shared DS primitive fix, benefits every page using `PageHeader` + `Dropdown` together.

**Testing:** Backend 17/17 new tests pass (event-triggered reconcile verified via polling without manual reconcile call, escalation math exact, export/saved-views verified). Frontend ~95%→100% after the PageHeader z-index fix. Full regression on V1 endpoints/UI clean.



Full rebuild of the mobile & tablet design language before adding any more features:

- **Renamed** Forge → BuildCon House across all user-facing surfaces (login, dashboard, sidebar, customer portal, settings, catalog import).
- **Tokens** — semantic color roles (blue `#2563EB` primary + porcelain gray neutrals), 8pt spacing scale, 6-step radius, 5-level elevation, motion tokens, Inter Variable typography (Regular/Medium/SemiBold/Bold loaded via expo-font).
- **Primitives** rebuilt from scratch in `/src/components/ui.tsx`: Button (6 variants), IconButton (6 tones + badge), Card (flat/elevated/outlined), Badge, StatusBadge, Chip (with count), Tabs, SegmentedControl, TextField, SearchField, KpiCard, ListRow, Avatar, PriceTag, BrandMark, Alert, EmptyState, ErrorState, LoadingState, Skeleton, SectionHeader, ScreenTitle, Divider.
- **Shell** — new admin `_layout` with tablet sidebar (blue-tinted active items, BuildCon brand + tagline) and phone bottom-nav featuring a **center floating action button** for New Quotation.
- **Screens migrated** to the DS: Login (two-pane premium hero), Dashboard (4-col KPI grid, avatar-lead activity, side-by-side content), Quotations list (premium card design with number pill + avatar + status), Quotation Detail (hero + mobile line-item cards with indexed pill, tabular table on tablet), Customers (tier chips with counts, filter chips), Notifications (typed badges, unread dots), Settings (profile hero + iconed sections), Team, ScaffoldScreen. Payments, Purchases, Catalog and the Quotation Builder inherit the tokens directly.
- **Global Inter default** — `Text.defaultProps.style` set to `{ fontFamily: font.regular }` in `app/_layout.tsx` so every Text element without an explicit fontFamily renders Inter automatically (including legacy inline styles). Individual weights still opt-in via `type.*` tokens.
- **Quality bar** — Linear/Stripe/Notion/Arc — whitespace over borders, subtle elevation, no hardcoded colors anywhere below the tokens layer.

## Iteration 2 — Catalog Rebuild (in progress)

Delivered in three approval-gated phases:

- **2A · Foundation (DELIVERED, awaiting approval).** MediaStorage abstraction (SupabaseStorageDriver), `product_media` collection, migration of all 250 VITRA images to Supabase, ranked search + facets, family-first backend endpoint, MongoDB text/hierarchy indexes, reusable import framework helpers (`framework.py`), `SupplierManifest` pattern, orchestrator writes to Supabase, zero base64 blobs in product docs. Certification: `/app/memory/iteration_2a_certification.md`. Migration report: `/app/memory/media_migration_20260704_202102.json`.
- **2B · Premium Catalog UI (queued).** Family-first URLs, Shopify-style family page, hierarchical browse, rich cards, visual variant picker, sticky filters, virtualization, animations, skeleton shimmer.
- **2C · Cross-app polish (queued).** Quotation Builder browses by hierarchy, customer portal parity, product comparison, Complete-the-Set engine, admin media manager, catalog QA dashboard.

Brand import order (only after 2A/2B/2C are all approved): VITRA (already imported, will re-certify) → GROHE → GEBERIT → HANSGROHE → AXOR. Approval pause after each brand.

## Iteration 3 — Catalog Import & Certification System (Delivered in prior fork)

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


## Persistence & Disaster Recovery migration (2026-07-07, DELIVERED)

Root cause fully diagnosed (see `/app/memory/persistence_audit_2026-07-07.md`): every new
session/fork provisions a brand-new pod/volume seeded only from GitHub. Local MongoDB
(`mongod` inside the container) and `.env` (correctly gitignored) never survive that —
every session was a total data loss with a full demo re-seed on top.

**Migrated to permanent infrastructure:**
- `MONGO_URL` now points at a MongoDB **Atlas** M0 cluster (`cluster0.vmc0rmr.mongodb.net`) —
  no more local Mongo for real data. `backend/db.py` needed zero code changes.
- `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_ANON_KEY` wired for project
  `vburaxruvbnbahegtbya` (buckets `forge-products` public / `forge-private` private —
  both pre-existed from a prior session's migration and were reachable).
- `backend/.env.example` + `frontend/.env.example` committed (safe templates).
- `GET /api/health/system` (no auth, never leaks secret values) — mongo/supabase
  reachability, `is_local` flag, live collection counts, secrets-loaded booleans,
  actionable `warnings[]`.
- `backend/scripts/backup_db.py` / `restore_db.py` / `pull_backup_from_supabase.py` — JSON
  snapshot backup that now ALSO pushes to the Supabase private bucket (`backups/<ts>/*.json`)
  so the disaster-recovery point itself survives a session reset, not just local disk.
- **Critical data-safety fix in `backend/seed.py`**: `resync_catalog_if_needed()` used to
  wipe products/brands/categories back to demo data on ANY startup where the brand-name set
  didn't exactly match the 5 demo brands (a near-certainty after a real import, e.g. Axor
  folding into Hansgrohe). Added a guard — if any product exists without a `demo` tag, this
  function now returns immediately and never touches the catalog. `seed_if_empty()` now also
  checks `products` is empty (not just `users`) before seeding. Implements the user's explicit
  requirement: "products > 0 → skip seed; database empty → run seed."

**Catalog recovery — investigated before rebuilding, per explicit instruction:**
Found the original GROHE/GEBERIT/VITRA supplier files still live on Emergent's persistent
`customer-assets.emergentagent.com` storage (referenced by URL in
`backend/scripts/run_catalog_imports.py`, verified reachable, downloaded, re-ran the existing
production pipeline against Atlas). Result: **1,610 real products restored (0 demo)** —
Grohe 864, Geberit 496 (+9 SKU updates), Vitra 250 — with 1,612 `product_media` docs pointing
at live, verified-reachable Supabase image URLs (HTTP 200 confirmed on a sample).
**Hansgrohe + AXOR (1,272 products, 14 source XLSX files) were NOT recoverable** — no
persistent URL, not in git history, not in `backend/temp/`, not in this run's attached
assets. Per user's explicit instruction: left empty, not fabricated, documented here and in
the audit report — to be recovered only if/when the original files resurface.

**Verified post-restore (Priority 4):** product/brand/category counts match exactly, per-brand
`product_count` correct on `/api/brands` and `/api/categories`, a sample Supabase image URL
returns HTTP 200 with real bytes, `/api/products?q=mixer` search returns 364 relevant results,
category/brand filters return correctly-scoped counts. Backup taken immediately after
(Priority 5) and confirmed pulled-back successfully from Supabase.

**Total ledger (for when Hansgrohe/AXOR resurface):** 2,872 products = Vitra 250 + Grohe 854
+ Geberit 496 (per original tally) + Hansgrohe 826 + AXOR 446. Current live count: 1,610.

## Hansgrohe/AXOR recovery — Batch 1 of 3 (2026-07-07)

User re-uploaded 5 of the 14 original Hansgrohe files (3hole, BM, Ceramic, handshower, HFAV —
via customer-assets.emergentagent.com, since only 5 can attach per message). Delivered per the
user's "Forge Catalog Recovery" master prompt:
- **AXOR kept as a genuinely separate brand** (was previously folded into Hansgrohe by business
  rule) — `catalog_pipeline/orchestrator.py::import_accepted` now resolves brand PER ROW
  (`collection == "AXOR"` -> Axor brand; else the job's supplier brand), case-insensitive lookup
  to avoid duplicate brand docs.
- **Categories = supplier filename verbatim** (not invented) — `hansgrohe.py::FILE_TO_CATEGORY`
  now maps confirmed filenames to readable labels (BM, Ceramic, Three Hole Mixers, Hand Showers)
  and falls back to the literal stem for anything unconfirmed (HFAV).
- New `backend/scripts/run_hansgrohe_batch.py` — batch-aware importer that tracks progress in
  `/app/memory/hansgrohe_import_manifest.json` so future batches (2 of 3, 3 of 3) never
  reprocess a completed file and always report accurate "remaining files".
- Result: **364 new products** (261 Hansgrohe + 103 AXOR), 17 categories, 0 missing images,
  0 true duplicate SKUs.

**CRITICAL BUG FOUND + FIXED DURING THIS BATCH**: `import_accepted`'s existing-product lookup
was global on `sku` alone (`{"sku": sku}`), not scoped by brand. 3 Hansgrohe/AXOR article
numbers coincidentally collided with pre-existing Grohe SKUs (cross-manufacturer numeric code
collision), which caused those 3 Grohe products to be **silently overwritten** with
Hansgrohe/AXOR data. Detected by diffing every product against the pre-batch Supabase-backed
JSON snapshot (brand_id mismatches). Fixed:
- `import_accepted` now looks up `{"sku": sku, "brand_id": row_brand["id"]}` — SKU uniqueness is
  scoped per-brand, matching how real-world manufacturer article numbers actually work.
- Repaired all 3 corrupted docs: restored the original Grohe data from the pre-batch backup,
  and created 3 new distinct product docs (2 Hansgrohe, 1 AXOR) carrying the data that had been
  clobbered, re-pointing their already-uploaded Supabase image (`product_media`) docs to the new
  product IDs instead of re-uploading. Verified 0 remaining diffs against the backup, images
  reachable (HTTP 200) at their new product IDs.
- Took a fresh backup immediately after repair (`backend/backups/20260707_031204/`, also pushed
  to the Supabase private bucket).

**Current totals: 1,974 products** — Grohe 864, Geberit 496, Vitra 250, Hansgrohe 261, AXOR 103.
**Remaining Hansgrohe files (batch 2/3 candidates):** Holder, Thermostat, WBM, TBM, Single_lever,
Spout, Showerhose, kitchen, SHOWERS_HANSGROHE.

User directive: restrained premium aesthetic (Apple philosophy, not style). Warm off-white canvas,
near-black ink type, brass accent used ONLY for: primary CTA, focus, active nav, selected state, progress.
Headings: Fraunces serif; everything else Inter. Priority: Quotation Builder 70% / Purchases 20% / Quotation List 10%.

Done in this session (UI only, zero business-logic changes):
- Fixed corrupted Inter TTFs in /app/frontend/assets/fonts (were HTML error pages → real fonts from @expo-google-fonts CDN)
- Recreated missing /app/backend/.env (MONGO_URL, DB_NAME=buildcon_house, JWT_SECRET) and /app/frontend/.env after fork; reinstalled reportlab/openpyxl
- Shared primitives (ui.tsx): StatusBadge → calm dot+word (statusTone/toneColor), Chip selected → brass tint, PageHeader title → Fraunces serif
- Builder: BrandRail zinc-dark → warm light rail w/ brass active bars + serif wordmark; RecentQuotationsPanel light;
  ProductExplorer badges warm (Popular=brass) + ink prices + brass fav heart; LineRow sunken qty/rate cells, Inter tabular,
  brass focused state; RoomHeaderRow section band w/ brass active bar; RoomChipRow + CustomerBar + VariantChip brass selected;
  BuilderFooter + MobileControls brass primary CTA, refined totals; QuotationPane serif document number; ProductModal ink price
- Purchases: serif page title, local STAGE_TONE map (dot+word badges), all Tailwind hexes → Showroom tokens, brass rail markers
- Quotations list: removed blue number pill, brass New CTA, refined row typography
