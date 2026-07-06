// ═══════════════════════════════════════════════════════════════════════════
// Follow-ups · Sales Command Center — Design System V2.
// Superhuman Inbox × Linear. Every card is ranked by a deterministic AI
// Priority Score, carries an explainable Next Best Action, and the whole
// board is summarised by a personalised Today's Mission. Automated cards are
// produced by the backend's idempotent reconciliation engine — this screen
// only orchestrates reads + user actions, never invents data.
// ═══════════════════════════════════════════════════════════════════════════
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Linking, Platform, Pressable, RefreshControl, ScrollView,
  StyleSheet, Text, TextInput, useWindowDimensions, View,
} from "react-native";
import { Swipeable } from "react-native-gesture-handler";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { ActivityTimeline, TimelineEvent } from "@/src/components/ActivityTimeline";
import {
  Avatar, Badge, Button, Card, Chip, Dropdown, EmptyState, FilterBar,
  FormField, HeroCard, HoverCard, IconButton, Panel, PageHeader, SearchField,
  SegmentedControl, Sheet, Skeleton, SkeletonList, StatTile,
} from "@/src/components/ds";
import { toast } from "@/src/components/Toast";
import { useAuth } from "@/src/state/auth";
import { colors, elevation, moneyShort, radius, spacing, type } from "@/src/theme/tokens";

type FeatherName = keyof typeof Feather.glyphMap;

// ─────────────────────────────────────────────────────────────────────────────
// Types (mirror backend/models.py Followup + routes/followup_routes.py shapes)
// ─────────────────────────────────────────────────────────────────────────────
type Bucket = "overdue" | "today" | "tomorrow" | "this_week" | "later" | "snoozed" | "completed";
type PriorityLevel = "critical" | "high" | "medium" | "low";
type Channel = "call" | "whatsapp" | "email" | "visit";

type Followup = {
  id: string;
  rule_type: string;
  category: string;
  customer_id: string;
  customer_name: string;
  customer_phone?: string | null;
  customer_tier: "retail" | "trade" | "vip";
  quotation_id?: string | null;
  quotation_number?: string | null;
  purchase_id?: string | null;
  purchase_number?: string | null;
  project_name?: string | null;
  value: number;
  reason: string;
  reason_factors: string[];
  next_action: string;
  next_action_reason: string;
  suggested_channel: Channel;
  priority_score: number;
  priority_level: PriorityLevel;
  manual_priority_override?: PriorityLevel | null;
  effective_priority_level?: PriorityLevel;
  due_at: string;
  status: "open" | "snoozed" | "done" | "dismissed";
  snoozed_until?: string | null;
  is_automated: boolean;
  auto_resolved: boolean;
  resolution_note?: string | null;
  assigned_to?: string | null;
  assigned_to_name?: string | null;
  last_contacted_at?: string | null;
  contact_attempts: number;
  tags: string[];
  completed_at?: string | null;
  completed_outcome?: string | null;
  notes?: string | null;
  bucket: Bucket;
  created_at: string;
  updated_at: string;
};

type RuleInfo = { rule_type: string; label: string; category: string; description: string; active_count: number };

type Stats = {
  today_tasks: number; today_critical: number;
  overdue: number; overdue_critical: number;
  overdue_payments_count: number; overdue_payments_amount: number; overdue_payments_amount_short: string;
  expiring_quotations_count: number;
  tomorrow: number; this_week: number;
  waiting_for_customer: number;
  completed_today: number; completed_trend: number;
  snoozed: number; later: number;
  rules: RuleInfo[];
};

type Mission = {
  due_count: number; revenue_at_risk: number; revenue_at_risk_short: string;
  overdue_payments: number; quotations_expiring_today: number; critical_count: number;
  estimated_minutes: number;
  top_priorities: { id: string; customer_name: string; reason: string; priority_score: number }[];
  greeting_name: string;
};

type Insights = {
  calls_completed: number; whatsapps_sent: number; payments_collected: number;
  quotations_approved: number; response_rate: number;
};

type Detail = {
  followup: Followup;
  customer: {
    id: string; name: string; company?: string | null; phone?: string | null;
    email?: string | null; city?: string | null; address?: string | null; tier: string;
  };
  stats: {
    lifetime_revenue: number; outstanding_total: number; pending_quotations: number; pending_orders: number;
    conversion_rate: number; average_order_value: number; preferred_salesperson?: string | null;
    risk_level: "low" | "medium" | "high";
  };
  quotations: { id: string; number: string; status: string; grand_total: number; valid_until?: string | null; updated_at: string }[];
  payments: { id: string; amount: number; mode: string; paid_at?: string | null }[];
  purchases: { id: string; number: string; status: string; grand_total: number; updated_at: string }[];
  timeline: TimelineEvent[];
};

type Assignee = { id: string; full_name: string; role: string };
type CustomerLite = { id: string; name: string; company?: string | null; phone?: string | null; tier: string };
type SavedView = { id: string; name: string; filters: Record<string, any> };

type KpiFilter = Bucket | "waiting" | "all";

// ─────────────────────────────────────────────────────────────────────────────
// Static meta
// ─────────────────────────────────────────────────────────────────────────────
const BUCKET_META: Record<Bucket, { label: string; icon: FeatherName }> = {
  overdue: { label: "Overdue", icon: "alert-circle" },
  today: { label: "Today", icon: "sun" },
  tomorrow: { label: "Tomorrow", icon: "sunrise" },
  this_week: { label: "This Week", icon: "calendar" },
  later: { label: "Later", icon: "clock" },
  snoozed: { label: "Snoozed", icon: "bell-off" },
  completed: { label: "Completed", icon: "check-circle" },
};
const SECTION_ORDER: Bucket[] = ["overdue", "today", "tomorrow", "this_week", "later", "snoozed", "completed"];

const PRIORITY_TONE: Record<PriorityLevel, { bg: string; fg: string; border: string }> = {
  critical: { bg: colors.errorBg, fg: colors.error, border: colors.errorBorder },
  high: { bg: colors.warningBg, fg: colors.warning, border: colors.warningBorder },
  // Deliberately NEUTRAL (not brand blue) — see UX audit: blue was overloaded
  // as brand + action + "medium priority" simultaneously, diluting meaning.
  medium: { bg: "#EEF0F3", fg: colors.onSurfaceSecondary, border: colors.borderStrong },
  low: { bg: colors.surfaceTertiary, fg: colors.onSurfaceMuted, border: colors.border },
};

const CATEGORY_ICON: Record<string, FeatherName> = {
  quotation: "file-text", payment: "credit-card", purchase: "shopping-bag",
  dispatch: "truck", delivery: "package", complaint: "alert-triangle",
  general: "flag", sales: "trending-up", support: "life-buoy",
};
const CHANNEL_ICON: Record<Channel, FeatherName> = {
  call: "phone", whatsapp: "message-circle", email: "mail", visit: "map-pin",
};
const CATEGORY_OPTIONS = [
  { value: "all", label: "All types" },
  { value: "quotation", label: "Quotation" },
  { value: "payment", label: "Payment" },
  { value: "dispatch", label: "Dispatch" },
  { value: "delivery", label: "Delivery" },
  { value: "sales", label: "Sales" },
  { value: "general", label: "General" },
];

// ─────────────────────────────────────────────────────────────────────────────
// Small formatters
// ─────────────────────────────────────────────────────────────────────────────
function startOfDay(d: Date): Date { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; }
function dateShort(iso?: string | null): string {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" }); }
  catch { return "—"; }
}
function timeAgo(iso?: string | null): string {
  if (!iso) return "Never contacted";
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return "Never contacted";
  const diffMin = Math.floor((Date.now() - d) / 60000);
  if (diffMin < 1) return "Contacted just now";
  if (diffMin < 60) return `Contacted ${diffMin}m ago`;
  const h = Math.floor(diffMin / 60);
  if (h < 24) return `Contacted ${h}h ago`;
  return `Contacted ${Math.floor(h / 24)}d ago`;
}
function dueLabel(f: Followup): string {
  if (f.status === "done") return f.completed_at ? `Completed ${dateShort(f.completed_at)}` : "Completed";
  if (f.status === "dismissed") return "Dismissed";
  if (f.status === "snoozed" && f.snoozed_until) {
    const d = new Date(f.snoozed_until);
    return `Snoozed till ${d.toLocaleDateString("en-IN", { day: "numeric", month: "short" })}, ${d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`;
  }
  const d = new Date(f.due_at);
  if (Number.isNaN(d.getTime())) return "—";
  const days = Math.round((startOfDay(d).getTime() - startOfDay(new Date()).getTime()) / 86400000);
  const time = d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
  if (days < 0) return `Overdue ${Math.abs(days)}d`;
  if (days === 0) return `Today · ${time}`;
  if (days === 1) return `Tomorrow · ${time}`;
  if (days <= 7) return `${d.toLocaleDateString("en-IN", { weekday: "short" })} · ${time}`;
  return dateShort(f.due_at);
}
function isSameDay(aIso: string, b: Date): boolean {
  const a = new Date(aIso);
  return a.toDateString() === b.toDateString();
}
function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

// ═══════════════════════════════════════════════════════════════════════════
// Screen
// ═══════════════════════════════════════════════════════════════════════════
export default function FollowupsScreen() {
  const { staff } = useAuth();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 900;

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [rawItems, setRawItems] = useState<Followup[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [mission, setMission] = useState<Mission | null>(null);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [assignees, setAssignees] = useState<Assignee[]>([]);
  const [customers, setCustomers] = useState<CustomerLite[]>([]);

  const [q, setQ] = useState("");
  const [kpiFilter, setKpiFilter] = useState<KpiFilter>("all");
  const [priorityFilter, setPriorityFilter] = useState<PriorityLevel | "all">("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [tierFilter, setTierFilter] = useState<"all" | "retail" | "trade" | "vip">("all");
  const [ownerFilter, setOwnerFilter] = useState<"all" | "mine" | string>("all");
  const [collapsed, setCollapsed] = useState<Set<Bucket>>(new Set(["completed", "snoozed"]));

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [mobileSheet, setMobileSheet] = useState(false);

  const [rulesSheet, setRulesSheet] = useState(false);
  const [newSheet, setNewSheet] = useState(false);
  const [callOutcomeFor, setCallOutcomeFor] = useState<Followup | null>(null);
  const [noteFor, setNoteFor] = useState<Followup | null>(null);
  const [customSnoozeFor, setCustomSnoozeFor] = useState<Followup | null>(null);

  const [filtersExpanded, setFiltersExpanded] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [savedViewsSheet, setSavedViewsSheet] = useState(false);
  const [shortcutHelp, setShortcutHelp] = useState(false);

  // ── Data loading ──────────────────────────────────────────────────────────
  const loadList = useCallback(async () => {
    try { setRawItems(await api.get<Followup[]>("/followups")); }
    catch (e: any) { toast.error(e?.detail || "Could not load follow-ups"); }
  }, []);

  const refreshStatsQuiet = useCallback(async () => {
    try {
      const [s, m, i] = await Promise.all([
        api.get<Stats>("/followups/stats"),
        api.get<Mission>("/followups/mission"),
        api.get<Insights>("/followups/insights"),
      ]);
      setStats(s); setMission(m); setInsights(i);
    } catch { /* best-effort */ }
  }, []);

  const bootstrap = useCallback(async () => {
    try { await api.post("/followups/reconcile"); } catch { /* best-effort */ }
    try {
      const [s, m, i, list, a, c, sv] = await Promise.all([
        api.get<Stats>("/followups/stats"),
        api.get<Mission>("/followups/mission"),
        api.get<Insights>("/followups/insights"),
        api.get<Followup[]>("/followups"),
        api.get<Assignee[]>("/followups/config/assignees"),
        api.get<CustomerLite[]>("/customers"),
        api.get<SavedView[]>("/followups/saved-views").catch(() => []),
      ]);
      setStats(s); setMission(m); setInsights(i); setRawItems(list); setAssignees(a); setCustomers(c); setSavedViews(sv);
      return list;
    } catch (e: any) { toast.error(e?.detail || "Could not load the workspace"); return []; }
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      const list = await bootstrap();
      setLoading(false);
      // Auto-select the #1 priority open card so the Context Panel is never
      // an empty "Select a follow-up" placeholder on first load (desktop only
      // — mobile keeps the sheet closed until the user taps a card).
      if (isDesktop) {
        const top = [...list]
          .filter((f) => f.status === "open")
          .sort((a, b) => b.priority_score - a.priority_score)[0];
        if (top) { setSelectedId(top.id); loadDetail(top.id); }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await bootstrap();
    setRefreshing(false);
    toast.success("Workspace synced");
  }, [bootstrap]);

  const loadDetail = useCallback(async (id: string) => {
    setLoadingDetail(true);
    try { setDetail(await api.get<Detail>(`/followups/${id}`)); }
    catch (e: any) { toast.error(e?.detail || "Could not load details"); setDetail(null); }
    finally { setLoadingDetail(false); }
  }, []);

  const selectCard = useCallback((f: Followup) => {
    setSelectedId(f.id);
    loadDetail(f.id);
    if (!isDesktop) setMobileSheet(true);
  }, [isDesktop, loadDetail]);

  // ── Optimistic local patch helper ────────────────────────────────────────
  const patchLocal = useCallback((id: string, patch: Partial<Followup>) => {
    setRawItems((prev) => prev.map((f) => (f.id === id ? { ...f, ...patch } : f)));
  }, []);

  // ── Actions ───────────────────────────────────────────────────────────────
  const contact = useCallback(async (f: Followup, channel: Channel) => {
    try {
      const res = await api.post<{ channel: string; phone?: string | null; wa_url?: string; email?: string | null }>(
        `/followups/${f.id}/contact`, { channel },
      );
      if (channel === "call") {
        if (!res.phone) { toast.error("No phone number on file"); return; }
        await Linking.openURL(`tel:${res.phone}`);
        setCallOutcomeFor(f);
      } else if (channel === "whatsapp") {
        if (!res.wa_url) { toast.error("Could not build WhatsApp message"); return; }
        await Linking.openURL(res.wa_url);
        toast.success("WhatsApp opened");
      } else if (channel === "email") {
        if (!res.email) { toast.error("No email on file for this customer"); return; }
        await Linking.openURL(`mailto:${res.email}?subject=${encodeURIComponent(f.quotation_number || f.project_name || "Following up")}`);
      }
      patchLocal(f.id, { last_contacted_at: new Date().toISOString() });
    } catch (e: any) { toast.error(e?.detail || "Action failed"); }
  }, [patchLocal]);

  const completeFollowup = useCallback(async (f: Followup) => {
    if (Platform.OS !== "web") Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    patchLocal(f.id, { status: "done", bucket: "completed", completed_at: new Date().toISOString() });
    try { await api.post(`/followups/${f.id}/complete`, {}); toast.success("Marked complete"); refreshStatsQuiet(); }
    catch (e: any) { toast.error(e?.detail || "Could not complete"); loadList(); }
  }, [patchLocal, refreshStatsQuiet, loadList]);

  const snoozeFollowup = useCallback(async (f: Followup, preset: "15m" | "1h" | "tomorrow" | "next_week") => {
    if (Platform.OS !== "web") Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    patchLocal(f.id, { status: "snoozed", bucket: "snoozed" });
    try { await api.post(`/followups/${f.id}/snooze`, { preset }); toast.success("Snoozed"); refreshStatsQuiet(); }
    catch (e: any) { toast.error(e?.detail || "Could not snooze"); loadList(); }
  }, [patchLocal, refreshStatsQuiet, loadList]);

  const customSnooze = useCallback(async (f: Followup, untilIso: string) => {
    patchLocal(f.id, { status: "snoozed", bucket: "snoozed" });
    setCustomSnoozeFor(null);
    try { await api.post(`/followups/${f.id}/snooze`, { until: untilIso }); toast.success("Snoozed"); refreshStatsQuiet(); }
    catch (e: any) { toast.error(e?.detail || "Could not snooze"); loadList(); }
  }, [patchLocal, refreshStatsQuiet, loadList]);

  const assignFollowup = useCallback(async (f: Followup, userId: string) => {
    const u = assignees.find((a) => a.id === userId);
    patchLocal(f.id, { assigned_to: userId, assigned_to_name: u?.full_name });
    try { await api.patch(`/followups/${f.id}`, { assigned_to: userId }); toast.success(`Assigned to ${u?.full_name || "—"}`); }
    catch (e: any) { toast.error(e?.detail || "Could not assign"); }
  }, [assignees, patchLocal]);

  const dismissFollowup = useCallback(async (f: Followup) => {
    patchLocal(f.id, { status: "dismissed", bucket: "completed" });
    try { await api.patch(`/followups/${f.id}`, { status: "dismissed" }); toast.success("Dismissed"); refreshStatsQuiet(); }
    catch (e: any) { toast.error(e?.detail || "Could not dismiss"); loadList(); }
  }, [patchLocal, refreshStatsQuiet, loadList]);

  const saveNote = useCallback(async (f: Followup, notes: string) => {
    patchLocal(f.id, { notes });
    try { await api.patch(`/followups/${f.id}`, { notes }); toast.success("Note saved"); setNoteFor(null); }
    catch (e: any) { toast.error(e?.detail || "Could not save note"); }
  }, [patchLocal]);

  const logCallOutcome = useCallback(async (f: Followup, outcome: string, notes?: string) => {
    try {
      await api.post(`/followups/${f.id}/log-call`, { outcome, notes: notes || undefined });
      toast.success("Call logged");
      setCallOutcomeFor(null);
      await loadList();
      refreshStatsQuiet();
    } catch (e: any) { toast.error(e?.detail || "Could not log call"); }
  }, [loadList, refreshStatsQuiet]);

  const createFollowup = useCallback(async (payload: any) => {
    try {
      await api.post("/followups", payload);
      toast.success("Follow-up created");
      setNewSheet(false);
      await loadList();
      refreshStatsQuiet();
    } catch (e: any) { toast.error(e?.detail || "Could not create follow-up"); }
  }, [loadList, refreshStatsQuiet]);

  // ── Filtering (100% client-side ⇒ instant) ──────────────────────────────
  const filtered = useMemo(() => {
    let list = rawItems;
    const term = q.trim().toLowerCase();
    if (term) {
      list = list.filter((f) => (
        f.customer_name?.toLowerCase().includes(term)
        || f.customer_phone?.toLowerCase().includes(term)
        || f.quotation_number?.toLowerCase().includes(term)
        || f.purchase_number?.toLowerCase().includes(term)
        || f.project_name?.toLowerCase().includes(term)
        || f.reason?.toLowerCase().includes(term)
        || f.tags?.some((t) => t.toLowerCase().includes(term))
      ));
    }
    if (kpiFilter === "waiting") {
      list = list.filter((f) => f.status === "open" && (f.rule_type === "quotation_inactive" || f.rule_type === "payment_partial"));
    } else if (kpiFilter === "completed") {
      list = list.filter((f) => f.bucket === "completed" && !!f.completed_at && isSameDay(f.completed_at, new Date()));
    } else if (kpiFilter !== "all") {
      list = list.filter((f) => f.bucket === kpiFilter);
    }
    if (priorityFilter !== "all") list = list.filter((f) => (f.manual_priority_override || f.priority_level) === priorityFilter);
    if (categoryFilter !== "all") list = list.filter((f) => f.category === categoryFilter);
    if (tierFilter !== "all") list = list.filter((f) => f.customer_tier === tierFilter);
    if (ownerFilter === "mine") list = list.filter((f) => f.assigned_to === staff?.id);
    else if (ownerFilter !== "all") list = list.filter((f) => f.assigned_to === ownerFilter);
    return [...list].sort((a, b) => (b.priority_score - a.priority_score) || (a.due_at || "").localeCompare(b.due_at || ""));
  }, [rawItems, q, kpiFilter, priorityFilter, categoryFilter, tierFilter, ownerFilter, staff]);

  const sections = useMemo(() => {
    const map: Record<string, Followup[]> = {};
    for (const f of filtered) (map[f.bucket] ||= []).push(f);
    return SECTION_ORDER.filter((b) => map[b]?.length).map((b) => ({ bucket: b, items: map[b] }));
  }, [filtered]);

  const priorityCounts = useMemo(() => {
    const c: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0 };
    for (const f of rawItems) if (f.status === "open" || f.status === "snoozed") {
      const lvl = f.manual_priority_override || f.priority_level;
      c[lvl] = (c[lvl] || 0) + 1;
    }
    return c;
  }, [rawItems]);

  const topPriorityOpen = useMemo(
    () => [...rawItems].filter((f) => f.bucket === "overdue" || f.bucket === "today")
      .sort((a, b) => b.priority_score - a.priority_score)[0] || null,
    [rawItems],
  );

  // Rank badge (repeats the Mission's "#1/#2/#3" framing inside the main
  // list itself — closes the "who do I call first" 5-second-scan gap).
  const rankMap = useMemo(() => {
    const top3 = [...rawItems]
      .filter((f) => f.status === "open" && (f.bucket === "overdue" || f.bucket === "today"))
      .sort((a, b) => b.priority_score - a.priority_score)
      .slice(0, 3);
    const m = new Map<string, number>();
    top3.forEach((f, i) => m.set(f.id, i + 1));
    return m;
  }, [rawItems]);

  const toggleKpi = (v: KpiFilter) => setKpiFilter((cur) => (cur === v ? "all" : v));
  const toggleSection = (b: Bucket) => setCollapsed((prev) => {
    const n = new Set(prev);
    if (n.has(b)) n.delete(b); else n.add(b);
    return n;
  });

  const ownerLabel = ownerFilter === "all" ? "Owner: All" : ownerFilter === "mine" ? "Owner: Mine" : `Owner: ${assignees.find((a) => a.id === ownerFilter)?.full_name || "—"}`;
  const activeFilterCount = [priorityFilter !== "all", categoryFilter !== "all", tierFilter !== "all", ownerFilter !== "all"].filter(Boolean).length;

  // ── Bulk selection ───────────────────────────────────────────────────────
  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }, []);
  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  const bulkSnooze = useCallback(async (preset: "1h" | "tomorrow" | "next_week") => {
    const ids = Array.from(selectedIds);
    await Promise.all(ids.map((id) => api.post(`/followups/${id}/snooze`, { preset }).catch(() => null)));
    setRawItems((prev) => prev.map((f) => (selectedIds.has(f.id) ? { ...f, status: "snoozed", bucket: "snoozed" } : f)));
    toast.success(`Snoozed ${ids.length} follow-up${ids.length === 1 ? "" : "s"}`);
    clearSelection();
    refreshStatsQuiet();
  }, [selectedIds, clearSelection, refreshStatsQuiet]);

  const bulkComplete = useCallback(async () => {
    const ids = Array.from(selectedIds);
    await Promise.all(ids.map((id) => api.post(`/followups/${id}/complete`, {}).catch(() => null)));
    setRawItems((prev) => prev.map((f) => (selectedIds.has(f.id) ? { ...f, status: "done", bucket: "completed", completed_at: new Date().toISOString() } : f)));
    toast.success(`Completed ${ids.length} follow-up${ids.length === 1 ? "" : "s"}`);
    clearSelection();
    refreshStatsQuiet();
  }, [selectedIds, clearSelection, refreshStatsQuiet]);

  const bulkAssign = useCallback(async (userId: string) => {
    const ids = Array.from(selectedIds);
    const u = assignees.find((a) => a.id === userId);
    await Promise.all(ids.map((id) => api.patch(`/followups/${id}`, { assigned_to: userId }).catch(() => null)));
    setRawItems((prev) => prev.map((f) => (selectedIds.has(f.id) ? { ...f, assigned_to: userId, assigned_to_name: u?.full_name } : f)));
    toast.success(`Assigned ${ids.length} follow-up${ids.length === 1 ? "" : "s"} to ${u?.full_name || "—"}`);
    clearSelection();
  }, [selectedIds, assignees, clearSelection]);

  // ── Saved Views ──────────────────────────────────────────────────────────
  const applySavedView = useCallback((v: SavedView) => {
    const flt = v.filters || {};
    setQ(flt.q || "");
    setKpiFilter(flt.kpiFilter || "all");
    setPriorityFilter(flt.priorityFilter || "all");
    setCategoryFilter(flt.categoryFilter || "all");
    setTierFilter(flt.tierFilter || "all");
    setOwnerFilter(flt.ownerFilter || "all");
    setSavedViewsSheet(false);
    toast.success(`Applied "${v.name}"`);
  }, []);

  const saveCurrentView = useCallback(async (name: string) => {
    const filters = { q, kpiFilter, priorityFilter, categoryFilter, tierFilter, ownerFilter };
    try {
      const v = await api.post<SavedView>("/followups/saved-views", { name, filters });
      setSavedViews((prev) => [v, ...prev]);
      toast.success("View saved");
    } catch (e: any) { toast.error(e?.detail || "Could not save view"); }
  }, [q, kpiFilter, priorityFilter, categoryFilter, tierFilter, ownerFilter]);

  const deleteSavedView = useCallback(async (id: string) => {
    setSavedViews((prev) => prev.filter((v) => v.id !== id));
    try { await api.delete(`/followups/saved-views/${id}`); } catch { /* best-effort */ }
  }, []);

  // ── Export ───────────────────────────────────────────────────────────────
  const doExport = useCallback(async (format: "xlsx" | "csv") => {
    const qs = new URLSearchParams({ format });
    if (kpiFilter !== "all" && kpiFilter !== "waiting" && kpiFilter !== "completed") qs.set("bucket", kpiFilter);
    if (priorityFilter !== "all") qs.set("priority", priorityFilter);
    if (categoryFilter !== "all") qs.set("category", categoryFilter);
    if (tierFilter !== "all") qs.set("customer_tier", tierFilter);
    if (ownerFilter === "mine" && staff?.id) qs.set("assigned_to", staff.id);
    else if (ownerFilter !== "all") qs.set("assigned_to", ownerFilter);
    if (q.trim()) qs.set("q", q.trim());
    try {
      const url = await api.authenticatedUrl(`/followups/export?${qs.toString()}`);
      if (Platform.OS === "web") {
        // @ts-ignore — web only
        window.open(url, "_blank");
      } else {
        await Linking.openURL(url);
      }
      toast.success("Export ready");
    } catch { toast.error("Could not export"); }
  }, [kpiFilter, priorityFilter, categoryFilter, tierFilter, ownerFilter, q, staff]);

  // ── Keyboard shortcuts (web only) ───────────────────────────────────────
  useEffect(() => {
    if (Platform.OS !== "web") return;
    const selected = rawItems.find((f) => f.id === selectedId) || null;
    function onKeyDown(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") {
        if (e.key === "Escape") (e.target as HTMLElement).blur();
        return;
      }
      switch (e.key) {
        case "c": case "C": if (selected) contact(selected, "call"); break;
        case "w": case "W": if (selected) contact(selected, "whatsapp"); break;
        case "e": case "E": if (selected) contact(selected, "email"); break;
        case " ": if (selected) { e.preventDefault(); completeFollowup(selected); } break;
        case "s": case "S": if (selected) setCustomSnoozeFor(null); if (selected) snoozeFollowup(selected, "1h"); break;
        case "/": {
          e.preventDefault();
          // @ts-ignore — RN Web maps testID → data-testid on the underlying <input>
          const el = document.querySelector('[data-testid="followups-search"]') as HTMLInputElement | null;
          el?.focus();
          break;
        }
        case "?": setShortcutHelp((v) => !v); break;
        case "Escape":
          setSelectedId(null); setDetail(null); setMobileSheet(false);
          setCallOutcomeFor(null); setNoteFor(null); setCustomSnoozeFor(null);
          break;
        default: break;
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [rawItems, selectedId, contact, completeFollowup, snoozeFollowup]);

  const activeTileStyle = { borderColor: colors.brand, backgroundColor: colors.brandTint };

  // ═══════════════════════════════════════════════════════════════════════
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <PageHeader
        overline="WORKSPACE"
        title="Follow-ups"
        subtitle="Never lose another customer. Every follow-up, payment reminder and quotation reminder in one workspace."
        actions={
          <>
            <IconButton icon="rotate-cw" onPress={onRefresh} tone="surface" accessibilityLabel="Refresh" size={38} />
            <Button label="Automation Rules" icon="zap" variant="secondary" size="md" onPress={() => setRulesSheet(true)} />
            <Dropdown
              label="Export" icon="download" variant="secondary"
              items={[
                { label: "Export as Excel (.xlsx)", icon: "file-text", onPress: () => doExport("xlsx") },
                { label: "Export as CSV", icon: "file", onPress: () => doExport("csv") },
              ]}
            />
            <Button label="New Follow-up" icon="plus" variant="primary" size="md" onPress={() => setNewSheet(true)} testID="new-followup-btn" />
          </>
        }
      />

      <ScrollView
        contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg, paddingBottom: spacing.xxxl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
      >
        {/* Today's Mission */}
        <MissionHero mission={mission} loading={loading} onJumpTop={() => topPriorityOpen && selectCard(topPriorityOpen)} />

        {/* KPI strip */}
        <View style={{ flexDirection: "row", gap: spacing.md, flexWrap: "wrap" }}>
          <StatTile label="Today's Tasks" value={stats ? stats.today_tasks : "—"} icon="sun" tone="brand"
            sub={stats?.today_critical ? `${stats.today_critical} critical` : "On track"}
            onPress={() => toggleKpi("today")} style={kpiFilter === "today" ? activeTileStyle : undefined} />
          <StatTile label="Overdue Tasks" value={stats ? stats.overdue : "—"} icon="alert-circle" tone="danger"
            sub={stats?.overdue_critical ? `${stats.overdue_critical} critical` : "None overdue"}
            onPress={() => toggleKpi("overdue")} style={kpiFilter === "overdue" ? activeTileStyle : undefined} />
          <StatTile label="Payments Overdue" value={stats ? stats.overdue_payments_count : "—"} icon="credit-card" tone="danger"
            sub={stats?.overdue_payments_count ? `₹${stats.overdue_payments_amount_short} at stake` : "None overdue"}
            onPress={() => toggleKpi("overdue")} />
          <StatTile label="Expiring Soon" value={stats ? stats.expiring_quotations_count : "—"} icon="clock" tone="warning"
            sub="Quotations lapsing" onPress={() => setCategoryFilter("quotation")} />
          <StatTile label="Waiting For Customer" value={stats ? stats.waiting_for_customer : "—"} icon="watch" tone="warning"
            sub="Ball's in their court" onPress={() => toggleKpi("waiting")} style={kpiFilter === "waiting" ? activeTileStyle : undefined} />
          <StatTile label="Completed Today" value={stats ? stats.completed_today : "—"} icon="check-circle" tone="success"
            sub={stats ? `${stats.completed_trend >= 0 ? "+" : ""}${stats.completed_trend} vs yesterday` : undefined}
            onPress={() => toggleKpi("completed")} style={kpiFilter === "completed" ? activeTileStyle : undefined} />
        </View>

        {/* Smart search + filters — Priority chips always visible; the rest
            collapse behind "More filters" to keep the list within reach
            (UX audit: filters previously pushed the first card ~200px down). */}
        <Panel padding={spacing.md}>
          <View style={{ gap: spacing.md }}>
            <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center" }}>
              <View style={{ flex: 1 }}>
                <SearchField
                  testID="followups-search"
                  value={q}
                  onChangeText={setQ}
                  onClear={() => setQ("")}
                  placeholder="Search customer, phone, quotation #, project…"
                />
              </View>
              <IconButton icon="bookmark" onPress={() => setSavedViewsSheet(true)} tone="surface" accessibilityLabel="Saved views" size={40} />
              <IconButton icon="help-circle" onPress={() => setShortcutHelp(true)} tone="surface" accessibilityLabel="Keyboard shortcuts" size={40} />
            </View>
            <FilterBar
              label="PRIORITY"
              value={priorityFilter}
              onChange={setPriorityFilter as any}
              options={[
                { value: "all", label: "All priorities" },
                { value: "critical", label: "Critical", count: priorityCounts.critical || undefined },
                { value: "high", label: "High", count: priorityCounts.high || undefined },
                { value: "medium", label: "Medium", count: priorityCounts.medium || undefined },
                { value: "low", label: "Low", count: priorityCounts.low || undefined },
              ]}
            />
            <Pressable onPress={() => setFiltersExpanded((v) => !v)} style={{ flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start" }}>
              <Feather name={filtersExpanded ? "chevron-up" : "sliders"} size={13} color={colors.onSurfaceSecondary} />
              <Text style={{ fontSize: 12, fontWeight: "700", color: colors.onSurfaceSecondary }}>
                {filtersExpanded ? "Hide filters" : "More filters"}{activeFilterCount ? ` (${activeFilterCount})` : ""}
              </Text>
            </Pressable>
            {filtersExpanded ? (
              <>
                <FilterBar label="TYPE" value={categoryFilter} onChange={setCategoryFilter} options={CATEGORY_OPTIONS} />
                <View style={{ flexDirection: "row", gap: spacing.md, alignItems: "center", flexWrap: "wrap" }}>
                  <SegmentedControl
                    size="sm"
                    value={tierFilter}
                    onChange={setTierFilter as any}
                    options={[
                      { value: "all", label: "All customers" },
                      { value: "retail", label: "Retail" },
                      { value: "trade", label: "Trade" },
                      { value: "vip", label: "VIP" },
                    ]}
                  />
                  <Dropdown
                    label={ownerLabel}
                    icon="user"
                    variant="secondary"
                    items={[
                      { label: "All owners", icon: "users", onPress: () => setOwnerFilter("all") },
                      { label: "Mine", icon: "user-check", onPress: () => setOwnerFilter("mine") },
                      ...assignees.map((a) => ({ label: a.full_name, icon: "user" as FeatherName, onPress: () => setOwnerFilter(a.id) })),
                    ]}
                  />
                </View>
              </>
            ) : null}
            {kpiFilter !== "all" || activeFilterCount > 0 ? (
              <Chip
                label="Clear filters ✕"
                active
                onPress={() => { setKpiFilter("all"); setPriorityFilter("all"); setCategoryFilter("all"); setTierFilter("all"); setOwnerFilter("all"); }}
              />
            ) : null}
          </View>
        </Panel>

        {/* Bulk action bar — appears once ≥1 card is selected. Unlocks the
            "manage 300+ customers without feeling overwhelmed" requirement. */}
        {selectedIds.size > 0 ? (
          <BulkActionBar
            count={selectedIds.size}
            assignees={assignees}
            onClear={clearSelection}
            onSnooze={bulkSnooze}
            onComplete={bulkComplete}
            onAssign={bulkAssign}
          />
        ) : null}

        {/* Main layout — Inbox (left) · Context + Insights (right) */}
        <View style={{ flexDirection: isDesktop ? "row" : "column", gap: spacing.lg, alignItems: "flex-start" }}>
          <View style={{ flex: isDesktop ? 1.5 : undefined, width: isDesktop ? undefined : "100%", gap: spacing.md, minWidth: 0 }}>
            {loading ? (
              <View style={{ gap: spacing.md }}>
                <Skeleton w="30%" h={16} radius={radius.sm} />
                <SkeletonList rows={4} />
                <Skeleton w="30%" h={16} radius={radius.sm} />
                <SkeletonList rows={3} />
              </View>
            ) : sections.length === 0 ? (
              <Card>
                <EmptyState
                  icon="check-circle" tone="brand"
                  title="You're all caught up."
                  subtitle="Nothing requires attention. Automated follow-ups will appear here the moment a quotation, payment or purchase needs you."
                  action={<Button label="New Follow-up" icon="plus" variant="primary" onPress={() => setNewSheet(true)} />}
                />
              </Card>
            ) : (
              sections.map((sec) => (
                <InboxSection
                  key={sec.bucket}
                  bucket={sec.bucket}
                  items={sec.items}
                  collapsed={collapsed.has(sec.bucket)}
                  onToggle={() => toggleSection(sec.bucket)}
                  selectedId={selectedId}
                  assignees={assignees}
                  rankMap={rankMap}
                  selectedIds={selectedIds}
                  onToggleSelect={toggleSelect}
                  onSelect={selectCard}
                  onCall={(f) => contact(f, "call")}
                  onWhatsApp={(f) => contact(f, "whatsapp")}
                  onEmail={(f) => contact(f, "email")}
                  onComplete={completeFollowup}
                  onSnooze={snoozeFollowup}
                  onCustomSnooze={setCustomSnoozeFor}
                  onAssign={assignFollowup}
                  onNote={setNoteFor}
                  onDismiss={dismissFollowup}
                />
              ))
            )}
          </View>

          {isDesktop ? (
            <View style={{ width: 400, gap: spacing.md }}>
              <ContextPanel detail={detail} loading={loadingDetail} />
              <InsightsPanel insights={insights} />
            </View>
          ) : null}
        </View>
      </ScrollView>

      {/* Mobile: floating quick-contact for the #1 priority item */}
      {!isDesktop && topPriorityOpen ? (
        <View style={styles.fabWrap} pointerEvents="box-none">
          <Pressable
            testID="fab-whatsapp"
            onPress={() => contact(topPriorityOpen, "whatsapp")}
            style={[styles.fab, { backgroundColor: colors.success }]}
          >
            <Feather name="message-circle" size={20} color={colors.onBrand} />
          </Pressable>
          <Pressable
            testID="fab-call"
            onPress={() => contact(topPriorityOpen, "call")}
            style={[styles.fab, { backgroundColor: colors.brand }]}
          >
            <Feather name="phone" size={20} color={colors.onBrand} />
          </Pressable>
        </View>
      ) : null}

      {/* Mobile: customer context bottom sheet */}
      <Sheet
        visible={!isDesktop && mobileSheet}
        onClose={() => setMobileSheet(false)}
        variant="bottom"
        title={detail?.customer?.company || detail?.customer?.name || "Customer"}
        subtitle={detail?.followup?.reason}
      >
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}>
          <ContextPanel detail={detail} loading={loadingDetail} embedded />
          <InsightsPanel insights={insights} />
        </ScrollView>
      </Sheet>

      <CallOutcomeSheet visible={!!callOutcomeFor} f={callOutcomeFor} onClose={() => setCallOutcomeFor(null)} onSubmit={logCallOutcome} />
      <NewFollowupSheet
        visible={newSheet} onClose={() => setNewSheet(false)} customers={customers} assignees={assignees}
        defaultAssignee={staff?.id} onCreate={createFollowup}
      />
      <AutomationRulesSheet visible={rulesSheet} onClose={() => setRulesSheet(false)} rules={stats?.rules || []} />
      <NoteSheet visible={!!noteFor} f={noteFor} onClose={() => setNoteFor(null)} onSave={saveNote} />
      <CustomSnoozeSheet visible={!!customSnoozeFor} f={customSnoozeFor} onClose={() => setCustomSnoozeFor(null)} onSave={customSnooze} />
      <SavedViewsSheet
        visible={savedViewsSheet} onClose={() => setSavedViewsSheet(false)} views={savedViews}
        onApply={applySavedView} onSave={saveCurrentView} onDelete={deleteSavedView}
      />
      <ShortcutHelpSheet visible={shortcutHelp} onClose={() => setShortcutHelp(false)} />
    </SafeAreaView>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// BulkActionBar — appears once ≥1 card is selected. Superhuman-style batch
// processing so a salesperson can clear dozens of stale cards in one pass.
// ─────────────────────────────────────────────────────────────────────────────
function BulkActionBar({ count, assignees, onClear, onSnooze, onComplete, onAssign }: {
  count: number; assignees: Assignee[]; onClear: () => void;
  onSnooze: (preset: "1h" | "tomorrow" | "next_week") => void;
  onComplete: () => void; onAssign: (userId: string) => void;
}) {
  return (
    <View style={[styles.bulkBar, elevation.medium]}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flex: 1 }}>
        <Badge label={String(count)} tone="brand" size="sm" />
        <Text style={{ fontSize: 13, fontWeight: "700", color: colors.onSurface }}>selected</Text>
      </View>
      <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center", flexWrap: "wrap" }}>
        <Dropdown
          label="Snooze" icon="clock" variant="secondary"
          items={[
            { label: "1 hour", icon: "clock", onPress: () => onSnooze("1h") },
            { label: "Tomorrow", icon: "sunrise", onPress: () => onSnooze("tomorrow") },
            { label: "Next week", icon: "calendar", onPress: () => onSnooze("next_week") },
          ]}
        />
        <Dropdown
          label="Assign" icon="user-plus" variant="secondary"
          items={assignees.map((a) => ({ label: a.full_name, icon: "user" as FeatherName, onPress: () => onAssign(a.id) }))}
        />
        <Button label="Complete" icon="check" variant="primary" size="sm" onPress={onComplete} />
        <IconButton icon="x" onPress={onClear} tone="surface" size={34} accessibilityLabel="Clear selection" />
      </View>
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SavedViewsSheet — persisted filter configurations (Export/Saved Views are
// no longer stubbed per product decision).
// ─────────────────────────────────────────────────────────────────────────────
function SavedViewsSheet({ visible, onClose, views, onApply, onSave, onDelete }: {
  visible: boolean; onClose: () => void; views: SavedView[];
  onApply: (v: SavedView) => void; onSave: (name: string) => void; onDelete: (id: string) => void;
}) {
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  useEffect(() => { if (visible) { setNaming(false); setName(""); } }, [visible]);
  return (
    <Sheet visible={visible} onClose={onClose} variant="drawer" title="Saved Views" subtitle="Persist your filter combinations so you can jump straight back to them.">
      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.md }}>
        {views.length === 0 ? (
          <EmptyState icon="bookmark" title="No saved views yet" subtitle="Set up your filters above, then save them here for one-tap access." />
        ) : (
          views.map((v) => (
            <View key={v.id} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
              <Pressable onPress={() => onApply(v)} style={{ flex: 1, flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.surfaceSecondary }}>
                <Feather name="bookmark" size={14} color={colors.brand} />
                <Text style={type.bodySm}>{v.name}</Text>
              </Pressable>
              <IconButton icon="trash-2" onPress={() => onDelete(v.id)} tone="danger" size={36} accessibilityLabel="Delete view" />
            </View>
          ))
        )}
        <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: colors.divider, marginVertical: spacing.sm }} />
        {naming ? (
          <View style={{ gap: spacing.sm }}>
            <FormField label="View name">
              <TextInput value={name} onChangeText={setName} placeholder="e.g. My VIP overdue payments" placeholderTextColor={colors.onSurfaceMuted} style={styles.textInput} autoFocus />
            </FormField>
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <Button label="Cancel" variant="secondary" size="md" onPress={() => setNaming(false)} />
              <Button label="Save View" icon="check" variant="primary" size="md" onPress={() => { if (name.trim()) { onSave(name.trim()); setNaming(false); setName(""); } }} />
            </View>
          </View>
        ) : (
          <Button label="Save current filters as a view" icon="plus" variant="secondary" size="md" onPress={() => setNaming(true)} />
        )}
      </ScrollView>
    </Sheet>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ShortcutHelpSheet — makes the (already implemented) keyboard shortcuts
// discoverable. Triggered by the "?" key or the header help icon.
// ─────────────────────────────────────────────────────────────────────────────
const SHORTCUTS: { keys: string; label: string }[] = [
  { keys: "C", label: "Call the selected follow-up" },
  { keys: "W", label: "WhatsApp the selected follow-up" },
  { keys: "E", label: "Email the selected follow-up" },
  { keys: "Space", label: "Mark selected follow-up complete" },
  { keys: "S", label: "Snooze selected follow-up 1 hour" },
  { keys: "/", label: "Focus search" },
  { keys: "Esc", label: "Deselect / close panels" },
  { keys: "?", label: "Toggle this shortcut list" },
];
function ShortcutHelpSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  return (
    <Sheet visible={visible} onClose={onClose} variant="modal" title="Keyboard Shortcuts" subtitle="Select a card, then use these — web only." width={420}>
      <View style={{ padding: spacing.xl, gap: spacing.sm }}>
        {SHORTCUTS.map((s) => (
          <View key={s.keys} style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
            <Text style={type.bodySm}>{s.label}</Text>
            <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border }}>
              <Text style={{ fontSize: 12, fontWeight: "700", color: colors.onSurface, fontFamily: Platform.select({ web: "monospace", default: undefined }) }}>{s.keys}</Text>
            </View>
          </View>
        ))}
      </View>
    </Sheet>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MissionHero — Today's Mission
// ─────────────────────────────────────────────────────────────────────────────
function MissionHero({ mission, loading, onJumpTop }: { mission: Mission | null; loading: boolean; onJumpTop: () => void }) {
  if (loading || !mission) {
    return (
      <View style={{ padding: spacing.xl, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, gap: spacing.md }}>
        <Skeleton w="40%" h={12} radius={radius.sm} />
        <Skeleton w="70%" h={22} radius={radius.sm} />
        <Skeleton w="90%" h={14} radius={radius.sm} />
      </View>
    );
  }
  const clean = mission.due_count === 0;
  return (
    <HeroCard
      overline="TODAY'S MISSION"
      title={clean ? `${greeting()}, ${mission.greeting_name}. You're clear.` : `${greeting()}, ${mission.greeting_name}. ${mission.due_count} follow-up${mission.due_count === 1 ? "" : "s"} need you.`}
      subtitle={clean
        ? "No revenue is at risk right now — great work staying ahead."
        : `₹${mission.revenue_at_risk_short.replace("₹", "")} potential revenue at risk · ${mission.overdue_payments} overdue payment${mission.overdue_payments === 1 ? "" : "s"} · ${mission.quotations_expiring_today} quotation${mission.quotations_expiring_today === 1 ? "" : "s"} expiring today · Est. ${mission.estimated_minutes} min to clear`}
      icon={clean ? "check-circle" : "zap"}
      iconTone={clean ? "success" : mission.critical_count > 0 ? "danger" : "brand"}
      actions={clean ? undefined : <Button label="Start with #1" icon="arrow-right" variant="primary" size="md" onPress={onJumpTop} testID="mission-jump-top" />}
      metaRow={!clean && mission.top_priorities.length ? (
        <View style={{ gap: spacing.sm, marginTop: spacing.sm }}>
          <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: colors.divider }} />
          {mission.top_priorities.map((p, i) => (
            <View key={p.id} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
              <View style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: colors.brandTint, alignItems: "center", justifyContent: "center" }}>
                <Text style={{ fontSize: 11, fontWeight: "700", color: colors.brand }}>{i + 1}</Text>
              </View>
              <Text style={[type.bodySm, { flex: 1 }]} numberOfLines={1}>{p.customer_name} — {p.reason}</Text>
              <Badge label={String(p.priority_score)} tone="brand" size="sm" />
            </View>
          ))}
        </View>
      ) : undefined}
    />
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// InsightsPanel — bottom-right insights (calls, WhatsApps, payments, response)
// ─────────────────────────────────────────────────────────────────────────────
function InsightsPanel({ insights }: { insights: Insights | null }) {
  return (
    <Panel title="Today's conversion" overline="INSIGHTS">
      {!insights ? (
        <View style={{ gap: spacing.sm }}>
          <Skeleton w="100%" h={14} radius={radius.sm} />
          <Skeleton w="100%" h={14} radius={radius.sm} />
        </View>
      ) : (
        <View style={{ gap: spacing.sm }}>
          <InsightRow icon="phone" label="Calls completed" value={String(insights.calls_completed)} />
          <InsightRow icon="message-circle" label="WhatsApps sent" value={String(insights.whatsapps_sent)} />
          <InsightRow icon="credit-card" label="Payments collected" value={moneyShort(insights.payments_collected)} />
          <InsightRow icon="check-square" label="Quotations approved" value={String(insights.quotations_approved)} />
          <InsightRow icon="activity" label="Response rate" value={`${insights.response_rate}%`} />
        </View>
      )}
    </Panel>
  );
}
function InsightRow({ icon, label, value }: { icon: FeatherName; label: string; value: string }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
      <View style={{ width: 26, height: 26, borderRadius: 8, backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center" }}>
        <Feather name={icon} size={13} color={colors.onSurfaceSecondary} />
      </View>
      <Text style={[type.bodySm, { flex: 1 }]}>{label}</Text>
      <Text style={{ fontSize: 13, fontWeight: "700", color: colors.onSurface, fontVariant: ["tabular-nums"] }}>{value}</Text>
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// InboxSection — collapsible bucket group
// ─────────────────────────────────────────────────────────────────────────────
function InboxSection({
  bucket, items, collapsed, onToggle, selectedId, assignees, rankMap, selectedIds, onToggleSelect,
  onSelect, onCall, onWhatsApp, onEmail, onComplete, onSnooze, onCustomSnooze, onAssign, onNote, onDismiss,
}: {
  bucket: Bucket; items: Followup[]; collapsed: boolean; onToggle: () => void; selectedId: string | null;
  assignees: Assignee[]; rankMap: Map<string, number>; selectedIds: Set<string>; onToggleSelect: (id: string) => void;
  onSelect: (f: Followup) => void;
  onCall: (f: Followup) => void; onWhatsApp: (f: Followup) => void; onEmail: (f: Followup) => void;
  onComplete: (f: Followup) => void; onSnooze: (f: Followup, preset: "15m" | "1h" | "tomorrow" | "next_week") => void;
  onCustomSnooze: (f: Followup) => void; onAssign: (f: Followup, userId: string) => void;
  onNote: (f: Followup) => void; onDismiss: (f: Followup) => void;
}) {
  const meta = BUCKET_META[bucket];
  return (
    <View style={{ gap: spacing.sm }}>
      <Pressable onPress={onToggle} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 4 }}>
        <Feather name={meta.icon} size={14} color={colors.onSurfaceSecondary} />
        <Text style={type.overline}>{meta.label}</Text>
        <Badge label={String(items.length)} tone="neutral" size="sm" />
        <View style={{ flex: 1 }} />
        <Feather name={collapsed ? "chevron-down" : "chevron-up"} size={16} color={colors.onSurfaceMuted} />
      </Pressable>
      {!collapsed ? (
        <View style={{ gap: spacing.sm }}>
          {items.map((f) => (
            <FollowupCard
              key={f.id}
              f={f}
              active={f.id === selectedId}
              assignees={assignees}
              rank={rankMap.get(f.id)}
              checked={selectedIds.has(f.id)}
              onToggleSelect={() => onToggleSelect(f.id)}
              onPress={() => onSelect(f)}
              onCall={() => onCall(f)}
              onWhatsApp={() => onWhatsApp(f)}
              onEmail={() => onEmail(f)}
              onComplete={() => onComplete(f)}
              onSnooze={(p) => onSnooze(f, p)}
              onCustomSnooze={() => onCustomSnooze(f)}
              onAssign={(uid) => onAssign(f, uid)}
              onNote={() => onNote(f)}
              onDismiss={() => onDismiss(f)}
            />
          ))}
        </View>
      ) : null}
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ScoreBadge — the AI Priority Score. Explainable, deterministic.
// ─────────────────────────────────────────────────────────────────────────────
function ScoreBadge({ score, level }: { score: number; level: PriorityLevel }) {
  const tone = PRIORITY_TONE[level];
  return (
    <View style={{ alignItems: "center", gap: 2, minWidth: 46 }}>
      <View style={{ width: 38, height: 38, borderRadius: 19, backgroundColor: tone.bg, borderWidth: 1.5, borderColor: tone.border, alignItems: "center", justifyContent: "center" }}>
        <Text style={{ fontSize: 15, fontWeight: "700", color: tone.fg, fontVariant: ["tabular-nums"] }}>{score}</Text>
      </View>
      <Text style={{ fontSize: 9, fontWeight: "700", color: tone.fg, letterSpacing: 0.4, textTransform: "uppercase" }}>{level}</Text>
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// IconMenuButton — icon-only trigger + small overlay menu (promoted Snooze /
// Assign — closes the "top actions buried 2 clicks deep" audit finding).
// ─────────────────────────────────────────────────────────────────────────────
function IconMenuButton({ icon, tone = "surface", accessibilityLabel, items, testID }: {
  icon: FeatherName; tone?: "surface" | "brandLight"; accessibilityLabel?: string;
  items: { label: string; icon?: FeatherName; onPress: () => void; tone?: "default" | "danger" }[];
  testID?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <View style={{ position: "relative" }}>
      <IconButton icon={icon} onPress={() => setOpen((v) => !v)} size={34} tone={tone} accessibilityLabel={accessibilityLabel} testID={testID} />
      {open ? (
        <>
          <Pressable onPress={() => setOpen(false)} style={StyleSheet.absoluteFillObject as any} />
          <View style={[{
            position: "absolute", top: 38, left: 0, minWidth: 190,
            borderRadius: radius.md, backgroundColor: colors.surfaceSecondary,
            borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
            paddingVertical: 4, zIndex: 100,
          }, elevation.overlay]}>
            {items.map((it, i) => (
              <Pressable
                key={i}
                onPress={() => { setOpen(false); it.onPress(); }}
                style={({ pressed, hovered }: any) => ({
                  flexDirection: "row", alignItems: "center", gap: spacing.sm,
                  paddingVertical: 10, paddingHorizontal: spacing.md,
                  backgroundColor: pressed ? colors.surfaceTertiary : hovered ? colors.surfaceSubtle : "transparent",
                })}
              >
                {it.icon ? <Feather name={it.icon} size={14} color={it.tone === "danger" ? colors.error : colors.onSurfaceSecondary} /> : null}
                <Text style={{ fontSize: 13, fontWeight: "500", color: it.tone === "danger" ? colors.error : colors.onSurface }}>{it.label}</Text>
              </Pressable>
            ))}
          </View>
        </>
      ) : null}
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// FollowupCard — the inbox row. Swipe right=Complete, left=Snooze (mobile).
// Long-press = quick Assign. Left-edge color bar = instant priority scan.
// ─────────────────────────────────────────────────────────────────────────────
function FollowupCard({
  f, active, assignees, rank, checked, onToggleSelect,
  onPress, onCall, onWhatsApp, onEmail, onComplete, onSnooze, onCustomSnooze, onAssign, onNote, onDismiss,
}: {
  f: Followup; active: boolean; assignees: Assignee[]; rank?: number; checked: boolean; onToggleSelect: () => void;
  onPress: () => void; onCall: () => void; onWhatsApp: () => void; onEmail: () => void;
  onComplete: () => void; onSnooze: (p: "15m" | "1h" | "tomorrow" | "next_week") => void;
  onCustomSnooze: () => void; onAssign: (userId: string) => void; onNote: () => void; onDismiss: () => void;
}) {
  const level = f.manual_priority_override || f.priority_level;
  const tone = PRIORITY_TONE[level];
  const isResolved = f.status === "done" || f.status === "dismissed";
  const overdueDue = f.bucket === "overdue";
  const swipeRef = useRef<Swipeable>(null);

  const content = (
    <HoverCard onPress={onPress} padding={spacing.md} testID={`followup-${f.id}`} style={{
      borderColor: active ? colors.brand : colors.border,
      backgroundColor: active ? colors.brandTint : colors.surfaceSecondary,
      borderLeftWidth: 4,
      borderLeftColor: isResolved ? colors.border : tone.fg,
      ...(active ? elevation.medium : {}),
    }}>
      <View style={{ gap: spacing.sm }}>
        {/* Header row */}
        <View style={{ flexDirection: "row", alignItems: "flex-start", gap: spacing.sm }}>
          {!isResolved ? (
            <Pressable onPress={onToggleSelect} hitSlop={8} style={{ paddingTop: 2 }} accessibilityLabel="Select">
              <Feather name={checked ? "check-square" : "square"} size={18} color={checked ? colors.brand : colors.onSurfaceMuted} />
            </Pressable>
          ) : null}
          <Avatar name={f.customer_name} size={38} tone="brand" />
          <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
              {rank ? (
                <View style={styles.rankChip}>
                  <Text style={styles.rankChipText}>#{rank}</Text>
                </View>
              ) : null}
              <Text style={type.titleSm} numberOfLines={1}>{f.customer_name}</Text>
              {f.is_automated ? <Badge label="Auto" tone="info" size="sm" icon="zap" /> : null}
            </View>
            <Text style={type.caption} numberOfLines={1}>
              {[f.project_name, f.quotation_number || f.purchase_number].filter(Boolean).join(" · ") || "General follow-up"}
            </Text>
          </View>
          {!isResolved ? <ScoreBadge score={f.priority_score} level={level} /> : (
            <Badge label={f.status === "dismissed" ? "Dismissed" : (f.completed_outcome || "Done")} tone={f.status === "dismissed" ? "neutral" : "success"} size="sm" />
          )}
        </View>

        {/* Revenue — dedicated visual chip (was buried in prose; audit gap) */}
        {f.value > 0 ? (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm, paddingHorizontal: 8, paddingVertical: 3 }}>
            <Feather name="trending-up" size={11} color={colors.onSurfaceSecondary} />
            <Text style={{ fontSize: 12, fontWeight: "700", color: colors.onSurface }}>₹{moneyShort(f.value)}</Text>
            <Text style={type.caption}>at stake</Text>
          </View>
        ) : null}

        {/* Reason + explainability */}
        <View style={{ gap: 2 }}>
          <Text style={type.bodySm} numberOfLines={2}>{f.reason}</Text>
          {f.reason_factors?.length ? (
            <Text style={type.caption} numberOfLines={1}>{f.reason_factors.join(" · ")}</Text>
          ) : null}
        </View>

        {/* Tags */}
        {f.tags?.length ? (
          <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
            {f.tags.map((t, i) => <Badge key={`${t}-${i}`} label={t} tone="neutral" size="sm" />)}
          </View>
        ) : null}

        {/* Next Best Action */}
        {!isResolved ? (
          <View style={{ backgroundColor: colors.brandTint, borderRadius: radius.sm, padding: spacing.sm, gap: 2 }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <Feather name={CHANNEL_ICON[f.suggested_channel]} size={12} color={colors.brand} />
              <Text style={{ fontSize: 12, fontWeight: "700", color: colors.brand }}>{f.next_action}</Text>
            </View>
            <Text style={{ fontSize: 11, color: colors.brand, opacity: 0.85 }} numberOfLines={2}>{f.next_action_reason}</Text>
          </View>
        ) : f.resolution_note ? (
          <Text style={type.caption} numberOfLines={2}>{f.resolution_note}</Text>
        ) : null}

        {/* Meta row */}
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm }}>
          <Text style={{ fontSize: 12, fontWeight: "600", color: overdueDue ? colors.error : colors.onSurfaceSecondary }}>{dueLabel(f)}</Text>
          <Text style={type.caption} numberOfLines={1}>{timeAgo(f.last_contacted_at)}</Text>
        </View>
        {f.assigned_to_name ? (
          <Text style={type.caption}>Assigned to {f.assigned_to_name}</Text>
        ) : null}

        {/* Actions — Call/WhatsApp/Snooze/Assign/Complete are 1-click; the
            rest (Email, custom snooze, note, dismiss) live in the overflow. */}
        {!isResolved ? (
          <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center", flexWrap: "wrap", marginTop: 2 }}>
            <IconButton icon="phone" onPress={onCall} size={34} tone="brandLight" accessibilityLabel="Call" testID={`call-${f.id}`} />
            <IconButton icon="message-circle" onPress={onWhatsApp} size={34} tone="surface" accessibilityLabel="WhatsApp" testID={`wa-${f.id}`} />
            <IconMenuButton
              icon="clock" accessibilityLabel="Snooze" testID={`snooze-${f.id}`}
              items={[
                { label: "Snooze 15 min", icon: "clock", onPress: () => onSnooze("15m") },
                { label: "Snooze 1 hour", icon: "clock", onPress: () => onSnooze("1h") },
                { label: "Snooze till tomorrow", icon: "sunrise", onPress: () => onSnooze("tomorrow") },
                { label: "Snooze next week", icon: "calendar", onPress: () => onSnooze("next_week") },
                { label: "Custom snooze…", icon: "edit-2", onPress: onCustomSnooze },
              ]}
            />
            <IconMenuButton
              icon="user-plus" accessibilityLabel="Assign" testID={`assign-${f.id}`}
              items={assignees.map((a) => ({ label: `Assign to ${a.full_name}`, icon: "user" as FeatherName, onPress: () => onAssign(a.id) }))}
            />
            <IconButton icon="check" onPress={onComplete} size={34} tone="surface" accessibilityLabel="Mark complete" testID={`complete-${f.id}`} />
            <Dropdown
              label="More" icon="more-horizontal" variant="secondary"
              items={[
                { label: "Email", icon: "mail", onPress: onEmail },
                { label: "Add note", icon: "edit-3", onPress: onNote },
                { label: "Dismiss", icon: "x-circle", tone: "danger" as const, onPress: onDismiss },
              ]}
            />
          </View>
        ) : null}
      </View>
    </HoverCard>
  );

  if (Platform.OS === "web" || isResolved) return content;

  return (
    <Swipeable
      ref={swipeRef}
      friction={2}
      leftThreshold={40}
      rightThreshold={40}
      renderLeftActions={() => (
        <View style={[styles.swipeAction, { backgroundColor: colors.success }]}>
          <Feather name="check" size={18} color={colors.onBrand} />
          <Text style={styles.swipeText}>Complete</Text>
        </View>
      )}
      renderRightActions={() => (
        <View style={[styles.swipeAction, { backgroundColor: colors.warning }]}>
          <Text style={styles.swipeText}>Snooze</Text>
          <Feather name="clock" size={18} color={colors.onBrand} />
        </View>
      )}
      onSwipeableOpen={(direction) => {
        swipeRef.current?.close();
        if (direction === "left") onComplete();
        else onSnooze("1h");
      }}
    >
      <Pressable onLongPress={() => assignees[0] && onAssign(assignees[0].id)} delayLongPress={450}>
        {content}
      </Pressable>
    </Swipeable>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ContextPanel — full customer context (desktop right column / mobile sheet)
// ─────────────────────────────────────────────────────────────────────────────
function ContextPanel({ detail, loading, embedded }: { detail: Detail | null; loading: boolean; embedded?: boolean }) {
  if (loading) {
    return (
      <Panel title="Customer" overline="CONTEXT">
        <View style={{ gap: spacing.sm }}>
          <Skeleton w="60%" h={16} radius={radius.sm} />
          <Skeleton w="90%" h={12} radius={radius.sm} />
          <Skeleton w="100%" h={60} radius={radius.md} />
        </View>
      </Panel>
    );
  }
  if (!detail) {
    return embedded ? null : (
      <Panel title="Customer" overline="CONTEXT">
        <EmptyState icon="user" title="Select a follow-up" subtitle="Choose a card on the left to see full customer context, timeline and history." />
      </Panel>
    );
  }
  const { followup, customer, stats, quotations, purchases, timeline } = detail;
  return (
    <View style={{ gap: spacing.md }}>
      <Panel overline="CONTEXT" title={customer.company || customer.name}>
        <View style={{ gap: spacing.sm }}>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
            {customer.phone ? <Badge label={customer.phone} tone="neutral" size="sm" icon="phone" /> : null}
            {customer.email ? <Badge label={customer.email} tone="neutral" size="sm" icon="mail" /> : null}
            {customer.city ? <Badge label={customer.city} tone="neutral" size="sm" icon="map-pin" /> : null}
            <Badge label={(customer.tier || "retail").toUpperCase()} tone={customer.tier === "vip" ? "success" : customer.tier === "trade" ? "info" : "neutral"} size="sm" />
            <Badge
              label={`${stats.risk_level.toUpperCase()} RISK`}
              tone={stats.risk_level === "high" ? "error" : stats.risk_level === "medium" ? "warning" : "success"}
              size="sm" icon="shield"
            />
          </View>
          {customer.address ? <Text style={type.caption}>{customer.address}</Text> : null}
          {(followup.assigned_to_name || stats.preferred_salesperson) ? (
            <Text style={type.caption}>
              Salesperson: {followup.assigned_to_name || "—"}
              {stats.preferred_salesperson && stats.preferred_salesperson !== followup.assigned_to_name ? ` · Usually served by ${stats.preferred_salesperson}` : ""}
            </Text>
          ) : null}
        </View>
      </Panel>

      <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
        <StatTile dense label="Lifetime Revenue" value={moneyShort(stats.lifetime_revenue)} icon="trending-up" tone="brand" />
        <StatTile dense label="Outstanding" value={moneyShort(stats.outstanding_total)} icon="alert-circle" tone={stats.outstanding_total > 0 ? "danger" : "success"} />
        <StatTile dense label="Conversion Rate" value={`${stats.conversion_rate}%`} icon="percent" tone="neutral" />
        <StatTile dense label="Avg. Order Value" value={moneyShort(stats.average_order_value)} icon="bar-chart-2" tone="neutral" />
        <StatTile dense label="Pending Quotations" value={String(stats.pending_quotations)} icon="file-text" tone="neutral" />
        <StatTile dense label="Pending Orders" value={String(stats.pending_orders)} icon="package" tone="neutral" />
      </View>

      {quotations.length ? (
        <Panel title="Pending quotations" overline="QUOTATIONS">
          <View style={{ gap: spacing.sm }}>
            {quotations.slice(0, 5).map((q) => (
              <View key={q.id} style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <Text style={type.bodySm} numberOfLines={1}>{q.number}</Text>
                <Text style={{ fontSize: 13, fontWeight: "700", color: colors.onSurface }}>{moneyShort(q.grand_total)}</Text>
              </View>
            ))}
          </View>
        </Panel>
      ) : null}

      {purchases.length ? (
        <Panel title="Recent purchases" overline="PURCHASES">
          <View style={{ gap: spacing.sm }}>
            {purchases.slice(0, 5).map((p) => (
              <View key={p.id} style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <Text style={type.bodySm} numberOfLines={1}>{p.number}</Text>
                <Badge label={p.status.replace(/_/g, " ")} tone="neutral" size="sm" />
              </View>
            ))}
          </View>
        </Panel>
      ) : null}

      <Panel title="Timeline" overline="ACTIVITY">
        <ActivityTimeline events={timeline} emptyLabel="No activity logged yet for this customer." />
      </Panel>
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CallOutcomeSheet
// ─────────────────────────────────────────────────────────────────────────────
const OUTCOMES: { value: string; label: string; icon: FeatherName; tone: "success" | "warning" | "danger" | "brand" }[] = [
  { value: "interested", label: "Interested", icon: "thumbs-up", tone: "success" },
  { value: "call_back", label: "Call Back", icon: "phone-call", tone: "brand" },
  { value: "no_answer", label: "No Answer", icon: "phone-missed", tone: "warning" },
  { value: "rejected", label: "Rejected", icon: "thumbs-down", tone: "danger" },
  { value: "converted", label: "Converted", icon: "award", tone: "success" },
];
function CallOutcomeSheet({ visible, f, onClose, onSubmit }: {
  visible: boolean; f: Followup | null; onClose: () => void; onSubmit: (f: Followup, outcome: string, notes?: string) => void;
}) {
  const [outcome, setOutcome] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  useEffect(() => { if (visible) { setOutcome(null); setNotes(""); } }, [visible]);
  if (!f) return null;
  return (
    <Sheet visible={visible} onClose={onClose} variant="modal" title="Log Call Outcome" subtitle={f.customer_name} width={440}
      footer={<>
        <Button label="Cancel" variant="secondary" onPress={onClose} size="md" />
        <View style={{ flex: 1 }} />
        <Button label="Save" variant="primary" icon="check" disabled={!outcome} onPress={() => outcome && onSubmit(f, outcome, notes || undefined)} size="md" testID="save-call-outcome" />
      </>}
    >
      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.md }}>
        <Text style={type.overline}>OUTCOME</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
          {OUTCOMES.map((o) => {
            const on = outcome === o.value;
            const tone = { success: colors.success, warning: colors.warning, danger: colors.error, brand: colors.brand }[o.tone];
            return (
              <Pressable key={o.value} testID={`outcome-${o.value}`} onPress={() => setOutcome(o.value)}
                style={{
                  paddingHorizontal: spacing.md, height: 40, borderRadius: radius.md,
                  borderWidth: StyleSheet.hairlineWidth, borderColor: on ? tone : colors.border,
                  backgroundColor: on ? tone : colors.surfaceSecondary,
                  flexDirection: "row", alignItems: "center", gap: 6,
                }}
              >
                <Feather name={o.icon} size={14} color={on ? colors.onBrand : colors.onSurfaceSecondary} />
                <Text style={{ fontSize: 13, fontWeight: "600", color: on ? colors.onBrand : colors.onSurface }}>{o.label}</Text>
              </Pressable>
            );
          })}
        </View>
        <FormField label="Notes" helper="Optional — visible on the customer timeline">
          <TextInput value={notes} onChangeText={setNotes} placeholder="What did the customer say?" placeholderTextColor={colors.onSurfaceMuted}
            style={styles.textArea} multiline testID="outcome-notes" />
        </FormField>
      </ScrollView>
    </Sheet>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// NoteSheet
// ─────────────────────────────────────────────────────────────────────────────
function NoteSheet({ visible, f, onClose, onSave }: { visible: boolean; f: Followup | null; onClose: () => void; onSave: (f: Followup, notes: string) => void }) {
  const [notes, setNotes] = useState("");
  useEffect(() => { setNotes(f?.notes || ""); }, [f]);
  if (!f) return null;
  return (
    <Sheet visible={visible} onClose={onClose} variant="modal" title="Add Note" subtitle={f.customer_name} width={420}
      footer={<>
        <Button label="Cancel" variant="secondary" onPress={onClose} size="md" />
        <View style={{ flex: 1 }} />
        <Button label="Save Note" variant="primary" icon="check" onPress={() => onSave(f, notes)} size="md" />
      </>}
    >
      <View style={{ padding: spacing.xl }}>
        <TextInput value={notes} onChangeText={setNotes} placeholder="Write a note…" placeholderTextColor={colors.onSurfaceMuted}
          style={styles.textArea} multiline autoFocus testID="note-input" />
      </View>
    </Sheet>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CustomSnoozeSheet
// ─────────────────────────────────────────────────────────────────────────────
function CustomSnoozeSheet({ visible, f, onClose, onSave }: { visible: boolean; f: Followup | null; onClose: () => void; onSave: (f: Followup, untilIso: string) => void }) {
  const [date, setDate] = useState("");
  const [time, setTime] = useState("09:00");
  useEffect(() => {
    if (visible) {
      const d = new Date(Date.now() + 86400000);
      setDate(d.toISOString().slice(0, 10));
      setTime("09:00");
    }
  }, [visible]);
  if (!f) return null;
  const submit = () => {
    if (!date) { toast.error("Pick a date"); return; }
    const iso = new Date(`${date}T${time || "09:00"}:00`).toISOString();
    onSave(f, iso);
  };
  return (
    <Sheet visible={visible} onClose={onClose} variant="modal" title="Custom Snooze" subtitle={f.customer_name} width={400}
      footer={<>
        <Button label="Cancel" variant="secondary" onPress={onClose} size="md" />
        <View style={{ flex: 1 }} />
        <Button label="Snooze" variant="primary" icon="clock" onPress={submit} size="md" />
      </>}
    >
      <View style={{ padding: spacing.xl, gap: spacing.md }}>
        <FormField label="Date">
          {Platform.OS === "web" ? (
            // @ts-ignore native HTML date input
            <input type="date" value={date} onChange={(e: any) => setDate(e.target.value)}
              style={{ border: `1px solid ${colors.border}`, borderRadius: radius.md, padding: "10px 12px", fontSize: 14, backgroundColor: colors.surfaceSecondary, color: colors.onSurface, fontFamily: "inherit", outline: "none", boxSizing: "border-box", height: 40 } as any} />
          ) : (
            <TextInput value={date} onChangeText={setDate} placeholder="YYYY-MM-DD" placeholderTextColor={colors.onSurfaceMuted} style={styles.textInput} />
          )}
        </FormField>
        <FormField label="Time">
          {Platform.OS === "web" ? (
            // @ts-ignore native HTML time input
            <input type="time" value={time} onChange={(e: any) => setTime(e.target.value)}
              style={{ border: `1px solid ${colors.border}`, borderRadius: radius.md, padding: "10px 12px", fontSize: 14, backgroundColor: colors.surfaceSecondary, color: colors.onSurface, fontFamily: "inherit", outline: "none", boxSizing: "border-box", height: 40 } as any} />
          ) : (
            <TextInput value={time} onChangeText={setTime} placeholder="HH:MM" placeholderTextColor={colors.onSurfaceMuted} style={styles.textInput} />
          )}
        </FormField>
      </View>
    </Sheet>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// NewFollowupSheet — manual reminder
// ─────────────────────────────────────────────────────────────────────────────
const NEW_CATEGORIES = ["general", "quotation", "payment", "sales", "support"] as const;
const NEW_CHANNELS: Channel[] = ["call", "whatsapp", "email", "visit"];
function NewFollowupSheet({ visible, onClose, customers, assignees, defaultAssignee, onCreate }: {
  visible: boolean; onClose: () => void; customers: CustomerLite[]; assignees: Assignee[]; defaultAssignee?: string;
  onCreate: (payload: any) => void;
}) {
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [customerQuery, setCustomerQuery] = useState("");
  const [category, setCategory] = useState<string>("general");
  const [channel, setChannel] = useState<Channel>("call");
  const [reason, setReason] = useState("");
  const [assignedTo, setAssignedTo] = useState<string | undefined>(defaultAssignee);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (visible) { setCustomerId(null); setCustomerQuery(""); setCategory("general"); setChannel("call"); setReason(""); setAssignedTo(defaultAssignee); }
  }, [visible, defaultAssignee]);

  const matches = useMemo(() => {
    const term = customerQuery.trim().toLowerCase();
    if (!term) return customers.slice(0, 8);
    return customers.filter((c) => (c.company || c.name).toLowerCase().includes(term) || c.phone?.includes(term)).slice(0, 8);
  }, [customers, customerQuery]);
  const selectedCustomer = customers.find((c) => c.id === customerId);

  const submit = async () => {
    if (!customerId) { toast.error("Choose a customer"); return; }
    if (!reason.trim()) { toast.error("Add a reason"); return; }
    setSaving(true);
    try { await onCreate({ customer_id: customerId, category, channel, reason: reason.trim(), assigned_to: assignedTo }); }
    finally { setSaving(false); }
  };

  return (
    <Sheet visible={visible} onClose={onClose} variant="drawer" title="New Follow-up" subtitle="Manually add a reminder — the workspace will rank it alongside automated cards."
      footer={<>
        <Button label="Cancel" variant="secondary" onPress={onClose} size="md" />
        <View style={{ flex: 1 }} />
        <Button label="Create Follow-up" variant="primary" icon="plus" loading={saving} onPress={submit} size="md" testID="create-followup" />
      </>}
    >
      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg }}>
        <FormField label="Customer" required>
          <SearchField value={selectedCustomer ? (selectedCustomer.company || selectedCustomer.name) : customerQuery}
            onChangeText={(v) => { setCustomerQuery(v); setCustomerId(null); }} placeholder="Search customer…" onClear={() => { setCustomerQuery(""); setCustomerId(null); }} />
          {!customerId && matches.length ? (
            <View style={{ borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, marginTop: 6, overflow: "hidden" }}>
              {matches.map((c) => (
                <Pressable key={c.id} onPress={() => { setCustomerId(c.id); setCustomerQuery(""); }}
                  style={{ padding: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.divider }}>
                  <Text style={type.bodySm}>{c.company || c.name}</Text>
                  {c.phone ? <Text style={type.caption}>{c.phone}</Text> : null}
                </Pressable>
              ))}
            </View>
          ) : null}
        </FormField>

        <FormField label="Type">
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
            {NEW_CATEGORIES.map((c) => (
              <Chip key={c} label={c.charAt(0).toUpperCase() + c.slice(1)} active={category === c} onPress={() => setCategory(c)} />
            ))}
          </View>
        </FormField>

        <FormField label="Preferred channel">
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
            {NEW_CHANNELS.map((c) => (
              <Chip key={c} label={c.charAt(0).toUpperCase() + c.slice(1)} icon={CHANNEL_ICON[c]} active={channel === c} onPress={() => setChannel(c)} />
            ))}
          </View>
        </FormField>

        <FormField label="Reason" required helper="What should the salesperson do and why?">
          <TextInput value={reason} onChangeText={setReason} placeholder="e.g. Customer requested a call back about tile samples" placeholderTextColor={colors.onSurfaceMuted}
            style={styles.textArea} multiline testID="new-followup-reason" />
        </FormField>

        <FormField label="Assign to">
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
            {assignees.map((a) => (
              <Chip key={a.id} label={a.full_name} active={assignedTo === a.id} onPress={() => setAssignedTo(a.id)} />
            ))}
          </View>
        </FormField>
      </ScrollView>
    </Sheet>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// AutomationRulesSheet — the visible automation engine
// ─────────────────────────────────────────────────────────────────────────────
function AutomationRulesSheet({ visible, onClose, rules }: { visible: boolean; onClose: () => void; rules: RuleInfo[] }) {
  return (
    <Sheet visible={visible} onClose={onClose} variant="drawer" title="Automation Rules"
      subtitle="Every card below is generated live by reconciling quotations, payments and purchases — never by hand.">
      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.md }}>
        {rules.map((r) => (
          <Card key={r.rule_type} variant="outlined">
            <View style={{ flexDirection: "row", alignItems: "flex-start", gap: spacing.md }}>
              <View style={{ width: 34, height: 34, borderRadius: radius.sm, backgroundColor: colors.brandTint, alignItems: "center", justifyContent: "center" }}>
                <Feather name={CATEGORY_ICON[r.category] || "flag"} size={16} color={colors.brand} />
              </View>
              <View style={{ flex: 1, gap: 2 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <Text style={type.titleSm}>{r.label}</Text>
                  <Badge label="Generated Automatically" tone="info" size="sm" icon="zap" />
                </View>
                <Text style={type.caption}>{r.description}</Text>
              </View>
              <Badge label={`${r.active_count} active`} tone={r.active_count > 0 ? "brand" : "neutral"} size="sm" />
            </View>
          </Card>
        ))}
        <Text style={[type.caption, { textAlign: "center", marginTop: spacing.sm }]}>
          Manual reminders (via the &quot;+ New Follow-up&quot; button, or a logged call outcome) are the only cards a human creates directly.
        </Text>
      </ScrollView>
    </Sheet>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  fabWrap: {
    position: "absolute", right: spacing.lg, bottom: spacing.xl, gap: spacing.sm,
  },
  fab: {
    width: 52, height: 52, borderRadius: 26, alignItems: "center", justifyContent: "center",
    shadowColor: "#0B1220", shadowOpacity: 0.18, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 6,
  },
  swipeAction: {
    flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    borderRadius: radius.md, marginVertical: 2,
  },
  swipeText: { color: "#FFFFFF", fontSize: 13, fontWeight: "700" },
  textInput: {
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, backgroundColor: colors.surfaceSecondary,
    color: colors.onSurface, fontFamily: type.body.fontFamily, height: 40,
    ...(Platform.OS === "web" ? { outlineStyle: "none" } as any : {}),
  },
  textArea: {
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, backgroundColor: colors.surfaceSecondary,
    color: colors.onSurface, fontFamily: type.body.fontFamily, minHeight: 90, textAlignVertical: "top",
    ...(Platform.OS === "web" ? { outlineStyle: "none" } as any : {}),
  },
  rankChip: {
    minWidth: 20, height: 20, borderRadius: 10, paddingHorizontal: 5,
    backgroundColor: colors.onSurface, alignItems: "center", justifyContent: "center",
  },
  rankChipText: { fontSize: 10, fontWeight: "800", color: colors.onSurfaceInverse },
  bulkBar: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.brandBorder,
    padding: spacing.md,
  },
});
