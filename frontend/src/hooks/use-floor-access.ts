import { useCallback, useEffect, useState } from "react";

import { useRouter } from "expo-router";

import { api, setRequestFloorId } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { storage } from "@/src/utils/storage";

export type Floor = { id: string; name: string; slug: string };
export type FloorAccess = { all_floors: boolean; floors: Floor[]; floor_ids: string[] };

const SELECTED_FLOOR_KEY = "forge.active-floor";
let cache: FloorAccess | null = null;
let inflight: Promise<FloorAccess> | null = null;
let selectedFloorCache: string | null = null;
let selectedFloorRead: Promise<string> | null = null;
let selectedFloorPersistence: Promise<void> = Promise.resolve();
const selectedFloorListeners = new Set<(floorId: string) => void>();

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
  if (selectedFloorCache !== null) return selectedFloorCache;
  if (!selectedFloorRead) {
    selectedFloorRead = storage.getItem<string>(SELECTED_FLOOR_KEY, "").then((saved) => {
      // A floor can be selected while storage is still being read (for
      // example immediately after login). Never let that older read win over
      // the already-published in-memory selection.
      if (selectedFloorCache === null) selectedFloorCache = saved || "";
      setRequestFloorId(selectedFloorCache);
      return selectedFloorCache;
    }).finally(() => {
      selectedFloorRead = null;
    });
  }
  return selectedFloorRead;
}

export function setSelectedFloorId(id: string) {
  selectedFloorCache = id;
  setRequestFloorId(id);
  selectedFloorListeners.forEach((listener) => listener(id));

  // Publish first for instant UI updates, then serialize writes so a fast
  // sequence of floor changes cannot finish out of order in storage.
  selectedFloorPersistence = selectedFloorPersistence
    .catch(() => undefined)
    .then(async () => { await storage.setItem(SELECTED_FLOOR_KEY, id); });
  return selectedFloorPersistence;
}

export function useFloorAccess() {
  const [access, setAccess] = useState<FloorAccess | null>(cache);
  const [selectedFloorId, setSelectedFloorIdState] = useState(selectedFloorCache || "");

  useEffect(() => {
    let alive = true;
    const onSelectedFloorChange = (floorId: string) => {
      if (alive) setSelectedFloorIdState(floorId);
    };
    selectedFloorListeners.add(onSelectedFloorChange);
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
    return () => {
      alive = false;
      selectedFloorListeners.delete(onSelectedFloorChange);
    };
  }, []);

  const selectFloor = useCallback((id: string) => {
    // Only a real, accessible floor can become active — never "" (see the
    // unscoped-default note above).
    const canSelect = Boolean(
      access && access.floors.some((floor) => floor.id === id) &&
      (access.all_floors || access.floor_ids.includes(id)),
    );
    if (!canSelect) return Promise.resolve();
    return setSelectedFloorId(id);
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
  const { access, selectedFloorId, selectFloor } = useFloorAccess();
  const router = useRouter();
  useEffect(() => {
    if (!access) return; // still loading — nothing to enforce yet
    const allowed = access.all_floors || access.floor_ids.includes(floorId);
    if (!allowed) {
      toast.error("You don't have access to that floor");
      router.replace("/(admin)/dashboard" as any);
      return;
    }
    // Update both persistence and the live shell state. Persisting only here
    // left the direct-link quotation builder mounted under the previous floor
    // until a later remount, so its nav and request scope could disagree.
    if (selectedFloorId !== floorId) void selectFloor(floorId);
  }, [access, floorId, router, selectedFloorId, selectFloor]);
}
