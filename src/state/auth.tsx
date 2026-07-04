// Auth store. Single React context that any screen consumes.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, clearToken, getToken, getTokenKind, setToken, TokenKind } from "@/src/api/client";

export type StaffUser = {
  id: string;
  email: string;
  full_name: string;
  role: "owner" | "admin" | "manager" | "sales" | "purchase" | "warehouse" | "accounts" | "worker";
  active: boolean;
};

export type CustomerUser = {
  id: string;
  email: string;
  name: string;
  company?: string | null;
  tier: "retail" | "trade" | "vip";
};

type AuthState = {
  loading: boolean;
  kind: TokenKind | null;
  staff: StaffUser | null;
  customer: CustomerUser | null;
  loginStaff: (email: string, password: string) => Promise<void>;
  loginCustomer: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState<TokenKind | null>(null);
  const [staff, setStaff] = useState<StaffUser | null>(null);
  const [customer, setCustomer] = useState<CustomerUser | null>(null);

  const hydrate = useCallback(async () => {
    try {
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
  }, []);

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

  const logout = useCallback(async () => {
    await clearToken();
    setStaff(null); setCustomer(null); setKind(null);
  }, []);

  const value = useMemo(
    () => ({ loading, kind, staff, customer, loginStaff, loginCustomer, logout }),
    [loading, kind, staff, customer, loginStaff, loginCustomer, logout],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
