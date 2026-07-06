// Customer profile with full activity timeline across quotations, purchases,
// and future payments. DS-aligned rebuild: PageHeader, StatTile, SegmentedControl,
// unified list row, Avatar. Business logic preserved.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ActivityTimeline, TimelineEvent } from "@/src/components/ActivityTimeline";
import {
  Avatar, Badge, Button, Card, EmptyState, PageHeader,
  SegmentedControl, StatTile, StatusBadge,
} from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, icon as iconSize, money, radius, spacing, type } from "@/src/theme/tokens";

type Customer = {
  id: string; name: string; company?: string | null; email: string;
  phone?: string | null; city?: string | null; tier: "retail" | "trade" | "vip";
  address?: string | null;
};
type Quotation = { id: string; number: string; status: string; grand_total: number; created_at: string; items: any[] };
type PO = { id: string; number: string; brand_name?: string | null; status: string; grand_total: number; created_at: string };

type Tab = "overview" | "quotations" | "purchases" | "timeline";

export default function CustomerDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 900;

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
      <PageHeader
        title={customer.company || customer.name}
        subtitle={`${customer.email}${customer.city ? ` · ${customer.city}` : ""}`}
        overline={`CUSTOMER · ${customer.tier.toUpperCase()}`}
        back={() => router.back()}
        actions={
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Button
              icon="edit-2"
              label="Edit"
              variant="secondary"
              size="md"
              onPress={() => router.push(`/(admin)/customers/${customer.id}/edit` as any)}
            />
          </View>
        }
      />

      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg, paddingBottom: spacing.xxxl }}>
        {/* Identity row */}
        <Card>
          <View style={{ flexDirection: "row", gap: spacing.lg, alignItems: "center", flexWrap: "wrap" }}>
            <Avatar name={customer.company || customer.name} size={64} tone="brand" />
            <View style={{ flex: 1, minWidth: 240, gap: 6 }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" }}>
                <Text style={type.titleLg} numberOfLines={1}>
                  {customer.company || customer.name}
                </Text>
                <Badge
                  label={customer.tier.toUpperCase()}
                  tone={customer.tier === "vip" ? "success" : customer.tier === "trade" ? "info" : "neutral"}
                />
              </View>
              <View style={{ gap: 6, marginTop: 4 }}>
                <Row icon="mail" text={customer.email} />
                {customer.phone ? <Row icon="phone" text={customer.phone} /> : null}
                {customer.address ? <Row icon="map-pin" text={customer.address} /> : null}
              </View>
            </View>
          </View>
        </Card>

        {/* Stats */}
        <View style={[styles.statsRow, !isDesktop && styles.statsRowMobile]}>
          <StatTile label="Lifetime Revenue" value={money(totalRevenue)} icon="trending-up" tone="success" sub="Won + ordered" />
          <StatTile label="Quotations" value={String(quotations.length)} icon="file-text" tone="brand" sub="All statuses" />
          <StatTile label="Purchase Orders" value={String(purchases.length)} icon="shopping-cart" tone="brand" sub="Across brands" />
          <StatTile label="Activity" value={String(timeline.length)} icon="activity" tone="neutral" sub="Events logged" />
        </View>

        {/* Tabs */}
        <SegmentedControl
          value={tab}
          onChange={setTab}
          options={[
            { value: "overview", label: "Overview" },
            { value: "quotations", label: `Quotations · ${quotations.length}` },
            { value: "purchases", label: `Purchases · ${purchases.length}` },
            { value: "timeline", label: "Timeline" },
          ]}
          fullWidth={!isDesktop}
        />

        {/* Body */}
        {tab === "overview" ? (
          <>
            <Card>
              <Text style={[type.overline, { marginBottom: spacing.md }]}>Latest activity</Text>
              <ActivityTimeline events={timeline.slice(0, 8)} dense emptyLabel="No activity yet" />
            </Card>
          </>
        ) : tab === "quotations" ? (
          quotations.length === 0 ? (
            <Card>
              <EmptyState icon="file-text" title="No quotations yet" subtitle="This customer hasn't received a quotation." />
            </Card>
          ) : (
            <Card padding={0}>
              {quotations.map((q, i) => (
                <Pressable
                  key={q.id}
                  onPress={() => router.push(`/(admin)/quotations/${q.id}` as any)}
                  style={({ pressed, hovered }: any) => [
                    styles.listRow,
                    {
                      borderTopWidth: i > 0 ? StyleSheet.hairlineWidth : 0,
                      borderTopColor: colors.divider,
                      backgroundColor: pressed ? colors.surfaceTertiary : hovered ? colors.surfaceSubtle : "transparent",
                    },
                  ]}
                >
                  <Text style={[type.mono, { width: 120 }]} numberOfLines={1}>{q.number}</Text>
                  <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
                    <Text style={type.titleSm} numberOfLines={1}>{q.items.length} items</Text>
                    <Text style={type.caption}>{fmtDate(q.created_at)}</Text>
                  </View>
                  <Text style={[type.mono, { width: 110, textAlign: "right", fontWeight: "700" }]}>
                    {money(q.grand_total)}
                  </Text>
                  <StatusBadge status={q.status} />
                </Pressable>
              ))}
            </Card>
          )
        ) : tab === "purchases" ? (
          purchases.length === 0 ? (
            <Card>
              <EmptyState icon="shopping-cart" title="No purchase orders" subtitle="Orders will appear here after placement." />
            </Card>
          ) : (
            <Card padding={0}>
              {purchases.map((p, i) => (
                <Pressable
                  key={p.id}
                  onPress={() => router.push(`/(admin)/purchase-orders/${p.id}` as any)}
                  style={({ pressed, hovered }: any) => [
                    styles.listRow,
                    {
                      borderTopWidth: i > 0 ? StyleSheet.hairlineWidth : 0,
                      borderTopColor: colors.divider,
                      backgroundColor: pressed ? colors.surfaceTertiary : hovered ? colors.surfaceSubtle : "transparent",
                    },
                  ]}
                >
                  <Text style={[type.mono, { width: 120 }]} numberOfLines={1}>{p.number}</Text>
                  <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
                    <Text style={type.titleSm} numberOfLines={1}>{p.brand_name || "—"}</Text>
                    <Text style={type.caption}>{fmtDate(p.created_at)}</Text>
                  </View>
                  <Text style={[type.mono, { width: 110, textAlign: "right", fontWeight: "700" }]}>
                    {money(p.grand_total)}
                  </Text>
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

function Row({ icon, text }: { icon: keyof typeof Feather.glyphMap; text: string }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
      <Feather name={icon} size={iconSize.sm} color={colors.onSurfaceMuted} />
      <Text style={[type.bodySm, { color: colors.onSurfaceSecondary }]} numberOfLines={1}>{text}</Text>
    </View>
  );
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  } catch { return "—"; }
}

const styles = StyleSheet.create({
  statsRow: { flexDirection: "row", gap: spacing.md },
  statsRowMobile: { flexWrap: "wrap" },
  listRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
});
