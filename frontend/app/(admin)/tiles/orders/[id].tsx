// Ground Floor → Tiles → Orders → detail — full chalan-by-chalan breakdown
// of a single order, the Release Material action, and Godown/Dispatch
// actions per chalan. Reads/writes the same PurchaseOrder the Customer-wise
// and Company-wise list views show — no separate copy.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { ChalanFormSheet } from "@/src/components/tiles/ChalanFormSheet";
import { StageProgress, stageLabel, type OrderStage } from "@/src/components/tiles/TileOrderCard";
import { colors, radius, spacing, type } from "@/src/theme/tokens";
import { downloadApiFile } from "@/src/utils/downloadFile";

type ChalanStage = "released" | "at_godown" | "dispatched";

type ChalanLine = { po_item_id: string; name: string; size?: string | null; qty: number; unit: string };

type Chalan = {
  id: string; number: string; created_at: string; items: ChalanLine[];
  reference_number?: string | null; receiver_name?: string | null; sender_name?: string | null;
  stage: ChalanStage; dispatch_note?: string | null;
};

type PoItem = { id: string; name: string; finish?: string | null; qty: number };

type OrderDetail = {
  id: string; number: string; customer_name: string; customer_phone?: string | null;
  supplier_name?: string | null; status: string; stage: OrderStage;
  items: PoItem[]; chalans: Chalan[]; remaining_qty_by_item: Record<string, number>;
};

const CHALAN_STAGE_LABEL: Record<ChalanStage, string> = {
  released: "Released", at_godown: "At Godown", dispatched: "Dispatched",
};

export default function TileOrderDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showChalanForm, setShowChalanForm] = useState(false);
  const [busyChalanId, setBusyChalanId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setLoadError(null);
    try {
      const r = await api.get<OrderDetail>(`/purchases/${id}/order-detail`);
      setOrder(r);
    } catch (e: any) {
      const message = e?.detail || "Could not load order";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const markGodown = async (chalanId: string) => {
    if (!id) return;
    setBusyChalanId(chalanId);
    try {
      await api.post(`/purchases/${id}/chalans/${chalanId}/godown-received`);
      toast.success("Marked received at Godown");
      await load();
    } catch (e: any) {
      toast.error(e?.detail || "Could not update chalan");
    } finally {
      setBusyChalanId(null);
    }
  };

  const dispatch = async (chalanId: string) => {
    if (!id) return;
    setBusyChalanId(chalanId);
    try {
      await api.post(`/purchases/${id}/chalans/${chalanId}/dispatch`, {});
      toast.success("Marked dispatched");
      await load();
    } catch (e: any) {
      toast.error(e?.detail || "Could not update chalan");
    } finally {
      setBusyChalanId(null);
    }
  };

  const downloadChalanPdf = async (chalan: Chalan) => {
    if (!id || !order) return;
    const stamp = new Date(chalan.created_at);
    const dd = String(stamp.getDate()).padStart(2, "0");
    const mm = String(stamp.getMonth() + 1).padStart(2, "0");
    const filename = `${chalan.number} ${order.customer_name} ${dd}-${mm}-${stamp.getFullYear()}.pdf`;
    await downloadApiFile(`/purchases/${id}/chalans/${chalan.id}/pdf`, filename, "chalan");
  };

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

  const hasRemaining = Object.values(order.remaining_qty_by_item).some((qty) => qty > 0);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Pressable onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back to Tile Orders</Text>
        </Pressable>

        <Text style={type.overline}>{order.number}</Text>
        <Text style={type.displayMd}>{order.customer_name}</Text>
        <Text style={type.bodyMuted}>
          {order.supplier_name || "No supplier assigned"} · {order.customer_phone || "No phone on file"}
        </Text>

        <View style={{ marginVertical: spacing.lg, gap: spacing.xs }}>
          <StageProgress stage={order.stage} />
          <Text style={[type.captionStrong, { color: colors.brandHover }]}>{stageLabel(order.stage)}</Text>
        </View>

        {hasRemaining ? (
          <Pressable style={styles.primaryButton} onPress={() => setShowChalanForm(true)}>
            <Feather name="file-text" size={16} color={colors.onBrand} />
            <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Release Material — Generate Chalan</Text>
          </Pressable>
        ) : null}

        <Text style={[type.titleMd, { marginTop: spacing.xl }]}>Chalans</Text>
        {order.chalans.length === 0 ? (
          <Text style={[type.bodyMuted, { marginTop: spacing.sm }]}>No material released yet.</Text>
        ) : (
          order.chalans.map((chalan) => (
            <View key={chalan.id} style={styles.chalanCard}>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={type.bodyStrong}>{chalan.number}</Text>
                <Text style={type.captionStrong}>{CHALAN_STAGE_LABEL[chalan.stage]}</Text>
              </View>
              {chalan.items.map((line) => (
                <Text key={line.po_item_id} style={type.bodySm}>
                  {line.name} {line.size ? `· ${line.size}` : ""} · {line.qty} {line.unit}
                </Text>
              ))}
              <View style={styles.chalanActions}>
                <Pressable style={styles.secondaryButton} onPress={() => downloadChalanPdf(chalan)}>
                  <Feather name="download" size={14} color={colors.onSurface} />
                  <Text style={type.bodySm}>PDF</Text>
                </Pressable>
                {chalan.stage === "released" ? (
                  <Pressable
                    style={styles.secondaryButton}
                    disabled={busyChalanId === chalan.id}
                    onPress={() => markGodown(chalan.id)}
                  >
                    <Text style={type.bodySm}>Material Received at Godown</Text>
                  </Pressable>
                ) : null}
                {chalan.stage !== "dispatched" ? (
                  <Pressable
                    style={styles.secondaryButton}
                    disabled={busyChalanId === chalan.id}
                    onPress={() => dispatch(chalan.id)}
                  >
                    <Text style={type.bodySm}>Dispatch</Text>
                  </Pressable>
                ) : null}
              </View>
            </View>
          ))
        )}
      </ScrollView>

      {showChalanForm ? (
        <ChalanFormSheet
          poId={order.id}
          items={order.items}
          remainingQtyByItem={order.remaining_qty_by_item}
          onClose={() => setShowChalanForm(false)}
          onGenerated={async () => {
            setShowChalanForm(false);
            await load();
          }}
        />
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.xl, width: "100%", maxWidth: 760, alignSelf: "center" },
  backRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.md },
  primaryButton: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md,
  },
  secondaryButton: {
    flexDirection: "row", alignItems: "center", gap: spacing.xs,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingVertical: spacing.xs, paddingHorizontal: spacing.sm,
  },
  chalanCard: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1,
    borderColor: colors.border, padding: spacing.lg, marginTop: spacing.sm, gap: spacing.xs,
  },
  chalanActions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm, flexWrap: "wrap" },
});
