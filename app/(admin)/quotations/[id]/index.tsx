import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Linking, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ActivityTimeline, TimelineEvent } from "@/src/components/ActivityTimeline";
import { Button, Card, IconButton, PriceTag, StatusBadge } from "@/src/components/ui";
import { api, getToken } from "@/src/api/client";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type Line = { id: string; sku: string; name: string; qty: number; unit_price: number; discount_pct: number | null; room?: string; description?: string | null; category_id?: string | null };
type Quotation = {
  id: string; number: string; customer_name: string; status: string;
  items: Line[]; rooms: string[]; subtotal: number; discount_total: number;
  grand_total: number; created_at: string; notes?: string;
  created_by_name: string;
  project_discount_pct?: number;
  category_discounts?: Record<string, number>;
};
type Breakdown = {
  lines: { line_id: string; discount_pct: number; discount_source: string; discount_amount: number; gross: number; net: number; total: number }[];
  totals: { subtotal: number; discount_total: number; grand_total: number };
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
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;

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
    try {
      const res = await fetch(`${api.base}/api/quotations/${id}/pdf`, { headers: { Authorization: `Bearer ${token}` } });
      const blob = await res.blob();
      const reader = new FileReader();
      reader.onloadend = () => Linking.openURL(reader.result as string);
      reader.readAsDataURL(blob);
    } catch {
      Linking.openURL(`${api.base}/api/quotations/${id}/pdf?_t=${encodeURIComponent(token)}`);
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
      {/* Sticky top bar — back on left, action buttons on right */}
      <View style={styles.topbar}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flex: 1, minWidth: 0 }}>
          <IconButton icon="chevron-left" onPress={() => router.back()} size={36} tone="surface" testID="back-btn" accessibilityLabel="Back" />
          <View style={{ minWidth: 0, flex: 1 }}>
            <Text style={type.overline}>Quotation</Text>
            <Text style={[type.titleMd, { marginTop: 2 }]} numberOfLines={1}>{q.number}</Text>
          </View>
        </View>
        <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
          <Button label="PDF" icon="download" variant="secondary" size="sm" onPress={openPdf} testID="download-pdf" />
          {NEXT_STATUS[q.status] ? (
            <Button
              label={isTablet ? `Mark ${NEXT_STATUS[q.status].replace("_", " ")}` : "Mark"}
              icon="check"
              size="sm"
              onPress={advance}
              testID="advance-status"
            />
          ) : null}
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.lg, paddingBottom: spacing.huge }}>
        {/* Hero section */}
        <View style={styles.hero}>
          <StatusBadge status={q.status} />
          <Text style={[type.displayLg, { marginTop: 10 }]} numberOfLines={2}>{q.customer_name || "Unknown customer"}</Text>
          <Text style={[type.bodyMuted, { marginTop: 4 }]}>
            Prepared by {q.created_by_name} · {new Date(q.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}
          </Text>
          <View style={styles.heroDivider} />
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end" }}>
            <View>
              <Text style={type.caption}>Grand total</Text>
              <PriceTag price={q.grand_total} size="xl" />
            </View>
            {q.status !== "ordered" && q.items.length > 0 ? (
              <Pressable
                onPress={() => router.push(`/(admin)/quotations/${id}/place-order` as any)}
                style={({ pressed }) => [styles.placeOrder, { opacity: pressed ? 0.88 : 1 }]}
                testID="place-order-btn"
              >
                <Feather name="shopping-cart" size={14} color={colors.brand} />
                <Text style={styles.placeOrderText}>Place Order</Text>
              </Pressable>
            ) : null}
          </View>
        </View>

        {/* Line items — tablet: table, phone: stacked cards */}
        {isTablet ? (
          <Card style={{ padding: 0 }} variant="flat">
            <View style={styles.tableHead}>
              <Text style={[type.overline, { width: 40 }]}>#</Text>
              <Text style={[type.overline, { flex: 1 }]}>Item</Text>
              <Text style={[type.overline, { width: 60, textAlign: "right" }]}>QTY</Text>
              <Text style={[type.overline, { width: 100, textAlign: "right" }]}>RATE</Text>
              <Text style={[type.overline, { width: 70, textAlign: "right" }]}>DISC%</Text>
              <Text style={[type.overline, { width: 110, textAlign: "right" }]}>AMOUNT</Text>
            </View>
            {q.items.map((it, i) => {
              const br = breakdown?.lines.find((b) => b.line_id === it.id);
              const pct = br?.discount_pct ?? (it.discount_pct ?? 0);
              const source = br?.discount_source ?? (it.discount_pct != null ? "product" : "none");
              return (
                <View key={it.id} style={styles.tableRow}>
                  <Text style={[type.mono, { width: 40 }]}>{String(i + 1).padStart(2, "0")}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 14, fontFamily: type.titleMd.fontFamily, fontWeight: "600", color: colors.onSurface }} numberOfLines={2}>{it.name}</Text>
                    <Text style={type.caption}>{it.sku}{it.room ? ` · ${it.room}` : ""}</Text>
                  </View>
                  <Text style={[type.mono, { width: 60, textAlign: "right" }]} numberOfLines={1}>{it.qty}</Text>
                  <Text style={[type.mono, { width: 100, textAlign: "right" }]} numberOfLines={1}>{money(it.unit_price)}</Text>
                  <View style={{ width: 70, alignItems: "flex-end" }}>
                    <Text style={type.mono}>{pct}%</Text>
                    {source !== "none" && source !== "product" ? <Text style={[type.caption, { fontSize: 10 }]}>via {source}</Text> : null}
                  </View>
                  <Text style={{ width: 110, textAlign: "right", fontSize: 14, fontFamily: type.titleMd.fontFamily, fontWeight: "700", fontVariant: ["tabular-nums"], color: colors.onSurface }} numberOfLines={1}>
                    {money(it.qty * it.unit_price * (1 - pct / 100))}
                  </Text>
                </View>
              );
            })}
          </Card>
        ) : (
          <View style={{ gap: spacing.sm }}>
            {q.items.map((it, i) => {
              const br = breakdown?.lines.find((b) => b.line_id === it.id);
              const pct = br?.discount_pct ?? (it.discount_pct ?? 0);
              const lineTotal = it.qty * it.unit_price * (1 - pct / 100);
              return (
                <View key={it.id} style={styles.mobileLineCard}>
                  <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-start" }}>
                    <View style={styles.lineIdx}>
                      <Text style={styles.lineIdxText}>{String(i + 1).padStart(2, "0")}</Text>
                    </View>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={{ fontSize: 14, fontFamily: type.titleMd.fontFamily, fontWeight: "600", color: colors.onSurface }} numberOfLines={2}>{it.name}</Text>
                      <Text style={[type.caption, { marginTop: 2 }]}>{it.sku}{it.room ? ` · ${it.room}` : ""}</Text>
                    </View>
                  </View>
                  <View style={styles.lineMeta}>
                    <View style={styles.metaCol}>
                      <Text style={type.caption}>Qty</Text>
                      <Text style={styles.metaValue}>{it.qty}</Text>
                    </View>
                    <View style={styles.metaCol}>
                      <Text style={type.caption}>Rate</Text>
                      <Text style={styles.metaValue} numberOfLines={1}>{money(it.unit_price)}</Text>
                    </View>
                    <View style={styles.metaCol}>
                      <Text style={type.caption}>Disc</Text>
                      <Text style={styles.metaValue}>{pct}%</Text>
                    </View>
                    <View style={[styles.metaCol, { alignItems: "flex-end" }]}>
                      <Text style={type.caption}>Total</Text>
                      <Text style={[styles.metaValue, { color: colors.brand }]} numberOfLines={1}>{money(lineTotal)}</Text>
                    </View>
                  </View>
                </View>
              );
            })}
          </View>
        )}

        {/* Totals card */}
        <Card variant="flat">
          <View style={{ gap: 8 }}>
            {q.project_discount_pct ? (
              <Row label="Project discount" value={`${q.project_discount_pct}%`} />
            ) : null}
            {q.category_discounts && Object.keys(q.category_discounts).length ? (
              <Row label="Category discounts" value={`${Object.keys(q.category_discounts).length} rules`} />
            ) : null}
            <Row label="Subtotal" value={money(q.subtotal)} />
            <Row label="Discount" value={`- ${money(q.discount_total)}`} />
            <View style={styles.totalRow}>
              <Text style={{ fontSize: 15, fontFamily: type.titleMd.fontFamily, fontWeight: "700", color: colors.onSurface }}>Grand total</Text>
              <Text style={{ fontSize: 22, fontFamily: type.displayMd.fontFamily, fontWeight: "700", fontVariant: ["tabular-nums"], color: colors.onSurface, letterSpacing: -0.3 }} numberOfLines={1}>
                {money(q.grand_total)}
              </Text>
            </View>
          </View>
        </Card>

        {q.notes ? (
          <Card variant="flat">
            <Text style={type.overline}>Notes</Text>
            <Text style={[type.body, { color: colors.onSurfaceSecondary, marginTop: 6, lineHeight: 22 }]}>{q.notes}</Text>
          </Card>
        ) : null}

        {linkedPos.length > 0 ? (
          <Card variant="flat">
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
                    <Text style={{ fontSize: 13, fontFamily: type.titleMd.fontFamily, fontWeight: "600", marginTop: 2, color: colors.onSurface }}>{po.brand_name || "—"}</Text>
                  </View>
                  <StatusBadge status={po.status} />
                  <Text style={{ width: 100, textAlign: "right", fontFamily: type.titleMd.fontFamily, fontWeight: "600", fontVariant: ["tabular-nums"], color: colors.onSurface }} numberOfLines={1}>{money(po.grand_total)}</Text>
                  <Feather name="chevron-right" size={14} color={colors.onSurfaceMuted} />
                </Pressable>
              ))}
            </View>
          </Card>
        ) : null}

        <Card variant="flat">
          <Text style={type.overline}>Activity</Text>
          <View style={{ marginTop: spacing.md }}>
            <ActivityTimeline events={timeline} emptyLabel="No activity yet — every mutation from now on will land here." />
          </View>
        </Card>
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: spacing.sm }}>
      <Text style={type.bodyMuted} numberOfLines={1}>{label}</Text>
      <Text style={{ fontSize: 14, fontFamily: type.bodyStrong.fontFamily, fontWeight: "500", fontVariant: ["tabular-nums"], color: colors.onSurface, flexShrink: 0 }} numberOfLines={1}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  topbar: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface,
    gap: spacing.sm,
  },
  hero: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    padding: spacing.lg,
  },
  heroDivider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
    marginVertical: spacing.md,
  },
  placeOrder: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 12, paddingVertical: 8,
    borderRadius: radius.md,
    backgroundColor: colors.brandTint,
    borderWidth: 1, borderColor: colors.brandBorder,
  },
  placeOrderText: {
    fontSize: 13, fontFamily: type.titleMd.fontFamily,
    fontWeight: "600", color: colors.brand,
  },
  tableHead: {
    flexDirection: "row",
    padding: spacing.md,
    backgroundColor: colors.surfaceTertiary,
    borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    alignItems: "center", gap: 8,
  },
  tableRow: {
    flexDirection: "row", padding: spacing.md, alignItems: "center", gap: 8,
    borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.divider,
  },
  mobileLineCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    padding: spacing.md, gap: spacing.md,
  },
  lineIdx: {
    width: 28, height: 28, borderRadius: 8,
    backgroundColor: colors.brandTint,
    alignItems: "center", justifyContent: "center",
  },
  lineIdxText: {
    fontSize: 11, fontFamily: type.titleMd.fontFamily,
    fontWeight: "700", color: colors.brand,
    fontVariant: ["tabular-nums"],
  },
  lineMeta: {
    flexDirection: "row", justifyContent: "space-between",
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.divider,
  },
  metaCol: { gap: 2, minWidth: 60 },
  metaValue: {
    fontSize: 13, fontFamily: type.titleMd.fontFamily,
    fontWeight: "600", color: colors.onSurface,
    fontVariant: ["tabular-nums"],
  },
  totalRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingTop: spacing.md,
    marginTop: 6,
    borderTopWidth: 1, borderColor: colors.borderStrong,
  },
  linkedPoRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    padding: spacing.md, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface,
  },
});
