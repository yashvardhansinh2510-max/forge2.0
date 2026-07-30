// frontend/app/(admin)/tiles/orders/index.tsx
// Ground Floor → Tiles → Orders — three tabs over the same underlying
// CustomerOrder/PurchaseOrder data: Customer (one card per CustomerOrder),
// Company (one card per supplier, landing only — never customer orders
// directly), and Dispatch List (the permanent dispatch register).
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { tileOrdersApi, type CustomerOrderCard, type DispatchListRow, type SupplierLandingCard } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { AgeingBadge, BrandStatusChips, StatusPill } from "@/src/components/tiles/TileOrderStatusUI";
import { useBp } from "@/src/design/responsive";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

type TabKey = "customer" | "company" | "dispatch-list";
const TABS: [TabKey, string][] = [["customer", "Customer"], ["company", "Company"], ["dispatch-list", "Dispatch List"]];

export default function TileOrdersScreen() {
  useRequireFloorAccess("ground-floor");
  const router = useRouter();
  const { isPhone, isTablet } = useBp();
  const cols = isPhone ? 1 : isTablet ? 2 : 3;
  const cardSlotStyle = { width: `${100 / cols}%` as const, padding: spacing.sm };
  const [tab, setTab] = useState<TabKey>("customer");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [customerOrders, setCustomerOrders] = useState<CustomerOrderCard[]>([]);
  const [suppliers, setSuppliers] = useState<SupplierLandingCard[]>([]);
  const [dispatchRows, setDispatchRows] = useState<DispatchListRow[]>([]);
  const [dispatchSearch, setDispatchSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      if (tab === "customer") {
        setCustomerOrders((await tileOrdersApi.listCustomerOrders()).orders);
      } else if (tab === "company") {
        setSuppliers((await tileOrdersApi.listSuppliers()).suppliers);
      } else {
        setDispatchRows((await tileOrdersApi.listDispatches({ search: dispatchSearch || undefined })).rows);
      }
    } catch (e: any) {
      const message = e?.detail || "Could not load orders";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [tab, dispatchSearch]);

  useEffect(() => { load(); }, [load]);

  const openCustomerOrder = (id: string) => router.push(`/(admin)/tiles/orders/${id}` as any);
  const openSupplier = (supplierId: string | null) => router.push(`/(admin)/tiles/orders/company/${supplierId || "unassigned"}` as any);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={type.overline}>GROUND FLOOR · TILES</Text>
        <Text style={type.displayMd}>Tile Orders</Text>
        <Text style={type.bodyMuted}>Track every tile order from placement to delivery.</Text>

        <View style={styles.tabRow}>
          {TABS.map(([key, label]) => (
            <Pressable key={key} onPress={() => setTab(key)} style={[styles.tab, tab === key ? styles.tabActive : null]}>
              <Text style={[type.bodyStrong, tab === key ? { color: colors.brandHover } : null]}>{label}</Text>
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
                <View key={order.id} style={cardSlotStyle}>
                  <Pressable onPress={() => openCustomerOrder(order.id)} style={styles.customerCard}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                      <View style={{ flex: 1, minWidth: 0 }}>
                        <Text numberOfLines={1} style={type.titleSm}>{order.customer_name}</Text>
                        <Text numberOfLines={1} style={type.bodyMuted}>{order.customer_phone || "No phone on file"}</Text>
                      </View>
                      <Text style={type.captionStrong}>{order.number}</Text>
                    </View>
                    <AgeingBadge days={order.waiting_days} band={order.ageing_band} />
                    <BrandStatusChips brands={order.brands} />
                    <View style={styles.customerCardFooter}>
                      <Text style={type.bodyMuted}>{order.total_products} products · {order.total_boxes} boxes</Text>
                      <StatusPill status={order.overall_status} />
                    </View>
                  </Pressable>
                </View>
              ))}
            </View>
          )
        ) : tab === "company" ? (
          suppliers.length === 0 ? (
            <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No suppliers with active orders yet.</Text>
          ) : (
            <View style={styles.cardGrid}>
              {suppliers.map((supplier) => (
                <View key={supplier.supplier_id || "unassigned"} style={cardSlotStyle}>
                  <Pressable onPress={() => openSupplier(supplier.supplier_id)} style={styles.supplierCard}>
                    <Feather name="briefcase" size={18} color={colors.onSurfaceMuted} />
                    <Text style={type.titleMd}>{supplier.supplier_name}</Text>
                    <Text style={type.bodyMuted}>{supplier.active_orders} active order{supplier.active_orders === 1 ? "" : "s"}</Text>
                    {supplier.max_supplier_silent_days > 0 ? (
                      <Text style={[type.captionStrong, { color: colors.warningFg }]}>Supplier silent {supplier.max_supplier_silent_days}d</Text>
                    ) : null}
                  </Pressable>
                </View>
              ))}
            </View>
          )
        ) : (
          <View style={{ marginTop: spacing.md }}>
            <TextInput
              placeholder="Search customer, supplier, dispatch, chalan…" value={dispatchSearch}
              onChangeText={setDispatchSearch} onSubmitEditing={() => load()} style={styles.searchInput}
            />
            {dispatchRows.length === 0 ? (
              <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No dispatches yet.</Text>
            ) : (
              dispatchRows.map((row, i) => (
                <View key={`${row.dispatch_number}-${i}`} style={styles.dispatchRow}>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={type.bodyStrong}>{row.dispatch_number} · {row.chalan_number}</Text>
                    <Text style={type.bodySm}>{row.tile_name} {row.tile_size ? `· ${row.tile_size}` : ""} · {row.boxes} boxes</Text>
                    <Text style={type.bodyMuted}>{row.customer_name} · {row.supplier_name} · {row.destination}</Text>
                  </View>
                  <View style={{ alignItems: "flex-end", gap: spacing.xs }}>
                    <Text style={type.bodyMuted}>{row.dispatch_date}</Text>
                    <Text style={[type.captionStrong, { color: colors.brandHover }]}>{row.status}</Text>
                  </View>
                </View>
              ))
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.xl, width: "100%", maxWidth: 1120, alignSelf: "center" },
  tabRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg, marginBottom: spacing.md },
  tab: { paddingVertical: spacing.sm, paddingHorizontal: spacing.lg, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  tabActive: { backgroundColor: colors.brandTint, borderColor: colors.brandBorder },
  retryButton: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.xl },
  cardGrid: { flexDirection: "row", flexWrap: "wrap", marginHorizontal: -spacing.sm, marginTop: spacing.sm },
  customerCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, gap: spacing.sm },
  customerCardFooter: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider },
  supplierCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, gap: spacing.xs },
  searchInput: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingVertical: spacing.sm, paddingHorizontal: spacing.md, marginBottom: spacing.md },
  dispatchRow: { flexDirection: "row", justifyContent: "space-between", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md, marginBottom: spacing.sm },
});
