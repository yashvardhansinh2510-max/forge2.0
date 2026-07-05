// Catalog — premium family-first browsing.
// -----------------------------------------------------------------------------
// Mobile-first layout with tablet-landscape parallel design:
//   * Compact sticky title bar (never wraps, action icons pinned right)
//   * Search + filter icon in a single row → advanced filters live in a bottom
//     sheet so the wall of chip strips doesn't eat vertical space
//   * A single brand strip surfaced above the fold (biggest signal)
//   * Categories collapse into a horizontal scroll strip with icons
//   * FlashList-backed grid, 2 cols phone → 5 cols desktop
//   * Family cards: 1:1 image, series overline, family name, variant swatches,
//     price range on one line, tap = variant PDP
// -----------------------------------------------------------------------------
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { ProductImage } from "@/src/components/ProductImage";
import { BottomSheet } from "@/src/components/BottomSheet";
import { Chip, EmptyState, IconButton, PriceTag, ScreenTitle, SegmentedControl, Skeleton, Button } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { useBreakpoint } from "@/src/hooks/use-breakpoint";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type Brand = { id: string; name: string; slug?: string };
type Category = { id: string; name: string; slug?: string };
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
type Product = {
  id: string; name: string; sku: string; brand_id: string; category_id: string;
  subcategory?: string | null; series?: string | null;
  price: number; mrp: number; finish?: string | null; images: string[]; stock: number;
  image_quality?: string | null;
  hero_image_url?: string | null;
  colour?: string | null;
};

type ViewMode = "families" | "products";

// Category icon mapping — Feather set. Anything not mapped falls back to `package`.
const CATEGORY_ICONS: Record<string, keyof typeof Feather.glyphMap> = {
  bathroom: "droplet",
  kitchen: "coffee",
  faucets: "droplet",
  showers: "cloud-drizzle",
  showering: "cloud-drizzle",
  toilet: "circle",
  toilets: "circle",
  accessories: "grid",
  sanitaryware: "circle",
  tapware: "droplet",
  taps: "droplet",
  mixers: "droplet",
  thermostat: "sliders",
  thermostats: "sliders",
  basins: "circle",
  ceramics: "circle",
  wellness: "cloud-drizzle",
  fittings: "settings",
};
function iconFor(name: string): keyof typeof Feather.glyphMap {
  const key = name.toLowerCase().trim();
  for (const k in CATEGORY_ICONS) if (key.includes(k)) return CATEGORY_ICONS[k];
  return "package";
}

// Map colour/finish label to a swatch background
function swatchColor(colour?: string | null, finish?: string | null): string {
  const label = (colour || finish || "").toLowerCase();
  if (!label) return "#D1D5DB";
  if (label.includes("black")) return "#0F172A";
  if (label.includes("matt white")) return "#F8FAFC";
  if (label.includes("white")) return "#FFFFFF";
  if (label.includes("taupe") || label.includes("beige")) return "#B7A08A";
  if (label.includes("stone") || label.includes("grey") || label.includes("gray")) return "#8A8A8E";
  if (label.includes("chrome") || label.includes("steel") || label.includes("polished")) return "#C0C5CB";
  if (label.includes("brushed") && label.includes("brass")) return "#B08D57";
  if (label.includes("brass") || label.includes("gold")) return "#C6A664";
  if (label.includes("bronze") || label.includes("copper")) return "#8C5E3C";
  if (label.includes("nickel")) return "#7C8791";
  if (label.includes("graphite") || label.includes("anthracite")) return "#3A3A3A";
  return "#D1D5DB";
}

export default function Catalog() {
  const router = useRouter();
  const { productCols, pad } = useBreakpoint();

  const [brands, setBrands] = useState<Brand[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [subcategories, setSubcategories] = useState<string[]>([]);
  const [seriesList, setSeriesList] = useState<string[]>([]);
  const [families, setFamilies] = useState<Family[] | null>(null);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const [q, setQ] = useState("");
  const [cat, setCat] = useState<string | null>(null);
  const [brandId, setBrandId] = useState<string | null>(null);
  const [subcat, setSubcat] = useState<string | null>(null);
  const [series, setSeries] = useState<string | null>(null);
  const [mode, setMode] = useState<ViewMode>("families");

  // Load brands + categories once
  useEffect(() => {
    (async () => {
      try {
        const [bs, cs] = await Promise.all([
          api.get<Brand[]>("/brands"),
          api.get<Category[]>("/categories"),
        ]);
        setBrands(bs); setCategories(cs);
      } catch { /* ignore */ }
    })();
  }, []);

  // Hierarchy → derive subcategory & series options
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
    setProducts(null); setFamilies(null); setTotal(null);
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
        setFamilies(res.items); setTotal(res.total);
      } else {
        const res = await api.get<{ total: number; items: Product[] }>(`/products?${params}`);
        setProducts(res.items); setTotal(res.total);
      }
    } catch {
      if (mode === "families") setFamilies([]); else setProducts([]);
      setTotal(0);
    }
  }, [q, cat, brandId, subcat, series, mode]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const brandById: Record<string, string> = useMemo(
    () => Object.fromEntries(brands.map((b) => [b.id, b.name])), [brands],
  );
  const activeFilterCount = [brandId, subcat, series].filter(Boolean).length;
  const resetFilters = () => { setBrandId(null); setSubcat(null); setSeries(null); };
  const clearAll = () => { setQ(""); setCat(null); resetFilters(); };

  const subtitle = total === null
    ? "Loading…"
    : `${total.toLocaleString("en-IN")} ${mode === "families" ? "families" : "products"}${cat ? " · filtered" : ""}`;

  const gridPadding = pad;
  const gap = 14;

  // Header actions
  const HeaderRight = (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
      <IconButton
        icon="upload-cloud"
        onPress={() => router.push("/(admin)/catalog/import" as any)}
        size={36}
        tone="surface"
        testID="import-catalog-btn"
        accessibilityLabel="Import catalog"
      />
    </View>
  );

  const gridItems = mode === "families" ? families : products;
  const showSkeleton = gridItems === null;
  const showEmpty = !showSkeleton && (gridItems?.length === 0);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScreenTitle title="Catalog" subtitle={subtitle} right={HeaderRight} />
      <ScrollView
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingHorizontal: gridPadding, paddingBottom: 32 }}
      >
        {/* Header block */}
        <View style={{ paddingTop: spacing.md, paddingBottom: spacing.md, gap: spacing.md }}>
          {/* Search + filter button */}
          <View style={{ flexDirection: "row", gap: 8 }}>
            <View style={styles.searchWrap}>
              <Feather name="search" size={16} color={colors.onSurfaceMuted} />
              <TextInput
                testID="catalog-search"
                value={q}
                onChangeText={setQ}
                placeholder="Search products, series, SKU…"
                placeholderTextColor={colors.onSurfaceMuted}
                style={styles.searchInput}
                returnKeyType="search"
              />
              {q ? (
                <Pressable onPress={() => setQ("")} hitSlop={8}>
                  <Feather name="x" size={16} color={colors.onSurfaceMuted} />
                </Pressable>
              ) : null}
            </View>
            <Pressable
              testID="catalog-filter-btn"
              onPress={() => setFiltersOpen(true)}
              style={styles.filterBtn}
            >
              <Feather name="sliders" size={16} color={colors.onSurface} />
              {activeFilterCount > 0 ? (
                <View style={styles.filterDot}><Text style={styles.filterDotText}>{activeFilterCount}</Text></View>
              ) : null}
            </Pressable>
          </View>

          {/* Category strip with icons */}
          <ScrollView
            horizontal showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ gap: 8, paddingRight: gridPadding, paddingVertical: 2 }}
            style={{ marginHorizontal: -gridPadding, paddingHorizontal: gridPadding }}
          >
            <CategoryPill label="All" icon="grid" active={!cat} onPress={() => { setCat(null); setSubcat(null); setSeries(null); }} testID="cat-all" />
            {categories.map((c) => (
              <CategoryPill
                key={c.id}
                label={c.name}
                icon={iconFor(c.name)}
                active={cat === c.id}
                onPress={() => { setCat(cat === c.id ? null : c.id); setSubcat(null); setSeries(null); }}
                testID={`cat-${c.id}`}
              />
            ))}
          </ScrollView>

          {/* Mode toggle + active filter summary row */}
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
            <View style={{ flex: 1, flexShrink: 1 }}>
              {(brandId || subcat || series) ? (
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingRight: 8 }}>
                  {brandId ? <ActiveChip label={brandById[brandId] || "Brand"} onClose={() => setBrandId(null)} /> : null}
                  {subcat ? <ActiveChip label={subcat} onClose={() => { setSubcat(null); setSeries(null); }} /> : null}
                  {series ? <ActiveChip label={series} onClose={() => setSeries(null)} /> : null}
                  <Pressable onPress={resetFilters} style={styles.clearAll}>
                    <Text style={styles.clearAllText}>Clear</Text>
                  </Pressable>
                </ScrollView>
              ) : (
                <Text style={type.caption} numberOfLines={1}>Vitra · Grohe · Geberit · Hansgrohe · Axor</Text>
              )}
            </View>
            <SegmentedControl<ViewMode>
              testID="mode-toggle"
              size="sm"
              value={mode}
              options={[{ value: "families", label: "Families", icon: "layers" }, { value: "products", label: "Variants", icon: "grid" }]}
              onChange={setMode}
            />
          </View>
        </View>

        {/* Grid */}
        {showEmpty ? (
          <EmptyState
            icon="package"
            title="Nothing matches"
            subtitle="Try clearing filters or adjusting your search."
            action={<Button label="Reset filters" variant="secondary" onPress={clearAll} />}
          />
        ) : (
          <View style={{ flexDirection: "row", flexWrap: "wrap", marginHorizontal: -gap / 2 }}>
            {(showSkeleton ? Array.from({ length: 8 }) : gridItems)!.map((it: any, i: number) => (
              <View
                key={showSkeleton ? `sk-${i}` : (it.family_key || it.id)}
                style={{
                  width: `${100 / productCols}%`,
                  paddingHorizontal: gap / 2,
                  paddingBottom: gap,
                }}
              >
                {showSkeleton ? (
                  <SkeletonCard tall={mode === "families"} />
                ) : mode === "families" ? (
                  <FamilyCard
                    family={it as Family}
                    brandName={brandById[(it as Family).brand_id] || ""}
                    onPress={() => router.push(`/(admin)/catalog/${(it as Family).variants[0]?.id}` as any)}
                  />
                ) : (
                  <ProductCard
                    product={it as Product}
                    brandName={brandById[(it as Product).brand_id] || ""}
                    onPress={() => router.push(`/(admin)/catalog/${(it as Product).id}` as any)}
                  />
                )}
              </View>
            ))}
          </View>
        )}
      </ScrollView>

      <FiltersSheet
        visible={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        brands={brands}
        subcategories={subcategories}
        seriesList={seriesList}
        brandId={brandId} setBrandId={setBrandId}
        subcat={subcat} setSubcat={setSubcat}
        series={series} setSeries={setSeries}
        onReset={resetFilters}
      />
    </View>
  );
}

// ---------- Category pill (icon + label) ----------
function CategoryPill({
  label, icon, active, onPress, testID,
}: {
  label: string; icon: keyof typeof Feather.glyphMap;
  active?: boolean; onPress?: () => void; testID?: string;
}) {
  return (
    <Pressable
      onPress={onPress}
      testID={testID}
      style={{
        flexDirection: "row", alignItems: "center", gap: 8,
        paddingHorizontal: 14, height: 40, borderRadius: 999,
        borderWidth: 1, borderColor: active ? colors.brand : colors.border,
        backgroundColor: active ? colors.brand : colors.surfaceSecondary,
      }}
    >
      <Feather name={icon} size={14} color={active ? colors.onBrand : colors.onSurfaceSecondary} />
      <Text style={{ color: active ? colors.onBrand : colors.onSurface, fontSize: 13, fontWeight: active ? "700" : "500" }}>{label}</Text>
    </Pressable>
  );
}

function ActiveChip({ label, onClose }: { label: string; onClose: () => void }) {
  return (
    <View style={{
      flexDirection: "row", alignItems: "center", gap: 6,
      paddingLeft: 10, paddingRight: 4, height: 26,
      backgroundColor: colors.brand, borderRadius: 999,
    }}>
      <Text style={{ color: colors.onBrand, fontSize: 11, fontWeight: "700" }} numberOfLines={1}>{label}</Text>
      <Pressable onPress={onClose} hitSlop={8} style={{ paddingHorizontal: 4 }}>
        <Feather name="x" size={12} color={colors.onBrand} />
      </Pressable>
    </View>
  );
}

// ---------- Family card ----------
function FamilyCard({ family: f, brandName, onPress }: { family: Family; brandName: string; onPress: () => void }) {
  return (
    <Pressable
      testID={`family-${f.family_key}`}
      onPress={onPress}
      style={({ pressed }) => [styles.card, { opacity: pressed ? 0.9 : 1 }]}
    >
      <View style={styles.imageWrap}>
        <ProductImage
          source={f.sample_image ? [f.sample_image] : []}
          style={StyleSheet.absoluteFill as any}
          contentFit="contain"
          fallbackLabel={f.variants[0]?.sku || ""}
          borderRadius={0}
        />
        <View style={styles.brandOverlay}>
          <Text style={styles.brandOverlayText}>{brandName.toUpperCase()}</Text>
        </View>
        {f.product_count > 1 ? (
          <View style={styles.variantsPill}>
            <Text style={styles.variantsPillText}>{f.product_count} variants</Text>
          </View>
        ) : null}
      </View>
      <View style={{ padding: 12, gap: 4 }}>
        {f.series ? <Text style={styles.overlineSubtle} numberOfLines={1}>{f.series}</Text> : null}
        <Text numberOfLines={2} style={styles.title}>{f.family_name}</Text>
        {f.subcategory ? <Text style={type.caption} numberOfLines={1}>{f.subcategory}</Text> : null}

        {/* swatch row */}
        {f.variants.length > 1 ? (
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 4, marginTop: 2 }}>
            {f.variants.slice(0, 5).map((v) => (
              <View key={v.id} style={styles.swatchRing}>
                <View style={[styles.swatchDot, { backgroundColor: swatchColor(v.colour, v.finish) }]} />
              </View>
            ))}
            {f.variants.length > 5 ? (
              <View style={styles.swatchRing}>
                <Text style={{ fontSize: 8, fontWeight: "700", color: colors.onSurfaceMuted }}>+{f.variants.length - 5}</Text>
              </View>
            ) : null}
          </View>
        ) : null}

        <View style={{ marginTop: 6 }}>
          {f.max_price > f.min_price ? (
            <Text style={styles.priceRange}>
              {money(f.min_price)}
              <Text style={styles.priceRangeMuted}> – {money(f.max_price)}</Text>
            </Text>
          ) : (
            <PriceTag price={f.min_price} size="md" />
          )}
        </View>
      </View>
    </Pressable>
  );
}

// ---------- Product (variant) card ----------
function ProductCard({ product: p, brandName, onPress }: { product: Product; brandName: string; onPress: () => void }) {
  return (
    <Pressable
      testID={`product-${p.id}`}
      onPress={onPress}
      style={({ pressed }) => [styles.card, { opacity: pressed ? 0.9 : 1 }]}
    >
      <View style={styles.imageWrap}>
        <ProductImage
          source={p.hero_image_url ? [p.hero_image_url, ...(p.images || [])] : p.images}
          style={StyleSheet.absoluteFill as any}
          contentFit="contain"
          fallbackLabel={p.sku}
          borderRadius={0}
        />
        <View style={styles.brandOverlay}>
          <Text style={styles.brandOverlayText}>{brandName.toUpperCase()}</Text>
        </View>
        {p.mrp > p.price ? (
          <View style={styles.discountPill}>
            <Text style={styles.discountPillText}>−{Math.round((1 - p.price / p.mrp) * 100)}%</Text>
          </View>
        ) : null}
      </View>
      <View style={{ padding: 12, gap: 4 }}>
        {p.series ? <Text style={styles.overlineSubtle} numberOfLines={1}>{p.series}</Text> : null}
        <Text numberOfLines={2} style={styles.title}>{p.name}</Text>
        <Text style={type.caption} numberOfLines={1}>{p.sku}{p.finish ? ` · ${p.finish}` : ""}</Text>
        <View style={{ marginTop: 6 }}>
          <PriceTag price={p.price} mrp={p.mrp} size="md" />
        </View>
      </View>
    </Pressable>
  );
}

function SkeletonCard({ tall }: { tall?: boolean }) {
  return (
    <View style={styles.card}>
      <View style={[styles.imageWrap, { height: tall ? 180 : 160 }]}>
        <Skeleton w="100%" h="100%" />
      </View>
      <View style={{ padding: 12, gap: 8 }}>
        <Skeleton w="70%" />
        <Skeleton w="40%" />
        <Skeleton w="50%" h={16} />
      </View>
    </View>
  );
}

// ---------- Filters bottom sheet ----------
function FiltersSheet({
  visible, onClose, brands, subcategories, seriesList,
  brandId, setBrandId, subcat, setSubcat, series, setSeries, onReset,
}: {
  visible: boolean; onClose: () => void;
  brands: Brand[]; subcategories: string[]; seriesList: string[];
  brandId: string | null; setBrandId: (v: string | null) => void;
  subcat: string | null; setSubcat: (v: string | null) => void;
  series: string | null; setSeries: (v: string | null) => void;
  onReset: () => void;
}) {
  return (
    <BottomSheet
      visible={visible}
      onClose={onClose}
      title="Filters"
      testID="catalog-filters"
      footer={
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}><Button label="Reset" variant="secondary" onPress={() => { onReset(); }} fullWidth /></View>
          <View style={{ flex: 1 }}><Button label="Show results" onPress={onClose} fullWidth /></View>
        </View>
      }
    >
      <View style={{ gap: spacing.xl }}>
        <FilterSection title="Brand">
          <Chip label="All brands" active={!brandId} onPress={() => setBrandId(null)} testID="brand-all" />
          {brands.map((b) => (
            <Chip key={b.id} label={b.name} active={brandId === b.id} onPress={() => setBrandId(brandId === b.id ? null : b.id)} testID={`brand-${b.id}`} />
          ))}
        </FilterSection>
        {subcategories.length > 0 ? (
          <FilterSection title="Subcategory">
            <Chip label="Any" active={!subcat} onPress={() => { setSubcat(null); setSeries(null); }} testID="subcat-all" />
            {subcategories.map((s) => (
              <Chip key={s} label={s} active={subcat === s} onPress={() => { setSubcat(subcat === s ? null : s); setSeries(null); }} />
            ))}
          </FilterSection>
        ) : null}
        {seriesList.length > 0 ? (
          <FilterSection title="Series">
            <Chip label="Any" active={!series} onPress={() => setSeries(null)} testID="series-all" />
            {seriesList.map((s) => (
              <Chip key={s} label={s} active={series === s} onPress={() => setSeries(series === s ? null : s)} />
            ))}
          </FilterSection>
        ) : null}
      </View>
    </BottomSheet>
  );
}

function FilterSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={{ gap: spacing.sm }}>
      <Text style={type.overline}>{title}</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  searchWrap: {
    flex: 1, flexDirection: "row", alignItems: "center", gap: 10,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
    paddingHorizontal: 14, borderRadius: radius.md, height: 44,
  },
  searchInput: { flex: 1, fontSize: 14, color: colors.onSurface, height: 44 },
  filterBtn: {
    width: 44, height: 44, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center", position: "relative",
  },
  filterDot: {
    position: "absolute", top: 6, right: 6, minWidth: 16, height: 16, borderRadius: 8,
    backgroundColor: colors.brand, alignItems: "center", justifyContent: "center", paddingHorizontal: 3,
  },
  filterDotText: { color: colors.onBrand, fontSize: 9, fontWeight: "800" },
  clearAll: { paddingHorizontal: 10, height: 26, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  clearAllText: { fontSize: 11, fontWeight: "600", color: colors.onSurfaceMuted, textDecorationLine: "underline" },

  card: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, overflow: "hidden",
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  imageWrap: {
    width: "100%", aspectRatio: 1, backgroundColor: colors.surfaceTertiary, position: "relative",
  },
  brandOverlay: {
    position: "absolute", top: 10, left: 10,
    backgroundColor: "rgba(255,255,255,0.95)", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4,
  },
  brandOverlayText: { fontSize: 9, fontWeight: "800", color: colors.onSurface, letterSpacing: 0.8 },
  variantsPill: {
    position: "absolute", bottom: 10, right: 10,
    backgroundColor: "rgba(24,24,27,0.88)", paddingHorizontal: 8, paddingVertical: 4, borderRadius: 4,
  },
  variantsPillText: { color: "#fff", fontSize: 10, fontWeight: "700", letterSpacing: 0.4 },
  discountPill: {
    position: "absolute", top: 10, right: 10,
    backgroundColor: colors.brand, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4,
  },
  discountPillText: { color: colors.onBrand, fontSize: 10, fontWeight: "800" },
  overlineSubtle: { fontSize: 10, fontWeight: "700", letterSpacing: 1.1, color: colors.onSurfaceMuted, textTransform: "uppercase" },
  title: { fontSize: 14, fontWeight: "600", color: colors.onSurface, lineHeight: 18, minHeight: 36 },
  priceRange: { fontSize: 14, fontWeight: "700", color: colors.onSurface, fontVariant: ["tabular-nums"] },
  priceRangeMuted: { fontSize: 12, fontWeight: "500", color: colors.onSurfaceMuted },
  swatchRing: {
    width: 20, height: 20, borderRadius: 10, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center", overflow: "hidden",
    backgroundColor: colors.surfaceSecondary,
  },
  swatchDot: { width: 16, height: 16, borderRadius: 8 },
});
