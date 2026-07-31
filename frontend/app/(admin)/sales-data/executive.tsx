import { Redirect, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ScrollView, Text, View } from "react-native";

import { api } from "@/src/api/client";
import { AdminPage } from "@/src/components/AdminPage";
import { Card, EmptyState, ErrorState, KpiCard, LoadingState, PillTabs, SegmentedControl, Table, TableCell, TableHeader, TableRow } from "@/src/components/ui";
import { useAuth } from "@/src/state/auth";
import { colors, spacing, type } from "@/src/theme/tokens";

type Filters = { floors: { id: string; name: string }[]; brands: { id: string; name: string }[]; salespeople: { id: string; full_name: string }[] };
type Dashboard = { kpis: { revenue: number; orders: number; aov: number; gross_sales: number; customers: number }; trend: { bucket: string; revenue: number }[]; floors: any[]; brands: any[]; products: any[]; customers: any[]; salespeople: any[]; referrals: any[] };
const PRESETS = [{ value: "today", label: "Today" }, { value: "last_7_days", label: "7D" }, { value: "last_30_days", label: "30D" }, { value: "this_month", label: "Month" }, { value: "quarter", label: "Quarter" }, { value: "year", label: "Year" }];
const money = (n = 0) => `₹${Math.round(n).toLocaleString("en-IN")}`;

function RevenueBars({ points }: { points: Dashboard["trend"] }) {
  const max = Math.max(...points.map((p) => p.revenue), 1);
  if (!points.length) return <EmptyState title="No confirmed revenue in this period" subtitle="Adjust the date or floor filter to inspect another period." />;
  return <View testID="executive-revenue-trend" style={{ flexDirection: "row", alignItems: "flex-end", height: 150, gap: 6 }}>
    {points.slice(-14).map((p) => <View key={p.bucket} style={{ flex: 1, gap: 6, alignItems: "center" }}><View style={{ width: "100%", minHeight: 4, height: `${Math.max(4, p.revenue / max * 100)}%` as any, backgroundColor: colors.brand, borderRadius: 2 }} /><Text numberOfLines={1} style={type.caption}>{p.bucket.slice(-5)}</Text></View>)}
  </View>;
}

export default function ExecutiveAnalytics() {
  const { staff } = useAuth(); const router = useRouter();
  const [filters, setFilters] = useState<Filters | null>(null); const [data, setData] = useState<Dashboard | null>(null); const [error, setError] = useState<string | null>(null);
  const [floor, setFloor] = useState("all"); const [preset, setPreset] = useState("this_month"); const [granularity, setGranularity] = useState("month");
  const query = useMemo(() => new URLSearchParams({ floor_id: floor, preset, granularity }).toString(), [floor, preset, granularity]);
  const load = useCallback(() => { setError(null); setData(null); api.get<Dashboard>(`/executive-analytics/dashboard?${query}`).then(setData).catch((e: any) => setError(e.detail || "Could not load executive analytics")); }, [query]);
  useEffect(() => { api.get<Filters>("/executive-analytics/filters").then(setFilters).catch(() => setFilters({ floors: [], brands: [], salespeople: [] })); }, []);
  useEffect(() => { load(); }, [load]);
  if (staff && !["owner", "admin", "manager"].includes(staff.role)) return <Redirect href="/(admin)/dashboard" />;
  return <AdminPage title="Executive Analytics" subtitle="Confirmed and completed orders only · live business books" actions={<PillTabs testID="executive-granularity" value={granularity} onChange={setGranularity} options={[{ value: "day", label: "D" }, { value: "month", label: "M" }, { value: "quarter", label: "Q" }, { value: "year", label: "Y" }]} />}>
    <ScrollView contentContainerStyle={{ gap: spacing.lg, paddingBottom: spacing.xxxl }}>
      <View style={{ gap: spacing.sm }} testID="executive-global-filters"><SegmentedControl testID="executive-floor-filter" value={floor} onChange={setFloor} options={[{ value: "all", label: "All Floors" }, ...(filters?.floors || []).map((f) => ({ value: f.id, label: f.name }))]} /><PillTabs testID="executive-date-filter" value={preset} onChange={setPreset} options={PRESETS} /></View>
      {error ? <ErrorState subtitle={error} onRetry={load} /> : null}
      {!error && !data ? <LoadingState label="Building live executive view…" /> : null}
      {data ? <>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }} testID="executive-kpis">
          <KpiCard label="Total Revenue" value={money(data.kpis.revenue)} style={{ flex: 1, minWidth: 150 }} /><KpiCard label="Confirmed Orders" value={String(data.kpis.orders)} style={{ flex: 1, minWidth: 130 }} /><KpiCard label="Average Order" value={money(data.kpis.aov)} style={{ flex: 1, minWidth: 150 }} /><KpiCard label="Customers" value={String(data.kpis.customers)} style={{ flex: 1, minWidth: 120 }} />
        </View>
        <Card testID="executive-trend-panel" style={{ gap: spacing.md }}><Text style={type.titleMd}>Revenue trend</Text><Text style={type.caption}>Live confirmed-order revenue for the selected period</Text><RevenueBars points={data.trend} /></Card>
        <Card testID="executive-floor-panel" style={{ gap: spacing.md }}><Text style={type.titleMd}>Floor performance</Text><Table><TableHeader columns={[{ label: "Floor", flex: 2 }, { label: "Revenue", align: "right" }, { label: "Orders", align: "right" }]} />{data.floors.map((row, i) => <TableRow key={row.floor_id} isLast={i === data.floors.length - 1} onPress={() => setFloor(row.floor_id)} testID={`executive-floor-${row.floor_id}`}><TableCell flex={2}>{row.floor_id}</TableCell><TableCell align="right">{money(row.revenue)}</TableCell><TableCell align="right">{String(row.orders)}</TableCell></TableRow>)}</Table></Card>
        <Card testID="executive-brand-panel" style={{ gap: spacing.md }}><Text style={type.titleMd}>Brand performance</Text><Table><TableHeader columns={[{ label: "Brand", flex: 2 }, { label: "Revenue", align: "right" }, { label: "Qty", align: "right" }]} />{data.brands.map((row, i) => <TableRow key={row.brand_id || i} isLast={i === data.brands.length - 1} onPress={() => router.push(`/(admin)/sales-data/brand/${row.brand_id}` as any)} testID={`executive-brand-${row.brand_id}`}><TableCell flex={2}>{row.brand_name || "Unmapped"}</TableCell><TableCell align="right">{money(row.revenue)}</TableCell><TableCell align="right">{String(row.quantity)}</TableCell></TableRow>)}</Table></Card>
        <Card testID="executive-customer-panel" style={{ gap: spacing.md }}><Text style={type.titleMd}>Customer lifetime value</Text><Table><TableHeader columns={[{ label: "Customer", flex: 2 }, { label: "Lifetime revenue", align: "right" }, { label: "Orders", align: "right" }]} />{data.customers.map((row, i) => <TableRow key={row.customer_id} isLast={i === data.customers.length - 1} onPress={() => router.push(`/(admin)/customers/${row.customer_id}` as any)} testID={`executive-customer-${row.customer_id}`}><TableCell flex={2}>{row.name}</TableCell><TableCell align="right">{money(row.revenue)}</TableCell><TableCell align="right">{String(row.orders)}</TableCell></TableRow>)}</Table></Card>
      </> : null}
    </ScrollView>
  </AdminPage>;
}