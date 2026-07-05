// BuildCon House · Admin Dashboard
// KPI grid + activity feed + top products — built entirely from DS primitives.

import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { ProductImage } from "@/src/components/ProductImage";
import {
  Avatar,
  Card,
  EmptyState,
  KpiCard,
  ListRow,
  Skeleton,
  StatusBadge,
} from "@/src/components/ui";
import { api } from "@/src/api/client";
import { useAuth } from "@/src/state/auth";
import { colors, money, moneyShort, radius, roleLabels, spacing, type } from "@/src/theme/tokens";

type Stats = {
  revenue_month: number;
  open_pipeline: number;
  pending_approval: number;
  quotes_this_month: number;
  customers: number;
  products: number;
  followups_due: number;
  recent_activity: { id: string; title: string; status: string; amount: number; at: string }[];
  top_products: { product_id: string; name: string; sku: string; image?: string | null; qty: number; revenue: number }[];
};

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const { staff } = useAuth();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;

  const load = useCallback(async () => {
    try {
      const s = await api.get<Stats>("/dashboard/stats");
      setStats(s);
    } catch {
      /* handled via empty state */
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const now = new Date();
  const hour = now.getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  const kpis = stats ? [
    { label: "Revenue (month)", value: moneyShort(stats.revenue_month), sub: money(stats.revenue_month), icon: "trending-up" as const, tone: "success" as const },
    { label: "Open pipeline",   value: moneyShort(stats.open_pipeline), sub: money(stats.open_pipeline), icon: "layers" as const,      tone: "brand" as const },
    { label: "Quotes this month", value: String(stats.quotes_this_month), icon: "file-text" as const, tone: "neutral" as const },
    { label: "Pending approval",  value: String(stats.pending_approval),  icon: "clock" as const,     tone: "warning" as const },
  ] : [];

  return (
    <AdminPage
      title={`${greeting}, ${(staff?.full_name || "").split(" ")[0]}`}
      subtitle={`${roleLabels[staff?.role || ""] || ""} · ${new Date().toLocaleDateString("en-IN", { weekday: "long", month: "long", day: "numeric" })}`}
      right={
        <Pressable
          testID="new-quotation-cta"
          onPress={() => router.push("/(admin)/quotations/new" as any)}
          style={({ pressed }) => [styles.cta, { opacity: pressed ? 0.88 : 1 }]}
        >
          <Feather name="plus" size={16} color={colors.onBrand} />
          <Text style={styles.ctaText}>New Quotation</Text>
        </Pressable>
      }
    >
      <ScrollView
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
        contentContainerStyle={{ gap: spacing.lg }}
      >
        {/* KPI grid */}
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
          {stats ? kpis.map((k) => (
            <View key={k.label} style={{ flexBasis: isTablet ? "23.5%" : "47.5%", flexGrow: 1, minWidth: isTablet ? 160 : 140 }}>
              <KpiCard label={k.label} value={k.value} sub={k.sub} icon={k.icon} tone={k.tone} />
            </View>
          )) : Array.from({ length: 4 }).map((_, i) => (
            <View key={i} style={{ flexBasis: isTablet ? "23.5%" : "47.5%", flexGrow: 1, minWidth: isTablet ? 160 : 140, padding: spacing.lg, borderRadius: radius.lg, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, gap: 10 }}>
              <Skeleton w={110} h={12} />
              <Skeleton w={150} h={26} />
            </View>
          ))}
        </View>

        {/* Content split */}
        <View style={{ flexDirection: isTablet ? "row" : "column", gap: spacing.lg }}>
          <Card style={{ flex: isTablet ? 1.4 : undefined, padding: 0 }} variant="flat">
            <View style={styles.cardHeader}>
              <View>
                <Text style={type.titleMd}>Recent activity</Text>
                <Text style={[type.caption, { marginTop: 2 }]}>Latest quotations across your team</Text>
              </View>
              <Pressable onPress={() => router.push("/(admin)/quotations" as any)} testID="view-all-quotations" hitSlop={8}>
                <Text style={styles.viewAll}>View all</Text>
              </Pressable>
            </View>
            {!stats ? (
              <View style={{ padding: spacing.lg, gap: 12 }}>
                {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} h={44} />)}
              </View>
            ) : stats.recent_activity.length === 0 ? (
              <EmptyState icon="inbox" title="No recent activity" subtitle="Quotations will show up here once created." />
            ) : (
              stats.recent_activity.map((a, idx) => (
                <ListRow
                  key={a.id}
                  testID={`activity-${a.id}`}
                  isFirst={idx === 0}
                  onPress={() => router.push(`/(admin)/quotations/${a.id}` as any)}
                  leading={<Avatar name={a.title} size={36} tone="surface" />}
                  title={a.title}
                  subtitle={new Date(a.at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                  meta={money(a.amount)}
                  right={<View style={{ marginTop: 4 }}><StatusBadge status={a.status} /></View>}
                />
              ))
            )}
          </Card>

          <Card style={{ flex: 1, padding: 0 }} variant="flat">
            <View style={styles.cardHeader}>
              <View>
                <Text style={type.titleMd}>Top products</Text>
                <Text style={[type.caption, { marginTop: 2 }]}>By revenue · this month</Text>
              </View>
              <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: colors.brandTint, alignItems: "center", justifyContent: "center" }}>
                <Feather name="trending-up" size={16} color={colors.brand} />
              </View>
            </View>
            {!stats ? (
              <View style={{ padding: spacing.lg, gap: 12 }}>
                {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} h={52} />)}
              </View>
            ) : stats.top_products.length === 0 ? (
              <EmptyState icon="package" title="No products quoted yet" />
            ) : (
              stats.top_products.map((p, i) => (
                <View key={p.product_id} style={[styles.productRow, { borderTopWidth: i === 0 ? 0 : StyleSheet.hairlineWidth }]}>
                  <ProductImage source={p.image} style={styles.thumb} fallbackLabel={p.sku} borderRadius={10} />
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={{ fontSize: 14, fontFamily: type.titleMd.fontFamily, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{p.name}</Text>
                    <Text style={type.caption} numberOfLines={1}>{p.sku} · {p.qty} units</Text>
                  </View>
                  <Text style={{
                    fontSize: 14,
                    fontFamily: type.titleMd.fontFamily,
                    fontWeight: "600",
                    color: colors.onSurface,
                    fontVariant: ["tabular-nums"],
                  }}>{moneyShort(p.revenue)}</Text>
                </View>
              ))
            )}
          </Card>
        </View>

        {/* Quick stats strip */}
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
          {[
            { label: "Customers",     value: stats?.customers ?? "—",     icon: "users" as const,   route: "/(admin)/customers" },
            { label: "Active products", value: stats?.products ?? "—",     icon: "package" as const, route: "/(admin)/catalog" },
            { label: "Follow-ups due", value: stats?.followups_due ?? "—", icon: "bell" as const,    route: "/(admin)/followups" },
          ].map((q) => (
            <Pressable
              key={q.label}
              onPress={() => router.push(q.route as any)}
              style={({ pressed }) => [styles.quickStat, {
                flex: isTablet ? 1 : undefined,
                width: isTablet ? undefined : "100%",
                opacity: pressed ? 0.92 : 1,
              }]}
            >
              <View style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: colors.brandTint, alignItems: "center", justifyContent: "center" }}>
                <Feather name={q.icon} size={16} color={colors.brand} />
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={type.captionStrong}>{q.label}</Text>
                <Text style={{ fontSize: 20, fontFamily: type.titleLg.fontFamily, fontWeight: "700", color: colors.onSurface, marginTop: 2, letterSpacing: -0.2 }}>
                  {String(q.value)}
                </Text>
              </View>
              <Feather name="chevron-right" size={16} color={colors.onSurfaceMuted} />
            </Pressable>
          ))}
        </View>
      </ScrollView>
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  cta: {
    flexDirection: "row", gap: 6, alignItems: "center",
    backgroundColor: colors.brand,
    paddingHorizontal: 14, paddingVertical: 10,
    borderRadius: radius.md,
  },
  ctaText: {
    color: colors.onBrand,
    fontSize: 13,
    fontFamily: type.titleMd.fontFamily,
    fontWeight: "600",
    letterSpacing: -0.1,
  },
  cardHeader: {
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start",
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    gap: spacing.md,
  },
  viewAll: {
    color: colors.brand,
    fontSize: 13,
    fontFamily: type.titleMd.fontFamily,
    fontWeight: "600",
  },
  productRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    paddingHorizontal: spacing.lg, paddingVertical: 12,
    borderColor: colors.divider,
  },
  thumb: { width: 44, height: 44, borderRadius: 10, backgroundColor: colors.surfaceTertiary },
  quickStat: {
    flexDirection: "row", alignItems: "center", gap: 12,
    backgroundColor: colors.surfaceSecondary,
    padding: spacing.lg,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
});
