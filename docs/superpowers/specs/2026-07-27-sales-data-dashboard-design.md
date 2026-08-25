# Sales Data Dashboard — Design

Date: 2026-07-27
Status: Approved (pending final spec review)

## Purpose

An owner/admin-only dashboard showing every completed sale (won quotation),
filterable by floor and by referrer (architect / interior designer), with a
separate brand-revenue view. Replaces nothing existing — this is a new page.

## Scope

In scope:
- Revenue totals and trends across Ground floor / The Sanitary Bathroom
  (first floor) / both combined.
- A "Referred By" filter for Architect and Interior Designer, each backed by
  a real directory of named people (not free text), with per-person revenue
  drill-down (day/month/quarter/year).
- A separate "By Brand" tab showing ranked brand revenue with per-brand
  drill-down.
- Owner + Admin access only.

Out of scope (explicitly deferred):
- Other referral sources (Walk-in, Instagram, etc.) staying individually
  tracked — they remain in the existing free-text `reference_source` field,
  uncategorized on this dashboard.
- Backfilling/migrating historical quotations' free-text "Architect" values
  into the new structured directory — this starts fresh from today.
- Floor and Referred-By filters affecting the By Brand tab (see below —
  only the date range carries over there).

## What counts as a sale

A quotation counts as revenue the moment `status == "won"`, using
`grand_total`. This matches the existing `/dashboard/stats` revenue
calculation exactly — no new definition of "sale" is introduced.

## Data model changes

### New `Referrer` model (new `referrers` collection)

```python
class Referrer(TimestampedModel):
    name: str
    type: Literal["architect", "interior_designer"]
    phone: Optional[str] = None
    company: Optional[str] = None
    created_by: str
```

Simple directory. No floor scoping — a referrer can send business to either
floor.

### `Quotation` additions

Three new optional fields, additive and backward-compatible:

```python
referrer_type: Optional[Literal["architect", "interior_designer"]] = None
referrer_id: Optional[str] = None
referrer_name: Optional[str] = None  # denormalized at write time
```

`reference_source` (existing free-text field: "Walk-in", "Instagram", etc.)
is untouched. These new fields are populated only when the salesperson
picks Architect or Interior Designer as the referred-by category.

`referrer_name` is denormalized (copied at the time the quotation is
saved) so a later rename/edit of the `Referrer` record doesn't rewrite
history — past quotations keep showing the name as it was when the sale
happened.

## Referrer capture flow

In the quotation builder, choosing "Architect" or "Interior Designer" as
Referred By opens a searchable picker over existing `Referrer` records of
that type, with an inline "+ Add new" (name + type only) if the person
isn't listed yet. No separate management step is required before a sales
rep can use a new referrer — the directory grows organically. A simple
directory list (name, type, phone/company if filled in) is viewable for
reference, editable later if more detail is wanted.

Any authenticated user who can build quotations can create/select a
referrer this way (same permission level as creating a quotation) — this
is a data-entry action, distinct from viewing the analytics dashboard,
which is owner/admin only.

## Backend

New `backend/routes/sales_data_routes.py`. Every endpoint is gated with the
existing `require_roles("owner", "admin")` dependency (`backend/auth.py`).

All aggregation reads from `db.quotations` filtered to `status == "won"`,
scoped with the existing `floor_query()` pattern where a floor filter
applies.

### `GET /sales-data/overview`

Params: `floor_id` (optional; omitted/`"both"` = all floors),
`referrer_type` (optional: `architect` | `interior_designer`),
`date_from`, `date_to`, `granularity` (`day` | `month` | `quarter` | `year`).

Returns:
- `total_revenue`
- `revenue_by_floor`: `[{floor_id, floor_name, revenue}]`
- `trend`: `[{bucket_label, revenue}]` bucketed by `granularity` over the
  date range
- `referrers` (only present when `referrer_type` is set): ranked
  `[{referrer_id, name, revenue}]` for that type, within the same filters

### `GET /sales-data/referrers/{referrer_id}`

Params: `date_from`, `date_to`, `granularity`.

Returns that person's own `trend` (same bucket shape as above) and their
list of won quotations (`number, customer_name, grand_total, updated_at`)
in the range.

### `GET /sales-data/brands`

Params: `date_from`, `date_to` only (no floor/referrer filters — see
Scope). Joins won quotations' line items → `products.brand_id` →
`brands.name` to produce ranked `[{brand_id, brand_name, revenue}]` within
the date range.

### `GET /sales-data/brands/{brand_id}`

Params: `date_from`, `date_to`, `granularity`. Returns that brand's `trend`
and its top products by revenue in the range.

## Frontend

New route: `frontend/app/(admin)/sales-data.tsx`. Nav entry added to
`frontend/app/(admin)/_layout.tsx` with `roles: ["owner", "admin"]`,
following the exact pattern already used for the `team` nav item — hidden
from every other role, both in the nav and if the URL is hit directly
(route itself checks role and redirects, same as other gated admin pages).

### Filter bar (applies to Overview tab; date range also applies to By Brand)

- **Floor**: Both / Ground floor / The Sanitary Bathroom — pulled from the
  real `/floors` list, not hardcoded labels.
- **Referred By**: All / Architect / Interior Designer.
- **Date range**: picker, defaults to "this month".
- **Granularity**: Day / Month / Quarter / Year toggle, controls trend
  chart bucketing.

### Tabs: Overview / By Brand

**Overview:**
- KPI cards + trend chart, scoped by the current filters. When Referred By
  is All: cards show Total / Ground floor / First floor revenue. When set
  to Architect or Interior Designer: cards re-scope in place (e.g.
  Architect Revenue / # Active / Avg Deal Size) — the layout position
  doesn't change, only the numbers, so switching the filter never
  restructures the page.
- When a referrer type is selected, a ranked list of people appears below
  the chart. Tapping a person opens their own detail screen: trend chart
  (respecting the granularity toggle) + their list of won quotations.

**By Brand** (independent of Floor/Referred-By, respects date range):
- Ranked list of brands by revenue.
- Tapping a brand opens its detail screen: trend chart + top products
  under that brand in the range.

## Error handling / edge cases

- No won quotations in range → KPIs show ₹0, trend chart and ranked lists
  render empty states, not errors.
- A referrer with zero revenue in the current range simply doesn't appear
  in the ranked list (it's a revenue ranking, not a full directory dump).
- Deleting/deactivating a `Referrer` record (not built now, but the model
  allows for it later via `TimestampedModel`) — out of scope for this
  spec; not needed for launch since referrers are only ever added, never
  removed, today.

## Testing

- Backend: unit tests for the aggregation logic in `sales_data_routes.py`
  (revenue bucketing by day/month/quarter/year, floor filter, referrer
  filter, brand join) using the existing test patterns in
  `backend/tests/unit`.
- Backend: role-gate test confirming non-owner/admin roles get rejected.
- Frontend: manual verification in the running app (this is a
  data-dashboard page, not logic-heavy — no new frontend unit tests
  planned beyond existing conventions).
