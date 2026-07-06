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
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, KeyboardAvoidingView, Linking, Modal, Platform, Pressable,
  ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api, ApiError } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { colors, radius, shadow, spacing, type } from "@/src/theme/tokens";
import { color as ds, font as dsFont } from "@/src/design/tokens";

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
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;
  const isTablet = width >= 768;

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

  // -----------------------------------
  // Data loaders
  // -----------------------------------
  const loadFacets = useCallback(async () => {
    try {
      const [b, s] = await Promise.all([
        api.get<{ all: number; brands: BrandFacet[] }>("/purchases/brands"),
        api.get<StageMeta[]>("/purchases/stages"),
      ]);
      setBrands(b.brands); setBrandsTotal(b.all);
      setStages(s);
    } catch (e) { /* silent */ }
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
  useEffect(() => {
    const t = setTimeout(loadItems, 220);
    return () => clearTimeout(t);
  }, [loadItems]);

  // -----------------------------------
  // Mutations
  // -----------------------------------
  const moveItem = useCallback(async (itemId: string, toStage: Stage, note?: string) => {
    try {
      await api.post(`/purchases/items/${itemId}/move`, { stage: toStage, note });
      toast.success(`Moved to ${VIEW_META.today.label ? "" : ""}${stages.find((s) => s.key === toStage)?.label || toStage}`);
      await Promise.all([loadItems(), loadFacets()]);
    } catch (e: any) { toast.error(e?.detail || "Move failed"); }
  }, [loadItems, loadFacets, stages]);

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
    const url = api.authenticatedUrl(`/purchases/export.xlsx?${qs.toString()}`);
    try {
      if (Platform.OS === "web") {
        // @ts-ignore — web only
        window.open(url, "_blank");
      } else {
        await Linking.openURL(url);
      }
      toast.success("Excel export ready");
    } catch (e: any) {
      toast.error("Export failed");
    }
  }, [view, brand, q, stage]);

  // -----------------------------------
  // Derived
  // -----------------------------------
  const blockedRows = useMemo(() => items.filter((i) => i.blocked), [items]);
  const regularRows = useMemo(() => (view === "today" ? items.filter((i) => !i.blocked) : items), [items, view]);
  const blockedByCustomer = useMemo(() => {
    const map = new Map<string, Item[]>();
    blockedRows.forEach((r) => {
      const k = r.customer_name || "—";
      const list = map.get(k) || []; list.push(r); map.set(k, list);
    });
    return Array.from(map.entries());
  }, [blockedRows]);

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
        <View style={[styles.body, !isDesktop && { flexDirection: "column" }]}>
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

          {/* MAIN */}
          <View style={{ flex: 1, minWidth: 0, gap: spacing.lg }}>
            {/* Today view: BLOCKED section */}
            {view === "today" && blockedRows.length > 0 ? (
              <View style={styles.blockedBox}>
                <View style={styles.blockedHeader}>
                  <Feather name="alert-triangle" size={14} color={colors.error} />
                  <Text style={styles.blockedTitle}>BLOCKED — cannot dispatch today</Text>
                  <View style={{ marginLeft: "auto" }}>
                    <Text style={{ color: colors.error, fontSize: 12, fontWeight: "600" }}>
                      {blockedRows.length} item{blockedRows.length === 1 ? "" : "s"} · aged &gt; {slaDays}d
                    </Text>
                  </View>
                </View>
                {blockedByCustomer.map(([customerName, rows]) => (
                  <View key={customerName} style={{ marginTop: 12 }}>
                    <Text style={{ fontSize: 12, fontWeight: "700", color: colors.onSurfaceSecondary, marginBottom: 6 }}>
                      {customerName}
                    </Text>
                    {rows.map((r) => (
                      <BlockedCard
                        key={r.item_id} row={r}
                        onOpenMove={() => setRowMoveTarget(r)}
                        onTransfer={() => setTransferItem(r)}
                      />
                    ))}
                  </View>
                ))}
              </View>
            ) : null}

            {/* Header for main table */}
            {view === "today" ? (
              <View>
                <Text style={styles.overline}>Today</Text>
                {regularRows.length === 0 && blockedRows.length > 0 ? (
                  <Text style={[type.caption, { marginTop: 4 }]}>
                    No units packed and ready — check blocked items above.
                  </Text>
                ) : null}
              </View>
            ) : null}

            {/* Table */}
            <View style={styles.tableCard}>
              {loading ? (
                <View style={{ padding: spacing.xxl, alignItems: "center" }}><ActivityIndicator /></View>
              ) : regularRows.length === 0 ? (
                <View style={{ padding: spacing.xxl, alignItems: "center", gap: 8 }}>
                  <Feather name="inbox" size={22} color={colors.onSurfaceMuted} />
                  <Text style={type.bodyMuted}>No items match this view.</Text>
                </View>
              ) : (
                <>
                  {/* Table header */}
                  {isTablet ? (
                    <View style={styles.tHead}>
                      <View style={{ width: 30 }}>
                        <BulkChk
                          checked={regularRows.length > 0 && regularRows.every((r) => selected.has(r.item_id))}
                          onToggle={() => {
                            setSelected((prev) => {
                              const next = new Set(prev);
                              const allSelected = regularRows.every((r) => next.has(r.item_id));
                              if (allSelected) regularRows.forEach((r) => next.delete(r.item_id));
                              else regularRows.forEach((r) => next.add(r.item_id));
                              return next;
                            });
                          }}
                        />
                      </View>
                      <Text style={[styles.th, { flex: 2 }]}>PRODUCT / SKU</Text>
                      <Text style={[styles.th, { flex: 1.2 }]}>CUSTOMER</Text>
                      <Text style={[styles.th, { width: 96 }]}>BRAND</Text>
                      <Text style={[styles.th, { width: 130 }]}>STAGE</Text>
                      <Text style={[styles.th, { width: 44, textAlign: "right" }]}>QTY</Text>
                      <Text style={[styles.th, { flex: 1.1 }]}>LAST MOVE / BY</Text>
                      <Text style={[styles.th, { width: 90, textAlign: "right" }]}>ACTION</Text>
                    </View>
                  ) : null}

                  {regularRows.map((r) => (
                    <ItemRow
                      key={r.item_id}
                      row={r}
                      isTablet={isTablet}
                      checked={selected.has(r.item_id)}
                      onToggle={() => {
                        setSelected((prev) => {
                          const next = new Set(prev);
                          if (next.has(r.item_id)) next.delete(r.item_id); else next.add(r.item_id);
                          return next;
                        });
                      }}
                      onOpenMove={() => setRowMoveTarget(r)}
                      onTransfer={() => setTransferItem(r)}
                      onOpenPo={() => router.push(`/(admin)/purchase-orders/${r.po_id}` as any)}
                    />
                  ))}
                </>
              )}
            </View>
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
      <MoveMenu
        visible={!!rowMoveTarget}
        stages={stages}
        onClose={() => setRowMoveTarget(null)}
        onPick={async (s) => {
          if (rowMoveTarget) await moveItem(rowMoveTarget.item_id, s);
          setRowMoveTarget(null);
        }}
        title={rowMoveTarget ? `Move ${rowMoveTarget.name}` : ""}
        currentStage={rowMoveTarget?.stage}
      />
      <TransferModal
        item={transferItem}
        onClose={() => setTransferItem(null)}
        onSuccess={async () => {
          setTransferItem(null);
          await Promise.all([loadItems(), loadFacets()]);
        }}
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
// Row + card components
// -----------------------------------------------------------------------------
function ItemRow(props: {
  row: Item; isTablet: boolean; checked: boolean;
  onToggle: () => void; onOpenMove: () => void; onTransfer: () => void; onOpenPo: () => void;
}) {
  const { row, isTablet, checked, onToggle, onOpenMove, onTransfer, onOpenPo } = props;
  if (!isTablet) {
    return (
      <View style={styles.mobileRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <BulkChk checked={checked} onToggle={onToggle} />
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{row.name}</Text>
            <Text style={type.caption}>{row.sku} · {row.customer_name}</Text>
          </View>
          <StageBadge stage={row.stage} tone={row.stage_tone} label={row.stage_label} />
        </View>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
          <Text style={type.caption}>Qty {row.qty} · {row.brand_name} · {row.age_days}d</Text>
          <View style={{ flexDirection: "row", gap: 6 }}>
            <Pressable onPress={onOpenMove} style={styles.moveBtn}><Text style={styles.moveBtnText}>Move</Text></Pressable>
            <Pressable onPress={onTransfer} style={styles.transferBtn}><Feather name="repeat" size={12} color={colors.onSurface} /></Pressable>
          </View>
        </View>
      </View>
    );
  }
  return (
    <View style={[styles.tr, row.blocked && { backgroundColor: ds.riskTint }]}>
      <View style={{ width: 30 }}>
        <BulkChk checked={checked} onToggle={onToggle} />
      </View>
      {/* Product */}
      <Pressable onPress={onOpenPo} style={{ flex: 2, flexDirection: "row", alignItems: "center", gap: 10, minWidth: 0 }}>
        <View style={styles.thumb}>
          {row.image ? (
            // eslint-disable-next-line jsx-a11y/alt-text
            <View style={{ ...StyleSheet.absoluteFillObject, overflow: "hidden", borderRadius: 6 }}>
              {/* Use native <img> on web for base64/URL images; Expo Image on native would be better */}
              {Platform.OS === "web" ? (
                // @ts-ignore
                <img src={row.image} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : null}
            </View>
          ) : (
            <Feather name="image" size={14} color={colors.onSurfaceMuted} />
          )}
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{row.name}</Text>
          <Text style={styles.mono}>{row.sku}</Text>
        </View>
      </Pressable>
      {/* Customer */}
      <View style={{ flex: 1.2, minWidth: 0 }}>
        <Text style={{ fontSize: 13, color: colors.onSurface }} numberOfLines={1}>{row.customer_name}</Text>
        <Text style={styles.mono}>{row.po_number}</Text>
      </View>
      {/* Brand */}
      <Text style={{ width: 96, fontSize: 13, color: colors.onSurface, textTransform: "uppercase", fontWeight: "600" }} numberOfLines={1}>
        {row.brand_name}
      </Text>
      {/* Stage */}
      <View style={{ width: 130 }}>
        <StageBadge stage={row.stage} tone={row.stage_tone} label={row.stage_label} />
      </View>
      {/* Qty */}
      <Text style={{ width: 44, textAlign: "right", fontSize: 13, fontWeight: "600", color: colors.onSurface }}>
        {row.qty}
      </Text>
      {/* Last move */}
      <View style={{ flex: 1.1, minWidth: 0 }}>
        <Text style={{ fontSize: 12, color: colors.onSurface }} numberOfLines={1}>{fmtDate(row.last_moved_at)}</Text>
        <Text style={type.caption} numberOfLines={1}>{row.last_moved_by_name || "—"}</Text>
      </View>
      {/* Action */}
      <View style={{ width: 90, alignItems: "flex-end", flexDirection: "row", justifyContent: "flex-end", gap: 6 }}>
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

function BlockedCard({ row, onOpenMove, onTransfer }: { row: Item; onOpenMove: () => void; onTransfer: () => void }) {
  return (
    <View style={styles.blockedCard}>
      <View style={styles.blockedThumb}>
        {row.image && Platform.OS === "web" ? (
          // @ts-ignore
          <img src={row.image} style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: 8 }} />
        ) : <Feather name="image" size={16} color={colors.onSurfaceMuted} />}
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{row.name}</Text>
        <Text style={styles.mono}>{row.sku} · {row.brand_name}</Text>
      </View>
      <View style={styles.orderInPill}>
        <Text style={{ color: ds.warn, fontWeight: "600", fontSize: 12 }}>{row.stage_label} · {row.qty} unit{row.qty === 1 ? "" : "s"}</Text>
      </View>
      <View style={styles.agePill}>
        <Feather name="alert-triangle" size={11} color={colors.error} />
        <Text style={{ color: colors.error, fontSize: 11, fontWeight: "700" }}>{row.age_days}d</Text>
      </View>
      <View style={{ flexDirection: "row", gap: 6 }}>
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

type CustomerLite = { id: string; name: string; company?: string | null };

function TransferModal({ item, onClose, onSuccess }: {
  item: Item | null; onClose: () => void; onSuccess: () => void | Promise<void>;
}) {
  const [customers, setCustomers] = useState<CustomerLite[]>([]);
  const [pick, setPick] = useState<string>("");
  const [qty, setQty] = useState<string>("1");
  const [reason, setReason] = useState<string>("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!item) return;
    setPick(""); setQty(String(item.qty)); setReason("");
    api.get<CustomerLite[]>(`/customers`).then((list) => {
      setCustomers((list || []).filter((c) => c.id !== item.customer_id));
    }).catch(() => {});
  }, [item]);

  if (!item) return null;

  const submit = async () => {
    if (!pick) { toast.error("Pick a destination customer"); return; }
    const n = Number(qty || "0");
    if (!n || n <= 0) { toast.error("Enter a valid qty"); return; }
    if (n > item.qty) { toast.error(`Only ${item.qty} available`); return; }
    setBusy(true);
    try {
      const r = await api.post<{ destination: { po_number: string } }>(`/purchases/items/${item.item_id}/transfer`, {
        new_customer_id: pick, qty: n, reason: reason || null,
      });
      toast.success(`Transferred · new PO ${r.destination.po_number}`);
      await onSuccess();
    } catch (e: any) {
      toast.error(e instanceof ApiError ? e.detail || e.message : "Transfer failed");
    } finally { setBusy(false); }
  };

  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.transferBackdrop}
      >
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
        <View style={styles.transferCard}>
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <Text style={type.titleMd}>Transfer to Another Customer</Text>
            <Pressable onPress={onClose} hitSlop={8}><Feather name="x" size={16} color={colors.onSurfaceMuted} /></Pressable>
          </View>

          <Text style={styles.fieldLabel}>PRODUCT</Text>
          <View style={styles.transferProduct}>
            <View style={styles.transferThumb}>
              {item.image && Platform.OS === "web" ? (
                // @ts-ignore
                <img src={item.image} style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: 6 }} />
              ) : <Feather name="image" size={14} color={colors.onSurfaceMuted} />}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }} numberOfLines={2}>{item.name}</Text>
              <Text style={styles.mono}>{item.sku}</Text>
            </View>
          </View>

          <View style={{ flexDirection: "row", gap: 10, marginTop: 12 }}>
            <View style={{ flex: 1 }}>
              <Text style={styles.fieldLabel}>CURRENT CUSTOMER</Text>
              <View style={styles.transferReadonly}>
                <Text style={{ fontSize: 13, fontWeight: "600" }} numberOfLines={1}>{item.customer_name}</Text>
                <Text style={styles.mono}>{item.po_number}</Text>
              </View>
            </View>
            <View style={{ width: 110 }}>
              <Text style={styles.fieldLabel}>QTY TO TRANSFER</Text>
              <TextInput
                testID="transfer-qty"
                value={qty} onChangeText={(v) => setQty(v.replace(/[^0-9.]/g, ""))}
                keyboardType="numeric"
                style={[styles.input, { textAlign: "center", fontWeight: "700" }]}
              />
              <Text style={{ fontSize: 11, color: colors.onSurfaceMuted, marginTop: 4, textAlign: "center" }}>
                Available: {item.qty}
              </Text>
            </View>
          </View>

          <View style={{ marginTop: 12 }}>
            <Text style={styles.fieldLabel}>NEW CUSTOMER</Text>
            {Platform.OS === "web" ? (
              // @ts-ignore
              <select
                testID="transfer-customer"
                value={pick}
                onChange={(e: any) => setPick(e.target.value)}
                style={{
                  borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 10, fontSize: 14,
                  backgroundColor: colors.surfaceSecondary, color: colors.onSurface, width: "100%",
                } as any}
              >
                <option value="">Select new customer</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>{c.company || c.name}</option>
                ))}
              </select>
            ) : (
              <ScrollView style={{ maxHeight: 160, borderWidth: 1, borderColor: colors.border, borderRadius: 8 }}>
                {customers.map((c) => (
                  <Pressable key={c.id} onPress={() => setPick(c.id)} style={[styles.custPick, pick === c.id && styles.custPickOn]}>
                    <Text style={{ fontSize: 13, color: colors.onSurface, flex: 1 }} numberOfLines={1}>{c.company || c.name}</Text>
                    {pick === c.id ? <Feather name="check" size={13} color={colors.brand} /> : null}
                  </Pressable>
                ))}
              </ScrollView>
            )}
          </View>

          <View style={{ marginTop: 12 }}>
            <Text style={styles.fieldLabel}>REASON (optional)</Text>
            <TextInput
              testID="transfer-reason"
              value={reason} onChangeText={setReason}
              placeholder="Enter reason for transfer…"
              placeholderTextColor={colors.onSurfaceMuted}
              style={[styles.input, { minHeight: 60 }]}
              multiline
            />
          </View>

          <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
            <Pressable onPress={onClose} style={[styles.cancelBtn, { flex: 1 }]}>
              <Text style={{ color: colors.onSurface, fontWeight: "600" }}>Cancel</Text>
            </Pressable>
            <Pressable
              testID="transfer-submit"
              onPress={submit} disabled={busy}
              style={({ pressed }) => [styles.transferPrimary, { flex: 1.4 }, busy ? { opacity: 0.6 } : pressed ? { opacity: 0.9 } : null]}
            >
              {busy ? <ActivityIndicator size="small" color={colors.onBrand} /> :
                <Text style={{ color: colors.onBrand, fontWeight: "700" }}>Transfer &amp; Create PO</Text>
              }
            </Pressable>
          </View>

          <View style={styles.transferFoot}>
            <Feather name="info" size={11} color={colors.onSurfaceMuted} />
            <Text style={{ fontSize: 11, color: colors.onSurfaceMuted }}>
              This will create a new PO for the new customer. Audit trail is preserved.
            </Text>
          </View>
        </View>
      </KeyboardAvoidingView>
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
});
