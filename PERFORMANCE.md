# Forge Performance Hardening — Task 1

**Measurement date:** 2026-07-12  
**Runtime:** Emergent preview (Expo/React Native Web development bundle), FastAPI, MongoDB Atlas, Supabase Storage  
**Catalog:** 2,966 products / 2,970 media records  
**Method:** repeated direct-localhost API requests, repeated preview-ingress requests, Mongo execution plans, isolated query-stage timings, production web export, and browser navigation/network observation.

## Executive conclusion

Navigation latency is not primarily Expo Router, React rendering, Mongo compute, or preview ingress. The dominant cost is the number of geographically remote MongoDB Atlas round trips made by each API request.

Before optimization, every authenticated endpoint performed two sequential Atlas reads before its business query:

1. session revocation check: median ~229 ms;
2. user/customer lookup: median ~229 ms;
3. endpoint business queries: additional ~229 ms per sequential query group.

This produced a fixed ~458 ms authentication tax per API call. Pages that launch several requests in parallel still waited 0.7–2.2 seconds; workflows that await reconciliation or execute many sequential operations waited longer.

The first evidence-backed improvement caches only successfully validated principals for 10 seconds and parallelizes the first session + principal validation. Logout, logout-all, and single-session revocation explicitly invalidate the cache.

## Measurement summary

### Preview versus application latency

Preview ingress is a minor contributor after the first Metro load:

| Metric | Direct localhost | Preview | Preview overhead |
|---|---:|---:|---:|
| `/api/health` median | 276 ms | 279 ms | ~3 ms |
| `/api/products` popular median (before) | 2,180 ms | 2,219 ms | ~39 ms |
| `/api/categories` median (before) | 973 ms | 997 ms | ~24 ms |
| `/api/customers` median (before) | 756 ms | 754 ms | negligible |

**Decision:** preview networking is not the root cause. Direct API timings were already slow.

### Initial Expo/Metro versus in-app navigation

| Measurement | Result |
|---|---:|
| Fresh dev-preview hydration | ~3.35 s |
| Production web export bundling | 14.98 s build-time only |
| Production JS bundle | 3.15 MB uncompressed |
| In-app route visible shell | ~1.31–1.36 s before optimization |
| Route network idle | ~1.49–9.51 s depending on screen |

Metro adds a one-time development hydration cost. It does not explain repeated route latency.

### Mongo execution evidence

Mongo execution plans are fast once the request reaches Atlas:

| Query plan | Mongo execution | Docs examined | Index behavior |
|---|---:|---:|---|
| active product page, 60 | 0 ms | 60 | IXSCAN |
| active + brand, 60 | 1 ms | 60 | IXSCAN |
| category + name sort, 60 | 6 ms | 440 | IXSCAN + in-memory sort |
| regex `basin`, 60 | 3 ms | 142 | IXSCAN on active prefix |
| 60 product IDs | 0 ms | 60 | IXSCAN |

Observed application-side query calls each cost ~228–230 ms because network RTT dominates:

- `count_documents`: 229 ms;
- global usage aggregation: 229 ms;
- per-user usage: 228 ms;
- full product page fetch: 231 ms;
- media hydration: 230 ms;
- variant hydration: 229 ms;
- hierarchy aggregation: 508 ms warm, returning 2,447 grouped rows.

The popular product path also downloads a slim 2,966-row ranking pool on every page request: ~473 ms warm. This is a remaining Task 2/3 optimization target, not part of the first fix.

### Endpoint baseline before first fix

Warm medians, direct localhost:

| Endpoint | Before |
|---|---:|
| `/auth/me` | 506 ms |
| `/brands` | 972 ms |
| `/categories` | 973 ms |
| `/dashboard/stats` | 1,438 ms |
| `/products?sort=popular&limit=60` | 2,180 ms |
| `/customers` | 756 ms |
| `/quotations/recent` | 756 ms |
| `/payments/stats` | 1,233 ms |
| `/followups/stats` | 1,246 ms |

No application endpoint returned cache headers directly. Preview added `no-store, no-cache, must-revalidate`.

## Frontend request and render observations

### Duplicate/refetch findings

- Quotation Builder requests `/categories` twice on mount: once in its six-request reference-data batch and once in the brand-change effect for the initial `null` brand.
- Payments runs `loadOrders("")` in its initial effect and schedules the same request again from the search effect.
- Auth hydration calls `/auth/me` when the whole Expo application remounts on direct URL navigation. Normal client-side route switches keep `AuthProvider` mounted; browser automation that performs full URL navigations overstates this as nine route-level calls.
- Catalog hierarchy is fetched again whenever `brandId`, `cat`, or `subcat` changes even though the response is invariant and 520 KB. This is a confirmed future optimization target.

### Rerender evidence

React DevTools Profiler was not available. No unsupported flame-graph claim is made. Observable evidence:

- route shell visibility is consistent (~1.3 s);
- product grid appears before all reference requests finish;
- no critical JavaScript console errors were observed;
- font request aborts and shadow deprecation warnings were observed in development mode;
- no evidence currently shows React rerenders as the primary bottleneck.

### Images

- Representative Supabase image: 5.5 KB JPEG;
- cold retrieval: 1,799 ms;
- warm retrieval: 86–110 ms;
- response headers: `Cache-Control: public, max-age=31536000, immutable`, ETag present;
- frontend uses `expo-image` with `memory-disk` caching and list virtualization.

Images are cold-start sensitive but correctly configured for long-lived caching. The browser agent's statement that no effective caching existed is contradicted by response headers and repeated warm fetch measurements.

## First optimization

### Problem

Every authenticated request paid two sequential remote Atlas reads before endpoint logic.

### Root cause

`get_current_user` / `get_current_customer` separately awaited session validation and principal lookup. With ~229 ms Atlas RTT, authentication alone cost ~458 ms per API request.

### Evidence

- session lookup: 229 ms median;
- user lookup: 229 ms median;
- sequential combined: 458 ms median;
- equivalent first-time parallel validation: ~230 ms;
- endpoint timing pattern matched authentication tax plus one RTT per sequential business-query group.

### Fix

- Run the session and principal lookups concurrently on a cold cache miss.
- Cache only an already validated active principal for 10 seconds.
- Bound cache to 2,048 entries and remove expired entries.
- Explicitly invalidate on current-session logout, logout-all, and single-session revoke.
- Preserve legacy tokens without session IDs.
- Do not cache rejected/revoked/inactive principals.

### Before/after benchmark

Warm direct medians:

| Endpoint | Before | After | Improvement |
|---|---:|---:|---:|
| `/auth/me` | 506 ms | 42 ms | **91.7%** |
| `/brands` | 972 ms | 520 ms | **46.5%** |
| `/categories` | 973 ms | 521 ms | **46.5%** |
| `/dashboard/stats` | 1,438 ms | 995 ms | **30.8%** |
| `/customers` | 756 ms | 281 ms | **62.8%** |
| `/quotations/recent` | 756 ms | 281 ms | **62.8%** |
| `/payments/stats` | 1,233 ms | 755 ms | **38.8%** |
| `/followups/stats` | 1,246 ms | 775 ms | **37.8%** |

Preview `/auth/me` warm median fell to ~80 ms; `/customers` and `/quotations/recent` fell to ~280 ms. Preview overhead remains small.

Popular product listing remained variable at ~1.7–2.7 seconds because it still executes count + usage reads, downloads/ranks the complete 2,966-row pool, then hydrates product/media/variant pages. Authentication was only one portion of that path.

## Safety and risks

- Session revocation visibility can be delayed by at most 10 seconds if revocation happens outside Forge's own logout/revoke routes. Forge routes invalidate immediately.
- In-memory cache is per worker. Current deployment uses one worker; with multiple workers the maximum external-revocation delay remains 10 seconds per worker.
- User role/active-profile changes made directly in Mongo may be visible up to 10 seconds later.
- The cache is bounded and stores no password hashes or JWTs.

## Remaining measured issues after Task 1 (historical)

The following items were the handoff into Performance Sprint 2. Items 1 and the backend portion of item 2 are resolved below; frontend-only items remain out of scope for this milestone.

1. Popular catalog path re-ranked matching products and hydrated variants/media through several Atlas round trips.
2. Catalog pagination returned the correct pages, but the frontend still needed infinite-scroll verification.
3. The 520 KB hierarchy response was repeatedly refetched by the frontend.
4. Dashboard awaited follow-up reconciliation before starting six read requests.
5. Quotation Builder duplicated categories fetch and had no shared request cache.
6. Payments duplicated its initial orders fetch.
7. Production JS bundle was 3.15 MB uncompressed; route-level code splitting was not evident.
8. React flame graph remained unavailable.

---

# Performance Sprint 2 — Backend Catalog Milestone

**Measurement date:** 2026-07-12  
**Scope:** backend evidence, indexes, query architecture, pagination correctness, and catalog endpoint regression only. No React Query, virtualization, infinite-scroll UI, image loading, or PDF work was performed.

## Root cause

MongoDB compute was not the main delay. Atlas command wall time was about **228–230 ms per round trip**, while server-side execution was normally **0–137 ms**. Catalog endpoints composed many of those remote reads sequentially:

- `/products` performed count + global usage + user usage, product paging, media hydration, family-sibling hydration, and sibling-media hydration;
- `/catalog/search` had no text index, paid a failed text-search round trip, fell back to regex, then issued per-family media lookups (N+1);
- `/catalog/facets` awaited eight independent aggregations sequentially;
- hierarchy, family, detail, recent/frequent, alternates, and complete-set endpoints also chained independent Atlas reads;
- deterministic sorts used `(name, id)` or `(price, id)`, but existing indexes omitted the `id` tie-breaker, forcing blocking sorts and broad scans.

Serialization was not material: encoding a 60-product / 200+ KB response measured **5–9 ms**, and JSON rendering measured **1–2 ms**.

## Query-plan evidence

Before index changes:

| Query shape | Mongo execution | Docs examined | Keys examined | Plan issue |
|---|---:|---:|---:|---|
| active + `name,id`, first 60 | 45 ms | 2,966 | 2,966 | IXSCAN + blocking SORT |
| popular regular page, first 60 | 73 ms | 2,966 | 2,966 | IXSCAN + blocking SORT |
| popular regular page, deep skip | 105 ms | 2,966 | 2,966 | blocking SORT + SKIP |
| active + `price,id` ASC | 34 ms | 2,966 | 2,966 | blocking SORT |
| text search | failed | — | — | `IndexNotFound` |
| page media / sibling lookup | 0–1 ms | 60–66 | indexed | compute fast; each wall call still ~229 ms |

Evidence-backed indexes added:

- `products_active_name_id`: `(active, name, id)`;
- `products_active_price_id`: `(active, price, id)`;
- `products_active_price_desc_id`: `(active, price DESC, id)` because mixed `price DESC, id ASC` cannot reverse-scan the ascending index;
- `products_text_v1`: weighted text index used by the durable Mongo fallback;
- `usage_user_recent`: `(user_id, last_used_at DESC)`;
- `usage_user_count`: `(user_id, count DESC)`.

After index changes:

| Query shape | Mongo execution | Docs examined | Keys examined | Winning index |
|---|---:|---:|---:|---|
| active + `name,id`, first 60 | 2 ms | 60 | 60 | `products_active_name_id` |
| active + `price,id` ASC | 2 ms | 60 | 60 | `products_active_price_id` |
| active + `price DESC,id` | 2 ms | 60 | 60 | `products_active_price_desc_id` |
| text `basin`, first 90 | 4 ms | 894 | 447 | `products_text_v1` |
| deep `name,id` skip 2,900 | 72 ms | 60 | 2,960 | index scan; skip key-walk remains |

All measured Mongo execution is under 200 ms. A remote uncached command cannot meet a 200 ms wall target because the measured Atlas RTT alone is ~228 ms.

## Backend architecture change

Forge now builds a read-only catalog snapshot during application startup:

- 2,966 active products (~3.02 MB serialized);
- 2,970 media records (~2.59 MB serialized);
- brand/category references and product-usage rows;
- precomputed product, family, media, and usage maps.

The five source reads run concurrently. Catalog requests then filter, rank, paginate, hydrate media/variants, group families, calculate facets, and resolve related products in process without repeated Atlas round trips. The existing API paths, parameters, response shapes, and offset pagination contract are preserved.

Freshness controls:

- routed product/media/import mutations schedule a background snapshot refresh;
- quotation product-usage writes update the snapshot immediately with lock-protected copy-on-write state;
- a 300-second stale-while-revalidate safety timer catches catalog writes performed by offline scripts;
- startup does not report ready until the initial snapshot is loaded.

Snapshot refresh itself measured **2.39–4.57 s** against remote Atlas, but occurs at startup/background refresh rather than in the catalog request path.

## Before / after endpoint benchmarks

Direct localhost warm medians. Before uses three repetitions; after uses five. Authentication principal caching from Sprint 1 was already active in both sets.

| Endpoint | Before | After | Speed-up |
|---|---:|---:|---:|
| products popular, skip 0 | 1,448.3 ms | **17.7 ms** | 81.8× |
| products popular, skip 60 | 1,493.3 ms | **14.0 ms** | 106.7× |
| products popular, skip 2,900 | 2,966.6 ms | **18.8 ms** | 157.8× |
| products name, skip 0 | 1,288.9 ms | **16.7 ms** | 77.2× |
| products name, skip 2,900 | 1,990.2 ms | **18.1 ms** | 110.0× |
| products price ascending | 1,542.2 ms | **13.1 ms** | 117.7× |
| products price descending | 1,282.0 ms | **13.2 ms** | 97.1× |
| products recent | 1,963.8 ms | **17.1 ms** | 114.8× |
| products search `basin` | 2,093.2 ms | **23.5 ms** | 89.1× |
| product families | 829.7 ms | **56.7 ms** | 14.6× |
| catalog hierarchy | 1,054.2 ms | **39.3 ms** | 26.8× |
| catalog facets | 2,049.8 ms | **49.9 ms** | 41.1× |
| grouped catalog search `basin` | 7,769.9 ms | **49.8 ms** | 156.0× |
| recent / frequent products | 1,248.9 ms | **42.9 ms** | 29.1× |
| brands / categories | 526–527 ms | **42.9 ms** | ~12.3× |
| product detail | 1,006.8 ms | **42.0 ms** | 24.0× |
| alternates | 1,974.0 ms | **43.9 ms** | 45.0× |
| complete the set | 1,212.7 ms | **43.0 ms** | 28.2× |
| family detail | 1,207.9 ms | **42.0 ms** | 28.8× |

Every measured backend catalog read is below 200 ms after startup.

## Pagination and data-integrity verification

- total remains **2,966** active products;
- popular pages from skip 0 through skip 2,940 returned **2,966 rows / 2,966 unique IDs / 0 duplicates**;
- final page at skip 2,940 returned 26 rows;
- skip 0, 60, and 2,900 were verified for popular, recent, name, price ascending, and price descending;
- exact page-ID parity against direct Mongo sorting/filtering passed for all sort modes and `q=basin`;
- brands remain 5, categories remain 26, families remain 2,361;
- catalog regression suite passed (32 tests in the focused local run).

## Files modified

- `backend/services/catalog_service.py` — startup catalog read model, local ranking/filtering/paging/media/family/facet/search services;
- `backend/routes/catalog_routes.py` — all catalog reads use the shared read model; product writes refresh it;
- `backend/routes/media_routes.py` — media reads use the read model and media writes refresh it;
- `backend/routes/catalog_import_routes.py` — import/rollback refresh hooks;
- `backend/routes/quotation_routes.py` — concurrent usage writes plus immediate read-model usage sync;
- `backend/server.py` — startup snapshot preload;
- `backend/scripts/ensure_indexes.py` — durable index definitions;
- `backend/bootstrap.py` — required index validation and text-index signature support;
- `PERFORMANCE.md` — this evidence and benchmark record.

## Remaining bottlenecks and limits

1. Atlas RTT remains ~228–230 ms. Writes and non-cached backend modules still pay that network floor.
2. Snapshot preload/refresh takes 2.4–4.6 seconds and uses roughly 5.6 MB serialized source data (more as Python objects). It is intentionally moved out of request latency.
3. State is per process. A multi-worker deployment would hold one snapshot per worker; routed writes refresh only the current worker. A shared version signal would be needed before scaling workers.
4. Offline/direct database writes can be visible for up to 300 seconds; routed writes refresh immediately in the background, and usage changes update immediately.
5. Deep Mongo offset pagination still walks ~2,960 index keys. The request path no longer pays this cost, and offset behavior was intentionally preserved rather than redesigning the API to cursor pagination.
6. The hierarchy payload is still ~520 KB. Backend generation is 39 ms, but frontend duplicate fetch/parse behavior remains a later frontend sprint concern.
7. Frontend request deduplication, React Query behavior, infinite-scroll UI verification, virtualization, and image loading/caching are explicitly deferred per the backend-only milestone.

## Backend milestone gate

Backend catalog performance is no longer the primary bottleneck: all measured catalog reads are 13–57 ms median after startup, query execution is under 200 ms, and all 2,966 products are reachable with stable pagination. Stop here before frontend optimization, as requested.
