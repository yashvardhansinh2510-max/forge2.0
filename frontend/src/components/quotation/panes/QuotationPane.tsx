// QuotationPane — the center pane. Header (customer, save state), room chips,
// canvas, footer.
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { StatusBadge } from "@/src/components/ui";
import { colors, spacing, type } from "@/src/theme/tokens";

import { useBuilder } from "../context/BuilderContext";
import { RoomChipRow } from "../canvas/RoomChipRow";
import { QuotationCanvas } from "../canvas/QuotationCanvas";
import { BuilderFooter } from "../footer/BuilderFooter";
import { CustomerBar } from "../footer/CustomerBar";

export function QuotationPane() {
  const b = useBuilder();

  return (
    <View style={styles.panel}>
      <View style={styles.head}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={type.titleMd} numberOfLines={1}>{b.quotationNumber || "New Quotation"}</Text>
            <View style={{ flexDirection: "row", gap: 6, alignItems: "center", marginTop: 2 }}>
              {b.saveState === "saving" ? <ActivityIndicator size="small" color={colors.onSurfaceMuted} /> : null}
              <Text
                style={[type.caption, { color: b.saveState === "error" ? colors.error : colors.onSurfaceMuted }]}
                testID="save-status"
              >
                {b.saveLabel}
              </Text>
            </View>
          </View>
          <StatusBadge status="draft" />
        </View>

        <CustomerBar />

        <RoomChipRow />
      </View>

      <View style={{ flex: 1 }}>
        <QuotationCanvas />
      </View>

      <BuilderFooter />
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { flex: 1, backgroundColor: colors.surfaceSecondary },
  head: {
    padding: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface, gap: spacing.sm,
  },
});
