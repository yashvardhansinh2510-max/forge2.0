import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ProductImage } from "@/src/components/ProductImage";
import { Button, Card } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type Product = {
  id: string; name: string; sku: string; description?: string | null;
  finish?: string | null; material?: string | null; dimensions?: string | null; warranty?: string | null;
  price: number; mrp: number; stock: number; images: string[]; tags: string[];
  brand_id: string; category_id: string;
  subcategory?: string | null; series?: string | null; family_key?: string | null;
  family_name?: string | null; variant_label?: string | null;
  finish_code?: string | null; colour?: string | null;
  image_quality?: string | null;
  image_meta?: { width: number; height: number; quality: string; source_format: string; sha1?: string }[];
  specs?: Record<string, any>;
};

const QUALITY_STYLES: Record<string, { bg: string; fg: string; label: string; hint: string }> = {
  excellent: { bg: "#DCFCE7", fg: "#166534", label: "Excellent quality",
               hint: "Vector or ≥1024px source — production-ready." },
  good:      { bg: "#DBEAFE", fg: "#1E3A8A", label: "Good quality",
               hint: "640–1024px source — suitable for cards and PDFs." },
  acceptable:{ bg: "#FEF3C7", fg: "#92400E", label: "Acceptable quality",
               hint: "320–640px source — usable but not premium." },
  poor:      { bg: "#FEE2E2", fg: "#991B1B", label: "Thumbnail-grade",
               hint: "Supplier only shipped a low-res thumbnail. Recommend sourcing official media." },
  missing:   { bg: "#F3F4F6", fg: "#6B7280", label: "No image available",
               hint: "Supplier file has no image for this SKU." },
};

function swatchColor(label?: string | null): string {
  const l = (label || "").toLowerCase();
  if (!l) return "#D1D5DB";
  if (l.includes("black")) return "#0F172A";
  if (l.includes("matt white")) return "#F8FAFC";
  if (l.includes("white")) return "#FFFFFF";
  if (l.includes("taupe") || l.includes("beige")) return "#B7A08A";
  if (l.includes("stone") || l.includes("grey") || l.includes("gray")) return "#8A8A8E";
  if (l.includes("chrome") || l.includes("steel")) return "#C0C5CB";
  if (l.includes("brass") || l.includes("gold")) return "#C6A664";
  if (l.includes("bronze") || l.includes("copper")) return "#8C5E3C";
  if (l.includes("nickel")) return "#7C8791";
  return "#D1D5DB";
}

export default function ProductDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;

  const [p, setP] = useState<Product | null>(null);
  const [siblings, setSiblings] = useState<Product[]>([]);
  const [alternates, setAlternates] = useState<Product[]>([]);
  const [imageIdx, setImageIdx] = useState(0);

  useEffect(() => {
    if (!id) return;
    setP(null); setSiblings([]); setAlternates([]); setImageIdx(0);
    (async () => {
      try {
        const prod = await api.get<Product>(`/products/${id}`);
        setP(prod);
        // Fetch sibling variants in the same family
        if (prod.family_key) {
          const res = await api.get<{ items: Product[] }>(`/products?family_key=${encodeURIComponent(prod.family_key)}&limit=20`);
          setSiblings(res.items.filter((x) => x.id !== prod.id));
        }
        // Fetch alternates (existing endpoint)
        try {
          const alt = await api.get<{ items: Product[] }>(`/products/${prod.id}/alternates?limit=6`);
          setAlternates(alt.items || []);
        } catch { /* ignore */ }
      } catch {
        setP(null);
      }
    })();
  }, [id]);

  const qMeta = useMemo(() => {
    if (!p) return null;
    return QUALITY_STYLES[p.image_quality || "missing"] || QUALITY_STYLES.missing;
  }, [p]);

  if (!p) return <View style={{ flex: 1, backgroundColor: colors.surface }} />;

  const currentImage = p.images[imageIdx] || null;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <View style={styles.topbar}>
        <Pressable testID="back-btn" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Feather name="chevron-left" size={18} color={colors.onSurface} />
          <Text style={{ fontSize: 14, fontWeight: "500" }}>Catalog</Text>
        </Pressable>
        <View style={{ flex: 1 }} />
        {p.series ? <Text style={[type.caption, { marginRight: spacing.md }]}>{p.series}</Text> : null}
      </View>

      <ScrollView contentContainerStyle={{ padding: isTablet ? spacing.xxl : spacing.lg, gap: spacing.xl }} showsVerticalScrollIndicator={false}>
        <View style={{ flexDirection: isTablet ? "row" : "column", gap: spacing.xl }}>
          {/* GALLERY */}
          <View style={{ flex: 1, gap: spacing.md }}>
            <View style={{ aspectRatio: 1, borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.surfaceTertiary }}>
              <ProductImage
                source={currentImage ? [currentImage] : []}
                style={StyleSheet.absoluteFill as any}
                contentFit="cover" fallbackLabel={p.sku} borderRadius={radius.lg}
              />
              {qMeta ? (
                <View style={[styles.qualityBadgeAbs, { backgroundColor: qMeta.bg }]}>
                  <Text style={{ fontSize: 10, fontWeight: "700", color: qMeta.fg, letterSpacing: 0.4 }}>
                    {qMeta.label.toUpperCase()}
                  </Text>
                </View>
              ) : null}
            </View>
            {p.images.length > 1 ? (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
                {p.images.map((_img, i) => (
                  <Pressable key={i} onPress={() => setImageIdx(i)}
                    style={[styles.thumb, imageIdx === i && { borderColor: colors.brand, borderWidth: 2 }]}>
                    <ProductImage source={[p.images[i]]} style={StyleSheet.absoluteFill as any} contentFit="cover" fallbackLabel="" borderRadius={0} />
                  </Pressable>
                ))}
              </ScrollView>
            ) : null}
            {qMeta && p.image_quality === "poor" ? (
              <View style={{ padding: 10, backgroundColor: qMeta.bg, borderRadius: 8, flexDirection: "row", gap: 8, alignItems: "flex-start" }}>
                <Feather name="alert-triangle" size={14} color={qMeta.fg} style={{ marginTop: 2 }} />
                <Text style={{ flex: 1, fontSize: 12, color: qMeta.fg, lineHeight: 18 }}>{qMeta.hint}</Text>
              </View>
            ) : null}
          </View>

          {/* DETAILS */}
          <View style={{ flex: 1.1, gap: spacing.lg }}>
            {/* Breadcrumb */}
            {(p.subcategory || p.series) ? (
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                {p.subcategory ? <Text style={type.overline}>{p.subcategory}</Text> : null}
                {p.subcategory && p.series ? <Feather name="chevron-right" size={12} color={colors.onSurfaceMuted} /> : null}
                {p.series ? <Text style={type.overline}>{p.series}</Text> : null}
              </View>
            ) : null}

            <View>
              <Text style={[type.displayLg, { marginTop: 4 }]}>{p.family_name || p.name}</Text>
              <Text style={[type.mono, { marginTop: 4 }]}>{p.sku}</Text>
              {p.colour ? (
                <View style={{ flexDirection: "row", gap: 6, alignItems: "center", marginTop: 8 }}>
                  <View style={[styles.swatchDot, { backgroundColor: swatchColor(p.colour) }]} />
                  <Text style={{ fontSize: 13, color: colors.onSurfaceSecondary }}>{p.colour}{p.finish_code ? `  ·  code ${p.finish_code}` : ""}</Text>
                </View>
              ) : null}
            </View>

            <View style={{ flexDirection: "row", alignItems: "baseline", gap: spacing.md }}>
              <Text style={{ fontSize: 30, fontWeight: "700", color: colors.onSurface, fontVariant: ["tabular-nums"] }}>{money(p.price)}</Text>
              {p.mrp > p.price ? (
                <>
                  <Text style={{ fontSize: 16, color: colors.onSurfaceMuted, textDecorationLine: "line-through" }}>{money(p.mrp)}</Text>
                  <View style={{ backgroundColor: colors.successBg, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4 }}>
                    <Text style={{ color: colors.success, fontSize: 11, fontWeight: "700" }}>SAVE {Math.round((1 - p.price / p.mrp) * 100)}%</Text>
                  </View>
                </>
              ) : null}
            </View>

            {/* Finish selector — sibling variants */}
            {siblings.length > 0 ? (
              <View style={{ gap: spacing.sm }}>
                <Text style={type.overline}>Finish · {siblings.length + 1} variants</Text>
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                  <VariantPill product={p} active onPress={() => {}} />
                  {siblings.map((s) => (
                    <VariantPill key={s.id} product={s} active={false} onPress={() => router.replace(`/(admin)/catalog/${s.id}` as any)} />
                  ))}
                </View>
              </View>
            ) : null}

            {p.description ? (
              <Text style={[type.body, { color: colors.onSurfaceSecondary, lineHeight: 22 }]}>{p.description}</Text>
            ) : null}

            {/* Specs */}
            <Card style={{ padding: 0 }}>
              {[
                ["Series",     p.series],
                ["Family",     p.family_name],
                ["Subcategory",p.subcategory],
                ["Colour",     p.colour],
                ["Finish",     p.finish],
                ["Finish code",p.finish_code],
                ["Material",   p.material],
                ["Dimensions", p.dimensions],
                ["Warranty",   p.warranty],
                ["In stock",   String(p.stock)],
                ...((p.specs && Object.keys(p.specs).length)
                  ? Object.entries(p.specs).map(([k, v]) => [k, Array.isArray(v) ? v.join(", ") : String(v)])
                  : []),
              ]
                .filter(([, v]) => v && String(v).trim() !== "")
                .map(([k, v], i) => (
                  <View key={String(k)} style={[styles.specRow, { borderTopWidth: i === 0 ? 0 : StyleSheet.hairlineWidth, borderColor: colors.border }]}>
                    <Text style={type.caption}>{k}</Text>
                    <Text style={{ fontSize: 13, fontWeight: "500", color: colors.onSurface, textAlign: "right", flex: 1, marginLeft: 12 }}>{String(v)}</Text>
                  </View>
                ))}
            </Card>

            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <Button label="Add to quotation" icon="plus" onPress={() => router.push("/(admin)/quotations/new" as any)} testID="add-to-quote" size="lg" />
              <Button label="Share" variant="secondary" icon="share-2" onPress={() => {}} size="lg" />
            </View>
          </View>
        </View>

        {/* Related / alternates */}
        {alternates.length > 0 ? (
          <View style={{ gap: spacing.md }}>
            <Text style={type.overline}>Related products</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 12 }}>
              {alternates.map((a) => (
                <Pressable
                  key={a.id}
                  onPress={() => router.replace(`/(admin)/catalog/${a.id}` as any)}
                  style={{ width: 200 }}
                >
                  <View style={{ aspectRatio: 1, borderRadius: radius.md, overflow: "hidden", backgroundColor: colors.surfaceTertiary }}>
                    <ProductImage source={a.images} style={StyleSheet.absoluteFill as any} contentFit="cover" fallbackLabel={a.sku} borderRadius={radius.md} />
                  </View>
                  <Text numberOfLines={2} style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface, marginTop: 6 }}>{a.name}</Text>
                  <Text style={[type.mono, { fontSize: 13, fontWeight: "700", marginTop: 2 }]}>{money(a.price)}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function VariantPill({ product, active, onPress }: { product: Product; active: boolean; onPress: () => void }) {
  const label = product.colour || product.variant_label || product.finish || "Variant";
  return (
    <Pressable
      onPress={onPress}
      style={{
        flexDirection: "row", alignItems: "center", gap: 8,
        borderWidth: active ? 2 : 1, borderColor: active ? colors.brand : colors.border,
        paddingLeft: 6, paddingRight: 12, paddingVertical: 6, borderRadius: 999,
        backgroundColor: active ? colors.brandTint : colors.surfaceSecondary,
      }}
    >
      <View style={[styles.swatchDot, { backgroundColor: swatchColor(label) }]} />
      <Text style={{ fontSize: 12, fontWeight: active ? "700" : "600", color: colors.onSurface }}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  topbar: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.lg, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border, backgroundColor: colors.surface,
  },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  specRow: { flexDirection: "row", justifyContent: "space-between", padding: spacing.md },
  swatchDot: { width: 18, height: 18, borderRadius: 9, borderWidth: 1, borderColor: colors.border },
  thumb: { width: 64, height: 64, borderRadius: radius.sm, overflow: "hidden", backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border },
  qualityBadgeAbs: { position: "absolute", top: 12, left: 12, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
});
