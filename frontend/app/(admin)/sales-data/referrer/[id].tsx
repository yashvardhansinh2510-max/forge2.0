import { useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { api } from "@/src/api/client";
import {
  EmptyState, ErrorState, LoadingState, PillTabs, Table, TableCell, TableHeader, TableRow,
} from "@/src/components/ui";
import { fmtMoney } from "@/src/design/tokens";
import { spacing } from "@/src/theme/tokens";
import { TrendChart } from "@/src/components/salesData/TrendChart";
import {
  DATE_PRESET_LABEL, DatePreset, Granularity, presetToRange,
} from "@/src/components/salesData/salesDataApi";

type ReferrerDetailResponse = {
  referrer: { id: string; name: string; type: string; phone?: string | null; company?: string | null };
  total_revenue: number;
  trend: { bucket: string; revenue: number }[];
  quotations: { id: string; number: string; customer_name: string; grand_total: number; updated_at: string | null }[];
};

export default function ReferrerDetail() {
  const { id, preset: presetParam, floorId } = useLocalSearchParams<{ id: string; preset?: string; floorId?: string }>();
  const preset: DatePreset = presetParam && presetParam in DATE_PRESET_LABEL ? (presetParam as DatePreset) : "this_month";
  const [granularity, setGranularity] = useState<Granularity>("month");
  const [data, setData] = useState<ReferrerDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { date_from, date_to } = presetToRange(preset);

  const load = useCallback(() => {
    setError(null);
    setData(null);
    const params = new URLSearchParams();
    params.set("granularity", granularity);
    if (floorId && floorId !== "both") params.set("floor_id", floorId);
    if (date_from) params.set("date_from", date_from);
    if (date_to) params.set("date_to", date_to);
    api.get<ReferrerDetailResponse>(`/sales-data/referrers/${id}?${params.toString()}`)
      .then(setData)
      .catch((e: any) => setError(e?.detail || "Could not load referrer"));
  }, [id, granularity, date_from, date_to, floorId]);

  useEffect(() => { load(); }, [load]);

  return (
    <AdminPage
      title={data?.referrer.name || "Referrer"}
      subtitle={data ? `₹${fmtMoney(data.total_revenue)} total revenue · ${DATE_PRESET_LABEL[preset]}` : undefined}
    >
      <PillTabs
        testID="referrer-detail-granularity"
        value={granularity}
        onChange={setGranularity}
        options={[
          { value: "day", label: "Day" }, { value: "month", label: "Month" },
          { value: "quarter", label: "Quarter" }, { value: "year", label: "Year" },
        ]}
      />
      {error ? <ErrorState subtitle={error} onRetry={load} /> : null}
      {!error && !data ? <LoadingState label="Loading…" /> : null}
      {data ? (
        <View style={{ gap: spacing.lg }}>
          <TrendChart points={data.trend} />
          {data.quotations.length === 0 ? (
            <EmptyState title="No won quotations in this range" />
          ) : (
            <Table>
              <TableHeader columns={[
                { label: "Number", flex: 1 }, { label: "Customer", flex: 2 }, { label: "Amount", align: "right" },
              ]} />
              {data.quotations.map((q, i) => (
                <TableRow key={q.id} isLast={i === data.quotations.length - 1} testID={`referrer-quote-row-${q.id}`}>
                  <TableCell flex={1}>{q.number}</TableCell>
                  <TableCell flex={2}>{q.customer_name}</TableCell>
                  <TableCell align="right">₹{fmtMoney(q.grand_total)}</TableCell>
                </TableRow>
              ))}
            </Table>
          )}
        </View>
      ) : null}
    </AdminPage>
  );
}
