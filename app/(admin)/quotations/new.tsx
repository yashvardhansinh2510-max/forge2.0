// Forge Quotation Builder 2.0 · Phase 1A
// -----------------------------------------------------------------------------
// Every mutation flows through a single `useHistory` snapshot so undo/redo
// covers add/remove products, drag-reorder, room ops, price edits, qty edits,
// discount changes, customer swap, variant selection, alternate swaps, notes,
// room names — everything a salesperson can touch.
//
// Cross-platform DnD via `react-native-draggable-flatlist` for both the room
// chip row (horizontal) and the flat line list (which mixes room headers and
// lines so dragging a line across headers changes its room automatically).
//
// Variants appear as a compact swatch strip on picker rows; alternates load on
// demand from `/api/products/{id}/alternates` (smart-mix ranked family →
// brand+category → category).
//
// Keyboard on web: Cmd/Ctrl+Z / Cmd/Ctrl+Shift+Z / Cmd/Ctrl+K.
// -----------------------------------------------------------------------------
import { Feather } from "@expo/vector-icons";
import { Image } from "expo-image";
import * as Haptics from "expo-haptics";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator, FlatList, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet,
  Text, TextInput, useWindowDimensions, View,
} from "react-native";
import DraggableFlatList, { RenderItemParams, ScaleDecorator } from "react-native-draggable-flatlist";

// Web-only "grab" cursor hint on drag handles. Silently ignored on native.
const grabCursor: any = Platform.OS === "web" ? { cursor: "grab" } : null;

import { BottomSheet } from "@/src/components/BottomSheet";
import { Badge, Button, EmptyState, StatusBadge } from "@/src/components/ui";
import { toast } from "@/src/components/Toast";
import { api } from "@/src/api/client";
import { useHistory, useUndoRedoShortcuts } from "@/src/hooks/useHistory";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

// ---------- Types ----------
type ProductVariant = {
  sku: string; finish?: string | null; size?: string | null; color?: string | null;
  mrp: number; price: number; stock?: number;
};
type Product = {
  id: string; name: string; sku: string; price: number; mrp: number;
  finish?: string | null; images: string[]; category_id: string; brand_id: string;
  variants?: ProductVariant[];
};
type Category = { id: string; name: string };
type Customer = { id: string; name: string; company?: string | null; email: string };
type Line = {
  id: string; product_id: string; sku: string; name: string; image?: string | null;
  category_id?: string | null; room?: string;
  qty: number; unit_price: number;
  discount_pct: number | null;
  tax_pct: number; description?: string | null; notes?: string | null;
  finish?: string | null;
};
type SaveState = "idle" | "saving" | "saved" | "error";

// One immutable snapshot of everything the user can undo.
type BuilderState = {
  customerId: string | null;
  lines: Line[];
  rooms: string[];
  collapsedRooms: Record<string, boolean>;
  activeRoom: string;
  notes: string;
  projectDiscount: number;
  categoryDiscounts: Record<string, number>;
};

const DEFAULT_ROOMS = ["Master Bath", "Powder Room", "Guest Bath", "Kitchen", "Utility", "Living", "Study"];

const INITIAL_STATE: BuilderState = {
  customerId: null,
  lines: [],
  rooms: [DEFAULT_ROOMS[0]],
  collapsedRooms: {},
  activeRoom: DEFAULT_ROOMS[0],
  notes: "",
  projectDiscount: 0,
  categoryDiscounts: {},
};

// ---------- Pure helpers ----------
function effectivePct(l: Line, catDiscs: Record<string, number>, projPct: number): { pct: number; source: string } {
  if (l.discount_pct != null) return { pct: l.discount_pct, source: "product" };
  if (l.category_id && catDiscs[l.category_id] != null) return { pct: catDiscs[l.category_id], source: "category" };
  if (projPct) return { pct: projPct, source: "project" };
  return { pct: 0, source: "none" };
}

// Approximate swatch colour from a finish label. Kept deliberately small — we
// fall back to a neutral chrome tone when we don't recognise the finish.
function finishSwatch(finish?: string | null): string {
  const f = (finish || "").toLowerCase();
  if (!f) return "#c5c8cc";
  if (f.includes("matt black") || f.includes("matte black") || f.includes(" black")) return "#111214";
  if (f.includes("chrome")) return "#c5c8cc";
  if (f.includes("brushed") && f.includes("brass")) return "#a37f38";
  if (f.includes("brass") || f.includes("gold")) return "#d4a94b";
  if (f.includes("copper")) return "#b87333";
  if (f.includes("bronze")) return "#8a5a2b";
  if (f.includes("nickel")) return "#a5a5a8";
  if (f.includes("stone") || f.includes("grey") || f.includes("gray")) return "#8a8a8f";
  if (f.includes("taupe")) return "#7f6f5b";
  if (f.includes("white")) return "#f6f6f7";
  return "#c5c8cc";
}

// Priority label for a line's discount source
function sourceBadge(source: string): { tone: "info" | "success" | "warning"; label: string } | null {
  if (source === "category") return { tone: "info", label: "Cat" };
  if (source === "project") return { tone: "success", label: "Proj" };
  return null;
}

// ---------- Component ----------
export default function QuotationBuilder() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;
  const isDesktop = width >= 1280;

  // Reference data — not part of undoable state.
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [recent, setRecent] = useState<Product[]>([]);
  const [frequent, setFrequent] = useState<Product[]>([]);
  const [pickerTab, setPickerTab] = useState<"search" | "recent" | "frequent">("search");
  const [q, setQ] = useState("");
  const searchRef = useRef<TextInput | null>(null);

  // Undo/redo document state
  const history = useHistory<BuilderState>(INITIAL_STATE, { max: 200, coalesceMs: 800 });
  const s = history.state;
  useUndoRedoShortcuts(history as any, true);

  // Autosave metadata (not undoable)
  const [quotationId, setQuotationId] = useState<string | null>(null);
  const [quotationNumber, setQuotationNumber] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Panel/mobile tab
  const [tab, setTab] = useState<"catalog" | "receipt">("receipt");

  // Sheets
  const [discountSheet, setDiscountSheet] = useState<null | { kind: "project" } | { kind: "category"; category_id: string } | { kind: "line"; line_id: string }>(null);
  const [roomSheet, setRoomSheet] = useState<null | { kind: "add" } | { kind: "rename"; name: string }>(null);
  const [roomInput, setRoomInput] = useState("");
  const [descSheet, setDescSheet] = useState<null | { line_id: string }>(null);
  const [swapSheet, setSwapSheet] = useState<null | { line_id: string; product_id: string }>(null);
  const [swapItems, setSwapItems] = useState<Product[]>([]);
  const [swapLoading, setSwapLoading] = useState(false);

  // Inline room rename — when set, that room header renders a TextInput instead
  // of its label. Escape or blur cancels; Enter commits via `renameRoom`.
  const [inlineRenameRoom, setInlineRenameRoom] = useState<string | null>(null);
  const [inlineRenameValue, setInlineRenameValue] = useState("");

  // ---------- Load reference data ----------
  useEffect(() => {
    (async () => {
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
      if (cs[0] && !s.customerId) {
        history.replace({ ...history.state, customerId: cs[0].id });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------- Product search ----------
  useEffect(() => {
    if (pickerTab !== "search") return;
    const t = setTimeout(async () => {
      const res = await api.get<{ items: Product[] }>(`/products?limit=40${q ? `&q=${encodeURIComponent(q)}` : ""}`);
      setProducts(res.items);
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
  const totals = useMemo(() => {
    let sub = 0, disc = 0, tax = 0;
    for (const l of s.lines) {
      const gross = l.qty * l.unit_price;
      const { pct } = effectivePct(l, s.categoryDiscounts, s.projectDiscount);
      const d = gross * pct / 100;
      const net = gross - d;
      const t = net * (l.tax_pct || 0) / 100;
      sub += gross; disc += d; tax += t;
    }
    return { subtotal: sub, discount: disc, tax, grand: Math.round((sub - disc + tax) * 100) / 100 };
  }, [s.lines, s.projectDiscount, s.categoryDiscounts]);

  const catNameById: Record<string, string> = useMemo(
    () => Object.fromEntries(categories.map((c) => [c.id, c.name])),
    [categories],
  );
  const usedCategoryIds = Array.from(new Set(s.lines.map((l) => l.category_id).filter(Boolean))) as string[];
  const pickerList: Product[] = pickerTab === "recent" ? recent : pickerTab === "frequent" ? frequent : products;

  // ---------- Mutation helpers (all go through history.apply) ----------
  const setCustomer = (id: string) => {
    if (id === s.customerId) return;
    Haptics.selectionAsync();
    history.apply((cur) => ({ ...cur, customerId: id }));
  };

  const addFromProduct = (p: Product, variant?: ProductVariant) => {
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
          discount_pct: null, tax_pct: 18, finish,
        }],
      };
    });
  };

  const updateLine = (id: string, patch: Partial<Line>, coalesceKey?: string) =>
    history.apply(
      (cur) => ({ ...cur, lines: cur.lines.map((l) => (l.id === id ? { ...l, ...patch } : l)) }),
      { coalesceKey: coalesceKey ? `${coalesceKey}:${id}` : undefined },
    );

  const removeLine = (id: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    history.apply((cur) => ({ ...cur, lines: cur.lines.filter((l) => l.id !== id) }));
  };
  const duplicateLine = (id: string) => {
    Haptics.selectionAsync();
    history.apply((cur) => {
      const idx = cur.lines.findIndex((l) => l.id === id);
      if (idx < 0) return cur;
      const copy = { ...cur.lines[idx], id: `${cur.lines[idx].product_id}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}` };
      const next = [...cur.lines]; next.splice(idx + 1, 0, copy);
      return { ...cur, lines: next };
    });
  };
  const moveLineToNextRoom = (id: string) => {
    history.apply((cur) => {
      const l = cur.lines.find((x) => x.id === id);
      if (!l) return cur;
      const idx = cur.rooms.indexOf(l.room || "");
      const nextRoom = cur.rooms[(idx + 1) % cur.rooms.length];
      return { ...cur, lines: cur.lines.map((x) => (x.id === id ? { ...x, room: nextRoom } : x)) };
    });
    Haptics.selectionAsync();
  };

  // Rooms
  const addRoom = (name: string) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    history.apply((cur) => {
      if (cur.rooms.includes(trimmed)) return cur;
      return { ...cur, rooms: [...cur.rooms, trimmed], activeRoom: trimmed };
    });
  };
  const renameRoom = (from: string, to: string) => {
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
  };
  const duplicateRoom = (name: string) => {
    history.apply((cur) => {
      let copyName = `${name} (copy)`; let i = 2;
      while (cur.rooms.includes(copyName)) copyName = `${name} (copy ${i++})`;
      const clones = cur.lines
        .filter((l) => l.room === name)
        .map((l) => ({ ...l, id: `${l.product_id}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, room: copyName }));
      return { ...cur, rooms: [...cur.rooms, copyName], lines: [...cur.lines, ...clones], activeRoom: copyName };
    });
  };
  const deleteRoom = (name: string) => {
    if (s.rooms.length <= 1) {
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
  };
  const toggleCollapse = (name: string) =>
    // Collapse toggles are UI state — skip history so undo doesn't rewind them.
    history.apply((cur) => ({ ...cur, collapsedRooms: { ...cur.collapsedRooms, [name]: !cur.collapsedRooms[name] } }), { skipHistory: true });
  const setActiveRoom = (name: string) =>
    history.apply((cur) => (cur.activeRoom === name ? cur : { ...cur, activeRoom: name }), { skipHistory: true });

  // Discounts
  const setProjectDiscount = (n: number) =>
    history.apply((cur) => ({ ...cur, projectDiscount: Math.max(0, Math.min(100, n)) }));
  const setCategoryDiscount = (cid: string, pct: number | null) =>
    history.apply((cur) => {
      const next = { ...cur.categoryDiscounts };
      if (pct == null) delete next[cid]; else next[cid] = Math.max(0, Math.min(100, pct));
      return { ...cur, categoryDiscounts: next };
    });

  // Notes — inline in footer, coalesced so a paragraph of typing = one undo entry.
  const setNotes = (n: string) => history.apply((cur) => ({ ...cur, notes: n }), { coalesceKey: "notes" });

  // DnD — reorder rooms (horizontal)
  const onRoomDragEnd = ({ data }: { data: string[] }) =>
    history.apply((cur) => ({ ...cur, rooms: data }));

  // DnD — reorder flat rows (mixed room-headers + lines).
  const onLinesDragEnd = ({ data }: { data: BuilderRow[] }) => {
    history.apply((cur) => {
      const newLines: Line[] = [];
      let curRoom = cur.rooms[0];
      for (const row of data) {
        if (row.kind === "room-header") curRoom = row.roomName;
        else newLines.push({ ...row.line, room: curRoom });
      }
      return { ...cur, lines: newLines };
    });
  };

  // Swap alternates
  const openSwap = async (l: Line) => {
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
  };
  const commitSwap = (target: Product, variant?: ProductVariant) => {
    if (!swapSheet) return;
    Haptics.selectionAsync();
    history.apply((cur) => {
      const idx = cur.lines.findIndex((l) => l.id === swapSheet.line_id);
      if (idx < 0) return cur;
      const src = cur.lines[idx];
      const finish = variant?.finish ?? variant?.color ?? variant?.size ?? target.finish ?? null;
      const displayName = variant && (variant.finish || variant.color || variant.size)
        ? `${target.name} · ${variant.finish || variant.color || variant.size}`
        : target.name;
      const next = [...cur.lines];
      next[idx] = {
        ...src, // preserves qty, discount_pct, tax_pct, notes, description, room
        product_id: target.id,
        sku: variant?.sku ?? target.sku,
        name: displayName,
        image: target.images?.[0] ?? src.image,
        category_id: target.category_id,
        unit_price: variant?.price ?? target.price,
        finish,
      };
      return { ...cur, lines: next };
    });
    setSwapSheet(null); setSwapItems([]);
  };

  // ---------- Finish ----------
  const finalize = async () => {
    await persist();
    if (!quotationId) return;
    router.replace(`/(admin)/quotations/${quotationId}` as any);
  };

  // ---------- Save status label ----------
  const saveLabel = saveState === "saving" ? "Saving…"
    : saveState === "error" ? "Save failed"
    : savedAt ? `Saved · ${savedAt.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`
    : "Draft — no changes yet";

  // ---------- Flat rows for the receipt DnD list ----------
  type BuilderRow =
    | { kind: "room-header"; id: string; roomName: string; itemCount: number; subtotal: number; collapsed: boolean }
    | { kind: "line"; id: string; line: Line };

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

  // ---------- Web: cmd/ctrl+K focuses search ----------
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

  // ---------- Renderers ----------
  const renderProductRow = ({ item }: { item: Product }) => {
    const hasVariants = (item.variants || []).length > 0;
    return (
      <View style={{ gap: 6 }}>
        <Pressable
          testID={`add-product-${item.id}`}
          onPress={() => addFromProduct(item)}
          style={({ pressed }) => [styles.pRow, { backgroundColor: pressed ? colors.surfaceTertiary : colors.surfaceSecondary }]}
        >
          {item.images?.[0] ? <Image source={{ uri: item.images[0] }} style={styles.pThumb} /> : <View style={styles.pThumb} />}
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{item.name}</Text>
            <Text style={type.caption}>{item.sku}{item.finish ? ` · ${item.finish}` : ""}</Text>
          </View>
          <Text style={[type.mono, { fontSize: 13, fontWeight: "600" }]}>{money(item.price)}</Text>
          <Feather name="plus" size={16} color={colors.brand} />
        </Pressable>
        {hasVariants ? (
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ gap: 6, paddingLeft: 54, paddingBottom: 2 }}
          >
            {(item.variants || []).map((v) => {
              const delta = (v.price ?? item.price) - item.price;
              return (
                <Pressable
                  key={v.sku}
                  testID={`add-variant-${v.sku}`}
                  onPress={() => addFromProduct(item, v)}
                  style={({ pressed }) => [styles.variantChip, pressed && { opacity: 0.85 }]}
                >
                  <View style={[styles.swatch, { backgroundColor: finishSwatch(v.finish) }]} />
                  <Text style={styles.variantChipLabel} numberOfLines={1}>
                    {v.finish || v.color || v.size || v.sku}
                  </Text>
                  {delta !== 0 ? (
                    <Text style={[styles.variantDelta, { color: delta > 0 ? colors.onSurfaceMuted : colors.success }]}>
                      {delta > 0 ? "+" : "−"}{money(Math.abs(delta))}
                    </Text>
                  ) : null}
                </Pressable>
              );
            })}
          </ScrollView>
        ) : null}
      </View>
    );
  };

  const renderRoomChipDraggable = ({ item, drag, isActive }: RenderItemParams<string>) => {
    const active = s.activeRoom === item;
    return (
      <ScaleDecorator>
        <Pressable
          onLongPress={drag}
          delayLongPress={160}
          onPress={() => setActiveRoom(item)}
          testID={`room-${item}`}
          style={[styles.roomTab, active && styles.roomTabActive, isActive && { opacity: 0.7 }, grabCursor]}
        >
          <Feather name="menu" size={11} color={active ? colors.onBrand : colors.onSurfaceMuted} style={{ opacity: 0.7, marginRight: 4 }} />
          <Text style={{ fontSize: 12, fontWeight: "600", color: active ? colors.onBrand : colors.onSurfaceSecondary }}>{item}</Text>
        </Pressable>
      </ScaleDecorator>
    );
  };

  const renderReceiptRow = ({ item, drag, isActive }: RenderItemParams<BuilderRow>) => {
    if (item.kind === "room-header") {
      const isActiveRoom = s.activeRoom === item.roomName;
      const isRenaming = inlineRenameRoom === item.roomName;
      const commitInlineRename = () => {
        if (inlineRenameRoom) renameRoom(inlineRenameRoom, inlineRenameValue);
        setInlineRenameRoom(null);
      };
      return (
        <View style={[styles.roomHeader, isActiveRoom && { borderColor: colors.brand }, isActive && { opacity: 0.7 }]}>
          <Pressable
            onLongPress={drag}
            delayLongPress={160}
            hitSlop={6}
            style={[styles.dragHandle, grabCursor]}
            testID={`room-drag-${item.roomName}`}
          >
            <Feather name="menu" size={13} color={colors.onSurfaceMuted} />
          </Pressable>
          <Pressable onPress={() => toggleCollapse(item.roomName)} testID={`room-toggle-${item.roomName}`} hitSlop={6}>
            <Feather name={item.collapsed ? "chevron-right" : "chevron-down"} size={16} color={colors.onSurface} />
          </Pressable>
          {isRenaming ? (
            <TextInput
              testID={`room-inline-input-${item.roomName}`}
              value={inlineRenameValue}
              onChangeText={setInlineRenameValue}
              autoFocus
              onBlur={commitInlineRename}
              onSubmitEditing={commitInlineRename}
              onKeyPress={(e) => { if ((e.nativeEvent as any).key === "Escape") setInlineRenameRoom(null); }}
              returnKeyType="done"
              style={styles.inlineRoomInput}
              selectTextOnFocus
            />
          ) : (
            <Pressable onPress={() => setActiveRoom(item.roomName)} style={{ flex: 1 }}>
              <Text style={{ fontSize: 14, fontWeight: "700", color: colors.onSurface }}>{item.roomName}</Text>
              <Text style={type.caption}>{item.itemCount} items · {money(item.subtotal)}</Text>
            </Pressable>
          )}
          <Pressable
            testID={`room-rename-${item.roomName}`}
            hitSlop={8}
            onPress={() => {
              if (isRenaming) commitInlineRename();
              else { setInlineRenameRoom(item.roomName); setInlineRenameValue(item.roomName); }
            }}
          >
            <Feather name={isRenaming ? "check" : "edit-2"} size={14} color={isRenaming ? colors.brand : colors.onSurfaceMuted} />
          </Pressable>
          <Pressable testID={`room-dup-${item.roomName}`} hitSlop={8} onPress={() => duplicateRoom(item.roomName)}>
            <Feather name="copy" size={14} color={colors.onSurfaceMuted} />
          </Pressable>
          <Pressable testID={`room-delete-${item.roomName}`} hitSlop={8} onPress={() => deleteRoom(item.roomName)}>
            <Feather name="trash-2" size={14} color={colors.error} />
          </Pressable>
        </View>
      );
    }

    const l = item.line;
    const eff = effectivePct(l, s.categoryDiscounts, s.projectDiscount);
    const badge = sourceBadge(eff.source);
    const total = l.qty * l.unit_price * (1 - eff.pct / 100);
    return (
      <View style={[styles.lineRow, isActive && { opacity: 0.75, transform: [{ scale: 0.99 }] }]}>
        <Pressable
          onLongPress={drag}
          delayLongPress={160}
          hitSlop={6}
          style={[styles.dragHandle, grabCursor]}
          testID={`line-drag-${l.id}`}
        >
          <Feather name="menu" size={14} color={colors.onSurfaceMuted} />
        </Pressable>
        {l.image ? <Image source={{ uri: l.image }} style={styles.lineThumb} /> : <View style={styles.lineThumb} />}
        <View style={{ flex: 1, gap: 4 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface, flex: 1 }} numberOfLines={1}>{l.name}</Text>
            {l.finish ? <View style={[styles.swatch, { backgroundColor: finishSwatch(l.finish), width: 10, height: 10, borderWidth: 0.5 }]} /> : null}
            {badge ? <Badge tone={badge.tone} label={badge.label} /> : null}
          </View>
          <Text style={type.caption}>{l.sku}</Text>
          {l.description ? <Text style={type.caption} numberOfLines={2}>{l.description}</Text> : null}
          <View style={{ flexDirection: "row", gap: 6, marginTop: 2, flexWrap: "wrap" }}>
            <View style={styles.inputMini}>
              <Text style={styles.inputLabel}>QTY</Text>
              <TextInput
                testID={`qty-${l.id}`}
                value={String(l.qty)}
                keyboardType="number-pad"
                onChangeText={(v) => updateLine(l.id, { qty: Math.max(0, Number(v) || 0) }, "qty")}
                style={styles.inputVal}
                selectTextOnFocus
              />
            </View>
            <View style={styles.inputMini}>
              <Text style={styles.inputLabel}>RATE</Text>
              <TextInput
                testID={`rate-${l.id}`}
                value={String(l.unit_price)}
                keyboardType="decimal-pad"
                onChangeText={(v) => updateLine(l.id, { unit_price: Number(v) || 0 }, "rate")}
                style={styles.inputVal}
                selectTextOnFocus
              />
            </View>
            <Pressable
              testID={`disc-${l.id}`}
              onPress={() => setDiscountSheet({ kind: "line", line_id: l.id })}
              style={[styles.inputMini, { justifyContent: "center", flexDirection: "row", alignItems: "center", gap: 4 }]}
            >
              <Text style={styles.inputLabel}>DISC</Text>
              <Text style={styles.inputVal}>{eff.pct}%</Text>
              {l.discount_pct == null && eff.source !== "none" ? <Feather name="link" size={9} color={colors.onSurfaceMuted} /> : null}
            </Pressable>

            <Pressable testID={`line-desc-${l.id}`} onPress={() => setDescSheet({ line_id: l.id })} style={styles.lineIcon}>
              <Feather name="align-left" size={13} color={colors.onSurfaceMuted} />
            </Pressable>
            <Pressable testID={`line-swap-${l.id}`} onPress={() => openSwap(l)} style={styles.lineIcon}>
              <Feather name="refresh-cw" size={13} color={colors.onSurfaceMuted} />
            </Pressable>
            <Pressable testID={`line-dup-${l.id}`} onPress={() => duplicateLine(l.id)} style={styles.lineIcon}>
              <Feather name="copy" size={13} color={colors.onSurfaceMuted} />
            </Pressable>
            <Pressable testID={`line-move-${l.id}`} onPress={() => moveLineToNextRoom(l.id)} style={styles.lineIcon}>
              <Feather name="corner-up-right" size={13} color={colors.onSurfaceMuted} />
            </Pressable>
            <Pressable testID={`line-del-${l.id}`} onPress={() => removeLine(l.id)} style={styles.lineIcon}>
              <Feather name="trash-2" size={13} color={colors.error} />
            </Pressable>
          </View>
        </View>
        <Text style={[type.mono, { fontSize: 13, fontWeight: "700" }]}>{money(total)}</Text>
      </View>
    );
  };

  const CatalogPanel = (
    <View style={styles.panel}>
      <View style={styles.panelHead}>
        <Text style={type.titleMd}>Add products</Text>
        <View style={styles.searchWrap}>
          <Feather name="search" size={16} color={colors.onSurfaceMuted} />
          <TextInput
            ref={searchRef}
            testID="builder-search"
            value={q}
            onChangeText={(v) => { setQ(v); setPickerTab("search"); }}
            placeholder={Platform.OS === "web" ? "Search catalog · ⌘K to focus · Enter to add" : "Search catalog · Enter to add first"}
            placeholderTextColor={colors.onSurfaceMuted}
            style={styles.searchInput}
            onSubmitEditing={() => pickerList[0] && addFromProduct(pickerList[0])}
          />
        </View>
        <View style={styles.pickerTabs}>
          {[
            { k: "search" as const, label: "All", icon: "search" as const },
            { k: "recent" as const, label: "Recent", icon: "clock" as const },
            { k: "frequent" as const, label: "Frequent", icon: "star" as const },
          ].map((t) => (
            <Pressable
              key={t.k}
              testID={`picker-tab-${t.k}`}
              onPress={() => setPickerTab(t.k)}
              style={[styles.pickerTab, pickerTab === t.k && styles.pickerTabActive]}
            >
              <Feather name={t.icon} size={12} color={pickerTab === t.k ? colors.onBrand : colors.onSurfaceMuted} />
              <Text style={{ fontSize: 12, fontWeight: "600", color: pickerTab === t.k ? colors.onBrand : colors.onSurfaceSecondary }}>{t.label}</Text>
            </Pressable>
          ))}
        </View>
      </View>
      <FlatList
        data={pickerList}
        keyExtractor={(p) => p.id}
        contentContainerStyle={{ padding: spacing.md, gap: 8 }}
        renderItem={renderProductRow}
        ListEmptyComponent={
          <EmptyState
            icon={pickerTab === "search" ? "search" : pickerTab === "recent" ? "clock" : "star"}
            title={pickerTab === "search" ? "Type to search" : pickerTab === "recent" ? "No recent products" : "No favourites yet"}
            subtitle={pickerTab === "search" ? "Search across brands, SKUs and tags." : "Add products to a quotation to see them here."}
          />
        }
      />
    </View>
  );

  const ReceiptPanel = (
    <View style={[styles.panel, { backgroundColor: colors.surfaceSecondary }]}>
      <View style={styles.panelHead}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <View>
            <Text style={type.titleMd}>{quotationNumber || "New Quotation"}</Text>
            <View style={{ flexDirection: "row", gap: 6, alignItems: "center", marginTop: 2 }}>
              {saveState === "saving" ? <ActivityIndicator size="small" color={colors.onSurfaceMuted} /> : null}
              <Text style={[type.caption, { color: saveState === "error" ? colors.error : colors.onSurfaceMuted }]} testID="save-status">{saveLabel}</Text>
            </View>
          </View>
          <StatusBadge status="draft" />
        </View>

        {/* Customer picker */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 2 }}>
          {customers.map((c) => (
            <Pressable
              key={c.id}
              testID={`cust-${c.id}`}
              onPress={() => setCustomer(c.id)}
              style={[styles.custChip, s.customerId === c.id && styles.custChipActive]}
            >
              <Text style={{ fontSize: 12, fontWeight: "600", color: s.customerId === c.id ? colors.onBrand : colors.onSurface }}>
                {c.company || c.name}
              </Text>
            </Pressable>
          ))}
        </ScrollView>

        {/* Room chips — horizontal drag reorder */}
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <View style={{ flex: 1 }}>
            <DraggableFlatList
              data={s.rooms}
              horizontal
              keyExtractor={(r) => r}
              onDragEnd={onRoomDragEnd}
              renderItem={renderRoomChipDraggable}
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ gap: 6, paddingVertical: 2 }}
              activationDistance={8}
            />
          </View>
          <Pressable
            onPress={() => { setRoomInput(""); setRoomSheet({ kind: "add" }); }}
            testID="add-room-btn"
            style={[styles.roomTab, { borderStyle: "dashed", paddingHorizontal: 10 }]}
          >
            <Feather name="plus" size={13} color={colors.onSurfaceMuted} />
          </Pressable>
        </View>
      </View>

      {/* Receipt DnD list — mixes headers and lines */}
      <View style={{ flex: 1 }}>
        {flatRows.length === 0 || (flatRows.length <= s.rooms.length && s.lines.length === 0) ? (
          <EmptyState icon="file-plus" title="Add your first product" subtitle="Search on the left and tap to add. Everything totals live." />
        ) : (
          <DraggableFlatList
            data={flatRows}
            keyExtractor={(row) => row.id}
            onDragEnd={onLinesDragEnd}
            renderItem={renderReceiptRow}
            contentContainerStyle={{ padding: spacing.md, gap: 6 }}
            activationDistance={10}
            keyboardShouldPersistTaps="handled"
            testID="receipt-list"
          />
        )}
      </View>

      {/* Footer totals + CTA */}
      <View style={styles.footer}>
        {/* Inline notes — one undo entry per burst of typing, printed on the PDF. */}
        <View style={styles.notesWrap}>
          <Feather name="edit-3" size={13} color={colors.onSurfaceMuted} />
          <TextInput
            testID="quote-notes-input"
            value={s.notes}
            onChangeText={setNotes}
            placeholder="Add a note for the customer (printed on the PDF)…"
            placeholderTextColor={colors.onSurfaceMuted}
            style={styles.notesInput}
            multiline
          />
        </View>

        <Pressable
          onPress={() => setDiscountSheet({ kind: "project" })}
          testID="open-discount-sheet"
          style={styles.discBar}
        >
          <View style={{ flex: 1 }}>
            <Text style={type.overline}>Discount</Text>
            <Text style={{ fontSize: 12, color: colors.onSurfaceSecondary }} numberOfLines={1}>
              {s.projectDiscount ? `Project ${s.projectDiscount}%` : "No project discount"}
              {Object.keys(s.categoryDiscounts).length ? ` · ${Object.keys(s.categoryDiscounts).length} category discounts` : ""}
            </Text>
          </View>
          <Feather name="sliders" size={14} color={colors.onSurface} />
        </Pressable>

        <View style={styles.totalsGrid}>
          <View style={styles.tRow}><Text style={type.caption}>Subtotal</Text><Text style={type.mono}>{money(totals.subtotal)}</Text></View>
          <View style={styles.tRow}><Text style={type.caption}>Discount</Text><Text style={[type.mono, { color: colors.error }]}>− {money(totals.discount)}</Text></View>
          <View style={styles.tRow}><Text style={type.caption}>Tax</Text><Text style={type.mono}>{money(totals.tax)}</Text></View>
          <View style={[styles.tRow, { borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border, paddingTop: 8, marginTop: 4 }]}>
            <Text style={{ fontSize: 14, fontWeight: "700" }}>Grand total</Text>
            <Text style={{ fontSize: 20, fontWeight: "700", fontVariant: ["tabular-nums"] }}>{money(totals.grand)}</Text>
          </View>
        </View>
        <Pressable
          testID="save-quotation-btn"
          onPress={finalize}
          disabled={!s.customerId || s.lines.length === 0}
          style={({ pressed }) => [styles.saveBtn, { opacity: !s.customerId || s.lines.length === 0 ? 0.4 : pressed ? 0.9 : 1 }]}
        >
          <Feather name="check" size={16} color={colors.onBrand} />
          <Text style={styles.saveBtnText}>Finish & review</Text>
        </Pressable>
      </View>
    </View>
  );

  // ---------- Discount sheet plumbing ----------
  const currentDiscSheet = discountSheet;
  const closeDiscount = () => setDiscountSheet(null);
  const [tempProjPct, setTempProjPct] = useState<string>("0");
  const [tempLinePct, setTempLinePct] = useState<string>("");
  const [tempCatPct, setTempCatPct] = useState<string>("");
  useEffect(() => {
    if (!currentDiscSheet) return;
    if (currentDiscSheet.kind === "project") setTempProjPct(String(s.projectDiscount));
    else if (currentDiscSheet.kind === "line") {
      const l = s.lines.find((x) => x.id === currentDiscSheet.line_id);
      setTempLinePct(l?.discount_pct != null ? String(l.discount_pct) : "");
    } else if (currentDiscSheet.kind === "category") {
      setTempCatPct(s.categoryDiscounts[currentDiscSheet.category_id] != null ? String(s.categoryDiscounts[currentDiscSheet.category_id]) : "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentDiscSheet]);
  const applyDiscount = () => {
    if (!currentDiscSheet) return;
    if (currentDiscSheet.kind === "project") setProjectDiscount(Number(tempProjPct) || 0);
    else if (currentDiscSheet.kind === "line") {
      updateLine(currentDiscSheet.line_id, { discount_pct: tempLinePct === "" ? null : Math.max(0, Math.min(100, Number(tempLinePct) || 0)) });
    } else if (currentDiscSheet.kind === "category") {
      setCategoryDiscount(currentDiscSheet.category_id, tempCatPct === "" ? null : Number(tempCatPct) || 0);
    }
    closeDiscount();
  };
  const currentLine = currentDiscSheet?.kind === "line" ? s.lines.find((l) => l.id === currentDiscSheet.line_id) : null;
  const currentLineEff = currentLine ? effectivePct(currentLine, s.categoryDiscounts, s.projectDiscount) : null;

  const descLine = descSheet ? s.lines.find((x) => x.id === descSheet.line_id) : null;

  // ---------- Render ----------
  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={styles.topbar}>
        <Pressable testID="builder-back" onPress={() => router.back()} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <Feather name="chevron-left" size={18} color={colors.onSurface} />
          <Text style={{ fontSize: 14, fontWeight: "500" }}>Cancel</Text>
        </Pressable>
        <View style={{ flex: 1, alignItems: "center" }}>
          <Text style={type.titleMd}>New Quotation</Text>
          <Text style={type.caption} numberOfLines={1}>
            {s.lines.length} items · {money(totals.grand)} · {saveLabel}
            {history.pastSize > 0 ? ` · ${history.pastSize} step${history.pastSize === 1 ? "" : "s"}` : ""}
          </Text>
        </View>
        <View style={{ flexDirection: "row", gap: 4, alignItems: "center" }}>
          {isDesktop ? (
            <View style={styles.shortcutHint} testID="shortcut-hint">
              <Text style={styles.shortcutKey}>⌘Z</Text>
              <Text style={styles.shortcutSep}>·</Text>
              <Text style={styles.shortcutKey}>⇧⌘Z</Text>
              <Text style={styles.shortcutSep}>·</Text>
              <Text style={styles.shortcutKey}>⌘K</Text>
            </View>
          ) : null}
          <Pressable
            testID="undo-btn"
            onPress={history.undo}
            disabled={!history.canUndo}
            style={({ pressed }) => [styles.topBtn, { opacity: !history.canUndo ? 0.35 : pressed ? 0.7 : 1 }]}
            hitSlop={6}
          >
            <Feather name="corner-up-left" size={16} color={colors.onSurface} />
            {isDesktop ? <Text style={styles.topBtnLabel}>Undo</Text> : null}
          </Pressable>
          <Pressable
            testID="redo-btn"
            onPress={history.redo}
            disabled={!history.canRedo}
            style={({ pressed }) => [styles.topBtn, { opacity: !history.canRedo ? 0.35 : pressed ? 0.7 : 1 }]}
            hitSlop={6}
          >
            <Feather name="corner-up-right" size={16} color={colors.onSurface} />
            {isDesktop ? <Text style={styles.topBtnLabel}>Redo</Text> : null}
          </Pressable>
        </View>
      </View>

      {isTablet ? (
        <View style={{ flex: 1, flexDirection: "row" }}>
          <View style={{ flex: 1.1 }}>{CatalogPanel}</View>
          <View style={{ width: StyleSheet.hairlineWidth, backgroundColor: colors.border }} />
          <View style={{ flex: 1 }}>{ReceiptPanel}</View>
        </View>
      ) : (
        <>
          <View style={{ flexDirection: "row", padding: 8, gap: 6, backgroundColor: colors.surfaceSecondary, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border }}>
            {(["catalog", "receipt"] as const).map((t) => (
              <Pressable
                key={t}
                onPress={() => setTab(t)}
                style={[styles.tabBtn, tab === t && styles.tabBtnActive]}
                testID={`builder-tab-${t}`}
              >
                <Text style={{ color: tab === t ? colors.onBrand : colors.onSurface, fontSize: 13, fontWeight: "600" }}>
                  {t === "catalog" ? "Add products" : `Quotation (${s.lines.length})`}
                </Text>
              </Pressable>
            ))}
          </View>
          <View style={{ flex: 1 }}>{tab === "catalog" ? CatalogPanel : ReceiptPanel}</View>
        </>
      )}

      {/* Discount Sheet */}
      <BottomSheet
        visible={!!discountSheet}
        onClose={closeDiscount}
        title={
          currentDiscSheet?.kind === "line" ? "Item discount"
          : currentDiscSheet?.kind === "category" ? "Category discount"
          : "Discounts"
        }
        testID="discount-sheet"
        footer={
          <View style={{ flexDirection: "row", gap: 8, justifyContent: "flex-end" }}>
            <Button label="Cancel" variant="secondary" onPress={closeDiscount} />
            <Button label="Apply" onPress={applyDiscount} testID="apply-discount" />
          </View>
        }
      >
        {currentDiscSheet?.kind === "project" ? (
          <View style={{ gap: spacing.lg }}>
            <View style={{ gap: 6 }}>
              <Text style={type.overline}>Project-wide %</Text>
              <TextInput
                testID="project-disc-input"
                value={tempProjPct}
                onChangeText={setTempProjPct}
                keyboardType="decimal-pad"
                placeholder="0"
                style={styles.bigInput}
              />
              <Text style={type.caption}>Applied to items that do not have an override.</Text>
            </View>

            <View style={{ gap: 8 }}>
              <Text style={type.overline}>Category overrides</Text>
              {usedCategoryIds.length === 0 ? (
                <Text style={type.caption}>Add products first — categories used will appear here.</Text>
              ) : usedCategoryIds.map((cid) => (
                <Pressable
                  key={cid}
                  testID={`edit-cat-${cid}`}
                  onPress={() => setDiscountSheet({ kind: "category", category_id: cid })}
                  style={styles.catRow}
                >
                  <Text style={{ flex: 1, fontSize: 13, fontWeight: "600" }}>{catNameById[cid] || "—"}</Text>
                  <Text style={type.mono}>{s.categoryDiscounts[cid] != null ? `${s.categoryDiscounts[cid]}%` : "Add discount"}</Text>
                  <Feather name={s.categoryDiscounts[cid] != null ? "edit-2" : "plus"} size={14} color={colors.brand} />
                </Pressable>
              ))}
            </View>

            <View style={styles.calloutBox}>
              <Text style={type.overline}>How it stacks</Text>
              <Text style={type.caption}>
                Product override → Category → Project. The first non-null wins per item.
              </Text>
            </View>
          </View>
        ) : currentDiscSheet?.kind === "category" ? (
          <View style={{ gap: spacing.md }}>
            <Text style={type.body}>{catNameById[currentDiscSheet.category_id] || "Category"}</Text>
            <TextInput
              testID="category-disc-input"
              value={tempCatPct}
              onChangeText={setTempCatPct}
              keyboardType="decimal-pad"
              placeholder="Leave empty to remove"
              style={styles.bigInput}
            />
            <Text style={type.caption}>Applied to all items in this category, unless the item has its own product-level override.</Text>
          </View>
        ) : currentDiscSheet?.kind === "line" && currentLine ? (
          <View style={{ gap: spacing.md }}>
            <Text style={type.body}>{currentLine.name}</Text>
            <TextInput
              testID="line-disc-input"
              value={tempLinePct}
              onChangeText={setTempLinePct}
              keyboardType="decimal-pad"
              placeholder="Empty → inherit from category / project"
              style={styles.bigInput}
            />
            {currentLineEff && currentLineEff.source !== "none" && currentLine.discount_pct == null ? (
              <View style={styles.calloutBox}>
                <Text style={type.overline}>Currently inheriting</Text>
                <Text style={type.body}>{currentLineEff.pct}% from {currentLineEff.source}</Text>
              </View>
            ) : null}
          </View>
        ) : null}
      </BottomSheet>

      {/* Room add/rename sheet */}
      <BottomSheet
        visible={!!roomSheet}
        onClose={() => setRoomSheet(null)}
        title={roomSheet?.kind === "add" ? "Add room" : "Rename room"}
        testID="room-sheet"
        footer={
          <View style={{ flexDirection: "row", gap: 8, justifyContent: "flex-end" }}>
            <Button label="Cancel" variant="secondary" onPress={() => setRoomSheet(null)} />
            <Button
              label={roomSheet?.kind === "add" ? "Add" : "Save"}
              testID="save-room"
              onPress={() => {
                if (roomSheet?.kind === "add") addRoom(roomInput);
                else if (roomSheet?.kind === "rename") renameRoom(roomSheet.name, roomInput);
                setRoomSheet(null);
              }}
            />
          </View>
        }
      >
        <View style={{ gap: spacing.md }}>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
            {DEFAULT_ROOMS.filter((r) => !s.rooms.includes(r)).map((r) => (
              <Pressable
                key={r}
                testID={`suggest-${r}`}
                onPress={() => setRoomInput(r)}
                style={styles.suggestion}
              >
                <Text style={{ fontSize: 12, fontWeight: "600", color: colors.onSurfaceSecondary }}>{r}</Text>
              </Pressable>
            ))}
          </View>
          <TextInput
            testID="room-input"
            value={roomInput}
            onChangeText={setRoomInput}
            placeholder="e.g. Master Bath"
            style={styles.bigInput}
            autoFocus
          />
        </View>
      </BottomSheet>

      {/* Line description sheet */}
      <BottomSheet
        visible={!!descSheet}
        onClose={() => setDescSheet(null)}
        title="Item description"
        testID="desc-sheet"
        footer={
          <View style={{ flexDirection: "row", gap: 8, justifyContent: "flex-end" }}>
            <Button label="Done" onPress={() => setDescSheet(null)} testID="close-desc-sheet" />
          </View>
        }
      >
        {descLine ? (
          <View style={{ gap: spacing.md }}>
            <Text style={type.body}>{descLine.name}</Text>
            <TextInput
              testID="desc-input"
              value={descLine.description || ""}
              onChangeText={(v) => updateLine(descLine.id, { description: v }, "desc")}
              multiline
              placeholder="Add a note visible on the PDF (e.g. Installation excluded)"
              style={[styles.bigInput, { minHeight: 110, textAlignVertical: "top" }]}
            />
          </View>
        ) : null}
      </BottomSheet>

      {/* Alternates swap sheet */}
      <BottomSheet
        visible={!!swapSheet}
        onClose={() => { setSwapSheet(null); setSwapItems([]); }}
        title="Swap for an alternate"
        testID="swap-sheet"
      >
        {swapLoading ? (
          <View style={{ alignItems: "center", padding: spacing.xl }}>
            <ActivityIndicator />
          </View>
        ) : swapItems.length === 0 ? (
          <EmptyState icon="refresh-cw" title="No alternates found" subtitle="Try a different product." />
        ) : (
          <View style={{ gap: 8 }}>
            <Text style={type.caption}>Ranked closest-first · family → brand+category → category. Qty, discount and room are preserved.</Text>
            {swapItems.map((p) => (
              <View key={p.id} style={{ gap: 4 }}>
                <Pressable
                  testID={`swap-target-${p.id}`}
                  onPress={() => commitSwap(p)}
                  style={({ pressed }) => [styles.pRow, { backgroundColor: pressed ? colors.surfaceTertiary : colors.surfaceSecondary }]}
                >
                  {p.images?.[0] ? <Image source={{ uri: p.images[0] }} style={styles.pThumb} /> : <View style={styles.pThumb} />}
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{p.name}</Text>
                    <Text style={type.caption}>{p.sku}{p.finish ? ` · ${p.finish}` : ""}</Text>
                  </View>
                  <Text style={[type.mono, { fontSize: 13, fontWeight: "600" }]}>{money(p.price)}</Text>
                  <Feather name="corner-down-right" size={14} color={colors.brand} />
                </Pressable>
                {(p.variants || []).length > 0 ? (
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingLeft: 54, paddingBottom: 2 }}>
                    {(p.variants || []).map((v) => {
                      const delta = (v.price ?? p.price) - p.price;
                      return (
                        <Pressable
                          key={v.sku}
                          testID={`swap-variant-${v.sku}`}
                          onPress={() => commitSwap(p, v)}
                          style={({ pressed }) => [styles.variantChip, pressed && { opacity: 0.85 }]}
                        >
                          <View style={[styles.swatch, { backgroundColor: finishSwatch(v.finish) }]} />
                          <Text style={styles.variantChipLabel} numberOfLines={1}>{v.finish || v.color || v.size || v.sku}</Text>
                          {delta !== 0 ? (
                            <Text style={[styles.variantDelta, { color: delta > 0 ? colors.onSurfaceMuted : colors.success }]}>
                              {delta > 0 ? "+" : "−"}{money(Math.abs(delta))}
                            </Text>
                          ) : null}
                        </Pressable>
                      );
                    })}
                  </ScrollView>
                ) : null}
              </View>
            ))}
          </View>
        )}
      </BottomSheet>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  topbar: {
    flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg,
    paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface, gap: 6,
  },
  topBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  topBtnLabel: { fontSize: 12, fontWeight: "600", color: colors.onSurface },

  panel: { flex: 1, backgroundColor: colors.surface },
  panelHead: {
    padding: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface, gap: spacing.sm,
  },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: 8,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
    paddingHorizontal: 12, borderRadius: radius.md,
  },
  searchInput: { flex: 1, fontSize: 14, paddingVertical: 10, color: colors.onSurface },

  pickerTabs: { flexDirection: "row", gap: 6, backgroundColor: colors.surfaceTertiary, padding: 3, borderRadius: radius.md },
  pickerTab: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, paddingVertical: 7, borderRadius: radius.sm },
  pickerTabActive: { backgroundColor: colors.brand },

  pRow: {
    flexDirection: "row", alignItems: "center", gap: 10, padding: 10, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  pThumb: { width: 44, height: 44, borderRadius: 8, backgroundColor: colors.surfaceTertiary },

  variantChip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
  },
  variantChipLabel: { fontSize: 11, fontWeight: "600", color: colors.onSurface, maxWidth: 96 },
  variantDelta: { fontSize: 10, fontWeight: "700", fontVariant: ["tabular-nums"] },
  swatch: { width: 12, height: 12, borderRadius: 999, borderWidth: 1, borderColor: "rgba(0,0,0,0.12)" },

  custChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border },
  custChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  roomTab: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  roomTabActive: { backgroundColor: colors.brand, borderColor: colors.brand },

  roomHeader: {
    flexDirection: "row", alignItems: "center", gap: 8, padding: 10, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
  },

  lineRow: {
    flexDirection: "row", gap: 10, padding: 10, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  dragHandle: {
    width: 20, alignItems: "center", justifyContent: "center", alignSelf: "stretch",
    marginRight: -2, marginLeft: -4,
  },
  lineThumb: { width: 48, height: 48, borderRadius: 8, backgroundColor: colors.surfaceTertiary },
  inputMini: {
    borderWidth: 1, borderColor: colors.border, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 3, minWidth: 60,
    backgroundColor: colors.surface,
  },
  inputLabel: { fontSize: 9, color: colors.onSurfaceMuted, fontWeight: "700", letterSpacing: 0.5 },
  inputVal: { fontSize: 13, fontFamily: Platform.select({ ios: "Menlo", android: "monospace" }), color: colors.onSurface, padding: 0, minWidth: 40 },
  lineIcon: { width: 28, height: 28, borderRadius: 6, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },

  footer: {
    padding: spacing.md, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface, gap: spacing.md,
  },
  discBar: {
    flexDirection: "row", alignItems: "center", gap: 8, padding: 10,
    backgroundColor: colors.surfaceTertiary, borderRadius: radius.md,
  },
  totalsGrid: { gap: 4 },
  tRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  saveBtn: {
    backgroundColor: colors.brand, paddingVertical: 14, borderRadius: radius.md,
    flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 8,
  },
  saveBtnText: { color: colors.onBrand, fontSize: 15, fontWeight: "700" },

  tabBtn: { flex: 1, alignItems: "center", paddingVertical: 10, borderRadius: radius.md, backgroundColor: colors.surfaceTertiary },
  tabBtnActive: { backgroundColor: colors.brand },

  bigInput: {
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
    borderRadius: radius.md, paddingHorizontal: 14, paddingVertical: 12, fontSize: 15, color: colors.onSurface,
  },
  catRow: {
    flexDirection: "row", alignItems: "center", gap: 10, padding: 10, backgroundColor: colors.surface,
    borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  calloutBox: {
    padding: 12, borderRadius: radius.md, backgroundColor: colors.surfaceTertiary, gap: 4,
  },
  suggestion: {
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999,
    backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border,
  },
  inlineRoomInput: {
    flex: 1, fontSize: 14, fontWeight: "700", color: colors.onSurface,
    paddingVertical: 4, paddingHorizontal: 6, borderRadius: 6,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.brand,
  },
  notesWrap: {
    flexDirection: "row", alignItems: "flex-start", gap: 8, padding: 10,
    backgroundColor: colors.surfaceTertiary, borderRadius: radius.md,
  },
  notesInput: {
    flex: 1, fontSize: 13, color: colors.onSurface, padding: 0, minHeight: 20, maxHeight: 84,
  },
  shortcutHint: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6,
    backgroundColor: colors.surfaceTertiary, marginRight: 4,
  },
  shortcutKey: { fontSize: 10, fontWeight: "700", color: colors.onSurfaceSecondary, fontVariant: ["tabular-nums"] },
  shortcutSep: { fontSize: 10, color: colors.onSurfaceMuted },
});
