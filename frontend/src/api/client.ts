// Thin fetch wrapper with token injection.
import { storage } from "@/src/utils/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;
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
  patch: <T>(p: string, b?: any) => request<T>("PATCH", p, b),
  delete: <T>(p: string) => request<T>("DELETE", p),
  pdfUrl: (path: string, token: string) => `${BASE}/api${path}?_t=${encodeURIComponent(token)}`,
  base: BASE,
};
