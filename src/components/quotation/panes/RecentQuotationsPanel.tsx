// RecentQuotationsPanel — embedded compact list in the left rail.
// Clicking any row restores the whole builder session (customer, rooms,
// items, discounts, UI state) via the backend GET /quotations/{id}.
import { Feather } from "@expo/vector-icons";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { money, radius, spacing } from "@/src/theme/tokens";
import { color as ds, statusTone } from "@/src/design/tokens";
import { useBuilder } from "../context/BuilderContext";

export function RecentQuotationsPanel() {
  const b = useBuilder();

  if (!b.recentQuotations.length) return null;

  return (
    <View style={styles.wrap}>
      <View style={styles.headRow}>
        <Text style={styles.groupLabel}>Recent Quotations</Text>
        <Pressable hitSlop={6} onPress={b.startNewQuotation} testID="rail-new-quote">
          <Feather name="plus" size={14} color={ds.inkSoft} />
        </Pressable>
      </View>
      {b.recentQuotations.slice(0, 8).map((q) => {
        const active = b.quotationId === q.id;
        return (
          <Pressable
            key={q.id}
            onPress={() => b.restoreQuotation(q.id)}
            style={[styles.row, active && styles.rowActive]}
            testID={`rail-recent-${q.number}`}
          >
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={styles.num} numberOfLines={1}>{q.number}</Text>
              <Text style={styles.sub} numberOfLines={1}>
                {q.customer_name || "—"}
                {q.project_name ? ` · ${q.project_name}` : ""}
              </Text>
            </View>
            <View style={{ alignItems: "flex-end" }}>
              <Text style={styles.amt}>{money(q.grand_total || 0)}</Text>
              <Text style={styles.status}>{statusTone[q.status]?.label || q.status}</Text>
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: spacing.lg, paddingHorizontal: 4, gap: 3, paddingBottom: 12 },
  headRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 4, marginBottom: 4 },
  groupLabel: { fontSize: 10, fontWeight: "600", color: ds.inkSoft, letterSpacing: 1.2, textTransform: "uppercase" },
  row: {
    flexDirection: "row", gap: 8, paddingHorizontal: 10, paddingVertical: 8, borderRadius: radius.sm,
  },
  rowActive: { backgroundColor: ds.sunken },
  num: { fontSize: 11.5, fontWeight: "600", color: ds.ink, fontVariant: ["tabular-nums"] },
  sub: { fontSize: 10.5, color: ds.inkSoft, marginTop: 1 },
  amt: { fontSize: 11, fontWeight: "600", color: ds.ink, fontVariant: ["tabular-nums"] },
  status: { fontSize: 9, color: ds.inkSoft, textTransform: "uppercase", letterSpacing: 0.6, marginTop: 1 },
});
