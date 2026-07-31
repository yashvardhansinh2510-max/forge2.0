// frontend/src/components/tiles/TileOrderStatusUI.tsx
// Shared building blocks for every Tile Orders screen: the overall_status
// pill (business-language label, see statusLabel()), the waiting-days
// ageing badge (green/amber/red per the design doc's 0-7/8-14/15+ bands),
// and the per-line box-counter rows.
//
// Tile Orders workflow redesign (2026-08): the ladder value stored on the
// backend (Pending/Ready/Partially Dispatched/Dispatched/Delivered) is
// unchanged, but staff never see those words — statusLabel() translates
// them to the business vocabulary confirmed with BuildCon (Released instead
// of Ready, Delivered instead of Dispatched). The box-counter row is split
// into a Brand-page version (Ordered/Released/Remaining) and a
// Customer-page version (Ordered/Released/Godown/Delivered) — no more
// generic Ready/Dispatched/Pending counters.
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

// Backend ladder word -> business word BuildCon staff actually use.
export function statusLabel(status: TileOverallStatus): string {
  switch (status) {
    case "Pending": return "Pending";
    case "Ready": return "Released";
    case "Partially Dispatched": return "Partially Delivered";
    case "Dispatched": return "Delivered";
    case "Delivered": return "Delivered";
    default: return status;
  }
}

export function StatusPill({ status }: { status: TileOverallStatus }) {
  const palette = STATUS_COLORS[status] || STATUS_COLORS.Pending;
  return (
    <View style={{
      alignSelf: "flex-start", paddingVertical: 3, paddingHorizontal: spacing.sm,
      borderRadius: radius.pill, backgroundColor: palette.bg, borderWidth: 1, borderColor: palette.border,
    }}>
      <Text style={[type.captionStrong, { color: palette.fg }]}>{statusLabel(status)}</Text>
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

function Cell({ label, value, emphasis }: { label: string; value: number; emphasis?: boolean }) {
  return (
    <View style={{ alignItems: "center", flex: 1 }}>
      <Text style={[type.numeric as any, emphasis ? { color: colors.brand } : null]}>{value}</Text>
      <Text style={[type.bodyMuted, { fontSize: 11 }]}>{label}</Text>
    </View>
  );
}

// Brand page — its ONLY job is Release Material, so it only ever shows
// what's left to release. No Godown/Dispatched columns here; those
// decisions belong to BuildCon on the Customer page.
export function BrandBoxCounterRow({ ordered, released, remaining }: { ordered: number; released: number; remaining: number }) {
  return (
    <View style={{ flexDirection: "row", paddingVertical: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider }}>
      <Cell label="Ordered" value={ordered} />
      <Cell label="Released" value={released} emphasis />
      <Cell label="Remaining" value={remaining} />
    </View>
  );
}

// Customer page — BuildCon operations. Shows every bucket a box can be in
// once the Brand has released it: still-Released (in the brand's stock
// pipeline, available to move), at BuildCon's own Godown, or Delivered to
// the customer.
export function CustomerBoxCounterRow({ ordered, released, godown, delivered }: { ordered: number; released: number; godown: number; delivered: number }) {
  return (
    <View style={{ flexDirection: "row", paddingVertical: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider }}>
      <Cell label="Ordered" value={ordered} />
      <Cell label="Released" value={released} emphasis={released > 0} />
      <Cell label="Godown" value={godown} emphasis={godown > 0} />
      <Cell label="Delivered" value={delivered} />
    </View>
  );
}

type WorkflowStage = "quotation" | "release" | "released" | "godown" | "dispatch" | "register" | "chalan" | "delivered";
const WORKFLOW_STEPS: { key: WorkflowStage; label: string }[] = [
  { key: "quotation", label: "Quotation" },
  { key: "release", label: "Brand release" },
  { key: "released", label: "Released" },
  { key: "godown", label: "Godown / direct" },
  { key: "dispatch", label: "Dispatch" },
  { key: "register", label: "Register" },
  { key: "chalan", label: "Chalan" },
  { key: "delivered", label: "Delivered" },
];

export function WorkflowRail({ active, testID }: { active: WorkflowStage; testID?: string }) {
  const current = Math.max(0, WORKFLOW_STEPS.findIndex((step) => step.key === active));
  return (
    <View testID={testID} style={workflowStyles.rail}>
      {WORKFLOW_STEPS.map((step, index) => {
        const isActive = index === current;
        const isComplete = index < current;
        return (
          <View key={step.key} style={workflowStyles.step}>
            <View style={[workflowStyles.dot, isActive || isComplete ? workflowStyles.dotActive : null]} />
            <Text style={[workflowStyles.label, isActive ? workflowStyles.labelActive : null]}>{step.label}</Text>
            {index < WORKFLOW_STEPS.length - 1 ? <View style={[workflowStyles.line, isComplete ? workflowStyles.lineActive : null]} /> : null}
          </View>
        );
      })}
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

const workflowStyles = {
  rail: {
    flexDirection: "row" as const, alignItems: "center" as const, flexWrap: "wrap" as const,
    backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, gap: 4,
  },
  step: { flexDirection: "row" as const, alignItems: "center" as const, gap: 4 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.onSurfaceSubtle },
  dotActive: { backgroundColor: colors.brand },
  label: { ...type.caption, fontSize: 10, color: colors.onSurfaceMuted },
  labelActive: { color: colors.brand, fontWeight: "700" as const },
  line: { width: 10, height: 1, backgroundColor: colors.border, marginHorizontal: 1 },
  lineActive: { backgroundColor: colors.brand },
};
