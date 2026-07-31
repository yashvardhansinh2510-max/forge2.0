// frontend/app/(admin)/tiles/orders/[id].tsx
// Ground Floor → Tiles → Tile Orders → Customer detail — this IS BuildCon
// operations (workflow redesign, 2026-08). Once a Brand releases material,
// it shows up here for BuildCon to decide: Move to Godown, or Dispatch
// (from Released or from Godown stock) straight to the customer. The
// Brand/Company page never makes this decision and never generates a
// Chalan — only the two Dispatch actions on this page do. Products are
// grouped by BRAND (never by dealer/supplier company).
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { tileOrdersApi, type CustomerOrderDetail, type CustomerOrderItem } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { DispatchFromGodownSheet, DispatchFromReleasedSheet, MoveToGodownSheet } from "@/src/components/tiles/TileMovementSheets";
import { AgeingBadge, StatusPill, WorkflowRail } from "@/src/components/tiles/TileOrderStatusUI";
import { Sheet } from "@/src/components/ui";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

type ActiveSheet = { kind: "godown" | "dispatch-released" | "dispatch-godown"; poId: string; item: CustomerOrderItem } | null;

export default function CustomerOrderDetailScreen() {
  useRequireFloorAccess("ground-floor");
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [order, setOrder] = useState<CustomerOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sheet, setSheet] = useState<ActiveSheet>(null);
  const [timeline, setTimeline] = useState<Record<string, any>[] | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setLoadError(null);
    try {
      setOrder(await tileOrdersApi.customerOrderDetail(id));
    } catch (e: any) {
      const message = e?.detail || "Could not load order";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const openTimeline = async () => {
    if (!id) return;
    setTimelineLoading(true);
    try {
      const result = await tileOrdersApi.customerOrderTimeline(id);
      setTimeline(result.events);
    } catch (e: any) {
      toast.error(e?.detail || "Could not load order timeline");
    } finally {
      setTimelineLoading(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface, justifyContent: "center" }}>
        <ActivityIndicator color={colors.brand} />
      </SafeAreaView>
    );
  }

  if (loadError || !order) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface, justifyContent: "center", alignItems: "center", gap: spacing.md, padding: spacing.xl }}>
        <Text style={type.bodyStrong}>{loadError || "Order not found"}</Text>
        <Pressable testID="tile-order-retry" style={styles.primaryButton} onPress={() => load()}>
          <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Retry</Text>
        </Pressable>
        <Pressable testID="tile-order-back" onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back to Tile Orders</Text>
        </Pressable>
      </SafeAreaView>
    );
  }

  const { summary, suppliers: brandGroups } = order;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Pressable testID="tile-order-back" onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back to Tile Orders</Text>
        </Pressable>

        <View style={styles.summaryBar}>
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <Text style={type.overline}>{summary.number}</Text>
            <StatusPill status={summary.overall_status} />
          </View>
          <Text style={type.displayMd}>{summary.customer_name}</Text>
          <Text style={type.bodyMuted}>{summary.order_date.slice(0, 10)} · {summary.brand_count} brand{summary.brand_count === 1 ? "" : "s"}</Text>
          <View style={styles.summaryMetrics}>
            <Text style={styles.summaryMetric}>{summary.total_products} products</Text><Text style={styles.summaryMetric}>{summary.total_boxes} boxes</Text><Text style={styles.summaryMetric}>{summary.completion_percentage}% complete</Text>
          </View>
          <AgeingBadge days={summary.waiting_days} band={summary.ageing_band} />
        </View>
        <WorkflowRail active={summary.completion_percentage >= 100 ? "delivered" : summary.overall_status === "Ready" ? "released" : "release"} testID="tile-customer-workflow-rail" />

        {brandGroups.map((group) => (
          <View key={group.purchase_order_id} style={{ marginTop: spacing.md }}>
            <View style={styles.brandHeader}>
              <Text style={type.titleMd}>{group.brand_name}</Text>
              <StatusPill status={group.overall_status} />
            </View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tableShell}><View style={styles.operationTable}><View style={styles.tableHeader}><Text style={[styles.productCol, styles.tableLabel]}>PRODUCT</Text><Text style={[styles.qtyCol, styles.tableLabel]}>ORDERED</Text><Text style={[styles.qtyCol, styles.tableLabel]}>RELEASED</Text><Text style={[styles.qtyCol, styles.tableLabel]}>GODOWN</Text><Text style={[styles.qtyCol, styles.tableLabel]}>DISPATCHED</Text><Text style={[styles.qtyCol, styles.tableLabel]}>DELIVERED</Text><Text style={[styles.qtyCol, styles.tableLabel]}>REMAINING</Text><Text style={[styles.actionsCol, styles.tableLabel]}>ACTIONS</Text></View>{group.items.map((item) => <View key={item.po_item_id} style={styles.tableRow}><View style={styles.productCol}><Text numberOfLines={1} style={type.bodyStrong}>{item.tile_name}</Text><Text numberOfLines={1} style={type.caption}>{[item.series, item.finish, item.size].filter(Boolean).join(" · ") || "—"}</Text></View><Text style={[styles.qtyCol, styles.mono]}>{item.boxes_ordered}</Text><Text style={[styles.qtyCol, styles.mono]}>{item.boxes_ready}</Text><Text style={[styles.qtyCol, styles.mono]}>{item.boxes_godown}</Text><Text style={[styles.qtyCol, styles.mono]}>{item.boxes_dispatched}</Text><Text style={[styles.qtyCol, styles.mono]}>{item.boxes_dispatched}</Text><Text style={[styles.qtyCol, styles.mono]}>{item.boxes_pending}</Text><View style={styles.actionsCol}><View style={styles.inlineActions}>{item.boxes_ready > 0 ? <><Pressable testID={`tile-order-move-godown-${item.po_item_id}`} onPress={() => setSheet({ kind: "godown", poId: group.purchase_order_id, item })} style={styles.actionOutline}><Text style={styles.actionOutlineText}>Move to Godown</Text></Pressable><Pressable testID={`tile-order-dispatch-released-${item.po_item_id}`} onPress={() => setSheet({ kind: "dispatch-released", poId: group.purchase_order_id, item })} style={styles.actionPrimary}><Text style={styles.actionPrimaryText}>Dispatch from Released</Text></Pressable></> : null}{item.boxes_godown > 0 ? <Pressable testID={`tile-order-dispatch-godown-${item.po_item_id}`} onPress={() => setSheet({ kind: "dispatch-godown", poId: group.purchase_order_id, item })} style={styles.actionPrimary}><Text style={styles.actionPrimaryText}>Dispatch from Godown</Text></Pressable> : null}{item.boxes_ready <= 0 && item.boxes_godown <= 0 ? <Text style={styles.awaitingText}>Awaiting brand release</Text> : null}</View></View></View>)}</View></ScrollView>
          </View>
        ))}
        <Pressable testID="tile-order-view-timeline" onPress={openTimeline} style={styles.timelineButton}><Text style={styles.actionOutlineText}>{timelineLoading ? "Loading timeline…" : "View Timeline"}</Text></Pressable>
      </ScrollView>

      <Sheet visible={timeline !== null} onClose={() => setTimeline(null)} title="Order timeline" subtitle="Immutable material movement history" testID="tile-order-timeline-sheet">
        <ScrollView contentContainerStyle={styles.timelineList}>{timeline?.length ? timeline.map((event, index) => <View key={`${event.id || event.created_at || "event"}-${index}`} style={styles.timelineRow}><Text style={type.bodyStrong}>{event.title || event.type || "Workflow event"}</Text><Text style={type.bodyMuted}>{event.created_at || event.timestamp || "—"}</Text></View>) : <Text style={type.bodyMuted}>No timeline events yet.</Text>}</ScrollView>
      </Sheet>

      {sheet?.kind === "godown" ? (
        <MoveToGodownSheet
          poId={sheet.poId} items={[sheet.item]} onClose={() => setSheet(null)}
          onDone={async () => { setSheet(null); await load(); }}
        />
      ) : null}
      {sheet?.kind === "dispatch-released" ? (
        <DispatchFromReleasedSheet
          poId={sheet.poId} items={[sheet.item]} onClose={() => setSheet(null)}
          onDone={async () => { setSheet(null); await load(); }}
        />
      ) : null}
      {sheet?.kind === "dispatch-godown" ? (
        <DispatchFromGodownSheet
          poId={sheet.poId} items={[sheet.item]} onClose={() => setSheet(null)}
          onDone={async () => { setSheet(null); await load(); }}
        />
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.md, width: "100%", alignSelf: "stretch" },
  backRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.md },
  primaryButton: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.xl },
  summaryBar: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, padding: spacing.md, gap: spacing.xs },
  summaryMetrics: { flexDirection: "row", gap: spacing.md, flexWrap: "wrap" },
  summaryMetric: { ...type.captionStrong, color: colors.onSurfaceSecondary },
  brandHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm },
  tableShell: { borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  operationTable: { minWidth: 1160, width: "100%" },
  tableHeader: { flexDirection: "row", alignItems: "center", minHeight: 32, paddingHorizontal: spacing.sm, backgroundColor: colors.surfaceTertiary, borderBottomWidth: 1, borderColor: colors.border },
  tableRow: { flexDirection: "row", alignItems: "center", minHeight: 46, paddingHorizontal: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.divider, gap: spacing.xs },
  tableLabel: { ...type.overline, fontSize: 10, color: colors.onSurfaceMuted },
  productCol: { width: 270 }, qtyCol: { width: 82, textAlign: "right" }, actionsCol: { width: 390 },
  mono: { ...type.bodySm, fontFamily: type.numeric.fontFamily, fontVariant: ["tabular-nums"] },
  inlineActions: { flexDirection: "row", gap: 5, flexWrap: "wrap" },
  actionOutline: { minHeight: 28, justifyContent: "center", paddingHorizontal: 8, paddingVertical: 5, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.brandBorder },
  actionPrimary: { minHeight: 28, justifyContent: "center", paddingHorizontal: 8, paddingVertical: 5, borderRadius: radius.sm, backgroundColor: colors.brand },
  actionOutlineText: { ...type.captionStrong, fontSize: 10, color: colors.brandHover },
  actionPrimaryText: { ...type.captionStrong, fontSize: 10, color: colors.onBrand },
  awaitingText: { ...type.caption, color: colors.onSurfaceMuted },
  timelineButton: { alignSelf: "flex-start", marginTop: spacing.md, borderWidth: 1, borderColor: colors.brandBorder, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.xs },
  timelineList: { padding: spacing.lg, gap: spacing.xs },
  timelineRow: { paddingVertical: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.divider, gap: 2 },
});
