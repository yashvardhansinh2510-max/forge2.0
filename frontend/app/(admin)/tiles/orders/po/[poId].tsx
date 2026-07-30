// frontend/app/(admin)/tiles/orders/po/[poId].tsx
// Ground Floor → Tiles → Orders → Company → Supplier → Order detail — the
// only screen with Ready/Dispatch actions, per the design doc's clean
// separation between customer-facing (read-only) and supplier-facing
// (actionable) surfaces.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { tileOrdersApi, type PurchaseOrderDetail } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { DispatchSheet, MarkReadySheet } from "@/src/components/tiles/ReadyDispatchSheets";
import { BoxCounterRow, StatusPill } from "@/src/components/tiles/TileOrderStatusUI";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

export default function SupplierOrderDetailScreen() {
  useRequireFloorAccess("ground-floor");
  const { poId } = useLocalSearchParams<{ poId: string }>();
  const router = useRouter();
  const [order, setOrder] = useState<PurchaseOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sheet, setSheet] = useState<"ready" | "dispatch" | null>(null);

  const load = useCallback(async () => {
    if (!poId) return;
    setLoading(true);
    setLoadError(null);
    try {
      setOrder(await tileOrdersApi.purchaseOrderDetail(poId));
    } catch (e: any) {
      const message = e?.detail || "Could not load order";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [poId]);

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
        <Pressable onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back</Text>
        </Pressable>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Pressable onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back to Supplier</Text>
        </Pressable>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <Text style={type.displayMd}>{order.customer_name}</Text>
          <StatusPill status={order.overall_status} />
        </View>
        <Text style={type.bodyMuted}>{order.number} · {order.supplier_name || "No supplier"}</Text>

        <View style={{ flexDirection: "row", gap: spacing.sm, marginVertical: spacing.lg }}>
          <Pressable style={styles.actionButton} onPress={() => setSheet("ready")}>
            <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Mark Ready For Pickup</Text>
          </Pressable>
          <Pressable style={styles.actionButton} onPress={() => setSheet("dispatch")}>
            <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Dispatch</Text>
          </Pressable>
        </View>

        {order.items.map((item) => (
          <View key={item.id} style={styles.itemCard}>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <Text style={type.bodyStrong}>{item.name}</Text>
              <StatusPill status={item.overall_status} />
            </View>
            <Text style={type.bodyMuted}>{[item.series, item.finish, item.size].filter(Boolean).join(" · ") || "—"}</Text>
            <BoxCounterRow ordered={item.qty} ready={item.boxes_ready} dispatched={item.boxes_dispatched} pending={item.boxes_pending} />
            <Text style={type.bodyMuted}>Currently: {item.current_location}</Text>
          </View>
        ))}
      </ScrollView>

      {sheet === "ready" ? (
        <MarkReadySheet poId={order.id} items={order.items} onClose={() => setSheet(null)} onDone={async () => { setSheet(null); await load(); }} />
      ) : null}
      {sheet === "dispatch" ? (
        <DispatchSheet
          poId={order.id} items={order.items} customerName={order.customer_name} customerAddress="" customerCity=""
          onClose={() => setSheet(null)} onDone={async () => { setSheet(null); await load(); }}
        />
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.xl, width: "100%", maxWidth: 760, alignSelf: "center" },
  backRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.md },
  actionButton: { flex: 1, backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md, alignItems: "center" },
  itemCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, marginBottom: spacing.sm, gap: spacing.xs },
});
