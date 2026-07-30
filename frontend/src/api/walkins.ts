// Walk-ins — Phase 4 (2026-07-30). Thin typed API client, same shape as
// src/api/tileOrders.ts.
import { api } from "@/src/api/client";

function toQuery(params?: Record<string, any>): string {
  if (!params) return "";
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

export type WalkInStatus =
  | "new" | "contacted" | "selection_scheduled" | "selection_completed"
  | "quotation_created" | "converted" | "lost";

export type WalkIn = {
  id: string; number: string; customer_id: string; customer_name: string;
  customer_phone: string | null; alternate_phone: string | null; visited_at: string;
  salesperson_id: string | null; salesperson_name: string | null; source: string;
  floor_id: string; interested_products: string[]; budget: number | null; notes: string | null;
  manual_priority_override: "low" | "medium" | "high" | "critical" | null;
  status: WalkInStatus; next_followup_at: string | null; lost_reason: string | null;
  selection_quotation_id: string | null; converted_at: string | null;
  created_at: string; updated_at: string;
};

export type WalkInsDashboard = {
  today_walkins: number; this_week: number; pending_followups: number;
  selections_scheduled: number; converted: number; lost: number;
  conversion_rate: number; avg_conversion_days: number; total: number;
};

export type WalkInsAnalytics = {
  funnel: { walk_ins: number; selections: number; quotations: number; orders: number };
  conversion_rate_pct: number; lost_leads: number; revenue_generated: number; revenue_lost: number;
  salesperson_performance: { salesperson: string; walkins: number; converted: number; lost: number }[];
};

export const walkinsApi = {
  list: (params?: {
    status?: string; priority?: string; salesperson_id?: string; source?: string; floor_id?: string;
    date_from?: string; date_to?: string; search?: string;
  }) => api.get<WalkIn[]>(`/walkins${toQuery(params)}`),

  get: (id: string) => api.get<WalkIn>(`/walkins/${id}`),

  create: (body: {
    customer_name: string; customer_phone: string; alternate_phone?: string; email?: string;
    visited_at?: string; salesperson_id?: string; source: string; floor_id: string;
    interested_products?: string[]; budget?: number; notes?: string;
    priority?: "low" | "medium" | "high" | "critical"; next_followup_at?: string;
  }) => api.post<WalkIn>("/walkins", body),

  update: (id: string, body: Partial<{
    status: WalkInStatus; salesperson_id: string; notes: string;
    manual_priority_override: "low" | "medium" | "high" | "critical";
    next_followup_at: string; lost_reason: string; alternate_phone: string;
    budget: number; interested_products: string[];
  }>) => api.patch<WalkIn>(`/walkins/${id}`, body),

  contact: (id: string, channel: "whatsapp" | "email") =>
    api.post<{ channel: string; message?: string; wa_url?: string; subject?: string; body?: string; mailto_url?: string }>(
      `/walkins/${id}/contact?channel=${channel}`,
    ),

  timeline: (id: string) => api.get<Record<string, any>[]>(`/walkins/${id}/timeline`),

  checkDuplicate: (phone?: string, alternatePhone?: string) =>
    api.get<{ customer: Record<string, any> | null }>(`/walkins/check-duplicate${toQuery({ phone, alternate_phone: alternatePhone })}`),

  dashboard: () => api.get<WalkInsDashboard>("/walkins/dashboard"),
  analytics: () => api.get<WalkInsAnalytics>("/walkins/analytics"),

  listSources: () => api.get<{ sources: string[] }>("/walkins/config/sources"),
  updateSources: (sources: string[]) => api.put<{ sources: string[] }>("/walkins/config/sources", { sources }),

  listAssignees: () => api.get<{ id: string; full_name: string; role: string }[]>("/followups/config/assignees"),
};
