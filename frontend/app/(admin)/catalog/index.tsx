import { Feather } from "@expo/vector-icons";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { FlatList, Pressable, ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Chip, EmptyState, Skeleton } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type Brand = { id: string; name: string };
type Category = { id: string; name: string };
type Product = {
  id: string; name: string; sku: string; brand_id: string; category_id: string;
  price: number; mrp: number; finish?: string | null; images: string[]; stock: number;
};

export default function Catalog() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;
  const cols = isTablet ? 4 : 2;
  const gap = 12;

  const [brands, setBrands] = useState<Brand[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState<string | null>(null);
  const [brandId, setBrandId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setProducts(null);
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (cat) params.set("category_id", cat);
    if (brandId) params.set("brand_id", brandId);
    params.set("limit", "60");
    const res = await api.get<{ total: number; items: Product[] }>(`/products?${params}`);
    setProducts(res.items);
  }, [q, cat, brandId]);

  useEffect(() => {
    (async () => {
      const [bs, cs] = await Promise.all([
        api.get<Brand[]>("/brands"),
        api.get<Category[]>("/categories"),
      ]);
      setBrands(bs); setCategories(cs);
    })();
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const cardWidth = useMemo(() => {
    return `${(100 - (cols - 1) * 2) / cols}%`;
  }, [cols]);

  const brandById: Record<string, string> = Object.fromEntries(brands.map((b) => [b.id, b.name]));

  return (
    <AdminPage
      title="Catalog"
      subtitle={`${products?.length ?? "—"} products · Kohler, Grohe, Duravit, Jaquar & more`}
    >
      {/* Search + filters */}
      <View style={{ gap: spacing.md }}>
        <View style={styles.searchWrap}>
          <Feather name="search" size={16} color={colors.onSurfaceMuted} />
          <TextInput
            testID="catalog-search"
            value={q}
            onChangeText={setQ}
            placeholder="Search name, SKU, tag…"
            placeholderTextColor={colors.onSurfaceMuted}
            style={styles.searchInput}
          />
          {q ? (
            <Pressable onPress={() => setQ("")} hitSlop={8}>
              <Feather name="x" size={16} color={colors.onSurfaceMuted} />
            </Pressable>
          ) : null}
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingHorizontal: 2 }}>
          <Chip label="All categories" active={!cat} onPress={() => setCat(null)} testID="cat-all" />
          {categories.map((c) => (
            <Chip key={c.id} label={c.name} active={cat === c.id} onPress={() => setCat(cat === c.id ? null : c.id)} testID={`cat-${c.id}`} />
          ))}
        </ScrollView>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingHorizontal: 2 }}>
          <Chip label="All brands" active={!brandId} onPress={() => setBrandId(null)} testID="brand-all" />
          {brands.map((b) => (
            <Chip key={b.id} label={b.name} active={brandId === b.id} onPress={() => setBrandId(brandId === b.id ? null : b.id)} testID={`brand-${b.id}`} />
          ))}
        </ScrollView>
      </View>

      {/* Grid */}
      {!products ? (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap }}>
          {Array.from({ length: 8 }).map((_, i) => (
            <View key={i} style={[styles.card, { width: cardWidth as any }]}>
              <Skeleton w="100%" h={140} />
              <View style={{ padding: 12, gap: 6 }}>
                <Skeleton w="70%" />
                <Skeleton w="40%" />
              </View>
            </View>
          ))}
        </View>
      ) : products.length === 0 ? (
        <EmptyState icon="package" title="No products match" subtitle="Try clearing filters or adjusting your search." />
      ) : (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap }}>
          {products.map((p) => (
            <Pressable
              key={p.id}
              testID={`product-${p.id}`}
              onPress={() => router.push(`/(admin)/catalog/${p.id}` as any)}
              style={({ pressed }) => [styles.card, { width: cardWidth as any, opacity: pressed ? 0.85 : 1 }]}
            >
              <View style={styles.imageWrap}>
                {p.images?.[0] ? (
                  <Image source={{ uri: p.images[0] }} style={StyleSheet.absoluteFill} contentFit="cover" transition={200} />
                ) : null}
                <View style={styles.brandBadge}>
                  <Text style={styles.brandBadgeText}>{brandById[p.brand_id] || "—"}</Text>
                </View>
                {p.mrp > p.price ? (
                  <View style={styles.saleBadge}>
                    <Text style={styles.saleBadgeText}>−{Math.round((1 - p.price / p.mrp) * 100)}%</Text>
                  </View>
                ) : null}
              </View>
              <View style={{ padding: 12, gap: 4 }}>
                <Text numberOfLines={2} style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface, minHeight: 36 }}>{p.name}</Text>
                <Text style={type.caption}>{p.sku}{p.finish ? ` · ${p.finish}` : ""}</Text>
                <View style={{ flexDirection: "row", alignItems: "baseline", gap: 8, marginTop: 4 }}>
                  <Text style={[type.mono, { fontSize: 15, fontWeight: "700" }]}>{money(p.price)}</Text>
                  {p.mrp > p.price ? (
                    <Text style={{ fontSize: 11, color: colors.onSurfaceMuted, textDecorationLine: "line-through" }}>{money(p.mrp)}</Text>
                  ) : null}
                </View>
              </View>
            </Pressable>
          ))}
        </View>
      )}
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: 10,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
    paddingHorizontal: 14, borderRadius: radius.md,
  },
  searchInput: { flex: 1, fontSize: 14, paddingVertical: 12, color: colors.onSurface },
  card: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, overflow: "hidden",
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  imageWrap: { width: "100%", height: 160, backgroundColor: colors.surfaceTertiary, position: "relative" },
  brandBadge: { position: "absolute", top: 8, left: 8, backgroundColor: "rgba(255,255,255,0.9)", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  brandBadgeText: { fontSize: 10, fontWeight: "700", color: colors.onSurface, letterSpacing: 0.4 },
  saleBadge: { position: "absolute", top: 8, right: 8, backgroundColor: colors.brand, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  saleBadgeText: { fontSize: 10, fontWeight: "700", color: colors.onBrand },
});
