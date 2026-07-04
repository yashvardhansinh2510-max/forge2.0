# Forge — Product Requirements

**Vision:** Premium ERP/CRM/POS for sanitaryware, bath fitting and building material distributors. Combines Linear+Stripe+Apple polish with showroom-grade simplicity.

## Iteration 2 — Quotation Builder 2.0 (Delivered)

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

