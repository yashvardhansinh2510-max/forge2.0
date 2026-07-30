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
import { AgeingBadge, CustomerBoxCounterRow, StatusPill } from "@/src/components/tiles/TileOrderStatusUI";
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
        <Pressable style={styles.primaryButton} onPress={() => load()}>
          <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Retry</Text>
        </Pressable>
        <Pressable onPress={() => router.back()} style={styles.backRow}>
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
        <Pressable onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back to Tile Orders</Text>
        </Pressable>

        <View style={styles.summaryCard}>
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <Text style={type.overline}>{summary.number}</Text>
            <StatusPill status={summary.overall_status} />
          </View>
          <Text style={type.displayMd}>{summary.customer_name}</Text>
          <Text style={type.bodyMuted}>{summary.order_date.slice(0, 10)} · {summary.brand_count} brand{summary.brand_count === 1 ? "" : "s"}</Text>
          <View style={{ flexDirection: "row", gap: spacing.lg, marginTop: spacing.sm }}>
            <View><Text style={type.numeric}>{summary.total_products}</Text><Text style={type.bodyMuted}>Products</Text></View>
            <View><Text style={type.numeric}>{summary.total_boxes}</Text><Text style={type.bodyMuted}>Boxes</Text></View>
            <View><Text style={type.numeric}>{summary.completion_percentage}%</Text><Text style={type.bodyMuted}>Complete</Text></View>
          </View>
          <AgeingBadge days={summary.waiting_days} band={summary.ageing_band} />
        </View>

        {brandGroups.map((group) => (
          <View key={group.purchase_order_id} style={{ marginTop: spacing.xl }}>
            <View style={styles.brandHeader}>
              <Text style={type.titleMd}>{group.brand_name}</Text>
              <StatusPill status={group.overall_status} />
            </View>
            {group.items.map((item) => (
              <View key={item.po_item_id} style={styles.itemCard}>
                <Text style={type.bodyStrong}>{item.tile_name}</Text>
                <Text style={type.bodyMuted}>{[item.series, item.finish, item.size].filter(Boolean).join(" · ") || "—"}</Text>
                <CustomerBoxCounterRow ordered={item.boxes_ordered} released={item.boxes_ready} godown={item.boxes_godown} delivered={item.boxes_dispatched} />
                <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", marginTop: spacing.sm }}>
                  <Pressable
                    disabled={item.boxes_ready <= 0} onPress={() => setSheet({ kind: "godown", poId: group.purchase_order_id, item })}
                    style={[styles.smallButton, item.boxes_ready <= 0 ? styles.smallButtonDisabled : null]}
                  >
                    <Text style={[type.captionStrong, { color: item.boxes_ready <= 0 ? colors.onSurfaceSubtle : colors.brandHover }]}>Move to Godown</Text>
                  </Pressable>
                  <Pressable
                    disabled={item.boxes_ready <= 0} onPress={() => setSheet({ kind: "dispatch-released", poId: group.purchase_order_id, item })}
                    style={[styles.smallButtonSolid, item.boxes_ready <= 0 ? styles.smallButtonDisabled : null]}
                  >
                    <Text style={[type.captionStrong, { color: item.boxes_ready <= 0 ? colors.onSurfaceSubtle : colors.onBrand }]}>Dispatch from Released</Text>
                  </Pressable>
                  <Pressable
                    disabled={item.boxes_godown <= 0} onPress={() => setSheet({ kind: "dispatch-godown", poId: group.purchase_order_id, item })}
                    style={[styles.smallButtonSolid, item.boxes_godown <= 0 ? styles.smallButtonDisabled : null]}
                  >
                    <Text style={[type.captionStrong, { color: item.boxes_godown <= 0 ? colors.onSurfaceSubtle : colors.onBrand }]}>Dispatch from Godown</Text>
                  </Pressable>
                </View>
              </View>
            ))}
          </View>
        ))}
      </ScrollView>

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
  scroll: { padding: spacing.xl, width: "100%", maxWidth: 760, alignSelf: "center" },
  backRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.md },
  primaryButton: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.xl },
  summaryCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, gap: spacing.xs },
  brandHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm },
  itemCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, marginTop: spacing.sm, gap: spacing.xs },
  smallButton: { borderWidth: 1, borderColor: colors.brandBorder, borderRadius: radius.md, paddingVertical: spacing.xs, paddingHorizontal: spacing.sm },
  smallButtonSolid: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.xs, paddingHorizontal: spacing.sm },
  smallButtonDisabled: { backgroundColor: colors.surfaceTertiary, borderColor: colors.border },
});
