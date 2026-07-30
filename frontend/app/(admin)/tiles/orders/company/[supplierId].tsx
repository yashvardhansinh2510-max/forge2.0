// frontend/app/(admin)/tiles/orders/company/[supplierId].tsx
// Ground Floor → Tiles → Orders → Company → Supplier dashboard. Shows
// ONLY this supplier's orders — never mixes in another supplier's, per
// the design doc's "supplier dashboards must never mix brands" rule.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { tileOrdersApi, type SupplierOrderRow, type SupplierOrdersKpi } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { AgeingBadge, StatusPill } from "@/src/components/tiles/TileOrderStatusUI";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

export default function SupplierDashboardScreen() {
  useRequireFloorAccess("ground-floor");
  const { supplierId } = useLocalSearchParams<{ supplierId: string }>();
  const router = useRouter();
  const [kpi, setKpi] = useState<SupplierOrdersKpi | null>(null);
  const [orders, setOrders] = useState<SupplierOrderRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!supplierId) return;
    setLoading(true);
    setLoadError(null);
    try {
      const r = await tileOrdersApi.supplierOrders(supplierId);
      setKpi(r.kpi);
      setOrders(r.orders);
    } catch (e: any) {
      const message = e?.detail || "Could not load supplier orders";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [supplierId]);

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
        <Pressable onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back to Company</Text>
        </Pressable>
        <Text style={type.displayMd}>Supplier orders</Text>

        {loadError ? (
          <View style={{ marginTop: spacing.xl, gap: spacing.md, alignItems: "flex-start" }}>
            <Text style={type.bodyStrong}>{loadError}</Text>
            <Pressable style={styles.retryButton} onPress={() => load()}>
              <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Retry</Text>
            </Pressable>
          </View>
        ) : (
          <>
            {kpi ? (
              <View style={styles.kpiBar}>
                {([
                  ["Orders", kpi.orders], ["Pending", kpi.pending], ["Ready", kpi.ready],
                  ["Partial", kpi.partially_dispatched], ["Completed", kpi.completed],
                  ["Oldest Pending", `${kpi.oldest_pending_days}d`],
                ] as [string, number | string][]).map(([label, value]) => (
                  <View key={label} style={styles.kpiCell}>
                    <Text style={type.numeric}>{value}</Text>
                    <Text style={type.bodyMuted}>{label}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            {orders.length === 0 ? (
              <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No orders for this supplier yet.</Text>
            ) : (
              orders.map((order) => (
                <Pressable key={order.po_id} onPress={() => openOrder(order.po_id)} style={styles.orderRow}>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={type.bodyStrong}>{order.customer_name}</Text>
                    <Text style={type.bodyMuted}>{order.po_number} · {order.total_products} products · {order.total_boxes} boxes</Text>
                  </View>
                  <View style={{ alignItems: "flex-end", gap: spacing.xs }}>
                    <AgeingBadge days={order.waiting_days} band={order.ageing_band} />
                    <StatusPill status={order.overall_status} />
                  </View>
                </Pressable>
              ))
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.xl, width: "100%", maxWidth: 900, alignSelf: "center" },
  backRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.md },
  retryButton: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.xl },
  kpiBar: { flexDirection: "row", flexWrap: "wrap", gap: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, marginVertical: spacing.lg },
  kpiCell: { minWidth: 80 },
  orderRow: { flexDirection: "row", justifyContent: "space-between", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md, marginBottom: spacing.sm },
});
