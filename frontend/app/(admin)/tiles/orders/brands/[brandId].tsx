// frontend/app/(admin)/tiles/orders/brands/[brandId].tsx
// Ground Floor → Tiles → Tile Orders → Brands → Brand Detail — this
// BRAND's Customer Orders only (Qutone, Dimore, Kajaria… never mixes in
// another brand's orders, and never groups by dealer/supplier company —
// see services/domain_outbox.py, PurchaseOrder.brand_id/brand_name is set
// once per-brand at order-placement time). Ordered/Released/Remaining are
// the only columns here; tapping a row opens the order for Release only.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { tileOrdersApi, type BrandOrderRow, type BrandOrdersKpi } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { AgeingBadge, StatusPill, WorkflowRail } from "@/src/components/tiles/TileOrderStatusUI";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

export default function BrandDashboardScreen() {
  useRequireFloorAccess("ground-floor");
  const { brandId } = useLocalSearchParams<{ brandId: string }>();
  const router = useRouter();
  const [kpi, setKpi] = useState<BrandOrdersKpi | null>(null);
  const [orders, setOrders] = useState<BrandOrderRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!brandId) return;
    setLoading(true);
    setLoadError(null);
    try {
      const r = await tileOrdersApi.brandOrders(brandId);
      setKpi(r.kpi);
      setOrders(r.orders);
    } catch (e: any) {
      const message = e?.detail || "Could not load brand orders";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [brandId]);

  useEffect(() => { load(); }, [load]);

  const openOrder = (poId: string) => router.push(`/(admin)/tiles/orders/po/${poId}` as any);

  if (loading) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface, justifyContent: "center" }}>
        <ActivityIndicator color={colors.brand} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Pressable testID="tile-brand-queue-back" onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back to Brands</Text>
        </Pressable>
        <Text style={type.displayMd}>Brand release queue</Text>
        <WorkflowRail active="release" testID="tile-brand-queue-workflow-rail" />

        {loadError ? (
          <View style={{ marginTop: spacing.xl, gap: spacing.md, alignItems: "flex-start" }}>
            <Text style={type.bodyStrong}>{loadError}</Text>
            <Pressable testID="tile-brand-queue-retry" style={styles.retryButton} onPress={() => load()}>
              <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Retry</Text>
            </Pressable>
          </View>
        ) : (
          <>
            {kpi ? (
              <View style={styles.kpiBar}>
                {([
                  ["Orders", kpi.orders], ["Pending", kpi.pending], ["Released", kpi.ready],
                  ["Partial", kpi.partially_dispatched], ["Completed", kpi.completed],
                  ["Boxes Remaining", kpi.boxes_remaining], ["Boxes Released", kpi.boxes_released],
                  ["Oldest Waiting", `${kpi.oldest_pending_days}d`],
                ] as [string, number | string][]).map(([label, value]) => (
                  <View key={label} style={styles.kpiCell}>
                    <Text style={[type.bodyStrong, styles.kpiNumber]}>{value}</Text>
                    <Text style={type.bodyMuted}>{label}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            {orders.length === 0 ? (
              <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No orders for this brand yet.</Text>
            ) : (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tableShell}><View style={styles.queueTable}><View style={styles.tableHeader}><Text style={[styles.customerCol, styles.tableLabel]}>CUSTOMER</Text><Text style={[styles.poCol, styles.tableLabel]}>ORDER NO.</Text><Text style={[styles.qtyCol, styles.tableLabel]}>PRODUCTS</Text><Text style={[styles.qtyCol, styles.tableLabel]}>ORDERED</Text><Text style={[styles.qtyCol, styles.tableLabel]}>RELEASED</Text><Text style={[styles.qtyCol, styles.tableLabel]}>REMAINING</Text><Text style={[styles.waitCol, styles.tableLabel]}>WAITING</Text><Text style={[styles.statusCol, styles.tableLabel]}>STATUS</Text><Text style={[styles.actionCol, styles.tableLabel]}>ACTION</Text></View>{orders.map((order) => <Pressable testID={`tile-brand-order-${order.po_id}`} key={order.po_id} onPress={() => openOrder(order.po_id)} style={styles.tableRow}><Text numberOfLines={1} style={[styles.customerCol, type.bodyStrong]}>{order.customer_name}</Text><Text style={[styles.poCol, styles.mono]}>{order.po_number}</Text><Text style={[styles.qtyCol, styles.mono]}>{order.total_products}</Text><Text style={[styles.qtyCol, styles.mono]}>{order.total_boxes}</Text><Text style={[styles.qtyCol, styles.mono]}>{order.boxes_released}</Text><Text style={[styles.qtyCol, styles.mono]}>{order.boxes_remaining}</Text><View style={styles.waitCol}><AgeingBadge days={order.waiting_days} band={order.ageing_band} /></View><View style={styles.statusCol}><StatusPill status={order.overall_status} /></View><Text style={[styles.actionCol, styles.openAction]}>Release →</Text></Pressable>)}</View></ScrollView>
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.md, width: "100%", alignSelf: "stretch" },
  backRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.md },
  retryButton: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.xl },
  kpiBar: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, padding: spacing.md, marginVertical: spacing.sm },
  kpiCell: { minWidth: 76 },
  kpiNumber: { fontVariant: ["tabular-nums"] },
  tableShell: { borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  queueTable: { minWidth: 1080, width: "100%" },
  tableHeader: { flexDirection: "row", alignItems: "center", minHeight: 32, paddingHorizontal: spacing.sm, backgroundColor: colors.surfaceTertiary, borderBottomWidth: 1, borderColor: colors.border },
  tableRow: { flexDirection: "row", alignItems: "center", minHeight: 40, paddingHorizontal: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.divider, gap: spacing.xs },
  tableLabel: { ...type.overline, fontSize: 10, color: colors.onSurfaceMuted },
  customerCol: { width: 190 }, poCol: { width: 125 }, qtyCol: { width: 82, textAlign: "right" }, waitCol: { width: 100 }, statusCol: { width: 140 }, actionCol: { width: 94 },
  mono: { ...type.bodySm, fontFamily: type.numeric.fontFamily, fontVariant: ["tabular-nums"] },
  openAction: { ...type.captionStrong, color: colors.brand },
});
