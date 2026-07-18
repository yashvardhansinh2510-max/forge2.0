// ═══════════════════════════════════════════════════════════════════════════
// Payments — migrated to Design System V2.
// Consumes ONLY primitives from @/src/components/ds. Zero local styles for
// spacing, color, radius, elevation, typography, or motion. Business logic
// preserved byte-for-byte from the previous implementation.
// ═══════════════════════════════════════════════════════════════════════════
import { Feather } from "@expo/vector-icons";
import { useCallback, useEffect, useState } from "react";
import {
  KeyboardAvoidingView, Linking, Platform, Pressable, ScrollView,
  StyleSheet, Text, TextInput, useWindowDimensions, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { useBp } from "@/src/design/responsive";
import { toast } from "@/src/components/Toast";
import {
  Alert as UIAlert,
  Badge, Button, Card, EmptyState, FormField, HeroCard,
  Panel, PageHeader, ProgressBar, SearchField, Sheet,
  Skeleton, StatTile, StatusBadge, HoverCard, ActivityRow,
} from "@/src/components/ds";
import {
  colors, icon as iconSize, moneyShort, radius, spacing, type,
} from "@/src/theme/tokens";

type PayMode = "cash" | "upi" | "bank" | "cheque" | "card";

type Stats = {
  total_outstanding: number;
  collected_this_month: number;
  active_orders: number;
  fully_paid: number;
};

type OrderRow = {
  id: string; number: string; customer_id: string; customer_name: string;
  grand_total: number; paid: number; outstanding: number;
  percent_collected: number; payment_status: "paid" | "partial" | "due";
  confirmed_at: string; outstanding_short: string | null;
};

type PaymentEntry = {
  id: string; amount: number; mode: PayMode;
  reference?: string | null; note?: string | null;
  paid_at?: string | null; created_at?: string; recorded_by_name?: string | null;
};

type OrderDetail = {
  id: string; number: string; status: string;
  customer: {
    id: string; name: string; company?: string | null;
    phone?: string | null; email?: string | null; city?: string | null;
  };
  customer_name: string; confirmed_at: string; notes?: string | null;
  project_name?: string | null;
  mrp: number; discounted_rate: number; grand_total: number;
  paid: number; outstanding: number; percent_collected: number;
  payment_status: "paid" | "partial" | "due";
  payments: PaymentEntry[];
};

const MODE_LABELS: Record<PayMode, string> = {
  cash: "Cash", upi: "UPI", bank: "Bank Transfer", cheque: "Cheque", card: "Credit Card",
};
const MODE_ICONS: Record<PayMode, keyof typeof Feather.glyphMap> = {
  cash: "dollar-sign", upi: "smartphone", bank: "briefcase", cheque: "file-text", card: "credit-card",
};

function money(n: number): string {
  return `₹${(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}
function dateShort(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  } catch { return "—"; }
}
function todayIso(): string { return new Date().toISOString().slice(0, 10); }

const paymentTone = (s: "paid" | "partial" | "due"): "success" | "warning" | "danger" =>
  s === "paid" ? "success" : s === "partial" ? "warning" : "danger";

// ═══════════════════════════════════════════════════════════════════════════
export default function PaymentsScreen() {
  const { isDesktop } = useBp();

  const [stats, setStats] = useState<Stats | null>(null);
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [waLoading, setWaLoading] = useState(false);

  const [showRecord, setShowRecord] = useState(false);
  const [amount, setAmount] = useState("");
  const [payDate, setPayDate] = useState(todayIso());
  const [mode, setMode] = useState<PayMode>("cash");
  const [reference, setReference] = useState("");
  const [saving, setSaving] = useState(false);

  const loadStats = useCallback(async () => {
    try { setStats(await api.get<Stats>("/payments/stats")); }
    catch (e: any) { console.warn("stats", e); }
  }, []);

  const loadOrders = useCallback(async (query: string = q) => {
    setLoadingList(true);
    try {
      const url = query ? `/payments/orders?q=${encodeURIComponent(query)}` : "/payments/orders";
      const list = await api.get<OrderRow[]>(url);
      setOrders(list);
      if (!selectedId && list.length) setSelectedId(list[0].id);
    } catch (e: any) {
      toast.error(e?.detail || "Could not load orders");
    } finally {
      setLoadingList(false);
    }
  }, [q, selectedId]);

  const loadDetail = useCallback(async (id: string) => {
    setLoadingDetail(true);
    try {
      const d = await api.get<OrderDetail>(`/payments/orders/${id}`);
      setDetail(d);
      setAmount(d.outstanding > 0 ? String(Math.round(d.outstanding)) : "");
    } catch (e: any) {
      toast.error(e?.detail || "Could not load order details");
      setDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  // Initial mount only.
  useEffect(() => {
    loadStats();
    loadOrders("");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const t = setTimeout(() => { loadOrders(q); }, 220);
    return () => clearTimeout(t);
  }, [q, loadOrders]);
  useEffect(() => { if (selectedId) loadDetail(selectedId); }, [selectedId, loadDetail]);

  const savePayment = async () => {
    if (!detail) return;
    const amt = Number((amount || "").toString().replace(/[^0-9.]/g, ""));
    if (!amt || amt <= 0) { toast.error("Enter a valid amount"); return; }
    setSaving(true);
    try {
      await api.post("/payments", {
        quotation_id: detail.id, amount: amt, mode,
        reference: reference || null,
        paid_at: payDate ? new Date(payDate + "T12:00:00Z").toISOString() : null,
      });
      toast.success("Payment recorded");
      setShowRecord(false);
      setReference("");
      setMode("cash");
      await Promise.all([loadStats(), loadOrders(q), loadDetail(detail.id)]);
    } catch (e: any) {
      toast.error(e?.detail || "Save failed");
    } finally { setSaving(false); }
  };

  const sendWhatsAppReminder = async () => {
    if (!detail) return;
    setWaLoading(true);
    try {
      const res = await api.get<{ wa_url: string; message: string; phone: string | null; phone_display: string | null }>(
        `/payments/orders/${detail.id}/whatsapp-reminder`,
      );
      if (!res.phone) toast.error("No phone number on file — please add one to the customer");
      else toast.success(`Opening WhatsApp for ${res.phone_display || res.phone}`);
      await Linking.openURL(res.wa_url);
    } catch (e: any) { toast.error(e?.detail || "Could not build reminder"); }
    finally { setWaLoading(false); }
  };

  const callCustomer = async () => {
    if (!detail?.customer.phone) { toast.error("No phone number on file"); return; }
    await Linking.openURL(`tel:${detail.customer.phone.replace(/\s+/g, "")}`);
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <PageHeader
        title="Payments"
        subtitle="Track outstanding balances, record payments, and send reminders."
        overline="COLLECTIONS"
        actions={
          <Button icon="download" label="Export" variant="secondary" size="md"
            onPress={() => toast.success("Export coming soon")} />
        }
      />

      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg, paddingBottom: spacing.xxxl }}>
        {/* Hero — white card with brand icon tile */}
        <HeroCard
          overline="THIS MONTH"
          title={stats ? `${moneyShort(stats.total_outstanding)} outstanding` : "Loading collections…"}
          subtitle="Follow up on partial and due orders. Recording a payment updates the customer's timeline automatically."
          icon="credit-card"
          iconTone="brand"
        />

        {/* Stats */}
        <View style={{ flexDirection: "row", gap: spacing.md, flexWrap: "wrap" }}>
          <StatTile label="Total Outstanding" value={stats ? moneyShort(stats.total_outstanding) : "—"}
            icon="alert-circle" tone="danger" sub="Across all active orders" />
          <StatTile label="Collected This Month" value={stats ? moneyShort(stats.collected_this_month) : "—"}
            icon="trending-up" tone="success" sub="Payments received" />
          <StatTile label="Active Orders" value={stats ? String(stats.active_orders) : "—"}
            icon="package" tone="brand" sub="Ordered · not fully paid" />
          <StatTile label="Fully Paid" value={stats ? String(stats.fully_paid) : "—"}
            icon="check-circle" tone="success" sub="Closed collections" />
        </View>

        {/* Body */}
        <View style={{ flexDirection: isDesktop ? "row" : "column", gap: spacing.lg, alignItems: "flex-start" }}>
          {/* Left rail */}
          <View style={{ width: isDesktop ? 380 : "100%" }}>
            <Panel title="Outstanding orders" overline="ORDERS" padding={spacing.md}>
              <View style={{ gap: spacing.md }}>
                <SearchField
                  testID="payments-search"
                  value={q}
                  onChangeText={setQ}
                  placeholder="Search orders…"
                  onClear={() => setQ("")}
                />
                {loadingList ? (
                  <View style={{ gap: spacing.sm }}>
                    {Array.from({ length: 5 }).map((_, i) => (
                      <View key={i} style={{
                        padding: spacing.md, gap: spacing.sm,
                        borderRadius: radius.md,
                        borderWidth: StyleSheet.hairlineWidth,
                        borderColor: colors.border,
                      }}>
                        <Skeleton w="60%" h={14} radius={radius.sm} />
                        <Skeleton w="40%" h={12} radius={radius.sm} />
                        <Skeleton w="100%" h={4} radius={radius.pill} />
                      </View>
                    ))}
                  </View>
                ) : orders.length === 0 ? (
                  <EmptyState icon="inbox" title="No collectable orders"
                    subtitle="Place an order from a quotation to start tracking payments here." />
                ) : (
                  <View style={{ gap: spacing.sm }}>
                    {orders.map((o) => (
                      <OrderRowCard
                        key={o.id}
                        row={o}
                        active={o.id === selectedId}
                        onPress={() => setSelectedId(o.id)}
                      />
                    ))}
                  </View>
                )}
              </View>
            </Panel>
          </View>

          {/* Right — detail */}
          <View style={{ flex: 1, gap: spacing.lg, minWidth: 0, width: isDesktop ? undefined : "100%" }}>
            {loadingDetail || !detail ? (
              <Card>
                <EmptyState
                  icon={loadingDetail ? "loader" : "file-text"}
                  title={loadingDetail ? "Loading order…" : "Select an order"}
                  subtitle={loadingDetail ? "Fetching the latest payment history." : "Choose a row on the left to see its details."}
                />
              </Card>
            ) : (
              <>
                {/* Detail header */}
                <Panel padding={spacing.lg}>
                  <View style={{
                    flexDirection: "row", justifyContent: "space-between",
                    alignItems: "flex-start", gap: spacing.md, flexWrap: "wrap",
                  }}>
                    <View style={{ flex: 1, minWidth: 200, gap: 4 }}>
                      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" }}>
                        <Text style={[type.titleLg, { flexShrink: 1 }]} numberOfLines={2}>
                          {detail.customer.company || detail.customer_name}
                        </Text>
                        <StatusBadge status={detail.payment_status} />
                      </View>
                      <Text style={type.caption} numberOfLines={2}>
                        {detail.number} · Confirmed {dateShort(detail.confirmed_at)}
                        {detail.customer.city ? ` · ${detail.customer.city}` : ""}
                      </Text>
                    </View>
                    <View style={{ flexDirection: "row", gap: spacing.sm, flexShrink: 0 }}>
                      <Button label="WhatsApp" icon="message-circle" variant="secondary" size="sm"
                        loading={waLoading} onPress={sendWhatsAppReminder} testID="wa-reminder-btn" />
                      <Button label="Call" icon="phone" variant="secondary" size="sm"
                        onPress={callCustomer} testID="call-btn" />
                    </View>
                  </View>
                </Panel>

                {/* Metrics */}
                <View style={{ flexDirection: "row", gap: spacing.md, flexWrap: "wrap" }}>
                  <StatTile dense label="MRP" value={money(detail.mrp)}
                    sub="Catalog price" tone="neutral" />
                  <StatTile dense label="Discounted" value={money(detail.discounted_rate)}
                    sub={detail.mrp > detail.discounted_rate ? `Save ${moneyShort(detail.mrp - detail.discounted_rate)}` : "No discount"}
                    tone="brand" />
                  <StatTile dense label="Paid" value={money(detail.paid)}
                    sub={`${detail.percent_collected}% of order`} tone="success" />
                  <StatTile dense label="Outstanding" value={money(detail.outstanding)}
                    sub={detail.outstanding > 0 ? "Remaining balance" : "Fully paid"}
                    tone={detail.outstanding > 0 ? "danger" : "success"} />
                </View>

                {/* Progress */}
                <Panel padding={spacing.lg}>
                  <View style={{ gap: spacing.sm }}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                      <Text style={type.overline}>Collection progress</Text>
                      <Text style={{
                        fontSize: 13, fontFamily: type.titleMd.fontFamily, fontWeight: "700",
                        color: colors.onSurface, fontVariant: ["tabular-nums"],
                      }}>{detail.percent_collected}%</Text>
                    </View>
                    <ProgressBar percent={detail.percent_collected}
                      tone={paymentTone(detail.payment_status)} size="md" />
                  </View>
                </Panel>

                {/* History */}
                <Panel
                  title="Payment history"
                  overline="LEDGER"
                  actions={detail.payments.length
                    ? <Badge label={`${detail.payments.length} entries`} tone="neutral" size="sm" />
                    : undefined}
                >
                  {detail.payments.length === 0 && detail.outstanding > 0 ? (
                    <UIAlert
                      tone="error"
                      title={`${money(detail.outstanding)} still outstanding`}
                      description="No payments recorded yet. Send a WhatsApp reminder or record the first payment below."
                    />
                  ) : detail.payments.length === 0 ? (
                    <EmptyState icon="check-circle" title="Fully paid"
                      subtitle="No payments to show." tone="brand" />
                  ) : (
                    <View>
                      {detail.payments.map((p, i) => (
                        <ActivityRow
                          key={p.id}
                          icon={MODE_ICONS[p.mode]}
                          iconTone="success"
                          title={`${MODE_LABELS[p.mode]} · ${money(p.amount)}`}
                          subtitle={
                            (p.reference || p.note)
                              ? `${p.reference || ""}${p.reference && p.note ? " · " : ""}${p.note || ""}`
                              : `Recorded by ${p.recorded_by_name || "—"}`
                          }
                          timestamp={dateShort(p.paid_at || p.created_at)}
                          isLast={i === detail.payments.length - 1}
                        />
                      ))}
                    </View>
                  )}
                </Panel>

                {/* CTA */}
                {detail.outstanding > 0 ? (
                  <Button
                    testID="open-record-payment"
                    label="Record Payment"
                    icon="plus"
                    variant="primary"
                    size="lg"
                    fullWidth
                    onPress={() => setShowRecord(true)}
                  />
                ) : (
                  <UIAlert tone="success" title="Order fully paid"
                    description="Every rupee collected — this order is closed." />
                )}
              </>
            )}
          </View>
        </View>
      </ScrollView>

      <RecordPaymentSheet
        visible={showRecord}
        onClose={() => setShowRecord(false)}
        detail={detail}
        amount={amount} setAmount={setAmount}
        payDate={payDate} setPayDate={setPayDate}
        mode={mode} setMode={setMode}
        reference={reference} setReference={setReference}
        onSave={savePayment}
        saving={saving}
      />
    </SafeAreaView>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// OrderRowCard — uses HoverCard primitive (scale 1.01 hover, low elevation).
// ─────────────────────────────────────────────────────────────────────────────
function OrderRowCard({ row, active, onPress }: { row: OrderRow; active: boolean; onPress: () => void }) {
  const tone = paymentTone(row.payment_status);
  return (
    <HoverCard
      onPress={onPress}
      padding={spacing.md}
      testID={`order-${row.number}`}
      style={{
        borderColor: active ? colors.brand : colors.border,
        backgroundColor: active ? colors.brandTint : colors.surfaceSecondary,
      }}
    >
      <View style={{ gap: spacing.sm }}>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm }}>
          <Text style={[type.titleSm, { flex: 1 }]} numberOfLines={1}>{row.customer_name}</Text>
          {row.payment_status === "paid" ? (
            <Badge label="Paid" tone="success" size="sm" icon="check" />
          ) : row.outstanding_short ? (
            <Badge label={`${row.outstanding_short} due`}
              tone={tone === "warning" ? "warning" : "error"} size="sm" />
          ) : null}
        </View>
        <Text style={type.caption} numberOfLines={1}>
          {row.number} · {dateShort(row.confirmed_at)}
        </Text>
        <ProgressBar percent={row.percent_collected} tone={tone} size="xs" />
        <Text style={type.caption}>
          {row.payment_status === "paid" ? "100% — fully paid" : `${row.percent_collected}% collected`}
        </Text>
      </View>
    </HoverCard>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// RecordPaymentSheet — unified Sheet primitive.
// ─────────────────────────────────────────────────────────────────────────────
function RecordPaymentSheet(props: {
  visible: boolean; onClose: () => void;
  detail: OrderDetail | null;
  amount: string; setAmount: (v: string) => void;
  payDate: string; setPayDate: (v: string) => void;
  mode: PayMode; setMode: (m: PayMode) => void;
  reference: string; setReference: (v: string) => void;
  onSave: () => void; saving: boolean;
}) {
  const { visible, onClose, detail, amount, setAmount, payDate, setPayDate, mode, setMode, reference, setReference, onSave, saving } = props;
  if (!detail) return null;
  const modes: PayMode[] = ["cash", "upi", "bank", "cheque", "card"];

  return (
    <Sheet
      visible={visible}
      onClose={onClose}
      variant="drawer"
      title="Record Payment"
      subtitle={`${detail.customer.company || detail.customer_name} · ${detail.number} · ${money(detail.outstanding)} outstanding`}
      testID="record-payment-sheet"
      footer={
        <>
          <Button label="Cancel" variant="secondary" onPress={onClose} size="md" />
          <View style={{ flex: 1 }} />
          <Button label="Save Payment" variant="primary" icon="check"
            onPress={onSave} loading={saving} size="md" testID="save-payment" />
        </>
      }
    >
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg }}>
          <FormField label="Amount Received (₹)" required>
            <TextInput
              testID="pay-amount"
              value={amount}
              onChangeText={(v) => setAmount(v.replace(/[^0-9.]/g, ""))}
              keyboardType="numeric"
              placeholder="e.g. 1090000"
              placeholderTextColor={colors.onSurfaceMuted}
              style={styles.numericInput}
            />
            <Text style={[type.caption, { marginTop: 6 }]}>Outstanding: {money(detail.outstanding)}</Text>
          </FormField>

          <FormField label="Date Received">
            {Platform.OS === "web" ? (
              // @ts-ignore native HTML date input
              <input type="date" value={payDate}
                onChange={(e: any) => setPayDate(e.target.value)}
                style={{
                  border: `1px solid ${colors.border}`, borderRadius: radius.md,
                  padding: "10px 12px", fontSize: 14,
                  backgroundColor: colors.surfaceSecondary, color: colors.onSurface,
                  fontFamily: "inherit", outline: "none", boxSizing: "border-box", height: 40,
                } as any}
              />
            ) : (
              <TextInput
                testID="pay-date"
                value={payDate}
                onChangeText={setPayDate}
                placeholder="YYYY-MM-DD"
                placeholderTextColor={colors.onSurfaceMuted}
                style={styles.textInput}
              />
            )}
          </FormField>

          <FormField label="Payment Method">
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
              {modes.map((m) => {
                const on = mode === m;
                return (
                  <Pressable
                    key={m}
                    testID={`pay-mode-${m}`}
                    onPress={() => setMode(m)}
                    style={({ pressed, hovered }: any) => ({
                      paddingHorizontal: spacing.md,
                      height: 40,
                      borderRadius: radius.md,
                      borderWidth: StyleSheet.hairlineWidth,
                      borderColor: on ? colors.brand : hovered ? colors.borderStrong : colors.border,
                      backgroundColor: on ? colors.brand : colors.surfaceSecondary,
                      alignItems: "center", justifyContent: "center",
                      flexDirection: "row", gap: 6,
                      opacity: pressed ? 0.85 : 1,
                    })}
                  >
                    <Feather name={MODE_ICONS[m]} size={iconSize.sm}
                      color={on ? colors.onBrand : colors.onSurfaceSecondary} />
                    <Text style={{
                      color: on ? colors.onBrand : colors.onSurface,
                      fontSize: 13, fontFamily: type.titleMd.fontFamily,
                      fontWeight: on ? "600" : "500",
                    }}>
                      {MODE_LABELS[m]}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          </FormField>

          <FormField label="Reference / Notes" helper="Cheque number, UTR, or any internal note">
            <TextInput
              testID="pay-reference"
              value={reference}
              onChangeText={setReference}
              placeholder="Optional…"
              placeholderTextColor={colors.onSurfaceMuted}
              style={[styles.textInput, { minHeight: 72, textAlignVertical: "top" }]}
              multiline
            />
          </FormField>
        </ScrollView>
      </KeyboardAvoidingView>
    </Sheet>
  );
}

// Local styles — only for form inputs (which are not in the DS yet).
const styles = StyleSheet.create({
  textInput: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    fontSize: 14,
    backgroundColor: colors.surfaceSecondary,
    color: colors.onSurface,
    fontFamily: type.body.fontFamily,
    height: 40,
    ...(Platform.OS === "web" ? { outlineStyle: "none" } as any : {}),
  },
  numericInput: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    fontSize: 22,
    fontFamily: type.titleLg.fontFamily,
    fontWeight: "700",
    backgroundColor: colors.surfaceSecondary,
    color: colors.onSurface,
    fontVariant: ["tabular-nums"],
    ...(Platform.OS === "web" ? { outlineStyle: "none" } as any : {}),
  },
});
