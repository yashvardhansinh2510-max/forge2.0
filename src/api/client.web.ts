// Browser implementation of the API client. This is intentionally separate
// from client.ts so web does not retain AsyncStorage/SecureStore in its startup
// dependency graph.
import { browserStorage } from "@/src/utils/storage/browser.web";

const SELECTED_FLOOR_KEY = "forge.active-floor";
const configuredBase = process.env.EXPO_PUBLIC_BACKEND_URL || "";
const BASE = !__DEV__ && (!configuredBase || configuredBase.startsWith("http://localhost"))
  ? "https://buildcon-backend-production.up.railway.app"
  : configuredBase;
const TOKEN_KEY = "forge.jwt";
const TOKEN_KIND_KEY = "forge.jwt.kind";
const REQUEST_TIMEOUT_MS = 30_000;
const inflightGets = new Map<string, Promise<unknown>>();
const responseCache = new Map<string, { expiresAt: number; value: unknown }>();
let tokenCache: string | null | undefined;
let tokenKindCache: TokenKind | null | undefined;
let floorCache: string | null | undefined;

export type TokenKind = "staff" | "customer";
export class ApiError extends Error {
  constructor(public status: number, public detail: string) { super(detail); }
}
type RequestOptions = { floorId?: string; signal?: AbortSignal; cacheMs?: number };

export async function setToken(token: string, kind: TokenKind) {
  tokenCache = token;
  tokenKindCache = kind;
  await browserStorage.secureSet(TOKEN_KEY, token);
  await browserStorage.setItem(TOKEN_KIND_KEY, kind);
}
export async function clearToken() {
  tokenCache = null;
  tokenKindCache = null;
  responseCache.clear();
  await browserStorage.secureRemove(TOKEN_KEY);
  await browserStorage.removeItem(TOKEN_KIND_KEY);
}
export async function getToken(): Promise<string | null> {
  if (tokenCache === undefined) tokenCache = (await browserStorage.secureGet<string>(TOKEN_KEY, "")) || null;
  return tokenCache ?? null;
}
export async function getTokenKind(): Promise<TokenKind | null> {
  if (tokenKindCache === undefined) tokenKindCache = ((await browserStorage.getItem<string>(TOKEN_KIND_KEY, "")) as TokenKind) || null;
  return tokenKindCache ?? null;
}
export function setRequestFloorId(floorId: string) {
  if (floorCache !== floorId) responseCache.clear();
  floorCache = floorId;
}
export function clearApiResponseCache() { responseCache.clear(); }
async function getRequestFloorId() {
  if (floorCache === undefined) floorCache = (await browserStorage.getItem<string>(SELECTED_FLOOR_KEY, "")) || "";
  return floorCache;
}
async function request<T>(method: string, path: string, body?: unknown, opts?: RequestOptions): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const floorId = opts?.floorId ?? await getRequestFloorId();
  if (floorId) headers["X-Floor-Id"] = floorId;
  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = setTimeout(() => { timedOut = true; controller.abort(); }, REQUEST_TIMEOUT_MS);
  const abortFromCaller = () => controller.abort();
  if (opts?.signal) {
    if (opts.signal.aborted) controller.abort();
    else opts.signal.addEventListener("abort", abortFromCaller, { once: true });
  }
  try {
    const response = await fetch(`${BASE}/api${path}`, {
      method, headers, body: body ? JSON.stringify(body) : undefined, signal: controller.signal,
    });
    const text = await response.text();
    let data: unknown = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        if (response.ok) throw new ApiError(502, "The server returned an invalid response. Please try again.");
      }
    }
    if (!response.ok) {
      const detail = data && typeof data === "object" && "detail" in data
        ? (data as { detail?: unknown }).detail
        : text || `HTTP ${response.status}`;
      throw new ApiError(response.status, typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data as T;
  } catch (error) {
    if (timedOut) throw new ApiError(408, "Request timed out. Please try again.");
    if (error instanceof TypeError) throw new ApiError(503, "Cannot reach the backend. Check the configured secure backend URL and try again.");
    throw error;
  } finally {
    clearTimeout(timeoutId);
    opts?.signal?.removeEventListener("abort", abortFromCaller);
  }
}
export const api = {
  get: <T>(path: string, opts?: RequestOptions) => {
    const key = `${opts?.floorId ?? floorCache ?? "auto"}:${path}`;
    const cached = responseCache.get(key);
    if (cached && cached.expiresAt > Date.now()) return Promise.resolve(cached.value as T);
    if (cached) responseCache.delete(key);
    const existing = inflightGets.get(key);
    if (existing) return existing as Promise<T>;
    const pending = request<T>("GET", path, undefined, opts).then((value) => {
      if (opts?.cacheMs && opts.cacheMs > 0) responseCache.set(key, { expiresAt: Date.now() + opts.cacheMs, value });
      return value;
    }).finally(() => inflightGets.delete(key));
    inflightGets.set(key, pending);
    return pending;
  },
  post: <T>(path: string, body?: unknown, opts?: RequestOptions) => { responseCache.clear(); return request<T>("POST", path, body, opts); },
  put: <T>(path: string, body?: unknown, opts?: RequestOptions) => { responseCache.clear(); return request<T>("PUT", path, body, opts); },
  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) => { responseCache.clear(); return request<T>("PATCH", path, body, opts); },
  delete: <T>(path: string, opts?: RequestOptions) => { responseCache.clear(); return request<T>("DELETE", path, undefined, opts); },
  authenticatedUrl: async (path: string) => {
    const { token } = await request<{ token: string }>("POST", "/downloads/token", { target: `/api${path}` });
    return `${BASE}/api${path}${path.includes("?") ? "&" : "?"}dl=${encodeURIComponent(token)}`;
  },
  base: BASE,
};
