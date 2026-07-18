// Thin fetch wrapper with token injection.
import { storage } from "@/src/utils/storage";

const SELECTED_FLOOR_KEY = "forge.active-floor";

// Empty string ⇒ same-origin fetch. Kubernetes ingress routes `/api/*` to backend.
const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";

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

export type TokenKind = "staff" | "customer";

export async function setToken(token: string, kind: TokenKind) {
  await storage.secureSet(TOKEN_KEY, token);
  await storage.setItem(TOKEN_KIND_KEY, kind);
}

export async function clearToken() {
  await storage.secureRemove(TOKEN_KEY);
  await storage.removeItem(TOKEN_KIND_KEY);
}

export async function getToken(): Promise<string | null> {
  return (await storage.secureGet<string>(TOKEN_KEY, "")) || null;
}

export async function getTokenKind(): Promise<TokenKind | null> {
  const v = await storage.getItem<string>(TOKEN_KIND_KEY, "");
  return (v as TokenKind) || null;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

async function request<T>(method: string, path: string, body?: any): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const floorId = await storage.getItem<string>(SELECTED_FLOOR_KEY, "");
  if (floorId) headers["X-Floor-Id"] = floorId;

  const res = await fetch(`${BASE}/api${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = data?.detail || `HTTP ${res.status}`;
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data as T;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, b?: any) => request<T>("POST", p, b),
  put: <T>(p: string, b?: any) => request<T>("PUT", p, b),
  patch: <T>(p: string, b?: any) => request<T>("PATCH", p, b),
  delete: <T>(p: string) => request<T>("DELETE", p),
  // Build a URL for a browser-download endpoint (PDF/xlsx). Browser
  // navigations can't send an Authorization header, so this mints a
  // short-lived single-use download token via a normal authenticated call
  // first, instead of embedding the real JWT in the URL where it would leak
  // into browser history and server access logs.
  authenticatedUrl: async (path: string): Promise<string> => {
    const { token } = await request<{ token: string }>("POST", "/downloads/token");
    const sep = path.includes("?") ? "&" : "?";
    return `${BASE}/api${path}${sep}dl=${encodeURIComponent(token)}`;
  },
  base: BASE,
};
