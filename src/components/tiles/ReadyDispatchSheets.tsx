// frontend/src/components/tiles/ReadyDispatchSheets.tsx
// Bottom-sheet forms for the two Supplier order-detail actions. DispatchSheet
// does client-side allocation across existing Ready Batches (oldest first)
// before calling preview/commit, so staff enter a plain "dispatch N boxes"
// number per item instead of picking an internal batch ID — see Task 18.
import { useState } from "react";
import { Modal, Pressable, ScrollView, Text, TextInput, View } from "react-native";

import { tileOrdersApi, type DispatchLineInput, type DispatchPreview, type PurchaseOrderItemDetail } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

async function allocateDispatchLines(poId: string, entries: { po_item_id: string; qty: number }[]): Promise<DispatchLineInput[]> {
  const lines: DispatchLineInput[] = [];
  for (const entry of entries) {
    let remaining = entry.qty;
    const { batches } = await tileOrdersApi.itemReadyBatches(poId, entry.po_item_id);
    for (const batch of batches) {
      if (remaining <= 0) break;
      const take = Math.min(remaining, batch.remaining_qty);
      lines.push({ po_item_id: entry.po_item_id, ready_batch_id: batch.id, qty: take });
      remaining -= take;
    }
    if (remaining > 0) {
      lines.push({ po_item_id: entry.po_item_id, ready_batch_id: null, qty: remaining });
    }
  }
  return lines;
}

export function MarkReadySheet({ poId, items, onClose, onDone }: { poId: string; items: PurchaseOrderItemDetail[]; onClose: () => void; onDone: () => void }) {
  const [qtyByItem, setQtyByItem] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const entries = items
      .map((item) => ({ po_item_id: item.id, qty: Number(qtyByItem[item.id] || 0) }))
      .filter((e) => e.qty > 0);
    if (entries.length === 0) {
      toast.error("Enter at least one quantity");
      return;
    }
    setBusy(true);
    try {
      await tileOrdersApi.markItemsReady(poId, entries);
      toast.success("Marked ready");
      onDone();
    } catch (e: any) {
      toast.error(e?.detail || "Could not mark items ready");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: "flex-end" }}>
        <View style={{ backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.xl, maxHeight: "80%" }}>
          <Text style={type.titleMd}>Mark Ready For Pickup</Text>
          <ScrollView style={{ marginVertical: spacing.md }}>
            {items.filter((item) => item.boxes_pending > 0).map((item) => (
              <View key={item.id} style={{ marginBottom: spacing.md }}>
                <Text style={type.bodyStrong}>{item.name}</Text>
                <Text style={type.bodyMuted}>{item.boxes_pending} boxes pending</Text>
                <TextInput
                  keyboardType="numeric" placeholder="Qty ready"
                  value={qtyByItem[item.id] || ""} onChangeText={(v) => setQtyByItem((s) => ({ ...s, [item.id]: v }))}
                  style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.sm, marginTop: spacing.xs }}
                />
              </View>
            ))}
          </ScrollView>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Pressable onPress={onClose} style={{ flex: 1, padding: spacing.md, alignItems: "center", borderRadius: radius.md, borderWidth: 1, borderColor: colors.border }}>
              <Text style={type.bodyStrong}>Cancel</Text>
            </Pressable>
            <Pressable disabled={busy} onPress={submit} style={{ flex: 1, padding: spacing.md, alignItems: "center", borderRadius: radius.md, backgroundColor: colors.brand }}>
              <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Mark Ready</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

export function DispatchSheet({ poId, items, customerName, customerAddress, customerCity, onClose, onDone }: {
  poId: string; items: PurchaseOrderItemDetail[]; customerName: string; customerAddress: string; customerCity: string;
  onClose: () => void; onDone: () => void;
}) {
  const [qtyByItem, setQtyByItem] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<DispatchPreview | null>(null);
  const [busy, setBusy] = useState(false);

  const entries = () => items
    .map((item) => ({ po_item_id: item.id, qty: Number(qtyByItem[item.id] || 0) }))
    .filter((e) => e.qty > 0);

  const runPreview = async () => {
    const built = entries();
    if (built.length === 0) {
      toast.error("Enter at least one quantity to dispatch");
      return;
    }
    setBusy(true);
    try {
      const lines = await allocateDispatchLines(poId, built);
      const result = await tileOrdersApi.previewDispatch(poId, lines, {
        destination_type: "Customer", destination_name: customerName, destination_address: customerAddress, destination_city: customerCity,
      });
      setPreview(result);
    } catch (e: any) {
      toast.error(e?.detail || "Could not preview dispatch");
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    setBusy(true);
    try {
      const lines = await allocateDispatchLines(poId, entries());
      await tileOrdersApi.commitDispatch(poId, lines, {
        destination_type: "Customer", destination_name: customerName, destination_address: customerAddress, destination_city: customerCity,
      });
      toast.success("Dispatched — Chalan generated");
      onDone();
    } catch (e: any) {
      toast.error(e?.detail || "Could not dispatch");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: "flex-end" }}>
        <View style={{ backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.xl, maxHeight: "85%" }}>
          <Text style={type.titleMd}>Dispatch</Text>
          <ScrollView style={{ marginVertical: spacing.md }}>
            {!preview ? items.filter((item) => item.boxes_ready + item.boxes_pending > 0).map((item) => (
              <View key={item.id} style={{ marginBottom: spacing.md }}>
                <Text style={type.bodyStrong}>{item.name}</Text>
                <Text style={type.bodyMuted}>Ready {item.boxes_ready} · Pending {item.boxes_pending}</Text>
                <TextInput
                  keyboardType="numeric" placeholder="Dispatch today"
                  value={qtyByItem[item.id] || ""} onChangeText={(v) => setQtyByItem((s) => ({ ...s, [item.id]: v }))}
                  style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.sm, marginTop: spacing.xs }}
                />
              </View>
            )) : (
              <View>
                <Text style={type.bodyStrong}>Will create: Dispatch → Chalan → Dispatch List entry</Text>
                {preview.warnings.map((w, i) => <Text key={i} style={[type.bodyMuted, { color: colors.warningFg }]}>{w}</Text>)}
                {preview.items.map((line, i) => (
                  <Text key={`${line.po_item_id}-${i}`} style={type.bodySm}>{line.tile_name} · {line.qty} boxes · {line.remaining_pending_after} pending after</Text>
                ))}
              </View>
            )}
          </ScrollView>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Pressable onPress={onClose} style={{ flex: 1, padding: spacing.md, alignItems: "center", borderRadius: radius.md, borderWidth: 1, borderColor: colors.border }}>
              <Text style={type.bodyStrong}>Cancel</Text>
            </Pressable>
            {!preview ? (
              <Pressable disabled={busy} onPress={runPreview} style={{ flex: 1, padding: spacing.md, alignItems: "center", borderRadius: radius.md, backgroundColor: colors.brand }}>
                <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Preview</Text>
              </Pressable>
            ) : (
              <Pressable disabled={busy} onPress={confirm} style={{ flex: 1, padding: spacing.md, alignItems: "center", borderRadius: radius.md, backgroundColor: colors.brand }}>
                <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Confirm Dispatch</Text>
              </Pressable>
            )}
          </View>
        </View>
      </View>
    </Modal>
  );
}
