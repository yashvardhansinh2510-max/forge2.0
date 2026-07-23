// Ground Floor → Tiles → Orders — Customer-wise / Company-wise views of the
// same underlying purchase orders. Both tabs read live from the backend on
// every load; there is no separate cache, so updating an order anywhere
// (Release Material, Godown, Dispatch) is reflected in both tabs immediately.
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { TileOrderCard, type OrderCard } from "@/src/components/tiles/TileOrderCard";
import { useBp } from "@/src/design/responsive";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

type TabKey = "customer" | "company";

type SupplierGroup = {
  supplier_id: string | null;
  supplier_name: string;
  orders: OrderCard[];
};

export default function TileOrdersScreen() {
  const router = useRouter();
  const { isPhone, isTablet } = useBp();
  const cols = isPhone ? 1 : isTablet ? 2 : 3;
  const cardSlotStyle = { width: `${100 / cols}%` as const, padding: spacing.sm };
  const [tab, setTab] = useState<TabKey>("customer");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [customerOrders, setCustomerOrders] = useState<OrderCard[]>([]);
  const [supplierGroups, setSupplierGroups] = useState<SupplierGroup[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      if (tab === "customer") {
        const r = await api.get<{ orders: OrderCard[] }>("/purchases/orders/customer-view");
        setCustomerOrders(r.orders);
      } else {
        const r = await api.get<{ suppliers: SupplierGroup[] }>("/purchases/orders/company-view");
        setSupplierGroups(r.suppliers);
      }
    } catch (e: any) {
      const message = e?.detail || "Could not load orders";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => { load(); }, [load]);

  const openOrder = (poId: string) => router.push(`/(admin)/tiles/orders/${poId}` as any);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={type.overline}>GROUND FLOOR · TILES</Text>
        <Text style={type.displayMd}>Tile Orders</Text>
        <Text style={type.bodyMuted}>Track every tile order from placement to delivery.</Text>

        <View style={styles.tabRow}>
          {(["customer", "company"] as TabKey[]).map((key) => (
            <Pressable
              key={key}
              onPress={() => setTab(key)}
              style={[styles.tab, tab === key ? styles.tabActive : null]}
            >
              <Text style={[type.bodyStrong, tab === key ? { color: colors.brandHover } : null]}>
                {key === "customer" ? "Customer-wise" : "Company-wise"}
              </Text>
            </Pressable>
          ))}
        </View>

        {loading ? (
          <ActivityIndicator style={{ marginTop: spacing.xl }} color={colors.brand} />
        ) : loadError ? (
          <View style={{ marginTop: spacing.xl, alignItems: "flex-start", gap: spacing.md }}>
            <Text style={type.bodyStrong}>{loadError}</Text>
            <Pressable style={styles.retryButton} onPress={() => load()}>
              <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Retry</Text>
            </Pressable>
          </View>
        ) : tab === "customer" ? (
          customerOrders.length === 0 ? (
            <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No tile orders yet.</Text>
          ) : (
            <View style={styles.cardGrid}>
              {customerOrders.map((order) => (
                <View key={order.po_id} style={cardSlotStyle}>
                  <TileOrderCard order={order} onPress={() => openOrder(order.po_id)} />
                </View>
              ))}
            </View>
          )
        ) : supplierGroups.length === 0 ? (
          <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No tile orders yet.</Text>
        ) : (
          supplierGroups.map((group) => (
            <View key={group.supplier_id || "unassigned"} style={{ marginTop: spacing.xl }}>
              <View style={styles.supplierHeader}>
                <Feather name="briefcase" size={16} color={colors.onSurfaceMuted} />
                <Text style={[type.titleMd, { flex: 1, minWidth: 0 }]} numberOfLines={1}>
                  {group.supplier_name}
                </Text>
                <Text style={type.bodyMuted}>
                  {group.orders.length} order{group.orders.length === 1 ? "" : "s"}
                </Text>
              </View>
              <View style={styles.cardGrid}>
                {group.orders.map((order) => (
                  <View key={order.po_id} style={cardSlotStyle}>
                    <TileOrderCard order={order} onPress={() => openOrder(order.po_id)} />
                  </View>
                ))}
              </View>
            </View>
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.xl, width: "100%", maxWidth: 1120, alignSelf: "center" },
  tabRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg, marginBottom: spacing.md },
  tab: {
    paddingVertical: spacing.sm, paddingHorizontal: spacing.lg,
    borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
  tabActive: { backgroundColor: colors.brandTint, borderColor: colors.brandBorder },
  retryButton: {
    backgroundColor: colors.brand, borderRadius: radius.md,
    paddingVertical: spacing.md, paddingHorizontal: spacing.xl,
  },
  cardGrid: { flexDirection: "row", flexWrap: "wrap", marginHorizontal: -spacing.sm, marginTop: spacing.sm },
  supplierHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm },
});
