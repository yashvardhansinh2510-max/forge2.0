// Builder footer — notes, discount bar, totals grid, finalize CTA.
import { Feather } from "@expo/vector-icons";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, font, money, radius, spacing, type } from "@/src/theme/tokens";
import { color as ds } from "@/src/design/tokens";

import { useBuilder } from "../context/BuilderContext";

export function BuilderFooter() {
  const b = useBuilder();

  return (
    <View style={styles.wrap}>
      <View style={styles.notes}>
        <Feather name="edit-3" size={13} color={colors.onSurfaceMuted} />
        <TextInput
          testID="quote-notes-input"
          value={b.s.notes}
          onChangeText={b.setNotes}
          placeholder="Add a note for the customer (printed on the PDF)…"
          placeholderTextColor={colors.onSurfaceMuted}
          style={styles.notesInput}
          multiline
        />
      </View>

      <Pressable
        onPress={() => b.setDiscountSheet({ kind: "project" })}
        testID="open-discount-sheet"
        style={styles.discBar}
      >
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={type.overline}>Discount</Text>
          <Text style={{ fontSize: 12, color: colors.onSurfaceSecondary }} numberOfLines={1}>
            {b.s.projectDiscount ? `Project ${b.s.projectDiscount}%` : "No project discount"}
            {Object.keys(b.s.categoryDiscounts).length ? ` · ${Object.keys(b.s.categoryDiscounts).length} category discounts` : ""}
          </Text>
        </View>
        <Feather name="sliders" size={14} color={colors.onSurface} />
      </Pressable>

      <View style={styles.totals}>
        <Row label="Subtotal" value={money(b.totals.subtotal)} />
        <Row label="Discount" value={`− ${money(b.totals.discount)}`} valueColor={colors.error} />
        <View style={[styles.tRow, { borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border, paddingTop: 8, marginTop: 4 }]}>
          <Text style={{ fontSize: 13, fontFamily: font.medium, fontWeight: "500", color: colors.onSurfaceSecondary }}>Grand total</Text>
          <Text style={{ fontSize: 22, fontFamily: font.regular, letterSpacing: -0.4, color: colors.onSurface, fontVariant: ["tabular-nums"] }}>{money(b.totals.grand)}</Text>
        </View>
      </View>

      <Pressable
        testID="save-quotation-btn"
        onPress={b.finalize}
        disabled={!b.s.customerId || b.s.lines.length === 0}
        style={({ pressed }) => [styles.saveBtn, { opacity: !b.s.customerId || b.s.lines.length === 0 ? 0.4 : pressed ? 0.9 : 1 }]}
      >
        <Feather name="check" size={16} color={colors.onBrand} />
        <Text style={styles.saveBtnText}>Finish & review</Text>
      </Pressable>
    </View>
  );
}

function Row({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <View style={styles.tRow}>
      <Text style={type.caption}>{label}</Text>
      <Text style={[{ fontFamily: font.regular, fontVariant: ["tabular-nums"] as any, fontSize: 13, color: colors.onSurface }, valueColor ? { color: valueColor } : null]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    padding: spacing.md, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface, gap: spacing.md,
  },
  notes: {
    flexDirection: "row", alignItems: "flex-start", gap: 8, padding: 10,
    backgroundColor: colors.surfaceTertiary, borderRadius: radius.md,
  },
  notesInput: { flex: 1, fontSize: 13, color: colors.onSurface, padding: 0, minHeight: 20, maxHeight: 84 },
  discBar: {
    flexDirection: "row", alignItems: "center", gap: 8, padding: 10,
    backgroundColor: colors.surfaceTertiary, borderRadius: radius.md,
  },
  totals: { gap: 4 },
  tRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  saveBtn: {
    backgroundColor: ds.brass, paddingVertical: 14, borderRadius: radius.md,
    flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 8,
  },
  saveBtnText: { color: ds.canvas, fontSize: 15, fontFamily: font.semibold, fontWeight: "600", letterSpacing: -0.1 },
});
