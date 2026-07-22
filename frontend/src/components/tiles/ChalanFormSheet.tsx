// Release Material → Generate Chalan form. Pre-fills each item's remaining
// unreleased quantity as the default — staff can adjust down for a partial
// batch release (multiple chalans can cover one order over time).
import { useState } from "react";
import { Modal, Pressable, ScrollView, Text, TextInput, View } from "react-native";

import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

type PoItem = { id: string; name: string; finish?: string | null; qty: number };

export function ChalanFormSheet({
  poId, items, remainingQtyByItem, onClose, onGenerated,
}: {
  poId: string;
  items: PoItem[];
  remainingQtyByItem: Record<string, number>;
  onClose: () => void;
  onGenerated: () => void;
}) {
  const releasable = items.filter((item) => (remainingQtyByItem[item.id] || 0) > 0);
  const [qtyById, setQtyById] = useState<Record<string, string>>(
    Object.fromEntries(releasable.map((item) => [item.id, String(remainingQtyByItem[item.id] || 0)])),
  );
  const [referenceNumber, setReferenceNumber] = useState("");
  const [receiverName, setReceiverName] = useState("");
  const [senderName, setSenderName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    const body = {
      items: releasable
        .map((item) => ({ po_item_id: item.id, qty: Number(qtyById[item.id] || 0) }))
        .filter((entry) => entry.qty > 0),
      reference_number: referenceNumber || null,
      receiver_name: receiverName || null,
      sender_name: senderName || null,
    };
    if (body.items.length === 0) {
      toast.error("Enter a quantity for at least one item");
      return;
    }
    setSubmitting(true);
    try {
      await api.post(`/purchases/${poId}/chalans`, body);
      toast.success("Chalan generated");
      onGenerated();
    } catch (e: any) {
      toast.error(e?.detail || "Could not generate chalan");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: "flex-end" }}>
        <View style={{
          backgroundColor: colors.surfaceSecondary, borderTopLeftRadius: radius.xl,
          borderTopRightRadius: radius.xl, maxHeight: "85%", padding: spacing.xl,
        }}>
          <Text style={type.titleLg}>Release Material</Text>
          <Text style={[type.bodyMuted, { marginBottom: spacing.md }]}>
            Generates a Chalan for the quantities below.
          </Text>
          <ScrollView style={{ maxHeight: 320 }}>
            {releasable.map((item) => (
              <View key={item.id} style={{ marginBottom: spacing.md }}>
                <Text style={type.bodyStrong}>{item.name}{item.finish ? ` · ${item.finish}` : ""}</Text>
                <Text style={type.caption}>Remaining: {remainingQtyByItem[item.id]}</Text>
                <TextInput
                  keyboardType="numeric"
                  value={qtyById[item.id]}
                  onChangeText={(v) => setQtyById((prev) => ({ ...prev, [item.id]: v }))}
                  style={{
                    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
                    padding: spacing.sm, marginTop: spacing.xs,
                  }}
                />
              </View>
            ))}
            <TextInput
              placeholder="Reference number (optional)"
              value={referenceNumber}
              onChangeText={setReferenceNumber}
              style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.sm, marginBottom: spacing.sm }}
            />
            <TextInput
              placeholder="Receiver name"
              value={receiverName}
              onChangeText={setReceiverName}
              style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.sm, marginBottom: spacing.sm }}
            />
            <TextInput
              placeholder="Supplier representative (sender)"
              value={senderName}
              onChangeText={setSenderName}
              style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.sm }}
            />
          </ScrollView>
          <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg }}>
            <Pressable
              onPress={onClose}
              style={{ flex: 1, alignItems: "center", padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border }}
            >
              <Text style={type.bodyStrong}>Cancel</Text>
            </Pressable>
            <Pressable
              onPress={submit}
              disabled={submitting}
              style={{ flex: 1, alignItems: "center", padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.brand, opacity: submitting ? 0.6 : 1 }}
            >
              <Text style={[type.bodyStrong, { color: colors.onBrand }]}>{submitting ? "Generating…" : "Generate Chalan"}</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}
