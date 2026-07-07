// BrandRail — narrow left rail for Quotation Builder V4.
// Accordion: tap a brand to select it AND expand its categories inline
// (nested rows, indented) — no separate "Categories" tab to hunt for.
// Categories are fetched lazily per-brand (cached) via the same /categories
// endpoint the rest of the app already uses, so counts stay authoritative.
// Below the rail: a compact "Recent Quotations" panel. Clicking a quotation
// restores the entire builder session (customer, rooms, items, discounts,
// UI state, filter selection).
// -----------------------------------------------------------------------------
import { Feather } from "@expo/vector-icons";
import { Image } from "expo-image";
import { useCallback, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { api } from "@/src/api/client";
import { colors, radius, spacing, type } from "@/src/theme/tokens";
import { color as ds, font as dsFont } from "@/src/design/tokens";
import { supplierLogoFor } from "@/src/design/BrandLogo";
import { useBuilder } from "../context/BuilderContext";
import { RecentQuotationsPanel } from "../panes/RecentQuotationsPanel";
import type { Category } from "../helpers/types";

export function BrandRail({ collapsed = false, onToggleCollapsed }: { collapsed?: boolean; onToggleCollapsed?: () => void }) {
  const b = useBuilder();
  const [q, setQ] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [catCache, setCatCache] = useState<Record<string, Category[]>>({});
  const [loadingBrandId, setLoadingBrandId] = useState<string | null>(null);
  const fetchedRef = useRef<Set<string>>(new Set());

  const filteredBrands = useMemo(() => {
    const src = b.brands;
    if (!q.trim()) return src;
    const needle = q.trim().toLowerCase();
    return src.filter((br) => (br.name || "").toLowerCase().includes(needle));
  }, [b.brands, q]);

  const ensureCategories = useCallback(async (brandId: string) => {
    if (fetchedRef.current.has(brandId)) return;
    fetchedRef.current.add(brandId);
    setLoadingBrandId(brandId);
    try {
      const cats = await api.get<Category[]>(`/categories?brand_id=${brandId}`);
      setCatCache((cur) => ({ ...cur, [brandId]: cats }));
    } catch {
      fetchedRef.current.delete(brandId); // allow a retry on next tap
    } finally {
      setLoadingBrandId((cur) => (cur === brandId ? null : cur));
    }
  }, []);

  const onTapBrand = useCallback((brandId: string) => {
    b.setSelectedBrandId(brandId);
    setExpanded((cur) => {
      const next = cur === brandId ? null : brandId;
      if (next) ensureCategories(brandId);
      return next;
    });
  }, [b, ensureCategories]);

  const onTapAll = useCallback(() => {
    b.setSelectedBrandId(null);
    setExpanded(null);
  }, [b]);

  const onTapCategory = useCallback((brandId: string, categoryId: string | null) => {
    if (b.selectedBrandId !== brandId) b.setSelectedBrandId(brandId);
    b.setSelectedCategoryId(categoryId);
  }, [b]);

  return (
    <View style={styles.panel}>
      <View style={[styles.head, collapsed && styles.headCollapsed]}>
        <Pressable
          onPress={onToggleCollapsed}
          style={[styles.collapseBtn, collapsed && { alignSelf: "center" }]}
          hitSlop={8}
          testID="rail-collapse-toggle"
          accessibilityLabel={collapsed ? "Expand brand rail" : "Collapse brand rail"}
        >
          <Feather name={collapsed ? "chevrons-right" : "chevrons-left"} size={14} color={ds.brassDeep} />
          {!collapsed ? <Text style={styles.collapseLabel}>Brands</Text> : null}
        </Pressable>
        {!collapsed ? (
          <View style={styles.searchWrap}>
            <Feather name="search" size={13} color={colors.onSurfaceMuted} />
            <TextInput
              value={q}
              onChangeText={setQ}
              placeholder="Search brands"
              placeholderTextColor={colors.onSurfaceMuted}
              style={styles.searchInput}
              testID="rail-search"
            />
            {q ? (
              <Pressable hitSlop={6} onPress={() => setQ("")}>
                <Feather name="x" size={12} color={colors.onSurfaceMuted} />
              </Pressable>
            ) : null}
          </View>
        ) : null}
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingVertical: 6, paddingHorizontal: collapsed ? 6 : 8 }}
        showsVerticalScrollIndicator={false}
      >
        <Pressable
          onPress={onTapAll}
          style={[styles.item, collapsed && styles.itemCollapsed, !b.selectedBrandId && styles.itemActive]}
          testID="rail-brand-all"
        >
          <View style={styles.itemIcon}>
            <Feather name="grid" size={13} color={colors.onSurfaceSecondary} />
          </View>
          {!collapsed ? (
            <>
              <Text style={[styles.itemLabel, !b.selectedBrandId && styles.itemLabelActive]} numberOfLines={1}>
                All brands
              </Text>
              <Text style={styles.itemCount}>{b.brands.reduce((s, br) => s + (br.product_count || 0), 0)}</Text>
            </>
          ) : null}
        </Pressable>

        {filteredBrands.map((br) => {
          const on = b.selectedBrandId === br.id;
          const isOpen = expanded === br.id;
          const cats = catCache[br.id] || [];
          return (
            <View key={br.id}>
              <Pressable
                onPress={() => onTapBrand(br.id)}
                style={[styles.item, collapsed && styles.itemCollapsed, on && styles.itemActive]}
                testID={`rail-brand-${br.name}`}
              >
                <View style={styles.brandBadge}>
                  {supplierLogoFor(br.name) ? (
                    <Image source={supplierLogoFor(br.name)} style={styles.brandBadgeLogo} contentFit="cover" />
                  ) : (
                    <Text style={styles.brandBadgeText}>{(br.name || "?").slice(0, 2).toUpperCase()}</Text>
                  )}
                </View>
                {!collapsed ? (
                  <>
                    <Text style={[styles.itemLabel, on && styles.itemLabelActive]} numberOfLines={1}>
                      {br.name}
                    </Text>
                    <Text style={styles.itemCount}>{br.product_count || 0}</Text>
                    <Feather
                      name="chevron-right"
                      size={13}
                      color={colors.onSurfaceMuted}
                      style={{ transform: [{ rotate: isOpen ? "90deg" : "0deg" }] }}
                    />
                  </>
                ) : null}
              </Pressable>

              {!collapsed && isOpen ? (
                loadingBrandId === br.id ? (
                  <View style={{ paddingVertical: 10, alignItems: "center" }}>
                    <ActivityIndicator size="small" color={ds.brass} />
                  </View>
                ) : (
                  <View style={styles.catGroup} testID={`rail-cats-${br.name}`}>
                    <Pressable
                      onPress={() => onTapCategory(br.id, null)}
                      style={[styles.catItem, on && !b.selectedCategoryId && styles.catItemActive]}
                    >
                      <View style={styles.catDot} />
                      <Text style={[styles.catLabel, on && !b.selectedCategoryId && styles.catLabelActive]}>
                        All {br.name}
                      </Text>
                    </Pressable>
                    {cats.map((c) => {
                      const catOn = on && b.selectedCategoryId === c.id;
                      return (
                        <Pressable
                          key={c.id}
                          onPress={() => onTapCategory(br.id, c.id)}
                          style={[styles.catItem, catOn && styles.catItemActive]}
                          testID={`rail-cat-${c.name}`}
                        >
                          <View style={[styles.catDot, catOn && { backgroundColor: ds.brass }]} />
                          <Text style={[styles.catLabel, catOn && styles.catLabelActive]} numberOfLines={1}>
                            {c.name}
                          </Text>
                          <Text style={styles.catCount}>{c.product_count || 0}</Text>
                        </Pressable>
                      );
                    })}
                  </View>
                )
              ) : null}
            </View>
          );
        })}

        {!collapsed ? (
          <>
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
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { flex: 1, backgroundColor: ds.canvas, borderRightWidth: StyleSheet.hairlineWidth, borderColor: ds.line },
  head: { padding: spacing.md, gap: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: ds.line },
  headCollapsed: { paddingHorizontal: 6, paddingVertical: spacing.md, alignItems: "center" },
  collapseBtn: {
    flexDirection: "row", alignItems: "center", gap: 8, minHeight: 32,
    paddingHorizontal: 8, borderRadius: radius.sm, backgroundColor: ds.brassTint,
    borderWidth: StyleSheet.hairlineWidth, borderColor: ds.brassLine,
  },
  collapseLabel: { fontSize: 11, fontWeight: "700", color: ds.brassDeep, letterSpacing: 0.8, textTransform: "uppercase" },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: 6,
    borderRadius: radius.md, backgroundColor: ds.surface, paddingHorizontal: 10,
    borderWidth: StyleSheet.hairlineWidth, borderColor: ds.line,
  },
  searchInput: { flex: 1, fontSize: 13, paddingVertical: 8, color: ds.ink },

  item: {
    flexDirection: "row", alignItems: "center", gap: 10,
    paddingHorizontal: 8, paddingVertical: 8, borderRadius: radius.sm, marginVertical: 1,
    borderLeftWidth: 3, borderLeftColor: "transparent",
  },
  itemCollapsed: { justifyContent: "center", paddingHorizontal: 0, minHeight: 40 },
  itemActive: { backgroundColor: ds.sunken, borderLeftColor: ds.brass },
  itemIcon: {
    width: 22, height: 22, borderRadius: 6, backgroundColor: ds.sunken,
    alignItems: "center", justifyContent: "center",
  },
  brandBadge: {
    width: 22, height: 22, borderRadius: 6, backgroundColor: ds.surface,
    borderWidth: StyleSheet.hairlineWidth, borderColor: ds.line,
    alignItems: "center", justifyContent: "center", overflow: "hidden",
  },
  brandBadgeLogo: { width: "100%", height: "100%" },
  brandBadgeText: { fontSize: 9, fontWeight: "700", color: ds.inkMid, letterSpacing: 0.3 },
  itemLabel: { flex: 1, fontSize: 13, color: ds.inkMid, fontWeight: "500" },
  itemLabelActive: { color: ds.ink, fontWeight: "600" },
  itemCount: { fontSize: 11, color: ds.inkSoft, fontVariant: ["tabular-nums"] },

  // Accordion — nested category rows under an expanded brand.
  catGroup: { marginLeft: 14, marginBottom: 2, borderLeftWidth: 1, borderLeftColor: ds.line, paddingLeft: 8 },
  catItem: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: 8, paddingVertical: 6, borderRadius: radius.sm, marginVertical: 1,
  },
  catItemActive: { backgroundColor: ds.sunken },
  catDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: ds.line },
  catLabel: { flex: 1, fontSize: 12, color: ds.inkSoft, fontWeight: "500" },
  catLabelActive: { color: ds.ink, fontWeight: "600" },
  catCount: { fontSize: 10.5, color: ds.inkSoft, fontVariant: ["tabular-nums"] },

  quickActionsWrap: { marginTop: spacing.lg, gap: 4, paddingHorizontal: 4 },
  groupLabel: { fontSize: 10, fontWeight: "600", color: ds.inkSoft, letterSpacing: 1.2, textTransform: "uppercase", paddingHorizontal: 4, marginBottom: 4 },
  quickAction: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: 10, paddingVertical: 8, borderRadius: radius.sm,
    backgroundColor: ds.surface, borderWidth: StyleSheet.hairlineWidth, borderColor: ds.line,
  },
  quickActionLabel: { flex: 1, fontSize: 12, color: ds.ink, fontWeight: "500" },
  kbHint: { fontSize: 10, color: ds.inkSoft, fontWeight: "600" },
});

