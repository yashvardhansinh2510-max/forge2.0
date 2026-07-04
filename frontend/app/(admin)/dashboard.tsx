import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { ProductImage } from "@/src/components/ProductImage";
import { Card, EmptyState, Skeleton, StatusBadge } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { useAuth } from "@/src/state/auth";
import { colors, money, radius, roleLabels, spacing, type } from "@/src/theme/tokens";

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
    } catch (e) {
      /* handled by empty state */
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const kpiCards = stats ? [
    { label: "Revenue (this month)", value: money(stats.revenue_month), icon: "trending-up", tone: "success" as const },
    { label: "Open Pipeline", value: money(stats.open_pipeline), icon: "layers", tone: "neutral" as const },
    { label: "Quotes this month", value: String(stats.quotes_this_month), icon: "file-text", tone: "neutral" as const },
    { label: "Pending Approval", value: String(stats.pending_approval), icon: "clock", tone: "warning" as const },
  ] : [];

  const now = new Date();
  const hour = now.getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  return (
    <AdminPage
      title={`${greeting}, ${(staff?.full_name || "").split(" ")[0]}`}
      subtitle={`${roleLabels[staff?.role || ""] || ""} · ${new Date().toLocaleDateString("en-IN", { weekday: "long", month: "long", day: "numeric" })}`}
      right={
        <Pressable
          testID="new-quotation-cta"
          onPress={() => router.push("/(admin)/quotations/new" as any)}
          style={styles.cta}
        >
          <Feather name="plus" size={16} color={colors.onBrand} />
          <Text style={styles.ctaText}>New Quotation</Text>
        </Pressable>
      }
    >
      <ScrollView
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        contentContainerStyle={{ gap: spacing.lg }}
      >
        {/* KPI Row */}
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
          {stats ? kpiCards.map((k) => (
            <View key={k.label} style={[styles.kpi, { width: isTablet ? "23.5%" : "48%" }]}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                <Text style={type.caption}>{k.label}</Text>
                <Feather name={k.icon as any} size={14} color={colors.onSurfaceMuted} />
              </View>
              <Text style={styles.kpiValue} numberOfLines={1} adjustsFontSizeToFit>{k.value}</Text>
            </View>
          )) : Array.from({ length: 4 }).map((_, i) => (
            <View key={i} style={[styles.kpi, { width: isTablet ? "23.5%" : "48%" }]}>
              <Skeleton w={100} h={12} />
              <Skeleton w={140} h={24} style={{ marginTop: 12 }} />
            </View>
          ))}
        </View>

        {/* Content split */}
        <View style={{ flexDirection: isTablet ? "row" : "column", gap: spacing.lg }}>
          {/* Recent activity */}
          <Card style={{ flex: isTablet ? 1.4 : undefined, padding: 0 }}>
            <View style={styles.cardHeader}>
              <Text style={type.titleMd}>Recent activity</Text>
              <Pressable onPress={() => router.push("/(admin)/quotations" as any)} testID="view-all-quotations">
                <Text style={{ color: colors.brand, fontSize: 13, fontWeight: "600" }}>View all</Text>
              </Pressable>
            </View>
            {!stats ? (
              <View style={{ padding: spacing.lg, gap: 12 }}>
                {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} h={40} />)}
              </View>
            ) : stats.recent_activity.length === 0 ? (
              <EmptyState icon="inbox" title="No recent activity" subtitle="Quotations will show up here once created." />
            ) : (
              stats.recent_activity.map((a, idx) => (
                <Pressable
                  key={a.id}
                  onPress={() => router.push(`/(admin)/quotations/${a.id}` as any)}
                  testID={`activity-${a.id}`}
                  style={({ pressed }) => [styles.row, {
                    backgroundColor: pressed ? colors.surfaceTertiary : "transparent",
                    borderTopWidth: idx === 0 ? 0 : StyleSheet.hairlineWidth,
                    borderColor: colors.border,
                  }]}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{a.title}</Text>
                    <Text style={type.caption}>{new Date(a.at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</Text>
                  </View>
                  <Text style={[type.mono, { marginRight: 10 }]}>{money(a.amount)}</Text>
                  <StatusBadge status={a.status} />
                </Pressable>
              ))
            )}
          </Card>

          {/* Top products */}
          <Card style={{ flex: 1, padding: 0 }}>
            <View style={styles.cardHeader}>
              <Text style={type.titleMd}>Top products</Text>
              <Text style={type.caption}>By revenue</Text>
            </View>
            {!stats ? (
              <View style={{ padding: spacing.lg, gap: 12 }}>
                {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} h={48} />)}
              </View>
            ) : stats.top_products.length === 0 ? (
              <EmptyState icon="package" title="No products quoted yet" />
            ) : (
              stats.top_products.map((p, i) => (
                <View key={p.product_id} style={[styles.productRow, { borderTopWidth: i === 0 ? 0 : StyleSheet.hairlineWidth, borderColor: colors.border }]}>
                  <ProductImage source={p.image} style={styles.thumb} fallbackLabel={p.sku} borderRadius={8} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{p.name}</Text>
                    <Text style={type.caption}>{p.sku} · {p.qty} units</Text>
                  </View>
                  <Text style={type.mono}>{money(p.revenue)}</Text>
                </View>
              ))
            )}
          </Card>
        </View>

        {/* Quick stats */}
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
          {[
            { label: "Customers", value: stats?.customers ?? "—", icon: "users" },
            { label: "Active products", value: stats?.products ?? "—", icon: "package" },
            { label: "Follow-ups due", value: stats?.followups_due ?? "—", icon: "bell" },
          ].map((q) => (
            <View key={q.label} style={[styles.quickStat, { flex: isTablet ? 1 : undefined, width: isTablet ? undefined : "100%" }]}>
              <Feather name={q.icon as any} size={16} color={colors.onSurfaceSecondary} />
              <Text style={type.caption}>{q.label}</Text>
              <Text style={[type.titleLg, { marginLeft: "auto" }]}>{String(q.value)}</Text>
            </View>
          ))}
        </View>
      </ScrollView>
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  cta: {
    flexDirection: "row", gap: 6, alignItems: "center",
    backgroundColor: colors.brand, paddingHorizontal: 14, paddingVertical: 9, borderRadius: radius.md,
  },
  ctaText: { color: colors.onBrand, fontSize: 13, fontWeight: "600" },
  kpi: {
    backgroundColor: colors.surfaceSecondary, padding: spacing.lg, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, gap: 12,
  },
  kpiValue: { fontSize: 24, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.3 },
  cardHeader: {
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md, flexDirection: "row",
    justifyContent: "space-between", alignItems: "center",
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
  },
  productRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    paddingHorizontal: spacing.lg, paddingVertical: 12,
  },
  thumb: { width: 40, height: 40, borderRadius: 8, backgroundColor: colors.surfaceTertiary },
  quickStat: {
    flexDirection: "row", alignItems: "center", gap: 10,
    backgroundColor: colors.surfaceSecondary, padding: spacing.md, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
});
