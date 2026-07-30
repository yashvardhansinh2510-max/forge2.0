// frontend/src/api/tileOrders.ts
// Typed client for the /tile-orders backend router (see
// backend/routes/tile_orders.py). Mirrors the thin api.get/post pattern
// already used throughout the app (@/src/api/client) — no separate fetch
// layer, just typed wrappers around it.
//
// Tile Orders workflow redesign (2026-08): the UI is organised around
// Brands, Customers and Material Movement — NOT Purchase Orders/Company.
// The Brand page's only action is Release Material. The Customer page
// decides Move to Godown vs. Dispatch (from Released or from Godown) and
// is the only place a Chalan/PDF is ever generated. Boxes are the one
// operational unit everywhere — the underlying `qty`/`boxes_*` field names
// are unchanged for backend compatibility, this file just labels them.
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
  boxes_ordered: number; boxes_ready: number; boxes_godown: number; boxes_dispatched: number; boxes_pending: number;
  current_location: TileLocation; overall_status: TileOverallStatus;
};

export type CustomerOrderBrandGroup = {
  purchase_order_id: string; supplier_name: string; brand_id: string | null; brand_name: string;
  overall_status: TileOverallStatus; items: CustomerOrderItem[];
};

export type CustomerOrderDetail = {
  summary: {
    id: string; number: string; customer_name: string; order_date: string; brand_count: number;
    total_products: number; total_boxes: number; completion_percentage: number;
    waiting_days: number; ageing_band: AgeingBand; overall_status: TileOverallStatus;
  };
  // Backend response key stays "suppliers" for wire-compat, but every group
  // now also carries brand_id/brand_name — the Customer Detail screen
  // groups and labels by BRAND, never by dealer/supplier company.
  suppliers: CustomerOrderBrandGroup[];
};

export type BrandLandingCard = { brand_id: string | null; brand_name: string; active_orders: number; max_supplier_silent_days: number };

export type BrandOrderRow = {
  po_id: string; po_number: string; customer_id: string; customer_name: string; order_date: string;
  arrival_date: string; waiting_days: number; ageing_band: AgeingBand; total_products: number; total_boxes: number;
  boxes_released: number; boxes_remaining: number; overall_status: TileOverallStatus; completion_percentage: number;
};

export type BrandOrdersKpi = {
  orders: number; pending: number; ready: number; partially_dispatched: number; completed: number;
  boxes_remaining: number; boxes_released: number; boxes_dispatched: number; oldest_pending_days: number;
};

export type PurchaseOrderItemDetail = {
  id: string; name: string; series: string | null; finish: string | null; size: string | null; sku: string | null;
  qty: number; boxes_ready: number; boxes_godown: number; boxes_dispatched: number; boxes_pending: number;
  current_location: TileLocation; overall_status: TileOverallStatus;
};

export type PurchaseOrderDetail = {
  id: string; number: string; customer_name: string; supplier_name: string | null;
  brand_id: string | null; brand_name: string | null;
  overall_status: TileOverallStatus; items: PurchaseOrderItemDetail[];
  delivery_name: string; delivery_phone: string; delivery_address: string; delivery_city: string;
};

export type MaterialMovementType =
  | "order_created" | "release" | "move_to_godown"
  | "dispatch_from_released" | "dispatch_from_godown" | "delivered";

export type MaterialMovementRow = {
  id: string; movement_type: MaterialMovementType; created_at: string;
  purchase_order_id: string; po_item_id: string | null; customer_id: string | null; customer_name: string;
  brand_id: string | null; brand_name: string; tile_name: string; series: string | null; finish: string | null;
  size: string | null; sku: string | null; boxes: number; source: string | null; destination: string | null;
  dispatch_id: string | null; dispatch_number: string | null; chalan_id: string | null; chalan_number: string | null;
  performed_by_name: string;
};

export type DispatchListRow = {
  dispatch_id: string; dispatch_number: string; dispatch_date: string;
  customer_id: string | null; customer_name: string; customer_order_id: string | null;
  brand_id: string | null; brand_name: string;
  tile_name: string; tile_size: string | null; boxes: number;
  source: "Released" | "Godown";
  chalan_id: string; chalan_number: string;
  vehicle_number: string | null; driver_name: string | null;
  status: "Dispatched" | "At Godown" | "Delivered";
  performed_by_name: string;
};

export type TileOrdersDashboard = {
  customer_orders: number; supplier_orders: number; dispatched_today: number; delivered_today: number;
  pending: number; ready: number; waiting_over_15_days: number; boxes_ordered: number; boxes_pending: number; revenue: number;
};

export type MovementItemInput = { po_item_id: string; qty: number };
export type DispatchDestinationOverride = {
  destination_name?: string; destination_address?: string; destination_city?: string;
  reference_number?: string; receiver_name?: string; sender_name?: string;
};

// No hardcoded floorId here — `api.get/post` already falls back to whatever
// floor is currently selected in the app's global floor switcher (see
// src/api/client.ts). Hardcoding "ground-floor" would silently break the
// module the moment someone switches floors.
export const tileOrdersApi = {
  // ---- Customer tab ----
  listCustomerOrders: (params?: { page?: number; page_size?: number; sort?: string; status?: string; search?: string }) =>
    api.get<{ orders: CustomerOrderCard[]; page: number; page_size: number; total: number }>(
      `/tile-orders/customer-orders${toQuery(params)}`,
    ),
  customerOrderDetail: (id: string) => api.get<CustomerOrderDetail>(`/tile-orders/customer-orders/${id}`),
  customerOrderTimeline: (id: string) => api.get<{ events: Record<string, any>[] }>(`/tile-orders/customer-orders/${id}/timeline`),

  // ---- Brands tab ----
  listBrands: () => api.get<{ brands: BrandLandingCard[] }>("/tile-orders/brands"),
  brandOrders: (brandId: string, params?: { page?: number; page_size?: number; sort?: string; status?: string; search?: string }) =>
    api.get<{ kpi: BrandOrdersKpi; orders: BrandOrderRow[]; page: number; page_size: number; total: number }>(
      `/tile-orders/brands/${brandId}/orders${toQuery(params)}`,
    ),
  purchaseOrderDetail: (poId: string) => api.get<PurchaseOrderDetail>(`/tile-orders/purchase-orders/${poId}`),

  // ---- Brand page's ONLY action ----
  releaseMaterial: (poId: string, items: MovementItemInput[]) =>
    api.post<{ po_id: string; ready_batches: Record<string, any>[]; overall_status: TileOverallStatus }>(
      `/tile-orders/purchase-orders/${poId}/ready`, { items },
    ),

  // ---- Customer page actions (BuildCon decides Godown vs. Dispatch) ----
  moveToGodown: (poId: string, items: MovementItemInput[]) =>
    api.post<{ po_id: string; moved: Record<string, any>[] }>(
      `/tile-orders/purchase-orders/${poId}/items/move-to-godown`, { items },
    ),
  dispatchFromReleased: (poId: string, items: MovementItemInput[], destination?: DispatchDestinationOverride) =>
    api.post<{ po_id: string; dispatch: Record<string, any>; chalan: Record<string, any>; overall_status: TileOverallStatus }>(
      `/tile-orders/purchase-orders/${poId}/dispatch-from-released`, { items, ...destination },
    ),
  dispatchFromGodown: (poId: string, items: MovementItemInput[], destination?: DispatchDestinationOverride) =>
    api.post<{ po_id: string; dispatch: Record<string, any>; chalan: Record<string, any>; overall_status: TileOverallStatus }>(
      `/tile-orders/purchase-orders/${poId}/dispatch-from-godown`, { items, ...destination },
    ),
  chalanPdfUrl: (chalanId: string) => api.authenticatedUrl(`/tile-orders/chalans/${chalanId}/pdf`),

  // ---- Material Movement Register ----
  listMovements: (params?: {
    customer_id?: string; brand_id?: string; movement_type?: string; date_from?: string; date_to?: string;
    chalan_number?: string; dispatch_number?: string; search?: string; page?: number; page_size?: number;
  }) => api.get<{ rows: MaterialMovementRow[]; page: number; page_size: number; total: number }>(
    `/tile-orders/movements${toQuery(params)}`,
  ),

  itemHistory: (itemId: string) => api.get<{ item_id: string; events: Record<string, any>[] }>(`/tile-orders/items/${itemId}/history`),
  dashboard: () => api.get<TileOrdersDashboard>("/tile-orders/dashboard"),

  // ---- Dispatch List (operational, dispatch-only) ----
  listDispatchList: (params?: {
    customer_id?: string; brand_id?: string; product?: string; dispatch_number?: string;
    chalan_number?: string; status?: string; date_from?: string; date_to?: string;
    search?: string; page?: number; page_size?: number;
  }) => api.get<{ rows: DispatchListRow[]; page: number; page_size: number; total: number }>(
    `/tile-orders/dispatches${toQuery(params)}`,
  ),
};

function toQuery(params?: Record<string, string | number | undefined>): string {
  if (!params) return "";
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (entries.length === 0) return "";
  return "?" + entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&");
}
