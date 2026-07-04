import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ProductImage } from "@/src/components/ProductImage";
import { Button, Card } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type Product = {
  id: string; name: string; sku: string; description?: string; finish?: string;
  material?: string; dimensions?: string; warranty?: string;
  price: number; mrp: number; stock: number; images: string[]; tags: string[];
};

export default function ProductDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [p, setP] = useState<Product | null>(null);
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;

  useEffect(() => {
    api.get<Product>(`/products/${id}`).then(setP).catch(() => setP(null));
  }, [id]);

  if (!p) return <View style={{ flex: 1, backgroundColor: colors.surface }} />;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <View style={styles.topbar}>
        <Pressable testID="back-btn" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Feather name="chevron-left" size={18} color={colors.onSurface} />
          <Text style={{ fontSize: 14, fontWeight: "500" }}>Catalog</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: isTablet ? spacing.xxl : spacing.lg, gap: spacing.xl }} showsVerticalScrollIndicator={false}>
        <View style={{ flexDirection: isTablet ? "row" : "column", gap: spacing.xl }}>
          <View style={{ flex: 1, aspectRatio: 1, borderRadius: radius.lg, overflow: "hidden" }}>
            <ProductImage source={p.images} style={StyleSheet.absoluteFill as any} contentFit="cover" fallbackLabel={p.sku} borderRadius={radius.lg} />
          </View>

          <View style={{ flex: 1.1, gap: spacing.lg }}>
            <View>
              <Text style={type.overline}>{p.finish || "PRODUCT"}</Text>
              <Text style={[type.displayLg, { marginTop: 4 }]}>{p.name}</Text>
              <Text style={[type.mono, { marginTop: 4 }]}>{p.sku}</Text>
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

            <Text style={[type.body, { color: colors.onSurfaceSecondary, lineHeight: 22 }]}>{p.description || "—"}</Text>

            <Card style={{ padding: 0 }}>
              {[
                ["Material", p.material],
                ["Finish", p.finish],
                ["Dimensions", p.dimensions],
                ["Warranty", p.warranty],
                ["In Stock", String(p.stock)],
              ].map(([k, v], i) => (
                <View key={String(k)} style={[styles.specRow, { borderTopWidth: i === 0 ? 0 : StyleSheet.hairlineWidth, borderColor: colors.border }]}>
                  <Text style={type.caption}>{k}</Text>
                  <Text style={{ fontSize: 13, fontWeight: "500", color: colors.onSurface }}>{v || "—"}</Text>
                </View>
              ))}
            </Card>

            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <Button label="Add to quotation" icon="plus" onPress={() => router.push("/(admin)/quotations/new" as any)} testID="add-to-quote" size="lg" />
              <Button label="Share" variant="secondary" icon="share-2" onPress={() => {}} size="lg" />
            </View>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  topbar: {
    paddingHorizontal: spacing.lg, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border, backgroundColor: colors.surface,
  },
  backBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  specRow: { flexDirection: "row", justifyContent: "space-between", padding: spacing.md },
});
