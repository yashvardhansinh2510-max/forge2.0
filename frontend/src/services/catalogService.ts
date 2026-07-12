// Shared catalog data service.
// -----------------------------------------------------------------------------
// Catalog, Quotation Builder and any future product picker use this single
// pagination/filter/cache contract. Requests are de-duplicated, successful
// pages/reference data are cached briefly, and pagination is merged by product
// identity so repeated onEndReached events cannot introduce duplicates.
import { api } from "@/src/api/client";

export const CATALOG_PAGE_SIZE = 60;
export type CatalogSort = "popular" | "recent" | "price_asc" | "price_desc" | "name";
export type CatalogMode = "products" | "families";

export type CatalogQuery = {
  mode?: CatalogMode;
  q?: string;
  brandId?: string | null;
  categoryId?: string | null;
  subcategory?: string | null;
  series?: string | null;
  sort?: CatalogSort;
};

export type CatalogPage<T> = { total: number; items: T[] };

type CacheEntry = { expiresAt: number; value: unknown };
const pageCache = new Map<string, CacheEntry>();
const pending = new Map<string, Promise<unknown>>();
const PAGE_TTL_MS = 60_000;
const REFERENCE_TTL_MS = 5 * 60_000;

function stableParams(query: CatalogQuery, skip: number, limit: number): URLSearchParams {
  const p = new URLSearchParams();
  p.set("limit", String(limit));
  p.set("skip", String(skip));
  if (query.mode !== "families") p.set("sort", query.sort || "popular");
  if (query.q?.trim()) p.set("q", query.q.trim());
  if (query.brandId) p.set("brand_id", query.brandId);
  if (query.categoryId) p.set("category_id", query.categoryId);
  if (query.subcategory) p.set("subcategory", query.subcategory);
  if (query.series) p.set("series", query.series);
  return p;
}

async function cachedGet<T>(path: string, ttlMs: number): Promise<T> {
  const cached = pageCache.get(path);
  if (cached && cached.expiresAt > Date.now()) return cached.value as T;
  const existing = pending.get(path);
  if (existing) return existing as Promise<T>;
  const request = api.get<T>(path)
    .then((value) => {
      pageCache.set(path, { value, expiresAt: Date.now() + ttlMs });
      return value;
    })
    .finally(() => pending.delete(path));
  pending.set(path, request);
  return request;
}

export function catalogQueryKey(query: CatalogQuery): string {
  return stableParams(query, 0, CATALOG_PAGE_SIZE).toString();
}

export async function fetchCatalogPage<T>(
  query: CatalogQuery,
  skip = 0,
  limit = CATALOG_PAGE_SIZE,
): Promise<CatalogPage<T>> {
  const params = stableParams(query, skip, limit);
  const endpoint = query.mode === "families" ? "/products/families" : "/products";
  return cachedGet<CatalogPage<T>>(`${endpoint}?${params.toString()}`, PAGE_TTL_MS);
}

export function mergeCatalogPage<T extends { id?: string; family_key?: string }>(
  current: T[],
  incoming: T[],
): T[] {
  const seen = new Set(current.map((item) => item.id || item.family_key).filter(Boolean));
  const next = [...current];
  for (const item of incoming) {
    const key = item.id || item.family_key;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    next.push(item);
  }
  return next;
}

export const catalogReferences = {
  brands: <T>() => cachedGet<T>("/brands", REFERENCE_TTL_MS),
  categories: <T>(brandId?: string | null) => cachedGet<T>(
    brandId ? `/categories?brand_id=${encodeURIComponent(brandId)}` : "/categories",
    REFERENCE_TTL_MS,
  ),
  hierarchy: <T>() => cachedGet<T>("/catalog/hierarchy", REFERENCE_TTL_MS),
};

export function clearCatalogCache(): void {
  pageCache.clear();
  pending.clear();
}
