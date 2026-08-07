// Floating add button + sticky mobile summary. Only rendered on phone.
import { Feather } from "@expo/vector-icons";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { colors, font, money, radius, spacing, type } from "@/src/theme/tokens";
import { color as ds } from "@/src/design/tokens";

import { useBuilder } from "../context/BuilderContext";

export function MobileFAB() {
  const b = useBuilder();
  return (
    <Pressable
      testID="mobile-fab"
      onPress={() => b.setPickerSheetOpen(true)}
      style={({ pressed }) => [styles.fab, pressed && { opacity: 0.9 }]}
    >
      <Feather name="plus" size={22} color={colors.onBrand} />
    </Pressable>
  );
}

export function MobileSummaryBar() {
  const b = useBuilder();
  return (
    <View style={styles.bar}>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={type.caption}>{b.s.lines.length} items · {b.saveLabel}</Text>
        <Text style={{ fontSize: 19, fontFamily: font.regular, letterSpacing: -0.3, color: colors.onSurface, fontVariant: ["tabular-nums"] }}>{money(b.totals.grand)}</Text>
      </View>
      <Pressable
        testID="mobile-add-first"
        onPress={() => b.setPickerSheetOpen(true)}
        style={styles.secondary}
      >
        <Feather name="plus" size={16} color={colors.onSurface} />
        <Text style={{ fontSize: 13, fontWeight: "600" }}>Add</Text>
      </Pressable>
      <Pressable
        testID="mobile-finalize"
        onPress={b.finalize}
        disabled={!b.s.customerId || b.s.lines.length === 0}
        style={({ pressed }) => [
          styles.primary,
          { opacity: !b.s.customerId || b.s.lines.length === 0 ? 0.4 : pressed ? 0.9 : 1 },
        ]}
      >
        <Feather name="check" size={16} color="#FFFFFF" />
        <Text style={{ fontSize: 13, fontFamily: font.semibold, fontWeight: "600", color: "#FFFFFF" }}>Finish</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  fab: {
    position: "absolute", right: spacing.lg, bottom: 96,
    width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brand,
    alignItems: "center", justifyContent: "center",
    shadowColor: "#000", shadowOpacity: 0.18, shadowRadius: 14, shadowOffset: { width: 0, height: 6 },
    elevation: 6,
  },
  bar: {
    flexDirection: "row", alignItems: "center", gap: 8, padding: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface,
    ...(Platform.OS === "ios" ? {
      shadowColor: "#000", shadowOpacity: 0.06, shadowRadius: 10, shadowOffset: { width: 0, height: -2 },
    } : { elevation: 4 }),
  },
  secondary: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
  },
  primary: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 16, paddingVertical: 10, borderRadius: radius.md,
    backgroundColor: ds.brass,
  },
});
