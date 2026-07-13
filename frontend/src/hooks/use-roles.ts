// useRoles — fetches the assignable role list from GET /api/roles so no
// screen ever hardcodes a role array. Cached in-memory for the process
// lifetime (roles change rarely; Team/Permissions screens call refresh()
// after any edit if they want to be extra safe, but it's not required).
import { useCallback, useEffect, useState } from "react";

import { api } from "@/src/api/client";

export type RoleInfo = {
  role: string;
  label: string;
  level: number;
  capabilities: string[];
};

let cache: RoleInfo[] | null = null;
let inflight: Promise<RoleInfo[]> | null = null;

async function fetchRoles(): Promise<RoleInfo[]> {
  if (cache) return cache;
  if (!inflight) {
    inflight = api.get<RoleInfo[]>("/roles").then((list) => {
      cache = list;
      inflight = null;
      return list;
    }).catch((e) => {
      inflight = null;
      throw e;
    });
  }
  return inflight;
}

export function useRoles() {
  const [roles, setRoles] = useState<RoleInfo[] | null>(cache);
  const [loading, setLoading] = useState(!cache);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await fetchRoles();
      setRoles(list);
      setError(null);
    } catch (e: any) {
      setError(e?.detail || "Could not load roles");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const labelFor = useCallback(
    (role: string) => roles?.find((r) => r.role === role)?.label || role,
    [roles],
  );

  return { roles: roles || [], loading, error, refresh: load, labelFor };
}
