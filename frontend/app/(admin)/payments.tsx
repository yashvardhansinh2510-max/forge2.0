// Payments — Customer collection tracker
// -----------------------------------------------------------------------------
// Two-pane responsive layout:
//   * Header card (title + subtitle on soft gradient background)
//   * 4-card stats row (outstanding · collected this month · active · fully paid)
//   * Left: search + orders list  |  Right: selected order detail + record modal
//
// The one new capability shipped with this page is a WhatsApp reminder button on
// the order header — one click composes a pre-made reminder message and opens
// wa.me/<phone>?text=<message> so the sales rep can send it instantly.
// -----------------------------------------------------------------------------
import { Feather } from "@expo/vector-icons";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, KeyboardAvoidingView, Linking, Modal, Platform, Pressable,
  ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { Button, Card, IconButton } from "@/src/components/ui";
import { colors, money, radius, shadow, spacing, statusMeta, type } from "@/src/theme/tokens";

type PayMode = "cash" | "upi" | "bank" | "cheque" | "card";

type Stats = {
  total_outstanding: number;
  collected_this_month: number;
  active_orders: number;
  fully_paid: number;
};

type OrderRow = {
  id: string;
  number: string;
  customer_id: string;
  customer_name: string;
  grand_total: number;
  paid: number;
  outstanding: number;
  percent_collected: number;
  payment_status: "paid" | "partial" | "due";
  confirmed_at: string;
  outstanding_short: string | null;
};

type PaymentEntry = {
  id: string;
  amount: number;
  mode: PayMode;
  reference?: string | null;
  note?: string | null;
  paid_at?: string | null;
  created_at?: string;
  recorded_by_name?: string | null;
};

type OrderDetail = {
  id: string;
  number: string;
  status: string;
  customer: { id: string; name: string; company?: string | null; phone?: string | null; email?: string | null; city?: string | null };
  customer_name: string;
  confirmed_at: string;
  notes?: string | null;
  project_name?: string | null;
  mrp: number;
  discounted_rate: number;
  grand_total: number;
  paid: number;
  outstanding: number;
  percent_collected: number;
  payment_status: "paid" | "partial" | "due";
  payments: PaymentEntry[];
};

const MODE_LABELS: Record<PayMode, string> = {
  cash: "Cash",
  upi: "UPI",
  bank: "Bank Transfer",
  cheque: "Cheque",
  card: "Credit Card",
};

const MODE_ICONS: Record<PayMode, string> = {
  cash: "dollar-sign",
  upi: "smartphone",
  bank: "briefcase",
  cheque: "file-text",
  card: "credit-card",
};

// Compact ₹ format for badges: ₹10.9L / ₹8.5L / ₹75k
function shortAmount(v: number): string {
  if (v >= 1_00_00_000) return `₹${(v / 1_00_00_000).toFixed(1)}Cr`;
  if (v >= 1_00_000) return `₹${(v / 1_00_000).toFixed(1)}L`;
  if (v >= 1_000) return `₹${(v / 1_000).toFixed(1)}k`;
  return `₹${Math.round(v)}`;
}

function dateShort(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  } catch { return "—"; }
}

function todayIso(): string {
  // yyyy-mm-dd
  return new Date().toISOString().slice(0, 10);
}

export default function PaymentsScreen() {
  const { width } = useWindowDimensions();
  const isDesktop = width >= 900;

  // Data
  const [stats, setStats] = useState<Stats | null>(null);
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [waLoading, setWaLoading] = useState(false);

  // Record payment modal
  const [showRecord, setShowRecord] = useState(false);
  const [amount, setAmount] = useState("");
  const [payDate, setPayDate] = useState(todayIso());
  const [mode, setMode] = useState<PayMode>("cash");
  const [reference, setReference] = useState("");
  const [saving, setSaving] = useState(false);

  const loadStats = useCallback(async () => {
    try {
      const s = await api.get<Stats>("/payments/stats");
      setStats(s);
    } catch (e: any) { console.warn("stats", e); }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  useEffect(() => { loadStats(); loadOrders(""); /* initial */ // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced search
  useEffect(() => {
    const t = setTimeout(() => { loadOrders(q); }, 220);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  useEffect(() => { if (selectedId) loadDetail(selectedId); }, [selectedId, loadDetail]);

  const savePayment = async () => {
    if (!detail) return;
    const amt = Number((amount || "").toString().replace(/[^0-9.]/g, ""));
    if (!amt || amt <= 0) { toast.error("Enter a valid amount"); return; }
    setSaving(true);
    try {
      await api.post("/payments", {
        quotation_id: detail.id,
        amount: amt,
        mode,
        reference: reference || null,
        paid_at: payDate ? new Date(payDate + "T12:00:00Z").toISOString() : null,
      });
      toast.success("Payment recorded");
      setShowRecord(false);
      setReference("");
      setMode("cash");
      // reload everything
      await Promise.all([loadStats(), loadOrders(q), loadDetail(detail.id)]);
    } catch (e: any) {
      toast.error(e?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const sendWhatsAppReminder = async () => {
    if (!detail) return;
    setWaLoading(true);
    try {
      const res = await api.get<{ wa_url: string; message: string; phone: string | null; phone_display: string | null }>(
        `/payments/orders/${detail.id}/whatsapp-reminder`,
      );
      if (!res.phone) {
        toast.error("No phone number on file — please add one to the customer");
        // Still open WhatsApp with just the pre-filled message
      } else {
        toast.success(`Opening WhatsApp for ${res.phone_display || res.phone}`);
      }
      const ok = await Linking.canOpenURL(res.wa_url);
      if (ok) await Linking.openURL(res.wa_url);
      else await Linking.openURL(res.wa_url); // browsers always resolve wa.me
    } catch (e: any) {
      toast.error(e?.detail || "Could not build reminder");
    } finally {
      setWaLoading(false);
    }
  };

  const callCustomer = async () => {
    if (!detail?.customer.phone) { toast.error("No phone number on file"); return; }
    const phone = detail.customer.phone.replace(/\s+/g, "");
    const url = `tel:${phone}`;
    const ok = await Linking.canOpenURL(url);
    if (ok) await Linking.openURL(url);
    else toast.error("Calling is not supported on this device");
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scrollBody}>
        {/* --------------- Header hero card --------------- */}
        <View style={styles.hero}>
          <Text style={styles.overlineHero}>BUILDCON HOUSE</Text>
          <Text style={styles.heroTitle}>Payments</Text>
          <Text style={styles.heroSubtitle}>
            Customer collection tracker — see what&apos;s owed, record payments, and send reminders instantly.
          </Text>
        </View>

        {/* --------------- Stats row --------------- */}
        <View style={[styles.statsRow, !isDesktop && styles.statsRowMobile]}>
          <StatCard label="Total Outstanding" value={stats ? money(stats.total_outstanding) : "—"} tone="danger" />
          <StatCard label="Collected This Month" value={stats ? money(stats.collected_this_month) : "—"} tone="success" />
          <StatCard label="Active Orders" value={stats ? String(stats.active_orders) : "—"} tone="neutral" />
          <StatCard label="Fully Paid" value={stats ? `${stats.fully_paid} ✓` : "—"} tone="success-bold" />
        </View>

        {/* --------------- Body: list + detail --------------- */}
        <View style={[styles.body, !isDesktop && styles.bodyMobile]}>
          {/* LEFT: Search + orders list */}
          <Card style={[styles.leftCol, isDesktop ? { width: 360 } : { width: "100%" }]}>
            <View style={styles.search}>
              <Feather name="search" size={14} color={colors.onSurfaceMuted} />
              <TextInput
                testID="payments-search"
                value={q}
                onChangeText={setQ}
                placeholder="Search orders…"
                placeholderTextColor={colors.onSurfaceMuted}
                style={styles.searchInput}
                autoCorrect={false}
                autoCapitalize="none"
              />
              {q ? (
                <Pressable onPress={() => setQ("")} hitSlop={8}>
                  <Feather name="x" size={14} color={colors.onSurfaceMuted} />
                </Pressable>
              ) : null}
            </View>

            {loadingList ? (
              <View style={{ paddingVertical: spacing.xl, alignItems: "center" }}>
                <ActivityIndicator />
              </View>
            ) : orders.length === 0 ? (
              <View style={{ paddingVertical: spacing.xl, alignItems: "center", gap: 6 }}>
                <Feather name="inbox" size={22} color={colors.onSurfaceMuted} />
                <Text style={type.caption}>No collectable orders yet.</Text>
              </View>
            ) : (
              <View style={{ gap: 8, marginTop: spacing.md }}>
                {orders.map((o) => (
                  <OrderCard
                    key={o.id}
                    row={o}
                    active={o.id === selectedId}
                    onPress={() => setSelectedId(o.id)}
                  />
                ))}
              </View>
            )}
          </Card>

          {/* RIGHT: Order detail */}
          <View style={[styles.rightCol, !isDesktop && { width: "100%" }]}>
            {!detail || loadingDetail ? (
              <Card style={{ padding: spacing.xxl, alignItems: "center", gap: 10 }}>
                {loadingDetail ? <ActivityIndicator /> : <Feather name="file-text" size={24} color={colors.onSurfaceMuted} />}
                <Text style={type.bodyMuted}>{loadingDetail ? "Loading order…" : "Select an order to see the details."}</Text>
              </Card>
            ) : (
              <>
                {/* Order header */}
                <Card>
                  <View style={styles.detailHeader}>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <Text style={type.titleLg} numberOfLines={1}>
                          {detail.customer.company || detail.customer_name}
                        </Text>
                        <StatusPill status={detail.status === "ordered" ? "ordered" : detail.payment_status} />
                      </View>
                      <Text style={[type.caption, { marginTop: 4 }]}>
                        {detail.number} · Confirmed {dateShort(detail.confirmed_at)}
                        {detail.customer.city ? ` · ${detail.customer.city}` : ""}
                      </Text>
                    </View>
                    <View style={{ flexDirection: "row", gap: 8 }}>
                      <Pressable
                        testID="wa-reminder-btn"
                        onPress={sendWhatsAppReminder}
                        disabled={waLoading}
                        style={({ pressed }) => [styles.waBtn, pressed && { opacity: 0.85 }]}
                      >
                        {waLoading ? (
                          <ActivityIndicator size="small" color="#166534" />
                        ) : (
                          <Feather name="message-circle" size={14} color="#166534" />
                        )}
                        <Text style={styles.waBtnText}>WhatsApp</Text>
                      </Pressable>
                      <Pressable
                        testID="call-btn"
                        onPress={callCustomer}
                        style={({ pressed }) => [styles.callBtn, pressed && { opacity: 0.85 }]}
                      >
                        <Feather name="phone" size={14} color={colors.onSurface} />
                        <Text style={styles.callBtnText}>Call</Text>
                      </Pressable>
                    </View>
                  </View>
                </Card>

                {/* Metric grid */}
                <View style={[styles.metricsGrid, !isDesktop && styles.metricsGridMobile]}>
                  <MetricCard label="MRP" value={money(detail.mrp)} sub="Catalogue price" tone="neutral" />
                  <MetricCard
                    label="Disc. Rate"
                    value={money(detail.discounted_rate)}
                    sub={detail.mrp > detail.discounted_rate ? `Save ${money(detail.mrp - detail.discounted_rate)}` : "No discount"}
                    tone="info"
                  />
                  <MetricCard
                    label="Paid"
                    value={money(detail.paid)}
                    sub={`${detail.percent_collected}% of order`}
                    tone="success"
                  />
                  <MetricCard
                    label="Outstanding"
                    value={money(detail.outstanding)}
                    sub={detail.outstanding > 0 ? "Remaining" : "Fully paid"}
                    tone={detail.outstanding > 0 ? "danger" : "success"}
                  />
                </View>

                {/* Payment history */}
                <Card>
                  <Text style={type.overline}>Payment History</Text>
                  <View style={{ marginTop: spacing.md, gap: 8 }}>
                    {detail.payments.length === 0 ? (
                      <View style={styles.historyEmpty}>
                        <Feather name="alert-circle" size={14} color={colors.error} />
                        <Text style={{ color: colors.error, fontSize: 13 }}>
                          {money(detail.outstanding)} still outstanding
                        </Text>
                      </View>
                    ) : (
                      detail.payments.map((p) => (
                        <View key={p.id} style={styles.paymentRow}>
                          <View style={styles.payIcon}>
                            <Feather name={MODE_ICONS[p.mode] as any} size={14} color={colors.onSurface} />
                          </View>
                          <View style={{ flex: 1, minWidth: 0 }}>
                            <Text style={{ fontSize: 13, fontWeight: "600" }} numberOfLines={1}>
                              {MODE_LABELS[p.mode]} · {dateShort(p.paid_at || p.created_at)}
                            </Text>
                            {(p.reference || p.note) ? (
                              <Text style={[type.caption]} numberOfLines={1}>
                                {p.reference}{p.reference && p.note ? " · " : ""}{p.note}
                              </Text>
                            ) : (
                              <Text style={type.caption}>Recorded by {p.recorded_by_name || "—"}</Text>
                            )}
                          </View>
                          <Text style={[type.mono, { fontWeight: "700", fontSize: 14 }]}>
                            + {money(p.amount)}
                          </Text>
                        </View>
                      ))
                    )}
                  </View>
                </Card>

                {/* Record payment CTA */}
                {detail.outstanding > 0 ? (
                  <Pressable
                    testID="open-record-payment"
                    onPress={() => setShowRecord(true)}
                    style={({ pressed }) => [styles.recordCta, pressed && { opacity: 0.9 }]}
                  >
                    <Feather name="plus" size={16} color={colors.onBrand} />
                    <Text style={styles.recordCtaText}>Record Payment</Text>
                  </Pressable>
                ) : (
                  <View style={styles.paidBanner}>
                    <Feather name="check-circle" size={16} color={colors.success} />
                    <Text style={{ color: colors.success, fontWeight: "600" }}>Order fully paid — great job!</Text>
                  </View>
                )}
              </>
            )}
          </View>
        </View>
      </ScrollView>

      {/* ---- Record Payment modal (right drawer) ---- */}
      <RecordPaymentModal
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

// -----------------------------------------------------------------------------
// Sub-components
// -----------------------------------------------------------------------------
function StatCard({ label, value, tone }: { label: string; value: string; tone: "danger" | "success" | "neutral" | "success-bold" }) {
  const color =
    tone === "danger" ? colors.error :
    tone === "success" ? colors.success :
    tone === "success-bold" ? colors.success :
    colors.onSurface;
  return (
    <View style={styles.statCard}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={[styles.statValue, { color }]}>{value}</Text>
    </View>
  );
}

function OrderCard({ row, active, onPress }: { row: OrderRow; active: boolean; onPress: () => void }) {
  const barColor =
    row.payment_status === "paid" ? colors.success :
    row.payment_status === "partial" ? "#F59E0B" :
    colors.error;
  return (
    <Pressable
      testID={`order-${row.number}`}
      onPress={onPress}
      style={[styles.orderCard, active && styles.orderCardActive]}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface, flex: 1 }} numberOfLines={1}>
          {row.customer_name}
        </Text>
        {row.payment_status === "paid" ? (
          <View style={styles.paidPill}>
            <Feather name="check" size={11} color="#166534" />
            <Text style={{ fontSize: 11, fontWeight: "700", color: "#166534" }}>Paid</Text>
          </View>
        ) : row.outstanding_short ? (
          <View style={styles.duePill}>
            <Text style={{ fontSize: 11, fontWeight: "700", color: "#991B1B" }}>{row.outstanding_short} due</Text>
          </View>
        ) : null}
      </View>
      <Text style={[type.caption, { marginTop: 4 }]}>
        {row.number} · {dateShort(row.confirmed_at)}
      </Text>
      <View style={styles.progressBase}>
        <View style={[styles.progressFill, { width: `${row.percent_collected}%`, backgroundColor: barColor }]} />
      </View>
      <Text style={{ fontSize: 11, color: colors.onSurfaceMuted, marginTop: 4 }}>
        {row.payment_status === "paid" ? "100% — fully paid" : `${row.percent_collected}% collected`}
      </Text>
    </Pressable>
  );
}

function StatusPill({ status }: { status: string }) {
  const meta = statusMeta[status] || { label: status, bg: colors.brandTint, fg: colors.onSurfaceSecondary };
  return (
    <View style={[styles.statusPill, { backgroundColor: meta.bg }]}>
      <View style={[styles.statusDot, { backgroundColor: meta.fg }]} />
      <Text style={{ fontSize: 11, fontWeight: "700", color: meta.fg, letterSpacing: 0.5, textTransform: "uppercase" }}>
        {meta.label}
      </Text>
    </View>
  );
}

function MetricCard({ label, value, sub, tone }: { label: string; value: string; sub: string; tone: "neutral" | "info" | "success" | "danger" }) {
  const valueColor =
    tone === "info" ? "#2563EB" :
    tone === "success" ? colors.success :
    tone === "danger" ? colors.error :
    colors.onSurface;
  const subColor =
    tone === "info" ? "#2563EB" :
    tone === "success" ? colors.success :
    tone === "danger" ? colors.error :
    colors.onSurfaceMuted;
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, { color: valueColor }]} numberOfLines={1}>{value}</Text>
      <Text style={{ fontSize: 11, color: subColor, marginTop: 2 }} numberOfLines={1}>{sub}</Text>
    </View>
  );
}

function RecordPaymentModal(props: {
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
    <Modal visible={visible} animationType="fade" transparent onRequestClose={onClose}>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.modalBackdrop}
      >
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
        <View style={styles.modalCard}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
            <View style={{ flex: 1 }}>
              <Text style={type.titleMd}>Record Payment</Text>
              <Text style={[type.caption, { marginTop: 2 }]} numberOfLines={2}>
                {detail.customer.company || detail.customer_name} · {detail.number} · {money(detail.outstanding)} outstanding
              </Text>
            </View>
            <IconButton icon="x" onPress={onClose} testID="close-record-modal" />
          </View>

          <ScrollView contentContainerStyle={{ gap: spacing.md, paddingBottom: spacing.md }}>
            <View>
              <Text style={styles.fieldLabel}>Amount Received (₹)</Text>
              <TextInput
                testID="pay-amount"
                value={amount}
                onChangeText={(v) => setAmount(v.replace(/[^0-9.]/g, ""))}
                keyboardType="numeric"
                placeholder="e.g. 1090000"
                placeholderTextColor={colors.onSurfaceMuted}
                style={[styles.input, { fontSize: 18, fontWeight: "600" }]}
              />
              <Text style={{ fontSize: 11, color: colors.onSurfaceMuted, marginTop: 4 }}>
                Outstanding: {money(detail.outstanding)}
              </Text>
            </View>

            <View>
              <Text style={styles.fieldLabel}>Date Received</Text>
              {Platform.OS === "web" ? (
                // @ts-ignore — HTML input on web
                <input
                  type="date"
                  value={payDate}
                  onChange={(e: any) => setPayDate(e.target.value)}
                  style={{
                    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
                    padding: 10, fontSize: 14, backgroundColor: colors.surfaceSecondary,
                    color: colors.onSurface, fontFamily: "inherit",
                  } as any}
                />
              ) : (
                <TextInput
                  testID="pay-date"
                  value={payDate}
                  onChangeText={setPayDate}
                  placeholder="YYYY-MM-DD"
                  placeholderTextColor={colors.onSurfaceMuted}
                  style={styles.input}
                />
              )}
            </View>

            <View>
              <Text style={styles.fieldLabel}>Payment Method</Text>
              <View style={styles.modeGrid}>
                {modes.map((m) => {
                  const on = mode === m;
                  return (
                    <Pressable
                      key={m}
                      testID={`pay-mode-${m}`}
                      onPress={() => setMode(m)}
                      style={[styles.modeChip, on && styles.modeChipActive]}
                    >
                      <Text style={[styles.modeText, on && styles.modeTextActive]}>{MODE_LABELS[m]}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>

            <View>
              <Text style={styles.fieldLabel}>Reference / Notes <Text style={{ color: colors.onSurfaceMuted, fontWeight: "400" }}>(optional)</Text></Text>
              <TextInput
                testID="pay-reference"
                value={reference}
                onChangeText={setReference}
                placeholder="Cheque no., UTR, or any note…"
                placeholderTextColor={colors.onSurfaceMuted}
                style={[styles.input, { minHeight: 60 }]}
                multiline
              />
            </View>
          </ScrollView>

          <View style={{ flexDirection: "row", gap: 10, marginTop: spacing.md }}>
            <Pressable
              testID="save-payment"
              onPress={onSave}
              disabled={saving}
              style={({ pressed }) => [styles.saveBtn, { opacity: saving ? 0.7 : pressed ? 0.9 : 1 }]}
            >
              {saving ? <ActivityIndicator size="small" color={colors.onBrand} /> : (
                <Text style={{ color: colors.onBrand, fontWeight: "700", fontSize: 14 }}>Save Payment</Text>
              )}
            </Pressable>
            <Pressable onPress={onClose} style={styles.cancelBtn}>
              <Text style={{ color: colors.onSurface, fontWeight: "600", fontSize: 14 }}>Cancel</Text>
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

// -----------------------------------------------------------------------------
// Styles
// -----------------------------------------------------------------------------
const styles = StyleSheet.create({
  scrollBody: { padding: spacing.xl, gap: spacing.lg, paddingBottom: spacing.xxxl },

  // Hero card
  hero: {
    padding: spacing.xl, borderRadius: radius.lg, backgroundColor: "#EEF4FF",
    borderWidth: 1, borderColor: "#DBEAFE",
    ...shadow.hair,
  },
  overlineHero: {
    fontSize: 10, fontWeight: "700", letterSpacing: 1.4, textTransform: "uppercase",
    color: "#6B7280", marginBottom: 6,
  },
  heroTitle: { fontSize: 32, fontWeight: "700", color: "#111827", letterSpacing: -0.5 },
  heroSubtitle: { fontSize: 14, color: "#4B5563", marginTop: 6, lineHeight: 20 },

  // Stats row
  statsRow: { flexDirection: "row", gap: spacing.md },
  statsRowMobile: { flexWrap: "wrap" },
  statCard: {
    flex: 1, minWidth: 160,
    padding: spacing.lg, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    ...shadow.hair,
  },
  statLabel: {
    fontSize: 11, fontWeight: "600", color: colors.onSurfaceMuted,
    textTransform: "uppercase", letterSpacing: 0.8,
  },
  statValue: { fontSize: 22, fontWeight: "700", marginTop: 8, fontVariant: ["tabular-nums"] },

  // Body 2-column
  body: { flexDirection: "row", gap: spacing.lg, alignItems: "flex-start" },
  bodyMobile: { flexDirection: "column" },

  // Left column
  leftCol: { padding: spacing.md, alignSelf: "flex-start" },
  search: {
    flexDirection: "row", alignItems: "center", gap: 8,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: 10, height: 38, backgroundColor: colors.surfaceSecondary,
  },
  searchInput: {
    flex: 1, fontSize: 13, color: colors.onSurface, paddingVertical: 0,
    ...(Platform.OS === "web" ? { outlineStyle: "none" } as any : {}),
  },
  orderCard: {
    padding: spacing.md, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  orderCardActive: {
    backgroundColor: "#EEF2FF", borderColor: "#C7D2FE",
  },
  duePill: {
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999,
    backgroundColor: "#FEE2E2",
  },
  paidPill: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999,
    backgroundColor: "#DCFCE7",
  },
  progressBase: {
    height: 3, marginTop: 8, borderRadius: 999, backgroundColor: colors.surfaceTertiary, overflow: "hidden",
  },
  progressFill: { height: "100%", borderRadius: 999 },

  // Right column
  rightCol: { flex: 1, gap: spacing.lg, minWidth: 0 },
  detailHeader: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: spacing.md, flexWrap: "wrap",
  },
  statusPill: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 10, height: 22, borderRadius: 999,
  },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  waBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 12, height: 34, borderRadius: radius.md,
    backgroundColor: "#F0FDF4", borderWidth: 1, borderColor: "#BBF7D0",
  },
  waBtnText: { color: "#166534", fontWeight: "700", fontSize: 12 },
  callBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 12, height: 34, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
  },
  callBtnText: { color: colors.onSurface, fontWeight: "600", fontSize: 12 },

  // Metric grid
  metricsGrid: { flexDirection: "row", gap: spacing.md },
  metricsGridMobile: { flexWrap: "wrap" },
  metric: {
    flex: 1, minWidth: 140,
    padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, alignItems: "center",
  },
  metricLabel: {
    fontSize: 10, fontWeight: "600", letterSpacing: 1.2, textTransform: "uppercase",
    color: colors.onSurfaceMuted,
  },
  metricValue: {
    fontSize: 18, fontWeight: "700", marginTop: 6, fontVariant: ["tabular-nums"],
  },

  // History
  historyEmpty: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: "#FEF2F2", borderRadius: radius.md, padding: 10,
    borderWidth: 1, borderColor: "#FECACA",
  },
  paymentRow: {
    flexDirection: "row", alignItems: "center", gap: 10,
    padding: 10, borderRadius: radius.md, backgroundColor: colors.surfaceTertiary,
  },
  payIcon: {
    width: 30, height: 30, borderRadius: 999, backgroundColor: colors.surfaceSecondary,
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border,
  },

  // Record CTA
  recordCta: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    backgroundColor: colors.brand, paddingVertical: 16, borderRadius: radius.md,
  },
  recordCtaText: { color: colors.onBrand, fontWeight: "700", fontSize: 15 },
  paidBanner: {
    flexDirection: "row", alignItems: "center", gap: 8, justifyContent: "center",
    backgroundColor: "#DCFCE7", borderRadius: radius.md, paddingVertical: 12,
    borderWidth: 1, borderColor: "#BBF7D0",
  },

  // Modal
  modalBackdrop: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end",
    ...(Platform.OS === "web" ? { alignItems: "flex-end", paddingRight: 24, paddingBottom: 24 } : { alignItems: "center", paddingBottom: 24 }),
  },
  modalCard: {
    width: "100%", maxWidth: 400,
    padding: spacing.lg, borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary, gap: 4,
    ...shadow.strong,
  },
  fieldLabel: {
    fontSize: 11, fontWeight: "600", letterSpacing: 0.8, textTransform: "uppercase",
    color: colors.onSurfaceMuted, marginBottom: 6,
  },
  input: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, backgroundColor: colors.surfaceSecondary,
    color: colors.onSurface,
    ...(Platform.OS === "web" ? { outlineStyle: "none" } as any : {}),
  },
  modeGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  modeChip: {
    paddingHorizontal: 14, height: 34, borderRadius: 8,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceTertiary,
    alignItems: "center", justifyContent: "center",
  },
  modeChipActive: {
    backgroundColor: colors.brand, borderColor: colors.brand,
  },
  modeText: { color: colors.onSurface, fontSize: 13, fontWeight: "500" },
  modeTextActive: { color: colors.onBrand, fontWeight: "700" },
  saveBtn: {
    flex: 1, height: 42, borderRadius: radius.md,
    backgroundColor: colors.brand, alignItems: "center", justifyContent: "center",
  },
  cancelBtn: {
    height: 42, paddingHorizontal: 20, borderRadius: radius.md,
    backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border,
  },
});
