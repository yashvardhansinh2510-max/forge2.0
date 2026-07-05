// BuilderTopbar — back, title, undo/redo, keyboard hint.
import { Feather } from "@expo/vector-icons";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { colors, money, radius, spacing, type } from "@/src/theme/tokens";
import { useBreakpoint } from "@/src/hooks/use-breakpoint";

import { useBuilder } from "../context/BuilderContext";

export function BuilderTopbar({ onBack }: { onBack: () => void }) {
  const b = useBuilder();
  const { isDesktop, isPhone } = useBreakpoint();

  return (
    <View style={styles.bar}>
      <Pressable
        testID="builder-back"
        onPress={onBack}
        style={{ flexDirection: "row", alignItems: "center", gap: 4 }}
        hitSlop={6}
      >
        <Feather name="chevron-left" size={18} color={colors.onSurface} />
        <Text style={{ fontSize: 14, fontWeight: "500" }}>{isPhone ? "" : "Cancel"}</Text>
      </Pressable>

      <View style={{ flex: 1, alignItems: "center", minWidth: 0 }}>
        <Text style={type.titleMd} numberOfLines={1}>New Quotation</Text>
        <Text style={type.caption} numberOfLines={1}>
          {b.s.lines.length} items · {money(b.totals.grand)} · {b.saveLabel}
          {b.history.pastSize > 0 ? ` · ${b.history.pastSize} step${b.history.pastSize === 1 ? "" : "s"}` : ""}
        </Text>
      </View>

      <View style={{ flexDirection: "row", gap: 4, alignItems: "center" }}>
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
          style={({ pressed }) => [styles.btn, { opacity: !b.history.canUndo ? 0.35 : pressed ? 0.7 : 1 }]}
          hitSlop={6}
        >
          <Feather name="corner-up-left" size={16} color={colors.onSurface} />
          {isDesktop ? <Text style={styles.btnLabel}>Undo</Text> : null}
        </Pressable>
        <Pressable
          testID="redo-btn"
          onPress={b.history.redo}
          disabled={!b.history.canRedo}
          style={({ pressed }) => [styles.btn, { opacity: !b.history.canRedo ? 0.35 : pressed ? 0.7 : 1 }]}
          hitSlop={6}
        >
          <Feather name="corner-up-right" size={16} color={colors.onSurface} />
          {isDesktop ? <Text style={styles.btnLabel}>Redo</Text> : null}
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg,
    paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface, gap: 6,
  },
  btn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  btnLabel: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  hint: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6,
    backgroundColor: colors.surfaceTertiary, marginRight: 4,
  },
  hintKey: { fontSize: 10, fontWeight: "700", color: colors.onSurfaceSecondary, fontVariant: ["tabular-nums"] },
  hintSep: { fontSize: 10, color: colors.onSurfaceMuted },
});
