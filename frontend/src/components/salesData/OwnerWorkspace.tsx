import { Redirect, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Text, View } from "react-native";

import { salesWorkspaceApi, type WorkspaceData, type WorkspaceName } from "@/src/api/salesWorkspaces";
import { AdminPage } from "@/src/components/AdminPage";
import { Card, EmptyState, ErrorState, KpiCard, LoadingState, PillTabs, Table, TableCell, TableHeader, TableRow } from "@/src/components/ui";
import { useBp } from "@/src/design/responsive";
import { fmtMoneyCompact } from "@/src/design/tokens";
import { getSelectedFloorId, useFloorAccess } from "@/src/hooks/use-floor-access";
import { useAuth } from "@/src/state/auth";
import { colors, spacing, type } from "@/src/theme/tokens";

const LABELS: Record<WorkspaceName, { title: string; subtitle: string; rows: "brands" | "products" | "customers" | "relationships" | "floors" }> = {
  revenue: { title: "Revenue", subtitle: "Confirmed sales, dated by order confirmation", rows: "brands" },
  collections: { title: "Collections", subtitle: "What has been collected and what remains due", rows: "customers" },
  forecasting: { title: "Forecasting", subtitle: "Conservative forecast from completed sales history", rows: "floors" },
  customers: { title: "Customers", subtitle: "Customers ranked by confirmed revenue", rows: "customers" },
  architects: { title: "Architects", subtitle: "Architects with attributed confirmed revenue", rows: "relationships" },
  "interior-designers": { title: "Interior Designers", subtitle: "Interior designers with attributed confirmed revenue", rows: "relationships" },
  relationships: { title: "Relationships", subtitle: "Referred customer relationships and generated revenue", rows: "relationships" },
  products: { title: "Products", subtitle: "Products ranked by net confirmed revenue", rows: "products" },
  brands: { title: "Brands", subtitle: "Brand contribution to confirmed revenue", rows: "brands" },
  suppliers: { title: "Suppliers", subtitle: "Sales contribution from available product attribution", rows: "brands" },
  operations: { title: "Operations", subtitle: "Confirmed-order workload by business unit", rows: "floors" },
};
const PRESETS = [{ value: "today", label: "Today" }, { value: "this_week", label: "This week" }, { value: "this_month", label: "This month" }, { value: "last_month", label: "Last month" }, { value: "quarter", label: "Quarter" }, { value: "year", label: "Year" }];

export function OwnerWorkspace({ workspace }: { workspace: WorkspaceName }) {
  const { staff } = useAuth(); const { floors } = useFloorAccess(); const router = useRouter(); const { isPhone, isTablet } = useBp();
  const [floorId, setFloorId] = useState(""); const [preset, setPreset] = useState("this_month"); const [data, setData] = useState<WorkspaceData | null>(null); const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (!floorId) void getSelectedFloorId().then((id) => setFloorId(id || "all")); }, [floorId]);
  const load = useCallback(() => { if (!floorId) return; setError(null); setData(null); salesWorkspaceApi.get(workspace, { floorId, preset }).then(setData).catch((e: any) => setError(e?.detail || "Could not load this workspace")); }, [workspace, floorId, preset]);
  useEffect(() => { load(); }, [load]);
  if (staff && staff.role !== "owner") return <Redirect href="/(admin)/sales-data" />;
  const meta = LABELS[workspace]; const cardStyle = isPhone ? { width: "100%" as const } : isTablet ? { width: "48%" as const } : { flex: 1, minWidth: 180 };
  return <AdminPage title={meta.title} subtitle={data ? `${meta.subtitle} · ${data.period}` : meta.subtitle}>
    <View style={{ gap: spacing.sm }}><Text style={type.overline}>Period</Text><PillTabs value={preset} onChange={setPreset} options={PRESETS} /></View>
    <View style={{ gap: spacing.sm }}><Text style={type.overline}>Business unit</Text><PillTabs value={floorId || "all"} onChange={setFloorId} options={[{ value: "all", label: "All units" }, ...floors.map((f) => ({ value: f.id, label: f.name }))]} /></View>
    {error ? <ErrorState subtitle={error} onRetry={load} /> : null}
    {!error && !data ? <LoadingState label={`Loading ${meta.title.toLowerCase()}…`} /> : null}
    {data ? <>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
        <KpiCard label="Revenue" value={fmtMoneyCompact(data.kpis.revenue)} question="What did confirmed sales generate?" style={cardStyle} />
        <KpiCard label="Orders" value={String(data.kpis.orders)} question="How many confirmed sales are included?" style={cardStyle} />
        <KpiCard label="Outstanding" value={fmtMoneyCompact(data.kpis.outstanding)} question="What is still due on these sales?" tone="warning" style={cardStyle} />
        <KpiCard label="Hansgrohe" value={fmtMoneyCompact(data.kpis.hansgrohe_revenue)} question="How much revenue did Hansgrohe generate?" tone="brand" style={cardStyle} />
      </View>
      {workspace === "forecasting" ? <Forecast data={data} /> : null}
      <WorkspaceTable kind={meta.rows} data={data} phone={isPhone} onOpen={(path) => router.push(path as never)} />
    </> : null}
  </AdminPage>;
}

function Forecast({ data }: { data: WorkspaceData }) { const forecast = data.forecast; return <Card variant="flat" padding={spacing.xl}><View style={{ gap: spacing.sm }}><Text style={type.titleSm}>Conservative forecast</Text>{forecast?.forecast === null ? <Text style={[type.body, { color: colors.onSurfaceMuted }]}>At least three completed months of confirmed sales are needed before a forecast is shown.</Text> : <><Text style={type.displayMd}>{fmtMoneyCompact(forecast?.forecast || 0)}</Text><Text style={[type.caption, { color: colors.onSurfaceMuted }]}>Average of the prior three completed months: {forecast?.monthly_history.map(fmtMoneyCompact).join(" · ")}</Text></>}</View></Card>; }

function WorkspaceTable({ kind, data, phone, onOpen }: { kind: "brands" | "products" | "customers" | "relationships" | "floors"; data: WorkspaceData; phone: boolean; onOpen: (path: string) => void }) {
  const rows: any[] = kind === "brands" ? data.brands : kind === "products" ? data.products : kind === "customers" ? data.customers : kind === "relationships" ? (data.relationships || []) : data.floors;
  if (!rows.length) return <EmptyState icon="bar-chart-2" title="No confirmed sales in this period" subtitle="Try a different date range or business unit." tone="brand" />;
  const title = kind === "relationships" ? "Revenue relationships" : kind === "floors" ? "Business units" : `Top ${kind}`;
  return <Card variant="flat" padding={spacing.lg}><View style={{ gap: spacing.md }}><Text style={type.titleSm}>{title}</Text>{phone ? <View style={{ gap: spacing.sm }}>{rows.slice(0, 25).map((r) => <View key={r.id || r.brand_id || r.product_id || r.customer_id || r.floor_id} style={{ minHeight: 56, borderBottomWidth: 1, borderBottomColor: colors.border, justifyContent: "center" }}><Text style={type.bodyStrong}>{r.name || r.floor_id}</Text><Text style={[type.caption, { color: colors.onSurfaceMuted }]}>{fmtMoneyCompact(r.revenue)} · {r.orders || r.quantity || 0} orders</Text></View>)}</View> : <Table><TableHeader columns={[{ label: "Name", flex: 2 }, { label: "Revenue", align: "right" }, { label: "Orders", align: "right" }]} />{rows.slice(0, 50).map((r, i) => <TableRow key={r.id || r.brand_id || r.product_id || r.customer_id || r.floor_id} isLast={i === Math.min(rows.length, 50) - 1} onPress={r.customer_id ? () => onOpen(`/(admin)/customers/${r.customer_id}`) : undefined}><TableCell flex={2}>{r.name || r.floor_id}</TableCell><TableCell align="right">{fmtMoneyCompact(r.revenue)}</TableCell><TableCell align="right">{String(r.orders || r.quantity || 0)}</TableCell></TableRow>)}</Table>}</View></Card>;
}
