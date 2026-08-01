// frontend/src/api/executive.ts
// Typed client for the Executive Overview endpoints (see
// backend/routes/executive_overview_routes.py). Same thin wrapper pattern as
// src/api/tileOrders.ts — no separate fetch layer.
//
// Every number these types carry is computed by the backend analytics layer.
// Nothing here recomputes a KPI, a delta, or a rank: a figure derived in the
// frontend is a figure that can disagree with the books.
import { api } from "@/src/api/client";

/** Mirrors backend services/analytics/periods.py. A comparison is never
 *  fabricated — when there is nothing to compare against, the state says so. */
export type HistoryState = "ok" | "no_prior_period" | "insufficient_history";

export type Comparison = {
  delta_pct: number | null;
  direction: "up" | "down" | "flat" | null;
  history_state: HistoryState;
};

/** The actions a row offers, already filtered by the caller's role server-side.
 *  The frontend must never re-derive permissions from this list. */
export type RowAction =
  | "open"
  | "open_customer"
  | "open_po"
  | "call"
  | "whatsapp"
  | "schedule_followup"
  | "assign"
  | "record_payment"
  | "send_reminder";

export type ExecutiveRow = {
  rule: string;
  kind: "attention" | "opportunity";
  headline: string;
  impact: number;
  age_days: number | null;
  context: [string, string][];
  destination: string;
  actions: RowAction[];
  entity: Record<string, string>;
  history_state: HistoryState;
};

export type HealthComponent = {
  key: string;
  label: string;
  value: number | null;
  weight: number;
  rule: string;
  destination: string;
  available: boolean;
};

export type HealthScore = {
  /** null when no signal can be measured — never rendered as 0. */
  score: number | null;
  band: "Healthy" | "Watch" | "At risk" | null;
  components: HealthComponent[];
  available: number;
  total: number;
  missing_signal_note: string;
};

export type MorningBrief = {
  greeting: string;
  yesterday: {
    revenue: number;
    orders: number;
    collections: number;
    top_product_revenue: number | null;
    label: string;
  };
  recommended_actions: ExecutiveRow[];
};

export type Kpis = {
  revenue: number;
  orders: number;
  aov: number;
  customers: number;
  outstanding: { ordered: number; collected: number; outstanding: number };
  comparison: Comparison;
  previous_revenue: number | null;
  previous_label: string | null;
};

export type MoneyBlocked = {
  total: number;
  awaiting_release: number;
  awaiting_dispatch: number;
  awaiting_payment: number;
  destination: string;
};

export type PendingQuotations = {
  count: number;
  value: number;
  max_age_days: number | null;
  destination: string;
};

export type PendingFollowups = {
  count: number;
  overdue_count: number;
  value: number;
  destination: string;
};

export type FloorRevenue = { floor_id: string; revenue: number; orders: number };

export type Overview = {
  health: HealthScore;
  brief: MorningBrief;
  kpis: Kpis;
  money_blocked: MoneyBlocked;
  pending_quotations: PendingQuotations;
  pending_followups: PendingFollowups;
  revenue_by_floor: FloorRevenue[];
  attention: ExecutiveRow[];
  opportunities: ExecutiveRow[];
  attention_total: number;
  opportunities_total: number;
  period: { start: string | null; end: string | null; label: string };
};

export type FeedEntry = {
  id: string;
  event_type: string;
  label: string;
  summary: string;
  actor_name: string;
  created_at: string;
  group: "today" | "yesterday" | "this_week" | "older";
  floor_id: string;
  value: number | null;
  destination: string;
  entity: Record<string, string>;
  is_completion: boolean;
};

export type TodaysPriorities = {
  rows: ExecutiveRow[];
  total: number;
  done_today: FeedEntry[];
};

export type ExecutiveQuery = {
  floorId?: string;
  preset?: string;
  dateFrom?: string;
  dateTo?: string;
};

function qs(q: ExecutiveQuery = {}): string {
  const params = new URLSearchParams();
  if (q.floorId) params.set("floor_id", q.floorId);
  if (q.preset) params.set("preset", q.preset);
  if (q.dateFrom) params.set("date_from", q.dateFrom);
  if (q.dateTo) params.set("date_to", q.dateTo);
  const s = params.toString();
  return s ? `?${s}` : "";
}

export const executiveApi = {
  overview: (q?: ExecutiveQuery) => api.get<Overview>(`/analytics/overview${qs(q)}`),
  health: (q?: ExecutiveQuery) => api.get<HealthScore>(`/analytics/health${qs(q)}`),
  attention: (q?: ExecutiveQuery) => api.get<{ rows: ExecutiveRow[]; total: number }>(`/analytics/attention${qs(q)}`),
  opportunities: (q?: ExecutiveQuery) => api.get<{ rows: ExecutiveRow[]; total: number }>(`/analytics/opportunities${qs(q)}`),
  brief: (q?: ExecutiveQuery) => api.get<MorningBrief>(`/analytics/brief${qs(q)}`),
  feed: (q?: ExecutiveQuery & { limit?: number }) => {
    const params = qs(q);
    const sep = params ? "&" : "?";
    return api.get<{ rows: FeedEntry[] }>(`/analytics/feed${params}${sep}limit=${q?.limit ?? 40}`);
  },
  today: (q?: ExecutiveQuery) => api.get<TodaysPriorities>(`/analytics/today${qs(q)}`),
};
