// Auth store. Single React context that any screen consumes.
// Supports staff + customer email/password login, PLUS "Sign in with Google"
// (Emergent's hosted OAuth — see auth.emergentagent.com flow):
//   - web: full-page redirect, session_id lands back in the URL hash/query
//   - native: expo-web-browser auth session, session_id read from the result
import * as Linking from "expo-linking";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Platform } from "react-native";
import * as WebBrowser from "expo-web-browser";

import { api, clearToken, getToken, getTokenKind, setToken, TokenKind } from "@/src/api/client";
import { storage } from "@/src/utils/storage";

export type StaffUser = {
  id: string;
  email: string;
  full_name: string;
  role: "owner" | "admin" | "manager" | "sales" | "purchase" | "warehouse" | "accounts" | "worker";
  active: boolean;
  avatar_url?: string | null;
};

export type CustomerUser = {
  id: string;
  email: string;
  name: string;
  company?: string | null;
  tier: "retail" | "trade" | "vip";
  avatar_url?: string | null;
};

export type GoogleLoginMode = "staff" | "customer";

type AuthState = {
  loading: boolean;
  kind: TokenKind | null;
  staff: StaffUser | null;
  customer: CustomerUser | null;
  loginStaff: (email: string, password: string) => Promise<void>;
  loginCustomer: (email: string, password: string) => Promise<void>;
  loginWithGoogle: (mode: GoogleLoginMode) => Promise<void>;
  googleBusy: boolean;
  googleError: string | null;
  clearGoogleError: () => void;
  logout: () => Promise<void>;
};

const AuthCtx = createContext<AuthState | null>(null);

const PENDING_MODE_KEY = "forge.google.pending_mode";
const GOOGLE_AUTH_ORIGIN = "https://auth.emergentagent.com/";

function readSessionIdFromWebUrl(): string | null {
  if (Platform.OS !== "web" || typeof window === "undefined") return null;
  const hash = window.location.hash || "";
  const search = window.location.search || "";
  const m = hash.match(/session_id=([^&]+)/) || search.match(/session_id=([^&]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

function cleanWebUrl() {
  if (Platform.OS === "web" && typeof window !== "undefined") {
    window.history.replaceState(null, "", window.location.pathname);
  }
}

function readSessionIdFromDeepLink(url: string): string | null {
  const m = url.match(/session_id=([^&]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState<TokenKind | null>(null);
  const [staff, setStaff] = useState<StaffUser | null>(null);
  const [customer, setCustomer] = useState<CustomerUser | null>(null);
  const [googleBusy, setGoogleBusy] = useState(false);
  const [googleError, setGoogleError] = useState<string | null>(null);

  const completeGoogleLogin = useCallback(async (mode: GoogleLoginMode, sessionId: string) => {
    if (mode === "staff") {
      const res = await api.post<{ access_token: string; user: StaffUser }>("/auth/google/staff", { session_id: sessionId });
      await setToken(res.access_token, "staff");
      setKind("staff"); setStaff(res.user); setCustomer(null);
    } else {
      const res = await api.post<{ access_token: string; customer: CustomerUser }>("/auth/google/customer", { session_id: sessionId });
      await setToken(res.access_token, "customer");
      setKind("customer"); setCustomer(res.customer); setStaff(null);
    }
  }, []);

  const hydrate = useCallback(async () => {
    try {
      // 1) Returning from Google — process the one-time session_id BEFORE
      // looking at any previously-stored token, per Emergent's auth playbook.
      const webSid = readSessionIdFromWebUrl();
      if (webSid) {
        const mode = ((await storage.getItem<string>(PENDING_MODE_KEY, "")) || "staff") as GoogleLoginMode;
        await storage.removeItem(PENDING_MODE_KEY);
        cleanWebUrl();
        try {
          await completeGoogleLogin(mode, webSid);
        } catch (e: any) {
          setGoogleError(e?.detail || "Google sign-in failed.");
          setStaff(null); setCustomer(null); setKind(null);
        }
        setLoading(false);
        return;
      }
      if (Platform.OS !== "web") {
        // Cold-start fallback — app was killed and reopened via the deep link.
        const initialUrl = await Linking.getInitialURL();
        const nativeSid = initialUrl ? readSessionIdFromDeepLink(initialUrl) : null;
        if (nativeSid) {
          const mode = ((await storage.getItem<string>(PENDING_MODE_KEY, "")) || "staff") as GoogleLoginMode;
          await storage.removeItem(PENDING_MODE_KEY);
          try {
            await completeGoogleLogin(mode, nativeSid);
          } catch (e: any) {
            setGoogleError(e?.detail || "Google sign-in failed.");
            setStaff(null); setCustomer(null); setKind(null);
          }
          setLoading(false);
          return;
        }
      }

      // 2) Normal path — restore a previously-stored session.
      const token = await getToken();
      const k = await getTokenKind();
      if (!token || !k) {
        setStaff(null); setCustomer(null); setKind(null);
        return;
      }
      setKind(k);
      if (k === "staff") {
        const me = await api.get<StaffUser>("/auth/me");
        setStaff(me);
      } else {
        const me = await api.get<CustomerUser>("/auth/customer/me");
        setCustomer(me);
      }
    } catch {
      await clearToken();
      setStaff(null); setCustomer(null); setKind(null);
    } finally {
      setLoading(false);
    }
  }, [completeGoogleLogin]);

  useEffect(() => { hydrate(); }, [hydrate]);

  const loginStaff = useCallback(async (email: string, password: string) => {
    const res = await api.post<{ access_token: string; user: StaffUser }>("/auth/login", { email, password });
    await setToken(res.access_token, "staff");
    setKind("staff"); setStaff(res.user); setCustomer(null);
  }, []);

  const loginCustomer = useCallback(async (email: string, password: string) => {
    const res = await api.post<{ access_token: string; customer: CustomerUser }>("/auth/customer/login", { email, password });
    await setToken(res.access_token, "customer");
    setKind("customer"); setCustomer(res.customer); setStaff(null);
  }, []);

  const loginWithGoogle = useCallback(async (mode: GoogleLoginMode) => {
    setGoogleError(null);
    if (Platform.OS === "web") {
      await storage.setItem(PENDING_MODE_KEY, mode);
      const redirectUrl = `${window.location.origin}/`;
      const authUrl = `${GOOGLE_AUTH_ORIGIN}?redirect=${encodeURIComponent(redirectUrl)}`;
      window.location.href = authUrl; // full navigation — page reloads, hydrate() picks it up on return
      return;
    }
    setGoogleBusy(true);
    try {
      const redirectUrl = Linking.createURL("auth");
      const authUrl = `${GOOGLE_AUTH_ORIGIN}?redirect=${encodeURIComponent(redirectUrl)}`;
      await storage.setItem(PENDING_MODE_KEY, mode);
      const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
      if (result.type === "success" && result.url) {
        const sid = readSessionIdFromDeepLink(result.url);
        if (sid) await completeGoogleLogin(mode, sid);
        else setGoogleError("Google sign-in did not return a valid session.");
      }
      // result.type === "cancel"/"dismiss" — user backed out, no error shown.
    } catch (e: any) {
      setGoogleError(e?.detail || e?.message || "Google sign-in failed.");
    } finally {
      setGoogleBusy(false);
    }
  }, [completeGoogleLogin]);

  const clearGoogleError = useCallback(() => setGoogleError(null), []);

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout"); } catch { /* best-effort */ }
    await clearToken();
    setStaff(null); setCustomer(null); setKind(null);
  }, []);

  const value = useMemo(
    () => ({
      loading, kind, staff, customer, loginStaff, loginCustomer,
      loginWithGoogle, googleBusy, googleError, clearGoogleError, logout,
    }),
    [loading, kind, staff, customer, loginStaff, loginCustomer, loginWithGoogle, googleBusy, googleError, clearGoogleError, logout],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
