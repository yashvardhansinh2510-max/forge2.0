// BrandRail — narrow left rail for Quotation Builder V4.
// Two tabs (Brands · Categories) + search + collapsible groups + product counts.
// Below the rail: a compact "Recent Quotations" panel. Clicking a quotation
// restores the entire builder session (customer, rooms, items, discounts,
// UI state, filter selection).
// -----------------------------------------------------------------------------
import { Feather } from "@expo/vector-icons";
import { useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, spacing, type } from "@/src/theme/tokens";
import { useBuilder } from "../context/BuilderContext";
import { RecentQuotationsPanel } from "../panes/RecentQuotationsPanel";

type Tab = "brands" | "categories";

export function BrandRail() {
  const b = useBuilder();
  const [tab, setTab] = useState<Tab>("brands");
  const [q, setQ] = useState("");

  const filteredBrands = useMemo(() => {
    const src = b.brands;
    if (!q.trim()) return src;
    const needle = q.trim().toLowerCase();
    return src.filter((br) => (br.name || "").toLowerCase().includes(needle));
  }, [b.brands, q]);

  const filteredCats = useMemo(() => {
    const src = b.categoriesForRail;
    if (!q.trim()) return src;
    const needle = q.trim().toLowerCase();
    return src.filter((c) => (c.name || "").toLowerCase().includes(needle));
  }, [b.categoriesForRail, q]);

  return (
    <View style={styles.panel}>
      <View style={styles.head}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <View style={styles.brandTile}><Feather name="home" size={13} color="#fff" /></View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.brand} numberOfLines={1}>BuildCon House</Text>
            <Text style={styles.brandSub} numberOfLines={1}>Let you live better</Text>
          </View>
        </View>
        <View style={styles.tabs}>
          {[
            { k: "brands" as const, label: "Brands" },
            { k: "categories" as const, label: "Categories" },
          ].map((t) => {
            const on = tab === t.k;
            return (
              <Pressable
                key={t.k}
                onPress={() => setTab(t.k)}
                style={[styles.tab, on && styles.tabActive]}
                testID={`rail-tab-${t.k}`}
              >
                <Text style={[styles.tabLabel, on && styles.tabLabelActive]}>{t.label}</Text>
              </Pressable>
            );
          })}
        </View>
        <View style={styles.searchWrap}>
          <Feather name="search" size={13} color={colors.onSurfaceMuted} />
          <TextInput
            value={q}
            onChangeText={setQ}
            placeholder={tab === "brands" ? "Search brands" : "Search categories"}
            placeholderTextColor={colors.onSurfaceMuted}
            style={styles.searchInput}
          />
          {q ? (
            <Pressable hitSlop={6} onPress={() => setQ("")}>
              <Feather name="x" size={12} color={colors.onSurfaceMuted} />
            </Pressable>
          ) : null}
        </View>
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingVertical: 6, paddingHorizontal: 8 }}
        showsVerticalScrollIndicator={false}
      >
        {tab === "brands" ? (
          <>
            <Pressable
              onPress={() => b.setSelectedBrandId(null)}
              style={[styles.item, !b.selectedBrandId && styles.itemActive]}
              testID="rail-brand-all"
            >
              <View style={styles.itemIcon}>
                <Feather name="grid" size={13} color={colors.onSurfaceSecondary} />
              </View>
              <Text style={[styles.itemLabel, !b.selectedBrandId && styles.itemLabelActive]} numberOfLines={1}>
                All brands
              </Text>
              <Text style={styles.itemCount}>{b.brands.reduce((s, br) => s + (br.product_count || 0), 0)}</Text>
            </Pressable>
            {filteredBrands.map((br) => {
              const on = b.selectedBrandId === br.id;
              return (
                <Pressable
                  key={br.id}
                  onPress={() => b.setSelectedBrandId(br.id)}
                  style={[styles.item, on && styles.itemActive]}
                  testID={`rail-brand-${br.name}`}
                >
                  <View style={styles.brandBadge}>
                    <Text style={styles.brandBadgeText}>{(br.name || "?").slice(0, 2).toUpperCase()}</Text>
                  </View>
                  <Text style={[styles.itemLabel, on && styles.itemLabelActive]} numberOfLines={1}>
                    {br.name}
                  </Text>
                  <Text style={styles.itemCount}>{br.product_count || 0}</Text>
                </Pressable>
              );
            })}
          </>
        ) : (
          <>
            <Pressable
              onPress={() => b.setSelectedCategoryId(null)}
              style={[styles.item, !b.selectedCategoryId && styles.itemActive]}
            >
              <View style={styles.itemIcon}>
                <Feather name="layers" size={13} color={colors.onSurfaceSecondary} />
              </View>
              <Text style={[styles.itemLabel, !b.selectedCategoryId && styles.itemLabelActive]}>
                All categories
              </Text>
              <Text style={styles.itemCount}>{filteredCats.reduce((s, c) => s + (c.product_count || 0), 0)}</Text>
            </Pressable>
            {filteredCats.map((c) => {
              const on = b.selectedCategoryId === c.id;
              return (
                <Pressable
                  key={c.id}
                  onPress={() => b.setSelectedCategoryId(c.id)}
                  style={[styles.item, on && styles.itemActive]}
                  testID={`rail-cat-${c.name}`}
                >
                  <View style={styles.itemIcon}>
                    <Feather name="circle" size={9} color={colors.onSurfaceMuted} />
                  </View>
                  <Text style={[styles.itemLabel, on && styles.itemLabelActive]} numberOfLines={1}>
                    {c.name}
                  </Text>
                  <Text style={styles.itemCount}>{c.product_count || 0}</Text>
                </Pressable>
              );
            })}
          </>
        )}

        {/* Quick action row */}
        <View style={styles.quickActionsWrap}>
          <Text style={styles.groupLabel}>Quick actions</Text>
          <Pressable style={styles.quickAction} onPress={() => b.setCustomProductSheetOpen(true)} testID="rail-custom-product">
            <Feather name="plus" size={14} color={colors.onSurface} />
            <Text style={styles.quickActionLabel}>Custom product</Text>
          </Pressable>
          <Pressable style={styles.quickAction} onPress={() => b.searchRef.current?.focus()} testID="rail-focus-search">
            <Feather name="search" size={14} color={colors.onSurface} />
            <Text style={styles.quickActionLabel}>Search catalog</Text>
            <Text style={styles.kbHint}>⌘K</Text>
          </Pressable>
        </View>

        {/* Recent quotations */}
        <RecentQuotationsPanel />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { flex: 1, backgroundColor: colors.surfaceInverse },
  head: { padding: spacing.md, gap: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: "#27272A" },
  brand: { fontSize: 14, fontWeight: "700", color: "#FAFAFA", letterSpacing: -0.2 },
  brandSub: { fontSize: 10, color: "#A1A1AA", marginTop: 1 },
  brandTile: {
    width: 26, height: 26, borderRadius: 8,
    backgroundColor: colors.brand,
    alignItems: "center", justifyContent: "center",
  },
  tabs: { flexDirection: "row", backgroundColor: "#27272A", borderRadius: radius.md, padding: 3, gap: 3 },
  tab: { flex: 1, paddingVertical: 6, alignItems: "center", justifyContent: "center", borderRadius: radius.sm },
  tabActive: { backgroundColor: "#3F3F46" },
  tabLabel: { fontSize: 12, fontWeight: "600", color: "#A1A1AA" },
  tabLabelActive: { color: "#FAFAFA" },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: 6,
    borderRadius: radius.md, backgroundColor: "#27272A", paddingHorizontal: 10,
  },
  searchInput: { flex: 1, fontSize: 13, paddingVertical: 8, color: "#FAFAFA" },

  item: {
    flexDirection: "row", alignItems: "center", gap: 10,
    paddingHorizontal: 8, paddingVertical: 8, borderRadius: radius.sm, marginVertical: 1,
  },
  itemActive: { backgroundColor: "#27272A" },
  itemIcon: {
    width: 22, height: 22, borderRadius: 6, backgroundColor: "#27272A",
    alignItems: "center", justifyContent: "center",
  },
  brandBadge: {
    width: 22, height: 22, borderRadius: 6, backgroundColor: "#FAFAFA",
    alignItems: "center", justifyContent: "center",
  },
  brandBadgeText: { fontSize: 9, fontWeight: "800", color: "#111", letterSpacing: 0.3 },
  itemLabel: { flex: 1, fontSize: 13, color: "#D4D4D8", fontWeight: "500" },
  itemLabelActive: { color: "#FAFAFA", fontWeight: "600" },
  itemCount: { fontSize: 11, color: "#71717A", fontVariant: ["tabular-nums"] },

  quickActionsWrap: { marginTop: spacing.lg, gap: 4, paddingHorizontal: 4 },
  groupLabel: { fontSize: 10, fontWeight: "700", color: "#71717A", letterSpacing: 1.2, textTransform: "uppercase", paddingHorizontal: 4, marginBottom: 4 },
  quickAction: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: 10, paddingVertical: 8, borderRadius: radius.sm,
    backgroundColor: "#27272A",
  },
  quickActionLabel: { flex: 1, fontSize: 12, color: "#FAFAFA", fontWeight: "500" },
  kbHint: { fontSize: 10, color: "#71717A", fontWeight: "700" },
});
