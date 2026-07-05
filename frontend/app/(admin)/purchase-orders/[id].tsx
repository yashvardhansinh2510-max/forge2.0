// Purchase Order Detail
// -----------------------------------------------------------------------------
// Tablet: two-pane (items + status | timeline & notes)
// Phone:  single scroll with sticky top action bar
//
// Actions:
//   * Change status (walks the ALLOWED_TRANSITIONS state machine)
//   * Receive items (per-line qty_received; auto-transitions status)
//   * Add internal note
//   * Add attachment (base64)
// -----------------------------------------------------------------------------
import { Feather } from "@expo/vector-icons";
import * as DocumentPicker from "expo-document-picker";
import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ActivityTimeline, TimelineEvent } from "@/src/components/ActivityTimeline";
import { Badge, Button, Card, IconButton } from "@/src/components/ui";
import { toast } from "@/src/components/Toast";
import { api } from "@/src/api/client";
import { colors, money, radius, shadow, spacing, type } from "@/src/theme/tokens";

type PoStatus =
  | "draft" | "awaiting_review" | "ordered" | "awaiting_supplier"
  | "partial_received" | "fully_received" | "packed" | "ready_for_dispatch" | "cancelled";

type PoItem = {
  id: string;
  product_id: string;
  sku: string;
  name: string;
  image?: string | null;
  room?: string | null;
  qty: number;
  qty_received: number;
  unit_cost: number;
};

type StatusEvent = {
  id: string;
  at: string;
  from_status: string | null;
  to_status: string;
  by_user_name: string;
  note?: string | null;
};

type Attachment = {
  id: string;
  at: string;
  by_user_name: string;
  filename: string;
  mime: string;
  data_url: string;
  size_bytes: number;
  note?: string | null;
};

type PO = {
  id: string;
  number: string;
  quotation_id?: string | null;
  quotation_number?: string | null;
  customer_id: string;
  customer_name: string;
  project_name?: string | null;
  brand_id?: string | null;
  brand_name?: string | null;
  supplier_id?: string | null;
  supplier_name?: string | null;
  status: PoStatus;
  items: PoItem[];
  status_history: StatusEvent[];
  attachments: Attachment[];
  internal_notes?: string | null;
  expected_delivery_at?: string | null;
  subtotal: number;
  grand_total: number;
  created_at: string;
  created_by_name: string;
};

type StatusConfig = {
  columns: { value: PoStatus; label: string }[];
  transitions: Record<string, PoStatus[]>;
  labels: Record<string, string>;
};

const STATUS_TONE: Record<PoStatus, string> = {
  draft: colors.onSurfaceMuted,
  awaiting_review: colors.warning,
  ordered: colors.info,
  awaiting_supplier: colors.info,
  partial_received: colors.warning,
  fully_received: colors.success,
  packed: colors.success,
  ready_for_dispatch: colors.success,
  cancelled: colors.error,
};

export default function PurchaseOrderDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;

  const [po, setPo] = useState<PO | null>(null);
  const [config, setConfig] = useState<StatusConfig | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [receiveOpen, setReceiveOpen] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);
  const [notesDraft, setNotesDraft] = useState("");
  const [notesEditing, setNotesEditing] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [d, cfg, tl] = await Promise.all([
      api.get<PO>(`/purchase-orders/${id}`),
      api.get<StatusConfig>("/purchase-orders/config/statuses"),
      api.get<TimelineEvent[]>(`/activity/purchase/${id}`),
    ]);
    setPo(d);
    setConfig(cfg);
    setTimeline(tl);
    setNotesDraft(d.internal_notes || "");
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const allowedNext = useMemo(
    () => (po && config ? (config.transitions[po.status] || []).filter((s) => s !== po.status) : []),
    [po, config],
  );

  const changeStatus = async (next: PoStatus, note?: string) => {
    if (!po) return;
    setBusy(true);
    try {
      await api.post(`/purchase-orders/${po.id}/status`, { to_status: next, note });
      toast.success(`Marked ${config?.labels[next] || next}`);
      await load();
    } catch (e: any) {
      toast.error(e?.detail || "Status change failed");
    } finally {
      setBusy(false);
      setStatusOpen(false);
    }
  };

  const receiveItems = async (receipts: Record<string, number>, note?: string) => {
    if (!po) return;
    setBusy(true);
    try {
      await api.post(`/purchase-orders/${po.id}/receive`, { receipts, note });
      toast.success("Receipts saved");
      await load();
    } catch (e: any) {
      toast.error(e?.detail || "Save failed");
    } finally {
      setBusy(false);
      setReceiveOpen(false);
    }
  };

  const saveNotes = async () => {
    if (!po) return;
    setBusy(true);
    try {
      await api.patch(`/purchase-orders/${po.id}`, { internal_notes: notesDraft });
      toast.success("Notes saved");
      setNotesEditing(false);
      await load();
    } catch (e: any) {
      toast.error(e?.detail || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const addAttachment = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({ multiple: false, type: "*/*", copyToCacheDirectory: true });
      if (res.canceled || !res.assets?.[0]) return;
      const asset = res.assets[0];
      let dataUrl = "";
      if (Platform.OS === "web") {
        // On web, asset.uri is already a blob: URL or data URL. Fetch → base64.
        const blob = await (await fetch(asset.uri)).blob();
        dataUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onloadend = () => resolve(reader.result as string);
          reader.onerror = reject;
          reader.readAsDataURL(blob);
        });
      } else {
        // Native: fetch → base64 via FileReader-equivalent
        const blob = await (await fetch(asset.uri)).blob();
        dataUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onloadend = () => resolve(reader.result as string);
          reader.onerror = reject;
          reader.readAsDataURL(blob);
        });
      }
      await api.post(`/purchase-orders/${id}/attachments`, {
        filename: asset.name,
        mime: asset.mimeType || "application/octet-stream",
        data_url: dataUrl,
      });
      toast.success("Attachment added");
      await load();
    } catch (e: any) {
      toast.error(e?.detail || "Could not attach");
    }
  };

  if (!po || !config) return <View style={{ flex: 1, backgroundColor: colors.surface }} />;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <View style={styles.topbar}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <Feather name="chevron-left" size={18} color={colors.onSurface} />
          <Text style={{ fontSize: 14, fontWeight: "500" }}>Purchases</Text>
        </Pressable>
        <View style={{ flexDirection: "row", gap: 8 }}>
          {po.status !== "draft" && po.status !== "cancelled" && po.status !== "packed" && po.status !== "ready_for_dispatch" ? (
            <Button label="Receive" icon="package" variant="secondary" size="sm" onPress={() => setReceiveOpen(true)} testID="receive-btn" />
          ) : null}
          {allowedNext.length > 0 ? (
            <Button label="Change Status" icon="arrow-right" size="sm" onPress={() => setStatusOpen(true)} testID="status-btn" />
          ) : null}
        </View>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg, flexDirection: isTablet ? "row" : "column" }}
      >
        {/* Left / main column */}
        <View style={{ flex: isTablet ? 1.6 : undefined, gap: spacing.lg }}>
          <View>
            <Text style={[type.mono, { color: colors.onSurfaceMuted }]}>{po.number}</Text>
            <Text style={[type.displayLg, { marginTop: 4 }]}>{po.customer_name}</Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8, alignItems: "center" }}>
              <View style={[styles.statusPill, { backgroundColor: STATUS_TONE[po.status] + "22", borderColor: STATUS_TONE[po.status] }]}>
                <View style={[styles.statusDot, { backgroundColor: STATUS_TONE[po.status] }]} />
                <Text style={{ fontSize: 12, fontWeight: "700", color: STATUS_TONE[po.status] }}>
                  {config.labels[po.status]}
                </Text>
              </View>
              {po.brand_name ? <Badge label={po.brand_name} tone="neutral" /> : null}
              {po.supplier_name ? (
                <Text style={type.caption}>via {po.supplier_name}</Text>
              ) : (
                <Text style={[type.caption, { color: colors.warning }]}>No supplier</Text>
              )}
              {po.quotation_number ? (
                <Pressable onPress={() => router.push(`/(admin)/quotations/${po.quotation_id}` as any)}>
                  <Text style={[type.caption, { textDecorationLine: "underline" }]}>from {po.quotation_number}</Text>
                </Pressable>
              ) : null}
            </View>
          </View>

          {/* Items table */}
          <Card style={{ padding: 0 }}>
            <View style={styles.itemsHeader}>
              <Text style={[type.overline, { width: 40 }]}>#</Text>
              <Text style={[type.overline, { flex: 1 }]}>Item</Text>
              <Text style={[type.overline, { width: 70, textAlign: "right" }]}>QTY</Text>
              <Text style={[type.overline, { width: 90, textAlign: "right" }]}>RECD</Text>
              <Text style={[type.overline, { width: 90, textAlign: "right" }]}>COST</Text>
              <Text style={[type.overline, { width: 100, textAlign: "right" }]}>AMOUNT</Text>
            </View>
            {po.items.map((it, i) => {
              const full = it.qty_received >= it.qty - 1e-6 && it.qty > 0;
              const partial = it.qty_received > 0 && !full;
              return (
                <View key={it.id} style={[styles.itemRow, { borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border }]}>
                  <Text style={[type.mono, { width: 40 }]}>{String(i + 1).padStart(2, "0")}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 13, fontWeight: "600" }} numberOfLines={2}>{it.name}</Text>
                    <Text style={type.caption}>{it.sku}{it.room ? ` · ${it.room}` : ""}</Text>
                  </View>
                  <Text style={[type.mono, { width: 70, textAlign: "right" }]}>{it.qty}</Text>
                  <View style={{ width: 90, alignItems: "flex-end" }}>
                    <Text style={[type.mono, { fontWeight: "600", color: full ? colors.success : partial ? colors.warning : colors.onSurfaceMuted }]}>
                      {it.qty_received}
                    </Text>
                    {partial ? (
                      <Text style={[type.caption, { fontSize: 10 }]}>{Math.round((it.qty_received / it.qty) * 100)}%</Text>
                    ) : null}
                  </View>
                  <Text style={[type.mono, { width: 90, textAlign: "right" }]}>{money(it.unit_cost)}</Text>
                  <Text style={[type.mono, { width: 100, textAlign: "right", fontWeight: "700" }]}>
                    {money(it.qty * it.unit_cost)}
                  </Text>
                </View>
              );
            })}
            <View style={styles.itemsFooter}>
              <View style={{ flex: 1 }} />
              <View style={{ minWidth: 220, gap: 4 }}>
                <FooterRow label="Subtotal" value={money(po.subtotal)} />
                <View style={{ borderTopWidth: 1, borderColor: colors.onSurface, paddingTop: 8, marginTop: 4 }}>
                  <FooterRow label="Grand total" value={money(po.grand_total)} bold />
                </View>
              </View>
            </View>
          </Card>

          {/* Internal notes */}
          <Card>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Text style={type.overline}>Internal Notes</Text>
              {!notesEditing ? (
                <Pressable onPress={() => setNotesEditing(true)} hitSlop={8}>
                  <Feather name="edit-2" size={14} color={colors.onSurfaceMuted} />
                </Pressable>
              ) : null}
            </View>
            {notesEditing ? (
              <View style={{ gap: spacing.sm, marginTop: 8 }}>
                <TextInput
                  value={notesDraft}
                  onChangeText={setNotesDraft}
                  multiline
                  placeholder="Add internal notes (visible only to team)"
                  placeholderTextColor={colors.onSurfaceMuted}
                  style={styles.notesInput}
                  testID="notes-input"
                />
                <View style={{ flexDirection: "row", gap: 8, justifyContent: "flex-end" }}>
                  <Button label="Cancel" variant="ghost" size="sm" onPress={() => { setNotesEditing(false); setNotesDraft(po.internal_notes || ""); }} />
                  <Button label="Save" icon="check" size="sm" onPress={saveNotes} loading={busy} testID="save-notes" />
                </View>
              </View>
            ) : (
              <Text style={{ fontSize: 13, color: po.internal_notes ? colors.onSurface : colors.onSurfaceMuted, marginTop: 6 }}>
                {po.internal_notes || "No internal notes yet."}
              </Text>
            )}
          </Card>

          {/* Attachments */}
          <Card>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm }}>
              <Text style={type.overline}>Attachments</Text>
              <Pressable onPress={addAttachment} style={styles.attachBtn}>
                <Feather name="paperclip" size={12} color={colors.onSurface} />
                <Text style={{ fontSize: 12, fontWeight: "600" }}>Attach</Text>
              </Pressable>
            </View>
            {po.attachments.length === 0 ? (
              <Text style={type.caption}>No attachments</Text>
            ) : (
              <View style={{ gap: 6 }}>
                {po.attachments.map((a) => (
                  <View key={a.id} style={styles.attachRow}>
                    <Feather name="file" size={14} color={colors.onSurfaceMuted} />
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 13, fontWeight: "500" }} numberOfLines={1}>{a.filename}</Text>
                      <Text style={type.caption}>{a.by_user_name} · {new Date(a.at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</Text>
                    </View>
                    <Text style={type.caption}>{(a.size_bytes / 1024).toFixed(1)} KB</Text>
                  </View>
                ))}
              </View>
            )}
          </Card>
        </View>

        {/* Right column — status timeline + activity */}
        <View style={{ flex: isTablet ? 1 : undefined, gap: spacing.lg }}>
          <Card>
            <Text style={type.overline}>Status Timeline</Text>
            <View style={{ marginTop: spacing.md, gap: spacing.md }}>
              {po.status_history.slice().reverse().map((ev) => (
                <View key={ev.id} style={{ flexDirection: "row", gap: spacing.md }}>
                  <View style={[styles.statusMarker, { backgroundColor: STATUS_TONE[ev.to_status as PoStatus] || colors.onSurfaceMuted }]} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 13, fontWeight: "600" }}>
                      {config.labels[ev.to_status] || ev.to_status}
                      {ev.from_status ? (
                        <Text style={type.caption}> · from {config.labels[ev.from_status] || ev.from_status}</Text>
                      ) : null}
                    </Text>
                    <Text style={type.caption}>
                      {ev.by_user_name} · {new Date(ev.at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                    </Text>
                    {ev.note ? <Text style={[type.body, { fontSize: 12, marginTop: 2, color: colors.onSurfaceSecondary }]}>“{ev.note}”</Text> : null}
                  </View>
                </View>
              ))}
            </View>
          </Card>

          <Card>
            <Text style={type.overline}>Activity</Text>
            <View style={{ marginTop: spacing.md }}>
              <ActivityTimeline events={timeline} emptyLabel="No activity yet" dense />
            </View>
          </Card>
        </View>
      </ScrollView>

      {/* Modals */}
      <StatusModal
        visible={statusOpen}
        onClose={() => setStatusOpen(false)}
        current={po.status}
        allowed={allowedNext}
        labels={config.labels}
        busy={busy}
        onConfirm={changeStatus}
      />
      <ReceiveModal
        visible={receiveOpen}
        onClose={() => setReceiveOpen(false)}
        items={po.items}
        busy={busy}
        onConfirm={receiveItems}
      />
    </SafeAreaView>
  );
}

// -----------------------------------------------------------------------------
// StatusModal — pick from ALLOWED_TRANSITIONS with an optional note
// -----------------------------------------------------------------------------
function StatusModal({
  visible, onClose, current, allowed, labels, busy, onConfirm,
}: {
  visible: boolean;
  onClose: () => void;
  current: PoStatus;
  allowed: PoStatus[];
  labels: Record<string, string>;
  busy: boolean;
  onConfirm: (next: PoStatus, note?: string) => void;
}) {
  const [next, setNext] = useState<PoStatus | null>(null);
  const [note, setNote] = useState("");
  useEffect(() => { if (visible) { setNext(null); setNote(""); } }, [visible]);
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable onPress={onClose} style={styles.modalScrim}>
        <Pressable onPress={() => {}} style={styles.modalCard}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={type.titleMd}>Change status</Text>
            <IconButton icon="x" size={30} onPress={onClose} />
          </View>
          <Text style={[type.caption, { marginTop: 4 }]}>Current · {labels[current]}</Text>
          <View style={{ gap: 8, marginTop: spacing.md }}>
            {allowed.map((s) => (
              <Pressable
                key={s}
                testID={`status-opt-${s}`}
                onPress={() => setNext(s)}
                style={[styles.optionRow, next === s && { borderColor: colors.brand, backgroundColor: colors.brandTint }]}
              >
                <View style={[styles.statusDot, { backgroundColor: STATUS_TONE[s] }]} />
                <Text style={{ fontSize: 14, fontWeight: "600", flex: 1 }}>{labels[s]}</Text>
                {next === s ? <Feather name="check" size={16} color={colors.brand} /> : null}
              </Pressable>
            ))}
          </View>
          <TextInput
            value={note}
            onChangeText={setNote}
            placeholder="Add a note (optional)"
            placeholderTextColor={colors.onSurfaceMuted}
            style={[styles.notesInput, { minHeight: 60, marginTop: spacing.md }]}
            multiline
          />
          <View style={{ flexDirection: "row", gap: 8, justifyContent: "flex-end", marginTop: spacing.md }}>
            <Button label="Cancel" variant="ghost" onPress={onClose} />
            <Button
              label="Confirm"
              icon="check"
              onPress={() => next && onConfirm(next, note || undefined)}
              disabled={!next}
              loading={busy}
              testID="confirm-status"
            />
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

// -----------------------------------------------------------------------------
// ReceiveModal — per-line qty_received input
// -----------------------------------------------------------------------------
function ReceiveModal({
  visible, onClose, items, busy, onConfirm,
}: {
  visible: boolean;
  onClose: () => void;
  items: PoItem[];
  busy: boolean;
  onConfirm: (r: Record<string, number>, note?: string) => void;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  useEffect(() => {
    if (visible) {
      const d: Record<string, string> = {};
      items.forEach((it) => { d[it.id] = String(it.qty_received); });
      setDraft(d);
      setNote("");
    }
  }, [visible, items]);

  const setAllFull = () => {
    const d: Record<string, string> = {};
    items.forEach((it) => { d[it.id] = String(it.qty); });
    setDraft(d);
  };

  const submit = () => {
    const payload: Record<string, number> = {};
    for (const it of items) {
      const n = parseFloat(draft[it.id] || "0");
      if (Number.isFinite(n) && Math.abs(n - it.qty_received) > 1e-6) payload[it.id] = n;
    }
    onConfirm(payload, note || undefined);
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable onPress={onClose} style={styles.modalScrim}>
        <Pressable onPress={() => {}} style={[styles.modalCard, { maxHeight: "90%" }]}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={type.titleMd}>Record receipts</Text>
            <IconButton icon="x" size={30} onPress={onClose} />
          </View>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
            <Text style={type.caption}>Enter quantities received per line item</Text>
            <Pressable onPress={setAllFull} hitSlop={8}>
              <Text style={{ fontSize: 12, fontWeight: "600", color: colors.brand }}>Mark all full</Text>
            </Pressable>
          </View>
          <ScrollView style={{ maxHeight: 360, marginTop: spacing.md }} contentContainerStyle={{ gap: spacing.sm }}>
            {items.map((it) => (
              <View key={it.id} style={styles.receiveRow}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 13, fontWeight: "600" }} numberOfLines={1}>{it.name}</Text>
                  <Text style={type.caption}>{it.sku} · ordered {it.qty}</Text>
                </View>
                <TextInput
                  value={draft[it.id] ?? "0"}
                  onChangeText={(v) => setDraft((d) => ({ ...d, [it.id]: v.replace(/[^0-9.]/g, "") }))}
                  keyboardType="numeric"
                  style={styles.qtyInput}
                  testID={`recv-${it.sku}`}
                />
                <Text style={type.caption}>of {it.qty}</Text>
              </View>
            ))}
          </ScrollView>
          <TextInput
            value={note}
            onChangeText={setNote}
            placeholder="Note (e.g. invoice #, courier)"
            placeholderTextColor={colors.onSurfaceMuted}
            style={[styles.notesInput, { minHeight: 50, marginTop: spacing.md }]}
            multiline
          />
          <View style={{ flexDirection: "row", gap: 8, justifyContent: "flex-end", marginTop: spacing.md }}>
            <Button label="Cancel" variant="ghost" onPress={onClose} />
            <Button label="Save receipts" icon="package" onPress={submit} loading={busy} testID="confirm-receive" />
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function FooterRow({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
      <Text style={bold ? { fontSize: 14, fontWeight: "700" } : type.bodyMuted}>{label}</Text>
      <Text style={[type.mono, bold && { fontSize: 16, fontWeight: "700" }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  topbar: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  statusPill: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: 999, borderWidth: 1,
  },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  itemsHeader: {
    flexDirection: "row", padding: spacing.md, backgroundColor: colors.surfaceTertiary,
    borderTopLeftRadius: radius.md, borderTopRightRadius: radius.md, alignItems: "center",
  },
  itemRow: { flexDirection: "row", padding: spacing.md, alignItems: "center", gap: 8 },
  itemsFooter: {
    flexDirection: "row", padding: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surfaceTertiary,
    borderBottomLeftRadius: radius.md, borderBottomRightRadius: radius.md,
  },
  notesInput: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    padding: 10, fontSize: 14, backgroundColor: colors.surface, minHeight: 80,
    textAlignVertical: "top", color: colors.onSurface,
  },
  attachBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  attachRow: {
    flexDirection: "row", gap: 8, alignItems: "center",
    padding: spacing.sm, borderRadius: radius.sm,
    backgroundColor: colors.surfaceTertiary,
  },
  statusMarker: { width: 10, height: 10, borderRadius: 5, marginTop: 4 },
  modalScrim: { flex: 1, backgroundColor: colors.overlay, justifyContent: "center", alignItems: "center", padding: spacing.lg },
  modalCard: {
    width: "100%", maxWidth: 480,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.lg, ...shadow.lifted,
  },
  optionRow: {
    flexDirection: "row", alignItems: "center", gap: 10,
    padding: spacing.md, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  receiveRow: {
    flexDirection: "row", alignItems: "center", gap: 10,
    padding: 10, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  qtyInput: {
    width: 70, textAlign: "right", fontVariant: ["tabular-nums"],
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    padding: 8, fontSize: 14, color: colors.onSurface, backgroundColor: colors.surface,
  },
});
