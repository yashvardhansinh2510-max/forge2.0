import { api } from "@/src/api/client";

export type PurchaseStage =
  | "order_in_company" | "company_billing" | "in_box"
  | "dispatched" | "in_transit" | "delivered";

export type PurchaseItem = {
  item_id: string;
  po_id: string;
  po_number: string;
  quotation_id?: string | null;
  quotation_number?: string | null;
  product_id: string;
  sku: string;
  name: string;
  image?: string | null;
  customer_id: string;
  customer_name: string;
  brand_id: string;
  brand_name: string;
  supplier_id?: string | null;
  supplier_name?: string | null;
  stage: PurchaseStage;
  stage_label: string;
  stage_tone: { bg: string; fg: string };
  qty: number;
  unit_cost: number;
  room?: string | null;
  last_moved_at: string;
  last_moved_by_name: string | null;
  age_days: number;
  blocked: boolean;
  sla_days: number;
};

export type PurchasesPage = {
  items: PurchaseItem[];
  total: number;
  has_more: boolean;
  next_skip: number | null;
  summaries: {
    sla_days: number;
    blocked_count: number;
    stage_counts: Partial<Record<PurchaseStage, number>>;
  };
};

export type PurchasesPageQuery = {
  view: "today" | "stock" | "customers" | "dispatch_record";
  brand?: string;
  stage?: PurchaseStage | "";
  q?: string;
  skip?: number;
  limit?: number;
};

export function purchasesPagePath(query: PurchasesPageQuery): string {
  const params = new URLSearchParams({
    view: query.view,
    skip: String(query.skip ?? 0),
    limit: String(query.limit ?? 30),
  });
  if (query.brand && query.brand !== "all") params.set("brand", query.brand);
  if (query.stage) params.set("stage", query.stage);
  if (query.q?.trim()) params.set("q", query.q.trim());
  return `/purchases/items/page?${params.toString()}`;
}

export function getPurchasesPage(query: PurchasesPageQuery, signal?: AbortSignal) {
  return api.get<PurchasesPage>(purchasesPagePath(query), { signal });
}
