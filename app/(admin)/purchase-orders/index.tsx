// Purchase Orders Dashboard
// -----------------------------------------------------------------------------
// The operational heart of Forge. Shows POs across 8 lifecycle statuses.
//
//   * Tablet ≥ 900px: horizontal kanban board with a column per status.
//   * Phone: vertical status tabs + list view.
//
// The Kanban columns are ordered per the ALLOWED_TRANSITIONS state machine on
// the backend. Cards are one-tap → open PO detail. Search bar filters live.
// -----------------------------------------------------------------------------
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Badge, Card, EmptyState, Skeleton } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type PoStatus =
  | "draft" | "awaiting_review" | "ordered" | "awaiting_supplier"
  | "partial_received" | "fully_received" | "packed" | "ready_for_dispatch" | "cancelled";

type PO = {
  id: string;
  number: string;
  quotation_number?: string | null;
  customer_name: string;
  brand_name?: string | null;
  supplier_name?: string | null;
  status: PoStatus;
  items: { id: string; qty: number; qty_received: number; sku: string }[];
  grand_total: number;
  created_at: string;
  expected_delivery_at?: string | null;
};

type ColumnStat = { status: PoStatus; label: string; count: number; value: number };
type DashboardResp = { columns: ColumnStat[]; total_open_value: number };

const STATUS_TONE: Record<PoStatus, string> = {
  draft: colors.onSurfaceMuted,
  awaiting_review: colors.warning,
  ordered: colors.info,
  awaiting_supplier: colors.info,
  partial_received: colors.warning,
  fully_received: colors.success,
  packed: colors.success,
  ready_for_dispatch: colors.success,
  cancelled: colors.error,
};

export default function PurchaseOrdersDashboard() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;

  const [stats, setStats] = useState<DashboardResp | null>(null);
  const [orders, setOrders] = useState<PO[] | null>(null);
  const [q, setQ] = useState("");
  const [filterStatus, setFilterStatus] = useState<PoStatus | "all">("all");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, l] = await Promise.all([
        api.get<DashboardResp>("/purchase-orders/dashboard"),
        api.get<PO[]>(`/purchase-orders${q ? `?q=${encodeURIComponent(q)}` : ""}`),
      ]);
      setStats(d);
      setOrders(l);
    } catch (e) {
      setStats({ columns: [], total_open_value: 0 });
      setOrders([]);
    }
  }, [q]);

  useEffect(() => { load(); }, [load]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  const byStatus = useMemo(() => {
    const m: Record<string, PO[]> = {};
    for (const p of orders || []) {
      (m[p.status] ||= []).push(p);
    }
    return m;
  }, [orders]);

  const filteredList = useMemo(
    () => (orders || []).filter((p) => filterStatus === "all" || p.status === filterStatus),
    [orders, filterStatus],
  );

  const totalPOs = orders?.length ?? 0;
  const openValue = stats?.total_open_value ?? 0;

  return (
    <AdminPage
      title="Purchases"
      subtitle={
        stats
          ? `${totalPOs} orders · ₹${openValue.toLocaleString("en-IN", { maximumFractionDigits: 0 })} in flight`
          : "Loading operations…"
      }
    >
      {/* Search bar */}
      <View style={styles.searchWrap}>
        <Feather name="search" size={16} color={colors.onSurfaceMuted} />
        <TextInput
          testID="po-search"
          value={q}
          onChangeText={setQ}
          placeholder="Search PO #, customer, brand, supplier, SKU…"
          placeholderTextColor={colors.onSurfaceMuted}
          style={styles.searchInput}
        />
        {q ? (
          <Pressable onPress={() => setQ("")}>
            <Feather name="x-circle" size={16} color={colors.onSurfaceMuted} />
          </Pressable>
        ) : null}
      </View>

      {!orders ? (
        <View style={{ gap: spacing.md }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}><Skeleton w="70%" h={14} /><View style={{ height: 8 }} /><Skeleton w="40%" h={12} /></Card>
          ))}
        </View>
      ) : orders.length === 0 ? (
        <EmptyState
          icon="shopping-cart"
          title="No Purchase Orders yet"
          subtitle="POs will appear here once you Place Order on an approved quotation."
        />
      ) : isTablet ? (
        <KanbanBoard
          stats={stats}
          byStatus={byStatus}
          onOpenPo={(id) => router.push(`/(admin)/purchase-orders/${id}` as any)}
          onRefresh={onRefresh}
          refreshing={refreshing}
        />
      ) : (
        <MobileList
          stats={stats}
          orders={filteredList}
          filterStatus={filterStatus}
          setFilterStatus={setFilterStatus}
          onOpenPo={(id) => router.push(`/(admin)/purchase-orders/${id}` as any)}
          onRefresh={onRefresh}
          refreshing={refreshing}
        />
      )}
    </AdminPage>
  );
}

// -----------------------------------------------------------------------------
// Tablet Kanban board
// -----------------------------------------------------------------------------
function KanbanBoard({
  stats, byStatus, onOpenPo, onRefresh, refreshing,
}: {
  stats: DashboardResp | null;
  byStatus: Record<string, PO[]>;
  onOpenPo: (id: string) => void;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const columns = stats?.columns || [];
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      style={{ marginHorizontal: -spacing.lg }}
      contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.md }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      {columns.map((col) => (
        <View key={col.status} style={styles.column}>
          <View style={[styles.columnHeader, { borderTopColor: STATUS_TONE[col.status as PoStatus] }]}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Text style={type.overline}>{col.label}</Text>
              <View style={styles.countPill}>
                <Text style={{ fontSize: 11, fontWeight: "700", color: colors.onSurface }}>{col.count}</Text>
              </View>
            </View>
            <Text style={[type.caption, { marginTop: 4 }]}>
              {col.value ? money(col.value) : "—"}
            </Text>
          </View>
          <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingHorizontal: 8, paddingBottom: 8, gap: 8 }} showsVerticalScrollIndicator={false}>
            {(byStatus[col.status] || []).map((po) => (
              <PoCard key={po.id} po={po} onPress={() => onOpenPo(po.id)} />
            ))}
            {!byStatus[col.status]?.length ? (
              <Text style={[type.caption, { textAlign: "center", paddingVertical: spacing.md, opacity: 0.6 }]}>—</Text>
            ) : null}
          </ScrollView>
        </View>
      ))}
    </ScrollView>
  );
}

// -----------------------------------------------------------------------------
// Mobile list
// -----------------------------------------------------------------------------
function MobileList({
  stats, orders, filterStatus, setFilterStatus, onOpenPo, onRefresh, refreshing,
}: {
  stats: DashboardResp | null;
  orders: PO[];
  filterStatus: PoStatus | "all";
  setFilterStatus: (s: PoStatus | "all") => void;
  onOpenPo: (id: string) => void;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  return (
    <View style={{ flex: 1 }}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: 8, paddingVertical: 4 }}
      >
        <FilterChip label="All" count={orders.length} active={filterStatus === "all"} onPress={() => setFilterStatus("all")} />
        {stats?.columns.map((c) => (
          <FilterChip
            key={c.status}
            label={c.label}
            count={c.count}
            active={filterStatus === c.status}
            onPress={() => setFilterStatus(c.status as PoStatus)}
          />
        ))}
      </ScrollView>
      <ScrollView
        style={{ flex: 1, marginTop: spacing.md }}
        contentContainerStyle={{ gap: spacing.md, paddingBottom: spacing.xl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {orders.length === 0 ? (
          <EmptyState icon="inbox" title="No POs in this state" />
        ) : (
          orders.map((po) => <PoCard key={po.id} po={po} onPress={() => onOpenPo(po.id)} wide />)
        )}
      </ScrollView>
    </View>
  );
}

// -----------------------------------------------------------------------------
// Shared card
// -----------------------------------------------------------------------------
function PoCard({ po, onPress, wide }: { po: PO; onPress: () => void; wide?: boolean }) {
  const received = po.items.reduce((s, i) => s + i.qty_received, 0);
  const total = po.items.reduce((s, i) => s + i.qty, 0);
  const pct = total ? Math.round((received / total) * 100) : 0;
  return (
    <Pressable
      testID={`po-${po.id}`}
      onPress={onPress}
      style={({ pressed }) => [styles.poCard, wide && styles.poCardWide, pressed && { opacity: 0.85 }]}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
        <Text style={[type.mono, { fontSize: 12 }]}>{po.number}</Text>
        <View style={[styles.brandPill, { backgroundColor: STATUS_TONE[po.status] + "18" }]}>
          <Text style={{ fontSize: 10, fontWeight: "700", color: STATUS_TONE[po.status], letterSpacing: 0.3 }}>
            {(po.brand_name || "—").toUpperCase()}
          </Text>
        </View>
      </View>
      <Text numberOfLines={1} style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface, marginTop: 6 }}>
        {po.customer_name}
      </Text>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
        <Text style={type.caption}>{po.items.length} items{po.quotation_number ? ` · ${po.quotation_number}` : ""}</Text>
        <Text style={[type.mono, { fontSize: 12, fontWeight: "700" }]}>{money(po.grand_total)}</Text>
      </View>
      {po.status === "partial_received" ? (
        <View style={{ marginTop: 6 }}>
          <View style={{ height: 4, borderRadius: 2, backgroundColor: colors.surfaceTertiary, overflow: "hidden" }}>
            <View style={{ height: 4, width: `${pct}%`, backgroundColor: colors.success }} />
          </View>
          <Text style={[type.caption, { fontSize: 10, marginTop: 2 }]}>{pct}% received</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

function FilterChip({ label, count, active, onPress }: { label: string; count: number; active: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.filterChip, active && { backgroundColor: colors.brand, borderColor: colors.brand }]}
    >
      <Text style={{ fontSize: 12, fontWeight: "600", color: active ? colors.onBrand : colors.onSurface }}>
        {label}
      </Text>
      <View style={[styles.chipCount, active && { backgroundColor: "rgba(255,255,255,0.2)" }]}>
        <Text style={{ fontSize: 10, fontWeight: "700", color: active ? colors.onBrand : colors.onSurface }}>{count}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: 10,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
    paddingHorizontal: 14, borderRadius: radius.md,
  },
  searchInput: { flex: 1, fontSize: 14, paddingVertical: 12, color: colors.onSurface },
  column: {
    width: 280, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, overflow: "hidden",
  },
  columnHeader: {
    padding: spacing.md, borderTopWidth: 3,
    backgroundColor: colors.surfaceSecondary,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  countPill: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, backgroundColor: colors.surfaceTertiary },
  poCard: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  poCardWide: {},
  brandPill: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  filterChip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 12, height: 32, borderRadius: 999,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  chipCount: { paddingHorizontal: 6, paddingVertical: 1, borderRadius: 999, backgroundColor: colors.surfaceTertiary, minWidth: 20, alignItems: "center" },
});
