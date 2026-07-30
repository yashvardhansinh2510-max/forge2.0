// frontend/src/api/tileOrders.ts
// Typed client for the /tile-orders backend router (see
// backend/routes/tile_orders.py). Mirrors the thin api.get/post pattern
// already used throughout the app (@/src/api/client) — no separate fetch
// layer, just typed wrappers around it.
import { api } from "@/src/api/client";

export type TileOverallStatus = "Pending" | "Ready" | "Partially Dispatched" | "Dispatched" | "Delivered";
export type TileLocation = "Pending" | "Ready" | "Dispatched" | "Godown" | "Delivered";
export type AgeingBand = "green" | "amber" | "red";

export type CustomerOrderBrand = { brand_id: string | null; brand_name: string; supplier_id: string | null; supplier_name: string; purchase_order_id: string; status: TileOverallStatus };

export type CustomerOrderCard = {
  id: string; number: string; customer_name: string; customer_phone: string | null;
  order_date: string; waiting_days: number; ageing_band: AgeingBand;
  brands: CustomerOrderBrand[]; total_products: number; total_boxes: number; total_value: number;
  overall_status: TileOverallStatus; completion_percentage: number;
};

export type CustomerOrderItem = {
  po_item_id: string; tile_name: string; series: string | null; finish: string | null; size: string | null;
  boxes_ordered: number; boxes_ready: number; boxes_dispatched: number; boxes_pending: number;
  current_location: TileLocation; overall_status: TileOverallStatus;
};

export type CustomerOrderSupplierGroup = { purchase_order_id: string; supplier_name: string; overall_status: TileOverallStatus; items: CustomerOrderItem[] };

export type CustomerOrderDetail = {
  summary: {
    id: string; number: string; customer_name: string; order_date: string; brand_count: number;
    total_products: number; total_boxes: number; completion_percentage: number;
    waiting_days: number; ageing_band: AgeingBand; overall_status: TileOverallStatus;
  };
  suppliers: CustomerOrderSupplierGroup[];
};

export type SupplierLandingCard = { supplier_id: string | null; supplier_name: string; active_orders: number; max_supplier_silent_days: number };

export type SupplierOrderRow = {
  po_id: string; po_number: string; customer_id: string; customer_name: string; order_date: string;
  waiting_days: number; ageing_band: AgeingBand; total_products: number; total_boxes: number;
  overall_status: TileOverallStatus; completion_percentage: number;
};

export type SupplierOrdersKpi = {
  orders: number; pending: number; ready: number; partially_dispatched: number; completed: number;
  boxes_pending: number; boxes_ready: number; boxes_dispatched: number; oldest_pending_days: number;
};

export type SupplierAnalytics = {
  orders: number; waiting_avg_days: number; ready_time_avg_days: number; dispatch_time_avg_days: number;
  fulfilment_time_avg_days: number; oldest_pending_days: number; completion_percentage_avg: number;
};

export type PurchaseOrderItemDetail = {
  id: string; name: string; series: string | null; finish: string | null; size: string | null; sku: string | null;
  qty: number; boxes_ready: number; boxes_dispatched: number; boxes_pending: number;
  current_location: TileLocation; overall_status: TileOverallStatus;
};

export type PurchaseOrderDetail = {
  id: string; number: string; customer_name: string; supplier_name: string | null;
  overall_status: TileOverallStatus; items: PurchaseOrderItemDetail[];
};

export type ReadyBatch = { id: string; batch_number: string; po_item_id: string; qty: number; remaining_qty: number; created_at: string };

export type DispatchPreviewLine = { po_item_id: string; tile_name: string; qty: number; source: "existing" | "pending"; remaining_pending_after: number };
export type DispatchPreview = { po_id: string; items: DispatchPreviewLine[]; warnings: string[]; will_create: { dispatch_number: string; chalan_number: string; creates_dispatch_list_entry: boolean } };

export type DispatchLineInput = { po_item_id: string; ready_batch_id: string | null; qty: number };
export type DispatchDestination = { destination_type: "Customer" | "Godown"; destination_name: string; destination_address: string; destination_city: string; reference_number?: string; receiver_name?: string; sender_name?: string };

export type DispatchListRow = { dispatch_number: string; chalan_number: string; customer_name: string; supplier_name: string; tile_name: string; tile_size: string | null; boxes: number; dispatch_date: string; destination: string; status: "Dispatched" | "At Godown" | "Delivered" };

export type TileOrdersDashboard = {
  customer_orders: number; supplier_orders: number; dispatched_today: number; delivered_today: number;
  pending: number; ready: number; waiting_over_15_days: number; boxes_ordered: number; boxes_pending: number; revenue: number;
};

const FLOOR = { floorId: "ground-floor" };

export const tileOrdersApi = {
  listCustomerOrders: (params?: { page?: number; page_size?: number; sort?: string; status?: string; search?: string }) =>
    api.get<{ orders: CustomerOrderCard[]; page: number; page_size: number; total: number }>(
      `/tile-orders/customer-orders${toQuery(params)}`, FLOOR,
    ),
  customerOrderDetail: (id: string) => api.get<CustomerOrderDetail>(`/tile-orders/customer-orders/${id}`, FLOOR),
  customerOrderTimeline: (id: string) => api.get<{ events: Record<string, any>[] }>(`/tile-orders/customer-orders/${id}/timeline`, FLOOR),

  listSuppliers: () => api.get<{ suppliers: SupplierLandingCard[] }>("/tile-orders/suppliers", FLOOR),
  supplierOrders: (supplierId: string, params?: { page?: number; page_size?: number; sort?: string; status?: string; search?: string }) =>
    api.get<{ kpi: SupplierOrdersKpi; orders: SupplierOrderRow[]; page: number; page_size: number; total: number }>(
      `/tile-orders/suppliers/${supplierId}/orders${toQuery(params)}`, FLOOR,
    ),
  supplierAnalytics: (supplierId: string) => api.get<SupplierAnalytics>(`/tile-orders/suppliers/${supplierId}/analytics`, FLOOR),

  purchaseOrderDetail: (poId: string) => api.get<PurchaseOrderDetail>(`/tile-orders/purchase-orders/${poId}`, FLOOR),
  markItemsReady: (poId: string, items: { po_item_id: string; qty: number }[]) =>
    api.post<{ po_id: string; ready_batches: ReadyBatch[]; overall_status: TileOverallStatus }>(
      `/tile-orders/purchase-orders/${poId}/ready`, { items }, FLOOR,
    ),
  previewDispatch: (poId: string, items: DispatchLineInput[], destination: DispatchDestination) =>
    api.post<DispatchPreview>(`/tile-orders/purchase-orders/${poId}/dispatch/preview`, { items, ...destination }, FLOOR),
  commitDispatch: (poId: string, items: DispatchLineInput[], destination: DispatchDestination) =>
    api.post<{ po_id: string; dispatch: Record<string, any>; chalan: Record<string, any>; overall_status: TileOverallStatus }>(
      `/tile-orders/purchase-orders/${poId}/dispatch`, { items, ...destination }, FLOOR,
    ),
  itemReadyBatches: (poId: string, itemId: string) => api.get<{ batches: ReadyBatch[] }>(`/tile-orders/purchase-orders/${poId}/items/${itemId}/ready-batches`, FLOOR),
  markGodownReceived: (dispatchId: string, note?: string) =>
    api.post<{ dispatch_id: string; godown_received_at: string }>(`/tile-orders/dispatches/${dispatchId}/godown-received`, { note }, FLOOR),

  listDispatches: (params?: Record<string, string | number | undefined>) =>
    api.get<{ rows: DispatchListRow[]; page: number; page_size: number; total: number }>(`/tile-orders/dispatches${toQuery(params)}`, FLOOR),
  itemHistory: (itemId: string) => api.get<{ item_id: string; events: Record<string, any>[] }>(`/tile-orders/items/${itemId}/history`, FLOOR),
  dashboard: () => api.get<TileOrdersDashboard>("/tile-orders/dashboard", FLOOR),
};

function toQuery(params?: Record<string, string | number | undefined>): string {
  if (!params) return "";
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (entries.length === 0) return "";
  return "?" + entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&");
}
