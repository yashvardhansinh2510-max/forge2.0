// Minimal bar-chart — no charting library exists anywhere in this codebase
// (grep confirms it), so this stays a plain View-based bar row rather than
// adding a new dependency for one chart.
import { Text, View } from "react-native";

import { fmtMoneyCompact } from "@/src/design/tokens";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

export function TrendChart({ points }: { points: { bucket: string; revenue: number }[] }) {
  if (points.length === 0) {
    return <Text style={[type.bodyMuted, { padding: spacing.lg, textAlign: "center" }]}>No data in this range</Text>;
  }
  const max = Math.max(...points.map((p) => p.revenue), 1);
  return (
    <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 6, height: 140, paddingHorizontal: spacing.md }}>
      {points.map((p) => (
        <View key={p.bucket} style={{ flex: 1, alignItems: "center", gap: 4 }}>
          <Text style={{ fontSize: 10, color: colors.onSurfaceMuted }} numberOfLines={1}>
            {fmtMoneyCompact(p.revenue)}
          </Text>
          <View
            style={{
              width: "100%",
              height: Math.max(4, (p.revenue / max) * 90),
              backgroundColor: colors.brand,
              borderRadius: radius.sm,
            }}
          />
          <Text style={{ fontSize: 9, color: colors.onSurfaceMuted }} numberOfLines={1}>{p.bucket}</Text>
        </View>
      ))}
    </View>
  );
}
