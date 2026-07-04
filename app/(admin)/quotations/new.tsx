// Forge Quotation Builder — flagship feature.
// Split-pane on tablet, tabbed on phone. Keyboard-first, instant search,
// inline qty/discount editing, live totals, sticky "Save" CTA.
import { Feather } from "@expo/vector-icons";
import { Image } from "expo-image";
import * as Haptics from "expo-haptics";
import { useRouter } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import {
  FlatList, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet,
  Text, TextInput, useWindowDimensions, View,
} from "react-native";

import { Card, EmptyState, StatusBadge } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type Product = {
  id: string; name: string; sku: string; price: number; mrp: number;
  finish?: string | null; images: string[];
};
type Customer = { id: string; name: string; company?: string | null; email: string };
type Line = {
  id: string; product_id: string; sku: string; name: string; image?: string | null;
  room?: string; qty: number; unit_price: number; discount_pct: number; tax_pct: number;
};

const DEFAULT_ROOMS = ["Master Bath", "Powder Room", "Guest Bath", "Kitchen", "Utility"];

export default function QuotationBuilder() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;

  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [q, setQ] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [rooms, setRooms] = useState<string[]>([DEFAULT_ROOMS[0]]);
  const [activeRoom, setActiveRoom] = useState<string>(DEFAULT_ROOMS[0]);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get<Customer[]>("/customers").then((cs) => {
      setCustomers(cs);
      if (cs[0]) setCustomerId(cs[0].id);
    });
  }, []);

  useEffect(() => {
    const t = setTimeout(async () => {
      const res = await api.get<{ items: Product[] }>(`/products?limit=30${q ? `&q=${encodeURIComponent(q)}` : ""}`);
      setProducts(res.items);
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  const totals = useMemo(() => {
    let sub = 0, disc = 0, tax = 0;
    for (const l of lines) {
      const gross = l.qty * l.unit_price;
      const d = gross * (l.discount_pct || 0) / 100;
      const netAfter = gross - d;
      const t = netAfter * (l.tax_pct || 0) / 100;
      sub += gross; disc += d; tax += t;
    }
    return {
      subtotal: sub, discount: disc, tax,
      grand: Math.round((sub - disc + tax) * 100) / 100,
    };
  }, [lines]);

  const addProduct = (p: Product) => {
    Haptics.selectionAsync();
    // If the same product exists in the active room, just bump qty
    const idx = lines.findIndex((l) => l.product_id === p.id && l.room === activeRoom);
    if (idx >= 0) {
      const next = [...lines]; next[idx].qty += 1; setLines(next);
    } else {
      setLines([
        ...lines,
        {
          id: `${p.id}-${Date.now()}`,
          product_id: p.id, sku: p.sku, name: p.name, image: p.images?.[0],
          room: activeRoom, qty: 1, unit_price: p.price, discount_pct: 0, tax_pct: 18,
        },
      ]);
    }
  };

  const updateLine = (id: string, patch: Partial<Line>) => {
    setLines(lines.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  };
  const removeLine = (id: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setLines(lines.filter((l) => l.id !== id));
  };

  const addRoom = () => {
    const next = DEFAULT_ROOMS.find((r) => !rooms.includes(r)) || `Area ${rooms.length + 1}`;
    setRooms([...rooms, next]); setActiveRoom(next);
  };

  const save = async () => {
    if (!customerId) return;
    setSaving(true);
    try {
      const payload = {
        customer_id: customerId,
        items: lines.map((l) => ({
          id: l.id, product_id: l.product_id, sku: l.sku, name: l.name, image: l.image,
          room: l.room, qty: l.qty, unit_price: l.unit_price,
          discount_pct: l.discount_pct, tax_pct: l.tax_pct,
        })),
        rooms,
        notes,
      };
      const created = await api.post<{ id: string; number: string }>("/quotations", payload);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      router.replace(`/(admin)/quotations/${created.id}` as any);
    } finally {
      setSaving(false);
    }
  };

  const CatalogPanel = (
    <View style={styles.panel}>
      <View style={styles.panelHead}>
        <Text style={type.titleMd}>Add products</Text>
        <View style={styles.searchWrap}>
          <Feather name="search" size={16} color={colors.onSurfaceMuted} />
          <TextInput
            testID="builder-search"
            value={q}
            onChangeText={setQ}
            placeholder="Search catalog · press ↵ to add first"
            placeholderTextColor={colors.onSurfaceMuted}
            style={styles.searchInput}
            onSubmitEditing={() => products[0] && addProduct(products[0])}
          />
        </View>
      </View>
      <FlatList
        data={products}
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
        ListEmptyComponent={<EmptyState icon="search" title="Type to search" subtitle="Search across brands, SKUs and tags." />}
      />
    </View>
  );

  const ReceiptPanel = (
    <View style={[styles.panel, { backgroundColor: colors.surfaceSecondary }]}>
      <View style={styles.panelHead}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={type.titleMd}>Quotation</Text>
          <StatusBadge status="draft" />
        </View>
        {/* Customer picker */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
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

        {/* Room tabs */}
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
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
          <Pressable onPress={addRoom} testID="add-room" style={[styles.roomTab, { borderStyle: "dashed" }]}>
            <Feather name="plus" size={13} color={colors.onSurfaceMuted} />
          </Pressable>
        </View>
      </View>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: spacing.md, gap: 8 }} keyboardShouldPersistTaps="handled">
        {rooms.map((r) => {
          const roomLines = lines.filter((l) => l.room === r);
          if (roomLines.length === 0 && r !== activeRoom) return null;
          return (
            <View key={r} style={{ gap: 8 }}>
              <Text style={type.overline}>{r}</Text>
              {roomLines.length === 0 ? (
                <Text style={type.caption}>No items in this room yet. Add from the left.</Text>
              ) : roomLines.map((l) => (
                <View key={l.id} style={styles.lineRow}>
                  {l.image ? <Image source={{ uri: l.image }} style={styles.lineThumb} /> : <View style={styles.lineThumb} />}
                  <View style={{ flex: 1, gap: 4 }}>
                    <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{l.name}</Text>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                      <Text style={type.caption}>{l.sku}</Text>
                    </View>
                    <View style={{ flexDirection: "row", gap: 8, marginTop: 2 }}>
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
                      <View style={styles.inputMini}>
                        <Text style={styles.inputLabel}>DISC %</Text>
                        <TextInput
                          testID={`disc-${l.id}`}
                          value={String(l.discount_pct)}
                          keyboardType="decimal-pad"
                          onChangeText={(v) => updateLine(l.id, { discount_pct: Math.min(100, Math.max(0, Number(v) || 0)) })}
                          style={styles.inputVal}
                          selectTextOnFocus
                        />
                      </View>
                    </View>
                  </View>
                  <View style={{ alignItems: "flex-end", gap: 4 }}>
                    <Text style={[type.mono, { fontSize: 13, fontWeight: "700" }]}>
                      {money((l.qty * l.unit_price) * (1 - l.discount_pct / 100))}
                    </Text>
                    <Pressable testID={`remove-${l.id}`} onPress={() => removeLine(l.id)} hitSlop={8}>
                      <Feather name="trash-2" size={14} color={colors.error} />
                    </Pressable>
                  </View>
                </View>
              ))}
            </View>
          );
        })}
        {lines.length === 0 ? (
          <EmptyState icon="file-plus" title="Add your first product" subtitle="Search on the left and tap to add. Everything totals live." />
        ) : null}
      </ScrollView>

      {/* Footer totals + CTA */}
      <View style={styles.footer}>
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
          onPress={save}
          disabled={saving || !customerId || lines.length === 0}
          style={({ pressed }) => [styles.saveBtn, {
            opacity: !customerId || lines.length === 0 ? 0.4 : pressed ? 0.9 : 1,
          }]}
        >
          <Feather name="check" size={16} color={colors.onBrand} />
          <Text style={styles.saveBtnText}>{saving ? "Saving…" : "Save quotation"}</Text>
        </Pressable>
      </View>
    </View>
  );

  const [tab, setTab] = useState<"catalog" | "receipt">("receipt");

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={styles.topbar}>
        <Pressable testID="builder-back" onPress={() => router.back()} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <Feather name="chevron-left" size={18} color={colors.onSurface} />
          <Text style={{ fontSize: 14, fontWeight: "500" }}>Cancel</Text>
        </Pressable>
        <View style={{ flex: 1, alignItems: "center" }}>
          <Text style={type.titleMd}>New Quotation</Text>
          <Text style={type.caption}>{lines.length} items · {money(totals.grand)}</Text>
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
  pRow: {
    flexDirection: "row", alignItems: "center", gap: 10, padding: 10, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  pThumb: { width: 44, height: 44, borderRadius: 8, backgroundColor: colors.surfaceTertiary },

  custChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border },
  custChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  roomTab: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  roomTabActive: { backgroundColor: colors.brand, borderColor: colors.brand },

  lineRow: {
    flexDirection: "row", gap: 10, padding: 10, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  lineThumb: { width: 48, height: 48, borderRadius: 8, backgroundColor: colors.surfaceTertiary },
  inputMini: {
    borderWidth: 1, borderColor: colors.border, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 3, minWidth: 62,
    backgroundColor: colors.surface,
  },
  inputLabel: { fontSize: 9, color: colors.onSurfaceMuted, fontWeight: "700", letterSpacing: 0.5 },
  inputVal: { fontSize: 13, fontFamily: Platform.select({ ios: "Menlo", android: "monospace" }), color: colors.onSurface, padding: 0, minWidth: 40 },

  footer: {
    padding: spacing.md, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface, gap: spacing.md,
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
});
