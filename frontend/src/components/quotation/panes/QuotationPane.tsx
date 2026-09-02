// QuotationPane V4 — the right pane in the V4 shell.
// Renders: sticky header (number + save state + status), room chip row, canvas
// (rooms + line items), footer (notes + discount + totals + place order).
//
// Customer / phone / project / reference-source live in the topbar on desktop
// and in this pane's fixed header on compact layouts, so they never disappear
// behind the quotation canvas.
import { Feather } from "@expo/vector-icons";
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { StatusBadge } from "@/src/components/ui";
import { colors, spacing, type } from "@/src/theme/tokens";
import { font as dsFont } from "@/src/design/tokens";

import { useBuilder } from "../context/BuilderContext";
import { RoomChipRow } from "../canvas/RoomChipRow";
import { QuotationCanvas } from "../canvas/QuotationCanvas";
import { BuilderFooter } from "../footer/BuilderFooter";

export function QuotationPane({ compact = false }: { compact?: boolean }) {
  const b = useBuilder();

  const customer = b.customers.find((c) => c.id === b.s.customerId);
  const revs = b.recentQuotations.find((q) => q.id === b.quotationId)?.revision_count ?? 0;

  return (
    <View style={styles.panel}>
      <View style={styles.head}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.docNumber} numberOfLines={1}>
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

        {/* The top bar intentionally stays compact on phone and two-pane
            layouts. Keep every customer/project field here instead of making
            the salesperson scroll past the quotation table to find them. */}
        {compact ? <CompactHeaderFields /> : null}

        <RoomChipRow />
      </View>

      <View style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
        <QuotationCanvas compact={compact} />
      </View>

      <BuilderFooter compact={compact} />
    </View>
  );
}

function CompactHeaderFields() {
  const b = useBuilder();
  const customer = b.customers.find((c) => c.id === b.s.customerId);

  return (
    <View style={styles.compactFields} testID="compact-quotation-fields">
      <Pressable
        testID="compact-hdr-customer"
        onPress={() => b.setCustomerSwitcherOpen(true)}
        style={[styles.compactField, styles.compactFieldWide]}
      >
        <Text style={styles.fieldLabel}>Customer</Text>
        <View style={styles.customerValueRow}>
          <Text style={styles.fieldValue} numberOfLines={1}>{customer?.company || customer?.name || "Select customer"}</Text>
          <Feather name="chevron-down" size={12} color={colors.onSurfaceMuted} />
        </View>
      </Pressable>
      <CompactTextField label="Project" value={b.s.header.projectName} onChange={b.setProjectName} placeholder="Project name" testID="compact-hdr-project" />
      <CompactTextField label="Address" value={b.s.header.address} onChange={b.setAddress} placeholder="Site / delivery address" testID="compact-hdr-address" wide />
      <CompactTextField label="Phone" value={b.s.header.phone} onChange={b.setPhone} placeholder="+91 ·········" testID="compact-hdr-phone" />
      <CompactTextField label="Reference" value={b.s.header.referenceSource} onChange={b.setReferenceSource} placeholder="Walk-in · Architect" testID="compact-hdr-ref" />
      <Pressable
        testID="compact-hdr-referrer"
        onPress={() => b.setReferrerSwitcherOpen(true)}
        accessibilityRole="button"
        accessibilityLabel="Choose referrer"
        style={({ pressed }) => [styles.compactField, styles.compactFieldWide, pressed && styles.compactFieldPressed]}
      >
        <Text style={styles.fieldLabel}>Referred by</Text>
        <View style={styles.customerValueRow}>
          <Text style={styles.fieldValue} numberOfLines={1}>{b.s.header.referrerName || "None"}</Text>
          <Feather name="chevron-down" size={12} color={colors.onSurfaceMuted} />
        </View>
      </Pressable>
    </View>
  );
}

function CompactTextField({
  label, value, onChange, placeholder, testID, wide = false,
}: {
  label: string; value: string; onChange: (value: string) => void; placeholder: string; testID: string; wide?: boolean;
}) {
  return (
    <View style={[styles.compactField, wide && styles.compactFieldWide]}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={colors.onSurfaceMuted}
        numberOfLines={1}
        style={[styles.fieldInput, Platform.OS === "web" && ({ outlineStyle: "none" } as any)]}
        testID={testID}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { flex: 1, minHeight: 0, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  head: {
    padding: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary, gap: spacing.sm,
  },
  docNumber: { fontFamily: dsFont.display, fontSize: 22, lineHeight: 28, letterSpacing: -0.2, color: colors.onSurface },
  customerLine: { fontSize: 12, fontWeight: "600", color: colors.onSurfaceSecondary, marginTop: 4 },
  compactFields: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  compactField: {
    flexGrow: 1, flexBasis: "47%", minWidth: 0, minHeight: 44, paddingHorizontal: 9, paddingVertical: 6,
    borderRadius: 8, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.surface,
  },
  compactFieldWide: { flexBasis: "100%" },
  compactFieldPressed: { backgroundColor: colors.surfaceTertiary },
  fieldLabel: { fontSize: 9, fontWeight: "700", color: colors.onSurfaceMuted, letterSpacing: 0.7, textTransform: "uppercase" },
  fieldValue: { flex: 1, minWidth: 0, marginTop: 1, fontSize: 12, fontWeight: "600", color: colors.onSurface },
  fieldInput: { padding: 0, marginTop: 1, fontSize: 12, fontWeight: "600", color: colors.onSurface },
  customerValueRow: { flexDirection: "row", alignItems: "center", gap: 4 },
});
