# Sales Data → Executive Operating System — Design

**Date:** 2026-08-01
**Status:** Approved design, pending implementation plan
**Supersedes:** `2026-07-27-sales-data-dashboard-design.md` (that design's routes and
`sales_data_routes.py` are absorbed and retired by this one)

---

## 1. What this is

`Sales Data` becomes the owner's executive operating system: a multi-workspace
decision surface where every card answers one business question and nothing is a
dead-end statistic. It keeps its existing name, sidebar entry, and `/sales-data`
route hierarchy.

**Owner-first philosophy (binding on every implementation decision):**

- Every metric answers exactly one business question.
- Every table leads somewhere. Every chart is clickable. Every KPI explains itself.
- Every insight tells the owner what action to take.
- No decorative charts. Operational intelligence over visual density.
- If a widget cannot influence a business decision, it is removed — not shrunk.

---

## 2. Scope decisions

### 2.1 In scope

Eight workspaces under one shared analytics layer, one filter system, one chart
system, one drill-down graph.

### 2.2 Explicitly dropped (approved 2026-08-01)

| Dropped | Reason |
|---|---|
| Profit, Gross Margin | No cost price exists on products or quotation lines. `unit_cost` lives only on `PurchaseOrderItem`, and 30 of 36 POs are still `draft`. Cannot be computed honestly. |
| Most-profitable products, Brand profit contribution | Same root cause. |
| Stock levels, "stock running out", Brand inventory turnover | `Product.stock` is `0` on all 3,529 products — the field is not maintained. |

**Replacement for the stock questions:** sales velocity computed from order line
history — fastest selling, slow moving, zero sales. Same business question, real data.

If costing later becomes a decided business process, `metrics.py` is where profit
would be added; no workspace redesign would be required.

### 2.3 Live data reality at design time (`buildcon_house`, 2026-08-01)

Recorded so later sessions do not mistake empty cards for bugs.

| Collection | Count | Note |
|---|---|---|
| `quotations` | 78 | 35 `ordered` (₹39,77,337), 33 `draft`, 5 `sent`, 2 `approved`, 2 `won` |
| order history span | 2026-07-01 → 2026-07-31 | **one month only** — no prior period exists |
| `customers` | 122 | |
| `walkins` | 110 | span 2026-07-30 → 07-31, 106 still `new` |
| `payments` | 31 | 8 `completed`, 23 `pending`; ₹21,87,744 total |
| `followups` | 232 | 143 `open`, 87 `done`, 2 `dismissed` |
| `customer_orders` | 13 | 6 ground / 7 first |
| `ready_batches` / `dispatches` / `chalans` | 20 / 25 / 25 | |
| `purchase_orders` | 36 | item stages: 33 `order_in_company`, 3 `company_billing`, 2 `dispatched`, 1 `in_box` |
| `brands` / `suppliers` / `products` | 8 / 7 / 3,529 | |
| `referrers` | **0** | |
| quotations with a referrer | **0 of 78** | `referrer_type`, `referrer_id`, `referrer_name` are all `None` on every document |

---

## 3. Correctness fixes (prerequisite — Phase 1, before any workspace)

These are pre-existing defects. Every number in every workspace depends on them.

### 3.1 `ordered_at`

`routes/quotation_routes.py:897` flips status to `ordered` and stamps only
`updated_at`. Every later edit re-stamps it, so editing an old order silently
moves its revenue into the current period.

- Add `ordered_at: Optional[str]` to `Quotation`, stamped once at the `ordered`
  transition, never rewritten.
- Migration backfills `ordered_at = updated_at` for the 35 existing ordered
  quotations (best available approximation; documented as such).
- **Every revenue calculation in the system dates by `ordered_at`.**
  `updated_at` is never used for business reporting again.

### 3.2 `items.net_amount`

`executive_analytics_routes.py:111-112` computes line revenue as
`qty × unit_price`, ignoring `discount_pct` and the room/category/project discount
cascade. Brand revenue therefore does not sum to total revenue — two answers to
one question.

- `services/pricing.py::per_line_net_amounts()` already owns the canonical cascade
  (Product override > Room > Category > Project). It is the only pricing engine.
- Denormalize its result to `items.net_amount` at write time inside
  `recalc_quotation_totals()`. Migration backfills existing documents.
- Every product / brand / category / room aggregation sums `items.net_amount`.

Guaranteed by construction, not by convention:

```
Product Revenue = Brand Revenue = Category Revenue = Quotation Revenue
```

### 3.3 Analytics indexes

No index on `quotations` supports any analytics access pattern today.

| Collection | Index |
|---|---|
| `quotations` | `{status, floor_id, ordered_at}`, `{floor_id, created_at}`, `{referrer_id, status}`, `{customer_id, status}`, `{items.product_id}` |
| `payments` | `{quotation_id, status}`, `{floor_id, paid_at}` |
| `walkins` | `{floor_id, created_at}` |
| `followups` | `{floor_id, status, due_at}` |
| `customer_orders` | `{floor_id, overall_status, created_at}` |
| `dispatches` | `{floor_id, dispatch_date}`, `{customer_order_id}` |

Added via the existing forward-only migration runner. Per the documented gotcha,
every `create_index` call tolerates MongoDB error code 85 (same keys, different
existing name).

---

## 4. Backend architecture — `backend/services/analytics/`

Approach B: one canonical package, readable modular pipelines, a narrow registry
for headline KPIs. No declarative abstraction hiding the aggregations. No
materialized rollups.

```
backend/services/analytics/
  filters.py    AnalyticsFilter dataclass + build_match() — the ONLY match builder
  periods.py    period resolution, previous period, MoM/QoQ/YoY, history_state
  metrics.py    narrow registry: one implementation per headline KPI
  cache.py      Redis-or-memory, version-keyed automatic invalidation

  revenue.py    products.py   brands.py     customers.py
  referrals.py  operations.py trends.py     forecast.py    attention.py
```

Routes (`routes/executive_analytics_routes.py`, rewritten) stay thin — parse query,
build one `AnalyticsFilter`, call a service, return.

### 4.1 `filters.py`

One `AnalyticsFilter` carries: floor, date preset/custom range, brand, category,
supplier, salesperson, referrer type + id, customer, status. `build_match()` is the
single place a Mongo match document is constructed for analytics.

Floor access is enforced through the existing `accessible_floor_ids(user)`. An
explicit floor outside the caller's access is a `403`.

**Floor semantics:** the Sales Data floor filter offers **All Floors** and
aggregates both units while preserving per-floor breakdowns. This is deliberately
distinct from the shell's operational active-floor switcher (where "All floors" was
removed on 2026-07-31 so a concrete floor is always active). Sales Data is a
role-gated report scope (`owner`, `admin`, `manager`), not an operational context.

### 4.2 `periods.py`

Resolves presets and custom ranges; computes the comparison window for
previous-period, MoM, QoQ, YoY. Returns a `history_state` alongside every
comparison:

| State | Meaning | UI |
|---|---|---|
| `ok` | Prior window has data | Show delta, arrow, sparkline |
| `no_prior_period` | Prior window exists but is empty | "No previous period available." |
| `insufficient_history` | Not enough history for this comparison (e.g. YoY with 1 month) | "Historical comparison available after more business history is collected." |

Never `+100%`. Never `0%`. Never a fabricated value. The engine is complete now and
starts producing real comparisons the moment history accumulates — no future code
change required.

### 4.3 `metrics.py` — canonical KPI definitions

Each of these has exactly one implementation. No workspace may redefine one.

| KPI | Definition |
|---|---|
| Revenue | Σ `grand_total` where `status = ordered`, dated by `ordered_at` |
| Orders | Count of the same set |
| Average Order Value | Revenue ÷ Orders |
| Outstanding Amount | Σ ordered `grand_total` − Σ `payments.amount` where `status = completed`. The 23 `pending` payments are *recorded, not received* — they are never counted as collected |
| Conversion | Per funnel stage, each numerator and denominator named explicitly in the funnel definition (§7) |
| Referral Revenue | Revenue grouped by `referrer_id` + `referrer_type` |
| Brand Revenue | Σ `items.net_amount` joined product → brand |
| Product Revenue | Σ `items.net_amount` grouped by `items.product_id` |
| Customer Lifetime Value | Lifetime Σ ordered `grand_total` grouped by `customer_id` |

### 4.4 `cache.py` — version-keyed automatic invalidation

Redis when `REDIS_URL` is set, in-process fallback otherwise — the same optional
pattern already proven in `services/rate_limit.py`. Only expensive aggregate
results are cached; cheap lookups are not.

**Invalidation is automatic and requires no manual clearing, ever.** Each source
collection has a version counter. Every metric declares which collections it reads.
The cache key embeds those versions:

```
analytics:{metric_id}:q{quotations_v}:p{payments_v}:c{customers_v}:d{dispatches_v}
         :r{ready_batches_v}:f{followups_v}:{filter_hash}:{accessible_floor_set}
```

A write to any of these bumps its counter (`INCR`), which changes the key, which
makes every dependent cached entry unreachable at once. No explicit deletes, no
invalidation bugs from a missed path. Bump points, wired into the existing
`services/domain_outbox.py` write paths:

- quotation created / edited / **status changed** / referrer changed
- payment recorded / status changed
- customer created / edited
- dispatch created / delivered
- ready batch (release) created / consumed
- follow-up created / completed / dismissed

**The accessible floor set is part of the key.** Omitting it would serve one user's
floor-scoped rows to another.

---

## 5. Referral analytics architecture

### 5.1 Single source of truth

Reporting reads only:

```
Quotation.referrer_type   ("architect" | "interior_designer")
Quotation.referrer_id
Quotation.referrer_name   (denormalized snapshot at write time)
```

No architect table. No interior designer table. No separate referral tables. No
duplicated metrics anywhere. Editing a quotation's Referred By updates every
dashboard automatically, because every dashboard aggregates that field directly.

`Referrer` remains a **name and contact directory only** — it stores zero metrics.
Its existing model already matches the required shape exactly:

```python
class Referrer(TimestampedModel):
    name: str
    type: ReferrerType          # "architect" | "interior_designer"
    phone: Optional[str]
    company: Optional[str]
    created_by: str
```

### 5.2 Shared Referred By component in both builders

Today only the Sanitary (standard) builder exposes Referred By
(`BuilderTopbar.tsx` → `ReferrerSwitcherSheet.tsx`). `TilesDocBuilder.tsx` has no
such field, so Ground Floor quotations structurally cannot carry a referral — which
makes floor-split referral analytics impossible.

- Extract the existing sheet into one shared `ReferredByField` component.
- Both the Ground Floor tiles builder and the Sanitary builder render the **exact
  same component**, with the same Architect / Interior Designer type selection.
- Both search the same shared Referrer directory.
- Creating a referrer from either workflow makes it immediately available in the
  other. One directory, one type field, no duplicates.

### 5.3 Empty-state onboarding

Zero of 78 quotations carry a referrer today, so referral workspaces start empty.
They must never show a bare "no data" or a zero.

> **Unlock referral intelligence**
> Start capturing referral information in quotations to unlock Architect and
> Interior Designer performance insights.
> `[ Open Referrer Directory ]`

A premium onboarding state with a working CTA into the Referrer directory.

---

## 6. Drill-down graph (the navigation contract)

Nothing is a dead-end statistic. Every KPI, every chart segment, and every table
row is a node with a defined destination. Filter context (floor, date range, active
filters) is carried through every hop via URL query params, so any drill-down state
is shareable and back-navigable.

**Canonical paths:**

```
Revenue → Floor → Brand → Product → Order (Quotation) → Customer
Brand → Products → Orders → Customers
Architect / Interior Designer → Customers → Quotations → Revenue → Order detail
Salesperson → Walk-ins / Quotations → Order → Customer
Customer → Orders → Products → Brands
Operations row → the operational screen that resolves it
```

**Terminal nodes are existing operational screens** — the executive system hands
off to the app rather than dead-ending:

| Destination | Route |
|---|---|
| Quotation / order detail | `/(admin)/quotations/[id]` |
| Customer profile | `/(admin)/customers/[id]` |
| Tile order detail | `/(admin)/tiles/orders/...` |
| Payments | `/(admin)/payments` |
| Follow-ups | `/(admin)/followups` |
| Purchases | `/(admin)/purchases` |

Every table is sortable, filterable, searchable, sticky-headed, paginated, and
exportable to CSV / Excel / PDF.

---

## 7. Executive Intelligence Blueprint

Every workspace, every KPI, its MongoDB source, its aggregation, its drill-down,
and the owner question it answers. Implementation may not add a card that is not on
this table without adding it here first.

Shorthand: `Q` = `quotations`, `ORD` = `Q where status=ordered` dated by `ordered_at`,
`NET` = `Σ items.net_amount`.

### Workspace 1 — Executive Overview (`/sales-data`, `/sales-data/executive`)

| Card | Source | Aggregation | Drill-down | Owner question |
|---|---|---|---|---|
| Revenue | `ORD` | `Σ grand_total` + prior-period compare + sparkline | Revenue by Floor | How much revenue did we generate? Ahead or behind? |
| Orders | `ORD` | `count` + compare | Order list | How many orders did we close? |
| Average Order | `ORD` | Revenue ÷ Orders + compare | Order list sorted by value | Are deals getting bigger or smaller? |
| Outstanding Payments | `ORD`, `payments` | Σ ordered − Σ completed payments | Payments workspace | How much money is owed to us? |
| Pending Quotations | `Q status ∈ {draft,sent,approved}` | count + Σ value + max age | Quotation list sorted by age × value | How much revenue is sitting undecided? |
| Pending Dispatches | `customer_orders`, `dispatches` | orders with undispatched boxes | Operations → Dispatch | Which customers are waiting? |
| Pending Releases | Ground Floor: `ready_batches`. Sanitary: `purchase_orders.items.stage` (one card, two floor-specific sources — see Workspace 7) | lines/boxes not yet released | Operations → Release | What material is stuck before dispatch? |
| Pending Follow-ups | `followups status=open` | count, overdue count, Σ `value` | Follow-ups | Who has not been contacted? |
| **Attention Center** | multiple | §8 | each row to its own resolution screen | What is today's biggest business risk? |
| Revenue trend | `ORD` | bucket by day/week/month/quarter/year | Sales Performance | Where is the business heading? |
| Revenue by Floor | `ORD` | group `floor_id` | Floor-filtered overview | Which floor is winning? |
| Top 5 movers | brands, products, referrers, salespeople | rank + rank movement vs prior period | respective workspace | Who and what is driving the month? |

### Workspace 2 — Sales Performance (`/sales-data/sales`)

| Card | Source | Aggregation | Drill-down | Owner question |
|---|---|---|---|---|
| Revenue by day / week / month / quarter / year | `ORD` | `$dateToString` bucket on `ordered_at` | period → order list | How is revenue trending? |
| Revenue by Salesperson | `ORD` | group `created_by`, + orders, AOV, growth, rank movement | salesperson profile | Which salesperson generated the most revenue? |
| Salesperson conversion | `walkins`, `Q`, `ORD` | orders ÷ walk-ins handled | walk-in list | Who converts, who only collects footfall? |
| Salesperson activity | `walkins`, `Q`, `followups` | last activity timestamp per person | that person's queue | Who has gone quiet? |
| Sales funnel | see below | see below | each stage to its queue | Where is the biggest bottleneck? |
| Revenue by Category | `ORD` unwound | `NET` grouped by `items.category_id` | Products filtered by category | Which categories carry the business? |

**Funnel stage definitions** (each denominator explicit):

| Stage | Source | Count |
|---|---|---|
| Walk-ins | `walkins` `is_deleted=false` | count in period |
| Selections | `Q doc_type=tiles_selection` | count in period |
| Quotations | `Q doc_type ∈ {standard, tiles_quotation}`, status ∉ {rejected, lost} | count in period |
| Approved | `Q status=approved` | count in period |
| Confirmed Orders | `ORD` | count in period |
| Release | `ready_batches` / PO item stage | released lines |
| Dispatch | `dispatches` | dispatched |
| Payments | `payments status=completed` | collected |

Each stage reports conversion from stage 1, drop-off from the previous stage, median
time in stage, and revenue lost at the drop.

### Workspace 3 — Referrals (`/sales-data/referrals`, `/architects`, `/interior-designers`)

Both sub-workspaces are the same component, filtered by `referrer_type`.

| Card | Source | Aggregation | Drill-down | Owner question |
|---|---|---|---|---|
| Total Customers Referred | `Q` | distinct `customer_id` by `referrer_id` | customer list | How much business does this partner send? |
| Total / Approved / Confirmed Quotations | `Q` | count by status by `referrer_id` | quotation list | How much of it is real? |
| Revenue Generated | `ORD` | `Σ grand_total` by `referrer_id` | order list | Which architect generated the most revenue? |
| Average Order Value | `ORD` | revenue ÷ orders | order list | Which partner brings premium customers? |
| Conversion Rate | `Q`, `ORD` | ordered ÷ total quotations | quotation list | Which partner converts best? |
| Pending Quotations | `Q status ∈ {draft,sent,approved}` | count + Σ value | quotation list | What is still open with this partner? |
| Pending Payments | `ORD`, `payments` | outstanding by referrer | payments | Which partner's customers owe money? |
| First / Last Referral Date | `Q` | `$min` / `$max` `created_at` | timeline | When did they start, when did they stop? |
| Active / Inactive | `Q` | last referral vs inactivity threshold | partner profile | Which architect has stopped referring? |
| Repeat Customers | `Q` | customers with ≥2 referred quotations | customer list | Are their clients coming back? |
| Monthly Revenue / Revenue Trend | `ORD` | bucket by `ordered_at` | period order list | Is this partner growing or fading? |
| Brand Preference | `ORD` unwound | `NET` by brand for that referrer | brand workspace | What do their clients buy? |
| Product Preference | `ORD` unwound | `NET` by product | product profile | Which products do they specify? |
| Floor Split | `ORD` | group `floor_id` | floor-filtered view | Ground Floor or Sanitary? |

**Partner profile** (drill target): Summary · Revenue · Customers · Timeline · All
Quotations · Orders · Payments · Brands Purchased · Products Purchased · Recent
Activity · Conversion Funnel.

### Workspace 4 — Products (`/sales-data/products`)

| Card | Source | Aggregation | Drill-down | Owner question |
|---|---|---|---|---|
| Revenue by Product | `ORD` unwound | `NET` by `items.product_id` | product profile → customer list | Which products generate the most revenue? |
| Units sold | `ORD` unwound | `Σ items.qty` | order list | What actually moves? |
| Average selling price | `ORD` unwound | `NET ÷ qty` | order list | Are we discounting this product away? |
| Customers per product | `ORD` unwound | distinct `customer_id` | customer list | Broad appeal or one big buyer? |
| Growth | `ORD` unwound | vs prior period, with `history_state` | period comparison | Which products are rising? |
| Fastest selling | `ORD` unwound | units ÷ days on sale | product profile | What should we stock deeper? |
| Slow moving | `ORD` unwound | sold, but below velocity threshold | product profile | What is tying up attention? |
| Zero sales | `products` LEFT JOIN `ORD` | products with no ordered line ever | product profile | Which products never sell? |
| Frequently bought together | `ORD` | product pair co-occurrence within an order | product profile | What should we cross-sell? |

### Workspace 5 — Brands (`/sales-data/brands`)

| Card | Source | Aggregation | Drill-down | Owner question |
|---|---|---|---|---|
| Brand Revenue | `ORD` unwound | `NET` by product → `brand_id` | brand profile → products | Which brands carry us? |
| Brand Growth / Decline | `ORD` unwound | vs prior period + rank movement | period comparison | Which brands are growing? Which are dying? |
| Brand Average Order | `ORD` | revenue ÷ orders containing the brand | order list | Which brands anchor big deals? |
| Brand Conversion | `Q`, `ORD` | ordered ÷ quoted, per brand | quotation list | Which brands get quoted but not bought? |
| Brand Pending Orders | `purchase_orders` | open POs by brand + value | Purchases | What is on order and not here? |
| Brand Dispatch Delay | `customer_orders`, `dispatches` | median order → dispatch days by brand | Operations | Which brands make customers wait? |
| Supplier strength | `suppliers`, `purchase_orders`, `dispatches` | fulfilment rate + median lead time | supplier profile | Which suppliers are strongest? |

### Workspace 6 — Customers (`/sales-data/customers`)

| Card | Source | Aggregation | Drill-down | Owner question |
|---|---|---|---|---|
| Top Customers | `ORD` | `Σ grand_total` by `customer_id` | customer profile | Which customers spend the most? |
| Lifetime Value | `ORD` all-time | lifetime revenue, orders, first/last order | customer profile | Who is genuinely valuable? |
| Repeat Rate | `ORD` | customers with ≥2 orders ÷ all ordering customers | customer list | Do they come back? |
| Average Order | `ORD` | per-customer AOV | order list | Who buys big? |
| Inactive Customers | `ORD` | last order older than threshold | customer profile + follow-up CTA | Which customers disappeared? |
| Likely to reorder | `ORD` | order cadence vs time since last order | customer profile + follow-up CTA | Who should we call today? |
| Largest Pending Customers | `Q` open, `ORD`, `payments` | open quotation value + outstanding | quotation / payments | Where is the biggest open money? |
| Referred by | `Q` | referrer attribution per customer | partner profile | Which partner sent this customer? |

### Workspace 7 — Operations (`/sales-data/operations`)

Sorted by business impact (₹ at stake × age), never alphabetically.

| Card | Source | Aggregation | Drill-down | Owner question |
|---|---|---|---|---|
| Pending Releases | Ground Floor: `ready_batches` box counters. Sanitary: `purchase_orders.items.stage` not yet past release | unreleased lines/boxes, value, age | Ground Floor → Tile Orders release queue; Sanitary → Purchases | What is blocked before dispatch? |
| Pending Dispatches | `customer_orders`, `dispatches` | ready-not-dispatched boxes, value, age | Dispatch list | Which customers are waiting? |
| Pending Payments / Overdue | `ORD`, `payments` | outstanding by order, days since order | Payments | Which payments are overdue? |
| Pending Purchases | `purchase_orders status=draft` | count + value stuck in draft | Purchases | What did we forget to order? |
| Pending Follow-ups | `followups status=open` | overdue count, Σ `value`, priority | Follow-ups | Who is falling through? |
| Stuck Quotations | `Q status ∈ {draft,sent,approved}` | age + value, ranked by value × age | Quotation detail | Which quotations are stuck? |
| Delayed Suppliers | `purchase_orders` | overdue vs `expected_delivery_at` | supplier profile | Which suppliers are late? |
| Late Deliveries | `dispatches` | dispatched not delivered, age | Dispatch record | What has not landed? |
| Where money is blocked | all of the above | total ₹ by blockage category | each category | Where is money getting blocked? |

### Workspace 8 — Forecasting & Historical Trends (`/sales-data/forecasting`)

Every card here degrades to `insufficient_history` until enough periods exist.

| Card | Source | Aggregation | Drill-down | Owner question |
|---|---|---|---|---|
| Historical revenue by period | `ORD` | full history bucketed | period order list | What does our history look like? |
| MoM / QoQ / YoY | `ORD` | `periods.py` comparisons | period comparison | Are we growing year over year? |
| Run-rate projection | `ORD` | period-to-date ÷ elapsed × period length | current period orders | Where will we land this month? |
| Pipeline-weighted forecast | `Q` open, historical conversion | open value × stage conversion rate | quotation list | What is realistically coming? |
| Seasonality | `ORD` | revenue by month-of-year across years | that month's orders | When are our strong months? |
| Best/worst period | `ORD` | ranked periods | period order list | What was our best month ever? |

---

## 8. Attention Center

Only problems. Never a "you're doing great" card. Each rule produces a row with a ₹
business impact, an age, and a one-click destination that resolves it. Rows are
ranked by impact, and the section is empty (with a calm confirmation) when nothing
is wrong.

| Rule | Trigger | Impact | Destination |
|---|---|---|---|
| High-value quotation stalled | open quotation, age > threshold | quotation value | quotation detail |
| Payment overdue | outstanding, days since order > terms | outstanding amount | payments |
| Customer waiting dispatch | ready, undispatched, age > threshold | order value | dispatch list |
| Material stuck before release | PO line unreleased, age > threshold | line value | release queue |
| Follow-up overdue | `due_at < now`, `status=open` | followup `value` | follow-ups |
| Salesperson inactive | no walk-in/quotation/follow-up in N days | their open pipeline value | their queue |
| Supplier delay | PO past `expected_delivery_at` | PO value | supplier / purchases |
| Brand decline | brand revenue down > X% vs prior period | revenue delta | brand profile |
| Referral partner gone quiet | last referral > N days | their historical monthly revenue | partner profile |

Rules whose comparison window has no history report `insufficient_history` and are
suppressed rather than fired on a fabricated delta.

**Thresholds live in one `attention.py` constant block**, never scattered across
rules. Starting values, tunable in that one place:

| Constant | Value |
|---|---|
| `QUOTATION_STALE_DAYS` | 7 |
| `QUOTATION_HIGH_VALUE` | ₹1,00,000 |
| `PAYMENT_OVERDUE_DAYS` | 30 from `ordered_at` (no payment-terms field exists yet; when one is added, it takes precedence) |
| `DISPATCH_WAITING_DAYS` | 3 from ready |
| `RELEASE_STUCK_DAYS` | 5 |
| `SALESPERSON_INACTIVE_DAYS` | 5 |
| `SUPPLIER_DELAY_DAYS` | 0 past `expected_delivery_at` |
| `BRAND_DECLINE_PCT` | 25% vs prior period |
| `REFERRER_QUIET_DAYS` | 60 |
| `CUSTOMER_INACTIVE_DAYS` | 180 |

---

## 9. Frontend architecture

### 9.1 Routes

```
/sales-data                              → Executive Overview
/sales-data/executive                    → Executive Overview
/sales-data/sales                        → Sales Performance
/sales-data/referrals                    → Referral summary (both types)
/sales-data/referrals/architects
/sales-data/referrals/interior-designers
/sales-data/products
/sales-data/brands
/sales-data/customers
/sales-data/operations
/sales-data/forecasting
```

Sidebar keeps the single entry **Sales Data**. A workspace switcher lives inside.
Existing `/sales-data/*` deep links keep working; legacy screens and
`sales_data_routes.py` are removed only after the replacing phase is verified
feature-for-feature.

### 9.2 Shared shell — `src/components/analytics/`

| Component | Role |
|---|---|
| `WorkspaceSwitcher` | the eight workspaces, active state, keyboard navigable |
| `FilterBar` | sticky. Floor · Date · Brand · Category · Supplier · Salesperson · Architect · Interior Designer · Customer · Status. One implementation, every workspace |
| `KpiRow` | sticky KPI strip |
| `KpiCard` | value, comparison, delta, sparkline, self-explaining tooltip, click → drill-down |
| `DataTable` | promoted from `src/components/tiles/TileTable.tsx` — reuses its hard-won RN-Web fixes. Sort, filter, search, sticky header, pagination, row click-through, CSV/Excel/PDF export |
| `ExportMenu` | CSV · Excel · PDF, via the existing `openApiFile` blob helper |
| `AttentionList` | ranked problem rows with impact and destination |
| `StateViews` | loading · empty · no-data · `no_prior_period` · `insufficient_history` · referral onboarding |

**Filter state lives in URL query params** so every drill-down is shareable,
bookmarkable, and back-navigable with context intact.

### 9.3 BuildCon chart kit — `src/components/charts/`

New dependency: **`react-native-svg`** (`expo install`, works web + iOS + Android).
No third-party charting library — the visual language stays ours.

Components: `Sparkline` · `LineChart` · `AreaChart` · `BarChart` · `HorizontalBar` ·
`StackedBar` · `Donut` · `FunnelChart` · `Heatmap` · `TrendIndicator` ·
`ComparisonOverlay`.

Every chart shares one `ChartFrame` providing: design tokens (no local colours),
responsive sizing, hover (web) and touch (mobile), tooltips, click-through to the
drill-down graph, loading / empty / no-data states, and accessibility labels.
Adding a chart type must not require changing the frame.

### 9.4 Visual system

Warm white. High typography. Large whitespace. 12-column responsive grid, 8px
spacing system, 32px section spacing, 24px card padding, 16px row padding. Sticky
filters and sticky KPI row. Desktop first; tablet and mobile responsive at the
app's existing `useBp()` breakpoints (768 / 1024).

Known RN-Web traps to respect (all previously cost this codebase real time):
`adjustsFontSizeToFit` is a no-op on web — use `moneyShort`/compact formatters in
tiles; a `flexDirection` override on phone must carry the matching `alignItems`; a
horizontal `ScrollView` shrink-wraps to max-content; `position:sticky` needs the
rows in an inner vertical `ScrollView`; sticky-top and sticky-right are mutually
exclusive; use `isNearScrollEnd` for any new infinite list.

---

## 10. Phasing

Each phase is fully functional and verified before the next begins.

| Phase | Contents |
|---|---|
| **0** | Correctness fixes: `ordered_at`, `items.net_amount`, index migration, `services/analytics/` skeleton (`filters`, `periods`, `metrics`, `cache`), chart kit foundation |
| **1** | Executive Overview + Attention Center |
| **2** | Sales Performance; Referral Analytics + shared `ReferredByField` in both builders |
| **3** | Products; Brands |
| **4** | Customers |
| **5** | Operations, Bottlenecks, Pending Revenue |
| **6** | Forecasting & Historical Trends; legacy `sales_data_routes.py` and old screens removed |

Phase 0 is not optional and not deferrable — Phase 1's numbers are wrong without it.

**Implementation plans are written per phase, not one plan for all seven.** This
document is the architecture that keeps them coherent; each phase gets its own plan
written against it, and no phase's plan may introduce an aggregation, KPI, or
drill-down path that is not in the Blueprint (§7) without amending this document
first.

## 11. Verification protocol (every phase)

1. Every KPI cross-checked against a direct Mongo query, value for value.
2. Every aggregation reconciles: product = brand = category = quotation revenue.
3. Every filter verified, including the three-way floor probe (no header /
   `first-floor` / `ground-floor`) that catches ambient-state leaks the UI hides.
4. Every drill-down path opens the right record with filter context preserved.
5. Every export (CSV / Excel / PDF) opens and matches the on-screen data.
6. Responsive pass at 1280 / 768 / 375.
7. No placeholder components. No empty cards. No fabricated values.
8. Backend unit tests for every new service module.
9. Fix, re-verify, and only then proceed.

## 12. Risks and open items

- **Referral workspaces stay empty until the field is used.** The build is correct
  and the onboarding state is honest, but the owner sees no partner numbers until
  quotations start carrying a Referred By. Worth a deliberate rollout conversation.
- **One month of history** means most comparison cards ship in
  `insufficient_history` and become useful as data accumulates. Expected, designed
  for, not a defect.
- **Walk-in data is two days old** (110 records, 106 `new`), so funnel conversion
  will read near zero until walk-ins age through the pipeline.
- **`customer_orders` uses `overall_status`**, not `status` — a naive `status`
  query returns `None` for all 13 documents.
- The shared backend on `:8010` does not auto-reload and may be in use by another
  session; confirm before restarting.
