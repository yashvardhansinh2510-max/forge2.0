import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { api } from "@/src/api/client";
import { AdminPage } from "@/src/components/AdminPage";
import { Card, ErrorState, KpiCard, LoadingState, Table, TableCell, TableHeader, TableRow } from "@/src/components/ui";
import { spacing, type } from "@/src/theme/tokens";

type Detail = { salesperson?: { full_name: string }; referrer?: { name: string; type: string }; kpis: { revenue: number; orders: number; aov: number; customers: number }; brands: any[]; products: any[]; customers: any[] };
const money = (n = 0) => `₹${Math.round(n).toLocaleString("en-IN")}`;
export default function PeopleAnalytics() {
  const { kind, id } = useLocalSearchParams<{ kind: "salespeople" | "referrers"; id: string }>(); const router = useRouter(); const [data, setData] = useState<Detail | null>(null); const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => { if (!id || !kind) return; api.get<Detail>(`/executive-analytics/${kind}/${id}?preset=this_month`).then(setData).catch((e: any) => setError(e.detail || "Could not load analytics")); }, [kind, id]);
  useEffect(() => { load(); }, [load]); const name = data?.salesperson?.full_name || data?.referrer?.name || "Performance detail";
  return <AdminPage title={name} subtitle={kind === "salespeople" ? "Salesperson performance" : "Referral performance"} back={() => router.back()}><ScrollView contentContainerStyle={{ gap: spacing.lg, paddingBottom: spacing.xxxl }}>{error ? <ErrorState subtitle={error} onRetry={load} /> : null}{!error && !data ? <LoadingState label="Loading performance…" /> : null}{data ? <><View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}><KpiCard label="Revenue" value={money(data.kpis.revenue)} style={{ flex: 1, minWidth: 140 }} /><KpiCard label="Orders" value={String(data.kpis.orders)} style={{ flex: 1, minWidth: 110 }} /><KpiCard label="Average deal" value={money(data.kpis.aov)} style={{ flex: 1, minWidth: 140 }} /><KpiCard label="Customers" value={String(data.kpis.customers)} style={{ flex: 1, minWidth: 110 }} /></View><Card testID="people-detail-brands" style={{ gap: spacing.md }}><Text style={type.titleMd}>Top brands</Text><Table><TableHeader columns={[{ label: "Brand", flex: 2 }, { label: "Revenue", align: "right" }]} />{data.brands.slice(0, 10).map((row, i) => <TableRow key={row.brand_id || i} isLast={i === Math.min(10, data.brands.length) - 1} testID={`people-brand-${row.brand_id}`}><TableCell flex={2}>{row.brand_name || "Unmapped"}</TableCell><TableCell align="right">{money(row.revenue)}</TableCell></TableRow>)}</Table></Card></> : null}</ScrollView></AdminPage>;
}