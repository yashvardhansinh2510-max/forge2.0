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
import { ActivityIndicator, Linking, Modal, Platform, Pressable, ScrollView, Text, TextInput, View, type ViewStyle } from "react-native";

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

function Sheet({ title, children, onClose, maxHeight = "80%" }: { title: string; children: React.ReactNode; onClose: () => void; maxHeight?: ViewStyle["maxHeight"] }) {
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
      <Pressable disabled={busy} onPress={onCancel} style={{ flex: 1, padding: spacing.md, alignItems: "center", borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, opacity: busy ? 0.5 : 1 }}>
        <Text style={type.bodyStrong}>Cancel</Text>
      </Pressable>
      <Pressable disabled={busy} onPress={onConfirm} style={{ flex: 1, flexDirection: "row", justifyContent: "center", alignItems: "center", gap: spacing.xs, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.brand, opacity: busy ? 0.85 : 1 }}>
        {busy ? <ActivityIndicator size="small" color={colors.onBrand} /> : null}
        <Text style={[type.bodyStrong, { color: colors.onBrand }]}>{busy ? "Processing…" : confirmLabel}</Text>
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

// Each sheet opens with the full available quantity already filled in —
// the common case is "move/dispatch everything that is available", and an
// empty field made every Confirm button reject the first tap with "Enter
// at least one quantity".
function prefill<T>(items: T[], id: (item: T) => string, max: (item: T) => number) {
  return Object.fromEntries(items.filter((item) => max(item) > 0).map((item) => [id(item), String(max(item))]));
}

function collectEntries(qtyByItem: Record<string, string>) {
  return Object.entries(qtyByItem)
    .map(([po_item_id, v]) => ({ po_item_id, qty: Number(v || 0) }))
    .filter((e) => e.qty > 0);
}

// ---------------------------------------------------------------- Brand page
export function ReleaseMaterialSheet({ poId, items, onClose, onDone }: { poId: string; items: PurchaseOrderItemDetail[]; onClose: () => void; onDone: () => void }) {
  const [qtyByItem, setQtyByItem] = useState<Record<string, string>>(
    () => prefill(items, (item) => item.id, (item) => item.boxes_pending),
  );
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
  const [qtyByItem, setQtyByItem] = useState<Record<string, string>>(
    () => prefill(items, (item) => item.po_item_id, (item) => item.boxes_ready),
  );
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

// Transport details a warehouse fills in at dispatch time. TileChalan has
// always had vehicle_number/driver_name columns (they print on the Chalan
// PDF and show on the Dispatch List) but nothing ever collected them, so
// both rendered permanently blank.
export type TransportDetails = { vehicle_number: string; driver_name: string; receiver_name: string; reference_number: string };
const EMPTY_TRANSPORT: TransportDetails = { vehicle_number: "", driver_name: "", receiver_name: "", reference_number: "" };

function TransportFields({ value, onChange }: { value: TransportDetails; onChange: (next: TransportDetails) => void }) {
  const field = (key: keyof TransportDetails, label: string, placeholder: string) => (
    <View style={{ flex: 1, minWidth: 150 }}>
      <Text style={type.caption}>{label}</Text>
      <TextInput
        testID={`tile-dispatch-${key.replace(/_/g, "-")}`}
        value={value[key]} onChangeText={(v) => onChange({ ...value, [key]: v })} placeholder={placeholder}
        placeholderTextColor={colors.onSurfaceSubtle}
        style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.sm, marginTop: 2 }}
      />
    </View>
  );
  return (
    <View style={{ gap: spacing.sm, marginBottom: spacing.md }}>
      <Text style={type.bodyStrong}>Transport details</Text>
      <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
        {field("vehicle_number", "Vehicle number", "GJ-01-AB-1234")}
        {field("driver_name", "Driver name", "Driver")}
      </View>
      <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
        {field("receiver_name", "Received by", "Site contact")}
        {field("reference_number", "Reference no.", "Optional")}
      </View>
    </View>
  );
}

function transportPayload(t: TransportDetails) {
  return Object.fromEntries(Object.entries(t).filter(([, v]) => v.trim() !== ""));
}

async function submitDispatch(
  poId: string, entries: { po_item_id: string; qty: number }[],
  fn: (poId: string, entries: { po_item_id: string; qty: number }[]) => Promise<{ chalan: { id: string; [key: string]: any } }>,
  onDone: () => void, setBusy: (b: boolean) => void,
) {
  setBusy(true);
  let result: { chalan: { id: string; [key: string]: any } };
  try {
    result = await fn(poId, entries);
  } catch (e: any) {
    toast.error(e?.detail || "Could not dispatch");
    setBusy(false);
    return;
  }
  // Dispatch + Chalan are already committed server-side at this point —
  // anything below (minting a download token, opening the PDF) is a
  // best-effort convenience. A failure here must never surface as "Could
  // not dispatch" (that already succeeded); it only affects whether the
  // PDF opens automatically.
  toast.success("Dispatched — Chalan generated");
  onDone();
  setBusy(false);
  try {
    const url = await tileOrdersApi.chalanPdfUrl(result.chalan.id);
    await openPdf(url);
  } catch {
    toast.error("Dispatch saved. Open the Chalan PDF from the Dispatch List tab.");
  }
}

function DispatchSheet({
  title, poId, items, available, dispatch, onClose, onDone,
}: {
  title: string; poId: string; items: CustomerOrderItem[];
  available: (item: CustomerOrderItem) => number;
  dispatch: (poId: string, entries: { po_item_id: string; qty: number }[], destination: Record<string, string>) => Promise<{ chalan: { id: string; [key: string]: any } }>;
  onClose: () => void; onDone: () => void;
}) {
  const [qtyByItem, setQtyByItem] = useState<Record<string, string>>(
    () => prefill(items, (item) => item.po_item_id, available),
  );
  const [transport, setTransport] = useState<TransportDetails>(EMPTY_TRANSPORT);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const entries = collectEntries(qtyByItem);
    if (entries.length === 0) {
      toast.error("Enter at least one quantity");
      return;
    }
    await submitDispatch(poId, entries, (id, e) => dispatch(id, e, transportPayload(transport)), onDone, setBusy);
  };

  return (
    <Sheet title={title} onClose={onClose}>
      <ScrollView style={{ marginVertical: spacing.md }}>
        {items.filter((item) => available(item) > 0).map((item) => (
          <QtyRow
            key={item.po_item_id} name={item.tile_name} hint={`${available(item)} boxes available`}
            value={qtyByItem[item.po_item_id] || ""} onChange={(v) => setQtyByItem((s) => ({ ...s, [item.po_item_id]: v }))}
          />
        ))}
        <TransportFields value={transport} onChange={setTransport} />
      </ScrollView>
      <Text style={[type.bodyMuted, { marginBottom: spacing.sm }]}>Creates a Dispatch, generates a Chalan, and opens the PDF.</Text>
      <SheetFooter onCancel={onClose} onConfirm={submit} confirmLabel="Confirm Dispatch" busy={busy} />
    </Sheet>
  );
}

export function DispatchFromReleasedSheet({ poId, items, onClose, onDone }: { poId: string; items: CustomerOrderItem[]; onClose: () => void; onDone: () => void }) {
  return (
    <DispatchSheet
      title="Dispatch from Released" poId={poId} items={items} available={(item) => item.boxes_ready}
      dispatch={(id, entries, destination) => tileOrdersApi.dispatchFromReleased(id, entries, destination)}
      onClose={onClose} onDone={onDone}
    />
  );
}

export function DispatchFromGodownSheet({ poId, items, onClose, onDone }: { poId: string; items: CustomerOrderItem[]; onClose: () => void; onDone: () => void }) {
  return (
    <DispatchSheet
      title="Dispatch from Godown" poId={poId} items={items} available={(item) => item.boxes_godown}
      dispatch={(id, entries, destination) => tileOrdersApi.dispatchFromGodown(id, entries, destination)}
      onClose={onClose} onDone={onDone}
    />
  );
}
