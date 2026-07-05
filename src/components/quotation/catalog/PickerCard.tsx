// Product picker card — tap to quick-add; long-press to focus in the Assistant
// (or open the quick-add sheet on mobile).
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { memo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { ProductImage } from "@/src/components/ProductImage";
import { colors, money, radius, type } from "@/src/theme/tokens";

import { VariantSwatchStrip } from "../shared/VariantChip";
import type { Product, ProductVariant } from "../helpers/types";

type Props = {
  product: Product;
  onQuickAdd: (p: Product, v?: ProductVariant) => void;
  onLongPress?: (p: Product) => void;
  onOpenDetails?: (p: Product) => void;
};

function PickerCardImpl({ product, onQuickAdd, onLongPress, onOpenDetails }: Props) {
  const handleLong = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (onLongPress) onLongPress(product);
    else if (onOpenDetails) onOpenDetails(product);
  };
  return (
    <View style={{ gap: 6 }}>
      <Pressable
        testID={`add-product-${product.id}`}
        onPress={() => onQuickAdd(product)}
        onLongPress={handleLong}
        delayLongPress={280}
        style={({ pressed }) => [
          styles.row,
          { backgroundColor: pressed ? colors.surfaceTertiary : colors.surfaceSecondary },
        ]}
      >
        <ProductImage source={product.images} style={styles.thumb} fallbackLabel={product.sku} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={styles.name} numberOfLines={1}>{product.name}</Text>
          <Text style={type.caption} numberOfLines={1}>
            {product.sku}{product.finish ? ` · ${product.finish}` : ""}
          </Text>
        </View>
        <Text style={styles.price}>{money(product.price)}</Text>
        <Pressable
          hitSlop={8}
          testID={`add-plus-${product.id}`}
          onPress={() => onQuickAdd(product)}
          style={styles.addBtn}
        >
          <Feather name="plus" size={16} color={colors.onBrand} />
        </Pressable>
      </Pressable>
      <VariantSwatchStrip
        product={product}
        onSelect={(v) => onQuickAdd(product, v)}
      />
    </View>
  );
}

export const PickerCard = memo(PickerCardImpl, (a, b) =>
  a.product.id === b.product.id && a.product.price === b.product.price && a.product.sku === b.product.sku
);

const styles = StyleSheet.create({
  row: {
    flexDirection: "row", alignItems: "center", gap: 10, padding: 10, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  thumb: { width: 44, height: 44, borderRadius: 8, backgroundColor: colors.surfaceTertiary },
  name: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  price: { fontFamily: "System", fontSize: 13, fontWeight: "700", color: colors.onSurface, fontVariant: ["tabular-nums"] },
  addBtn: {
    width: 28, height: 28, borderRadius: 999, backgroundColor: colors.brand,
    alignItems: "center", justifyContent: "center",
  },
});
