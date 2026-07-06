// Line row — image · name/sku · finish · qty/rate/disc · actions · total.
// Tapping the row focuses it in the Assistant pane (right pane / mobile sheet).
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { memo } from "react";
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { ProductImage } from "@/src/components/ProductImage";
import { Badge } from "@/src/components/ui";
import { colors, font, money, radius, type } from "@/src/theme/tokens";
import { color as ds } from "@/src/design/tokens";

import { useBuilder } from "../context/BuilderContext";
import { effectivePct, sourceBadge } from "../helpers/pricing";
import { FinishSwatch } from "../shared/VariantChip";
import { grabCursor } from "../shared/grabCursor";
import type { Line } from "../helpers/types";

function LineRowImpl({
  line, drag, isActive, catDiscs, projDisc,
}: {
  line: Line;
  drag: () => void;
  isActive: boolean;
  catDiscs: Record<string, number>;
  projDisc: number;
}) {
  const b = useBuilder();
  const l = line;
  const eff = effectivePct(l, catDiscs, projDisc);
  const badge = sourceBadge(eff.source);
  const total = l.qty * l.unit_price * (1 - eff.pct / 100);
  const focused = b.assistantFocus?.kind === "line" && b.assistantFocus.line_id === l.id;

  const focus = () => {
    b.setAssistantFocus({ kind: "line", line_id: l.id });
    if (Platform.OS !== "web") Haptics.selectionAsync();
  };

  return (
    <Pressable
      onPress={focus}
      style={[
        styles.row,
        focused && { borderColor: ds.brassLine, backgroundColor: ds.brassTint },
        isActive && { opacity: 0.75, transform: [{ scale: 0.99 }] },
      ]}
    >
      <Pressable
        onLongPress={drag}
        delayLongPress={160}
        hitSlop={6}
        style={[styles.dragHandle, grabCursor]}
        testID={`line-drag-${l.id}`}
      >
        <Feather name="menu" size={14} color={colors.onSurfaceMuted} />
      </Pressable>
      <ProductImage source={l.image} style={styles.thumb} fallbackLabel={l.sku} />
      <View style={{ flex: 1, gap: 4, minWidth: 0 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Text style={styles.name} numberOfLines={1}>{l.name}</Text>
          {l.finish ? <FinishSwatch finish={l.finish} size={10} /> : null}
          {badge ? <Badge tone={badge.tone} label={badge.label} /> : null}
        </View>
        <Text style={type.caption} numberOfLines={1}>{l.sku}</Text>
        {l.description ? <Text style={type.caption} numberOfLines={2}>{l.description}</Text> : null}
        <View style={{ flexDirection: "row", gap: 6, marginTop: 2, flexWrap: "wrap" }}>
          <View style={styles.mini}>
            <Text style={styles.miniLabel}>QTY</Text>
            <TextInput
              testID={`qty-${l.id}`}
              value={String(l.qty)}
              keyboardType="number-pad"
              onChangeText={(v) => b.updateLine(l.id, { qty: Math.max(0, Number(v) || 0) }, "qty")}
              style={styles.miniVal}
              selectTextOnFocus
            />
          </View>
          <View style={styles.mini}>
            <Text style={styles.miniLabel}>RATE</Text>
            <TextInput
              testID={`rate-${l.id}`}
              value={String(l.unit_price)}
              keyboardType="decimal-pad"
              onChangeText={(v) => b.updateLine(l.id, { unit_price: Number(v) || 0 }, "rate")}
              style={styles.miniVal}
              selectTextOnFocus
            />
          </View>
          <Pressable
            testID={`disc-${l.id}`}
            onPress={() => b.setDiscountSheet({ kind: "line", line_id: l.id })}
            style={[styles.mini, { justifyContent: "center", flexDirection: "row", alignItems: "center", gap: 4 }]}
          >
            <Text style={styles.miniLabel}>DISC</Text>
            <Text style={styles.miniVal}>{eff.pct}%</Text>
            {l.discount_pct == null && eff.source !== "none" ? <Feather name="link" size={9} color={colors.onSurfaceMuted} /> : null}
          </Pressable>

          <Pressable testID={`line-desc-${l.id}`} onPress={() => b.setDescSheet({ line_id: l.id })} style={styles.icon}>
            <Feather name="align-left" size={13} color={colors.onSurfaceMuted} />
          </Pressable>
          <Pressable testID={`line-swap-${l.id}`} onPress={() => b.openSwap(l)} style={styles.icon}>
            <Feather name="refresh-cw" size={13} color={colors.onSurfaceMuted} />
          </Pressable>
          <Pressable testID={`line-dup-${l.id}`} onPress={() => b.duplicateLine(l.id)} style={styles.icon}>
            <Feather name="copy" size={13} color={colors.onSurfaceMuted} />
          </Pressable>
          <Pressable testID={`line-move-${l.id}`} onPress={() => b.moveLineToNextRoom(l.id)} style={styles.icon}>
            <Feather name="corner-up-right" size={13} color={colors.onSurfaceMuted} />
          </Pressable>
          <Pressable testID={`line-del-${l.id}`} onPress={() => b.removeLine(l.id)} style={styles.icon}>
            <Feather name="trash-2" size={13} color={colors.error} />
          </Pressable>
        </View>
      </View>
      <Text style={styles.total}>{money(total)}</Text>
    </Pressable>
  );
}

export const LineRow = memo(LineRowImpl);

const styles = StyleSheet.create({
  row: {
    flexDirection: "row", gap: 10, padding: 10, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  dragHandle: {
    width: 20, alignItems: "center", justifyContent: "center", alignSelf: "stretch",
    marginRight: -2, marginLeft: -4,
  },
  thumb: { width: 48, height: 48, borderRadius: 8, backgroundColor: colors.surfaceTertiary },
  name: { fontSize: 13, fontFamily: font.semibold, fontWeight: "600", color: colors.onSurface, flex: 1, letterSpacing: -0.1 },
  mini: {
    borderRadius: 7, paddingHorizontal: 8, paddingVertical: 4, minWidth: 60,
    backgroundColor: colors.surfaceTertiary,
  },
  miniLabel: { fontSize: 9, fontFamily: font.semibold, color: colors.onSurfaceMuted, fontWeight: "600", letterSpacing: 0.8 },
  miniVal: { fontSize: 13, fontFamily: font.medium, fontWeight: "500", color: colors.onSurface, padding: 0, minWidth: 40, fontVariant: ["tabular-nums"] },
  icon: { width: 28, height: 28, borderRadius: 7, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  total: { fontFamily: font.semibold, fontSize: 13, fontWeight: "600", color: colors.onSurface, fontVariant: ["tabular-nums"], letterSpacing: -0.1 },
});
