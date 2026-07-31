// frontend/app/(admin)/tiles/orders/po/[poId].tsx
// Ground Floor → Tiles → Tile Orders → Brands → Brand → Order detail —
// the Brand page's ONLY responsibility is Release Material (workflow
// redesign, 2026-08). The supplier/brand never decides Godown or Dispatch
// — those decisions, and the Chalan, belong to BuildCon on the Customer
// page (see app/(admin)/tiles/orders/[id].tsx). Nothing else happens here.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { tileOrdersApi, type PurchaseOrderDetail } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { StatusPill, WorkflowRail } from "@/src/components/tiles/TileOrderStatusUI";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

export default function BrandOrderDetailScreen() {
  useRequireFloorAccess("ground-floor");
  const { poId } = useLocalSearchParams<{ poId: string }>();
  const router = useRouter();
  const [order, setOrder] = useState<PurchaseOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [releaseQty, setReleaseQty] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);

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
        <Pressable testID="tile-brand-release-back" onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back</Text>
        </Pressable>
      </SafeAreaView>
    );
  }

  const anyPending = order.items.some((item) => item.boxes_pending > 0);
  const selectedItems = order.items.flatMap((item) => {
    const qty = Number(releaseQty[item.id] || 0);
    return selected[item.id] && qty > 0 && qty <= item.boxes_pending ? [{ po_item_id: item.id, qty }] : [];
  });
  const toggleItem = (itemId: string) => setSelected((current) => ({ ...current, [itemId]: !current[itemId] }));
  const setQuantity = (itemId: string, value: string) => {
    const digits = value.replace(/[^0-9]/g, "");
    setReleaseQty((current) => ({ ...current, [itemId]: digits }));
    if (Number(digits) > 0) setSelected((current) => ({ ...current, [itemId]: true }));
  };
  const releaseSelected = async () => {
    if (!selectedItems.length) return;
    setSubmitting(true);
    try {
      await tileOrdersApi.releaseMaterial(order.id, selectedItems);
      toast.success(`${selectedItems.length} product line${selectedItems.length === 1 ? "" : "s"} released`);
      setReleaseQty({});
      setSelected({});
      await load();
    } catch (e: any) {
      toast.error(e?.detail || "Could not release material");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Pressable testID="tile-brand-release-back" onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back to {order.brand_name || "Brand"}</Text>
        </Pressable>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <Text style={type.displayMd}>{order.customer_name}</Text>
          <StatusPill status={order.overall_status} />
        </View>
        <Text style={type.bodyMuted}>{order.number} · {order.brand_name || "Unassigned brand"}</Text>

        <WorkflowRail active={anyPending ? "release" : "released"} testID="tile-brand-workflow-rail" />
        <Text style={[type.bodyMuted, { marginTop: spacing.sm }]}>Select one or more product lines, enter the release quantity, then submit the batch.</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tableShell}><View style={styles.releaseTable}><View style={styles.tableHeader}><Text style={[styles.selectCol, styles.tableLabel]}>SELECT</Text><Text style={[styles.productCol, styles.tableLabel]}>PRODUCT</Text><Text style={[styles.qtyCol, styles.tableLabel]}>ORDERED</Text><Text style={[styles.qtyCol, styles.tableLabel]}>RELEASED</Text><Text style={[styles.qtyCol, styles.tableLabel]}>REMAINING</Text><Text style={[styles.inputCol, styles.tableLabel]}>RELEASE QTY</Text></View>{order.items.map((item) => { const selectable = item.boxes_pending > 0; return <View key={item.id} style={styles.tableRow}><Pressable testID={`tile-release-select-${item.id}`} disabled={!selectable} onPress={() => toggleItem(item.id)} style={[styles.checkbox, selected[item.id] ? styles.checkboxActive : null, !selectable ? styles.checkboxDisabled : null]}>{selected[item.id] ? <Feather name="check" size={13} color={colors.onBrand} /> : null}</Pressable><View style={styles.productCol}><Text numberOfLines={1} style={type.bodyStrong}>{item.name}</Text><Text numberOfLines={1} style={type.caption}>{[item.series, item.finish, item.size].filter(Boolean).join(" · ") || "—"}</Text></View><Text style={[styles.qtyCol, styles.mono]}>{item.qty}</Text><Text style={[styles.qtyCol, styles.mono]}>{item.boxes_ready}</Text><Text style={[styles.qtyCol, styles.mono]}>{item.boxes_pending}</Text><TextInput testID={`tile-release-quantity-${item.id}`} editable={selectable} value={releaseQty[item.id] || ""} onChangeText={(value) => setQuantity(item.id, value)} keyboardType="number-pad" placeholder={selectable ? `Max ${item.boxes_pending}` : "Complete"} placeholderTextColor={colors.onSurfaceSubtle} style={[styles.qtyInput, !selectable ? styles.qtyInputDisabled : null]} /></View>; })}</View></ScrollView>
      </ScrollView>
      {anyPending ? <View style={styles.stickyFooter}><Text style={styles.footerMeta}>{selectedItems.length} selected · {selectedItems.reduce((total, item) => total + item.qty, 0)} boxes</Text><Pressable testID="tile-release-selected" disabled={!selectedItems.length || submitting} onPress={releaseSelected} style={[styles.actionButton, !selectedItems.length || submitting ? styles.actionButtonDisabled : null]}><Text style={[type.bodyStrong, { color: colors.onBrand }]}>{submitting ? "Releasing…" : "Release Selected"}</Text></Pressable></View> : <View style={styles.stickyFooter}><Text style={styles.footerMeta}>All material has been released for this brand order.</Text></View>}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.md, paddingBottom: 86, width: "100%", alignSelf: "stretch" },
  backRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.md },
  tableShell: { marginTop: spacing.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  releaseTable: { minWidth: 900, width: "100%" },
  tableHeader: { flexDirection: "row", alignItems: "center", minHeight: 32, paddingHorizontal: spacing.sm, backgroundColor: colors.surfaceTertiary, borderBottomWidth: 1, borderColor: colors.border },
  tableRow: { flexDirection: "row", alignItems: "center", minHeight: 46, paddingHorizontal: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.divider, gap: spacing.xs },
  tableLabel: { ...type.overline, fontSize: 10, color: colors.onSurfaceMuted },
  selectCol: { width: 62, textAlign: "center" }, productCol: { width: 330 }, qtyCol: { width: 96, textAlign: "right" }, inputCol: { width: 150 },
  mono: { ...type.bodySm, fontFamily: type.numeric.fontFamily, fontVariant: ["tabular-nums"] },
  checkbox: { width: 24, height: 24, marginHorizontal: 19, borderWidth: 1, borderColor: colors.brandBorder, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  checkboxActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  checkboxDisabled: { borderColor: colors.border, backgroundColor: colors.surfaceTertiary },
  qtyInput: { width: 130, minHeight: 32, borderWidth: 1, borderColor: colors.brandBorder, borderRadius: radius.sm, paddingHorizontal: spacing.sm, paddingVertical: 4, fontFamily: type.numeric.fontFamily, textAlign: "right", color: colors.onSurface },
  qtyInputDisabled: { borderColor: colors.border, backgroundColor: colors.surfaceTertiary, color: colors.onSurfaceMuted },
  stickyFooter: { minHeight: 64, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md },
  footerMeta: { ...type.bodyMuted, flex: 1 },
  actionButton: { minHeight: 40, backgroundColor: colors.brand, borderRadius: radius.sm, paddingVertical: spacing.sm, paddingHorizontal: spacing.lg, alignItems: "center", justifyContent: "center" },
  actionButtonDisabled: { backgroundColor: colors.onSurfaceSubtle },
});
