import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ActivityTimeline, TimelineEvent } from "@/src/components/ActivityTimeline";
import { Button, Card, StatusBadge } from "@/src/components/ui";
import { api, getToken } from "@/src/api/client";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type Line = { id: string; sku: string; name: string; qty: number; unit_price: number; discount_pct: number | null; tax_pct: number; room?: string; description?: string | null; category_id?: string | null };
type Quotation = {
  id: string; number: string; customer_name: string; status: string;
  items: Line[]; rooms: string[]; subtotal: number; discount_total: number;
  tax_total: number; grand_total: number; created_at: string; notes?: string;
  created_by_name: string;
  project_discount_pct?: number;
  category_discounts?: Record<string, number>;
};
type Breakdown = {
  lines: { line_id: string; discount_pct: number; discount_source: string; discount_amount: number; gross: number; net: number; total: number }[];
  totals: { subtotal: number; discount_total: number; tax_total: number; grand_total: number };
  project_discount_pct: number;
  category_discounts: Record<string, number>;
};

const NEXT_STATUS: Record<string, string> = {
  draft: "sent",
  sent: "won",
  pending_approval: "approved",
};

type PoStub = { id: string; number: string; brand_name?: string | null; status: string; grand_total: number };

export default function QuotationDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [q, setQ] = useState<Quotation | null>(null);
  const [breakdown, setBreakdown] = useState<Breakdown | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [linkedPos, setLinkedPos] = useState<PoStub[]>([]);

  const load = useCallback(async () => {
    const [doc, br, tl, pos] = await Promise.all([
      api.get<Quotation>(`/quotations/${id}`),
      api.get<Breakdown>(`/quotations/${id}/breakdown`).catch(() => null),
      api.get<TimelineEvent[]>(`/activity/quotation/${id}`).catch(() => []),
      api.get<PoStub[]>(`/purchase-orders?quotation_id=${id}`).catch(() => []),
    ]);
    setQ(doc); setBreakdown(br); setTimeline(tl); setLinkedPos(pos);
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const openPdf = async () => {
    const token = await getToken();
    if (!token) return;
    const url = `${api.base}/api/quotations/${id}/pdf?_t=${encodeURIComponent(token)}`;
    // browser can't send Authorization headers on window.open; server also accepts _t
    // (but our route requires header). We'll open a signed link built via fetch instead.
    // Simplest cross-platform: fetch blob and open via Linking (data:).
    try {
      const res = await fetch(`${api.base}/api/quotations/${id}/pdf`, { headers: { Authorization: `Bearer ${token}` } });
      const blob = await res.blob();
      const reader = new FileReader();
      reader.onloadend = () => Linking.openURL(reader.result as string);
      reader.readAsDataURL(blob);
    } catch {
      Linking.openURL(url);
    }
  };

  const advance = async () => {
    if (!q) return;
    const next = NEXT_STATUS[q.status];
    if (!next) return;
    const updated = await api.patch<Quotation>(`/quotations/${id}`, { status: next, reason: `Marked ${next}` });
    setQ(updated);
  };

  if (!q) return <View style={{ flex: 1, backgroundColor: colors.surface }} />;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <View style={styles.topbar}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <Feather name="chevron-left" size={18} color={colors.onSurface} />
          <Text style={{ fontSize: 14, fontWeight: "500" }}>Quotations</Text>
        </Pressable>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Button label="PDF" icon="download" variant="secondary" size="sm" onPress={openPdf} testID="download-pdf" />
          {NEXT_STATUS[q.status] ? (
            <Button label={`Mark ${NEXT_STATUS[q.status].replace("_", " ")}`} icon="check" size="sm" onPress={advance} testID="advance-status" />
          ) : null}
          {q.status !== "ordered" && q.items.length > 0 ? (
            <Button
              label="Place Order"
              icon="shopping-cart"
              size="sm"
              onPress={() => router.push(`/(admin)/quotations/${id}/place-order` as any)}
              testID="place-order-btn"
            />
          ) : null}
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg }}>
        <View>
          <Text style={[type.mono, { color: colors.onSurfaceMuted }]}>{q.number}</Text>
          <Text style={[type.displayLg, { marginTop: 4 }]}>{q.customer_name}</Text>
          <View style={{ flexDirection: "row", gap: 8, marginTop: 8, alignItems: "center" }}>
            <StatusBadge status={q.status} />
            <Text style={type.caption}>Prepared by {q.created_by_name} · {new Date(q.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}</Text>
          </View>
        </View>

        <Card style={{ padding: 0 }}>
          <View style={styles.headerRow}>
            <Text style={[type.overline, { width: 40 }]}>#</Text>
            <Text style={[type.overline, { flex: 1 }]}>Item</Text>
            <Text style={[type.overline, { width: 60, textAlign: "right" }]}>QTY</Text>
            <Text style={[type.overline, { width: 90, textAlign: "right" }]}>RATE</Text>
            <Text style={[type.overline, { width: 70, textAlign: "right" }]}>DISC%</Text>
            <Text style={[type.overline, { width: 100, textAlign: "right" }]}>AMOUNT</Text>
          </View>
          {q.items.map((it, i) => {
            const br = breakdown?.lines.find((b) => b.line_id === it.id);
            const pct = br?.discount_pct ?? (it.discount_pct ?? 0);
            const source = br?.discount_source ?? (it.discount_pct != null ? "product" : "none");
            return (
              <View key={it.id} style={[styles.row, { borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border }]}>
                <Text style={[type.mono, { width: 40 }]}>{String(i + 1).padStart(2, "0")}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }} numberOfLines={2}>{it.name}</Text>
                  <Text style={type.caption}>{it.sku}{it.room ? ` · ${it.room}` : ""}</Text>
                  {it.description ? <Text style={[type.caption, { marginTop: 2 }]} numberOfLines={2}>{it.description}</Text> : null}
                </View>
                <Text style={[type.mono, { width: 60, textAlign: "right" }]}>{it.qty}</Text>
                <Text style={[type.mono, { width: 90, textAlign: "right" }]}>{money(it.unit_price)}</Text>
                <View style={{ width: 70, alignItems: "flex-end" }}>
                  <Text style={type.mono}>{pct}%</Text>
                  {source !== "none" && source !== "product" ? (
                    <Text style={[type.caption, { fontSize: 10 }]}>via {source}</Text>
                  ) : null}
                </View>
                <Text style={[type.mono, { width: 100, textAlign: "right", fontWeight: "700" }]}>
                  {money(it.qty * it.unit_price * (1 - pct / 100))}
                </Text>
              </View>
            );
          })}
        </Card>

        <Card>
          <View style={{ gap: 6, marginLeft: "auto", minWidth: 280 }}>
            {q.project_discount_pct ? (
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={type.bodyMuted}>Project discount</Text>
                <Text style={type.mono}>{q.project_discount_pct}%</Text>
              </View>
            ) : null}
            {q.category_discounts && Object.keys(q.category_discounts).length ? (
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={type.bodyMuted}>Category discounts</Text>
                <Text style={type.mono}>{Object.keys(q.category_discounts).length} rules</Text>
              </View>
            ) : null}
            {[
              ["Subtotal", q.subtotal, ""],
              ["Discount", q.discount_total, "-"],
              ["Tax", q.tax_total, ""],
            ].map(([l, v, sign]) => (
              <View key={String(l)} style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={type.bodyMuted}>{l as string}</Text>
                <Text style={type.mono}>{sign as string}{money(v as number)}</Text>
              </View>
            ))}
            <View style={{ flexDirection: "row", justifyContent: "space-between", borderTopWidth: 1, borderColor: colors.onSurface, paddingTop: 8, marginTop: 4 }}>
              <Text style={{ fontSize: 15, fontWeight: "700" }}>Grand total</Text>
              <Text style={{ fontSize: 22, fontWeight: "700", fontVariant: ["tabular-nums"] }}>{money(q.grand_total)}</Text>
            </View>
          </View>
        </Card>

        {q.notes ? (
          <Card>
            <Text style={type.overline}>Notes</Text>
            <Text style={[type.body, { color: colors.onSurfaceSecondary, marginTop: 6 }]}>{q.notes}</Text>
          </Card>
        ) : null}

        {linkedPos.length > 0 ? (
          <Card>
            <Text style={type.overline}>Linked Purchase Orders</Text>
            <View style={{ gap: 8, marginTop: spacing.md }}>
              {linkedPos.map((po) => (
                <Pressable
                  key={po.id}
                  testID={`linked-po-${po.id}`}
                  onPress={() => router.push(`/(admin)/purchase-orders/${po.id}` as any)}
                  style={styles.linkedPoRow}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={[type.mono, { fontSize: 12 }]}>{po.number}</Text>
                    <Text style={{ fontSize: 13, fontWeight: "600", marginTop: 2 }}>{po.brand_name || "—"}</Text>
                  </View>
                  <StatusBadge status={po.status} />
                  <Text style={[type.mono, { width: 100, textAlign: "right", fontWeight: "600" }]}>{money(po.grand_total)}</Text>
                  <Feather name="chevron-right" size={14} color={colors.onSurfaceMuted} />
                </Pressable>
              ))}
            </View>
          </Card>
        ) : null}

        <Card>
          <Text style={type.overline}>Activity</Text>
          <View style={{ marginTop: spacing.md }}>
            <ActivityTimeline events={timeline} emptyLabel="No activity yet — every mutation from now on will land here." />
          </View>
        </Card>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  topbar: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  headerRow: {
    flexDirection: "row", padding: spacing.md, backgroundColor: colors.surfaceTertiary,
    borderTopLeftRadius: radius.md, borderTopRightRadius: radius.md, alignItems: "center",
  },
  row: { flexDirection: "row", padding: spacing.md, alignItems: "center", gap: 8 },
  linkedPoRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    padding: spacing.md, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface,
  },
});
