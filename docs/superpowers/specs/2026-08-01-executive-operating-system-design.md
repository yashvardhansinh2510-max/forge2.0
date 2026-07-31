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

- Every metric answers exactly one business question, and says which one.
- Every table leads somewhere. Every chart is clickable. Every KPI explains itself.
- Every insight tells the owner what action to take.
- Problems and opportunities are both first-class. Attention says what is breaking;
  Opportunity says where to grow.
- Owners think in money, not counts. Operational cards lead with ₹ at stake.
- No decorative charts. Operational intelligence over visual density.
- If a widget cannot influence a business decision, it is removed — not shrunk.

---

## 2. Scope decisions

### 2.1 Explicitly dropped (approved 2026-08-01)

| Dropped | Reason |
|---|---|
| Profit, Gross Margin | No cost price exists on products or quotation lines. `unit_cost` lives only on `PurchaseOrderItem`, and 30 of 36 POs are still `draft`. Cannot be computed honestly. |
| Most-profitable products, Brand profit contribution | Same root cause. |
| Stock levels, "stock running out", Brand inventory turnover | `Product.stock` is `0` on all 3,529 products — the field is not maintained. |

**Replacement for the stock questions:** sales velocity computed from order line
history — fastest selling, slow moving, zero sales. Same business question, real data.

If costing later becomes a decided business process, `metrics.py` is where profit
would be added; no workspace redesign would be required.

### 2.2 Live data reality at design time (`buildcon_house`, 2026-08-01)

Recorded so later sessions do not mistake empty cards for bugs.

| Collection | Count | Note |
|---|---|---|
| `quotations` | 78 | 35 `ordered` (₹39,77,337), 33 `draft`, 5 `sent`, 2 `approved`, 2 `won` |
| order history span | 2026-07-01 → 2026-07-31 | **one month only** — no prior period exists |
| `customers` | 122 | |
| `walkins` | 110 | span 2026-07-30 → 07-31, 106 still `new` |
| `payments` | 31 | 8 `completed`, 23 `pending`; ₹21,87,744 total |
| `followups` | 232 | 143 `open`, 87 `done`, 2 `dismissed` |
| `customer_orders` | 13 | 6 ground / 7 first. Status field is `overall_status`, not `status` |
| `ready_batches` / `dispatches` / `chalans` | 20 / 25 / 25 | |
| `purchase_orders` | 36 | item stages: 33 `order_in_company`, 3 `company_billing`, 2 `dispatched`, 1 `in_box` |
| `activity_events` | 2,413 | `entity_type`, `event_type`, `customer_id`, `quotation_id`, `summary` — backs the relationship timeline |
| `brands` / `suppliers` / `products` | 8 / 7 / 3,529 | |
| `referrers` | **0** | |
| quotations with a referrer | **0 of 78** | `referrer_type`, `referrer_id`, `referrer_name` are all `None` on every document |

---

## 3. Correctness fixes (prerequisite — Phase 0, before any workspace)

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
| `walkins` | `{floor_id, created_at}`, `{customer_id}` |
| `followups` | `{floor_id, status, due_at}` |
| `customer_orders` | `{floor_id, overall_status, created_at}` |
| `dispatches` | `{floor_id, dispatch_date}`, `{customer_order_id}` |
| `activity_events` | `{customer_id, created_at}`, `{quotation_id, created_at}` |

Added via the existing forward-only migration runner. Per the documented gotcha,
every `create_index` call tolerates MongoDB error code 85 (same keys, different
existing name).

### 3.4 Owner targets

The Business Health Score (§8) and several comparisons need something to measure
against. Rather than invent a benchmark, the owner declares one.

New `settings` document (the collection is already key-addressed, 4 docs today)
with key `analytics_targets`:

| Target | Default |
|---|---|
| `monthly_revenue_target` | unset |
| `target_conversion_pct` | unset |
| `target_collection_pct` | 90 |
| `payment_terms_days` | 30 |

Edited in Settings. Unset targets are **excluded from the score**, which then
reports how many signals it is based on. No invented benchmarks, ever.

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

  revenue.py     products.py    brands.py      customers.py
  referrals.py   operations.py  trends.py      forecast.py
  attention.py   opportunity.py health.py      brief.py
  timeline.py    search.py
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
previous-period, MoM, QoQ, YoY. Presets include **Yesterday · Today · This Week**
so the owner's daily rhythm is one tap, not a custom range.

Returns a `history_state` alongside every comparison:

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
| Conversion | Per funnel stage, each numerator and denominator named explicitly in the funnel definition (§7, Workspace 2) |
| Referral Revenue | Revenue grouped by `referrer_id` + `referrer_type` |
| Brand Revenue | Σ `items.net_amount` joined product → brand |
| Product Revenue | Σ `items.net_amount` grouped by `items.product_id` |
| Customer Lifetime Value | Lifetime Σ ordered `grand_total` grouped by `customer_id` |
| Money Blocked | Σ value of everything awaiting release, dispatch, or payment (§7, Workspace 7) |

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
Health Score → component → the workspace that resolves it
Attention / Opportunity row → the screen that acts on it
Operations row → the screen that unblocks the money
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

**Every KPI card renders its question.** The question text below is not
documentation — it ships on the card, in small type, under the value.

### Workspace 1 — Executive Overview (`/sales-data`, `/sales-data/executive`)

| Card | Source | Aggregation | Drill-down | Owner question (shown on card) |
|---|---|---|---|---|
| **Business Health Score** | §8 | weighted component score, 0-100 | expands to every component | "How healthy is the business right now?" |
| **Morning Brief** | §11 | deterministic digest of yesterday | each line to its record | "What happened yesterday and what do I do today?" |
| Revenue | `ORD` | `Σ grand_total` + compare + sparkline | Revenue by Floor | "Are we making more money?" |
| Orders | `ORD` | `count` + compare | order list | "How many deals did we close?" |
| Average Order | `ORD` | Revenue ÷ Orders + compare | order list by value | "Are deals getting bigger or smaller?" |
| Outstanding Payments | `ORD`, `payments` | Σ ordered − Σ completed | Payments | "How much money is owed to us?" |
| Money Blocked | §7 W7 | Σ ₹ awaiting release + dispatch + payment | Operations | "Where is money getting blocked?" |
| Pending Quotations | `Q status ∈ {draft,sent,approved}` | count + Σ value + max age | quotations by age × value | "How much revenue is sitting undecided?" |
| Pending Follow-ups | `followups status=open` | count, overdue, Σ `value` | Follow-ups | "Who has not been contacted?" |
| **Attention Center** | §9 | ranked problems | each row to its fix | "What is today's biggest risk?" |
| **Opportunity Center** | §10 | ranked openings | each row to its action | "Where should we grow?" |
| Revenue trend | `ORD` | bucket by day/week/month/quarter/year | Sales Performance | "Where is the business heading?" |
| Revenue by Floor | `ORD` | group `floor_id` | floor-filtered overview | "Which floor is winning?" |
| Top 5 movers | brands, products, referrers, salespeople | rank + rank movement vs prior | respective workspace | "Who and what is driving the month?" |

### Workspace 2 — Performance (`/sales-data/sales`)

| Card | Source | Aggregation | Drill-down | Owner question |
|---|---|---|---|---|
| Revenue by day / week / month / quarter / year | `ORD` | bucket on `ordered_at` | period → order list | "How is revenue trending?" |
| Revenue by Salesperson | `ORD` | group `created_by` + orders, AOV, growth, rank movement | salesperson profile | "Which salesperson generated the most revenue?" |
| Salesperson conversion | `walkins`, `Q`, `ORD` | orders ÷ walk-ins handled | walk-in list | "Who converts, who only collects footfall?" |
| Salesperson activity | `walkins`, `Q`, `followups` | last activity per person | that person's queue | "Who has gone quiet?" |
| Sales funnel | below | below | each stage to its queue | "Where is the biggest bottleneck?" |
| Revenue by Category | `ORD` unwound | `NET` by `items.category_id` | Products filtered | "Which categories carry the business?" |

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
| Total Customers Referred | `Q` | distinct `customer_id` by `referrer_id` | customer list | "How much business does this partner send?" |
| Total / Approved / Confirmed Quotations | `Q` | count by status by `referrer_id` | quotation list | "How much of it is real?" |
| Revenue Generated | `ORD` | `Σ grand_total` by `referrer_id` | order list | "Which architect generated the most revenue?" |
| Average Order Value | `ORD` | revenue ÷ orders | order list | "Which partner brings premium customers?" |
| Conversion Rate | `Q`, `ORD` | ordered ÷ total quotations | quotation list | "Which partner converts best?" |
| Pending Quotations | `Q` open | count + Σ value | quotation list | "What is still open with this partner?" |
| Pending Payments | `ORD`, `payments` | outstanding by referrer | payments | "Which partner's customers owe money?" |
| First / Last Referral Date | `Q` | `$min` / `$max` `created_at` | timeline | "When did they start, when did they stop?" |
| Active / Inactive | `Q` | last referral vs `REFERRER_QUIET_DAYS` | partner profile | "Which architect has stopped referring?" |
| Repeat Customers | `Q` | customers with ≥2 referred quotations | customer list | "Are their clients coming back?" |
| Monthly Revenue / Trend | `ORD` | bucket by `ordered_at` | period order list | "Is this partner growing or fading?" |
| Brand Preference | `ORD` unwound | `NET` by brand for that referrer | brand profile | "What do their clients buy?" |
| Product Preference | `ORD` unwound | `NET` by product | product profile | "Which products do they specify?" |
| Floor Split | `ORD` | group `floor_id` | floor-filtered view | "Ground Floor or Sanitary?" |

**Partner profile — a mini CRM, not a table row.** Header carries name, type, firm,
phone, lifetime revenue, customers, orders, average order, and active/quiet status.
Body sections: Summary · Revenue trend · Customers · **Relationship timeline**
(§13) · All Quotations · Orders · Payments · Preferred Brands · Products
Purchased · Most Recent Project · Recent Activity · Conversion Funnel.

### Workspace 4 — Products (`/sales-data/products`)

| Card | Source | Aggregation | Drill-down | Owner question |
|---|---|---|---|---|
| Revenue by Product | `ORD` unwound | `NET` by `items.product_id` | product profile → customers | "Which products generate the most revenue?" |
| Units sold | `ORD` unwound | `Σ items.qty` | order list | "What actually moves?" |
| Average selling price | `ORD` unwound | `NET ÷ qty` | order list | "Are we discounting this away?" |
| Average discount | `ORD` unwound | 1 − (`NET` ÷ (`qty × mrp`)) where `mrp` exists | order list | "How much margin are we giving up?" |
| Customers per product | `ORD` unwound | distinct `customer_id` | customer list | "Broad appeal or one big buyer?" |
| Growth | `ORD` unwound | vs prior period + `history_state` | period comparison | "Which products are rising?" |
| Fastest selling | `ORD` unwound | units ÷ days on sale | product profile | "What should we stock deeper?" |
| Slow moving | `ORD` unwound | sold, below velocity threshold | product profile | "What is tying up attention?" |
| Zero sales | `products` LEFT JOIN `ORD` | products with no ordered line ever | product profile | "Which products never sell?" |
| Frequently bought together | `ORD` | product pair co-occurrence per order | product profile | "What should we cross-sell?" |

### Workspace 5 — Brands (`/sales-data/brands`)

Brand intelligence is supplier-negotiation data, not a revenue list.

| Card | Source | Aggregation | Drill-down | Owner question |
|---|---|---|---|---|
| Brand Revenue | `ORD` unwound | `NET` by product → `brand_id` | brand profile | "Which brands carry us?" |
| Orders | `ORD` | orders containing the brand | order list | "How often do we sell it?" |
| Customers | `ORD` | distinct customers per brand | customer list | "How many buyers does it have?" |
| Average Ticket | `ORD` | brand revenue ÷ brand orders | order list | "Does this brand anchor big deals?" |
| Average Discount | `ORD` unwound | 1 − (`NET` ÷ (`qty × mrp`)) | order list | "What are we conceding to sell it?" |
| Repeat Customers | `ORD` | customers with ≥2 brand orders | customer list | "Does it earn loyalty?" |
| Preferred by Architects | `ORD` | brand `NET` where `referrer_type=architect` | partner list | "Which brands do architects specify?" |
| Preferred by Interior Designers | `ORD` | brand `NET` where `referrer_type=interior_designer` | partner list | "Which brands do designers specify?" |
| Popular Floors | `ORD` | brand `NET` by `floor_id` | floor view | "Which unit sells it?" |
| Popular Categories | `ORD` unwound | brand `NET` by category | Products | "What sells inside this brand?" |
| Fastest / Slowest Products | `ORD` unwound | velocity within brand | product profile | "What should we reorder or drop?" |
| Brand Growth / Decline | `ORD` unwound | vs prior + rank movement | period comparison | "Which brands are growing? Which are dying?" |
| Brand Conversion | `Q`, `ORD` | ordered ÷ quoted per brand | quotation list | "Which brands get quoted but not bought?" |
| Brand Pending Orders | `purchase_orders` | open POs by brand + value | Purchases | "What is on order and not here?" |
| Brand Dispatch Delay | `customer_orders`, `dispatches` | median order → dispatch days | Operations | "Which brands make customers wait?" |
| Supplier strength | `suppliers`, `purchase_orders`, `dispatches` | fulfilment rate + median lead time | supplier profile | "Which suppliers are strongest?" |

The architect/designer preference rows show the referral onboarding state (§5.3)
until Referred By is in use.

### Workspace 6 — Customers (`/sales-data/customers`)

| Card | Source | Aggregation | Drill-down | Owner question |
|---|---|---|---|---|
| **Heat Score** | §12 | Hot / Warm / Cold / Lost band + signals | customer profile | "Who is worth calling today?" |
| Top Customers | `ORD` | `Σ grand_total` by `customer_id` | customer profile | "Which customers spend the most?" |
| Lifetime Value | `ORD` all-time | revenue, orders, first/last order | customer profile | "Who is genuinely valuable?" |
| Repeat Rate | `ORD` | customers ≥2 orders ÷ ordering customers | customer list | "Do they come back?" |
| Average Order | `ORD` | per-customer AOV | order list | "Who buys big?" |
| **Relationship timeline** | §13 | walk-in → payment journey | each stage to its record | "Where is this relationship stuck?" |
| Inactive Customers | `ORD` | last order > `CUSTOMER_INACTIVE_DAYS` | profile + follow-up CTA | "Which customers disappeared?" |
| Likely to reorder | `ORD` | order cadence vs time since last | profile + follow-up CTA | "Who should we call today?" |
| Largest Pending Customers | `Q` open, `ORD`, `payments` | open value + outstanding | quotations / payments | "Where is the biggest open money?" |
| Referred by | `Q` | referrer attribution per customer | partner profile | "Which partner sent this customer?" |

### Workspace 7 — Operations (`/sales-data/operations`)

**Money first.** The workspace headline is ₹ blocked, broken down by cause. Counts
are secondary detail, never the headline. Sorted by business impact (₹ × age).

| Card | Source | Aggregation | Drill-down | Owner question |
|---|---|---|---|---|
| **Money Blocked (total)** | all below | Σ ₹ across every blocked stage | the largest contributor | "Where is money getting blocked?" |
| Waiting Release | Ground Floor: `ready_batches`. Sanitary: `purchase_orders.items.stage` not past release | Σ ₹ unreleased + age | Tile release queue / Purchases | "What is stuck before dispatch?" |
| Waiting Dispatch | `customer_orders`, `dispatches` | Σ ₹ ready-not-dispatched + age | Dispatch list | "Which customers are waiting?" |
| Waiting Payment | `ORD`, `payments` | Σ ₹ outstanding, overdue split out | Payments | "Which payments are overdue?" |
| Pending Purchases | `purchase_orders status=draft` | Σ ₹ stuck in draft | Purchases | "What did we forget to order?" |
| Stuck Quotations | `Q` open | Σ ₹ by age band, ranked value × age | quotation detail | "Which quotations are stuck?" |
| Pending Follow-ups | `followups status=open` | Σ `value` at stake, overdue count | Follow-ups | "Who is falling through?" |
| Delayed Suppliers | `purchase_orders` | Σ ₹ past `expected_delivery_at` | supplier profile | "Which suppliers are late?" |
| Late Deliveries | `dispatches` | Σ ₹ dispatched not delivered + age | Dispatch record | "What has not landed?" |

### Workspace 8 — Forecasting & Historical Trends (`/sales-data/forecasting`)

Every card here degrades to `insufficient_history` until enough periods exist.

| Card | Source | Aggregation | Drill-down | Owner question |
|---|---|---|---|---|
| Historical revenue by period | `ORD` | full history bucketed | period order list | "What does our history look like?" |
| MoM / QoQ / YoY | `ORD` | `periods.py` comparisons | period comparison | "Are we growing year over year?" |
| Run-rate projection | `ORD` | period-to-date ÷ elapsed × period length | current period orders | "Where will we land this month?" |
| Pipeline-weighted forecast | `Q` open, historical conversion | open value × stage conversion | quotation list | "What is realistically coming?" |
| Seasonality | `ORD` | revenue by month-of-year across years | that month's orders | "When are our strong months?" |
| Best / worst period | `ORD` | ranked periods | period order list | "What was our best month ever?" |

---

## 8. Business Health Score

The first thing the owner sees. One number, a band, and a direction — so ten KPIs
don't have to be interpreted before breakfast.

```
Business Health
92 / 100 · Healthy
↑ Better than last month
Based on 6 of 7 signals
```

**It is a weighted operational score, not a model.** Every component is a bounded
0-100 value produced by a stated rule. Tapping the score expands to show every
component, its raw value, its rule, its weight, and a link to the workspace that
would improve it. Nothing about it is opaque.

| Component | Rule | Weight | Needs a target? |
|---|---|---|---|
| Collection health | collected ÷ ordered revenue in period | 20 | No |
| Overdue money | 1 − (overdue outstanding ÷ total outstanding) | 10 | No |
| Pipeline health | share of open quotation **value** newer than `QUOTATION_STALE_DAYS` | 15 | No |
| Dispatch health | share of ready material dispatched within `DISPATCH_WAITING_DAYS` | 10 | No |
| Follow-up health | share of open follow-ups not overdue | 10 | No |
| Revenue attainment | revenue ÷ `monthly_revenue_target`, capped at 100 | 25 | **Yes** |
| Conversion health | conversion ÷ `target_conversion_pct`, capped at 100 | 10 | **Yes** |

**Weights renormalize over available components.** If no revenue target is set, the
remaining components are rescaled to 100 and the card states *"Based on 6 of 7
signals — set a revenue target to include revenue attainment"*, linking to Settings.
A score is never computed from an invented benchmark.

Bands: **85+ Healthy · 70–84 Watch · below 70 At risk.**

The "↑ Better than last month" line uses `periods.py` and degrades to
`insufficient_history` — with one month of data it will not render a direction.

---

## 9. Attention Center

Only problems. Never a "you're doing great" card. Each rule produces a row with a ₹
business impact, an age, and a one-click destination that resolves it. Rows are
ranked by impact, and the section shows a calm confirmation when nothing is wrong.

| Rule | Trigger | Impact | Destination |
|---|---|---|---|
| High-value quotation stalled | open quotation, age > threshold | quotation value | quotation detail |
| Payment overdue | outstanding, days since order > `payment_terms_days` | outstanding amount | payments |
| Customer waiting dispatch | ready, undispatched, age > threshold | order value | dispatch list |
| Material stuck before release | unreleased line, age > threshold | line value | release queue |
| Follow-up overdue | `due_at < now`, `status=open` | followup `value` | follow-ups |
| Salesperson inactive | no walk-in / quotation / follow-up in N days | their open pipeline value | their queue |
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
| `PAYMENT_OVERDUE_DAYS` | from `settings.analytics_targets.payment_terms_days`, default 30 |
| `DISPATCH_WAITING_DAYS` | 3 from ready |
| `RELEASE_STUCK_DAYS` | 5 |
| `SALESPERSON_INACTIVE_DAYS` | 5 |
| `SUPPLIER_DELAY_DAYS` | 0 past `expected_delivery_at` |
| `BRAND_DECLINE_PCT` | 25% vs prior period |
| `REFERRER_QUIET_DAYS` | 60 |
| `CUSTOMER_INACTIVE_DAYS` | 180 |

Opportunity rules (§10) draw from the same block:

| Constant | Value |
|---|---|
| `BRAND_GROWTH_PCT` | 25% vs prior period |
| `PARTNER_UNTOUCHED_DAYS` | 14 since last follow-up on an open quotation |
| `APPROVED_NOT_ORDERED_DAYS` | 3 |
| `WALKIN_UNQUOTED_DAYS` | 14 |

---

## 10. Opportunity Center

The mirror of Attention. Problems say what is broken; opportunities say where to
grow. Same row shape — a headline, the ₹ upside, and a one-click action.

| Rule | Trigger | Upside shown | Action |
|---|---|---|---|
| Partner with untouched pipeline | referrer has open quotations and no follow-up in N days | Σ open quotation value | partner profile → log follow-up |
| Fast-growing brand | brand growth > `BRAND_GROWTH_PCT` vs prior period | revenue delta | brand profile → "consider stocking deeper" |
| Customer likely to reorder | order cadence due, no open quotation | historical average order | customer profile → create quotation |
| High-intent walk-in not quoted | walk-in with `interested_products`, no quotation, age < 14d | budget or interest value | walk-in → start quotation |
| Approved quotation not ordered | `status=approved`, no order, age > 3d | quotation value | quotation detail → place order |
| Repeat-buyer cross-sell | frequently-bought-together product the customer has never bought | that product's average line value | product profile → add to quotation |
| Top customer gone quiet | high-LTV customer past `CUSTOMER_INACTIVE_DAYS` | lifetime average order | customer profile → log follow-up |
| Best salesperson underloaded | highest-conversion salesperson with fewest open quotations | their average order × capacity gap | assignment queue |

Growth-comparison rules degrade to `insufficient_history` like every other
comparison. Opportunity rows are ranked by upside ₹.

---

## 11. Morning Brief

A deterministic daily digest at the top of the Executive Overview. **No model is
involved** — it is a template filled from the same services every other card uses,
which is precisely why it can be trusted. It cannot be asked freeform questions.

```
Good morning, <name>

Yesterday
  Revenue        ₹3.8L
  Orders         7
  Collections    ₹2.1L
  Best brand     Dimore
  Best salesperson  Rahul
  Biggest risk   ₹5.4L quotation pending 9 days

Recommended actions
  • Call JK Enterprises — ₹5.4L quotation stalled 9 days
  • Release Dimore material — 12 boxes waiting 6 days
  • Follow up Architect Studio — 5 quotations, no contact in 14 days
```

Every figure is a link to its record. **Recommended actions are the top three rows
of Attention and Opportunity by ₹ impact** — not a separate rule set, so the brief
can never contradict the cards below it. Lines with no data are omitted rather than
shown as zero, and the brief degrades to a shorter form on a day with no activity.

---

## 12. Customer Heat Score

Replaces the binary active/inactive label with a scannable band. Deterministic,
computed from signals the business already records.

| Signal | Contribution |
|---|---|
| Days since last order | strongest positive when recent |
| Days since last visit (`walkins`) | recency of physical intent |
| Open quotation age | fresh open quotation is hot; stale one cools |
| Follow-up responsiveness | completed vs overdue follow-ups |
| Payment behaviour | on-time completed payments vs overdue outstanding |
| Order frequency | orders ÷ months since first order |

| Band | Meaning |
|---|---|
| **Hot** | Active intent right now — open fresh quotation or activity within 30 days |
| **Warm** | Real relationship, activity within 90 days |
| **Cold** | 90–180 days quiet |
| **Lost** | Past `CUSTOMER_INACTIVE_DAYS` with no open quotation |

The band always exposes **which signals produced it** on tap — a heat score the
owner cannot audit is a heat score the owner will not trust. Weights live in one
constant block in `customers.py`.

---

## 13. Relationship Intelligence (timeline)

Customers and partners are relationships, not rows. Every customer profile and
every partner profile carries one timeline instead of isolated tables:

```
Walk-in → Selection → Quotation → Order → Dispatch → Payment → Future orders
```

Each stage shows its date, its owner, its value, and links to the record. Stages
that never happened render as not-yet-reached rather than missing, so the timeline
answers *where the relationship is stuck* at a glance.

Sources: `walkins`, `quotations` (both doc types), `customer_orders`, `dispatches`,
`payments`, and `activity_events` (2,413 rows, already carrying `customer_id`,
`quotation_id`, `entity_type`, `event_type`, `summary`) for the fine-grained
interaction history between stages.

---

## 14. Global search

One search field in the Sales Data shell. Typing `JK` surfaces, without leaving the
page, grouped results across:

- Customers (name, phone)
- Quotations and orders (number, customer, project)
- Payments (reference, quotation number)
- Architects and interior designers (name, firm)
- Products (name, SKU) and brands

Results are grouped by entity type, each row links into the drill-down graph, and
the current floor scope and role gating apply exactly as they do everywhere else.

Implementation: one `search.py` service, case-insensitive prefix/substring match
across the indexed fields above, capped and paginated per group. At current volumes
this is trivial; the supporting indexes are listed in §3.3, and if the catalogue
grows past comfortable regex range the service is the single place to swap in a
Mongo text index without touching the UI.

**Global search ships in Phase 5, not earlier** — it surfaces products, brands,
partners and operations records, so shipping it before those workspaces exist would
produce results that dead-end, violating §6.

---

## 15. Frontend architecture

### 15.1 Routes

```
/sales-data                              → Executive Overview
/sales-data/executive                    → Executive Overview
/sales-data/sales                        → Performance
/sales-data/referrals                    → Referral summary (both types)
/sales-data/referrals/architects
/sales-data/referrals/interior-designers
/sales-data/products
/sales-data/brands
/sales-data/customers
/sales-data/operations
/sales-data/forecasting
```

Sidebar keeps the single entry **Sales Data**. Existing `/sales-data/*` deep links
keep working; legacy screens and `sales_data_routes.py` are removed only after the
replacing phase is verified feature-for-feature.

### 15.2 Workspace navigation — five visible, rest under More

The owner spends most of their time in a handful of places. The switcher shows:

```
Executive · Performance · Customers · Products · Operations · More ▾
```

`More` expands to **Brands · Architects · Interior Designers · Forecasting**. The
active workspace is always visible even when it lives under More. On tablet and
phone the switcher collapses to a single dropdown.

### 15.3 Shared shell — `src/components/analytics/`

| Component | Role |
|---|---|
| `WorkspaceSwitcher` | five primary + More, active state, keyboard navigable |
| `GlobalSearch` | §14, in the shell header |
| `FilterBar` | sticky. Floor · Date (incl. Yesterday/Today/This Week) · Brand · Category · Supplier · Salesperson · Architect · Interior Designer · Customer · Status. One implementation, every workspace |
| `KpiRow` | sticky KPI strip |
| `KpiCard` | value, comparison, delta, sparkline, **the question it answers**, click → drill-down |
| `HealthScoreCard` | score, band, direction, expandable component breakdown |
| `MorningBrief` | §11 |
| `AttentionList` / `OpportunityList` | ranked rows with ₹ impact and destination |
| `MoneyBlockedCard` | ₹-first operational summary |
| `HeatBadge` | Hot / Warm / Cold / Lost with signal breakdown on tap |
| `RelationshipTimeline` | §13 |
| `DataTable` | promoted from `src/components/tiles/TileTable.tsx` — reuses its hard-won RN-Web fixes. Sort, filter, search, sticky header, pagination, row click-through, CSV/Excel/PDF export |
| `ExportMenu` | CSV · Excel · PDF, via the existing `openApiFile` blob helper |
| `StateViews` | loading · empty · no-data · `no_prior_period` · `insufficient_history` · referral onboarding |

**Filter state lives in URL query params** so every drill-down is shareable,
bookmarkable, and back-navigable with context intact.

### 15.4 BuildCon chart kit — `src/components/charts/`

New dependency: **`react-native-svg`** (`expo install`, works web + iOS + Android).
No third-party charting library — the visual language stays ours.

Components: `Sparkline` · `LineChart` · `AreaChart` · `BarChart` · `HorizontalBar` ·
`StackedBar` · `Donut` · `FunnelChart` · `Heatmap` · `TrendIndicator` ·
`ComparisonOverlay`.

Every chart shares one `ChartFrame` providing: design tokens (no local colours),
responsive sizing, hover (web) and touch (mobile), tooltips, click-through to the
drill-down graph, loading / empty / no-data states, and accessibility labels.
Adding a chart type must not require changing the frame.

### 15.5 Visual system

Warm white. High typography. Large whitespace. 12-column responsive grid, 8px
spacing system, 32px section spacing, 24px card padding, 16px row padding. Sticky
filters and sticky KPI row. Desktop first; tablet and mobile responsive at the
app's existing `useBp()` breakpoints (768 / 1024).

Known RN-Web traps to respect (all previously cost this codebase real time):
`adjustsFontSizeToFit` is a no-op on web — use compact money formatters in tiles; a
`flexDirection` override on phone must carry the matching `alignItems`; a horizontal
`ScrollView` shrink-wraps to max-content; `position:sticky` needs the rows in an
inner vertical `ScrollView`; sticky-top and sticky-right are mutually exclusive; use
`isNearScrollEnd` for any new infinite list.

---

## 16. Phasing

Each phase is fully functional and verified before the next begins.

| Phase | Contents |
|---|---|
| **0** | Correctness fixes: `ordered_at`, `items.net_amount`, index migration, owner targets in Settings, `services/analytics/` skeleton (`filters`, `periods`, `metrics`, `cache`), chart kit foundation |
| **1** | Executive Overview · Business Health Score · Attention Center · Opportunity Center · Morning Brief |
| **2** | Performance · Referral Analytics · shared `ReferredByField` in both builders · partner CRM profiles |
| **3** | Products · Brands (full brand intelligence set) |
| **4** | Customers · Heat Score · Relationship timeline |
| **5** | Operations (money-first) · Global search |
| **6** | Forecasting & Historical Trends · legacy `sales_data_routes.py` and old screens removed |
| **7** | Alerts: notify-me subscriptions (revenue drop, collections overdue, architect inactive, brand collapse, large quotation expiring) delivered through the existing `notifications` collection and `services/notifications.py` |

Phase 0 is not optional and not deferrable — Phase 1's numbers are wrong without it.

**Implementation plans are written per phase, not one plan for all eight.** This
document is the architecture that keeps them coherent; each phase gets its own plan
written against it, and no phase's plan may introduce an aggregation, KPI, or
drill-down path that is not in the Blueprint (§7) without amending this document
first.

## 17. Verification protocol (every phase)

1. Every KPI cross-checked against a direct Mongo query, value for value.
2. Every aggregation reconciles: product = brand = category = quotation revenue.
3. Health Score recomputed by hand for one period and matched component by component.
4. Every filter verified, including the three-way floor probe (no header /
   `first-floor` / `ground-floor`) that catches ambient-state leaks the UI hides.
5. Every drill-down path opens the right record with filter context preserved.
6. Every export (CSV / Excel / PDF) opens and matches the on-screen data.
7. Responsive pass at 1280 / 768 / 375.
8. No placeholder components. No empty cards. No fabricated values.
9. Backend unit tests for every new service module.
10. Fix, re-verify, and only then proceed.

## 18. Risks and open items

- **Referral workspaces stay empty until the field is used.** The build is correct
  and the onboarding state is honest, but partner numbers only appear once
  quotations carry a Referred By. Worth a deliberate rollout conversation.
- **The Health Score is only as meaningful as its targets.** With no revenue or
  conversion target set it runs on 5 of 7 signals and says so. Setting those two
  numbers is the single highest-leverage thing the owner can do for it.
- **One month of history** means most comparison cards ship in
  `insufficient_history` and become useful as data accumulates. Expected, designed
  for, not a defect.
- **Walk-in data is two days old** (110 records, 106 `new`), so funnel conversion
  will read near zero until walk-ins age through the pipeline.
- **No payment-terms field exists** on customers or quotations. Overdue is computed
  from a single global `payment_terms_days` setting. If terms genuinely vary per
  customer, that field should be added and will take precedence.
- **`customer_orders` uses `overall_status`**, not `status` — a naive `status`
  query returns `None` for all 13 documents.
- The shared backend on `:8010` does not auto-reload and may be in use by another
  session; confirm before restarting.
