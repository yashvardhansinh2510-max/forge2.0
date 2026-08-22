// ProductPickerSheet — full-screen mobile picker.
// Wraps the shared ProductExplorer grid, presented as a modal for one-handed
// mobile use. Keeping this route on ProductExplorer is what gives Sanitary
// Bathroom Add Products the same shop-style filters and two-column browsing
// experience as the inline quotation catalog.
import { Feather } from "@expo/vector-icons";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors, spacing, type } from "@/src/theme/tokens";

import { ProductExplorer } from "../catalog/ProductExplorer";
import { useBuilder } from "../context/BuilderContext";

export function ProductPickerSheet() {
  const b = useBuilder();

  return (
    <Modal
      visible={b.pickerSheetOpen}
      animationType="slide"
      onRequestClose={() => b.setPickerSheetOpen(false)}
      presentationStyle="fullScreen"
    >
      <SafeAreaView edges={["top", "bottom"]} style={{ flex: 1, backgroundColor: colors.surface }}>
        <View style={styles.head}>
          <Pressable onPress={() => b.setPickerSheetOpen(false)} style={styles.close} testID="picker-sheet-close" accessibilityLabel="Close product picker">
            <Feather name="x" size={22} color={colors.onSurface} />
          </Pressable>
          <Text style={type.titleMd}>Add products</Text>
          <View style={{ width: 22 }} />
        </View>
        <View style={{ flex: 1 }}>
          {/* This is the only product view without the persistent BrandRail,
              so it owns the compact brand and category selectors. */}
          <ProductExplorer showCompactFilters />
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  head: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  close: { width: 44, height: 44, alignItems: "center", justifyContent: "center", marginLeft: -11 },
});
