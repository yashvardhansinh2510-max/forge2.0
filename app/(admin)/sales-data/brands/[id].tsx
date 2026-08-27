import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Text, View } from "react-native";

import { api } from "@/src/api/client";
import { AdminPage } from "@/src/components/AdminPage";
import { Card, ErrorState, LoadingState, Table, TableCell, TableHeader, TableRow } from "@/src/components/ui";
import { colors, spacing, type } from "@/src/theme/tokens";

type Detail = { brand: { name: string }; kpis: { revenue: number; orders: number; aov: number }; trend: { bucket: string; revenue: number }[]; products: any[]; customers: any[]; salespeople: any[]; referrals: any[] };
const money = (n = 0) => `₹${Math.round(n).toLocaleString("en-IN")}`;

export default function ExecutiveBrandDetail() {
  const { id } = useLocalSearchParams<{ id: string }>(); const router = useRouter(); const [data, setData] = useState<Detail | null>(null); const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => { if (!id) return; setData(null); api.get<Detail>(`/executive-analytics/brands/${id}?preset=this_month&granularity=month`).then(setData).catch((e: any) => setError(e.detail || "Could not load brand analytics")); }, [id]);
  useEffect(() => { load(); }, [load]);
  return <AdminPage title={data?.brand.name || "Brand analytics"} subtitle="Confirmed-order contribution, customers, products and team performance" back={() => router.back()} contentStyle={{ gap: spacing.lg }}>{error ? <ErrorState subtitle={error} onRetry={load} /> : null}{!error && !data ? <LoadingState label="Loading brand intelligence…" /> : null}{data ? <><View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}><Card testID="brand-detail-revenue" style={{ flex: 1, minWidth: 150 }}><Text style={type.caption}>Revenue</Text><Text style={type.titleLg}>{money(data.kpis.revenue)}</Text></Card><Card testID="brand-detail-orders" style={{ flex: 1, minWidth: 120 }}><Text style={type.caption}>Orders</Text><Text style={type.titleLg}>{data.kpis.orders}</Text></Card><Card testID="brand-detail-aov" style={{ flex: 1, minWidth: 150 }}><Text style={type.caption}>Average order</Text><Text style={type.titleLg}>{money(data.kpis.aov)}</Text></Card></View><Card testID="brand-detail-products" style={{ gap: spacing.md }}><Text style={type.titleMd}>Best selling products</Text><Table><TableHeader columns={[{ label: "Product", flex: 2 }, { label: "Revenue", align: "right" }]} />{data.products.map((row, i) => <TableRow key={row.product_id} isLast={i === data.products.length - 1} testID={`brand-product-${row.product_id}`}><TableCell flex={2}>{row.name}</TableCell><TableCell align="right">{money(row.revenue)}</TableCell></TableRow>)}</Table></Card><Card testID="brand-detail-customers" style={{ gap: spacing.md }}><Text style={type.titleMd}>Top customers</Text>{data.customers.slice(0, 5).map((row) => <View key={row.customer_id} style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider }}><Text style={type.bodyStrong}>{row.name}</Text><Text style={type.bodyStrong}>{money(row.revenue)}</Text></View>)}</Card></> : null}</AdminPage>;
}
