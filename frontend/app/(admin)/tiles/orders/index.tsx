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
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Linking, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { tileOrdersApi, type BrandLandingCard, type CustomerOrderCard, type DispatchListRow, type MaterialMovementRow } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { StatusPill, WorkflowRail } from "@/src/components/tiles/TileOrderStatusUI";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

type TabKey = "customer" | "brands" | "dispatch-list" | "material-register";
const TABS: [TabKey, string][] = [
  ["customer", "Customer"], ["brands", "Brands"],
  ["dispatch-list", "Dispatch List"],
  ["material-register", "Material Movement Register"],
];

// Only "Dispatched" is a real, reachable status today — nothing in the
// current workflow ever sets Dispatch.godown_received_at or delivered_at
// (both explicitly modeled as future/unimplemented, see models_tile_orders.py),
// so "At Godown"/"Delivered" filter chips would be permanently dead options.
const DISPATCH_STATUS_FILTERS = ["All", "Dispatched"] as const;

async function openPdf(url: string) {
  if (Platform.OS === "web") {
    // @ts-ignore — web only
    window.open(url, "_blank");
  } else {
    await Linking.openURL(url);
  }
}

const MOVEMENT_LABEL: Record<string, string> = {
  order_created: "Order Created", release: "Release", move_to_godown: "Move to Godown",
  dispatch_from_released: "Dispatch from Released", dispatch_from_godown: "Dispatch from Godown", delivered: "Delivered",
};

function dispatchRowKey(row: DispatchListRow, index: number) {
  // A Dispatch/Chalan may legitimately contain multiple lines with the
  // same product name, so the render index is required as a final stable
  // per-response discriminator.
  return `${row.dispatch_id}-${row.chalan_id}-${row.tile_name}-${index}`;
}

export default function TileOrdersScreen() {
  useRequireFloorAccess("ground-floor");
  const router = useRouter();
  const [tab, setTab] = useState<TabKey>("customer");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [customerOrders, setCustomerOrders] = useState<CustomerOrderCard[]>([]);
  const [brands, setBrands] = useState<BrandLandingCard[]>([]);
  const [movements, setMovements] = useState<MaterialMovementRow[]>([]);
  const [movementSearch, setMovementSearch] = useState("");
  const [dispatchRows, setDispatchRows] = useState<DispatchListRow[]>([]);
  const [dispatchSearch, setDispatchSearch] = useState("");
  const [dispatchStatus, setDispatchStatus] = useState<typeof DISPATCH_STATUS_FILTERS[number]>("All");
  const [selectedDispatch, setSelectedDispatch] = useState<DispatchListRow | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      if (tab === "customer") {
        setCustomerOrders((await tileOrdersApi.listCustomerOrders({ page_size: 30 })).orders);
      } else if (tab === "brands") {
        setBrands((await tileOrdersApi.listBrands()).brands);
      } else if (tab === "dispatch-list") {
        setDispatchRows((await tileOrdersApi.listDispatchList({
          search: dispatchSearch || undefined,
          status: dispatchStatus === "All" ? undefined : dispatchStatus,
          page_size: 100,
        })).rows);
      } else {
        setMovements((await tileOrdersApi.listMovements({ search: movementSearch || undefined, page_size: 100 })).rows);
      }
    } catch (e: any) {
      const message = e?.detail || "Could not load orders";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [tab, movementSearch, dispatchSearch, dispatchStatus]);

  useEffect(() => { load(); }, [load]);

  const openCustomerOrder = (id: string) => router.push(`/(admin)/tiles/orders/${id}` as any);
  const openBrand = (brandId: string | null) => router.push(`/(admin)/tiles/orders/brands/${brandId || "unassigned"}` as any);
  const viewChalanPdf = async (chalanId: string) => {
    try {
      const url = await tileOrdersApi.chalanPdfUrl(chalanId);
      await openPdf(url);
    } catch (e: any) {
      toast.error(e?.detail || "Could not open Chalan PDF");
    }
  };
  const printChalan = async (chalanId: string) => {
    try {
      const url = await tileOrdersApi.chalanPdfUrl(chalanId);
      if (Platform.OS === "web") {
        // The browser's PDF viewer provides the native print command after
        // opening the authenticated, server-generated Chalan.
        // @ts-ignore — web only
        const printWindow = window.open(url, "_blank");
        if (!printWindow) throw new Error("Popup blocked");
      } else {
        await Linking.openURL(url);
      }
    } catch (e: any) {
      toast.error(e?.detail || "Could not open Chalan for printing");
    }
  };
  const viewDispatch = async (row: DispatchListRow) => {
    try {
      const result = await tileOrdersApi.listDispatchList({ dispatch_number: row.dispatch_number });
      const detail = result.rows.find((item) => item.dispatch_id === row.dispatch_id) || row;
      setSelectedDispatch(detail);
    } catch (e: any) {
      toast.error(e?.detail || "Could not load dispatch details");
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={type.overline}>GROUND FLOOR · TILES</Text>
        <Text style={type.displayMd}>Tile Orders</Text>
        <Text style={type.bodyMuted}>Operations queue · release, dispatch and audit in one workspace.</Text>
        <WorkflowRail active="quotation" testID="tile-orders-workflow-rail" />

        <View style={styles.tabRow}>
          {TABS.map(([key, label]) => (
            <Pressable testID={`tile-orders-tab-${key}`} key={key} onPress={() => setTab(key)} style={[styles.tab, tab === key ? styles.tabActive : null]}>
              <Text style={[type.bodyStrong, tab === key ? { color: colors.brandHover } : null]}>{label}</Text>
            </Pressable>
          ))}
        </View>

        {loading ? (
          <ActivityIndicator style={{ marginTop: spacing.xl }} color={colors.brand} />
        ) : loadError ? (
          <View style={{ marginTop: spacing.xl, alignItems: "flex-start", gap: spacing.md }}>
            <Text style={type.bodyStrong}>{loadError}</Text>
            <Pressable testID="tile-orders-retry" style={styles.retryButton} onPress={() => load()}>
              <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Retry</Text>
            </Pressable>
          </View>
        ) : tab === "customer" ? (
          customerOrders.length === 0 ? <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No tile orders yet.</Text> : (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.gridShell}>
              <View style={styles.dashboardGrid}>
                <View style={styles.gridHeader}><Text style={[styles.customerCol, styles.gridLabel]}>CUSTOMER</Text><Text style={[styles.orderCol, styles.gridLabel]}>ORDER NO.</Text><Text style={[styles.brandCol, styles.gridLabel]}>BRANDS</Text><Text style={[styles.numberCol, styles.gridLabel]}>PRODUCTS</Text><Text style={[styles.numberCol, styles.gridLabel]}>BOXES</Text><Text style={[styles.statusCol, styles.gridLabel]}>STATUS</Text><Text style={[styles.waitCol, styles.gridLabel]}>WAITING</Text><Text style={[styles.progressCol, styles.gridLabel]}>PROGRESS</Text><Text style={[styles.actionCol, styles.gridLabel]}>ACTION</Text></View>
                {customerOrders.map((order) => (
                  <Pressable testID={`tile-orders-customer-${order.id}`} key={order.id} onPress={() => openCustomerOrder(order.id)} style={styles.gridRow}>
                    <Text numberOfLines={1} style={[styles.customerCol, type.bodyStrong]}>{order.customer_name}</Text><Text style={[styles.orderCol, styles.mono]}>{order.number}</Text><Text numberOfLines={1} style={[styles.brandCol, type.bodySm]}>{order.brands.map((brand) => brand.brand_name).join(", ")}</Text><Text style={[styles.numberCol, styles.mono]}>{order.total_products}</Text><Text style={[styles.numberCol, styles.mono]}>{order.total_boxes}</Text><View style={styles.statusCol}><StatusPill status={order.overall_status} /></View><Text style={[styles.waitCol, styles.mono]}>{order.waiting_days}d</Text><View style={styles.progressCol}><View style={styles.progressTrack}><View style={[styles.progressFill, { width: `${order.completion_percentage}%` }]} /></View><Text style={styles.progressLabel}>{order.completion_percentage}%</Text></View><Text style={[styles.actionCol, styles.openAction]}>Open →</Text>
                  </Pressable>
                ))}
              </View>
            </ScrollView>
          )
        ) : tab === "brands" ? (
          brands.length === 0 ? <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No brands with active orders yet.</Text> : (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.gridShell}>
              <View style={styles.brandGrid}>
                <View style={styles.gridHeader}><Text style={[styles.brandNameCol, styles.gridLabel]}>BRAND</Text><Text style={[styles.numberCol, styles.gridLabel]}>ACTIVE ORDERS</Text><Text style={[styles.waitCol, styles.gridLabel]}>OLDEST WAIT</Text><Text style={[styles.actionCol, styles.gridLabel]}>ACTION</Text></View>
                {brands.map((brand) => <Pressable testID={`tile-orders-brand-${brand.brand_id || "unassigned"}`} key={brand.brand_id || "unassigned"} onPress={() => openBrand(brand.brand_id)} style={styles.gridRow}><Text style={[styles.brandNameCol, type.bodyStrong]}>{brand.brand_name}</Text><Text style={[styles.numberCol, styles.mono]}>{brand.active_orders}</Text><Text style={[styles.waitCol, styles.mono]}>{brand.max_supplier_silent_days ? `${brand.max_supplier_silent_days}d` : "—"}</Text><Text style={[styles.actionCol, styles.openAction]}>Release queue →</Text></Pressable>)}
              </View>
            </ScrollView>
          )
        ) : tab === "dispatch-list" ? (
          <View style={{ marginTop: spacing.md }}>
            <TextInput
              testID="tile-orders-dispatch-search"
              placeholder="Search customer, brand, product, dispatch, chalan…" value={dispatchSearch}
              onChangeText={setDispatchSearch} onSubmitEditing={() => load()} style={styles.searchInput}
            />
            <View style={styles.filterRow}>
              {DISPATCH_STATUS_FILTERS.map((s) => (
                <Pressable testID={`tile-orders-dispatch-status-${s.toLowerCase().replaceAll(" ", "-")}`} key={s} onPress={() => setDispatchStatus(s)} style={[styles.filterChip, dispatchStatus === s ? styles.filterChipActive : null]}>
                  <Text style={[type.captionStrong, dispatchStatus === s ? { color: colors.brandHover } : null]}>{s}</Text>
                </Pressable>
              ))}
            </View>
            {dispatchRows.length === 0 ? <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No dispatches recorded yet.</Text> : <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.gridShell}><View style={styles.dispatchGrid}><View style={styles.gridHeader}><Text style={[styles.dispatchNoCol, styles.gridLabel]}>DISPATCH NO.</Text><Text style={[styles.customerCol, styles.gridLabel]}>CUSTOMER</Text><Text style={[styles.brandCol, styles.gridLabel]}>BRAND / PRODUCT</Text><Text style={[styles.numberCol, styles.gridLabel]}>BOXES</Text><Text style={[styles.sourceCol, styles.gridLabel]}>SOURCE</Text><Text style={[styles.sourceCol, styles.gridLabel]}>DESTINATION</Text><Text style={[styles.vehicleCol, styles.gridLabel]}>VEHICLE / DRIVER</Text><Text style={[styles.statusCol, styles.gridLabel]}>STATUS</Text><Text style={[styles.createdCol, styles.gridLabel]}>CREATED</Text><Text style={[styles.actionWideCol, styles.gridLabel]}>ACTIONS</Text></View>{dispatchRows.map((row, index) => <View key={dispatchRowKey(row, index)} style={styles.gridRow}><Text style={[styles.dispatchNoCol, styles.mono]}>{row.dispatch_number}</Text><Text numberOfLines={1} style={[styles.customerCol, type.bodySm]}>{row.customer_name}</Text><Text numberOfLines={1} style={[styles.brandCol, type.bodySm]}>{row.brand_name} · {row.tile_name}</Text><Text style={[styles.numberCol, styles.mono]}>{row.boxes}</Text><Text style={[styles.sourceCol, type.bodySm]}>{row.source}</Text><Text style={[styles.sourceCol, type.bodySm]}>Customer</Text><Text numberOfLines={1} style={[styles.vehicleCol, type.bodySm]}>{row.vehicle_number || "—"} · {row.driver_name || "—"}</Text><View style={[styles.statusCol, styles.dispatchStatus]}><Text style={styles.dispatchStatusText}>{row.status}</Text></View><Text style={[styles.createdCol, styles.mono]}>{row.dispatch_date?.slice(0, 10)}</Text><View style={styles.actionWideCol}><View style={styles.inlineActions}><Pressable testID={`tile-orders-view-chalan-${row.chalan_id}-${index}`} onPress={() => viewChalanPdf(row.chalan_id)} style={styles.compactPrimary}><Text style={styles.compactPrimaryText}>View Chalan</Text></Pressable><Pressable testID={`tile-orders-print-chalan-${row.chalan_id}-${index}`} onPress={() => printChalan(row.chalan_id)} style={styles.compactButton}><Text style={styles.compactButtonText}>Print Chalan</Text></Pressable><Pressable testID={`tile-orders-view-dispatch-${row.dispatch_id}-${index}`} onPress={() => viewDispatch(row)} style={styles.compactButton}><Text style={styles.compactButtonText}>View Dispatch</Text></Pressable></View></View></View>)}</View></ScrollView>}
          </View>
        ) : (
          <View style={{ marginTop: spacing.md }}>
            <TextInput
              testID="tile-orders-movement-search"
              placeholder="Search customer, brand, tile, chalan, dispatch…" value={movementSearch}
              onChangeText={setMovementSearch} onSubmitEditing={() => load()} style={styles.searchInput}
            />
            {movements.length === 0 ? <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No material movements recorded yet.</Text> : <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.gridShell}><View style={styles.movementGrid}><View style={styles.gridHeader}><Text style={[styles.createdCol, styles.gridLabel]}>TIMESTAMP</Text><Text style={[styles.customerCol, styles.gridLabel]}>CUSTOMER</Text><Text style={[styles.brandCol, styles.gridLabel]}>BRAND / PRODUCT</Text><Text style={[styles.sourceCol, styles.gridLabel]}>MOVEMENT</Text><Text style={[styles.numberCol, styles.gridLabel]}>QTY</Text><Text style={[styles.sourceCol, styles.gridLabel]}>FROM</Text><Text style={[styles.sourceCol, styles.gridLabel]}>TO</Text><Text style={[styles.referenceCol, styles.gridLabel]}>REFERENCE</Text><Text style={[styles.userCol, styles.gridLabel]}>USER</Text></View>{movements.map((row) => <View key={row.id} style={styles.gridRow}><Text style={[styles.createdCol, styles.mono]}>{row.created_at.slice(0, 16).replace("T", " ")}</Text><Text numberOfLines={1} style={[styles.customerCol, type.bodySm]}>{row.customer_name}</Text><Text numberOfLines={1} style={[styles.brandCol, type.bodySm]}>{row.brand_name} · {row.tile_name}</Text><Text style={[styles.sourceCol, type.bodySm]}>{MOVEMENT_LABEL[row.movement_type] || row.movement_type}</Text><Text style={[styles.numberCol, styles.mono]}>{row.boxes}</Text><Text style={[styles.sourceCol, type.bodySm]}>{row.source || "—"}</Text><Text style={[styles.sourceCol, type.bodySm]}>{row.destination || "—"}</Text><Text style={[styles.referenceCol, styles.mono]}>{row.chalan_number || row.dispatch_number || "—"}</Text><Text numberOfLines={1} style={[styles.userCol, type.bodySm]}>{row.performed_by_name}</Text></View>)}</View></ScrollView>}
          </View>
        )}
      </ScrollView>
      <Modal transparent visible={Boolean(selectedDispatch)} animationType="slide" onRequestClose={() => setSelectedDispatch(null)}>
        <View style={styles.modalOverlay}>
          <View style={styles.dispatchDetailSheet}>
            {selectedDispatch ? (
              <>
                <Text testID="tile-orders-dispatch-detail-number" style={type.titleMd}>{selectedDispatch.dispatch_number}</Text>
                <Text style={type.bodyMuted}>{selectedDispatch.dispatch_date} · {selectedDispatch.status}</Text>
                <Text style={type.bodyStrong}>{selectedDispatch.customer_name} · {selectedDispatch.brand_name}</Text>
                <Text style={type.bodyMuted}>{selectedDispatch.tile_name} · {selectedDispatch.boxes} boxes · {selectedDispatch.source}</Text>
                <Text style={type.bodyMuted}>Chalan {selectedDispatch.chalan_number}</Text>
                <View style={styles.detailActions}>
                  <Pressable testID="tile-orders-dispatch-detail-view-pdf" onPress={() => viewChalanPdf(selectedDispatch.chalan_id)} style={styles.smallButtonSolid}>
                    <Text style={[type.captionStrong, { color: colors.onBrand }]}>View PDF</Text>
                  </Pressable>
                  <Pressable testID="tile-orders-dispatch-detail-print" onPress={() => printChalan(selectedDispatch.chalan_id)} style={styles.smallButton}>
                    <Text style={[type.captionStrong, { color: colors.brandHover }]}>Print</Text>
                  </Pressable>
                  <Pressable testID="tile-orders-dispatch-detail-close" onPress={() => setSelectedDispatch(null)} style={styles.smallButton}>
                    <Text style={[type.captionStrong, { color: colors.brandHover }]}>Close</Text>
                  </Pressable>
                </View>
              </>
            ) : null}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: spacing.md, paddingVertical: spacing.md, width: "100%", alignSelf: "stretch" },
  tabRow: { flexDirection: "row", gap: spacing.xs, marginTop: spacing.sm, marginBottom: spacing.xs, flexWrap: "wrap" },
  tab: { paddingVertical: spacing.xs, paddingHorizontal: spacing.md, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, minHeight: 36, justifyContent: "center" },
  tabActive: { backgroundColor: colors.brandTint, borderColor: colors.brandBorder },
  retryButton: { backgroundColor: colors.brand, borderRadius: radius.sm, paddingVertical: spacing.sm, paddingHorizontal: spacing.lg },
  gridShell: { marginTop: spacing.xs, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, maxHeight: 860 },
  dashboardGrid: { minWidth: 1200, width: "100%" },
  brandGrid: { minWidth: 720, width: "100%" },
  dispatchGrid: { minWidth: 1620, width: "100%" },
  movementGrid: { minWidth: 1320, width: "100%" },
  gridHeader: { flexDirection: "row", minHeight: 32, alignItems: "center", backgroundColor: colors.surfaceTertiary, borderBottomWidth: 1, borderBottomColor: colors.border, paddingHorizontal: spacing.sm },
  gridRow: { flexDirection: "row", minHeight: 40, alignItems: "center", backgroundColor: colors.surfaceSecondary, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.divider, paddingHorizontal: spacing.sm, gap: spacing.xs },
  gridLabel: { ...type.overline, fontSize: 10, color: colors.onSurfaceMuted },
  mono: { ...type.bodySm, fontFamily: type.numeric.fontFamily, fontVariant: ["tabular-nums"] },
  customerCol: { width: 170 }, orderCol: { width: 115 }, brandCol: { width: 200 }, numberCol: { width: 72, textAlign: "right" }, statusCol: { width: 125, alignItems: "flex-start" }, waitCol: { width: 78, textAlign: "right" }, progressCol: { width: 130, flexDirection: "row", alignItems: "center", gap: spacing.xs }, actionCol: { width: 108 }, brandNameCol: { width: 300 }, dispatchNoCol: { width: 145 }, sourceCol: { width: 105 }, vehicleCol: { width: 170 }, createdCol: { width: 135 }, actionWideCol: { width: 320 }, referenceCol: { width: 150 }, userCol: { width: 140 },
  progressTrack: { width: 76, height: 4, backgroundColor: colors.surfaceTertiary, overflow: "hidden", borderRadius: radius.pill },
  progressFill: { height: "100%", backgroundColor: colors.brand, borderRadius: radius.pill },
  progressLabel: { ...type.captionStrong, width: 32, textAlign: "right" },
  openAction: { ...type.captionStrong, color: colors.brand },
  inlineActions: { flexDirection: "row", gap: 4 },
  compactButton: { borderWidth: 1, borderColor: colors.brandBorder, borderRadius: radius.sm, paddingVertical: 5, paddingHorizontal: 7, minHeight: 28, justifyContent: "center" },
  compactPrimary: { backgroundColor: colors.brand, borderRadius: radius.sm, paddingVertical: 5, paddingHorizontal: 7, minHeight: 28, justifyContent: "center" },
  compactButtonText: { ...type.captionStrong, fontSize: 10, color: colors.brandHover },
  compactPrimaryText: { ...type.captionStrong, fontSize: 10, color: colors.onBrand },
  dispatchStatus: { justifyContent: "center", minHeight: 24, paddingHorizontal: 6, backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm },
  dispatchStatusText: { ...type.captionStrong, fontSize: 10, color: colors.onSurfaceSecondary },
  searchInput: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingVertical: spacing.xs, paddingHorizontal: spacing.md, marginBottom: spacing.xs, minHeight: 38 },
  filterRow: { flexDirection: "row", gap: spacing.xs, marginBottom: spacing.xs, flexWrap: "wrap" },
  filterChip: { paddingVertical: 5, paddingHorizontal: spacing.md, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, minHeight: 30, justifyContent: "center" },
  filterChipActive: { backgroundColor: colors.brandTint, borderColor: colors.brandBorder },
  modalOverlay: { flex: 1, justifyContent: "flex-end", backgroundColor: colors.overlay },
  dispatchDetailSheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.md, borderTopRightRadius: radius.md, padding: spacing.lg, gap: spacing.xs },
  detailActions: { flexDirection: "row", gap: spacing.xs, flexWrap: "wrap", marginTop: spacing.xs },
  smallButton: { borderWidth: 1, borderColor: colors.brandBorder, borderRadius: radius.sm, paddingVertical: spacing.xs, paddingHorizontal: spacing.sm },
  smallButtonSolid: { backgroundColor: colors.brand, borderRadius: radius.sm, paddingVertical: spacing.xs, paddingHorizontal: spacing.sm },
});
