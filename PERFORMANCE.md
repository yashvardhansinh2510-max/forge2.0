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

## Remaining measured issues

1. Popular catalog path re-ranks the entire matching catalog and hydrates variants/media on every page.
2. Catalog route has no infinite scrolling and only renders the first 60 results in the current implementation.
3. The 520 KB hierarchy response is repeatedly refetched on filter changes.
4. Dashboard awaits follow-up reconciliation before starting six read requests.
5. Quotation Builder duplicates categories fetch and has no shared request cache.
6. Payments duplicates its initial orders fetch.
7. Production JS bundle is 3.15 MB uncompressed; route-level code splitting is not presently evident.
8. React flame graph is unavailable; rerender optimization should not be attempted without profiler evidence.

## Next verification gate

Before Task 1 is marked complete, the backend testing agent must regression-test authentication, revocation, roles, customer auth, and representative endpoints. Browser navigation should then be remeasured once to confirm click-to-visible/idle improvements. Per sprint instruction, work stops after this first verified improvement for review before addressing catalog architecture.
