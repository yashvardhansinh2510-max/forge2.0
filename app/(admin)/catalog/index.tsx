import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { ProductImage } from "@/src/components/ProductImage";
import { Chip, EmptyState, Skeleton } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type Brand = { id: string; name: string };
type Category = { id: string; name: string };
type Product = {
  id: string; name: string; sku: string; brand_id: string; category_id: string;
  subcategory?: string | null; series?: string | null; family_key?: string | null;
  family_name?: string | null; variant_label?: string | null; colour?: string | null;
  price: number; mrp: number; finish?: string | null; images: string[]; stock: number;
  image_quality?: string | null;
  hero_image_url?: string | null;
  gallery?: { url: string; role?: string; source_type?: string; quality?: string }[];
  media_summary?: { supplier: number; manufacturer: number; internal: number; best_quality: string; total: number };
};
type Family = {
  family_key: string; family_name: string; brand_id: string; category_id: string;
  subcategory?: string | null; series?: string | null;
  min_price: number; max_price: number; product_count: number;
  sample_image?: string | null; sample_image_quality?: string | null;
  variants: {
    id: string; sku: string; variant_label?: string | null; colour?: string | null;
    finish?: string | null; finish_code?: string | null; price: number; mrp: number;
    image?: string | null; image_quality?: string | null;
  }[];
};

type ViewMode = "families" | "products";

const QUALITY_STYLES: Record<string, { bg: string; fg: string; label: string }> = {
  excellent:  { bg: "#DCFCE7", fg: "#166534", label: "Excellent" },
  good:       { bg: "#DBEAFE", fg: "#1E3A8A", label: "Good"      },
  acceptable: { bg: "#FEF3C7", fg: "#92400E", label: "OK"        },
  poor:       { bg: "#FEE2E2", fg: "#991B1B", label: "Thumb"     },
  missing:    { bg: "#F3F4F6", fg: "#6B7280", label: "No image"  },
};

function QualityBadge({ quality }: { quality?: string | null }) {
  if (!quality) return null;
  const s = QUALITY_STYLES[quality] || QUALITY_STYLES.missing;
  return (
    <View style={{ backgroundColor: s.bg, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
      <Text style={{ fontSize: 9, fontWeight: "700", color: s.fg, letterSpacing: 0.4 }}>{s.label.toUpperCase()}</Text>
    </View>
  );
}

export default function Catalog() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;
  const cols = isTablet ? 4 : 2;
  const gap = 12;

  const [brands, setBrands] = useState<Brand[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [subcategories, setSubcategories] = useState<string[]>([]);
  const [seriesList, setSeriesList] = useState<string[]>([]);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [families, setFamilies] = useState<Family[] | null>(null);

  const [q, setQ] = useState("");
  const [cat, setCat] = useState<string | null>(null);
  const [brandId, setBrandId] = useState<string | null>(null);
  const [subcat, setSubcat] = useState<string | null>(null);
  const [series, setSeries] = useState<string | null>(null);
  const [mode, setMode] = useState<ViewMode>("families");

  // Load brands + categories once
  useEffect(() => {
    (async () => {
      const [bs, cs] = await Promise.all([
        api.get<Brand[]>("/brands"),
        api.get<Category[]>("/categories"),
      ]);
      setBrands(bs); setCategories(cs);
    })();
  }, []);

  // Whenever category changes, refresh the subcategory + series chip strips
  // by walking the hierarchy tree.
  useEffect(() => {
    (async () => {
      try {
        const res = await api.get<{ tree: any[] }>(`/catalog/hierarchy`);
        const subs = new Set<string>();
        const ser = new Set<string>();
        for (const b of res.tree) {
          if (brandId && b.brand.id !== brandId) continue;
          for (const c of b.categories) {
            if (cat && c.category.id !== cat) continue;
            for (const s of c.subcategories) {
              subs.add(s.name);
              for (const se of s.series) {
                if (!subcat || subcat === s.name) ser.add(se.name);
              }
            }
          }
        }
        setSubcategories(Array.from(subs).sort());
        setSeriesList(Array.from(ser).sort());
      } catch {
        setSubcategories([]); setSeriesList([]);
      }
    })();
  }, [cat, brandId, subcat]);

  const load = useCallback(async () => {
    setProducts(null); setFamilies(null);
    const params = new URLSearchParams();
    if (q)         params.set("q", q);
    if (cat)       params.set("category_id", cat);
    if (brandId)   params.set("brand_id", brandId);
    if (subcat)    params.set("subcategory", subcat);
    if (series)    params.set("series", series);
    params.set("limit", "60");
    try {
      if (mode === "families") {
        const res = await api.get<{ total: number; items: Family[] }>(`/products/families?${params}`);
        setFamilies(res.items);
      } else {
        const res = await api.get<{ total: number; items: Product[] }>(`/products?${params}`);
        setProducts(res.items);
      }
    } catch {
      if (mode === "families") setFamilies([]); else setProducts([]);
    }
  }, [q, cat, brandId, subcat, series, mode]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const cardWidth = useMemo(() => `${(100 - (cols - 1) * 2) / cols}%`, [cols]);
  const brandById: Record<string, string> = Object.fromEntries(brands.map((b) => [b.id, b.name]));
  const count = mode === "families" ? families?.length : products?.length;

  return (
    <AdminPage
      title="Catalog"
      subtitle={`${count ?? "—"} ${mode === "families" ? "families" : "products"} · Vitra, Grohe, Geberit, Hansgrohe & Axor`}
      right={
        <View style={{ flexDirection: "row", gap: 8 }}>
          <ModeToggle mode={mode} onChange={setMode} />
          <Pressable
            testID="import-catalog-btn"
            onPress={() => router.push("/(admin)/catalog/import" as any)}
            style={{ flexDirection: "row", gap: 6, alignItems: "center", backgroundColor: colors.brand, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 }}
          >
            <Feather name="upload-cloud" size={14} color={colors.onBrand} />
            <Text style={{ color: colors.onBrand, fontSize: 13, fontWeight: "600" }}>AI Import</Text>
          </Pressable>
        </View>
      }
    >
      {/* Search */}
      <View style={{ gap: spacing.md }}>
        <View style={styles.searchWrap}>
          <Feather name="search" size={16} color={colors.onSurfaceMuted} />
          <TextInput
            testID="catalog-search"
            value={q}
            onChangeText={setQ}
            placeholder="Search SKU, name, series, family, finish…"
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
          <Chip label="All categories" active={!cat} onPress={() => { setCat(null); setSubcat(null); setSeries(null); }} testID="cat-all" />
          {categories.map((c) => (
            <Chip key={c.id} label={c.name} active={cat === c.id} onPress={() => { setCat(cat === c.id ? null : c.id); setSubcat(null); setSeries(null); }} testID={`cat-${c.id}`} />
          ))}
        </ScrollView>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingHorizontal: 2 }}>
          <Chip label="All brands" active={!brandId} onPress={() => setBrandId(null)} testID="brand-all" />
          {brands.map((b) => (
            <Chip key={b.id} label={b.name} active={brandId === b.id} onPress={() => setBrandId(brandId === b.id ? null : b.id)} testID={`brand-${b.id}`} />
          ))}
        </ScrollView>

        {subcategories.length > 0 ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingHorizontal: 2 }}>
            <Text style={[type.caption, { alignSelf: "center", marginRight: 6 }]}>Subcategory</Text>
            <Chip label="Any" active={!subcat} onPress={() => { setSubcat(null); setSeries(null); }} testID="subcat-all" />
            {subcategories.map((s) => (
              <Chip key={s} label={s} active={subcat === s} onPress={() => { setSubcat(subcat === s ? null : s); setSeries(null); }} />
            ))}
          </ScrollView>
        ) : null}

        {seriesList.length > 0 ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingHorizontal: 2 }}>
            <Text style={[type.caption, { alignSelf: "center", marginRight: 6 }]}>Series</Text>
            <Chip label="Any" active={!series} onPress={() => setSeries(null)} testID="series-all" />
            {seriesList.map((s) => (
              <Chip key={s} label={s} active={series === s} onPress={() => setSeries(series === s ? null : s)} />
            ))}
          </ScrollView>
        ) : null}
      </View>

      {/* Grid */}
      {mode === "families" ? (
        <FamilyGrid
          families={families}
          brandById={brandById}
          cardWidth={cardWidth as any}
          gap={gap}
          onOpen={(fam) => router.push(`/(admin)/catalog/${fam.variants[0]?.id}` as any)}
        />
      ) : (
        <ProductGrid
          products={products}
          brandById={brandById}
          cardWidth={cardWidth as any}
          gap={gap}
          onOpen={(p) => router.push(`/(admin)/catalog/${p.id}` as any)}
        />
      )}
    </AdminPage>
  );
}

function ModeToggle({ mode, onChange }: { mode: ViewMode; onChange: (m: ViewMode) => void }) {
  return (
    <View style={{ flexDirection: "row", borderWidth: 1, borderColor: colors.border, borderRadius: 8, overflow: "hidden" }}>
      {(["families", "products"] as ViewMode[]).map((m) => (
        <Pressable
          key={m}
          testID={`mode-${m}`}
          onPress={() => onChange(m)}
          style={{ paddingHorizontal: 12, paddingVertical: 8, backgroundColor: mode === m ? colors.brand : "transparent" }}
        >
          <Text style={{ fontSize: 12, fontWeight: "600", color: mode === m ? colors.onBrand : colors.onSurfaceSecondary }}>
            {m === "families" ? "Families" : "All variants"}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

function ProductGrid({
  products, brandById, cardWidth, gap, onOpen,
}: {
  products: Product[] | null;
  brandById: Record<string, string>;
  cardWidth: any; gap: number;
  onOpen: (p: Product) => void;
}) {
  if (!products) {
    return (
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap }}>
        {Array.from({ length: 8 }).map((_, i) => (
          <View key={i} style={[styles.card, { width: cardWidth }]}>
            <Skeleton w="100%" h={140} />
            <View style={{ padding: 12, gap: 6 }}>
              <Skeleton w="70%" />
              <Skeleton w="40%" />
            </View>
          </View>
        ))}
      </View>
    );
  }
  if (products.length === 0) {
    return <EmptyState icon="package" title="No products match" subtitle="Try clearing filters or adjusting your search." />;
  }
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap }}>
      {products.map((p) => (
        <Pressable
          key={p.id}
          testID={`product-${p.id}`}
          onPress={() => onOpen(p)}
          style={({ pressed }) => [styles.card, { width: cardWidth, opacity: pressed ? 0.85 : 1 }]}
        >
          <View style={styles.imageWrap}>
            <ProductImage source={p.hero_image_url ? [p.hero_image_url, ...(p.images || [])] : p.images} style={StyleSheet.absoluteFill as any} contentFit="cover" fallbackLabel={p.sku} borderRadius={0} />
            <View style={styles.brandBadge}><Text style={styles.brandBadgeText}>{brandById[p.brand_id] || "—"}</Text></View>
            <View style={styles.qualityBadgeWrap}><QualityBadge quality={p.image_quality} /></View>
            {p.mrp > p.price ? (
              <View style={styles.saleBadge}>
                <Text style={styles.saleBadgeText}>−{Math.round((1 - p.price / p.mrp) * 100)}%</Text>
              </View>
            ) : null}
          </View>
          <View style={{ padding: 12, gap: 4 }}>
            <Text numberOfLines={2} style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface, minHeight: 36 }}>{p.name}</Text>
            <Text style={type.caption} numberOfLines={1}>{p.sku}{p.finish ? ` · ${p.finish}` : ""}</Text>
            <View style={{ flexDirection: "row", alignItems: "baseline", gap: 8, marginTop: 4 }}>
              <Text style={[type.mono, { fontSize: 15, fontWeight: "700" }]}>{money(p.price)}</Text>
              {p.mrp > p.price ? <Text style={{ fontSize: 11, color: colors.onSurfaceMuted, textDecorationLine: "line-through" }}>{money(p.mrp)}</Text> : null}
            </View>
          </View>
        </Pressable>
      ))}
    </View>
  );
}

function FamilyGrid({
  families, brandById, cardWidth, gap, onOpen,
}: {
  families: Family[] | null;
  brandById: Record<string, string>;
  cardWidth: any; gap: number;
  onOpen: (f: Family) => void;
}) {
  if (!families) {
    return (
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap }}>
        {Array.from({ length: 8 }).map((_, i) => (
          <View key={i} style={[styles.card, { width: cardWidth }]}>
            <Skeleton w="100%" h={180} />
            <View style={{ padding: 12, gap: 6 }}>
              <Skeleton w="70%" />
              <Skeleton w="40%" />
            </View>
          </View>
        ))}
      </View>
    );
  }
  if (families.length === 0) {
    return <EmptyState icon="package" title="No families match" subtitle="Try clearing filters or switch to All variants view." />;
  }
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap }}>
      {families.map((f) => (
        <Pressable
          key={f.family_key}
          testID={`family-${f.family_key}`}
          onPress={() => onOpen(f)}
          style={({ pressed }) => [styles.card, { width: cardWidth, opacity: pressed ? 0.85 : 1 }]}
        >
          <View style={[styles.imageWrap, { height: 180 }]}>
            <ProductImage
              source={f.sample_image ? [f.sample_image] : []}
              style={StyleSheet.absoluteFill as any}
              contentFit="cover" fallbackLabel={f.variants[0]?.sku || ""}
              borderRadius={0}
            />
            <View style={styles.brandBadge}><Text style={styles.brandBadgeText}>{brandById[f.brand_id] || "—"}</Text></View>
            <View style={styles.qualityBadgeWrap}><QualityBadge quality={f.sample_image_quality} /></View>
            <View style={styles.variantCountBadge}>
              <Text style={styles.variantCountText}>{f.product_count} {f.product_count === 1 ? "variant" : "variants"}</Text>
            </View>
          </View>
          <View style={{ padding: 12, gap: 6 }}>
            {f.series ? <Text style={type.overline} numberOfLines={1}>{f.series}</Text> : null}
            <Text numberOfLines={2} style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface, minHeight: 36 }}>{f.family_name}</Text>
            {f.subcategory ? <Text style={type.caption}>{f.subcategory}</Text> : null}
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
              {f.variants.slice(0, 5).map((v) => (
                <View key={v.id} style={styles.swatch}>
                  <View style={[styles.swatchDot, { backgroundColor: swatchColor(v.colour, v.finish) }]} />
                </View>
              ))}
              {f.variants.length > 5 ? (
                <View style={styles.swatch}><Text style={{ fontSize: 9, fontWeight: "700", color: colors.onSurfaceMuted }}>+{f.variants.length - 5}</Text></View>
              ) : null}
            </View>
            <View style={{ flexDirection: "row", alignItems: "baseline", gap: 6, marginTop: 4 }}>
              <Text style={[type.mono, { fontSize: 15, fontWeight: "700" }]}>{money(f.min_price)}</Text>
              {f.max_price > f.min_price ? (
                <Text style={{ fontSize: 12, color: colors.onSurfaceMuted }}>– {money(f.max_price)}</Text>
              ) : null}
            </View>
          </View>
        </Pressable>
      ))}
    </View>
  );
}

// Map a colour/finish label to a swatch background colour
function swatchColor(colour?: string | null, finish?: string | null): string {
  const label = (colour || finish || "").toLowerCase();
  if (!label) return "#D1D5DB";
  if (label.includes("black")) return "#0F172A";
  if (label.includes("matt white")) return "#F8FAFC";
  if (label.includes("white")) return "#FFFFFF";
  if (label.includes("taupe") || label.includes("beige")) return "#B7A08A";
  if (label.includes("stone") || label.includes("grey") || label.includes("gray")) return "#8A8A8E";
  if (label.includes("chrome") || label.includes("steel")) return "#C0C5CB";
  if (label.includes("brass") || label.includes("gold")) return "#C6A664";
  if (label.includes("bronze") || label.includes("copper")) return "#8C5E3C";
  if (label.includes("nickel")) return "#7C8791";
  return "#D1D5DB";
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
  qualityBadgeWrap: { position: "absolute", top: 30, left: 8 },
  variantCountBadge: { position: "absolute", bottom: 8, right: 8, backgroundColor: "rgba(15,23,42,0.85)", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4 },
  variantCountText: { color: "#fff", fontSize: 10, fontWeight: "700", letterSpacing: 0.4 },
  swatch: {
    width: 22, height: 22, borderRadius: 11, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center", overflow: "hidden",
  },
  swatchDot: { width: 20, height: 20, borderRadius: 10 },
});
