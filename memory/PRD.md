# Forge — Product Requirements

**Vision:** Premium ERP/CRM/POS for sanitaryware, bath fitting and building material distributors. Combines Linear+Stripe+Apple polish with showroom-grade simplicity.

## Iteration 1 — Delivered

### Fully implemented flagship experiences
1. **Authentication & RBAC** — JWT (bcrypt), 8 staff roles (owner/admin/manager/sales/purchase/warehouse/accounts/worker) + Customer Portal auth. Role-gated routes. Segmented login (Team vs Customer).
2. **Dashboard** — Role-agnostic KPIs (revenue MTD, open pipeline, quotes MTD, pending approvals), recent quotation activity, top products by revenue, follow-ups due, customer/product counts. Live data, pull-to-refresh.
3. **Product Catalog** — Search (name/SKU/tag), brand + category chip filters, responsive grid (4/2 cols), product detail with pricing, MRP strike-through, discount badge, spec table.
4. **Quotation Builder** — Tablet split-pane. Left: instant catalog search + tap-to-add. Right: line items grouped by Rooms, inline qty/rate/discount editing (monospace numeric inputs), live totals, sticky Save. Phone falls back to tabbed layout. Revision snapshots on update.
5. **Customer Portal** — Apple-order-portal hero, quotation cards with status, one-tap PDF download, contact-support CTA.
6. **Server-side PDF** — ReportLab-based professional quotation PDFs shared by both portals.

### Scaffolded (nav + models + APIs + empty screens)
- Purchase Orders, Payments, Follow-ups, Reports, Notifications, Team, Settings — every screen has real API, empty/loading/error states and "coming next" preview.

## Architecture
- **Backend**: FastAPI, modular routers (`/routes/*`), MongoDB (motor). All UUID PKs, no ObjectId leaks. JWT + bcrypt auth.
- **Frontend**: Expo Router v6, tablet-first custom sidebar → phone bottom tabs. Design tokens in `/src/theme/tokens.ts`. Auth context in `/src/state/auth.tsx`. API client in `/src/api/client.ts`.
- **PDF**: ReportLab (`/backend/pdf_generator.py`) — timeless minimal layout.
- **Catalog Import Pipeline**: Models ready (`CatalogImportJob`), API scaffold + LLM plumbing prepared for Claude Sonnet 4.5 via Emergent key (activated in next iteration).
- **RBAC**: Hierarchical role scoring + explicit `require_roles(...)` guards.

## Demo Data (seeded on first startup)
- 8 staff users (all roles), 4 customers, 7 brands (Kohler/Grohe/Duravit/TOTO/Jaquar/Hansgrohe/Roca), 7 categories, 16 products, 8 quotations across statuses, follow-ups & notifications.

## API Surface (v0.1)
- `POST /api/auth/login`, `GET /api/auth/me`
- `POST /api/auth/customer/login`, `GET /api/auth/customer/me`
- `GET /api/dashboard/stats`
- `GET /api/brands`, `GET /api/categories`
- `GET /api/products?q&brand_id&category_id&finish&limit&skip`, `GET /api/products/{id}`, `POST /api/products`
- `GET /api/customers`, `POST /api/customers`, `GET /api/customers/{id}`
- `GET/POST /api/quotations`, `GET/PATCH/DELETE /api/quotations/{id}`
- `GET /api/quotations/{id}/pdf` (staff), `GET /api/quotations/{id}/portal-pdf` (customer)
- `GET /api/portal/quotations` (customer portal)
- `GET /api/purchase-orders`, `/api/payments`, `/api/followups`, `/api/notifications`, `/api/team`, `/api/reports/overview`

## Non-goals (deferred)
- AI catalog extraction (models + pipeline in place, activation TBD)
- Full PO / Payments / Reports UI polish
- Offline sync (data models designed for it, not wired yet)
- Google OAuth (per user choice: JWT-only)
