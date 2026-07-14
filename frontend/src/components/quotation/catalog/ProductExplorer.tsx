// ProductExplorer — the center pane in V4. Premium product grid with
// virtualisation, badges (Popular / Frequently used / Recent), color
// swatches, favourite heart, quick-preview → ProductModal, and "Add" button.
//
// Uses FlatList w/ numColumns for grid layout. Search + sort + filters live
// in the sticky header.
import { Feather } from "@expo/vector-icons";
import { Image } from "expo-image";
import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, FlatList, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View } from "react-native";

import { EmptyState } from "@/src/components/ui";
import { ProductImage } from "@/src/components/ProductImage";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";
import { color as ds } from "@/src/design/tokens";
import { supplierLogoFor } from "@/src/design/BrandLogo";
import { storage } from "@/src/utils/storage";
import { useBuilder } from "../context/BuilderContext";
import { VariantSwatchStrip } from "../shared/VariantChip";
import { productImageList } from "../helpers/media";
import { quotationGridColumns } from "../helpers/responsive";
import type { Product, ProductVariant } from "../helpers/types";

const PHONE_BREAKPOINT = 640;
const RECENT_SEARCHES_KEY = "forge.builder.recentSearches.v1";
const MAX_RECENT_SEARCHES = 8;

type SortKey = "popular" | "recent" | "price_asc" | "price_desc" | "name";

const SORT_OPTIONS: { k: SortKey; label: string; icon: React.ComponentProps<typeof Feather>["name"] }[] = [
  { k: "popular", label: "Most used", icon: "trending-up" },
  { k: "recent", label: "Recent", icon: "clock" },
  { k: "price_asc", label: "Price ↑", icon: "arrow-up" },
  { k: "price_desc", label: "Price ↓", icon: "arrow-down" },
  { k: "name", label: "A–Z", icon: "align-left" },
];

export function ProductExplorer() {
  const b = useBuilder();
  const { width: windowWidth } = useWindowDimensions();
  const isPhone = windowWidth < PHONE_BREAKPOINT;

  const numCols = quotationGridColumns(windowWidth);
  const brandName = useMemo(() => {
    if (!b.selectedBrandId) return "All brands";
    return b.brands.find((x) => x.id === b.selectedBrandId)?.name || "Brand";
  }, [b.brands, b.selectedBrandId]);

  const catName = useMemo(() => {
    if (!b.selectedCategoryId) return null;
    return b.categories.find((c) => c.id === b.selectedCategoryId)?.name || null;
  }, [b.categories, b.selectedCategoryId]);

  // ---- Recent searches (phone catalog experience parity) ----------------
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  useEffect(() => {
    (async () => {
      const raw = await storage.getItem<string>(RECENT_SEARCHES_KEY, "[]");
      try {
        const parsed = JSON.parse(raw || "[]");
        if (Array.isArray(parsed)) setRecentSearches(parsed.filter((x) => typeof x === "string"));
      } catch { /* ignore corrupt cache */ }
    })();
  }, []);

  const commitSearch = useCallback((term: string) => {
    const t = term.trim();
    if (t.length < 2) return;
    setRecentSearches((cur) => {
      const next = [t, ...cur.filter((x) => x.toLowerCase() !== t.toLowerCase())].slice(0, MAX_RECENT_SEARCHES);
      storage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const clearRecentSearches = useCallback(() => {
    setRecentSearches([]);
    storage.setItem(RECENT_SEARCHES_KEY, JSON.stringify([]));
  }, []);

  const totalBrandProducts = useMemo(
    () => b.brands.reduce((s, br) => s + (br.product_count || 0), 0),
    [b.brands],
  );

  return (
    <View style={styles.panel}>
      <View style={styles.head}>
        <View style={styles.crumbs}>
          <Text style={styles.crumb}>{brandName}</Text>
          {catName ? (
            <>
              <Feather name="chevron-right" size={12} color={colors.onSurfaceMuted} />
              <Text style={[styles.crumb, styles.crumbActive]}>{catName}</Text>
            </>
          ) : null}
          <Text style={styles.crumbCount}>· {b.productTotal} products</Text>
        </View>

        <View style={styles.searchWrap}>
          <Feather name="search" size={14} color={colors.onSurfaceMuted} />
          <TextInput
            ref={b.searchRef}
            value={b.q}
            onChangeText={b.setQ}
            onSubmitEditing={() => commitSearch(b.q)}
            placeholder={Platform.OS === "web" ? "Search products · SKU · brand · finish · color · ⌘K" : "Search products"}
            placeholderTextColor={colors.onSurfaceMuted}
            style={styles.searchInput}
            testID="explorer-search"
            returnKeyType="search"
          />
          {b.q ? (
            <Pressable hitSlop={8} onPress={() => b.setQ("")} testID="explorer-search-clear">
              <Feather name="x" size={14} color={colors.onSurfaceMuted} />
            </Pressable>
          ) : null}
        </View>

        {!b.q && recentSearches.length > 0 ? (
          <View style={styles.recentRow}>
            <Text style={styles.recentLabel}>Recent</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
              {recentSearches.map((term) => (
                <Pressable
                  key={term}
                  onPress={() => { b.setQ(term); commitSearch(term); }}
                  style={styles.recentChip}
                  testID={`recent-search-${term}`}
                >
                  <Feather name="clock" size={10} color={colors.onSurfaceSecondary} />
                  <Text style={styles.recentChipLabel} numberOfLines={1}>{term}</Text>
                </Pressable>
              ))}
              <Pressable onPress={clearRecentSearches} style={styles.recentClear} testID="recent-search-clear">
                <Text style={styles.recentClearLabel}>Clear</Text>
              </Pressable>
            </ScrollView>
          </View>
        ) : null}

        {/* Mobile-only: brand + category selectors (tablet/desktop already show
            these permanently in BrandRail alongside the grid, so this block is
            redundant there and intentionally hidden). Keeps the phone catalog
            experience at full parity with desktop browsing. */}
        {isPhone ? (
          <>
            <ScrollView
              horizontal showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ gap: 6, paddingVertical: 2 }}
              testID="mobile-brand-selector"
            >
              <FilterPill
                label="All brands"
                count={totalBrandProducts}
                active={!b.selectedBrandId}
                onPress={() => b.setSelectedBrandId(null)}
                testID="mobile-brand-all"
              />
              {b.brands.map((br) => (
                <FilterPill
                  key={br.id}
                  label={br.name}
                  logo={supplierLogoFor(br.name)}
                  count={br.product_count}
                  active={b.selectedBrandId === br.id}
                  onPress={() => b.setSelectedBrandId(b.selectedBrandId === br.id ? null : br.id)}
                  testID={`mobile-brand-${br.name}`}
                />
              ))}
            </ScrollView>
            {b.categoriesForRail.length > 0 ? (
              <ScrollView
                horizontal showsHorizontalScrollIndicator={false}
                contentContainerStyle={{ gap: 6, paddingVertical: 2 }}
                testID="mobile-category-selector"
              >
                <FilterPill
                  label={`All ${brandName}`}
                  active={!b.selectedCategoryId}
                  onPress={() => b.setSelectedCategoryId(null)}
                  testID="mobile-category-all"
                />
                {b.categoriesForRail.map((c) => (
                  <FilterPill
                    key={c.id}
                    label={c.name}
                    count={c.product_count}
                    active={b.selectedCategoryId === c.id}
                    onPress={() => b.setSelectedCategoryId(b.selectedCategoryId === c.id ? null : c.id)}
                    testID={`mobile-category-${c.name}`}
                  />
                ))}
              </ScrollView>
            ) : null}
          </>
        ) : null}

        <View style={styles.sortRow}>
          {SORT_OPTIONS.map((opt) => {
            const on = b.sortKey === opt.k;
            return (
              <Pressable
                key={opt.k}
                onPress={() => b.setSortKey(opt.k)}
                style={[styles.sortChip, on && styles.sortChipActive]}
                testID={`sort-${opt.k}`}
              >
                <Feather name={opt.icon} size={11} color={on ? colors.onBrand : colors.onSurfaceSecondary} />
                <Text style={[styles.sortLabel, on && styles.sortLabelActive]}>{opt.label}</Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      <FlatList
        data={b.products}
        key={`grid-${numCols}`}
        numColumns={numCols}
        style={{ flex: 1, minHeight: 0 }}
        columnWrapperStyle={numCols > 1 ? { gap: 12 } : undefined}
        keyExtractor={(p) => p.id}
        contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: 32 }}
        keyboardShouldPersistTaps="handled"
        renderItem={({ item }) => (
          <ProductGridCard
            product={item}
            favourite={b.favouriteIds.includes(item.id)}
            onToggleFav={() => b.toggleFavourite(item.id)}
            onQuickAdd={(p, v) => b.addFromProduct(p, v)}
            onOpenModal={(p) => b.openProductModal(p)}
          />
        )}
        removeClippedSubviews={Platform.OS !== "web"}
        initialNumToRender={24}
        maxToRenderPerBatch={24}
        windowSize={21}
        onEndReached={() => b.loadMoreProducts()}
        onEndReachedThreshold={0.5}
        ListFooterComponent={
          b.productLoadingMore ? (
            <View style={{ paddingVertical: 20, alignItems: "center" }}>
              <ActivityIndicator size="small" color={ds.brass} />
            </View>
          ) : !b.productLoading && b.products.length > 0 && !b.productHasMore ? (
            <Text style={styles.endOfList}>
              {b.products.length} of {b.productTotal} products — you've reached the end
            </Text>
          ) : null
        }
        ListEmptyComponent={
          b.productLoading ? (
            <View style={[styles.skeletonGrid, { flexDirection: numCols > 1 ? "row" : "column", flexWrap: "wrap" }]}>
              {Array.from({ length: numCols > 1 ? 12 : 6 }).map((_, i) => (
                <View key={i} style={[styles.skeletonCard, { width: numCols > 1 ? `${100 / numCols}%` : "100%" }]}>
                  <View style={styles.skeletonMedia} />
                  <View style={{ padding: 10, gap: 8 }}>
                    <View style={[styles.skeletonLine, { width: "85%" }]} />
                    <View style={[styles.skeletonLine, { width: "50%", height: 9 }]} />
                    <View style={[styles.skeletonLine, { width: "40%", height: 13, marginTop: 4 }]} />
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <EmptyState icon="package" title="No products match" subtitle="Try clearing filters or a different search term." />
          )
        }
      />
    </View>
  );
}

// -----------------------------------------------------------------------------
// Product grid card
// -----------------------------------------------------------------------------
type CardProps = {
  product: Product;
  favourite: boolean;
  onToggleFav: () => void;
  onQuickAdd: (p: Product, v?: ProductVariant) => void;
  onOpenModal: (p: Product) => void;
};

function ProductGridCardImpl({ product, favourite, onToggleFav, onQuickAdd, onOpenModal }: CardProps) {
  const badges: { label: string; tone: "popular" | "frequent" | "recent" }[] = [];
  if (product.popular) badges.push({ label: "Popular", tone: "popular" });
  else if (product.frequently_used) badges.push({ label: "Frequently used", tone: "frequent" });
  else if (product.recently_used) badges.push({ label: "Recent", tone: "recent" });

  return (
    <Pressable
      onPress={() => onOpenModal(product)}
      onLongPress={() => onQuickAdd(product)}
      delayLongPress={220}
      style={({ pressed }) => [styles.card, pressed && { transform: [{ scale: 0.995 }] }]}
      testID={`product-card-${product.sku}`}
    >
      <View style={styles.cardMedia}>
        <ProductImage source={productImageList(product)} style={styles.thumb} fallbackLabel={product.sku} />
        {/* Overlay: badges + fav heart */}
        <View style={styles.badgeRow}>
          {badges.slice(0, 1).map((bg) => (
            <View
              key={bg.label}
              style={[
                styles.badge,
                bg.tone === "popular" && { backgroundColor: ds.brassTint },
                bg.tone === "frequent" && { backgroundColor: ds.sunken },
                bg.tone === "recent" && { backgroundColor: ds.sunken },
              ]}
            >
              <Text
                style={[
                  styles.badgeText,
                  bg.tone === "popular" && { color: ds.brassDeep },
                  bg.tone === "frequent" && { color: ds.inkMid },
                  bg.tone === "recent" && { color: ds.inkMid },
                ]}
              >
                {bg.label}
              </Text>
            </View>
          ))}
        </View>
        <Pressable
          hitSlop={8}
          onPress={onToggleFav}
          style={styles.favBtn}
          testID={`fav-${product.sku}`}
        >
          <Feather name="heart" size={14} color={favourite ? ds.brass : colors.onSurfaceMuted} />
        </Pressable>
      </View>

      <View style={styles.cardBody}>
        <Text style={styles.cardName} numberOfLines={2}>{product.name}</Text>
        <Text style={styles.cardSku} numberOfLines={1}>
          {product.sku}{product.brand_name ? ` · ${product.brand_name}` : ""}
        </Text>

        <View style={styles.priceRow}>
          <View style={styles.priceCol}>
            <Text style={styles.price} numberOfLines={1} ellipsizeMode="clip">{money(product.price)}</Text>
            {product.mrp && product.mrp > product.price ? (
              <Text style={styles.mrp} numberOfLines={1} ellipsizeMode="clip">{money(product.mrp)}</Text>
            ) : null}
          </View>
          <Pressable
            onPress={() => onQuickAdd(product)}
            style={styles.addBtn}
            hitSlop={4}
            testID={`add-${product.sku}`}
          >
            <Feather name="plus" size={13} color={colors.onBrand} />
            <Text style={styles.addLabel} numberOfLines={1}>Add</Text>
          </Pressable>
        </View>

        <View style={styles.variantSlot}>
          <VariantSwatchStrip product={product} onSelect={(v) => onQuickAdd(product, v)} paddingLeft={0} />
        </View>
      </View>
    </Pressable>
  );
}

const ProductGridCard = memo(
  ProductGridCardImpl,
  (a, b) =>
    a.product.id === b.product.id &&
    a.product.price === b.product.price &&
    a.favourite === b.favourite,
);

// -----------------------------------------------------------------------------
// FilterPill — compact brand/category selector chip used in the phone-only
// browsing row. Mirrors the standalone Catalog screen's BrandPill so the
// mobile builder picker matches the same browsing language.
// -----------------------------------------------------------------------------
function FilterPill({
  label, logo, count, active, onPress, testID,
}: {
  label: string; logo?: any; count?: number;
  active?: boolean; onPress?: () => void; testID?: string;
}) {
  return (
    <Pressable onPress={onPress} testID={testID} style={[styles.filterPill, active && styles.filterPillActive]}>
      {logo ? (
        <View style={styles.filterPillLogoWrap}>
          <Image source={logo} style={{ width: "100%", height: "100%" }} contentFit="cover" />
        </View>
      ) : null}
      <Text style={[styles.filterPillLabel, active && styles.filterPillLabelActive]} numberOfLines={1}>
        {label}
      </Text>
      {count != null ? (
        <Text style={[styles.filterPillCount, active && styles.filterPillCountActive]} numberOfLines={1}>
          {count}
        </Text>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  panel: { flex: 1, minHeight: 0, overflow: "hidden", backgroundColor: colors.surface },
  head: {
    paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary, gap: spacing.sm,
  },
  crumbs: { flexDirection: "row", alignItems: "center", gap: 6 },
  crumb: { fontSize: 13, fontWeight: "600", color: colors.onSurfaceSecondary },
  crumbActive: { color: colors.onSurface },
  crumbCount: { fontSize: 12, color: colors.onSurfaceMuted, marginLeft: 4 },

  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: 8,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
    paddingHorizontal: 12, borderRadius: radius.md, minHeight: 38,
  },
  searchInput: { flex: 1, fontSize: 13, paddingVertical: 8, color: colors.onSurface },

  recentRow: { gap: 4 },
  recentLabel: { fontSize: 10, fontWeight: "700", color: colors.onSurfaceMuted, letterSpacing: 0.8, textTransform: "uppercase" },
  recentChip: {
    flexDirection: "row", alignItems: "center", gap: 5,
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill,
    backgroundColor: colors.surface, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  recentChipLabel: { fontSize: 11, fontWeight: "600", color: colors.onSurfaceSecondary, maxWidth: 140 },
  recentClear: { paddingHorizontal: 8, paddingVertical: 5, justifyContent: "center" },
  recentClearLabel: { fontSize: 11, fontWeight: "600", color: colors.onSurfaceMuted, textDecorationLine: "underline" },

  filterPill: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 11, paddingLeft: 11, height: 34, borderRadius: 999,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  filterPillActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  filterPillLogoWrap: {
    width: 18, height: 18, borderRadius: 9, overflow: "hidden",
    backgroundColor: "#fff", borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  filterPillLabel: { fontSize: 12, fontWeight: "600", color: colors.onSurface, maxWidth: 140 },
  filterPillLabelActive: { color: colors.onBrand, fontWeight: "700" },
  filterPillCount: { fontSize: 10, color: colors.onSurfaceMuted },
  filterPillCountActive: { color: colors.onBrand, opacity: 0.85 },

  sortRow: { flexDirection: "row", gap: 6, flexWrap: "wrap" },
  sortChip: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill,
    backgroundColor: colors.surfaceTertiary,
  },
  sortChipActive: { backgroundColor: colors.brand },
  sortLabel: { fontSize: 11, fontWeight: "600", color: colors.onSurfaceSecondary },
  sortLabelActive: { color: colors.onBrand },

  card: {
    flex: 1, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    overflow: "hidden",
  },
  cardMedia: { aspectRatio: 1, backgroundColor: colors.surfaceTertiary, position: "relative" },
  thumb: { width: "100%", height: "100%" },
  badgeRow: { position: "absolute", top: 8, left: 8, flexDirection: "row", gap: 4 },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999 },
  badgeText: { fontSize: 10, fontWeight: "700", letterSpacing: 0.2 },
  favBtn: {
    position: "absolute", top: 8, right: 8,
    width: 26, height: 26, borderRadius: 999, backgroundColor: "rgba(255,255,255,0.92)",
    alignItems: "center", justifyContent: "center",
  },
  // Fixed-slot layout: cardName reserves 2 lines' worth of height always
  // (numberOfLines=2 + explicit minHeight) and the variant strip reserves
  // its row height even when a product has no variants — this is what
  // keeps every card in the grid the same height regardless of content.
  cardBody: { padding: 10, gap: 6 },
  cardName: { fontSize: 13, fontWeight: "600", color: colors.onSurface, lineHeight: 17, minHeight: 34 },
  cardSku: { fontSize: 11, color: colors.onSurfaceMuted, fontVariant: ["tabular-nums"] },
  priceRow: { flexDirection: "row", alignItems: "center", gap: 6, minHeight: 32 },
  priceCol: { flex: 1, minWidth: 0 },
  price: { fontSize: 14, fontWeight: "600", color: colors.onSurface, fontVariant: ["tabular-nums"], letterSpacing: -0.1 },
  mrp: { fontSize: 10, color: colors.onSurfaceMuted, textDecorationLine: "line-through", fontVariant: ["tabular-nums"] },
  addBtn: {
    flexDirection: "row", alignItems: "center", gap: 4, flexShrink: 0,
    paddingHorizontal: 9, paddingVertical: 6, borderRadius: radius.sm, backgroundColor: colors.brand,
  },
  addLabel: { fontSize: 11, fontWeight: "700", color: colors.onBrand, letterSpacing: 0.2 },
  variantSlot: { minHeight: 26, justifyContent: "center" },
  endOfList: {
    textAlign: "center", fontSize: 11, color: colors.onSurfaceMuted,
    paddingVertical: 20, paddingHorizontal: 24,
  },
  skeletonGrid: { gap: 12 },
  skeletonCard: {
    padding: 4,
  },
  skeletonMedia: {
    aspectRatio: 1, borderRadius: radius.md, backgroundColor: colors.surfaceTertiary,
  },
  skeletonLine: {
    height: 11, borderRadius: 4, backgroundColor: colors.surfaceTertiary,
  },
});
