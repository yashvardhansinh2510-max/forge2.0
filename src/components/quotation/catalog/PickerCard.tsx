// Product picker card — tap to quick-add; long-press to focus in the Assistant
// (or open the quick-add sheet on mobile). Whole-row tap and the inline "+"
// both quick-add; both flash the same success confirmation (row tint + toast)
// so the feedback is identical regardless of which hit-target the user used.
import * as Haptics from "expo-haptics";
import { memo, useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { toast } from "@/src/components/Toast";
import { ProductImage } from "@/src/components/ProductImage";
import { colors, money, radius, type } from "@/src/theme/tokens";

import { VariantSwatchStrip } from "../shared/VariantChip";
import { QuickAddButton } from "../shared/QuickAddButton";
import { productImageList } from "../helpers/media";
import type { Product, ProductVariant } from "../helpers/types";

type Props = {
  product: Product;
  onQuickAdd: (p: Product, v?: ProductVariant) => void;
  onLongPress?: (p: Product) => void;
  onOpenDetails?: (p: Product) => void;
};

const ROW_FLASH_MS = 700;

function PickerCardImpl({ product, onQuickAdd, onLongPress, onOpenDetails }: Props) {
  const [rowFlash, setRowFlash] = useState(false);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (flashTimer.current) clearTimeout(flashTimer.current); }, []);

  const handleLong = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (onLongPress) onLongPress(product);
    else if (onOpenDetails) onOpenDetails(product);
  };

  const handleRowAdd = () => {
    onQuickAdd(product);
    Haptics.selectionAsync();
    toast.success(`${product.name} added to quotation`);
    setRowFlash(true);
    if (flashTimer.current) clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setRowFlash(false), ROW_FLASH_MS);
  };

  return (
    <View style={{ gap: 6 }}>
      <Pressable
        testID={`add-product-${product.id}`}
        onPress={handleRowAdd}
        onLongPress={handleLong}
        delayLongPress={280}
        style={({ pressed }) => [
          styles.row,
          rowFlash
            ? { backgroundColor: colors.successBg, borderColor: colors.successBorder }
            : { backgroundColor: pressed ? colors.surfaceTertiary : colors.surfaceSecondary },
        ]}
      >
        <ProductImage source={productImageList(product)} style={styles.thumb} fallbackLabel={product.sku} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={styles.name} numberOfLines={1}>{product.name}</Text>
          <Text style={type.caption} numberOfLines={1}>
            {product.sku}{product.finish ? ` · ${product.finish}` : ""}
          </Text>
        </View>
        <Text style={styles.price} numberOfLines={1}>{money(product.price)}</Text>
        <QuickAddButton
          circular
          circularSize={28}
          iconSize={16}
          onAdd={() => onQuickAdd(product)}
          toastText={`${product.name} added to quotation`}
          testID={`add-plus-${product.id}`}
        />
      </Pressable>
      <VariantSwatchStrip
        product={product}
        onSelect={(v) => {
          onQuickAdd(product, v);
          Haptics.selectionAsync();
          toast.success(`${product.name} · ${v.finish || v.color || v.size || v.sku} added`);
        }}
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
  price: { fontFamily: "System", fontSize: 13, fontWeight: "700", color: colors.onSurface, fontVariant: ["tabular-nums"], flexShrink: 0 },
});
