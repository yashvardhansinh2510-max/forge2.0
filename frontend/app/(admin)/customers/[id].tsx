// Customer profile with full activity timeline across quotations, purchases,
// and future payments. Read-only for now; tapping any timeline entity opens
// the underlying record.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ActivityTimeline, TimelineEvent } from "@/src/components/ActivityTimeline";
import { Badge, Card, EmptyState, StatusBadge } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type Customer = {
  id: string; name: string; company?: string | null; email: string;
  phone?: string | null; city?: string | null; tier: "retail" | "trade" | "vip";
  gstin?: string | null; address?: string | null;
};
type Quotation = { id: string; number: string; status: string; grand_total: number; created_at: string; items: any[] };
type PO = { id: string; number: string; brand_name?: string | null; status: string; grand_total: number; created_at: string };

type Tab = "overview" | "quotations" | "purchases" | "timeline";

export default function CustomerDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [quotations, setQuotations] = useState<Quotation[]>([]);
  const [purchases, setPurchases] = useState<PO[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [tab, setTab] = useState<Tab>("overview");

  const load = useCallback(async () => {
    const [c, qs, pos, tl] = await Promise.all([
      api.get<Customer>(`/customers/${id}`),
      api.get<Quotation[]>(`/quotations`).then((all) => all.filter((q: any) => q.customer_id === id)).catch(() => []),
      api.get<PO[]>(`/purchase-orders?customer_id=${id}`).catch(() => []),
      api.get<TimelineEvent[]>(`/activity/customer/${id}`).catch(() => []),
    ]);
    setCustomer(c);
    setQuotations(qs);
    setPurchases(pos);
    setTimeline(tl);
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const totalRevenue = useMemo(
    () => quotations.filter((q) => ["won", "ordered"].includes(q.status)).reduce((s, q) => s + q.grand_total, 0),
    [quotations],
  );

  if (!customer) return <View style={{ flex: 1, backgroundColor: colors.surface }} />;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <View style={styles.topbar}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <Feather name="chevron-left" size={18} color={colors.onSurface} />
          <Text style={{ fontSize: 14, fontWeight: "500" }}>Customers</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg }}>
        {/* Header */}
        <View style={{ flexDirection: "row", gap: spacing.md, alignItems: "center" }}>
          <View style={styles.avatar}>
            <Text style={{ color: colors.onBrand, fontWeight: "700", fontSize: 22 }}>
              {(customer.company || customer.name)[0].toUpperCase()}
            </Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={type.displayLg}>{customer.company || customer.name}</Text>
            <View style={{ flexDirection: "row", gap: 6, marginTop: 4, alignItems: "center" }}>
              <Badge label={customer.tier.toUpperCase()} tone={customer.tier === "vip" ? "success" : customer.tier === "trade" ? "info" : "neutral"} />
              <Text style={type.caption}>{customer.email}{customer.city ? ` · ${customer.city}` : ""}</Text>
            </View>
          </View>
        </View>

        {/* Stats */}
        <View style={{ flexDirection: "row", gap: spacing.md, flexWrap: "wrap" }}>
          <StatCard label="Lifetime Revenue" value={money(totalRevenue)} icon="trending-up" />
          <StatCard label="Quotations" value={String(quotations.length)} icon="file-text" />
          <StatCard label="Purchase Orders" value={String(purchases.length)} icon="shopping-cart" />
          <StatCard label="Activity events" value={String(timeline.length)} icon="activity" />
        </View>

        {/* Tabs */}
        <View style={styles.tabs}>
          {(["overview", "quotations", "purchases", "timeline"] as const).map((t) => (
            <Pressable
              key={t}
              testID={`tab-${t}`}
              onPress={() => setTab(t)}
              style={[styles.tab, tab === t && styles.tabActive]}
            >
              <Text style={{ fontSize: 13, fontWeight: tab === t ? "700" : "500", color: tab === t ? colors.onSurface : colors.onSurfaceMuted, textTransform: "capitalize" }}>
                {t}
              </Text>
            </Pressable>
          ))}
        </View>

        {/* Body */}
        {tab === "overview" ? (
          <>
            <Card>
              <Text style={type.overline}>Contact</Text>
              <View style={{ gap: 6, marginTop: 8 }}>
                <Row icon="mail" text={customer.email} />
                {customer.phone ? <Row icon="phone" text={customer.phone} /> : null}
                {customer.address ? <Row icon="map-pin" text={customer.address} /> : null}
                {customer.gstin ? <Row icon="hash" text={`GSTIN · ${customer.gstin}`} /> : null}
              </View>
            </Card>
            <Card>
              <Text style={type.overline}>Latest activity</Text>
              <View style={{ marginTop: spacing.md }}>
                <ActivityTimeline events={timeline.slice(0, 8)} dense emptyLabel="No activity yet" />
              </View>
            </Card>
          </>
        ) : tab === "quotations" ? (
          quotations.length === 0 ? (
            <EmptyState icon="file-text" title="No quotations" />
          ) : (
            <Card style={{ padding: 0 }}>
              {quotations.map((q, i) => (
                <Pressable
                  key={q.id}
                  onPress={() => router.push(`/(admin)/quotations/${q.id}` as any)}
                  style={[styles.listRow, i > 0 && { borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border }]}
                >
                  <Text style={[type.mono, { width: 110 }]}>{q.number}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 13, fontWeight: "600" }}>{q.items.length} items</Text>
                    <Text style={type.caption}>{new Date(q.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</Text>
                  </View>
                  <Text style={[type.mono, { width: 100, textAlign: "right", fontWeight: "600" }]}>{money(q.grand_total)}</Text>
                  <StatusBadge status={q.status} />
                </Pressable>
              ))}
            </Card>
          )
        ) : tab === "purchases" ? (
          purchases.length === 0 ? (
            <EmptyState icon="shopping-cart" title="No purchase orders" />
          ) : (
            <Card style={{ padding: 0 }}>
              {purchases.map((p, i) => (
                <Pressable
                  key={p.id}
                  onPress={() => router.push(`/(admin)/purchase-orders/${p.id}` as any)}
                  style={[styles.listRow, i > 0 && { borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border }]}
                >
                  <Text style={[type.mono, { width: 110 }]}>{p.number}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 13, fontWeight: "600" }}>{p.brand_name || "—"}</Text>
                    <Text style={type.caption}>{new Date(p.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</Text>
                  </View>
                  <Text style={[type.mono, { width: 100, textAlign: "right", fontWeight: "600" }]}>{money(p.grand_total)}</Text>
                  <StatusBadge status={p.status} />
                </Pressable>
              ))}
            </Card>
          )
        ) : (
          <Card>
            <ActivityTimeline events={timeline} emptyLabel="Nothing yet" />
          </Card>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function StatCard({ label, value, icon }: { label: string; value: string; icon: keyof typeof import("@expo/vector-icons").Feather.glyphMap }) {
  return (
    <View style={styles.statCard}>
      <Feather name={icon} size={16} color={colors.onSurfaceMuted} />
      <Text style={[type.caption, { marginTop: 6 }]}>{label}</Text>
      <Text style={{ fontSize: 18, fontWeight: "700", color: colors.onSurface, marginTop: 2 }}>{value}</Text>
    </View>
  );
}

function Row({ icon, text }: { icon: keyof typeof import("@expo/vector-icons").Feather.glyphMap; text: string }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
      <Feather name={icon} size={13} color={colors.onSurfaceMuted} />
      <Text style={{ fontSize: 13, color: colors.onSurface }}>{text}</Text>
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
  avatar: {
    width: 60, height: 60, borderRadius: 999,
    backgroundColor: colors.brand, alignItems: "center", justifyContent: "center",
  },
  statCard: {
    flexGrow: 1, minWidth: 140,
    padding: spacing.md, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  tabs: {
    flexDirection: "row", gap: 4,
    backgroundColor: colors.surfaceTertiary,
    padding: 4, borderRadius: radius.md, alignSelf: "flex-start",
  },
  tab: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.sm + 2 },
  tabActive: { backgroundColor: colors.surfaceSecondary },
  listRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    padding: spacing.md,
  },
});
