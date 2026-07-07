// ProductPickerSheet — full-screen mobile picker.
// Wraps the same CatalogPane, but presented as a modal for one-handed mobile use.
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
          <Pressable onPress={() => b.setPickerSheetOpen(false)} hitSlop={12} testID="picker-sheet-close">
            <Feather name="x" size={22} color={colors.onSurface} />
          </Pressable>
          <Text style={type.titleMd}>Add products</Text>
          <View style={{ width: 22 }} />
        </View>
        <View style={{ flex: 1 }}>
          <ProductExplorer />
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
});
