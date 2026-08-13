// Thin fetch wrapper with token injection.
import { storage } from "@/src/utils/storage";

const SELECTED_FLOOR_KEY = "forge.active-floor";

// Empty string ⇒ same-origin fetch. Kubernetes ingress routes `/api/*` to backend.
const configuredBase = process.env.EXPO_PUBLIC_BACKEND_URL || "";
const BASE = !__DEV__ && (!configuredBase || configuredBase.startsWith("http://localhost"))
  ? "https://buildcon-backend-production.up.railway.app"
  : configuredBase;

// APP_STORE_PLAY_STORE_AUDIT.md Blocker #4: a release build whose
// EXPO_PUBLIC_BACKEND_URL is plain http:// boots to a fully network-dead
// app — iOS App Transport Security silently blocks every request, Android
// blocks cleartext by default on API 28+. That used to fail silently
// (every screen just looks broken); this makes it impossible to miss.
// Same-origin (`BASE === ""`) is a legitimate production setup (ingress
// terminates HTTPS in front of both the app and `/api/*`) and is not flagged.
if (!__DEV__ && BASE && !BASE.startsWith("https://")) {
  throw new Error(
    `EXPO_PUBLIC_BACKEND_URL must be https:// in a production build (got "${BASE}"). ` +
    "Never work around this with an ATS/cleartext exception — fix the URL in the build profile instead.",
  );
}
const TOKEN_KEY = "forge.jwt";
const TOKEN_KIND_KEY = "forge.jwt.kind"; // "staff" | "customer"
const REQUEST_TIMEOUT_MS = 30_000;
const inflightGets = new Map<string, Promise<unknown>>();
const responseCache = new Map<string, { expiresAt: number; value: unknown }>();
let tokenCache: string | null | undefined;
let tokenKindCache: TokenKind | null | undefined;
let floorCache: string | null | undefined;

export type TokenKind = "staff" | "customer";

export async function setToken(token: string, kind: TokenKind) {
  tokenCache = token;
  tokenKindCache = kind;
  await storage.secureSet(TOKEN_KEY, token);
  await storage.setItem(TOKEN_KIND_KEY, kind);
}

export async function clearToken() {
  tokenCache = null;
  tokenKindCache = null;
  responseCache.clear();
  await storage.secureRemove(TOKEN_KEY);
  await storage.removeItem(TOKEN_KIND_KEY);
}

export async function getToken(): Promise<string | null> {
  if (tokenCache !== undefined) return tokenCache;
  tokenCache = (await storage.secureGet<string>(TOKEN_KEY, "")) || null;
  return tokenCache;
}

export async function getTokenKind(): Promise<TokenKind | null> {
  if (tokenKindCache !== undefined) return tokenKindCache;
  const v = await storage.getItem<string>(TOKEN_KIND_KEY, "");
  tokenKindCache = (v as TokenKind) || null;
  return tokenKindCache;
}

/** Publish the active floor synchronously so requests never wait on storage. */
export function setRequestFloorId(floorId: string) {
  if (floorCache !== floorId) responseCache.clear();
  floorCache = floorId;
}

export function clearApiResponseCache() {
  responseCache.clear();
}

async function getRequestFloorId() {
  if (floorCache !== undefined) return floorCache || "";
  floorCache = (await storage.getItem<string>(SELECTED_FLOOR_KEY, "")) || "";
  return floorCache;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

type RequestOptions = { floorId?: string; signal?: AbortSignal; cacheMs?: number };

async function request<T>(method: string, path: string, body?: any, opts?: RequestOptions): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const floorId = opts?.floorId ?? (await getRequestFloorId());
  if (floorId) headers["X-Floor-Id"] = floorId;

  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);
  const abortFromCaller = () => controller.abort();
  if (opts?.signal) {
    if (opts.signal.aborted) controller.abort();
    else opts.signal.addEventListener("abort", abortFromCaller, { once: true });
  }

  try {
    const res = await fetch(`${BASE}/api${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    const text = await res.text();
    let data: unknown = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        if (res.ok) throw new ApiError(502, "The server returned an invalid response. Please try again.");
      }
    }
    if (!res.ok) {
      const detail = data && typeof data === "object" && "detail" in data
        ? (data as { detail?: unknown }).detail
        : text || `HTTP ${res.status}`;
      throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data as T;
  } catch (error) {
    if (timedOut) {
      throw new ApiError(408, "Request timed out. Please try again.");
    }
    // Fetch reports a transport failure as an unhelpful TypeError. Surface a
    // useful, actionable message instead of leaving floor screens looking as
    // though their buttons did nothing when the configured API is offline.
    if (error instanceof TypeError) {
      throw new ApiError(503, "Cannot reach the backend. Check the configured secure backend URL and try again.");
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
    opts?.signal?.removeEventListener("abort", abortFromCaller);
  }
}

export const api = {
  get: <T>(p: string, opts?: RequestOptions) => {
    // Deduplicate concurrent reads across screens/components. This is
    // intentionally in-flight only: dynamic data is never served stale, but
    // StrictMode/remounts and overlapping effects no longer hit the backend
    // twice for the same resource.
    const key = `${opts?.floorId ?? floorCache ?? "auto"}:${p}`;
    const cached = responseCache.get(key);
    if (cached && cached.expiresAt > Date.now()) return Promise.resolve(cached.value as T);
    if (cached) responseCache.delete(key);
    const existing = inflightGets.get(key);
    if (existing) return existing as Promise<T>;
    const pending = request<T>("GET", p, undefined, opts)
      .then((value) => {
        if (opts?.cacheMs && opts.cacheMs > 0) responseCache.set(key, { expiresAt: Date.now() + opts.cacheMs, value });
        return value;
      })
      .finally(() => inflightGets.delete(key));
    inflightGets.set(key, pending);
    return pending;
  },
  post: <T>(p: string, b?: any, opts?: RequestOptions) => { responseCache.clear(); return request<T>("POST", p, b, opts); },
  put: <T>(p: string, b?: any, opts?: RequestOptions) => { responseCache.clear(); return request<T>("PUT", p, b, opts); },
  patch: <T>(p: string, b?: any, opts?: RequestOptions) => { responseCache.clear(); return request<T>("PATCH", p, b, opts); },
  delete: <T>(p: string, opts?: RequestOptions) => { responseCache.clear(); return request<T>("DELETE", p, undefined, opts); },
  // Build a URL for a browser-download endpoint (PDF/xlsx). Browser
  // navigations can't send an Authorization header, so this mints a
  // short-lived single-use download token via a normal authenticated call
  // first, instead of embedding the real JWT in the URL where it would leak
  // into browser history and server access logs.
  authenticatedUrl: async (path: string): Promise<string> => {
    const target = `/api${path}`;
    const { token } = await request<{ token: string }>("POST", "/downloads/token", { target });
    const sep = path.includes("?") ? "&" : "?";
    return `${BASE}/api${path}${sep}dl=${encodeURIComponent(token)}`;
  },
  base: BASE,
};
