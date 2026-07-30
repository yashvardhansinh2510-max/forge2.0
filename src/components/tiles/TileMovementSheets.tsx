// frontend/src/components/tiles/TileMovementSheets.tsx
// Bottom-sheet forms for every Tile Orders movement action, split by page
// ownership (Tile Orders workflow redesign, 2026-08):
//   - ReleaseMaterialSheet  — Brand page's ONLY action. Never touches
//     Godown/Dispatch/Chalan; it's purely "the brand gave BuildCon N boxes".
//   - MoveToGodownSheet     — Customer page. Released -> Godown. No Chalan.
//   - DispatchFromReleasedSheet / DispatchFromGodownSheet — Customer page.
//     Always create a Dispatch + Chalan and auto-open the PDF.
// Replaces src/components/tiles/ReadyDispatchSheets.tsx (MarkReadySheet /
// DispatchSheet), which conflated all of this into one Brand-owned action.
import { useState } from "react";
import { Linking, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";

import { tileOrdersApi, type CustomerOrderItem, type PurchaseOrderItemDetail } from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

async function openPdf(url: string) {
  if (Platform.OS === "web") {
    // @ts-ignore — web only
    window.open(url, "_blank");
  } else {
    await Linking.openURL(url);
  }
}

function Sheet({ title, children, onClose, maxHeight = "80%" }: { title: string; children: React.ReactNode; onClose: () => void; maxHeight?: string }) {
  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: "flex-end" }}>
        <View style={{ backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.xl, maxHeight }}>
          <Text style={type.titleMd}>{title}</Text>
          {children}
        </View>
      </View>
    </Modal>
  );
}

function SheetFooter({ onCancel, onConfirm, confirmLabel, busy }: { onCancel: () => void; onConfirm: () => void; confirmLabel: string; busy: boolean }) {
  return (
    <View style={{ flexDirection: "row", gap: spacing.sm }}>
      <Pressable onPress={onCancel} style={{ flex: 1, padding: spacing.md, alignItems: "center", borderRadius: radius.md, borderWidth: 1, borderColor: colors.border }}>
        <Text style={type.bodyStrong}>Cancel</Text>
      </Pressable>
      <Pressable disabled={busy} onPress={onConfirm} style={{ flex: 1, padding: spacing.md, alignItems: "center", borderRadius: radius.md, backgroundColor: colors.brand, opacity: busy ? 0.6 : 1 }}>
        <Text style={[type.bodyStrong, { color: colors.onBrand }]}>{confirmLabel}</Text>
      </Pressable>
    </View>
  );
}

function QtyRow({ name, hint, value, onChange }: { name: string; hint: string; value: string; onChange: (v: string) => void }) {
  return (
    <View style={{ marginBottom: spacing.md }}>
      <Text style={type.bodyStrong}>{name}</Text>
      <Text style={type.bodyMuted}>{hint}</Text>
      <TextInput
        keyboardType="numeric" placeholder="Boxes"
        value={value} onChangeText={onChange}
        style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.sm, marginTop: spacing.xs }}
      />
    </View>
  );
}

function collectEntries(qtyByItem: Record<string, string>) {
  return Object.entries(qtyByItem)
    .map(([po_item_id, v]) => ({ po_item_id, qty: Number(v || 0) }))
    .filter((e) => e.qty > 0);
}

// ---------------------------------------------------------------- Brand page
export function ReleaseMaterialSheet({ poId, items, onClose, onDone }: { poId: string; items: PurchaseOrderItemDetail[]; onClose: () => void; onDone: () => void }) {
  const [qtyByItem, setQtyByItem] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const entries = collectEntries(qtyByItem);
    if (entries.length === 0) {
      toast.error("Enter at least one quantity");
      return;
    }
    setBusy(true);
    try {
      await tileOrdersApi.releaseMaterial(poId, entries);
      toast.success("Material released");
      onDone();
    } catch (e: any) {
      toast.error(e?.detail || "Could not release material");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet title="Release Material" onClose={onClose}>
      <ScrollView style={{ marginVertical: spacing.md }}>
        {items.filter((item) => item.boxes_pending > 0).map((item) => (
          <QtyRow
            key={item.id} name={item.name} hint={`${item.boxes_pending} boxes remaining`}
            value={qtyByItem[item.id] || ""} onChange={(v) => setQtyByItem((s) => ({ ...s, [item.id]: v }))}
          />
        ))}
      </ScrollView>
      <SheetFooter onCancel={onClose} onConfirm={submit} confirmLabel="Confirm Release" busy={busy} />
    </Sheet>
  );
}

// ------------------------------------------------------------- Customer page
export function MoveToGodownSheet({ poId, items, onClose, onDone }: { poId: string; items: CustomerOrderItem[]; onClose: () => void; onDone: () => void }) {
  const [qtyByItem, setQtyByItem] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const entries = collectEntries(qtyByItem);
    if (entries.length === 0) {
      toast.error("Enter at least one quantity");
      return;
    }
    setBusy(true);
    try {
      await tileOrdersApi.moveToGodown(poId, entries);
      toast.success("Moved to Godown");
      onDone();
    } catch (e: any) {
      toast.error(e?.detail || "Could not move to Godown");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet title="Move to Godown" onClose={onClose}>
      <ScrollView style={{ marginVertical: spacing.md }}>
        {items.filter((item) => item.boxes_ready > 0).map((item) => (
          <QtyRow
            key={item.po_item_id} name={item.tile_name} hint={`${item.boxes_ready} boxes Released`}
            value={qtyByItem[item.po_item_id] || ""} onChange={(v) => setQtyByItem((s) => ({ ...s, [item.po_item_id]: v }))}
          />
        ))}
      </ScrollView>
      <SheetFooter onCancel={onClose} onConfirm={submit} confirmLabel="Confirm Move" busy={busy} />
    </Sheet>
  );
}

async function submitDispatch(
  poId: string, entries: { po_item_id: string; qty: number }[],
  fn: (poId: string, entries: { po_item_id: string; qty: number }[]) => Promise<{ chalan: { id: string } }>,
  onDone: () => void, setBusy: (b: boolean) => void,
) {
  setBusy(true);
  try {
    const result = await fn(poId, entries);
    toast.success("Dispatched — Chalan generated");
    onDone();
    const url = await tileOrdersApi.chalanPdfUrl(result.chalan.id);
    await openPdf(url);
  } catch (e: any) {
    toast.error(e?.detail || "Could not dispatch");
  } finally {
    setBusy(false);
  }
}

export function DispatchFromReleasedSheet({ poId, items, onClose, onDone }: { poId: string; items: CustomerOrderItem[]; onClose: () => void; onDone: () => void }) {
  const [qtyByItem, setQtyByItem] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const entries = collectEntries(qtyByItem);
    if (entries.length === 0) {
      toast.error("Enter at least one quantity");
      return;
    }
    await submitDispatch(poId, entries, (id, e) => tileOrdersApi.dispatchFromReleased(id, e), onDone, setBusy);
  };

  return (
    <Sheet title="Dispatch from Released" onClose={onClose}>
      <ScrollView style={{ marginVertical: spacing.md }}>
        {items.filter((item) => item.boxes_ready > 0).map((item) => (
          <QtyRow
            key={item.po_item_id} name={item.tile_name} hint={`${item.boxes_ready} boxes Released`}
            value={qtyByItem[item.po_item_id] || ""} onChange={(v) => setQtyByItem((s) => ({ ...s, [item.po_item_id]: v }))}
          />
        ))}
      </ScrollView>
      <Text style={[type.bodyMuted, { marginBottom: spacing.sm }]}>Creates a Dispatch, generates a Chalan, and opens the PDF.</Text>
      <SheetFooter onCancel={onClose} onConfirm={submit} confirmLabel="Confirm Dispatch" busy={busy} />
    </Sheet>
  );
}

export function DispatchFromGodownSheet({ poId, items, onClose, onDone }: { poId: string; items: CustomerOrderItem[]; onClose: () => void; onDone: () => void }) {
  const [qtyByItem, setQtyByItem] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const entries = collectEntries(qtyByItem);
    if (entries.length === 0) {
      toast.error("Enter at least one quantity");
      return;
    }
    await submitDispatch(poId, entries, (id, e) => tileOrdersApi.dispatchFromGodown(id, e), onDone, setBusy);
  };

  return (
    <Sheet title="Dispatch from Godown" onClose={onClose}>
      <ScrollView style={{ marginVertical: spacing.md }}>
        {items.filter((item) => item.boxes_godown > 0).map((item) => (
          <QtyRow
            key={item.po_item_id} name={item.tile_name} hint={`${item.boxes_godown} boxes at Godown`}
            value={qtyByItem[item.po_item_id] || ""} onChange={(v) => setQtyByItem((s) => ({ ...s, [item.po_item_id]: v }))}
          />
        ))}
      </ScrollView>
      <Text style={[type.bodyMuted, { marginBottom: spacing.sm }]}>Creates a Dispatch, generates a Chalan, and opens the PDF.</Text>
      <SheetFooter onCancel={onClose} onConfirm={submit} confirmLabel="Confirm Dispatch" busy={busy} />
    </Sheet>
  );
}
