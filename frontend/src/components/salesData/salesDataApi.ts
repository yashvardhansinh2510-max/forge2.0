import dayjs from "dayjs";

export type Granularity = "day" | "month" | "quarter" | "year";
export type ReferredByFilter = "all" | "architect" | "interior_designer";
export type DatePreset = "today" | "this_month" | "this_quarter" | "this_year" | "all_time";

export type TrendPoint = { bucket: string; revenue: number };
export type OverviewResponse = {
  total_revenue: number;
  quotation_count: number;
  revenue_by_floor: { floor_id: string; revenue: number }[];
  trend: TrendPoint[];
  referrers: { referrer_id: string; name: string; revenue: number }[] | null;
};

export function presetToRange(preset: DatePreset): { date_from: string | null; date_to: string | null } {
  const now = dayjs();
  if (preset === "today") return { date_from: now.startOf("day").toISOString(), date_to: now.endOf("day").toISOString() };
  if (preset === "this_month") return { date_from: now.startOf("month").toISOString(), date_to: now.endOf("month").toISOString() };
  if (preset === "this_quarter") {
    const qStartMonth = Math.floor(now.month() / 3) * 3;
    const start = now.month(qStartMonth).startOf("month");
    return { date_from: start.toISOString(), date_to: start.add(3, "month").endOf("month").subtract(1, "month").endOf("month").toISOString() };
  }
  if (preset === "this_year") return { date_from: now.startOf("year").toISOString(), date_to: now.endOf("year").toISOString() };
  return { date_from: null, date_to: null }; // all_time
}

export const DATE_PRESET_LABEL: Record<DatePreset, string> = {
  today: "Today", this_month: "This Month", this_quarter: "This Quarter",
  this_year: "This Year", all_time: "All Time",
};
