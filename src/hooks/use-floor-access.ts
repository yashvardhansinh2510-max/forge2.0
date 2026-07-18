import { useCallback, useEffect, useState } from "react";

import { api } from "@/src/api/client";
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
      // All-floor staff default to the unscoped view (""); restricted staff
      // default to their first assigned floor. A saved choice wins if still valid.
      const fallback = value.all_floors ? "" : value.floors[0]?.id || "";
      const valid = saved && value.floor_ids.includes(saved) ? saved : fallback;
      setSelectedFloorIdState(valid);
      if (valid !== saved) void setSelectedFloorId(valid);
    }).catch(() => { if (alive) setAccess(null); });
    return () => { alive = false; };
  }, []);

  const selectFloor = useCallback(async (id: string) => {
    const allFloors = id === "" && access?.all_floors;
    if (!allFloors && !access?.floor_ids.includes(id)) return;
    await setSelectedFloorId(id);
    setSelectedFloorIdState(id);
  }, [access]);

  return { access, floors: access?.floors || [], selectedFloorId, selectFloor };
}
