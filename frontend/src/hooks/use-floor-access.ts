import { useCallback, useEffect, useState } from "react";

import { useRouter } from "expo-router";

import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { storage } from "@/src/utils/storage";

export type Floor = { id: string; name: string; slug: string };
export type FloorAccess = { all_floors: boolean; floors: Floor[]; floor_ids: string[] };

const SELECTED_FLOOR_KEY = "forge.active-floor";
let cache: FloorAccess | null = null;
let inflight: Promise<FloorAccess> | null = null;

async function loadAccess() {
  if (cache) return cache;
  if (!inflight) {
    inflight = api.get<FloorAccess>("/settings/floor-access").then((value) => {
      cache = value;
      inflight = null;
      return value;
    }).catch((error) => {
      inflight = null;
      throw error;
    });
  }
  return inflight;
}

export async function getSelectedFloorId() {
  return (await storage.getItem<string>(SELECTED_FLOOR_KEY, "")) || "";
}

export async function setSelectedFloorId(id: string) {
  await storage.setItem(SELECTED_FLOOR_KEY, id);
}

export function useFloorAccess() {
  const [access, setAccess] = useState<FloorAccess | null>(cache);
  const [selectedFloorId, setSelectedFloorIdState] = useState("");

  useEffect(() => {
    let alive = true;
    Promise.all([loadAccess(), getSelectedFloorId()]).then(([value, saved]) => {
      if (!alive) return;
      setAccess(value);
      // Everyone — including all-floor owners/managers — always has exactly
      // one concrete floor active. The old unscoped ("") default sent no
      // X-Floor-Id header, so every scoped query ran unfiltered and mixed
      // both business units' records together. A saved choice wins if it is
      // still a floor this account can access.
      const fallback = value.floors[0]?.id || "";
      const valid = saved && value.floor_ids.includes(saved) ? saved : fallback;
      setSelectedFloorIdState(valid);
      if (valid !== saved) void setSelectedFloorId(valid);
    }).catch(() => { if (alive) setAccess(null); });
    return () => { alive = false; };
  }, []);

  const selectFloor = useCallback(async (id: string) => {
    // Only a real, accessible floor can become active — never "" (see the
    // unscoped-default note above).
    if (!access?.floor_ids.includes(id)) return;
    await setSelectedFloorId(id);
    setSelectedFloorIdState(id);
  }, [access]);

  return { access, floors: access?.floors || [], selectedFloorId, selectFloor };
}

/** Gate a floor-specific screen, and make that floor the active one.
 *
 * Persisting the active floor matters as much as the access check: a
 * screen reached by direct URL, refresh or bookmark never went through the
 * sidebar link that switches floors, so the sticky selection could still
 * point at another business unit while its records were being written
 * (that is how tile documents ended up stamped `first-floor`). */
export function useRequireFloorAccess(floorId: string) {
  const { access } = useFloorAccess();
  const router = useRouter();
  useEffect(() => {
    if (!access) return; // still loading — nothing to enforce yet
    const allowed = access.all_floors || access.floor_ids.includes(floorId);
    if (!allowed) {
      toast.error("You don't have access to that floor");
      router.replace("/(admin)/dashboard" as any);
      return;
    }
    void getSelectedFloorId().then((current) => {
      if (current !== floorId) void setSelectedFloorId(floorId);
    });
  }, [access, floorId, router]);
}
