// frontend/app/(admin)/tiles/orders/index.tsx
// Ground Floor → Tiles → Tile Orders — three tabs matching how BuildCon
// staff actually think about this workflow (redesigned 2026-08, replacing
// the old Customer/Company/Dispatch List purchase-order-centric layout):
//   - Customer               — one card per CustomerOrder (unchanged idea).
//   - Brands                 — one card per BRAND (Qutone, Dimore,
//     Kajaria…), not per dealer/supplier company. "I need to release
//     Kajaria" is a brand lookup, not a company lookup.
//   - Material Movement Register — the permanent, chronological audit
//     trail of every box's journey (Order Created → Release → Move to
//     Godown → Dispatch from Released/Godown → Delivered).
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { tileOrdersApi, type BrandLandingCard, type CustomerOrderCard, type MaterialMovementRow } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { AgeingBadge, BrandStatusChips, StatusPill } from "@/src/components/tiles/TileOrderStatusUI";
import { useBp } from "@/src/design/responsive";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

type TabKey = "customer" | "brands" | "material-register";
const TABS: [TabKey, string][] = [["customer", "Customer"], ["brands", "Brands"], ["material-register", "Material Movement Register"]];

const MOVEMENT_LABEL: Record<string, string> = {
  order_created: "Order Created", release: "Release", move_to_godown: "Move to Godown",
  dispatch_from_released: "Dispatch from Released", dispatch_from_godown: "Dispatch from Godown", delivered: "Delivered",
};

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
  const [brands, setBrands] = useState<BrandLandingCard[]>([]);
  const [movements, setMovements] = useState<MaterialMovementRow[]>([]);
  const [movementSearch, setMovementSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      if (tab === "customer") {
        setCustomerOrders((await tileOrdersApi.listCustomerOrders()).orders);
      } else if (tab === "brands") {
        setBrands((await tileOrdersApi.listBrands()).brands);
      } else {
        setMovements((await tileOrdersApi.listMovements({ search: movementSearch || undefined })).rows);
      }
    } catch (e: any) {
      const message = e?.detail || "Could not load orders";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [tab, movementSearch]);

  useEffect(() => { load(); }, [load]);

  const openCustomerOrder = (id: string) => router.push(`/(admin)/tiles/orders/${id}` as any);
  const openBrand = (brandId: string | null) => router.push(`/(admin)/tiles/orders/brands/${brandId || "unassigned"}` as any);

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
        ) : tab === "brands" ? (
          brands.length === 0 ? (
            <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No brands with active orders yet.</Text>
          ) : (
            <View style={styles.cardGrid}>
              {brands.map((brand) => (
                <View key={brand.brand_id || "unassigned"} style={cardSlotStyle}>
                  <Pressable onPress={() => openBrand(brand.brand_id)} style={styles.brandCard}>
                    <Feather name="tag" size={18} color={colors.onSurfaceMuted} />
                    <Text style={type.titleMd}>{brand.brand_name}</Text>
                    <Text style={type.bodyMuted}>{brand.active_orders} active order{brand.active_orders === 1 ? "" : "s"}</Text>
                    {brand.max_supplier_silent_days > 0 ? (
                      <Text style={[type.captionStrong, { color: colors.warningFg }]}>Silent {brand.max_supplier_silent_days}d</Text>
                    ) : null}
                  </Pressable>
                </View>
              ))}
            </View>
          )
        ) : (
          <View style={{ marginTop: spacing.md }}>
            <TextInput
              placeholder="Search customer, brand, tile, chalan, dispatch…" value={movementSearch}
              onChangeText={setMovementSearch} onSubmitEditing={() => load()} style={styles.searchInput}
            />
            {movements.length === 0 ? (
              <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No material movements recorded yet.</Text>
            ) : (
              movements.map((row) => (
                <View key={row.id} style={styles.movementRow}>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={type.bodyStrong}>{MOVEMENT_LABEL[row.movement_type] || row.movement_type}</Text>
                    <Text style={type.bodySm}>{row.tile_name}{row.size ? ` · ${row.size}` : ""} · {row.boxes} boxes</Text>
                    <Text style={type.bodyMuted}>{row.customer_name} · {row.brand_name}</Text>
                    {row.source || row.destination ? (
                      <Text style={type.bodyMuted}>{row.source || "—"} → {row.destination || "—"}</Text>
                    ) : null}
                    {row.chalan_number ? <Text style={type.captionStrong}>Chalan {row.chalan_number} · Dispatch {row.dispatch_number}</Text> : null}
                  </View>
                  <View style={{ alignItems: "flex-end", gap: spacing.xs }}>
                    <Text style={type.bodyMuted}>{row.created_at.slice(0, 16).replace("T", " ")}</Text>
                    <Text style={type.captionStrong}>{row.performed_by_name}</Text>
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
  tabRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg, marginBottom: spacing.md, flexWrap: "wrap" },
  tab: { paddingVertical: spacing.sm, paddingHorizontal: spacing.lg, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  tabActive: { backgroundColor: colors.brandTint, borderColor: colors.brandBorder },
  retryButton: { backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.xl },
  cardGrid: { flexDirection: "row", flexWrap: "wrap", marginHorizontal: -spacing.sm, marginTop: spacing.sm },
  customerCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, gap: spacing.sm },
  customerCardFooter: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider },
  brandCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, gap: spacing.xs },
  searchInput: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingVertical: spacing.sm, paddingHorizontal: spacing.md, marginBottom: spacing.md },
  movementRow: { flexDirection: "row", justifyContent: "space-between", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md, marginBottom: spacing.sm },
});
