// Purchases — Material Tracker
// -----------------------------------------------------------------------------
// A per-line-item lifecycle workspace built on the same PO document store used
// by the create/receive flows. Every line item moves through 6 stages
// independently, gets recorded to an immutable stage history, and can be
// transferred to another customer (which spawns a fresh draft PO for the
// destination). Layout follows the FORGE V2 reference — Forge design language.
// -----------------------------------------------------------------------------
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { type Dispatch, type SetStateAction, useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, Linking, Modal, Platform, Pressable,
  ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { useBp } from "@/src/design/responsive";
import { ProductImage } from "@/src/components/ProductImage";
import { toast } from "@/src/components/Toast";
import { colors, radius, shadow, spacing, type } from "@/src/theme/tokens";
import { color as ds, font as dsFont } from "@/src/design/tokens";
import {
  HistorySheet, MovableItem, MoveStageSheet, TransferSheet,
} from "@/src/components/purchases/MovementEngine";

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------
type Stage =
  | "order_in_company" | "company_billing" | "in_box"
  | "dispatched" | "in_transit" | "delivered";

type StageMeta = { key: Stage; label: string; count: number; tone: { bg: string; fg: string } };

type BrandFacet = { id: string; name: string; count: number };
type CustomerFacet = { id: string; name: string; count: number; open: number };

type Item = {
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
  stage: Stage;
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

type ItemsResp = { sla_days: number; count: number; blocked_count: number; items: Item[] };

type Shortage = {
  id: string; customer_id: string; customer_name: string; sku: string; name: string; image?: string | null;
  committed_qty: number; allocated_qty: number; shortage_qty: number; reason: string;
  transferred_to_customer_name?: string | null;
};

type ViewMode = "today" | "stock" | "customers" | "dispatch_record";

const VIEW_ORDER: ViewMode[] = ["today", "stock", "customers", "dispatch_record"];
const VIEW_META: Record<ViewMode, { label: string; icon: keyof typeof Feather.glyphMap; sub: string }> = {
  today:            { label: "Today",           icon: "sun",       sub: "Attention today" },
  stock:            { label: "Stock",           icon: "package",   sub: "All stock items" },
  customers:        { label: "Customers",       icon: "users",     sub: "Grouped by customer" },
  dispatch_record:  { label: "Dispatch Record", icon: "truck",     sub: "Dispatched history" },
};

// Stage tone — one calm vocabulary; overrides whatever the backend sends.
const STAGE_TONE: Record<Stage, { bg: string; fg: string }> = {
  order_in_company: { bg: ds.sunken,    fg: ds.inkMid },
  company_billing:  { bg: ds.warnTint,  fg: ds.warn },
  in_box:           { bg: ds.sunken,    fg: ds.inkMid },
  dispatched:       { bg: ds.brassTint, fg: ds.brassDeep },
  in_transit:       { bg: ds.brassTint, fg: ds.brassDeep },
  delivered:        { bg: ds.okTint,    fg: ds.ok },
};

// -----------------------------------------------------------------------------
// Utilities
// -----------------------------------------------------------------------------
function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      day: "numeric", month: "short", year: "2-digit",
      hour: "numeric", minute: "2-digit", hour12: true,
    });
  } catch { return "—"; }
}

// -----------------------------------------------------------------------------
// Screen
// -----------------------------------------------------------------------------
export default function PurchasesScreen() {
  const router = useRouter();
  const { isDesktop } = useBp();

  // View + filter state
  const [view, setView] = useState<ViewMode>("today");
  const [brand, setBrand] = useState<string>("all");
  const [q, setQ] = useState<string>("");
  const [stage, setStage] = useState<Stage | "">("");

  // Data
  const [items, setItems] = useState<Item[]>([]);
  const [blockedCount, setBlockedCount] = useState(0);
  const [slaDays, setSlaDays] = useState(7);
  const [brands, setBrands] = useState<BrandFacet[]>([]);
  const [customers, setCustomers] = useState<CustomerFacet[]>([]);
  const [brandsTotal, setBrandsTotal] = useState(0);
  const [stages, setStages] = useState<StageMeta[]>([]);
  const [loading, setLoading] = useState(true);

  // Selection (for bulk move)
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Modals
  const [showMoveMenu, setShowMoveMenu] = useState(false);
  const [transferItem, setTransferItem] = useState<Item | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [rowMoveTarget, setRowMoveTarget] = useState<Item | null>(null);
  const [historyItemId, setHistoryItemId] = useState<string | null>(null);
  const [shortages, setShortages] = useState<Shortage[]>([]);
  const [showShortages, setShowShortages] = useState(false);

  const loadShortages = useCallback(async () => {
    try {
      const r = await api.get<{ items: Shortage[] }>("/purchases/shortages?status=awaiting_reorder");
      setShortages(r.items || []);
    } catch { /* soft-fail — non-critical banner */ }
  }, []);

  const toMovable = useCallback((r: Item): MovableItem => ({
    item_id: r.item_id, sku: r.sku, name: r.name, image: r.image, qty: r.qty,
    stage: r.stage, customer_id: r.customer_id, customer_name: r.customer_name,
    po_number: r.po_number, brand_name: r.brand_name, supplier_name: r.supplier_name,
  }), []);

  // -----------------------------------
  // Data loaders
  // -----------------------------------
  const loadFacets = useCallback(async () => {
    try {
      const [b, s, c] = await Promise.all([
        api.get<{ all: number; brands: BrandFacet[] }>("/purchases/brands"),
        api.get<StageMeta[]>("/purchases/stages"),
        api.get<CustomerFacet[]>("/purchases/customers"),
      ]);
      setBrands(b.brands); setBrandsTotal(b.all); setStages(s); setCustomers(c);
    } catch { /* Purchases remains usable when a secondary facet cannot load. */ }
  }, []);

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ view });
      if (brand && brand !== "all") qs.set("brand", brand);
      if (q) qs.set("q", q);
      if (stage) qs.set("stage", stage);
      const resp = await api.get<ItemsResp>(`/purchases/items?${qs.toString()}`);
      setItems(resp.items);
      setBlockedCount(resp.blocked_count);
      setSlaDays(resp.sla_days);
      // Prune selection to visible items
      setSelected((prev) => {
        const visible = new Set(resp.items.map((i) => i.item_id));
        const next = new Set<string>();
        prev.forEach((id) => { if (visible.has(id)) next.add(id); });
        return next;
      });
    } catch (e: any) {
      toast.error(e?.detail || "Could not load items");
    } finally { setLoading(false); }
  }, [view, brand, q, stage]);

  useEffect(() => { loadFacets(); }, [loadFacets]);
  useEffect(() => { loadShortages(); }, [loadShortages]);
  useEffect(() => {
    const t = setTimeout(loadItems, 220);
    return () => clearTimeout(t);
  }, [loadItems]);

  // -----------------------------------
  // Mutations
  // -----------------------------------
  const bulkMove = useCallback(async (toStage: Stage) => {
    if (selected.size === 0) { toast.error("Select at least one item"); return; }
    try {
      const r = await api.post<{ count: number }>(`/purchases/items/bulk-move`, {
        item_ids: Array.from(selected),
        stage: toStage,
      });
      toast.success(`Moved ${r.count} item${r.count === 1 ? "" : "s"}`);
      setSelected(new Set());
      setShowMoveMenu(false);
      await Promise.all([loadItems(), loadFacets()]);
    } catch (e: any) { toast.error(e?.detail || "Bulk move failed"); }
  }, [selected, loadItems, loadFacets]);

  const doExport = useCallback(async () => {
    const qs = new URLSearchParams({ view });
    if (brand && brand !== "all") qs.set("brand", brand);
    if (q) qs.set("q", q);
    if (stage) qs.set("stage", stage);
    try {
      const url = await api.authenticatedUrl(`/purchases/export.xlsx?${qs.toString()}`);
      if (Platform.OS === "web") {
        // @ts-ignore — web only
        window.open(url, "_blank");
      } else {
        await Linking.openURL(url);
      }
      toast.success("Excel export ready");
    } catch {
      toast.error("Export failed");
    }
  }, [view, brand, q, stage]);

  // -----------------------------------
  // Derived
  // -----------------------------------
  const blockedRows = useMemo(() => items.filter((i) => i.blocked), [items]);

  const activeStageCount = stages.reduce((acc, s) => acc + s.count, 0);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Header + top actions */}
        <View style={[styles.headerRow, !isDesktop && { flexDirection: "column", alignItems: "stretch", gap: 12 }]}>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.overline}>PURCHASES · {VIEW_META[view].label.toUpperCase()}</Text>
            <Text style={styles.pageTitle}>Purchases</Text>
            <Text style={type.bodyMuted}>
              Material tracker · {activeStageCount} item{activeStageCount === 1 ? "" : "s"} across all stages · SLA {slaDays}d
            </Text>
          </View>
          <View style={[styles.topActions, !isDesktop && { flexWrap: "wrap" }]}>
            <View style={styles.search}>
              <Feather name="search" size={14} color={colors.onSurfaceMuted} />
              <TextInput
                testID="purchases-search"
                value={q} onChangeText={setQ}
                placeholder="Search product, SKU, customer…"
                placeholderTextColor={colors.onSurfaceMuted}
                style={styles.searchInput}
                autoCorrect={false} autoCapitalize="none"
              />
              {q ? (
                <Pressable onPress={() => setQ("")} hitSlop={8}>
                  <Feather name="x" size={14} color={colors.onSurfaceMuted} />
                </Pressable>
              ) : null}
            </View>

            <Pressable testID="export-btn" onPress={doExport} style={({ pressed }) => [styles.iconAction, pressed && { opacity: 0.85 }]}>
              <Feather name="download" size={14} color={colors.success} />
              <Text style={{ color: colors.onSurface, fontWeight: "600", fontSize: 13 }}>Export .xlsx</Text>
            </Pressable>

            {shortages.length > 0 ? (
              <Pressable
                testID="shortages-btn"
                onPress={() => setShowShortages(true)}
                style={({ pressed }) => [styles.iconAction, { backgroundColor: "#FBEAEA", borderColor: "#EFC2C2" }, pressed && { opacity: 0.85 }]}
              >
                <Feather name="alert-triangle" size={14} color={colors.error} />
                <Text style={{ color: colors.error, fontWeight: "700", fontSize: 13 }}>
                  {shortages.length} Awaiting Reorder
                </Text>
              </Pressable>
            ) : null}

            <Pressable
              testID="move-material-btn"
              onPress={() => setShowMoveMenu(true)}
              disabled={selected.size === 0}
              style={({ pressed }) => [styles.iconAction, selected.size === 0 && { opacity: 0.5 }, pressed && { opacity: 0.85 }]}
            >
              <Text style={{ color: colors.onSurface, fontWeight: "600", fontSize: 13 }}>
                Move Material {selected.size > 0 ? `(${selected.size})` : ""}
              </Text>
              <Feather name="chevron-down" size={14} color={colors.onSurfaceMuted} />
            </Pressable>

            <Pressable
              testID="settings-btn"
              onPress={() => setShowSettings(true)}
              style={({ pressed }) => [styles.iconAction, pressed && { opacity: 0.85 }]}
            >
              <Feather name="sliders" size={14} color={colors.onSurfaceMuted} />
            </Pressable>
          </View>
        </View>

        {/* Body — left rail + main table */}
        <View style={[styles.body, !isDesktop && { flexDirection: "column", alignItems: "stretch" }]}>
          {/* LEFT RAIL — view selector + brand filter */}
          <View style={[styles.rail, isDesktop ? { width: 240 } : { width: "100%" }]}>
            <View style={styles.railBlock}>
              <Text style={styles.sectionLabel}>VIEW</Text>
              <View style={{ marginTop: 6 }}>
                {VIEW_ORDER.map((v) => {
                  const meta = VIEW_META[v];
                  const active = view === v;
                  const badge = v === "today" && blockedCount > 0 ? blockedCount : null;
                  return (
                    <Pressable
                      key={v}
                      testID={`view-${v}`}
                      onPress={() => { setView(v); setStage(""); }}
                      style={[styles.railItem, active && styles.railItemActive]}
                    >
                      <Feather name={meta.icon} size={14} color={active ? ds.brass : colors.onSurfaceMuted} />
                      <Text style={[styles.railItemText, active && { color: colors.onSurface, fontWeight: "600" }]}>{meta.label}</Text>
                      {badge != null ? (
                        <View style={styles.railBadge}>
                          <Text style={styles.railBadgeText}>{badge}</Text>
                        </View>
                      ) : null}
                    </Pressable>
                  );
                })}
              </View>
            </View>

            <View style={styles.railBlock}>
              <Text style={styles.sectionLabel}>BRAND</Text>
              <View style={{ marginTop: 6 }}>
                <Pressable
                  onPress={() => setBrand("all")}
                  style={[styles.brandItem, brand === "all" && styles.brandItemActive]}
                >
                  <Text style={[styles.brandLabel, brand === "all" && { color: colors.brand, fontWeight: "700" }]}>ALL</Text>
                  <Text style={styles.brandCount}>{brandsTotal}</Text>
                </Pressable>
                {brands.map((b) => (
                  <Pressable
                    key={b.id}
                    onPress={() => setBrand(b.id)}
                    style={[styles.brandItem, brand === b.id && styles.brandItemActive]}
                  >
                    <Text style={[styles.brandLabel, brand === b.id && { color: colors.brand, fontWeight: "700" }]} numberOfLines={1}>
                      {b.name}
                    </Text>
                    <Text style={styles.brandCount}>{b.count}</Text>
                  </Pressable>
                ))}
              </View>
            </View>

            <View style={styles.railBlock}>
              <Text style={styles.sectionLabel}>STAGE</Text>
              <View style={{ marginTop: 6 }}>
                <Pressable
                  onPress={() => setStage("")}
                  style={[styles.brandItem, stage === "" && styles.brandItemActive]}
                >
                  <Text style={[styles.brandLabel, stage === "" && { color: colors.brand, fontWeight: "700" }]}>All stages</Text>
                  <Text style={styles.brandCount}>{activeStageCount}</Text>
                </Pressable>
                {stages.map((s) => (
                  <Pressable
                    key={s.key}
                    onPress={() => setStage(s.key)}
                    style={[styles.brandItem, stage === s.key && styles.brandItemActive]}
                  >
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flex: 1 }}>
                      <View style={[styles.stageDot, { backgroundColor: STAGE_TONE[s.key]?.fg || s.tone.fg }]} />
                      <Text style={[styles.brandLabel, stage === s.key && { color: colors.brand, fontWeight: "700" }]} numberOfLines={1}>
                        {s.label}
                      </Text>
                    </View>
                    <Text style={styles.brandCount}>{s.count}</Text>
                  </Pressable>
                ))}
              </View>
            </View>
          </View>

          {/* MAIN — each tab is an operational workspace, not one table with a renamed filter. */}
          <View style={{ flex: 1, minWidth: 0, gap: spacing.lg }}>
            {view === "today" ? (
              <TodayWorkspace
                loading={loading}
                rows={items}
                blockedRows={blockedRows}
                slaDays={slaDays}
                onMove={setRowMoveTarget}
                onTransfer={setTransferItem}
                onHistory={setHistoryItemId}
              />
            ) : view === "stock" ? (
              <StockWorkspace
                loading={loading}
                rows={items}
                shortages={shortages}
                stages={stages}
                isDesktop={isDesktop}
                selected={selected}
                setSelected={setSelected}
                onMove={setRowMoveTarget}
                onTransfer={setTransferItem}
                onHistory={setHistoryItemId}
                onOpenPo={(poId) => router.push(`/(admin)/purchase-orders/${poId}` as any)}
              />
            ) : view === "customers" ? (
              <CustomerNavigator
                loading={loading}
                customers={customers}
                rows={items}
                onOpen={(customerId) => router.push(`/(admin)/customers/${customerId}` as any)}
              />
            ) : (
              <DispatchWorkspace
                loading={loading}
                rows={items}
                onHistory={setHistoryItemId}
                onOpenPo={(poId) => router.push(`/(admin)/purchase-orders/${poId}` as any)}
              />
            )}
          </View>
        </View>
      </ScrollView>

      {/* MODALS */}
      <MoveMenu
        visible={showMoveMenu}
        stages={stages}
        onClose={() => setShowMoveMenu(false)}
        onPick={(s) => bulkMove(s)}
        title={selected.size > 0 ? `Move ${selected.size} item${selected.size === 1 ? "" : "s"}` : "Bulk move"}
      />
      <MoveStageSheet
        visible={!!rowMoveTarget}
        item={rowMoveTarget ? toMovable(rowMoveTarget) : null}
        onClose={() => setRowMoveTarget(null)}
        onMoved={async () => { await Promise.all([loadItems(), loadFacets()]); }}
      />
      <TransferSheet
        visible={!!transferItem}
        item={transferItem ? toMovable(transferItem) : null}
        onClose={() => setTransferItem(null)}
        onSuccess={async () => { await Promise.all([loadItems(), loadFacets(), loadShortages()]); }}
      />
      <HistorySheet
        visible={!!historyItemId}
        itemId={historyItemId}
        onClose={() => setHistoryItemId(null)}
      />
      <ShortagesModal
        visible={showShortages}
        shortages={shortages}
        onClose={() => setShowShortages(false)}
        onChanged={async () => { await Promise.all([loadShortages(), loadItems(), loadFacets()]); }}
      />
      <SettingsModal
        visible={showSettings}
        currentSla={slaDays}
        onClose={() => setShowSettings(false)}
        onSaved={async (v) => {
          setSlaDays(v);
          setShowSettings(false);
          await loadItems();
        }}
      />
    </SafeAreaView>
  );
}

// -----------------------------------------------------------------------------
// Operational workspaces — intentionally distinct views over the accepted
// tracker contracts. The Today page prioritises actions; Stock is inventory;
// Customers is navigation; Dispatch is the delivery history.
// -----------------------------------------------------------------------------
function isToday(iso?: string | null) {
  if (!iso) return false;
  const date = new Date(iso); const now = new Date();
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
}

function OpsMetric({ label, value, icon, tone = "neutral" }: { label: string; value: number; icon: keyof typeof Feather.glyphMap; tone?: "neutral" | "warn" | "risk" | "ok" }) {
  const color = tone === "risk" ? colors.error : tone === "warn" ? ds.warn : tone === "ok" ? ds.ok : colors.onSurface;
  return (
    <View style={styles.opsMetric}>
      <Feather name={icon} size={14} color={color} />
      <Text style={[styles.opsMetricValue, { color }]}>{value}</Text>
      <Text style={styles.opsMetricLabel}>{label}</Text>
    </View>
  );
}

function TodayWorkspace({ loading, rows, blockedRows, slaDays, onMove, onTransfer, onHistory }: {
  loading: boolean; rows: Item[]; blockedRows: Item[]; slaDays: number;
  onMove: (item: Item) => void; onTransfer: (item: Item) => void; onHistory: (id: string) => void;
}) {
  const arrivals = rows.filter((r) => r.stage === "delivered" && isToday(r.last_moved_at));
  const dispatches = rows.filter((r) => ["dispatched", "in_transit"].includes(r.stage) && isToday(r.last_moved_at));
  const delayedSuppliers = Array.from(new Set(blockedRows.map((r) => r.supplier_name).filter(Boolean)));
  const urgent = [...blockedRows, ...rows.filter((r) => r.stage === "company_billing" || r.stage === "in_box")]
    .filter((row, index, list) => list.findIndex((candidate) => candidate.item_id === row.item_id) === index)
    .slice(0, 6);
  if (loading) return <View style={styles.loadingCard}><ActivityIndicator /><Text style={type.caption}>Preparing today’s operations…</Text></View>;
  return (
    <View style={{ gap: spacing.lg }}>
      <View>
        <Text style={styles.overline}>TODAY’S CONTROL TOWER</Text>
        <Text style={type.bodyMuted}>Arrivals, dispatches and the actions preventing customer delivery.</Text>
      </View>
      <View style={styles.opsMetrics}>
        <OpsMetric label="Today’s arrivals" value={arrivals.length} icon="package" tone="ok" />
        <OpsMetric label="Today’s dispatches" value={dispatches.length} icon="truck" tone="neutral" />
        <OpsMetric label="Delayed suppliers" value={delayedSuppliers.length} icon="clock" tone={delayedSuppliers.length ? "warn" : "ok"} />
        <OpsMetric label="Blocked orders" value={blockedRows.length} icon="alert-triangle" tone={blockedRows.length ? "risk" : "ok"} />
      </View>
      <View style={styles.workspaceCard}>
        <Text style={styles.workspaceTitle}>High-priority actions</Text>
        {urgent.length === 0 ? <Text style={type.bodyMuted}>No operational blockers require action today.</Text> : urgent.map((row) => (
          <View key={row.item_id} style={styles.actionRow}>
            <ProductImage source={row.image} style={styles.actionThumb} fallbackLabel={row.sku} disableSkeleton borderRadius={8} />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={styles.actionTitle} numberOfLines={1}>{row.name}</Text>
              <Text style={type.caption} numberOfLines={1}>{row.customer_name} · {row.supplier_name || "Supplier not assigned"} · {row.age_days}d in flow</Text>
            </View>
            <Pressable testID={`today-move-${row.item_id}`} onPress={() => onMove(row)} style={styles.workspaceAction}><Text style={styles.workspaceActionText}>Move</Text></Pressable>
          </View>
        ))}
      </View>
      {blockedRows.length > 0 ? (
        <View style={styles.blockedBox}>
          <View style={styles.blockedHeader}><Feather name="alert-triangle" size={14} color={colors.error} /><Text style={styles.blockedTitle}>BLOCKED ORDERS · past {slaDays}d SLA</Text></View>
          {blockedRows.slice(0, 8).map((row) => <BlockedCard key={row.item_id} row={row} onOpenMove={() => onMove(row)} onTransfer={() => onTransfer(row)} onHistory={() => onHistory(row.item_id)} />)}
        </View>
      ) : null}
    </View>
  );
}

function StockWorkspace({ loading, rows, shortages, stages, isDesktop, selected, setSelected, onMove, onTransfer, onHistory, onOpenPo }: {
  loading: boolean; rows: Item[]; shortages: Shortage[]; stages: StageMeta[]; isDesktop: boolean; selected: Set<string>;
  setSelected: Dispatch<SetStateAction<Set<string>>>; onMove: (item: Item) => void; onTransfer: (item: Item) => void; onHistory: (id: string) => void; onOpenPo: (id: string) => void;
}) {
  const pending = rows.filter((r) => ["order_in_company", "company_billing", "in_box"].includes(r.stage));
  const receiving = rows.filter((r) => ["company_billing", "in_box"].includes(r.stage));
  const ready = rows.filter((r) => ["dispatched", "in_transit"].includes(r.stage));
  if (loading) return <View style={styles.loadingCard}><ActivityIndicator /><Text style={type.caption}>Loading inventory movement…</Text></View>;
  return (
    <View style={{ gap: spacing.lg }}>
      <View><Text style={styles.overline}>STOCK CONTROL</Text><Text style={type.bodyMuted}>Receiving, pending receipts and stock ready for customer dispatch.</Text></View>
      <View style={styles.opsMetrics}>
        <OpsMetric label="Inventory movement" value={rows.length} icon="repeat" />
        <OpsMetric label="Pending receipts" value={pending.length} icon="clock" tone={pending.length ? "warn" : "ok"} />
        <OpsMetric label="Receiving" value={receiving.length} icon="inbox" />
        <OpsMetric label="Ready for dispatch" value={ready.length} icon="truck" tone="ok" />
        <OpsMetric label="Stock shortages" value={shortages.length} icon="alert-triangle" tone={shortages.length ? "risk" : "ok"} />
      </View>
      {shortages.length > 0 ? <View style={styles.shortageBanner}><Feather name="alert-triangle" size={15} color={colors.error} /><Text style={{ color: colors.error, fontWeight: "700" }}>{shortages.length} shortage{shortages.length === 1 ? "" : "s"} awaiting reorder</Text></View> : null}
      <TrackerRows rows={rows} isDesktop={isDesktop} selected={selected} setSelected={setSelected} onMove={onMove} onTransfer={onTransfer} onHistory={onHistory} onOpenPo={onOpenPo} />
    </View>
  );
}

function CustomerNavigator({ loading, customers, rows, onOpen }: { loading: boolean; customers: CustomerFacet[]; rows: Item[]; onOpen: (id: string) => void }) {
  const rowCount = useMemo(() => new Map(rows.map((row) => [row.customer_id, (rows.filter((candidate) => candidate.customer_id === row.customer_id)).length])), [rows]);
  if (loading) return <View style={styles.loadingCard}><ActivityIndicator /><Text style={type.caption}>Loading customer workspaces…</Text></View>;
  return (
    <View style={{ gap: spacing.lg }}>
      <View><Text style={styles.overline}>CUSTOMER WORKSPACES</Text><Text style={type.bodyMuted}>Select a customer to open their live purchases, shortages, payments and timeline.</Text></View>
      <View style={styles.workspaceCard}>
        {customers.length === 0 ? <Text style={type.bodyMuted}>No customer purchase workspaces yet.</Text> : customers.map((customer, index) => (
          <Pressable key={customer.id} testID={`customer-workspace-${customer.id}`} onPress={() => onOpen(customer.id)} style={({ pressed }) => [styles.customerNavRow, index > 0 && styles.customerNavDivider, pressed && { backgroundColor: colors.surfaceTertiary }]}>
            <View style={styles.customerAvatar}><Text style={styles.customerAvatarText}>{customer.name.slice(0, 1).toUpperCase()}</Text></View>
            <View style={{ flex: 1, minWidth: 0 }}><Text style={styles.actionTitle} numberOfLines={1}>{customer.name}</Text><Text style={type.caption}>{customer.open} open · {customer.count} tracked · {rowCount.get(customer.id) || 0} in current view</Text></View>
            <View style={[styles.openPill, customer.open > 0 && { backgroundColor: ds.brassTint }]}><Text style={styles.openPillText}>{customer.open} open</Text></View>
            <Feather name="chevron-right" size={16} color={colors.onSurfaceMuted} />
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function DispatchWorkspace({ loading, rows, onHistory, onOpenPo }: { loading: boolean; rows: Item[]; onHistory: (id: string) => void; onOpenPo: (id: string) => void }) {
  const dispatched = rows.filter((r) => r.stage === "dispatched");
  const transit = rows.filter((r) => r.stage === "in_transit");
  const delivered = rows.filter((r) => r.stage === "delivered");
  if (loading) return <View style={styles.loadingCard}><ActivityIndicator /><Text style={type.caption}>Loading dispatch history…</Text></View>;
  return (
    <View style={{ gap: spacing.lg }}>
      <View><Text style={styles.overline}>DISPATCH & DELIVERY</Text><Text style={type.bodyMuted}>Customer-bound dispatch history and live delivery stages.</Text></View>
      <View style={styles.opsMetrics}>
        <OpsMetric label="Dispatched" value={dispatched.length} icon="truck" />
        <OpsMetric label="In transit" value={transit.length} icon="navigation" tone="warn" />
        <OpsMetric label="Delivered" value={delivered.length} icon="check-circle" tone="ok" />
        <OpsMetric label="Returned" value={0} icon="corner-up-left" />
      </View>
      <View style={styles.workspaceCard}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm }}><Text style={styles.workspaceTitle}>Dispatch history</Text><Text style={type.caption}>Carrier status uses the linked supplier until a carrier is recorded.</Text></View>
        {rows.length === 0 ? <Text style={type.bodyMuted}>No dispatched or delivered items recorded.</Text> : rows.map((row, index) => (
          <Pressable key={row.item_id} onPress={() => onOpenPo(row.po_id)} style={({ pressed }) => [styles.dispatchRow, index > 0 && styles.customerNavDivider, pressed && { backgroundColor: colors.surfaceTertiary }]}>
            <ProductImage source={row.image} style={styles.actionThumb} fallbackLabel={row.sku} disableSkeleton borderRadius={8} />
            <View style={{ flex: 1, minWidth: 0 }}><Text style={styles.actionTitle} numberOfLines={1}>{row.name}</Text><Text style={type.caption} numberOfLines={1}>{row.customer_name} · {row.supplier_name || "Carrier pending"} · {fmtDate(row.last_moved_at)}</Text></View>
            <StageBadge stage={row.stage} tone={row.stage_tone} label={row.stage_label} />
            <Pressable testID={`dispatch-history-${row.item_id}`} onPress={() => onHistory(row.item_id)} style={styles.transferBtn}><Feather name="clock" size={12} color={colors.onSurface} /></Pressable>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

// The desktop ItemRow table assumes it gets most of the window width, but it
// actually renders inside the admin shell's own sidebar plus this page's rail
// (styles.rail, 240 wide) — so window-based isDesktop is the wrong signal for
// how many table columns fit. Measure this container's own width instead,
// mirroring BuilderShell's container-width responsive strategy.
const TABLE_FULL = 900;
const TABLE_STACK = 620;

function TrackerRows({ rows, isDesktop, selected, setSelected, onMove, onTransfer, onHistory, onOpenPo }: {
  rows: Item[]; isDesktop: boolean; selected: Set<string>; setSelected: Dispatch<SetStateAction<Set<string>>>;
  onMove: (item: Item) => void; onTransfer: (item: Item) => void; onHistory: (id: string) => void; onOpenPo: (id: string) => void;
}) {
  const [tableW, setTableW] = useState(Infinity);
  if (rows.length === 0) return <View style={styles.workspaceCard}><Text style={type.bodyMuted}>No inventory items match this stock view.</Text></View>;
  return (
    <View style={styles.tableCard} onLayout={(e) => setTableW(e.nativeEvent.layout.width)}>
      {rows.map((row) => (
        <ItemRow
          key={row.item_id} row={row} isDesktop={isDesktop} tableW={tableW}
          checked={selected.has(row.item_id)}
          onToggle={() => setSelected((current) => { const next = new Set(current); if (next.has(row.item_id)) next.delete(row.item_id); else next.add(row.item_id); return next; })}
          onOpenMove={() => onMove(row)} onTransfer={() => onTransfer(row)} onHistory={() => onHistory(row.item_id)} onOpenPo={() => onOpenPo(row.po_id)}
        />
      ))}
    </View>
  );
}

// -----------------------------------------------------------------------------
// Row + card components
// -----------------------------------------------------------------------------
function ItemRow(props: {
  row: Item; isDesktop: boolean; tableW: number; checked: boolean;
  onToggle: () => void; onOpenMove: () => void; onTransfer: () => void; onHistory: () => void; onOpenPo: () => void;
}) {
  const { row, isDesktop, tableW, checked, onToggle, onOpenMove, onTransfer, onHistory, onOpenPo } = props;
  const desktopTable = isDesktop && tableW >= TABLE_STACK;
  if (!desktopTable) {
    return (
      <View style={styles.mobileRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <BulkChk checked={checked} onToggle={onToggle} />
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{row.name}</Text>
            <Text style={type.caption} numberOfLines={1}>{row.sku} · {row.customer_name}</Text>
          </View>
          <StageBadge stage={row.stage} tone={row.stage_tone} label={row.stage_label} />
        </View>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 8, flexWrap: "wrap", gap: 6 }}>
          <Text style={type.caption} numberOfLines={1}>
            Qty {row.qty} · {row.brand_name} · {row.age_days}d{row.supplier_name ? ` · via ${row.supplier_name}` : ""}
          </Text>
          <View style={{ flexDirection: "row", gap: 6 }}>
            <Pressable onPress={onHistory} style={styles.transferBtn} hitSlop={6}><Feather name="clock" size={12} color={colors.onSurface} /></Pressable>
            <Pressable onPress={onOpenMove} style={styles.moveBtn} hitSlop={6}><Text style={styles.moveBtnText}>Move</Text></Pressable>
            <Pressable onPress={onTransfer} style={styles.transferBtn} hitSlop={6}><Feather name="repeat" size={12} color={colors.onSurface} /></Pressable>
          </View>
        </View>
      </View>
    );
  }
  const compact = tableW < TABLE_FULL;
  return (
    <View style={[styles.tr, row.blocked && { backgroundColor: ds.riskTint }]}>
      <View style={{ width: 30 }}>
        <BulkChk checked={checked} onToggle={onToggle} />
      </View>
      {/* Product */}
      <Pressable onPress={onOpenPo} style={{ flex: compact ? 3 : 2, flexDirection: "row", alignItems: "center", gap: 10, minWidth: 0 }}>
        <ProductImage
          source={row.image}
          style={styles.thumb}
          contentFit="cover"
          disableSkeleton
          fallbackLabel={row.sku}
          borderRadius={8}
        />
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{row.name}</Text>
          <Text style={styles.mono} numberOfLines={1}>{row.sku}{compact ? ` · ${row.brand_name}` : ""}</Text>
        </View>
      </Pressable>
      {/* Customer */}
      <View style={{ flex: compact ? 1.4 : 1.2, minWidth: 0 }}>
        <Text style={{ fontSize: 13, color: colors.onSurface }} numberOfLines={1}>{row.customer_name}</Text>
        <Text style={styles.mono} numberOfLines={1}>{row.po_number}{row.supplier_name ? ` · ${row.supplier_name}` : ""}</Text>
      </View>
      {/* Brand — folded into the SKU line below TABLE_FULL, where it's the least essential fixed column */}
      {!compact ? (
        <Text style={{ width: 96, fontSize: 13, color: colors.onSurface, textTransform: "uppercase", fontWeight: "600" }} numberOfLines={1}>
          {row.brand_name}
        </Text>
      ) : null}
      {/* Stage */}
      <View style={{ width: 130 }}>
        <StageBadge stage={row.stage} tone={row.stage_tone} label={row.stage_label} />
      </View>
      {/* Qty */}
      <Text style={{ width: 44, textAlign: "right", fontSize: 13, fontWeight: "600", color: colors.onSurface }}>
        {row.qty}
      </Text>
      {/* Last move — dropped below TABLE_FULL to give Product/Customer room */}
      {!compact ? (
        <View style={{ flex: 1.1, minWidth: 0 }}>
          <Text style={{ fontSize: 12, color: colors.onSurface }} numberOfLines={1}>{fmtDate(row.last_moved_at)}</Text>
          <Text style={type.caption} numberOfLines={1}>{row.last_moved_by_name || "—"}</Text>
        </View>
      ) : null}
      {/* Action */}
      <View style={{ width: 118, alignItems: "flex-end", flexDirection: "row", justifyContent: "flex-end", gap: 6 }}>
        <Pressable onPress={onHistory} testID={`row-history-${row.item_id}`} hitSlop={6} style={({ pressed }) => [styles.transferBtn, pressed && { opacity: 0.85 }]}>
          <Feather name="clock" size={12} color={colors.onSurface} />
        </Pressable>
        <Pressable onPress={onOpenMove} testID={`row-move-${row.item_id}`} style={({ pressed }) => [styles.moveBtn, pressed && { opacity: 0.85 }]}>
          <Text style={styles.moveBtnText}>Move</Text>
          <Feather name="chevron-down" size={11} color={colors.onSurfaceMuted} />
        </Pressable>
        <Pressable onPress={onTransfer} testID={`row-transfer-${row.item_id}`} hitSlop={6} style={({ pressed }) => [styles.transferBtn, pressed && { opacity: 0.85 }]}>
          <Feather name="repeat" size={12} color={colors.onSurface} />
        </Pressable>
      </View>
    </View>
  );
}

function BlockedCard({ row, onOpenMove, onTransfer, onHistory }: {
  row: Item; onOpenMove: () => void; onTransfer: () => void; onHistory: () => void;
}) {
  return (
    <View style={styles.blockedCard}>
      <ProductImage
        source={row.image}
        style={styles.blockedThumb}
        contentFit="cover"
        disableSkeleton
        fallbackLabel={row.sku}
        borderRadius={8}
      />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{row.name}</Text>
        <Text style={styles.mono} numberOfLines={1}>{row.sku} · {row.brand_name}{row.supplier_name ? ` · ${row.supplier_name}` : ""}</Text>
      </View>
      <View style={styles.orderInPill}>
        <Text style={{ color: ds.warn, fontWeight: "600", fontSize: 12 }}>{row.stage_label} · {row.qty} unit{row.qty === 1 ? "" : "s"}</Text>
      </View>
      <View style={styles.agePill}>
        <Feather name="alert-triangle" size={11} color={colors.error} />
        <Text style={{ color: colors.error, fontSize: 11, fontWeight: "700" }}>{row.age_days}d</Text>
      </View>
      <View style={{ flexDirection: "row", gap: 6 }}>
        <Pressable onPress={onHistory} style={styles.transferBtn}>
          <Feather name="clock" size={12} color={colors.onSurface} />
        </Pressable>
        <Pressable onPress={onOpenMove} style={styles.moveBtn}>
          <Text style={styles.moveBtnText}>Move</Text>
          <Feather name="chevron-down" size={11} color={colors.onSurfaceMuted} />
        </Pressable>
        <Pressable onPress={onTransfer} style={styles.transferBtn}>
          <Feather name="repeat" size={12} color={colors.onSurface} />
        </Pressable>
      </View>
    </View>
  );
}

function StageBadge({ stage, tone, label }: { stage: Stage; tone: { bg: string; fg: string }; label: string }) {
  const t = STAGE_TONE[stage] || tone;
  return (
    <View style={[styles.stageBadge, { backgroundColor: t.bg }]}>
      <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: t.fg, marginRight: 5 }} />
      <Text style={{ color: t.fg, fontSize: 11, fontWeight: "600" }} numberOfLines={1}>{label}</Text>
    </View>
  );
}

function BulkChk({ checked, onToggle }: { checked: boolean; onToggle: () => void }) {
  return (
    <Pressable onPress={onToggle} hitSlop={8} style={[styles.chk, checked && styles.chkOn]}>
      {checked ? <Feather name="check" size={11} color="#fff" /> : null}
    </Pressable>
  );
}

// -----------------------------------------------------------------------------
// Modals
// -----------------------------------------------------------------------------
function MoveMenu({ visible, stages, onClose, onPick, title, currentStage }: {
  visible: boolean; stages: StageMeta[]; onClose: () => void;
  onPick: (s: Stage) => void; title: string; currentStage?: Stage;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.modalBackdrop} onPress={onClose}>
        <View style={styles.menuCard}>
          <Text style={{ fontSize: 14, fontWeight: "700", marginBottom: 4 }}>{title}</Text>
          <Text style={type.caption}>Move to any stage</Text>
          <View style={{ marginTop: 10, gap: 4 }}>
            {stages.map((s) => (
              <Pressable
                key={s.key}
                testID={`move-to-${s.key}`}
                onPress={() => onPick(s.key)}
                disabled={s.key === currentStage}
                style={({ pressed }) => [
                  styles.menuItem, pressed && { backgroundColor: colors.surfaceTertiary },
                  s.key === currentStage && { opacity: 0.4 },
                ]}
              >
                <View style={[styles.stageDot, { backgroundColor: STAGE_TONE[s.key]?.fg || s.tone.fg }]} />
                <Text style={{ fontSize: 13, color: colors.onSurface, flex: 1 }}>{s.label}</Text>
                {s.key === currentStage ? <Text style={{ fontSize: 11, color: colors.onSurfaceMuted }}>current</Text> : null}
              </Pressable>
            ))}
          </View>
          <View style={{ borderTopWidth: 1, borderColor: colors.border, marginTop: 8, paddingTop: 8 }}>
            <Pressable
              testID="move-to-last-stage"
              onPress={() => onPick("delivered")}
              style={({ pressed }) => [styles.menuItem, pressed && { backgroundColor: colors.surfaceTertiary }]}
            >
              <Feather name="fast-forward" size={12} color={colors.brand} />
              <Text style={{ fontSize: 13, color: colors.brand, fontWeight: "700" }}>Move to Last Stage (Delivered)</Text>
            </Pressable>
          </View>
        </View>
      </Pressable>
    </Modal>
  );
}

function SettingsModal({ visible, currentSla, onClose, onSaved }: {
  visible: boolean; currentSla: number; onClose: () => void; onSaved: (v: number) => void;
}) {
  const [val, setVal] = useState(String(currentSla));
  const [busy, setBusy] = useState(false);
  useEffect(() => { setVal(String(currentSla)); }, [currentSla, visible]);
  const save = async () => {
    const n = Number(val);
    if (!n || n < 1 || n > 365) { toast.error("SLA must be between 1 and 365"); return; }
    setBusy(true);
    try {
      await api.post("/purchases/settings", { sla_days: n });
      toast.success(`SLA set to ${n} day${n === 1 ? "" : "s"}`);
      onSaved(n);
    } catch (e: any) { toast.error(e?.detail || "Save failed"); }
    finally { setBusy(false); }
  };
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.modalBackdrop} onPress={onClose}>
        <View style={styles.settingsCard}>
          <Text style={type.titleMd}>Purchases Settings</Text>
          <Text style={[type.caption, { marginTop: 2 }]}>Items in early stages beyond the SLA are flagged as blocked.</Text>
          <View style={{ marginTop: 12 }}>
            <Text style={styles.fieldLabel}>BLOCKED SLA (days)</Text>
            <TextInput
              testID="sla-input"
              value={val} onChangeText={(v) => setVal(v.replace(/[^0-9]/g, ""))}
              keyboardType="numeric"
              style={[styles.input, { fontSize: 16, fontWeight: "700" }]}
            />
            <Text style={{ fontSize: 11, color: colors.onSurfaceMuted, marginTop: 4 }}>
              Any item stuck in Order in Company / Company Billing / In Box for longer than this is shown in the Today view.
            </Text>
          </View>
          <View style={{ flexDirection: "row", gap: 8, marginTop: 14 }}>
            <Pressable onPress={onClose} style={[styles.cancelBtn, { flex: 1 }]}>
              <Text style={{ color: colors.onSurface, fontWeight: "600" }}>Cancel</Text>
            </Pressable>
            <Pressable testID="sla-save" onPress={save} disabled={busy} style={[styles.transferPrimary, { flex: 1 }]}>
              {busy ? <ActivityIndicator size="small" color={colors.onBrand} /> : <Text style={{ color: colors.onBrand, fontWeight: "700" }}>Save</Text>}
            </Pressable>
          </View>
        </View>
      </Pressable>
    </Modal>
  );
}

function ShortagesModal({ visible, shortages, onClose, onChanged }: {
  visible: boolean; shortages: Shortage[]; onClose: () => void; onChanged: () => void | Promise<void>;
}) {
  const router = useRouter();
  const [busyId, setBusyId] = useState<string | null>(null);

  const createPo = async (s: Shortage) => {
    setBusyId(s.id);
    try {
      const r = await api.post<{ po_number: string }>(`/purchases/shortages/${s.id}/create-po`);
      toast.success(`Reorder PO ${r.po_number} created for ${s.customer_name}`);
      await onChanged();
    } catch (e: any) { toast.error(e?.detail || "Could not create PO"); }
    finally { setBusyId(null); }
  };
  const dismiss = async (s: Shortage) => {
    setBusyId(s.id);
    try {
      await api.post(`/purchases/shortages/${s.id}/dismiss`, {});
      toast.success("Dismissed");
      await onChanged();
    } catch (e: any) { toast.error(e?.detail || "Could not dismiss"); }
    finally { setBusyId(null); }
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.modalBackdrop} onPress={onClose}>
        <Pressable style={[styles.settingsCard, { width: 520, maxWidth: "100%" }]} onPress={() => {}}>
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
            <Text style={type.titleMd}>Awaiting Reorder</Text>
            <Pressable onPress={onClose} hitSlop={8}><Feather name="x" size={16} color={colors.onSurfaceMuted} /></Pressable>
          </View>
          <Text style={[type.caption, { marginTop: 2, marginBottom: 10 }]}>Opened automatically when a transfer leaves a customer’s original order short.</Text>
          <ScrollView style={{ maxHeight: 420 }}>
            {shortages.length === 0 ? (
              <Text style={type.caption}>Nothing outstanding — nice.</Text>
            ) : shortages.map((s) => (
              <View key={s.id} style={styles.shortageRow}>
                <Pressable
                  style={{ flex: 1, minWidth: 0 }}
                  onPress={() => { onClose(); router.push(`/(admin)/customers/${s.customer_id}` as any); }}
                >
                  <Text style={{ fontSize: 13, fontWeight: "700", color: colors.onSurface }} numberOfLines={1}>{s.customer_name}</Text>
                  <Text style={{ fontSize: 12, color: colors.onSurfaceMuted }} numberOfLines={2}>{s.reason}</Text>
                </Pressable>
                <View style={{ flexDirection: "row", gap: 6 }}>
                  <Pressable
                    testID={`shortage-po-${s.id}`}
                    disabled={busyId === s.id}
                    onPress={() => createPo(s)}
                    style={[styles.transferPrimary, { paddingHorizontal: 10, opacity: busyId === s.id ? 0.6 : 1 }]}
                  >
                    <Text style={{ color: colors.onBrand, fontWeight: "700", fontSize: 12 }}>Create PO</Text>
                  </Pressable>
                  <Pressable
                    testID={`shortage-dismiss-${s.id}`}
                    disabled={busyId === s.id}
                    onPress={() => dismiss(s)}
                    style={[styles.cancelBtn, { paddingHorizontal: 10 }]}
                  >
                    <Text style={{ color: colors.onSurface, fontWeight: "600", fontSize: 12 }}>Dismiss</Text>
                  </Pressable>
                </View>
              </View>
            ))}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

// -----------------------------------------------------------------------------
// Styles
// -----------------------------------------------------------------------------
const styles = StyleSheet.create({
  scroll: { padding: spacing.xl, gap: spacing.lg, paddingBottom: spacing.xxxl },
  overline: {
    fontSize: 10, fontWeight: "700", letterSpacing: 1.4, textTransform: "uppercase",
    color: colors.onSurfaceMuted, marginBottom: 4,
  },
  pageTitle: { fontFamily: dsFont.display, fontSize: 30, lineHeight: 38, color: colors.onSurface, letterSpacing: -0.3 },

  // Top action bar
  headerRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.md },
  topActions: { flexDirection: "row", alignItems: "center", gap: 8, flexShrink: 0 },
  search: {
    flexDirection: "row", alignItems: "center", gap: 8,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: 10, height: 36, backgroundColor: colors.surfaceSecondary,
    minWidth: 240,
  },
  searchInput: {
    flex: 1, fontSize: 13, color: colors.onSurface, paddingVertical: 0,
    ...(Platform.OS === "web" ? { outlineStyle: "none" } as any : {}),
  },
  iconAction: {
    flexDirection: "row", alignItems: "center", gap: 6,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: 12, height: 36, backgroundColor: colors.surfaceSecondary,
  },

  // Body split
  body: { flexDirection: "row", gap: spacing.lg, alignItems: "flex-start" },

  // Rail
  rail: { gap: spacing.md },
  railBlock: {
    padding: spacing.md, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
  },
  sectionLabel: {
    fontSize: 10, fontWeight: "700", color: colors.onSurfaceMuted,
    letterSpacing: 1.2, textTransform: "uppercase",
  },
  railItem: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: 10, paddingVertical: 8, borderRadius: radius.sm,
    borderLeftWidth: 3, borderLeftColor: "transparent",
  },
  railItemActive: { backgroundColor: ds.sunken, borderLeftColor: ds.brass },
  railItemText: { fontSize: 13, color: colors.onSurface, flex: 1 },
  railBadge: {
    backgroundColor: colors.error, borderRadius: 999, paddingHorizontal: 6, minWidth: 20,
    height: 18, alignItems: "center", justifyContent: "center",
  },
  railBadgeText: { color: "#fff", fontSize: 11, fontWeight: "700" },

  brandItem: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.sm, gap: 8,
  },
  brandItemActive: { backgroundColor: ds.sunken },
  brandLabel: { fontSize: 13, color: colors.onSurface, flex: 1 },
  brandCount: { fontSize: 12, color: colors.onSurfaceMuted, fontWeight: "600" },
  stageDot: { width: 8, height: 8, borderRadius: 4 },

  // Blocked box
  blockedBox: {
    padding: spacing.md, borderRadius: radius.md,
    backgroundColor: ds.riskTint, borderWidth: 1, borderColor: "rgba(174,74,61,0.22)",
  },
  blockedHeader: { flexDirection: "row", alignItems: "center", gap: 6 },
  blockedTitle: {
    fontSize: 11, fontWeight: "800", color: colors.error, letterSpacing: 0.8, textTransform: "uppercase",
  },
  blockedCard: {
    flexDirection: "row", alignItems: "center", gap: 10,
    padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, marginBottom: 6,
  },
  blockedThumb: {
    width: 40, height: 40, borderRadius: 8, backgroundColor: colors.surfaceTertiary,
    alignItems: "center", justifyContent: "center", overflow: "hidden",
  },
  orderInPill: {
    paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: ds.warnTint,
  },
  agePill: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: ds.riskTint,
  },

  // Table
  tableCard: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, overflow: "hidden",
  },
  tHead: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: spacing.md, paddingVertical: 10,
    backgroundColor: colors.surfaceSubtle, borderBottomWidth: 1, borderColor: colors.border,
  },
  th: {
    fontSize: 11, fontWeight: "700", color: colors.onSurfaceMuted,
    letterSpacing: 0.8, textTransform: "uppercase",
  },
  tr: {
    flexDirection: "row", alignItems: "center", gap: 8, minHeight: 72,
    paddingHorizontal: spacing.md, paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  mobileRow: {
    padding: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  thumb: {
    width: 44, height: 44, borderRadius: 8, backgroundColor: colors.surfaceTertiary,
    alignItems: "center", justifyContent: "center", overflow: "hidden",
  },
  mono: { fontSize: 11, color: colors.onSurfaceMuted, fontVariant: ["tabular-nums"] },

  stageBadge: {
    alignSelf: "flex-start", flexDirection: "row", alignItems: "center",
    paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999,
  },

  chk: {
    width: 18, height: 18, borderRadius: 4, borderWidth: 1.5, borderColor: colors.border,
    alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary,
  },
  chkOn: { backgroundColor: colors.brand, borderColor: colors.brand },

  moveBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 10, height: 30, borderRadius: 8,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
  },
  moveBtnText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  transferBtn: {
    width: 30, height: 30, borderRadius: 8, alignItems: "center", justifyContent: "center",
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
  },

  // Modals
  modalBackdrop: {
    flex: 1, backgroundColor: "rgba(15,17,21,0.35)",
    alignItems: "flex-end", justifyContent: "flex-start",
    paddingTop: 90, paddingRight: 24,
    ...(Platform.OS !== "web" ? { alignItems: "center", justifyContent: "center", padding: 20 } : {}),
  },
  menuCard: {
    width: 300, padding: spacing.md, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    ...shadow.strong,
  },
  menuItem: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: 10, paddingVertical: 8, borderRadius: 6,
  },

  transferBackdrop: {
    flex: 1, backgroundColor: "rgba(15,17,21,0.35)",
    alignItems: "flex-end", justifyContent: "center", paddingRight: 24,
    ...(Platform.OS !== "web" ? { alignItems: "center", justifyContent: "center", padding: 20 } : {}),
  },
  transferCard: {
    width: 380, maxHeight: "90%", padding: spacing.lg, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    ...shadow.strong,
  },
  transferProduct: {
    flexDirection: "row", gap: 10, alignItems: "center",
    padding: 10, borderRadius: 8, backgroundColor: colors.surfaceTertiary,
  },
  transferThumb: {
    width: 44, height: 44, borderRadius: 6, backgroundColor: colors.surface,
    alignItems: "center", justifyContent: "center", overflow: "hidden",
  },
  transferReadonly: {
    padding: 10, borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  transferPrimary: {
    height: 40, borderRadius: 8, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center",
  },
  transferFoot: {
    flexDirection: "row", gap: 6, alignItems: "center", marginTop: 12,
    backgroundColor: colors.surfaceTertiary, padding: 8, borderRadius: 8,
    borderWidth: 1, borderColor: colors.border,
  },
  custPick: {
    flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  custPickOn: { backgroundColor: ds.sunken },

  // Form primitives
  fieldLabel: {
    fontSize: 10, fontWeight: "700", color: colors.onSurfaceMuted,
    letterSpacing: 1, textTransform: "uppercase", marginBottom: 6,
  },
  input: {
    borderWidth: 1, borderColor: colors.border, borderRadius: 8,
    paddingHorizontal: 10, paddingVertical: 10, fontSize: 14,
    backgroundColor: colors.surfaceSecondary, color: colors.onSurface,
    ...(Platform.OS === "web" ? { outlineStyle: "none" } as any : {}),
  },
  cancelBtn: {
    height: 40, paddingHorizontal: 14, borderRadius: 8, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary,
  },

  settingsCard: {
    width: 340, padding: spacing.lg, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    ...shadow.strong,
  },
  shortageRow: {
    flexDirection: "row", alignItems: "center", gap: 10,
    paddingVertical: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border,
  },
  loadingCard: { minHeight: 180, alignItems: "center", justifyContent: "center", gap: 10, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md },
  opsMetrics: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  opsMetric: { minWidth: 132, flexGrow: 1, gap: 4, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md },
  opsMetricValue: { fontSize: 24, fontWeight: "700", fontVariant: ["tabular-nums"] },
  opsMetricLabel: { fontSize: 11, color: colors.onSurfaceMuted, fontWeight: "600" },
  workspaceCard: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md },
  workspaceTitle: { fontSize: 14, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  actionRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 10, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  actionThumb: { width: 40, height: 40 },
  actionTitle: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  workspaceAction: { height: 32, paddingHorizontal: 10, borderRadius: radius.sm, justifyContent: "center", backgroundColor: colors.brand },
  workspaceActionText: { color: colors.onBrand, fontSize: 12, fontWeight: "700" },
  shortageBanner: { flexDirection: "row", alignItems: "center", gap: 8, padding: spacing.md, borderRadius: radius.md, backgroundColor: ds.riskTint, borderWidth: 1, borderColor: "rgba(174,74,61,0.22)" },
  customerNavRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12, paddingHorizontal: 4 },
  customerNavDivider: { borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  customerAvatar: { width: 34, height: 34, borderRadius: 17, backgroundColor: ds.brassTint, alignItems: "center", justifyContent: "center" },
  customerAvatarText: { color: ds.brassDeep, fontWeight: "800", fontSize: 14 },
  openPill: { minWidth: 46, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, alignItems: "center", backgroundColor: colors.surfaceTertiary },
  openPillText: { color: colors.onSurfaceSecondary, fontSize: 10.5, fontWeight: "700" },
  dispatchRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 10, paddingHorizontal: 4 },
});
