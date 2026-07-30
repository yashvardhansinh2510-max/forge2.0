// frontend/app/(admin)/tiles/orders/po/[poId].tsx
// Ground Floor → Tiles → Tile Orders → Brands → Brand → Order detail —
// the Brand page's ONLY responsibility is Release Material (workflow
// redesign, 2026-08). The supplier/brand never decides Godown or Dispatch
// — those decisions, and the Chalan, belong to BuildCon on the Customer
// page (see app/(admin)/tiles/orders/[id].tsx). Nothing else happens here.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { tileOrdersApi, type PurchaseOrderDetail } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { ReleaseMaterialSheet } from "@/src/components/tiles/TileMovementSheets";
import { BrandBoxCounterRow, StatusPill } from "@/src/components/tiles/TileOrderStatusUI";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

export default function BrandOrderDetailScreen() {
  useRequireFloorAccess("ground-floor");
  const { poId } = useLocalSearchParams<{ poId: string }>();
  const router = useRouter();
  const [order, setOrder] = useState<PurchaseOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showRelease, setShowRelease] = useState(false);

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

  const anyPending = order.items.some((item) => item.boxes_pending > 0);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Pressable onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back to {order.brand_name || "Brand"}</Text>
        </Pressable>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <Text style={type.displayMd}>{order.customer_name}</Text>
          <StatusPill status={order.overall_status} />
        </View>
        <Text style={type.bodyMuted}>{order.number} · {order.brand_name || "Unassigned brand"}</Text>

        <View style={{ marginVertical: spacing.lg }}>
          <Pressable
            disabled={!anyPending} onPress={() => setShowRelease(true)}
            style={[styles.actionButton, !anyPending ? { opacity: 0.5 } : null]}
          >
            <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Release Material</Text>
          </Pressable>
        </View>

        {order.items.map((item) => (
          <View key={item.id} style={styles.itemCard}>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <Text style={type.bodyStrong}>{item.name}</Text>
              <StatusPill status={item.overall_status} />
            </View>
            <Text style={type.bodyMuted}>{[item.series, item.finish, item.size].filter(Boolean).join(" · ") || "—"}</Text>
            <BrandBoxCounterRow ordered={item.qty} released={item.boxes_ready} remaining={item.boxes_pending} />
          </View>
        ))}
      </ScrollView>

      {showRelease ? (
        <ReleaseMaterialSheet
          poId={order.id} items={order.items} onClose={() => setShowRelease(false)}
          onDone={async () => { setShowRelease(false); await load(); }}
        />
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.xl, width: "100%", maxWidth: 760, alignSelf: "center" },
  backRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.md },
  actionButton: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md, alignItems: "center" },
  itemCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, marginBottom: spacing.sm, gap: spacing.xs },
});
