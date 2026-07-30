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
  reference_contact: string | null; architect: string | null; builder: string | null;
  floor_id: string; interested_products: string[]; budget: number | null; notes: string | null;
  manual_priority_override: "low" | "medium" | "high" | "critical" | null;
  status: WalkInStatus; next_followup_at: string | null; lost_reason: string | null;
  selection_quotation_id: string | null; converted_at: string | null;
  created_at: string; updated_at: string;
};

export type CustomerMatch = {
  id: string; name: string; company?: string | null; phone?: string | null;
  alternate_phone?: string | null; email?: string | null; city?: string | null;
  address?: string | null; tier?: string;
};

export type DuplicateMatches = { high: CustomerMatch[]; medium: CustomerMatch[]; low: CustomerMatch[] };

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
    address?: string; city?: string; state?: string; pincode?: string;
    visited_at?: string; salesperson_id?: string; source: string;
    reference_contact?: string; architect?: string; builder?: string;
    floor_id: string;
    interested_products?: string[]; budget?: number; notes?: string;
    priority?: "low" | "medium" | "high" | "critical"; next_followup_at?: string;
    use_existing_customer_id?: string; force_new_customer?: boolean;
  }) => api.post<WalkIn>("/walkins", body),

  update: (id: string, body: Partial<{
    status: WalkInStatus; salesperson_id: string; notes: string;
    manual_priority_override: "low" | "medium" | "high" | "critical";
    next_followup_at: string; lost_reason: string; alternate_phone: string;
    budget: number; interested_products: string[];
    reference_contact: string; architect: string; builder: string;
  }>) => api.patch<WalkIn>(`/walkins/${id}`, body),

  reassign: (id: string, salesperson_id: string) =>
    api.patch<WalkIn>(`/walkins/${id}/reassign`, { salesperson_id }),

  contact: (id: string, channel: "whatsapp" | "email") =>
    api.post<{ channel: string; message?: string; wa_url?: string; subject?: string; body?: string; mailto_url?: string }>(
      `/walkins/${id}/contact?channel=${channel}`,
    ),

  timeline: (id: string) => api.get<Record<string, any>[]>(`/walkins/${id}/timeline`),

  checkDuplicate: (params: { phone?: string; alternatePhone?: string; email?: string; name?: string; city?: string; address?: string }) =>
    api.get<DuplicateMatches>(`/walkins/check-duplicate${toQuery({
      phone: params.phone, alternate_phone: params.alternatePhone, email: params.email,
      name: params.name, city: params.city, address: params.address,
    })}`),

  dashboard: () => api.get<WalkInsDashboard>("/walkins/dashboard"),
  analytics: () => api.get<WalkInsAnalytics>("/walkins/analytics"),

  listSources: () => api.get<{ sources: string[] }>("/walkins/config/sources"),
  updateSources: (sources: string[]) => api.put<{ sources: string[] }>("/walkins/config/sources", { sources }),

  listAssignees: () => api.get<{ id: string; full_name: string; role: string }[]>("/followups/config/assignees"),
};

// Best-effort parse of ApiError.detail — the client stringifies non-string
// `detail` payloads to JSON (see src/api/client.ts), so a 409 duplicate
// response's `{message, matches}` object arrives here as a JSON string.
export function parseDuplicateConflict(detail: string | undefined): { message: string; matches: DuplicateMatches } | null {
  if (!detail) return null;
  try {
    const parsed = JSON.parse(detail);
    if (parsed && parsed.matches) return parsed;
  } catch {
    // not a JSON payload — a plain string error, not a duplicate conflict
  }
  return null;
}
