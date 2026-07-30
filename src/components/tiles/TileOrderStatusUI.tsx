// frontend/src/components/tiles/TileOrderStatusUI.tsx
// Shared building blocks for every Tile Orders logistics screen: the
// overall_status pill, the waiting-days ageing badge (green/amber/red per
// the design doc's 0-7/8-14/15+ bands), and the per-line box-counter row.
import { Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/src/theme/tokens";
import type { AgeingBand, CustomerOrderBrand, TileOverallStatus } from "@/src/api/tileOrders";

const STATUS_COLORS: Record<TileOverallStatus, { fg: string; bg: string; border: string }> = {
  Pending: { fg: colors.onSurfaceMuted, bg: colors.surfaceSecondary, border: colors.border },
  Ready: { fg: colors.infoFg, bg: colors.infoBg, border: colors.infoBorder },
  "Partially Dispatched": { fg: colors.warningFg, bg: colors.warningBg, border: colors.warningBorder },
  Dispatched: { fg: colors.successFg, bg: colors.successBg, border: colors.successBorder },
  Delivered: { fg: colors.successFg, bg: colors.successBg, border: colors.successBorder },
};

export function StatusPill({ status }: { status: TileOverallStatus }) {
  const palette = STATUS_COLORS[status] || STATUS_COLORS.Pending;
  return (
    <View style={{
      alignSelf: "flex-start", paddingVertical: 3, paddingHorizontal: spacing.sm,
      borderRadius: radius.pill, backgroundColor: palette.bg, borderWidth: 1, borderColor: palette.border,
    }}>
      <Text style={[type.captionStrong, { color: palette.fg }]}>{status}</Text>
    </View>
  );
}

const AGEING_COLORS: Record<AgeingBand, { fg: string; bg: string; border: string }> = {
  green: { fg: colors.successFg, bg: colors.successBg, border: colors.successBorder },
  amber: { fg: colors.warningFg, bg: colors.warningBg, border: colors.warningBorder },
  red: { fg: colors.errorFg, bg: colors.errorBg, border: colors.errorBorder },
};

export function AgeingBadge({ days, band }: { days: number; band: AgeingBand }) {
  const palette = AGEING_COLORS[band];
  return (
    <View style={{
      alignSelf: "flex-start", paddingVertical: 3, paddingHorizontal: spacing.sm,
      borderRadius: radius.pill, backgroundColor: palette.bg, borderWidth: 1, borderColor: palette.border,
    }}>
      <Text style={[type.captionStrong, { color: palette.fg }]}>{days} day{days === 1 ? "" : "s"} waiting</Text>
    </View>
  );
}

export function BoxCounterRow({ ordered, ready, dispatched, pending }: { ordered: number; ready: number; dispatched: number; pending: number }) {
  const cell = (label: string, value: number) => (
    <View style={{ alignItems: "center", flex: 1 }}>
      <Text style={type.numeric}>{value}</Text>
      <Text style={[type.bodyMuted, { fontSize: 11 }]}>{label}</Text>
    </View>
  );
  return (
    <View style={{ flexDirection: "row", paddingVertical: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider }}>
      {cell("Ordered", ordered)}
      {cell("Ready", ready)}
      {cell("Dispatched", dispatched)}
      {cell("Pending", pending)}
    </View>
  );
}

export function BrandStatusChips({ brands }: { brands: CustomerOrderBrand[] }) {
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
      {brands.map((brand) => (
        <View key={brand.purchase_order_id} style={{
          flexDirection: "row", alignItems: "center", gap: 4, paddingVertical: 2, paddingHorizontal: spacing.sm,
          borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
        }}>
          <Text style={type.bodySm}>{brand.brand_name}</Text>
          <StatusPill status={brand.status} />
        </View>
      ))}
    </View>
  );
}
