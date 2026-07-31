import { Redirect, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { api } from "@/src/api/client";
import {
  EmptyState, ErrorState, KpiCard, LoadingState, PillTabs, SegmentedControl, Table, TableCell,
  TableHeader, TableRow, Tabs,
} from "@/src/components/ui";
import { fmtMoney, fmtMoneyCompact } from "@/src/design/tokens";
import { spacing } from "@/src/theme/tokens";
import { useAuth } from "@/src/state/auth";
import { getSelectedFloorId } from "@/src/hooks/use-floor-access";
import { TrendChart } from "@/src/components/salesData/TrendChart";
import {
  DATE_PRESET_LABEL, DatePreset, Granularity, OverviewResponse, ReferredByFilter, presetToRange,
} from "@/src/components/salesData/salesDataApi";

type Floor = { id: string; name: string; slug: string };
type PageTab = "overview" | "brand";
type BrandRow = { brand_id: string; brand_name: string; revenue: number };

export default function SalesData() {
  const { staff } = useAuth();
  const router = useRouter();

  // All hooks are declared unconditionally, in the same order every render —
  // the role check below is a plain `if` AFTER every hook call, never a
  // conditional `return` before one. An early return before a hook would
  // violate the Rules of Hooks: this component would call a different
  // number of hooks depending on `staff.role`, and React throws "Rendered
  // fewer hooks than expected" the next time it re-renders with a
  // different hook count.
  const [floors, setFloors] = useState<Floor[]>([]);
  // Defaults to the business unit currently active in the shell, not to the
  // company-wide "Both" roll-up: Sales Data is a per-floor screen for the
  // floor you are working in. "Both" stays available as an explicit,
  // deliberate choice for owner/admin company-wide reporting.
  const [floorId, setFloorId] = useState<string>("");
  useEffect(() => { void getSelectedFloorId().then((id) => setFloorId(id || "both")); }, []);
  const [referredBy, setReferredBy] = useState<ReferredByFilter>("all");
  const [preset, setPreset] = useState<DatePreset>("this_month");
  const [granularity, setGranularity] = useState<Granularity>("month");
  const [tab, setTab] = useState<PageTab>("overview");

  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [brands, setBrands] = useState<BrandRow[] | null>(null);
  const [brandsError, setBrandsError] = useState<string | null>(null);

  useEffect(() => { api.get<Floor[]>("/settings/floors").then(setFloors).catch(() => setFloors([])); }, []);

  const load = useCallback(() => {
    if (!floorId) return; // active floor not resolved yet — never query unscoped
    setError(null);
    setOverview(null);
    const { date_from, date_to } = presetToRange(preset);
    const params = new URLSearchParams();
    if (floorId !== "both") params.set("floor_id", floorId);
    if (referredBy !== "all") params.set("referrer_type", referredBy);
    if (date_from) params.set("date_from", date_from);
    if (date_to) params.set("date_to", date_to);
    params.set("granularity", granularity);
    api.get<OverviewResponse>(`/sales-data/overview?${params.toString()}`)
      .then(setOverview)
      .catch((e: any) => setError(e?.detail || "Could not load sales data"));
  }, [floorId, referredBy, preset, granularity]);

  useEffect(() => { load(); }, [load]);

  const loadBrands = useCallback(() => {
    if (!floorId) return; // see load()
    setBrandsError(null);
    setBrands(null);
    const { date_from, date_to } = presetToRange(preset);
    const params = new URLSearchParams();
    if (floorId !== "both") params.set("floor_id", floorId);
    if (date_from) params.set("date_from", date_from);
    if (date_to) params.set("date_to", date_to);
    api.get<{ brands: BrandRow[] }>(`/sales-data/brands?${params.toString()}`)
      .then((res) => setBrands(res.brands))
      .catch((e: any) => setBrandsError(e?.detail || "Could not load brand revenue"));
  }, [preset, floorId]);

  useEffect(() => {
    if (tab !== "brand") return;
    loadBrands();
  }, [tab, loadBrands]);

  if (staff && staff.role !== "owner" && staff.role !== "admin") {
    return <Redirect href="/(admin)/dashboard" />;
  }

  return (
    <AdminPage title="Sales Data" subtitle="Every sale, filtered by floor, referrer, and brand">
      <View style={{ gap: spacing.md }}>
        <SegmentedControl
          testID="sales-data-floor"
          value={floorId}
          onChange={setFloorId}
          options={[
            { value: "both", label: "Both" },
            ...floors.map((f) => ({ value: f.id, label: f.name })),
          ]}
        />
        <PillTabs
          testID="sales-data-referred-by"
          value={referredBy}
          onChange={setReferredBy}
          options={[
            { value: "all", label: "All" },
            { value: "architect", label: "Architect" },
            { value: "interior_designer", label: "Interior Designer" },
          ]}
        />
        <PillTabs
          testID="sales-data-preset"
          value={preset}
          onChange={setPreset}
          options={(Object.keys(DATE_PRESET_LABEL) as DatePreset[]).map((p) => ({ value: p, label: DATE_PRESET_LABEL[p] }))}
        />
        <SegmentedControl
          testID="sales-data-granularity"
          value={granularity}
          onChange={setGranularity}
          options={[
            { value: "day", label: "Day" }, { value: "month", label: "Month" },
            { value: "quarter", label: "Quarter" }, { value: "year", label: "Year" },
          ]}
        />
      </View>

      <Tabs
        testID="sales-data-tabs"
        value={tab}
        onChange={setTab}
        options={[{ value: "overview", label: "Overview" }, { value: "brand", label: "By Brand" }]}
      />

      {tab === "overview" && error ? <ErrorState subtitle={error} onRetry={load} /> : null}
      {tab === "overview" && !error && !overview ? <LoadingState label="Loading sales data…" /> : null}
      {tab === "overview" && !error && overview && overview.total_revenue === 0 ? (
        <EmptyState title="No sales in this range" subtitle="Try a wider date range or different filters." />
      ) : null}
      {!error && overview && overview.total_revenue > 0 && tab === "overview" ? (
        <View style={{ gap: spacing.lg }}>
          <View style={{ flexDirection: "row", gap: spacing.md, flexWrap: "wrap" }}>
            {referredBy === "all" ? (
              <>
                <KpiCard label="Total Revenue" value={`₹${fmtMoneyCompact(overview.total_revenue)}`} style={{ flex: 1, minWidth: 160 }} />
                {overview.revenue_by_floor.map((f) => {
                  const floor = floors.find((fl) => fl.id === f.floor_id);
                  return (
                    <KpiCard
                      key={f.floor_id}
                      label={floor?.name || f.floor_id}
                      value={`₹${fmtMoneyCompact(f.revenue)}`}
                      style={{ flex: 1, minWidth: 160 }}
                    />
                  );
                })}
              </>
            ) : (
              // Referrer type selected — KPIs re-scope IN PLACE (same row,
              // same position) rather than the page restructuring, per the
              // approved design: Architect/Interior Designer Revenue, how
              // many people contributed, and the average deal size.
              <>
                <KpiCard
                  label={referredBy === "architect" ? "Architect Revenue" : "Interior Designer Revenue"}
                  value={`₹${fmtMoneyCompact(overview.total_revenue)}`}
                  style={{ flex: 1, minWidth: 160 }}
                />
                <KpiCard
                  label="# Active"
                  value={String(overview.referrers?.length || 0)}
                  style={{ flex: 1, minWidth: 160 }}
                />
                <KpiCard
                  label="Avg Deal Size"
                  value={`₹${fmtMoneyCompact(overview.quotation_count ? overview.total_revenue / overview.quotation_count : 0)}`}
                  style={{ flex: 1, minWidth: 160 }}
                />
              </>
            )}
          </View>
          <TrendChart points={overview.trend} />
          {overview.referrers ? (
            <Table>
              <TableHeader columns={[{ label: "Name", flex: 2 }, { label: "Revenue", align: "right" }]} />
              {overview.referrers.map((r, i) => (
                <TableRow
                  key={r.referrer_id}
                  isLast={i === overview.referrers!.length - 1}
                  onPress={() => router.push(`/(admin)/sales-data/referrer/${r.referrer_id}?preset=${preset}&floorId=${floorId}` as any)}
                  testID={`referrer-rank-row-${r.referrer_id}`}
                >
                  <TableCell flex={2}>{r.name}</TableCell>
                  <TableCell align="right">₹{fmtMoney(r.revenue)}</TableCell>
                </TableRow>
              ))}
            </Table>
          ) : null}
        </View>
      ) : null}

      {tab === "brand" ? (
        <View style={{ gap: spacing.lg }}>
          {brandsError ? <ErrorState subtitle={brandsError} onRetry={loadBrands} /> : null}
          {!brandsError && !brands ? <LoadingState label="Loading brand revenue…" /> : null}
          {brands && brands.length === 0 ? <EmptyState title="No brand revenue in this range" /> : null}
          {brands && brands.length > 0 ? (
            <Table>
              <TableHeader columns={[{ label: "Brand", flex: 2 }, { label: "Revenue", align: "right" }]} />
              {brands.map((b, i) => (
                <TableRow
                  key={b.brand_id}
                  isLast={i === brands.length - 1}
                  onPress={() => router.push(`/(admin)/sales-data/brand/${b.brand_id}?preset=${preset}&floorId=${floorId}` as any)}
                  testID={`brand-rank-row-${b.brand_id}`}
                >
                  <TableCell flex={2}>{b.brand_name}</TableCell>
                  <TableCell align="right">₹{fmtMoney(b.revenue)}</TableCell>
                </TableRow>
              ))}
            </Table>
          ) : null}
        </View>
      ) : null}
    </AdminPage>
  );
}
