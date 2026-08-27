// frontend/src/components/tiles/CreateDispatchSheet.tsx
// "Create dispatch" straight from the Dispatch List — the tab used to be
// history-only, so raising a dispatch meant knowing to go find the right
// customer order first. Three steps, all inside one sheet:
//
//   1. pick the customer order        (only orders with dispatchable stock)
//   2. pick the brand + source pool   (Released or Godown)
//   3. enter quantity per line + transport details -> Confirm
//
// Confirm calls the exact same backend actions the Customer workspace
// uses (dispatch-from-released / dispatch-from-godown), so a dispatch
// raised here is identical in every way — Chalan, Register row, timeline.
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import {
  tileOrdersApi,
  type CustomerOrderBrandGroup, type CustomerOrderCard, type CustomerOrderDetail,
} from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { Sheet } from "@/src/components/ui";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

type Source = "released" | "godown";

const available = (item: { boxes_ready: number; boxes_godown: number }, source: Source) =>
  source === "released" ? item.boxes_ready : item.boxes_godown;

const qtyUnit = (item: { quantity_unit?: string }) => item.quantity_unit === "Pieces" ? "pieces" : "boxes";

export function CreateDispatchSheet({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [orders, setOrders] = useState<CustomerOrderCard[] | null>(null);
  const [detail, setDetail] = useState<CustomerOrderDetail | null>(null);
  const [group, setGroup] = useState<CustomerOrderBrandGroup | null>(null);
  const [source, setSource] = useState<Source>("released");
  const [qty, setQty] = useState<Record<string, string>>({});
  const [transport, setTransport] = useState({ vehicle_number: "", driver_name: "", receiver_name: "", reference_number: "", labor_cost: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    tileOrdersApi.listCustomerOrders({ page_size: 100 })
      .then((r) => setOrders(r.orders))
      .catch((e: any) => setError(e?.detail || "Could not load orders"));
  }, []);

  const openOrder = useCallback(async (orderId: string) => {
    setBusy(true);
    try {
      setDetail(await tileOrdersApi.customerOrderDetail(orderId));
    } catch (e: any) {
      toast.error(e?.detail || "Could not load order");
    } finally {
      setBusy(false);
    }
  }, []);

  // A group is only worth offering if it actually has stock sitting in one
  // of the two dispatchable pools — otherwise the operator picks it and
  // finds an empty form.
  const dispatchableGroups = useMemo(
    () => (detail?.suppliers || []).filter((g) => g.items.some((i) => i.boxes_ready > 0 || i.boxes_godown > 0)),
    [detail],
  );

  const lines = useMemo(
    () => (group?.items || []).filter((item) => available(item, source) > 0),
    [group, source],
  );

  const chooseGroup = (next: CustomerOrderBrandGroup) => {
    const preferred: Source = next.items.some((i) => i.boxes_ready > 0) ? "released" : "godown";
    setGroup(next);
    setSource(preferred);
    setQty(Object.fromEntries(
      next.items.filter((i) => available(i, preferred) > 0).map((i) => [i.po_item_id, String(available(i, preferred))]),
    ));
  };

  const switchSource = (next: Source) => {
    setSource(next);
    setQty(Object.fromEntries(
      (group?.items || []).filter((i) => available(i, next) > 0).map((i) => [i.po_item_id, String(available(i, next))]),
    ));
  };

  const confirm = async () => {
    if (!group) return;
    const entries = Object.entries(qty)
      .map(([po_item_id, value]) => ({ po_item_id, qty: Number(value || 0) }))
      .filter((e) => e.qty > 0);
    if (entries.length === 0) {
      toast.error("Enter at least one quantity");
      return;
    }
    const laborCost = Number(transport.labor_cost || 0);
    if (!Number.isFinite(laborCost) || laborCost < 0) {
      toast.error("Enter a valid labour cost");
      return;
    }
    const destination = {
      ...Object.fromEntries(Object.entries(transport).filter(([key, value]) => key !== "labor_cost" && value.trim() !== "")),
      ...(laborCost > 0 ? { labor_cost: laborCost } : {}),
    };
    setBusy(true);
    let chalanId: string | null = null;
    try {
      const call = source === "released" ? tileOrdersApi.dispatchFromReleased : tileOrdersApi.dispatchFromGodown;
      const result = await call(group.purchase_order_id, entries, destination);
      chalanId = result.chalan?.id ?? null;
    } catch (e: any) {
      toast.error(e?.detail || "Could not create dispatch");
      setBusy(false);
      return;
    }
    // Dispatch + Chalan are committed at this point; opening the PDF is a
    // convenience that must never report the dispatch itself as failed.
    toast.success("Dispatch created — Chalan generated");
    setBusy(false);
    onCreated();
    onClose();
    if (chalanId) {
      try {
        const url = await tileOrdersApi.chalanPdfUrl(chalanId);
        if (Platform.OS === "web") {
          // @ts-ignore — web only
          window.open(url, "_blank");
        } else {
          await Linking.openURL(url);
        }
      } catch {
        toast.error("Dispatch saved. Open the Chalan from the Dispatch List.");
      }
    }
  };

  const subtitle = !detail ? "Step 1 of 3 · choose the customer order"
    : !group ? "Step 2 of 3 · choose the brand and stock pool"
      : "Step 3 of 3 · quantities and transport";

  return (
    <Sheet visible onClose={onClose} title="Create dispatch" subtitle={subtitle} testID="tile-create-dispatch-sheet">
      <ScrollView contentContainerStyle={styles.body}>
        {error ? <Text style={type.bodyStrong}>{error}</Text> : null}

        {!detail ? (
          orders === null ? <ActivityIndicator color={colors.brand} /> : orders.length === 0 ? (
            <Text style={type.bodyMuted}>No tile orders yet.</Text>
          ) : orders.map((order) => (
            <Pressable
              testID={`tile-create-dispatch-order-${order.id}`} key={order.id}
              onPress={() => openOrder(order.id)} style={styles.pickRow}
            >
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text numberOfLines={1} style={type.bodyStrong}>{order.customer_name}</Text>
                <Text style={type.caption}>{order.number} · {order.brands.map((b) => b.brand_name).join(", ")}</Text>
              </View>
              <Text style={styles.pickAction}>Select →</Text>
            </Pressable>
          ))
        ) : !group ? (
          <>
            <Pressable testID="tile-create-dispatch-back-orders" onPress={() => setDetail(null)} style={styles.linkRow}>
              <Text style={styles.pickAction}>← Choose a different order</Text>
            </Pressable>
            <Text style={type.bodyStrong}>{detail.summary.customer_name} · {detail.summary.number}</Text>
            {dispatchableGroups.length === 0 ? (
              <Text style={type.bodyMuted}>
                Nothing is available to dispatch on this order yet — the brand has to release material first
                (Tile Orders → Brands → Release queue).
              </Text>
            ) : dispatchableGroups.map((candidate) => (
              <Pressable
                testID={`tile-create-dispatch-group-${candidate.purchase_order_id}`} key={candidate.purchase_order_id}
                onPress={() => chooseGroup(candidate)} style={styles.pickRow}
              >
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={type.bodyStrong}>{candidate.brand_name}</Text>
                  <Text style={type.caption}>
                    {candidate.items.reduce((t, i) => t + i.boxes_ready, 0)} released ·{" "}
                    {candidate.items.reduce((t, i) => t + i.boxes_godown, 0)} at Godown
                  </Text>
                </View>
                <Text style={styles.pickAction}>Select →</Text>
              </Pressable>
            ))}
          </>
        ) : (
          <>
            <Pressable testID="tile-create-dispatch-back-groups" onPress={() => setGroup(null)} style={styles.linkRow}>
              <Text style={styles.pickAction}>← Choose a different brand</Text>
            </Pressable>
            <Text style={type.bodyStrong}>{detail.summary.customer_name} · {group.brand_name}</Text>
            <View style={styles.sourceRow}>
              {(["released", "godown"] as Source[]).map((option) => {
                const total = group.items.reduce((t, i) => t + available(i, option), 0);
                return (
                  <Pressable
                    testID={`tile-create-dispatch-source-${option}`} key={option} disabled={total <= 0}
                    onPress={() => switchSource(option)}
                    style={[styles.chip, source === option ? styles.chipActive : null, total <= 0 ? styles.chipDisabled : null]}
                  >
                    <Text style={[type.captionStrong, source === option ? { color: colors.brandHover } : null]}>
                      {option === "released" ? "From Released" : "From Godown"} · {total}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            {lines.length === 0 ? (
              <Text style={type.bodyMuted}>No quantity in this pool. Switch pool above.</Text>
            ) : lines.map((item) => (
              <View key={item.po_item_id} style={{ marginBottom: spacing.sm }}>
                <Text style={type.bodyStrong}>{item.tile_name}</Text>
                <Text style={type.bodyMuted}>{available(item, source)} {qtyUnit(item)} available</Text>
                <TextInput
                  testID={`tile-create-dispatch-qty-${item.po_item_id}`} keyboardType="number-pad"
                  value={qty[item.po_item_id] || ""}
                  onChangeText={(v) => setQty((s) => ({ ...s, [item.po_item_id]: v.replace(/[^0-9.]/g, "") }))}
                  placeholder={qtyUnit(item)} placeholderTextColor={colors.onSurfaceSubtle} style={styles.input}
                />
              </View>
            ))}
            <Text style={[type.bodyStrong, { marginTop: spacing.xs }]}>Transport details</Text>
            {([ 
              ["vehicle_number", "Vehicle number"], ["driver_name", "Driver name"],
              ["receiver_name", "Received by"], ["reference_number", "Reference no."],
            ] as const).map(([key, label]) => (
              <TextInput
                testID={`tile-create-dispatch-${key.replace(/_/g, "-")}`} key={key}
                value={transport[key]} onChangeText={(v) => setTransport((t) => ({ ...t, [key]: v }))}
                placeholder={label} placeholderTextColor={colors.onSurfaceSubtle} style={styles.input}
              />
            ))}
            <TextInput
              testID="tile-create-dispatch-labor-cost" keyboardType="decimal-pad"
              value={transport.labor_cost} onChangeText={(v) => setTransport((t) => ({ ...t, labor_cost: v.replace(/[^0-9.]/g, "") }))}
              placeholder="Labour cost (added to payment)" placeholderTextColor={colors.onSurfaceSubtle} style={styles.input}
            />
            <View style={styles.actionRow}>
              <Pressable
                testID="tile-create-dispatch-confirm" disabled={busy || lines.length === 0}
                onPress={confirm} style={[styles.primaryAction, busy || lines.length === 0 ? styles.disabled : null]}
              >
                <Text style={styles.primaryActionText}>{busy ? "Creating…" : "Create Dispatch + Chalan"}</Text>
              </Pressable>
              <Pressable testID="tile-create-dispatch-cancel" onPress={onClose} style={styles.outlineAction}>
                <Text style={styles.outlineActionText}>Cancel</Text>
              </Pressable>
            </View>
          </>
        )}
      </ScrollView>
    </Sheet>
  );
}

const styles = StyleSheet.create({
  body: { padding: spacing.lg, gap: spacing.xs },
  pickRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 52,
    paddingHorizontal: spacing.md, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary, marginBottom: spacing.xs,
  },
  linkRow: { minHeight: 36, justifyContent: "center" },
  pickAction: { ...type.captionStrong, color: colors.brand },
  sourceRow: { flexDirection: "row", gap: spacing.xs, marginVertical: spacing.sm, flexWrap: "wrap" },
  chip: {
    minHeight: 36, justifyContent: "center", paddingHorizontal: spacing.md, borderRadius: radius.sm,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  chipActive: { backgroundColor: colors.brandTint, borderColor: colors.brandBorder },
  chipDisabled: { opacity: 0.45 },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.sm, minHeight: 42, marginTop: 4, color: colors.onSurface },
  actionRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, marginTop: spacing.md },
  primaryAction: { minHeight: 44, justifyContent: "center", paddingHorizontal: spacing.lg, borderRadius: radius.sm, backgroundColor: colors.brand },
  primaryActionText: { ...type.bodyStrong, color: colors.onBrand },
  outlineAction: { minHeight: 44, justifyContent: "center", paddingHorizontal: spacing.lg, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.brandBorder },
  outlineActionText: { ...type.bodyStrong, color: colors.brandHover },
  disabled: { opacity: 0.6 },
});
