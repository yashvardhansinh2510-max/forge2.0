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

type BrandDetailResponse = {
  brand: { id: string; name: string };
  total_revenue: number;
  trend: { bucket: string; revenue: number }[];
  top_products: { product_id: string; name: string; sku: string; revenue: number }[];
};

export default function BrandDetail() {
  const { id, preset: presetParam, floorId } = useLocalSearchParams<{ id: string; preset?: string; floorId?: string }>();
  const preset: DatePreset = presetParam && presetParam in DATE_PRESET_LABEL ? (presetParam as DatePreset) : "this_month";
  const [granularity, setGranularity] = useState<Granularity>("month");
  const [data, setData] = useState<BrandDetailResponse | null>(null);
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
    api.get<BrandDetailResponse>(`/sales-data/brands/${id}?${params.toString()}`)
      .then(setData)
      .catch((e: any) => setError(e?.detail || "Could not load brand"));
  }, [id, granularity, date_from, date_to, floorId]);

  useEffect(() => { load(); }, [load]);

  return (
    <AdminPage
      title={data?.brand.name || "Brand"}
      subtitle={data ? `₹${fmtMoney(data.total_revenue)} total revenue · ${DATE_PRESET_LABEL[preset]}` : undefined}
    >
      <PillTabs
        testID="brand-detail-granularity"
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
          {data.top_products.length === 0 ? (
            <EmptyState title="No product revenue in this range" />
          ) : (
            <Table>
              <TableHeader columns={[
                { label: "Product", flex: 2 }, { label: "SKU", flex: 1 }, { label: "Revenue", align: "right" },
              ]} />
              {data.top_products.map((p, i) => (
                <TableRow key={p.product_id} isLast={i === data.top_products.length - 1} testID={`brand-product-row-${p.product_id}`}>
                  <TableCell flex={2}>{p.name}</TableCell>
                  <TableCell flex={1}>{p.sku}</TableCell>
                  <TableCell align="right">₹{fmtMoney(p.revenue)}</TableCell>
                </TableRow>
              ))}
            </Table>
          )}
        </View>
      ) : null}
    </AdminPage>
  );
}
