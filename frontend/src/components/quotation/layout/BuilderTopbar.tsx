// BuilderTopbar V4
// -----------------------------------------------------------------------------
// Full-width top bar with:
//   [Back] [Quotation# + save state]  [Customer · Phone · Project · Reference]  [Undo/Redo · Kb Hint · Preview · Place Order]
//
// Header fields are inline TextInputs so the salesperson never leaves the
// builder to fill them in. Values persist via BuilderContext (undoable +
// autosaved).
// -----------------------------------------------------------------------------
import { Feather } from "@expo/vector-icons";
import { useState } from "react";
import { Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, money, radius, spacing, statusMeta, type } from "@/src/theme/tokens";
import { color as ds } from "@/src/design/tokens";
import { useBreakpoint } from "@/src/hooks/use-breakpoint";

import { useBuilder } from "../context/BuilderContext";

export function BuilderTopbar({ onBack }: { onBack: () => void }) {
  const b = useBuilder();
  const { isDesktop, isPhone } = useBreakpoint();

  const revs = b.recentQuotations.find((q) => q.id === b.quotationId)?.revision_count ?? 0;
  const status = b.recentQuotations.find((q) => q.id === b.quotationId)?.status || "draft";
  const meta = statusMeta[status] || statusMeta.draft;

  return (
    <View style={styles.bar}>
      <Pressable testID="builder-back" onPress={onBack} style={styles.back} hitSlop={6}>
        <Feather name="chevron-left" size={18} color={colors.onSurface} />
        {!isPhone ? <Text style={styles.backLabel}>Back</Text> : null}
      </Pressable>

      <View style={styles.titleCol}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Text style={type.titleMd} numberOfLines={1}>
            Quotation Builder
          </Text>
          {b.quotationNumber ? (
            <View style={styles.numPill}>
              <Text style={styles.numPillText}>{b.quotationNumber}</Text>
            </View>
          ) : null}
          <View style={[styles.statusPill, { backgroundColor: meta.bg }]}>
            <Text style={[styles.statusText, { color: meta.fg }]}>{meta.label}</Text>
          </View>
          {revs > 0 ? (
            <View style={styles.revPill}>
              <Feather name="git-branch" size={10} color={colors.onSurfaceMuted} />
              <Text style={styles.revText}>Rev {revs}</Text>
            </View>
          ) : null}
        </View>
        <Text
          style={[type.caption, { color: b.saveState === "error" ? colors.error : colors.onSurfaceMuted }]}
          testID="save-status"
        >
          {b.s.lines.length} items · {money(b.totals.grand)} · {b.saveLabel}
          {b.history.pastSize > 0 ? ` · ${b.history.pastSize} step${b.history.pastSize === 1 ? "" : "s"}` : ""}
        </Text>
      </View>

      {isDesktop ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.headerFieldsRow}
          contentContainerStyle={styles.headerFieldsRowContent}
        >
          <Pressable
            testID="hdr-customer"
            onPress={() => b.setCustomerSwitcherOpen(true)}
            style={({ pressed }) => [styles.field, styles.fieldPressable, pressed && styles.fieldPressed]}
          >
            <Text style={styles.fieldLabel}>Customer</Text>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
              <Text style={styles.fieldValue} numberOfLines={1}>
                {b.customers.find((c) => c.id === b.s.customerId)?.name || "Select customer"}
              </Text>
              <Feather name="chevron-down" size={11} color={colors.onSurfaceMuted} />
            </View>
          </Pressable>
          <FieldPill
            label="Phone"
            value={b.s.header.phone}
            onChange={b.setPhone}
            placeholder="+91 ·········"
            testID="hdr-phone"
          />
          <FieldPill
            label="Project"
            value={b.s.header.projectName}
            onChange={b.setProjectName}
            placeholder="Project name"
            testID="hdr-project"
          />
          <FieldPill
            label="Ref"
            value={b.s.header.referenceSource}
            onChange={b.setReferenceSource}
            placeholder="Walk-in · Architect · Instagram"
            testID="hdr-ref"
          />
        </ScrollView>
      ) : null}

      <View style={{ flexDirection: "row", gap: 4, alignItems: "center" }}>
        {!isPhone ? (
          <>
            <Pressable
              testID="generate-quotation"
              onPress={b.generateOfficialQuotation}
              disabled={b.workflowBusy || b.s.lines.length === 0}
              style={({ pressed }) => [styles.workflowBtn, styles.quotationBtn, { opacity: b.workflowBusy || b.s.lines.length === 0 ? 0.45 : pressed ? 0.76 : 1 }]}
            >
              <Feather name="file-text" size={14} color={colors.onSurface} />
              <Text style={styles.workflowText}>Quotation</Text>
            </Pressable>
            <Pressable
              testID="place-order"
              onPress={b.placeOrder}
              disabled={b.workflowBusy || b.s.lines.length === 0}
              style={({ pressed }) => [styles.workflowBtn, styles.orderBtn, { opacity: b.workflowBusy || b.s.lines.length === 0 ? 0.45 : pressed ? 0.76 : 1 }]}
            >
              <Feather name="shopping-cart" size={14} color={colors.onBrand} />
              <Text style={[styles.workflowText, { color: colors.onBrand }]}>Place Order</Text>
            </Pressable>
          </>
        ) : null}
        {isDesktop && Platform.OS === "web" ? (
          <View style={styles.hint} testID="shortcut-hint">
            <Text style={styles.hintKey}>⌘Z</Text>
            <Text style={styles.hintSep}>·</Text>
            <Text style={styles.hintKey}>⇧⌘Z</Text>
            <Text style={styles.hintSep}>·</Text>
            <Text style={styles.hintKey}>⌘K</Text>
          </View>
        ) : null}
        <Pressable
          testID="undo-btn"
          onPress={b.history.undo}
          disabled={!b.history.canUndo}
          style={({ pressed }) => [styles.iconBtn, { opacity: !b.history.canUndo ? 0.35 : pressed ? 0.7 : 1 }]}
          hitSlop={6}
        >
          <Feather name="corner-up-left" size={16} color={colors.onSurface} />
        </Pressable>
        <Pressable
          testID="redo-btn"
          onPress={b.history.redo}
          disabled={!b.history.canRedo}
          style={({ pressed }) => [styles.iconBtn, { opacity: !b.history.canRedo ? 0.35 : pressed ? 0.7 : 1 }]}
          hitSlop={6}
        >
          <Feather name="corner-up-right" size={16} color={colors.onSurface} />
        </Pressable>
      </View>
    </View>
  );
}

// -----------------------------------------------------------------------------
// FieldPill — compact inline input used in the topbar. Falls back to a static
// label when readonly.
// -----------------------------------------------------------------------------
function FieldPill({
  label, value, onChange, placeholder, readonly, testID,
}: {
  label: string; value: string; onChange?: (v: string) => void;
  placeholder?: string; readonly?: boolean; testID?: string;
}) {
  const [focused, setFocused] = useState(false);
  return (
    <View style={[styles.field, focused && styles.fieldFocused]}>
      <Text style={styles.fieldLabel}>{label}</Text>
      {readonly ? (
        <Text style={styles.fieldValue} numberOfLines={1} testID={testID}>{value || "—"}</Text>
      ) : (
        <TextInput
          value={value}
          onChangeText={onChange}
          placeholder={placeholder}
          placeholderTextColor={colors.onSurfaceMuted}
          style={[styles.fieldInput, Platform.OS === "web" && ({ outlineStyle: "none" } as any)]}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          testID={testID}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg,
    paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary, gap: 10,
  },
  back: { flexDirection: "row", alignItems: "center", gap: 3 },
  backLabel: { fontSize: 13, fontWeight: "500", color: colors.onSurface },
  titleCol: { gap: 2 },
  numPill: {
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: colors.surfaceTertiary,
  },
  numPillText: { fontSize: 11, fontWeight: "700", color: colors.onSurface, fontVariant: ["tabular-nums"] },
  statusPill: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999 },
  statusText: { fontSize: 10, fontWeight: "700", letterSpacing: 0.4 },
  revPill: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: colors.surfaceTertiary,
  },
  revText: { fontSize: 10, fontWeight: "700", color: colors.onSurfaceMuted, letterSpacing: 0.3 },

  headerFieldsRow: {
    flex: 1, marginLeft: spacing.lg,
  },
  headerFieldsRowContent: {
    flexDirection: "row", gap: 8, alignItems: "center", flexGrow: 1, justifyContent: "flex-end",
  },
  field: {
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface, minWidth: 108, maxWidth: 200,
  },
  fieldFocused: { borderColor: ds.brass, backgroundColor: ds.brassTint },
  fieldPressable: {},
  fieldPressed: { borderColor: ds.brassLine, backgroundColor: ds.brassTint },
  fieldLabel: { fontSize: 9, fontWeight: "700", color: colors.onSurfaceMuted, letterSpacing: 0.8, textTransform: "uppercase" },
  fieldValue: { fontSize: 12, fontWeight: "600", color: colors.onSurface, marginTop: 1 },
  fieldInput: { fontSize: 12, fontWeight: "600", color: colors.onSurface, padding: 0, marginTop: 1, borderWidth: 0 },

  workflowBtn: { flexDirection: "row", alignItems: "center", gap: 6, height: 34, paddingHorizontal: 10, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth },
  quotationBtn: { backgroundColor: colors.surface, borderColor: colors.border },
  orderBtn: { backgroundColor: colors.brand, borderColor: colors.brand },
  workflowText: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  iconBtn: {
    padding: 8, borderRadius: radius.md,
    backgroundColor: colors.surfaceTertiary,
  },
  hint: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6,
    backgroundColor: colors.surfaceTertiary, marginRight: 4,
  },
  hintKey: { fontSize: 10, fontWeight: "700", color: colors.onSurfaceSecondary, fontVariant: ["tabular-nums"] },
  hintSep: { fontSize: 10, color: colors.onSurfaceMuted },
});
