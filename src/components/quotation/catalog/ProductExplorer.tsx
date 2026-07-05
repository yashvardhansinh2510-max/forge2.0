// ProductExplorer — the center pane in V4. Premium product grid with
// virtualisation, badges (Popular / Frequently used / Recent), color
// swatches, favourite heart, quick-preview → ProductModal, and "Add" button.
//
// Uses FlatList w/ numColumns for grid layout. Search + sort + filters live
// in the sticky header.
import { Feather } from "@expo/vector-icons";
import { memo, useMemo } from "react";
import { FlatList, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { EmptyState } from "@/src/components/ui";
import { ProductImage } from "@/src/components/ProductImage";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";
import { useBuilder } from "../context/BuilderContext";
import { VariantSwatchStrip } from "../shared/VariantChip";
import type { Product, ProductVariant } from "../helpers/types";

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

  const numCols = 2;
  const brandName = useMemo(() => {
    if (!b.selectedBrandId) return "All brands";
    return b.brands.find((x) => x.id === b.selectedBrandId)?.name || "Brand";
  }, [b.brands, b.selectedBrandId]);

  const catName = useMemo(() => {
    if (!b.selectedCategoryId) return null;
    return b.categories.find((c) => c.id === b.selectedCategoryId)?.name || null;
  }, [b.categories, b.selectedCategoryId]);

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
            placeholder={Platform.OS === "web" ? "Search products · SKU · brand · finish · color · ⌘K" : "Search products"}
            placeholderTextColor={colors.onSurfaceMuted}
            style={styles.searchInput}
            testID="explorer-search"
            returnKeyType="search"
          />
          {b.q ? (
            <Pressable hitSlop={8} onPress={() => b.setQ("")}>
              <Feather name="x" size={14} color={colors.onSurfaceMuted} />
            </Pressable>
          ) : null}
        </View>

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
        columnWrapperStyle={{ gap: 12 }}
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
        removeClippedSubviews
        initialNumToRender={10}
        maxToRenderPerBatch={10}
        windowSize={7}
        ListEmptyComponent={
          <EmptyState
            icon={b.productLoading ? "loader" : "package"}
            title={b.productLoading ? "Loading products…" : "No products match"}
            subtitle={b.productLoading ? "Fetching latest catalog" : "Try clearing filters or a different search term."}
          />
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
        <ProductImage source={product.images} style={styles.thumb} fallbackLabel={product.sku} />
        {/* Overlay: badges + fav heart */}
        <View style={styles.badgeRow}>
          {badges.slice(0, 1).map((bg) => (
            <View
              key={bg.label}
              style={[
                styles.badge,
                bg.tone === "popular" && { backgroundColor: "#FEF3C7" },
                bg.tone === "frequent" && { backgroundColor: "#DBEAFE" },
                bg.tone === "recent" && { backgroundColor: "#E4E4E7" },
              ]}
            >
              <Text
                style={[
                  styles.badgeText,
                  bg.tone === "popular" && { color: "#92400E" },
                  bg.tone === "frequent" && { color: "#1E40AF" },
                  bg.tone === "recent" && { color: "#3F3F46" },
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
          <Feather name="heart" size={14} color={favourite ? "#E11D48" : colors.onSurfaceMuted} />
        </Pressable>
      </View>

      <View style={styles.cardBody}>
        <Text style={styles.cardName} numberOfLines={2}>{product.name}</Text>
        <Text style={styles.cardSku} numberOfLines={1}>
          {product.sku}{product.brand_name ? ` · ${product.brand_name}` : ""}
        </Text>

        <View style={styles.priceRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.price}>{money(product.price)}</Text>
            {product.mrp && product.mrp > product.price ? (
              <Text style={styles.mrp}>{money(product.mrp)}</Text>
            ) : null}
          </View>
          <Pressable
            onPress={() => onQuickAdd(product)}
            style={styles.addBtn}
            hitSlop={4}
            testID={`add-${product.sku}`}
          >
            <Feather name="plus" size={14} color={colors.onBrand} />
            <Text style={styles.addLabel}>Add</Text>
          </Pressable>
        </View>

        <VariantSwatchStrip product={product} onSelect={(v) => onQuickAdd(product, v)} />
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

const styles = StyleSheet.create({
  panel: { flex: 1, backgroundColor: colors.surface },
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
  cardBody: { padding: 10, gap: 6 },
  cardName: { fontSize: 13, fontWeight: "600", color: colors.onSurface, lineHeight: 17 },
  cardSku: { fontSize: 11, color: colors.onSurfaceMuted, fontVariant: ["tabular-nums"] },
  priceRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  price: { fontSize: 14, fontWeight: "700", color: "#DC2626", fontVariant: ["tabular-nums"] },
  mrp: { fontSize: 10, color: colors.onSurfaceMuted, textDecorationLine: "line-through", fontVariant: ["tabular-nums"] },
  addBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.sm, backgroundColor: colors.brand,
  },
  addLabel: { fontSize: 11, fontWeight: "700", color: colors.onBrand, letterSpacing: 0.2 },
});
