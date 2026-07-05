// BuilderContext
// -----------------------------------------------------------------------------
// The single source of truth for the Quotation Builder. Every mutation flows
// through this provider so undo/redo, autosave, and derived views stay in sync.
//
// Consumers grab whichever slice they need via the exported hooks:
//   * useBuilder()          full API (mutations, sheets, refs)
//   * useBuilderState()     just the undoable state
//   * useBuilderTotals()    memoised totals
//   * useBuilderRows()      flat DnD rows
//   * useHistoryApi()       history-only view
//
// Presentation components remain stateless and pluggable.
// -----------------------------------------------------------------------------
import * as Haptics from "expo-haptics";
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Platform, TextInput } from "react-native";

import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { useHistory, useUndoRedoShortcuts } from "@/src/hooks/useHistory";
import type { HistoryApi } from "@/src/hooks/useHistory";

import { computeTotals, effectivePct } from "../helpers/pricing";
import {
  BuilderRow, BuilderState, Category, Customer, DEFAULT_ROOMS, DescSheetState, DiscountSheetState,
  INITIAL_BUILDER_STATE, Line, PickerTab, Product, ProductVariant, RoomSheetState, SaveState, SwapSheetState,
} from "../helpers/types";

// -----------------------------------------------------------------------------
// Assistant selection — which line/product is currently focused in the right pane.
// -----------------------------------------------------------------------------
export type AssistantFocus =
  | { kind: "line"; line_id: string }
  | { kind: "product"; product_id: string; product: Product }
  | null;

// -----------------------------------------------------------------------------
// Context shape
// -----------------------------------------------------------------------------
export type BuilderApi = {
  // History
  history: HistoryApi<BuilderState>;
  s: BuilderState;

  // Reference data
  customers: Customer[];
  categories: Category[];
  categoryById: Record<string, string>;

  // Product picker
  q: string;
  setQ: (v: string) => void;
  pickerTab: PickerTab;
  setPickerTab: (t: PickerTab) => void;
  pickerList: Product[];
  products: Product[];
  recent: Product[];
  frequent: Product[];
  searchRef: React.MutableRefObject<TextInput | null>;

  // Derived
  totals: { subtotal: number; discount: number; grand: number };
  usedCategoryIds: string[];
  flatRows: BuilderRow[];

  // Autosave
  quotationId: string | null;
  quotationNumber: string | null;
  saveState: SaveState;
  savedAt: Date | null;
  saveLabel: string;
  persist: () => Promise<void>;
  finalize: () => Promise<void>;

  // Mutations — customers/lines
  setCustomer: (id: string) => void;
  addFromProduct: (p: Product, variant?: ProductVariant) => void;
  updateLine: (id: string, patch: Partial<Line>, coalesceKey?: string) => void;
  removeLine: (id: string) => void;
  duplicateLine: (id: string) => void;
  moveLineToNextRoom: (id: string) => void;

  // Rooms
  addRoom: (name: string) => void;
  renameRoom: (from: string, to: string) => void;
  duplicateRoom: (name: string) => void;
  deleteRoom: (name: string) => void;
  toggleCollapse: (name: string) => void;
  setActiveRoom: (name: string) => void;
  onRoomDragEnd: (payload: { data: string[] }) => void;
  onLinesDragEnd: (payload: { data: BuilderRow[] }) => void;

  // Discounts / notes
  setProjectDiscount: (n: number) => void;
  setCategoryDiscount: (cid: string, pct: number | null) => void;
  setNotes: (n: string) => void;

  // Swap
  swapItems: Product[];
  swapLoading: boolean;
  openSwap: (l: Line) => Promise<void>;
  commitSwap: (target: Product, variant?: ProductVariant) => void;
  closeSwap: () => void;

  // Sheets — modal state
  discountSheet: DiscountSheetState; setDiscountSheet: (v: DiscountSheetState) => void;
  roomSheet: RoomSheetState; setRoomSheet: (v: RoomSheetState) => void;
  roomInput: string; setRoomInput: (v: string) => void;
  descSheet: DescSheetState; setDescSheet: (v: DescSheetState) => void;
  swapSheet: SwapSheetState;

  // Mobile-only sheets (Full-screen product picker & Assistant sheet)
  pickerSheetOpen: boolean; setPickerSheetOpen: (v: boolean) => void;
  quickAddProduct: Product | null; setQuickAddProduct: (p: Product | null) => void;

  // Inline room rename
  inlineRenameRoom: string | null; setInlineRenameRoom: (v: string | null) => void;
  inlineRenameValue: string; setInlineRenameValue: (v: string) => void;

  // Assistant pane focus (right pane / mobile bottom sheet)
  assistantFocus: AssistantFocus;
  setAssistantFocus: (f: AssistantFocus) => void;
  assistantOpenMobile: boolean;
  setAssistantOpenMobile: (v: boolean) => void;
};

const Ctx = createContext<BuilderApi | null>(null);

export function useBuilder(): BuilderApi {
  const c = useContext(Ctx);
  if (!c) throw new Error("useBuilder must be used inside BuilderProvider");
  return c;
}

// -----------------------------------------------------------------------------
// Provider
// -----------------------------------------------------------------------------
export function BuilderProvider({ onFinalize, children }: {
  onFinalize?: (quotationId: string) => void;
  children: React.ReactNode;
}) {
  // Reference data — not part of undoable state.
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [recent, setRecent] = useState<Product[]>([]);
  const [frequent, setFrequent] = useState<Product[]>([]);
  const [pickerTab, setPickerTab] = useState<PickerTab>("search");
  const [q, setQ] = useState("");
  const searchRef = useRef<TextInput | null>(null);

  // Undo/redo document state
  const history = useHistory<BuilderState>(INITIAL_BUILDER_STATE, { max: 200, coalesceMs: 800 });
  const s = history.state;
  useUndoRedoShortcuts(history as any, true);

  // Autosave metadata (not undoable)
  const [quotationId, setQuotationId] = useState<string | null>(null);
  const [quotationNumber, setQuotationNumber] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sheets
  const [discountSheet, setDiscountSheet] = useState<DiscountSheetState>(null);
  const [roomSheet, setRoomSheet] = useState<RoomSheetState>(null);
  const [roomInput, setRoomInput] = useState("");
  const [descSheet, setDescSheet] = useState<DescSheetState>(null);
  const [swapSheet, setSwapSheet] = useState<SwapSheetState>(null);
  const [swapItems, setSwapItems] = useState<Product[]>([]);
  const [swapLoading, setSwapLoading] = useState(false);

  // Mobile-only sheets
  const [pickerSheetOpen, setPickerSheetOpen] = useState(false);
  const [quickAddProduct, setQuickAddProduct] = useState<Product | null>(null);

  // Inline room rename
  const [inlineRenameRoom, setInlineRenameRoom] = useState<string | null>(null);
  const [inlineRenameValue, setInlineRenameValue] = useState("");

  // Assistant pane focus
  const [assistantFocus, setAssistantFocus] = useState<AssistantFocus>(null);
  const [assistantOpenMobile, setAssistantOpenMobile] = useState(false);

  // ---------- Load reference data ----------
  useEffect(() => {
    (async () => {
      try {
        const [cs, cats, rec, freq] = await Promise.all([
          api.get<Customer[]>("/customers"),
          api.get<Category[]>("/categories"),
          api.get<Product[]>("/products/recent"),
          api.get<Product[]>("/products/frequent"),
        ]);
        setCustomers(cs);
        setCategories(cats);
        setRecent(rec);
        setFrequent(freq);
        if (cs[0] && !history.state.customerId) {
          history.replace({ ...history.state, customerId: cs[0].id });
        }
      } catch (e) {
        // Reference data failure shouldn't nuke the builder shell.
        console.warn("Failed to load builder reference data", e);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------- Product search ----------
  useEffect(() => {
    if (pickerTab !== "search") return;
    const t = setTimeout(async () => {
      try {
        const res = await api.get<{ items: Product[] }>(`/products?limit=40${q ? `&q=${encodeURIComponent(q)}` : ""}`);
        setProducts(res.items);
      } catch (e) {
        console.warn("Product search failed", e);
      }
    }, 180);
    return () => clearTimeout(t);
  }, [q, pickerTab]);

  // ---------- Autosave ----------
  const persist = useCallback(async () => {
    if (!s.customerId) return;
    const payload = {
      customer_id: s.customerId,
      items: s.lines,
      rooms: s.rooms,
      notes: s.notes,
      project_discount_pct: s.projectDiscount,
      category_discounts: s.categoryDiscounts,
    };
    try {
      setSaveState("saving");
      if (!quotationId) {
        const created = await api.post<{ id: string; number: string }>("/quotations", payload);
        setQuotationId(created.id);
        setQuotationNumber(created.number);
      } else {
        const upd: any = { ...payload, silent: true, collapsed_rooms: Object.keys(s.collapsedRooms).filter((k) => s.collapsedRooms[k]) };
        delete upd.customer_id;
        await api.patch(`/quotations/${quotationId}`, upd);
      }
      setSaveState("saved");
      setSavedAt(new Date());
    } catch (e: any) {
      setSaveState("error");
      toast.error(e?.detail || "Save failed");
    }
  }, [s, quotationId]);

  useEffect(() => {
    if (!s.customerId) return;
    if (s.lines.length === 0 && !quotationId && s.projectDiscount === 0 && Object.keys(s.categoryDiscounts).length === 0) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => { persist(); }, 900);
    return () => { if (saveTimer.current) clearTimeout(saveTimer.current); };
  }, [s, quotationId, persist]);

  // ---------- Derived ----------
  const totals = useMemo(
    () => computeTotals(s.lines, s.projectDiscount, s.categoryDiscounts),
    [s.lines, s.projectDiscount, s.categoryDiscounts],
  );

  const categoryById: Record<string, string> = useMemo(
    () => Object.fromEntries(categories.map((c) => [c.id, c.name])),
    [categories],
  );

  const usedCategoryIds = useMemo(
    () => Array.from(new Set(s.lines.map((l) => l.category_id).filter(Boolean))) as string[],
    [s.lines],
  );

  const pickerList: Product[] = pickerTab === "recent" ? recent : pickerTab === "frequent" ? frequent : products;

  const flatRows: BuilderRow[] = useMemo(() => {
    const rows: BuilderRow[] = [];
    for (const room of s.rooms) {
      const roomLines = s.lines.filter((l) => l.room === room);
      const roomSub = roomLines.reduce((sum, l) => {
        const eff = effectivePct(l, s.categoryDiscounts, s.projectDiscount);
        return sum + l.qty * l.unit_price * (1 - eff.pct / 100);
      }, 0);
      const collapsed = !!s.collapsedRooms[room];
      rows.push({ kind: "room-header", id: `hdr-${room}`, roomName: room, itemCount: roomLines.length, subtotal: roomSub, collapsed });
      if (!collapsed) for (const l of roomLines) rows.push({ kind: "line", id: l.id, line: l });
    }
    return rows;
  }, [s]);

  // ---------- Mutations ----------
  const setCustomer = useCallback((id: string) => {
    if (id === history.state.customerId) return;
    Haptics.selectionAsync();
    history.apply((cur) => ({ ...cur, customerId: id }));
  }, [history]);

  const addFromProduct = useCallback((p: Product, variant?: ProductVariant) => {
    Haptics.selectionAsync();
    history.apply((cur) => {
      const sku = variant?.sku ?? p.sku;
      const idx = cur.lines.findIndex((l) => l.sku === sku && l.room === cur.activeRoom);
      if (idx >= 0) {
        const next = [...cur.lines]; next[idx] = { ...next[idx], qty: next[idx].qty + 1 };
        return { ...cur, lines: next };
      }
      const finish = variant?.finish ?? variant?.color ?? variant?.size ?? p.finish ?? null;
      const displayName = variant && (variant.finish || variant.color || variant.size)
        ? `${p.name} · ${variant.finish || variant.color || variant.size}`
        : p.name;
      return {
        ...cur,
        lines: [...cur.lines, {
          id: `${p.id}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          product_id: p.id, sku,
          name: displayName, image: p.images?.[0],
          category_id: p.category_id, room: cur.activeRoom,
          qty: 1, unit_price: variant?.price ?? p.price,
          discount_pct: null, finish,
          family_key: p.family_key ?? null,
        }],
      };
    });
  }, [history]);

  const updateLine = useCallback((id: string, patch: Partial<Line>, coalesceKey?: string) =>
    history.apply(
      (cur) => ({ ...cur, lines: cur.lines.map((l) => (l.id === id ? { ...l, ...patch } : l)) }),
      { coalesceKey: coalesceKey ? `${coalesceKey}:${id}` : undefined },
    ),
  [history]);

  const removeLine = useCallback((id: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    history.apply((cur) => ({ ...cur, lines: cur.lines.filter((l) => l.id !== id) }));
  }, [history]);

  const duplicateLine = useCallback((id: string) => {
    Haptics.selectionAsync();
    history.apply((cur) => {
      const idx = cur.lines.findIndex((l) => l.id === id);
      if (idx < 0) return cur;
      const copy = { ...cur.lines[idx], id: `${cur.lines[idx].product_id}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}` };
      const next = [...cur.lines]; next.splice(idx + 1, 0, copy);
      return { ...cur, lines: next };
    });
  }, [history]);

  const moveLineToNextRoom = useCallback((id: string) => {
    history.apply((cur) => {
      const l = cur.lines.find((x) => x.id === id);
      if (!l) return cur;
      const idx = cur.rooms.indexOf(l.room || "");
      const nextRoom = cur.rooms[(idx + 1) % cur.rooms.length];
      return { ...cur, lines: cur.lines.map((x) => (x.id === id ? { ...x, room: nextRoom } : x)) };
    });
    Haptics.selectionAsync();
  }, [history]);

  // Rooms
  const addRoom = useCallback((name: string) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    history.apply((cur) => {
      if (cur.rooms.includes(trimmed)) return cur;
      return { ...cur, rooms: [...cur.rooms, trimmed], activeRoom: trimmed };
    });
  }, [history]);

  const renameRoom = useCallback((from: string, to: string) => {
    const trimmed = to.trim();
    if (!trimmed || trimmed === from) return;
    history.apply((cur) => {
      if (cur.rooms.includes(trimmed)) return cur;
      const rooms = cur.rooms.map((r) => (r === from ? trimmed : r));
      const lines = cur.lines.map((l) => (l.room === from ? { ...l, room: trimmed } : l));
      const collapsed = { ...cur.collapsedRooms };
      if (collapsed[from]) { collapsed[trimmed] = true; delete collapsed[from]; }
      const activeRoom = cur.activeRoom === from ? trimmed : cur.activeRoom;
      return { ...cur, rooms, lines, collapsedRooms: collapsed, activeRoom };
    });
  }, [history]);

  const duplicateRoom = useCallback((name: string) => {
    history.apply((cur) => {
      let copyName = `${name} (copy)`; let i = 2;
      while (cur.rooms.includes(copyName)) copyName = `${name} (copy ${i++})`;
      const clones = cur.lines
        .filter((l) => l.room === name)
        .map((l) => ({ ...l, id: `${l.product_id}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, room: copyName }));
      return { ...cur, rooms: [...cur.rooms, copyName], lines: [...cur.lines, ...clones], activeRoom: copyName };
    });
  }, [history]);

  const deleteRoom = useCallback((name: string) => {
    if (history.state.rooms.length <= 1) {
      toast.error("Keep at least one room");
      return;
    }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    history.apply((cur) => {
      if (cur.rooms.length <= 1) return cur;
      const rooms = cur.rooms.filter((r) => r !== name);
      const lines = cur.lines.filter((l) => l.room !== name);
      const activeRoom = cur.activeRoom === name ? (rooms[0] || DEFAULT_ROOMS[0]) : cur.activeRoom;
      const { [name]: _dropped, ...collapsed } = cur.collapsedRooms;
      return { ...cur, rooms, lines, activeRoom, collapsedRooms: collapsed };
    });
  }, [history]);

  const toggleCollapse = useCallback((name: string) =>
    history.apply((cur) => ({ ...cur, collapsedRooms: { ...cur.collapsedRooms, [name]: !cur.collapsedRooms[name] } }), { skipHistory: true }),
  [history]);

  const setActiveRoom = useCallback((name: string) =>
    history.apply((cur) => (cur.activeRoom === name ? cur : { ...cur, activeRoom: name }), { skipHistory: true }),
  [history]);

  const setProjectDiscount = useCallback((n: number) =>
    history.apply((cur) => ({ ...cur, projectDiscount: Math.max(0, Math.min(100, n)) })),
  [history]);

  const setCategoryDiscount = useCallback((cid: string, pct: number | null) =>
    history.apply((cur) => {
      const next = { ...cur.categoryDiscounts };
      if (pct == null) delete next[cid]; else next[cid] = Math.max(0, Math.min(100, pct));
      return { ...cur, categoryDiscounts: next };
    }),
  [history]);

  const setNotes = useCallback((n: string) =>
    history.apply((cur) => ({ ...cur, notes: n }), { coalesceKey: "notes" }),
  [history]);

  const onRoomDragEnd = useCallback(({ data }: { data: string[] }) =>
    history.apply((cur) => ({ ...cur, rooms: data })),
  [history]);

  const onLinesDragEnd = useCallback(({ data }: { data: BuilderRow[] }) => {
    history.apply((cur) => {
      const newLines: Line[] = [];
      let curRoom = cur.rooms[0];
      for (const row of data) {
        if (row.kind === "room-header") curRoom = row.roomName;
        else newLines.push({ ...row.line, room: curRoom });
      }
      return { ...cur, lines: newLines };
    });
  }, [history]);

  // Swap alternates
  const openSwap = useCallback(async (l: Line) => {
    setSwapSheet({ line_id: l.id, product_id: l.product_id });
    setSwapLoading(true); setSwapItems([]);
    try {
      const res = await api.get<{ items: Product[] }>(`/products/${l.product_id}/alternates?limit=20`);
      setSwapItems(res.items || []);
    } catch (e: any) {
      toast.error(e?.detail || "Could not load alternates");
    } finally {
      setSwapLoading(false);
    }
  }, []);

  const commitSwap = useCallback((target: Product, variant?: ProductVariant) => {
    const cur = swapSheet;
    if (!cur) return;
    Haptics.selectionAsync();
    history.apply((c) => {
      const idx = c.lines.findIndex((l) => l.id === cur.line_id);
      if (idx < 0) return c;
      const src = c.lines[idx];
      const finish = variant?.finish ?? variant?.color ?? variant?.size ?? target.finish ?? null;
      const displayName = variant && (variant.finish || variant.color || variant.size)
        ? `${target.name} · ${variant.finish || variant.color || variant.size}`
        : target.name;
      const next = [...c.lines];
      next[idx] = {
        ...src,
        product_id: target.id,
        sku: variant?.sku ?? target.sku,
        name: displayName,
        image: target.images?.[0] ?? src.image,
        category_id: target.category_id,
        unit_price: variant?.price ?? target.price,
        finish,
        family_key: target.family_key ?? src.family_key ?? null,
      };
      return { ...c, lines: next };
    });
    setSwapSheet(null); setSwapItems([]);
  }, [history, swapSheet]);

  const closeSwap = useCallback(() => { setSwapSheet(null); setSwapItems([]); }, []);

  // Finalize
  const finalize = useCallback(async () => {
    await persist();
    if (!quotationId) return;
    onFinalize?.(quotationId);
  }, [persist, quotationId, onFinalize]);

  // Web-only: cmd/ctrl+K focuses search
  useEffect(() => {
    if (Platform.OS !== "web") return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Save label string
  const saveLabel = saveState === "saving" ? "Saving…"
    : saveState === "error" ? "Save failed"
    : savedAt ? `Saved · ${savedAt.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`
    : "Draft — no changes yet";

  const value: BuilderApi = {
    history, s,
    customers, categories, categoryById,
    q, setQ, pickerTab, setPickerTab, pickerList, products, recent, frequent, searchRef,
    totals, usedCategoryIds, flatRows,
    quotationId, quotationNumber, saveState, savedAt, saveLabel, persist, finalize,
    setCustomer, addFromProduct, updateLine, removeLine, duplicateLine, moveLineToNextRoom,
    addRoom, renameRoom, duplicateRoom, deleteRoom, toggleCollapse, setActiveRoom, onRoomDragEnd, onLinesDragEnd,
    setProjectDiscount, setCategoryDiscount, setNotes,
    swapItems, swapLoading, openSwap, commitSwap, closeSwap,
    discountSheet, setDiscountSheet,
    roomSheet, setRoomSheet, roomInput, setRoomInput,
    descSheet, setDescSheet,
    swapSheet,
    pickerSheetOpen, setPickerSheetOpen,
    quickAddProduct, setQuickAddProduct,
    inlineRenameRoom, setInlineRenameRoom, inlineRenameValue, setInlineRenameValue,
    assistantFocus, setAssistantFocus, assistantOpenMobile, setAssistantOpenMobile,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
