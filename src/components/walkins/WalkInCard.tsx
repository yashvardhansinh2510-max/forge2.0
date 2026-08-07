// Walk-in card — Phase 4 (2026-07-30). Same visual language as
// components/tiles cards: Card + IconButton + Button.
import { Pressable, Text, View } from "react-native";

import type { WalkIn } from "@/src/api/walkins";
import { Button, Card, IconButton } from "@/src/components/ui";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

const STATUS_LABEL: Record<WalkIn["status"], string> = {
  new: "New", contacted: "Contacted", selection_scheduled: "Selection Scheduled",
  selection_completed: "Selection Completed", quotation_created: "Quotation Created",
  converted: "Converted", lost: "Lost",
};
const STATUS_TONE: Record<WalkIn["status"], { bg: string; fg: string }> = {
  new: { bg: colors.brandTint, fg: colors.brandHover },
  contacted: { bg: colors.surfaceTertiary, fg: colors.onSurfaceSecondary },
  selection_scheduled: { bg: colors.warningBg, fg: colors.warning },
  selection_completed: { bg: colors.warningBg, fg: colors.warning },
  quotation_created: { bg: colors.warningBg, fg: colors.warning },
  converted: { bg: colors.successBg, fg: colors.success },
  lost: { bg: colors.surfaceTertiary, fg: colors.error },
};

function daysWaiting(visitedAt: string): number {
  const diff = Date.now() - new Date(visitedAt).getTime();
  return Math.max(0, Math.floor(diff / 86400000));
}

export function WalkInCard({
  w, onPress, onCall, onWhatsApp, onScheduleSelection,
}: {
  w: WalkIn; onPress: () => void; onCall: () => void; onWhatsApp: () => void; onScheduleSelection?: () => void;
}) {
  const tone = STATUS_TONE[w.status];
  const days = daysWaiting(w.visited_at);
  return (
    <Pressable onPress={onPress} testID={`walkin-card-${w.id}`}>
      <Card variant="outlined" style={{ marginBottom: spacing.sm, gap: spacing.xs }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
          <View style={{ flex: 1 }}>
            <Text style={type.bodyStrong}>{w.customer_name}</Text>
            <Text style={type.bodyMuted}>{w.customer_phone || "No phone"} · {w.number}</Text>
          </View>
          <View style={{ backgroundColor: tone.bg, borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 3 }}>
            <Text style={[type.captionStrong, { color: tone.fg }]}>{STATUS_LABEL[w.status]}</Text>
          </View>
        </View>
        <Text style={type.bodySm}>
          {w.source} · {(w.interested_products || []).join(", ") || "No products noted"}
        </Text>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <Text style={type.caption}>{w.salesperson_name || "Unassigned"} · Waiting {days}d</Text>
          {w.budget ? <Text style={type.captionStrong}>Budget ₹{w.budget.toLocaleString("en-IN")}</Text> : null}
        </View>
        <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs, flexWrap: "wrap" }}>
          <IconButton icon="phone" onPress={onCall} size={34} tone="brandLight" accessibilityLabel="Call" testID={`walkin-call-${w.id}`} />
          <IconButton icon="message-circle" onPress={onWhatsApp} size={34} tone="surface" accessibilityLabel="WhatsApp" testID={`walkin-wa-${w.id}`} />
          {onScheduleSelection && w.status !== "lost" && w.status !== "converted" && w.status !== "quotation_created" ? (
            <Button label="Schedule Selection" icon="calendar" variant="secondary" size="sm" onPress={onScheduleSelection} testID={`walkin-schedule-${w.id}`} />
          ) : null}
        </View>
      </Card>
    </Pressable>
  );
}
