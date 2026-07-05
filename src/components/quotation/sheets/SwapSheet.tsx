// Swap alternates sheet — ranked closest-first, preserves qty/discount/room.
import { Feather } from "@expo/vector-icons";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { BottomSheet } from "@/src/components/BottomSheet";
import { EmptyState } from "@/src/components/ui";
import { ProductImage } from "@/src/components/ProductImage";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

import { useBuilder } from "../context/BuilderContext";
import { VariantSwatchStrip } from "../shared/VariantChip";

export function SwapSheet() {
  const b = useBuilder();

  return (
    <BottomSheet
      visible={!!b.swapSheet}
      onClose={b.closeSwap}
      title="Swap for an alternate"
      testID="swap-sheet"
    >
      {b.swapLoading ? (
        <View style={{ alignItems: "center", padding: spacing.xl }}>
          <ActivityIndicator />
        </View>
      ) : b.swapItems.length === 0 ? (
        <EmptyState icon="refresh-cw" title="No alternates found" subtitle="Try a different product." />
      ) : (
        <View style={{ gap: 8 }}>
          <Text style={type.caption}>
            Ranked closest-first · family → brand+category → category. Qty, discount and room are preserved.
          </Text>
          {b.swapItems.map((p) => (
            <View key={p.id} style={{ gap: 4 }}>
              <Pressable
                testID={`swap-target-${p.id}`}
                onPress={() => b.commitSwap(p)}
                style={({ pressed }) => [
                  styles.row,
                  { backgroundColor: pressed ? colors.surfaceTertiary : colors.surfaceSecondary },
                ]}
              >
                <ProductImage source={p.images} style={styles.thumb} fallbackLabel={p.sku} />
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{p.name}</Text>
                  <Text style={type.caption}>{p.sku}{p.finish ? ` · ${p.finish}` : ""}</Text>
                </View>
                <Text style={{ fontFamily: "System", fontVariant: ["tabular-nums"], fontSize: 13, fontWeight: "600" }}>{money(p.price)}</Text>
                <Feather name="corner-down-right" size={14} color={colors.brand} />
              </Pressable>
              <VariantSwatchStrip
                product={p}
                onSelect={(v) => b.commitSwap(p, v)}
              />
            </View>
          ))}
        </View>
      )}
    </BottomSheet>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row", alignItems: "center", gap: 10, padding: 10, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  thumb: { width: 44, height: 44, borderRadius: 8, backgroundColor: colors.surfaceTertiary },
});
