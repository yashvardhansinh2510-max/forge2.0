# Milestone 4 — Sales Data MVP (Launch)

**Date:** 2026-08-02
**Status:** shipped
**Scope rule:** ship the launch dashboard as **Phase 1 of the complete Sales
Data architecture**, not as a replacement for it. Nothing deleted, nothing
hidden, nothing built twice.

---

## Objective

Give the owner one clean, reliable Sales Data page for launch, answering
eleven questions, built on the Phase 0 analytics foundation that already
exists.

`/sales-data` is the permanent entry point for the module. The Executive
pages stay in the codebase and keep evolving; no route was removed. Every
workspace on the roadmap keeps its place in the navigation and routes to a
real **Coming Soon** placeholder instead of an unmatched route, so a later
milestone adds a screen and flips one flag rather than forcing another
navigation redesign.

## What the page answers

| # | Question | Source |
|---|---|---|
| 1 | Total Revenue | `/analytics/overview` → `kpis.revenue` |
| 2 | Total Orders | `/analytics/overview` → `kpis.orders` |
| 3 | Outstanding Payments | `/analytics/overview` → `kpis.outstanding` |
| 4 | Revenue by Floor | `/analytics/overview` → `revenue_by_floor` |
| 5 | Revenue by Brand | **new** `/analytics/revenue-by-brand` |
| 6 | Revenue by Customer | **new** `/analytics/revenue-by-customer` |
| 7 | Referred By (Architects / Interior Designers) | `/analytics/referrers?type=` — Phase 0, unchanged |
| 8 | Best Selling Products | **new** `/analytics/best-selling-products` |
| 9 | Recent Orders | **new** `/analytics/recent-orders` |
| 10 | Date Filter | query params + **new** `/analytics/default-period` |
| 11 | Floor Filter | query params on every endpoint |

Six of eleven were already served by Phase 0 and are consumed as-is.

## Why four endpoints were added rather than reusing `/executive-analytics`

`/executive-analytics/dashboard` already returns brands, customers, products
and orders in one call. It was **not** reused, for one reason:

> It computes line revenue as `qty × unit_price`, which ignores the discount
> cascade. `/analytics/overview` computes Total Revenue from `grand_total`.

Putting both on one page would show the owner two different totals for the
same book. The new endpoints sum `items.net_amount` through the canonical
`metrics.line_revenue_pipeline`, which reconciles to `grand_total` by
construction.

**No new Mongo aggregation pipelines were written.** Brand and product
revenue go through the existing `line_revenue_pipeline`; customers and recent
orders fold in Python over a plain `find`, the convention
`gather_collections_orders` already established for doc-level rollups.

The four are shaped as independent, filterable, exportable resource endpoints
(`format=csv|xlsx`, cached via `cache.cached` with declared source
collections) rather than one page-shaped blob — because the Products, Brands
and Customers workspaces on the roadmap are these lists with more columns.

## Reconciliation — verified live

Against `buildcon_house`, July 2026, all units — Total Revenue **₹39,77,337**
across 35 confirmed orders:

| Breakdown | Sum |
|---|---|
| Revenue by Brand | ₹39,77,337 ✅ |
| Revenue by Customer | ₹39,77,337 ✅ |
| Best Selling Products | ₹39,77,337 ✅ |
| Recent Orders | ₹39,77,337 ✅ |
| Outstanding (orders vs KPI) | ₹38,32,023 = ₹38,32,023 ✅ |

### The "Unlinked products" bucket

10 of the 30 product ids on the live book's confirmed orders no longer
resolve to a catalog doc — **₹5,44,910, 13.7% of revenue**. Dropping them
would have made Revenue by Brand quietly total less than the KPI card above
it. They fold into an explicit `Unlinked products` row, badged *Unmatched*
and always sorted last: it is a data-quality note, not a brand.

## Smart default period

Live orders are all July 2026; the launch date is 2 August. A hardcoded
"this month" default would have opened the page to ₹0 on every card.

`periods.smart_default_period` (pure, unit-tested) resolves it server-side —
only the database knows whether the current month is empty, and the answer is
floor-dependent:

- Current month has confirmed orders → **This month**.
- Current month empty → the **calendar month of the most recent order**, with
  a banner saying so (`fallback_applied`).
- No orders ever → This month, **no banner** (claiming a fallback happened
  when there was nothing to fall back to would be false).

A calendar month, not a rolling 30 days: a rolling window silently changes
what every figure on the page means.

The owner's selection is persisted (`forge.sales-data.period`) and wins on
the next visit. A persisted choice is **never silently overridden** — if the
restored period turns out to be empty, the page offers a one-tap jump to the
period that has data instead of arguing with the user.

## Two live bugs found and fixed

1. **`_revenue_by_floor` hardcoded `["first-floor", "ground-floor"]`** for
   all-floor callers, silently omitting every other business unit from the
   owner's own Revenue by Floor breakdown. `second-floor` already exists in
   the live floors collection, so this was live and would have started losing
   real money the day that unit booked its first order. Now resolved from
   `db.floors`. Regression test asserts the literal never returns.

2. **The page contradicted itself.** `/analytics/overview` always reports
   every accessible floor in `revenue_by_floor` regardless of the floor
   filter — it is built as a cross-unit comparison. Rendered unfiltered under
   a single-unit KPI row, Total Revenue read 33.1 L while the breakdown below
   it summed to 39.8 L. The rows are now scoped to the active filter.

## Verification

- **Backend:** 832 unit tests pass (baseline 831 → +54 new, 1 pre-existing
  test extended). Floor scoping asserted structurally: every breakdown read
  goes through `build_match`, a restricted caller's every query carries a
  floor clause, an unrestricted caller's carries none, revenue is only ever
  counted from `status="ordered"`, dated by `ordered_at` never `updated_at`.
- **TypeScript:** `tsc --noEmit` clean.
- **Mongo:** live probe, reconciliation table above.
- **Browser:** all 11 requirements render; fallback banner, custom range,
  period persistence across reload, Coming Soon routing, and the Executive
  page still reachable and intact.
- **Responsive:** 375 / 768 / 1280 — no horizontal page overflow at any
  width. Table money switches to the compact form on phones, where the full
  `₹25,26,885` truncated to `₹25,26,…`.

## Known, not addressed here

- **No referral data exists.** `referrer_type` is null on every quotation and
  `db.referrers` is empty, so both Referred By workspaces render their empty
  state at launch. This is correct — referral data is never invented.
- **The live book contains test fixtures.** `TEST_LC4_*` and `Task19 *`
  records appear in Recent Orders and Revenue by Customer because they are
  genuinely confirmed orders in the database. Cleaning them is a data task,
  not a reporting one.
- `owner@forge.app` is still on the demo password (carried over, unrelated).
