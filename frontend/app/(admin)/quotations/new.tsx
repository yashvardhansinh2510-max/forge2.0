// Forge Quotation Builder 2.0
// - Autosave (debounced PATCH, silent)
// - Rooms 2.0: add, rename, duplicate, delete, collapse
// - Multi-level discounts: Product > Category > Project
// - Line actions: duplicate, remove, move to room, inline description
// - Picker tabs: Search / Recent / Frequent
// - Save-state indicator
import { Feather } from "@expo/vector-icons";
import { Image } from "expo-image";
import * as Haptics from "expo-haptics";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator, FlatList, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet,
  Text, TextInput, useWindowDimensions, View,
} from "react-native";

import { BottomSheet } from "@/src/components/BottomSheet";
import { Badge, Button, EmptyState, StatusBadge } from "@/src/components/ui";
import { toast } from "@/src/components/Toast";
import { api } from "@/src/api/client";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type Product = {
  id: string; name: string; sku: string; price: number; mrp: number;
  finish?: string | null; images: string[]; category_id: string; brand_id: string;
};
type Category = { id: string; name: string };
type Customer = { id: string; name: string; company?: string | null; email: string };
type Line = {
  id: string; product_id: string; sku: string; name: string; image?: string | null;
  category_id?: string | null; room?: string;
  qty: number; unit_price: number;
  discount_pct: number | null;    // null = inherit from category / project
  tax_pct: number; description?: string | null; notes?: string | null;
};

type SaveState = "idle" | "saving" | "saved" | "error";

const DEFAULT_ROOMS = ["Master Bath", "Powder Room", "Guest Bath", "Kitchen", "Utility", "Living", "Study"];

function effectivePct(l: Line, catDiscs: Record<string, number>, projPct: number): { pct: number; source: string } {
  if (l.discount_pct != null) return { pct: l.discount_pct, source: "product" };
  if (l.category_id && catDiscs[l.category_id] != null) return { pct: catDiscs[l.category_id], source: "category" };
  if (projPct) return { pct: projPct, source: "project" };
  return { pct: 0, source: "none" };
}

export default function QuotationBuilder() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;

  const [customers, setCustomers] = useState<Customer[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [recent, setRecent] = useState<Product[]>([]);
  const [frequent, setFrequent] = useState<Product[]>([]);
  const [pickerTab, setPickerTab] = useState<"search" | "recent" | "frequent">("search");
  const [q, setQ] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [rooms, setRooms] = useState<string[]>([DEFAULT_ROOMS[0]]);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [activeRoom, setActiveRoom] = useState<string>(DEFAULT_ROOMS[0]);
  const [notes, setNotes] = useState("");
  const [projectDiscount, setProjectDiscount] = useState(0);
  const [categoryDiscounts, setCategoryDiscounts] = useState<Record<string, number>>({});

  // Autosave plumbing
  const [quotationId, setQuotationId] = useState<string | null>(null);
  const [quotationNumber, setQuotationNumber] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sheets
  const [tab, setTab] = useState<"catalog" | "receipt">("receipt");
  const [discountSheet, setDiscountSheet] = useState<null | { kind: "project" } | { kind: "category"; category_id: string } | { kind: "line"; line_id: string }>(null);
  const [roomSheet, setRoomSheet] = useState<null | { kind: "add" } | { kind: "rename"; name: string }>(null);
  const [roomInput, setRoomInput] = useState("");
  const [descSheet, setDescSheet] = useState<null | { line_id: string }>(null);

  // ---- Load static data ----
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
      if (cs[0]) setCustomerId(cs[0].id);
    })();
  }, []);

  // ---- Product search ----
  useEffect(() => {
    if (pickerTab !== "search") return;
    const t = setTimeout(async () => {
      const res = await api.get<{ items: Product[] }>(`/products?limit=40${q ? `&q=${encodeURIComponent(q)}` : ""}`);
      setProducts(res.items);
    }, 180);
    return () => clearTimeout(t);
  }, [q, pickerTab]);

  // ---- Autosave orchestration ----
  const persist = useCallback(async () => {
    if (!customerId) return;
    const payload = {
      customer_id: customerId,
      items: lines,
      rooms,
      notes,
      project_discount_pct: projectDiscount,
      category_discounts: categoryDiscounts,
    };
    try {
      setSaveState("saving");
      if (!quotationId) {
        const created = await api.post<{ id: string; number: string }>("/quotations", payload);
        setQuotationId(created.id);
        setQuotationNumber(created.number);
      } else {
        const upd = { ...payload, silent: true, collapsed_rooms: Object.keys(collapsed).filter((k) => collapsed[k]) };
        // customer_id is not in QuotationUpdate — drop it
        delete (upd as any).customer_id;
        await api.patch(`/quotations/${quotationId}`, upd);
      }
      setSaveState("saved"); setSavedAt(new Date());
    } catch (e: any) {
      setSaveState("error");
      toast.error(e?.detail || "Save failed");
    }
  }, [customerId, lines, rooms, notes, projectDiscount, categoryDiscounts, quotationId, collapsed]);

  useEffect(() => {
    if (!customerId) return;
    // Debounced autosave — only after user has actually interacted
    if (lines.length === 0 && !quotationId && projectDiscount === 0 && Object.keys(categoryDiscounts).length === 0) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => { persist(); }, 900);
    return () => { if (saveTimer.current) clearTimeout(saveTimer.current); };
  }, [customerId, lines, rooms, notes, projectDiscount, categoryDiscounts, collapsed]);

  // ---- Totals ----
  const totals = useMemo(() => {
    let sub = 0, disc = 0, tax = 0;
    for (const l of lines) {
      const gross = l.qty * l.unit_price;
      const { pct } = effectivePct(l, categoryDiscounts, projectDiscount);
      const d = gross * pct / 100;
      const net = gross - d;
      const t = net * (l.tax_pct || 0) / 100;
      sub += gross; disc += d; tax += t;
    }
    return { subtotal: sub, discount: disc, tax, grand: Math.round((sub - disc + tax) * 100) / 100 };
  }, [lines, projectDiscount, categoryDiscounts]);

  // ---- Line ops ----
  const addProduct = (p: Product) => {
    Haptics.selectionAsync();
    const idx = lines.findIndex((l) => l.product_id === p.id && l.room === activeRoom);
    if (idx >= 0) {
      const next = [...lines]; next[idx] = { ...next[idx], qty: next[idx].qty + 1 }; setLines(next);
    } else {
      setLines([
        ...lines,
        {
          id: `${p.id}-${Date.now()}`,
          product_id: p.id, sku: p.sku, name: p.name, image: p.images?.[0],
          category_id: p.category_id, room: activeRoom, qty: 1, unit_price: p.price,
          discount_pct: null, tax_pct: 18,
        },
      ]);
    }
  };

  const updateLine = (id: string, patch: Partial<Line>) => setLines(lines.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  const removeLine = (id: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setLines(lines.filter((l) => l.id !== id));
  };
  const duplicateLine = (id: string) => {
    const idx = lines.findIndex((l) => l.id === id);
    if (idx < 0) return;
    const copy = { ...lines[idx], id: `${lines[idx].product_id}-${Date.now()}` };
    const next = [...lines]; next.splice(idx + 1, 0, copy); setLines(next);
    Haptics.selectionAsync();
  };
  const moveLine = (id: string, room: string) => {
    updateLine(id, { room });
    Haptics.selectionAsync();
  };

  // ---- Room ops ----
  const addRoom = (name: string) => {
    const trimmed = name.trim();
    if (!trimmed || rooms.includes(trimmed)) return;
    setRooms([...rooms, trimmed]); setActiveRoom(trimmed);
  };
  const renameRoom = (from: string, to: string) => {
    const trimmed = to.trim();
    if (!trimmed || trimmed === from) return;
    setRooms(rooms.map((r) => (r === from ? trimmed : r)));
    setLines(lines.map((l) => (l.room === from ? { ...l, room: trimmed } : l)));
    if (activeRoom === from) setActiveRoom(trimmed);
    setCollapsed(({ [from]: c, ...rest }) => (c ? { ...rest, [trimmed]: true } : rest));
  };
  const duplicateRoom = (name: string) => {
    let copyName = `${name} (copy)`; let i = 2;
    while (rooms.includes(copyName)) { copyName = `${name} (copy ${i++})`; }
    setRooms([...rooms, copyName]);
    setLines([...lines, ...lines.filter((l) => l.room === name).map((l) => ({ ...l, id: `${l.product_id}-${Date.now()}-${Math.random()}`, room: copyName }))]);
    setActiveRoom(copyName);
  };
  const deleteRoom = (name: string) => {
    if (rooms.length <= 1) { toast.error("Keep at least one room"); return; }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    setRooms(rooms.filter((r) => r !== name));
    setLines(lines.filter((l) => l.room !== name));
    if (activeRoom === name) setActiveRoom(rooms.find((r) => r !== name) || DEFAULT_ROOMS[0]);
  };
  const toggleCollapse = (name: string) => setCollapsed({ ...collapsed, [name]: !collapsed[name] });

  // ---- Finish / send ----
  const finalize = async () => {
    await persist();
    if (!quotationId) return;
    router.replace(`/(admin)/quotations/${quotationId}` as any);
  };

  // ---- Save status label ----
  const saveLabel = saveState === "saving" ? "Saving…"
    : saveState === "error" ? "Save failed"
    : savedAt ? `Saved · ${savedAt.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`
    : "Draft — no changes yet";

  const catNameById: Record<string, string> = Object.fromEntries(categories.map((c) => [c.id, c.name]));

  // ---- Product picker rows ----
  const pickerList: Product[] = pickerTab === "recent" ? recent : pickerTab === "frequent" ? frequent : products;

  const CatalogPanel = (
    <View style={styles.panel}>
      <View style={styles.panelHead}>
        <Text style={type.titleMd}>Add products</Text>
        <View style={styles.searchWrap}>
          <Feather name="search" size={16} color={colors.onSurfaceMuted} />
          <TextInput
            testID="builder-search"
            value={q}
            onChangeText={(v) => { setQ(v); setPickerTab("search"); }}
            placeholder="Search catalog · Enter to add first"
            placeholderTextColor={colors.onSurfaceMuted}
            style={styles.searchInput}
            onSubmitEditing={() => pickerList[0] && addProduct(pickerList[0])}
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
        renderItem={({ item }) => (
          <Pressable
            testID={`add-product-${item.id}`}
            onPress={() => addProduct(item)}
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
        )}
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

  const roomActiveIsCollapsed = (r: string) => !!collapsed[r];

  const RoomBlock = ({ name }: { name: string }) => {
    const roomLines = lines.filter((l) => l.room === name);
    const roomSub = roomLines.reduce((s, l) => s + l.qty * l.unit_price * (1 - (effectivePct(l, categoryDiscounts, projectDiscount).pct / 100)), 0);
    const isColl = roomActiveIsCollapsed(name);
    const isActive = activeRoom === name;
    return (
      <View style={{ gap: 8, marginBottom: 6 }}>
        <View style={[styles.roomHeader, isActive && { borderColor: colors.brand }]}>
          <Pressable onPress={() => toggleCollapse(name)} testID={`room-toggle-${name}`}>
            <Feather name={isColl ? "chevron-right" : "chevron-down"} size={16} color={colors.onSurface} />
          </Pressable>
          <Pressable onPress={() => setActiveRoom(name)} style={{ flex: 1 }}>
            <Text style={{ fontSize: 14, fontWeight: "700", color: colors.onSurface }}>{name}</Text>
            <Text style={type.caption}>{roomLines.length} items · {money(roomSub)}</Text>
          </Pressable>
          <Pressable
            testID={`room-rename-${name}`}
            hitSlop={8}
            onPress={() => { setRoomSheet({ kind: "rename", name }); setRoomInput(name); }}
          >
            <Feather name="edit-2" size={14} color={colors.onSurfaceMuted} />
          </Pressable>
          <Pressable testID={`room-dup-${name}`} hitSlop={8} onPress={() => duplicateRoom(name)}>
            <Feather name="copy" size={14} color={colors.onSurfaceMuted} />
          </Pressable>
          <Pressable testID={`room-delete-${name}`} hitSlop={8} onPress={() => deleteRoom(name)}>
            <Feather name="trash-2" size={14} color={colors.error} />
          </Pressable>
        </View>

        {!isColl ? (
          roomLines.length === 0 ? (
            <View style={styles.roomEmpty}>
              <Text style={type.caption}>No items yet — pick from Add products.</Text>
            </View>
          ) : roomLines.map((l) => {
            const eff = effectivePct(l, categoryDiscounts, projectDiscount);
            const total = l.qty * l.unit_price * (1 - eff.pct / 100);
            return (
              <View key={l.id} style={styles.lineRow}>
                {l.image ? <Image source={{ uri: l.image }} style={styles.lineThumb} /> : <View style={styles.lineThumb} />}
                <View style={{ flex: 1, gap: 4 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface, flex: 1 }} numberOfLines={1}>{l.name}</Text>
                    {eff.source !== "none" && eff.source !== "product" ? (
                      <Badge tone={eff.source === "category" ? "info" : "success"} label={eff.source === "category" ? "Cat" : "Proj"} />
                    ) : null}
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
                        onChangeText={(v) => updateLine(l.id, { qty: Math.max(0, Number(v) || 0) })}
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
                        onChangeText={(v) => updateLine(l.id, { unit_price: Number(v) || 0 })}
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

                    <Pressable testID={`line-menu-${l.id}`} onPress={() => setDescSheet({ line_id: l.id })} style={styles.lineIcon}>
                      <Feather name="align-left" size={13} color={colors.onSurfaceMuted} />
                    </Pressable>
                    <Pressable testID={`line-dup-${l.id}`} onPress={() => duplicateLine(l.id)} style={styles.lineIcon}>
                      <Feather name="copy" size={13} color={colors.onSurfaceMuted} />
                    </Pressable>
                    <Pressable testID={`line-move-${l.id}`} onPress={() => moveLine(l.id, rooms[(rooms.indexOf(l.room || "") + 1) % rooms.length])} style={styles.lineIcon}>
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
          })
        ) : null}
      </View>
    );
  };

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
              onPress={() => setCustomerId(c.id)}
              style={[styles.custChip, customerId === c.id && styles.custChipActive]}
            >
              <Text style={{ fontSize: 12, fontWeight: "600", color: customerId === c.id ? colors.onBrand : colors.onSurface }}>
                {c.company || c.name}
              </Text>
            </Pressable>
          ))}
        </ScrollView>

        {/* Room chips */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingVertical: 2 }}>
          {rooms.map((r) => (
            <Pressable
              key={r}
              testID={`room-${r}`}
              onPress={() => setActiveRoom(r)}
              style={[styles.roomTab, activeRoom === r && styles.roomTabActive]}
            >
              <Text style={{ fontSize: 12, fontWeight: "600", color: activeRoom === r ? colors.onBrand : colors.onSurfaceSecondary }}>{r}</Text>
            </Pressable>
          ))}
          <Pressable
            onPress={() => { setRoomInput(""); setRoomSheet({ kind: "add" }); }}
            testID="add-room-btn"
            style={[styles.roomTab, { borderStyle: "dashed" }]}
          >
            <Feather name="plus" size={13} color={colors.onSurfaceMuted} />
          </Pressable>
        </ScrollView>
      </View>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: spacing.md, gap: 4 }} keyboardShouldPersistTaps="handled">
        {rooms.map((r) => <RoomBlock key={r} name={r} />)}
        {lines.length === 0 ? (
          <EmptyState icon="file-plus" title="Add your first product" subtitle="Search on the left and tap to add. Everything totals live." />
        ) : null}
      </ScrollView>

      {/* Footer totals + CTA */}
      <View style={styles.footer}>
        <Pressable
          onPress={() => setDiscountSheet({ kind: "project" })}
          testID="open-discount-sheet"
          style={styles.discBar}
        >
          <View style={{ flex: 1 }}>
            <Text style={type.overline}>Discount</Text>
            <Text style={{ fontSize: 12, color: colors.onSurfaceSecondary }} numberOfLines={1}>
              {projectDiscount ? `Project ${projectDiscount}%` : "No project discount"}
              {Object.keys(categoryDiscounts).length ? ` · ${Object.keys(categoryDiscounts).length} category discounts` : ""}
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
          disabled={!customerId || lines.length === 0}
          style={({ pressed }) => [styles.saveBtn, { opacity: !customerId || lines.length === 0 ? 0.4 : pressed ? 0.9 : 1 }]}
        >
          <Feather name="check" size={16} color={colors.onBrand} />
          <Text style={styles.saveBtnText}>Finish & review</Text>
        </Pressable>
      </View>
    </View>
  );

  // ------ Discount sheet ------
  const currentDiscSheet = discountSheet;
  const closeDiscount = () => setDiscountSheet(null);

  const projectPct = projectDiscount;
  const [tempProjPct, setTempProjPct] = useState<string>("0");
  const [tempLinePct, setTempLinePct] = useState<string>("");
  const [tempCatPct, setTempCatPct] = useState<string>("");

  useEffect(() => {
    if (!currentDiscSheet) return;
    if (currentDiscSheet.kind === "project") setTempProjPct(String(projectPct));
    else if (currentDiscSheet.kind === "line") {
      const l = lines.find((x) => x.id === currentDiscSheet.line_id);
      setTempLinePct(l?.discount_pct != null ? String(l.discount_pct) : "");
    } else if (currentDiscSheet.kind === "category") {
      setTempCatPct(categoryDiscounts[currentDiscSheet.category_id] != null ? String(categoryDiscounts[currentDiscSheet.category_id]) : "");
    }
  }, [currentDiscSheet]);

  const applyDiscount = () => {
    if (!currentDiscSheet) return;
    if (currentDiscSheet.kind === "project") setProjectDiscount(Math.max(0, Math.min(100, Number(tempProjPct) || 0)));
    else if (currentDiscSheet.kind === "line") {
      updateLine(currentDiscSheet.line_id, { discount_pct: tempLinePct === "" ? null : Math.max(0, Math.min(100, Number(tempLinePct) || 0)) });
    } else if (currentDiscSheet.kind === "category") {
      const next = { ...categoryDiscounts };
      if (tempCatPct === "") delete next[currentDiscSheet.category_id];
      else next[currentDiscSheet.category_id] = Math.max(0, Math.min(100, Number(tempCatPct) || 0));
      setCategoryDiscounts(next);
    }
    closeDiscount();
  };

  const currentLine = currentDiscSheet?.kind === "line" ? lines.find((l) => l.id === currentDiscSheet.line_id) : null;
  const currentLineEff = currentLine ? effectivePct(currentLine, categoryDiscounts, projectDiscount) : null;

  // Categories that appear in lines (for the project sheet listing)
  const usedCategoryIds = Array.from(new Set(lines.map((l) => l.category_id).filter(Boolean))) as string[];

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={styles.topbar}>
        <Pressable testID="builder-back" onPress={() => router.back()} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <Feather name="chevron-left" size={18} color={colors.onSurface} />
          <Text style={{ fontSize: 14, fontWeight: "500" }}>Cancel</Text>
        </Pressable>
        <View style={{ flex: 1, alignItems: "center" }}>
          <Text style={type.titleMd}>New Quotation</Text>
          <Text style={type.caption} numberOfLines={1}>{lines.length} items · {money(totals.grand)} · {saveLabel}</Text>
        </View>
        <View style={{ width: 60 }} />
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
                  {t === "catalog" ? "Add products" : `Quotation (${lines.length})`}
                </Text>
              </Pressable>
            ))}
          </View>
          <View style={{ flex: 1 }}>{tab === "catalog" ? CatalogPanel : ReceiptPanel}</View>
        </>
      )}

      {/* Discount Sheet — universal */}
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
                <View key={cid} style={styles.catRow}>
                  <Text style={{ flex: 1, fontSize: 13, fontWeight: "600" }}>{catNameById[cid] || "—"}</Text>
                  <Text style={type.mono}>{categoryDiscounts[cid] != null ? `${categoryDiscounts[cid]}%` : "—"}</Text>
                  <Pressable
                    testID={`edit-cat-${cid}`}
                    onPress={() => setDiscountSheet({ kind: "category", category_id: cid })}
                    style={{ paddingHorizontal: 10, paddingVertical: 6 }}
                  >
                    <Feather name="edit-2" size={14} color={colors.brand} />
                  </Pressable>
                </View>
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
                <Text style={type.body}>
                  {currentLineEff.pct}% from {currentLineEff.source}
                </Text>
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
            {DEFAULT_ROOMS.filter((r) => !rooms.includes(r)).map((r) => (
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
        {(() => {
          const l = descSheet ? lines.find((x) => x.id === descSheet.line_id) : null;
          if (!l) return null;
          return (
            <View style={{ gap: spacing.md }}>
              <Text style={type.body}>{l.name}</Text>
              <TextInput
                testID="desc-input"
                value={l.description || ""}
                onChangeText={(v) => updateLine(l.id, { description: v })}
                multiline
                placeholder="Add a note visible on the PDF (e.g. Installation excluded)"
                style={[styles.bigInput, { minHeight: 110, textAlignVertical: "top" }]}
              />
            </View>
          );
        })()}
      </BottomSheet>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  topbar: {
    flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg,
    paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface,
  },
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

  custChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border },
  custChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  roomTab: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  roomTabActive: { backgroundColor: colors.brand, borderColor: colors.brand },

  roomHeader: {
    flexDirection: "row", alignItems: "center", gap: 8, padding: 10, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
  },
  roomEmpty: {
    padding: spacing.md, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    borderStyle: "dashed", alignItems: "center", backgroundColor: colors.surface,
  },

  lineRow: {
    flexDirection: "row", gap: 10, padding: 10, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
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
});
