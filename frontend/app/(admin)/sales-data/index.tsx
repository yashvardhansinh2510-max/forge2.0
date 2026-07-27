import { Redirect } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { api } from "@/src/api/client";
import {
  EmptyState, ErrorState, LoadingState, PillTabs, SegmentedControl, Tabs,
} from "@/src/components/ui";
import { spacing } from "@/src/theme/tokens";
import { useAuth } from "@/src/state/auth";
import {
  DATE_PRESET_LABEL, DatePreset, Granularity, OverviewResponse, ReferredByFilter, presetToRange,
} from "@/src/components/salesData/salesDataApi";

type Floor = { id: string; name: string; slug: string };
type PageTab = "overview" | "brand";

export default function SalesData() {
  const { staff } = useAuth();

  // All hooks are declared unconditionally, in the same order every render —
  // the role check below is a plain `if` AFTER every hook call, never a
  // conditional `return` before one. An early return before a hook would
  // violate the Rules of Hooks: this component would call a different
  // number of hooks depending on `staff.role`, and React throws "Rendered
  // fewer hooks than expected" the next time it re-renders with a
  // different hook count.
  const [floors, setFloors] = useState<Floor[]>([]);
  const [floorId, setFloorId] = useState<string>("both");
  const [referredBy, setReferredBy] = useState<ReferredByFilter>("all");
  const [preset, setPreset] = useState<DatePreset>("this_month");
  const [granularity, setGranularity] = useState<Granularity>("month");
  const [tab, setTab] = useState<PageTab>("overview");

  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.get<Floor[]>("/settings/floors").then(setFloors).catch(() => setFloors([])); }, []);

  const load = useCallback(() => {
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

      {error ? <ErrorState subtitle={error} onRetry={load} /> : null}
      {!error && !overview ? <LoadingState label="Loading sales data…" /> : null}
      {!error && overview && overview.total_revenue === 0 ? (
        <EmptyState title="No sales in this range" subtitle="Try a wider date range or different filters." />
      ) : null}
      {/* Overview KPI cards, trend chart, and referrer list are added in Task 9-10.
          By Brand tab content is added in Task 11. */}
    </AdminPage>
  );
}
