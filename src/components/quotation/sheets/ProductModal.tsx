// ProductModal — the premium floating product modal in V4.
// Opens when a product card is tapped/quick-previewed. Shows gallery, color
// swatches, finish selector, dimensions, description, warranty, editable
// price, quantity, Add / Add & Continue / Favourite. Also surfaces
// Alternatives (via /alternates) and Complete-the-set (via /complete-the-set)
// so the salesperson can extend the quotation without leaving the modal.
// -----------------------------------------------------------------------------
import { Feather } from "@expo/vector-icons";
import { useEffect, useMemo, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { api } from "@/src/api/client";
import { ProductImage } from "@/src/components/ProductImage";
import { colors, money, radius, shadow, spacing, type } from "@/src/theme/tokens";
import { useBuilder } from "../context/BuilderContext";
import type { Product, ProductVariant } from "../helpers/types";

export function ProductModal() {
  const b = useBuilder();
  const open = !!b.productModal;
  const product = b.productModal;

  const [selectedVariant, setSelectedVariant] = useState<ProductVariant | null>(null);
  const [qty, setQty] = useState(1);
  const [priceOverride, setPriceOverride] = useState<string>("");
  const [notes, setNotes] = useState<string>("");
  const [alternates, setAlternates] = useState<Product[]>([]);
  const [completeSet, setCompleteSet] = useState<Product[]>([]);
  const [loadingRel, setLoadingRel] = useState(false);

  // Reset when product changes.
  useEffect(() => {
    if (!product) return;
    setSelectedVariant(null);
    setQty(1);
    setPriceOverride("");
    setNotes("");
    setAlternates([]);
    setCompleteSet([]);
    setLoadingRel(true);
    (async () => {
      try {
        const [alt, set] = await Promise.all([
          api.get<{ items: Product[] }>(`/products/${product.id}/alternates?limit=8`),
          api.get<{ items: Product[] }>(`/products/${product.id}/complete-the-set?limit=6`),
        ]);
        setAlternates(alt.items || []);
        setCompleteSet(set.items || []);
      } catch {}
      finally { setLoadingRel(false); }
    })();
  }, [product]);

  const currentPrice = useMemo(() => {
    if (priceOverride) {
      const n = Number(priceOverride);
      return isNaN(n) ? (selectedVariant?.price ?? product?.price ?? 0) : n;
    }
    return selectedVariant?.price ?? product?.price ?? 0;
  }, [priceOverride, selectedVariant, product]);

  if (!product) return null;

  const heroImages = product.images && product.images.length ? product.images : [];

  const commit = (closeAfter: boolean) => {
    const v: ProductVariant | undefined = selectedVariant ?? undefined;
    // Custom price / quantity override via a synthetic variant — keeps
    // the existing addFromProduct path a single source of truth.
    const custom: ProductVariant = v
      ? { ...v, price: currentPrice }
      : { sku: product.sku, price: currentPrice, mrp: product.mrp, finish: product.finish ?? null };
    for (let i = 0; i < Math.max(1, Math.floor(qty)); i++) b.addFromProduct(product, custom);
    if (notes.trim() && b.s.lines.length) {
      // Attach notes to the just-added line (the last one).
      const last = b.s.lines[b.s.lines.length - 1];
      if (last) b.updateLine(last.id, { notes: notes.trim() });
    }
    if (closeAfter) b.closeProductModal();
  };

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={b.closeProductModal}>
      <Pressable style={styles.backdrop} onPress={b.closeProductModal}>
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
          {/* Header */}
          <View style={styles.header}>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={styles.crumb}>{product.brand_name || "Product"}{product.collection ? ` · ${product.collection}` : ""}</Text>
              <Text style={styles.title} numberOfLines={2}>{product.name}</Text>
              <Text style={styles.sku}>{product.sku}</Text>
            </View>
            <Pressable onPress={b.closeProductModal} style={styles.close} hitSlop={6}>
              <Feather name="x" size={18} color={colors.onSurface} />
            </Pressable>
          </View>

          <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingBottom: 16 }}>
            <View style={styles.body}>
              {/* Left: gallery + price */}
              <View style={styles.left}>
                <ProductImage source={heroImages} style={styles.hero} fallbackLabel={product.sku} />
                {heroImages.length > 1 ? (
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, marginTop: 8 }}>
                    {heroImages.slice(0, 6).map((url, i) => (
                      <View key={`${url}-${i}`} style={styles.thumb}>
                        <ProductImage source={[url]} style={{ width: "100%", height: "100%" }} fallbackLabel={product.sku} />
                      </View>
                    ))}
                  </ScrollView>
                ) : null}

                <View style={styles.priceCard}>
                  <View style={{ flexDirection: "row", alignItems: "baseline", gap: 8 }}>
                    <Text style={styles.priceBig}>{money(currentPrice)}</Text>
                    {product.mrp && product.mrp > currentPrice ? (
                      <Text style={styles.mrpBig}>{money(product.mrp)}</Text>
                    ) : null}
                  </View>
                  <Text style={styles.priceHint}>Editable selling price · MRP shown for reference</Text>
                  <TextInput
                    placeholder={String(product.price)}
                    placeholderTextColor={colors.onSurfaceMuted}
                    keyboardType="numeric"
                    value={priceOverride}
                    onChangeText={setPriceOverride}
                    style={styles.priceInput}
                    testID="pm-price-input"
                  />
                </View>
              </View>

              {/* Right: details */}
              <View style={styles.right}>
                {/* Variants / finishes */}
                {product.variants && product.variants.length ? (
                  <View style={{ gap: 6 }}>
                    <Text style={styles.sectionLabel}>Available finishes</Text>
                    <View style={styles.variantRow}>
                      {product.variants.map((v) => {
                        const on = selectedVariant?.sku === v.sku;
                        return (
                          <Pressable
                            key={v.sku}
                            onPress={() => setSelectedVariant(on ? null : v)}
                            style={[styles.variantChip, on && styles.variantChipActive]}
                            testID={`pm-variant-${v.sku}`}
                          >
                            <View style={[styles.swatch, { backgroundColor: colourHex(v.color || v.finish) }]} />
                            <Text style={[styles.variantLabel, on && { color: colors.onBrand }]}>{v.finish || v.color || v.size || v.sku}</Text>
                            {v.price !== product.price ? (
                              <Text style={[styles.variantDelta, on && { color: colors.onBrand }]}>
                                {v.price > product.price ? "+" : ""}{money(v.price - product.price)}
                              </Text>
                            ) : null}
                          </Pressable>
                        );
                      })}
                    </View>
                  </View>
                ) : null}

                <View style={styles.specGrid}>
                  {[
                    ["Category", (product as any).category_name || "—"],
                    ["Collection", product.collection || product.series || "—"],
                    ["Finish", product.finish || "—"],
                    ["Dimensions", (product as any).dimensions || "—"],
                    ["Warranty", (product as any).warranty || "—"],
                    ["Stock", (product.stock ?? "—") + ""],
                  ].map(([label, val]) => (
                    <View key={label} style={styles.specCell}>
                      <Text style={styles.specLabel}>{label}</Text>
                      <Text style={styles.specVal} numberOfLines={2}>{val}</Text>
                    </View>
                  ))}
                </View>

                {product.description ? (
                  <View style={{ gap: 4 }}>
                    <Text style={styles.sectionLabel}>Description</Text>
                    <Text style={styles.desc}>{product.description}</Text>
                  </View>
                ) : null}

                {/* Quantity + notes */}
                <View style={styles.qtyRow}>
                  <Text style={styles.sectionLabel}>Quantity</Text>
                  <View style={styles.qtyStepper}>
                    <Pressable onPress={() => setQty((n) => Math.max(1, n - 1))} style={styles.qtyBtn} testID="pm-qty-minus">
                      <Feather name="minus" size={14} color={colors.onSurface} />
                    </Pressable>
                    <TextInput
                      value={String(qty)}
                      onChangeText={(v) => setQty(Math.max(1, Math.floor(Number(v.replace(/[^0-9]/g, "")) || 1)))}
                      style={styles.qtyInput}
                      keyboardType="number-pad"
                    />
                    <Pressable onPress={() => setQty((n) => n + 1)} style={styles.qtyBtn} testID="pm-qty-plus">
                      <Feather name="plus" size={14} color={colors.onSurface} />
                    </Pressable>
                  </View>
                </View>

                <TextInput
                  value={notes}
                  onChangeText={setNotes}
                  placeholder="Notes (optional)"
                  placeholderTextColor={colors.onSurfaceMuted}
                  style={styles.notesInput}
                  multiline
                />
              </View>
            </View>

            {/* Alternatives */}
            {alternates.length ? (
              <View style={styles.relSection}>
                <View style={styles.relHead}>
                  <Text style={styles.relTitle}>Alternatives</Text>
                  <Text style={styles.relHint}>Same category — tap to swap into this modal</Text>
                </View>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10, paddingHorizontal: 20, paddingBottom: 6 }}>
                  {alternates.map((alt) => (
                    <Pressable
                      key={alt.id}
                      onPress={() => b.openProductModal(alt)}
                      style={styles.relCard}
                    >
                      <ProductImage source={alt.images} style={styles.relThumb} fallbackLabel={alt.sku} />
                      <Text style={styles.relName} numberOfLines={2}>{alt.name}</Text>
                      <Text style={styles.relPrice}>{money(alt.price)}</Text>
                    </Pressable>
                  ))}
                </ScrollView>
              </View>
            ) : null}

            {completeSet.length ? (
              <View style={styles.relSection}>
                <View style={styles.relHead}>
                  <Text style={styles.relTitle}>Complete the set</Text>
                  <Text style={styles.relHint}>From the same collection — tap to add to quotation</Text>
                </View>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10, paddingHorizontal: 20, paddingBottom: 6 }}>
                  {completeSet.map((s) => (
                    <Pressable
                      key={s.id}
                      onPress={() => b.addFromProduct(s)}
                      style={styles.relCard}
                    >
                      <ProductImage source={s.images} style={styles.relThumb} fallbackLabel={s.sku} />
                      <Text style={styles.relName} numberOfLines={2}>{s.name}</Text>
                      <Text style={styles.relPrice}>{money(s.price)}</Text>
                    </Pressable>
                  ))}
                </ScrollView>
              </View>
            ) : null}
          </ScrollView>

          {/* Footer actions */}
          <View style={styles.footer}>
            <Pressable
              onPress={() => b.toggleFavourite(product.id)}
              style={styles.footerGhost}
              testID="pm-favourite"
            >
              <Feather name="heart" size={14} color={b.favouriteIds.includes(product.id) ? "#E11D48" : colors.onSurface} />
              <Text style={styles.footerGhostLabel}>{b.favouriteIds.includes(product.id) ? "Favourited" : "Favourite"}</Text>
            </Pressable>
            <View style={{ flex: 1 }} />
            <Pressable onPress={() => commit(false)} style={styles.footerSecondary} testID="pm-add-more">
              <Text style={styles.footerSecondaryLabel}>Add another</Text>
            </Pressable>
            <Pressable onPress={() => commit(true)} style={styles.footerPrimary} testID="pm-add-close">
              <Feather name="plus" size={14} color={colors.onBrand} />
              <Text style={styles.footerPrimaryLabel}>Add to quotation</Text>
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

// -----------------------------------------------------------------------------
// Tiny colour helper — maps finish/color labels to swatch hex.
// -----------------------------------------------------------------------------
function colourHex(v?: string | null): string {
  if (!v) return colors.borderStrong;
  const s = v.toLowerCase();
  if (s.includes("matt black") || s.includes("black")) return "#111";
  if (s.includes("chrome")) return "#D4D4D8";
  if (s.includes("gold")) return "#D4AF37";
  if (s.includes("brass") || s.includes("bronze")) return "#A97142";
  if (s.includes("white")) return "#F4F4F5";
  if (s.includes("copper")) return "#B87333";
  if (s.includes("nickel")) return "#B0B7C1";
  if (s.includes("stainless")) return "#8E9099";
  if (s.includes("beige") || s.includes("cream")) return "#EDE6D3";
  return "#B0B7C1";
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1, backgroundColor: "rgba(9,9,11,0.55)",
    alignItems: "center", justifyContent: "center", padding: 24,
  },
  sheet: {
    width: "100%", maxWidth: 960, maxHeight: "92%",
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg,
    overflow: "hidden",
    ...shadow.strong,
  },

  header: {
    flexDirection: "row", padding: spacing.lg, alignItems: "flex-start", gap: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  crumb: { fontSize: 11, fontWeight: "700", color: colors.onSurfaceMuted, letterSpacing: 1.2, textTransform: "uppercase" },
  title: { fontSize: 20, fontWeight: "700", color: colors.onSurface, marginTop: 4, letterSpacing: -0.3 },
  sku: { fontSize: 12, color: colors.onSurfaceMuted, marginTop: 4, fontVariant: ["tabular-nums"] },
  close: {
    width: 32, height: 32, borderRadius: radius.md, alignItems: "center", justifyContent: "center",
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.surface,
  },

  body: { flexDirection: "row", padding: spacing.lg, gap: spacing.lg, flexWrap: "wrap" },
  left: { width: 300, gap: 12 },
  right: { flex: 1, minWidth: 260, gap: 14 },

  hero: { width: "100%", aspectRatio: 1, borderRadius: radius.md, backgroundColor: colors.surfaceTertiary },
  thumb: { width: 52, height: 52, borderRadius: 8, backgroundColor: colors.surfaceTertiary, overflow: "hidden" },

  priceCard: {
    padding: 12, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, gap: 6,
  },
  priceBig: { fontSize: 22, fontWeight: "800", color: "#DC2626", fontVariant: ["tabular-nums"] },
  mrpBig: { fontSize: 12, color: colors.onSurfaceMuted, textDecorationLine: "line-through", fontVariant: ["tabular-nums"] },
  priceHint: { fontSize: 10, color: colors.onSurfaceMuted },
  priceInput: {
    marginTop: 4, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    borderRadius: radius.sm, paddingHorizontal: 10, paddingVertical: 8, fontSize: 13, color: colors.onSurface,
  },

  sectionLabel: { fontSize: 11, fontWeight: "700", color: colors.onSurfaceMuted, letterSpacing: 1.1, textTransform: "uppercase" },

  variantRow: { flexDirection: "row", gap: 6, flexWrap: "wrap" },
  variantChip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  variantChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  swatch: { width: 12, height: 12, borderRadius: 999, borderWidth: 1, borderColor: colors.border },
  variantLabel: { fontSize: 11, fontWeight: "600", color: colors.onSurfaceSecondary },
  variantDelta: { fontSize: 10, fontWeight: "700", color: colors.onSurfaceMuted, fontVariant: ["tabular-nums"] },

  specGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  specCell: {
    width: "48%", padding: 8, borderRadius: radius.sm,
    backgroundColor: colors.surfaceTertiary,
  },
  specLabel: { fontSize: 10, fontWeight: "700", color: colors.onSurfaceMuted, letterSpacing: 1, textTransform: "uppercase", marginBottom: 2 },
  specVal: { fontSize: 12, fontWeight: "600", color: colors.onSurface },

  desc: { fontSize: 12, lineHeight: 18, color: colors.onSurfaceSecondary },

  qtyRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  qtyStepper: {
    flexDirection: "row", alignItems: "center", borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.surface,
  },
  qtyBtn: { paddingHorizontal: 10, paddingVertical: 8 },
  qtyInput: { width: 44, textAlign: "center", fontSize: 13, fontWeight: "700", color: colors.onSurface },

  notesInput: {
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, borderRadius: radius.md,
    minHeight: 48, padding: 10, fontSize: 12, color: colors.onSurface, backgroundColor: colors.surface,
  },

  relSection: { borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border, paddingTop: 12, marginTop: 4 },
  relHead: { paddingHorizontal: 20, paddingBottom: 8 },
  relTitle: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  relHint: { fontSize: 11, color: colors.onSurfaceMuted, marginTop: 1 },
  relCard: { width: 130, gap: 4 },
  relThumb: { width: "100%", aspectRatio: 1, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  relName: { fontSize: 11, fontWeight: "600", color: colors.onSurface, marginTop: 4 },
  relPrice: { fontSize: 11, fontWeight: "700", color: "#DC2626", fontVariant: ["tabular-nums"] },

  footer: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: spacing.lg, paddingVertical: 12,
    borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  footerGhost: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 10, paddingVertical: 8, borderRadius: radius.md,
  },
  footerGhostLabel: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  footerSecondary: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  footerSecondaryLabel: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  footerPrimary: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 16, paddingVertical: 10, borderRadius: radius.md, backgroundColor: colors.brand,
  },
  footerPrimaryLabel: { fontSize: 12, fontWeight: "700", color: colors.onBrand, letterSpacing: 0.2 },
});
