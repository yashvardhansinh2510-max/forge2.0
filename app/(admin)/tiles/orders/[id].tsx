// frontend/app/(admin)/tiles/orders/[id].tsx
// Ground Floor → Tiles → Orders → Customer detail — read-only summary +
// supplier-grouped product lines. Ready/Dispatch actions live on the
// Supplier order-detail page (Task 18), not here — this is the customer-
// facing view, staff use it to see the whole order's status at a glance.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { tileOrdersApi, type CustomerOrderDetail } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { AgeingBadge, BoxCounterRow, StatusPill } from "@/src/components/tiles/TileOrderStatusUI";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

export default function CustomerOrderDetailScreen() {
  useRequireFloorAccess("ground-floor");
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [order, setOrder] = useState<CustomerOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

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

  const { summary, suppliers } = order;

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

        {suppliers.map((group) => (
          <View key={group.purchase_order_id} style={{ marginTop: spacing.xl }}>
            <View style={styles.supplierHeader}>
              <Text style={type.titleMd}>{group.supplier_name}</Text>
              <StatusPill status={group.overall_status} />
            </View>
            {group.items.map((item) => (
              <View key={item.po_item_id} style={styles.itemCard}>
                <Text style={type.bodyStrong}>{item.tile_name}</Text>
                <Text style={type.bodyMuted}>{[item.series, item.finish, item.size].filter(Boolean).join(" · ") || "—"}</Text>
                <BoxCounterRow ordered={item.boxes_ordered} ready={item.boxes_ready} dispatched={item.boxes_dispatched} pending={item.boxes_pending} />
                <Text style={type.bodyMuted}>Currently: {item.current_location}</Text>
              </View>
            ))}
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.xl, width: "100%", maxWidth: 760, alignSelf: "center" },
  backRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.md },
  primaryButton: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.xl },
  summaryCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, gap: spacing.xs },
  supplierHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm },
  itemCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, marginTop: spacing.sm, gap: spacing.xs },
});
