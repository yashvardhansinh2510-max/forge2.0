// QuotationPane V4 — the right pane in the V4 shell.
// Renders: sticky header (number + save state + status), room chip row, canvas
// (rooms + line items), footer (notes + discount + totals + place order).
//
// Customer / phone / project / reference-source have moved to the topbar as
// inline pills in V4, so this pane only shows what the quotation *contains*.
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { StatusBadge } from "@/src/components/ui";
import { colors, spacing, type } from "@/src/theme/tokens";

import { useBuilder } from "../context/BuilderContext";
import { RoomChipRow } from "../canvas/RoomChipRow";
import { QuotationCanvas } from "../canvas/QuotationCanvas";
import { BuilderFooter } from "../footer/BuilderFooter";

export function QuotationPane() {
  const b = useBuilder();

  const customer = b.customers.find((c) => c.id === b.s.customerId);
  const revs = b.recentQuotations.find((q) => q.id === b.quotationId)?.revision_count ?? 0;

  return (
    <View style={styles.panel}>
      <View style={styles.head}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={type.titleMd} numberOfLines={1}>
              {b.quotationNumber || "New Quotation"}
            </Text>
            <View style={{ flexDirection: "row", gap: 6, alignItems: "center", marginTop: 2 }}>
              {b.saveState === "saving" ? <ActivityIndicator size="small" color={colors.onSurfaceMuted} /> : null}
              <Text
                style={[type.caption, { color: b.saveState === "error" ? colors.error : colors.onSurfaceMuted }]}
                testID="save-status"
              >
                {b.saveLabel}
                {revs > 0 ? ` · Rev ${revs}` : ""}
              </Text>
            </View>
            {customer ? (
              <Text style={styles.customerLine} numberOfLines={1}>
                {customer.company || customer.name}
                {b.s.header.projectName ? ` · ${b.s.header.projectName}` : ""}
              </Text>
            ) : null}
          </View>
          <StatusBadge status="draft" />
        </View>

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
    backgroundColor: colors.surfaceSecondary, gap: spacing.sm,
  },
  customerLine: { fontSize: 12, fontWeight: "600", color: colors.onSurfaceSecondary, marginTop: 4 },
});
