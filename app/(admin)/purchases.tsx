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
import { type Dispatch, type SetStateAction, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator, FlatList, Linking, Modal, Platform, Pressable,
  ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { getPurchasesPage, type PurchaseItem, type PurchasesPage } from "@/src/api/purchases";
import { useBp } from "@/src/design/responsive";
import { ProductImage } from "@/src/components/ProductImage";
import { toast } from "@/src/components/Toast";
import { colors, PRODUCT_IMAGE_ASPECT_RATIO, radius, shadow, spacing, type } from "@/src/theme/tokens";
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

type Item = PurchaseItem;
type BulkMoveResult = {
  item_id: string;
  ok: boolean;
  error?: string | null;
  error_code?: string | null;
};
type BulkMoveResponse = {
  count: number;
  succeeded: number;
  failed: number;
  results: BulkMoveResult[];
};

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
  // Scoped to whichever business unit is currently active (the X-Floor-Id
  // header set by src/api/client.ts) — NOT pinned to one floor. Pinning
  // this screen to "first-floor" is what made Ground Floor show The
  // Sanitary Bathroom's records.
  const router = useRouter();
  const { isDesktop } = useBp();

  // View + filter state
  const [view, setView] = useState<ViewMode>("today");
  const [brand, setBrand] = useState<string>("all");
  const [q, setQ] = useState<string>("");
  const [committedQ, setCommittedQ] = useState<string>("");
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
  const [loadingMore, setLoadingMore] = useState(false);
  const [total, setTotal] = useState(0);
  const [nextSkip, setNextSkip] = useState<number | null>(null);
  const nextSkipRef = useRef<number | null>(null);
  const [showMobileFilters, setShowMobileFilters] = useState(false);
  const [showMobileActions, setShowMobileActions] = useState(false);
  const requestSeq = useRef(0);
  const requestController = useRef<AbortController | null>(null);

  // Selection (for bulk move)
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkResponse, setBulkResponse] = useState<BulkMoveResponse | null>(null);
  const [bulkRetryStage, setBulkRetryStage] = useState<Stage | null>(null);
  const [bulkRefreshError, setBulkRefreshError] = useState<string | null>(null);

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
  const loadFacets = useCallback(async ({ throwOnError = false }: { throwOnError?: boolean } = {}) => {
    try {
      const [b, s, c] = await Promise.all([
        api.get<{ all: number; brands: BrandFacet[] }>("/purchases/brands"),
        api.get<StageMeta[]>("/purchases/stages"),
        api.get<CustomerFacet[]>("/purchases/customers"),
      ]);
      setBrands(b.brands); setBrandsTotal(b.all); setStages(s); setCustomers(c);
    } catch (e) {
      if (throwOnError) throw e;
      /* Purchases remains usable when a secondary facet cannot load. */
    }
  }, []);

  const loadItems = useCallback(async ({ throwOnError = false, append = false }: { throwOnError?: boolean; append?: boolean } = {}) => {
    if (append && nextSkipRef.current == null) return;
    const skip = append ? nextSkipRef.current || 0 : 0;
    const seq = ++requestSeq.current;
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    if (append) setLoadingMore(true);
    else setLoading(true);
    try {
      const resp: PurchasesPage = await getPurchasesPage({ view, brand, q: committedQ, stage, skip, limit: isDesktop ? 100 : 30 }, controller.signal);
      if (seq !== requestSeq.current) return;
      setItems((current) => append ? [...current, ...resp.items] : resp.items);
      setTotal(resp.total);
      setNextSkip(resp.next_skip);
      nextSkipRef.current = resp.next_skip;
      setBlockedCount(resp.summaries.blocked_count);
      setSlaDays(resp.summaries.sla_days);
      // Prune selection to visible items
      if (!append) setSelected((prev) => {
        const visible = new Set(resp.items.map((i) => i.item_id));
        const next = new Set<string>();
        prev.forEach((id) => { if (visible.has(id)) next.add(id); });
        return next;
      });
    } catch (e: any) {
      if (controller.signal.aborted) return;
      if (throwOnError) throw e;
      toast.error(e?.detail || "Could not load items");
    } finally {
      if (seq === requestSeq.current) { setLoading(false); setLoadingMore(false); }
    }
  }, [view, brand, committedQ, stage, isDesktop]);

  useEffect(() => { loadFacets(); }, [loadFacets]);
  useEffect(() => { loadShortages(); }, [loadShortages]);
  useEffect(() => {
    const t = setTimeout(() => setCommittedQ(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => {
    loadItems();
    return () => requestController.current?.abort();
  }, [loadItems]);

  const refreshPurchases = useCallback(async ({ strict = false }: { strict?: boolean } = {}) => {
    await Promise.all([
      loadItems({ throwOnError: strict }),
      loadFacets({ throwOnError: strict }),
    ]);
  }, [loadItems, loadFacets]);

  // -----------------------------------
  // Mutations
  // -----------------------------------
  const bulkMove = useCallback(async (toStage: Stage, itemIds?: string[]) => {
    const targetIds = itemIds?.length ? itemIds : Array.from(selected);
    if (targetIds.length === 0) { toast.error("Select at least one item"); return; }
    if (bulkBusy) return;
    setBulkBusy(true);
    setBulkResponse(null);
    setBulkRetryStage(null);
    setBulkRefreshError(null);
    try {
      const r = await api.post<BulkMoveResponse>(`/purchases/items/bulk-move`, {
        item_ids: targetIds,
        stage: toStage,
      });
      const succeededIds = r.results.filter((result) => result.ok).map((result) => result.item_id);
      const failedIds = r.results.filter((result) => !result.ok).map((result) => result.item_id);
      setBulkResponse(r);
      setBulkRetryStage(failedIds.length > 0 ? toStage : null);
      setSelected((prev) => {
        const next = new Set(prev);
        succeededIds.forEach((id) => next.delete(id));
        failedIds.forEach((id) => next.add(id));
        return next;
      });
      setShowMoveMenu(false);
      setBulkRetryStage(failedIds.length > 0 ? toStage : null);
      try {
        await refreshPurchases({ strict: true });
        setBulkResponse(r);
        if (r.failed === 0) {
          toast.success(`Moved ${r.succeeded} item${r.succeeded === 1 ? "" : "s"}`);
        } else if (r.succeeded > 0) {
          toast.success(`Moved ${r.succeeded} item${r.succeeded === 1 ? "" : "s"} · ${r.failed} failed`);
        } else {
          toast.error(`Bulk move failed for ${r.failed} item${r.failed === 1 ? "" : "s"}`);
        }
      } catch (refreshError: any) {
        setBulkResponse(null);
        setBulkRefreshError(refreshError?.detail || "Move completed, but the follow-up refresh failed. Data may be stale until you refresh.");
        toast.error(refreshError?.detail || "Move completed, but refresh failed");
      }
    } catch (e: any) {
      setBulkResponse(null);
      setBulkRetryStage(null);
      setBulkRefreshError(null);
      toast.error(e?.detail || "Bulk move failed");
    } finally {
      setBulkBusy(false);
    }
  }, [selected, bulkBusy, refreshPurchases]);

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
  const bulkFailedIds = useMemo(
    () => bulkResponse?.results.filter((result) => !result.ok).map((result) => result.item_id) || [],
    [bulkResponse],
  );
  const bulkResultTone = bulkRefreshError ? "error" : bulkResponse == null ? null : bulkResponse.failed === 0 ? "success" : bulkResponse.succeeded > 0 ? "partial" : "error";
  const bulkResultMessage = useMemo(() => {
    if (bulkRefreshError) {
      return bulkRefreshError;
    }
    if (!bulkResponse) return "";
    if (bulkResponse.failed === 0) {
      return `Moved ${bulkResponse.succeeded} item${bulkResponse.succeeded === 1 ? "" : "s"} successfully.`;
    }
    if (bulkResponse.succeeded > 0) {
      return `Moved ${bulkResponse.succeeded} item${bulkResponse.succeeded === 1 ? "" : "s"}; ${bulkResponse.failed} item${bulkResponse.failed === 1 ? "" : "s"} failed and remain selected.`;
    }
    return `No items moved. ${bulkResponse.failed} item${bulkResponse.failed === 1 ? "" : "s"} failed and remain selected.`;
  }, [bulkResponse, bulkRefreshError]);

  const activeStageCount = stages.reduce((acc, s) => acc + s.count, 0);

  if (!isDesktop) {
    const activeFilterCount = (brand !== "all" ? 1 : 0) + (stage ? 1 : 0);
    return (
      <SafeAreaView style={styles.mobileSafe} edges={["top"]}>
        <FlatList
          testID="purchases-mobile-list"
          data={items}
          keyExtractor={(item) => item.item_id}
          renderItem={({ item }) => (
            <MobilePurchaseCard
              item={item}
              selected={selected.has(item.item_id)}
              onSelect={() => setSelected((current) => {
                const next = new Set(current);
                if (next.has(item.item_id)) next.delete(item.item_id);
                else next.add(item.item_id);
                return next;
              })}
              onMove={() => setRowMoveTarget(item)}
              onTransfer={() => setTransferItem(item)}
              onHistory={() => setHistoryItemId(item.item_id)}
              onOpenPo={() => router.push(`/(admin)/purchase-orders/${item.po_id}` as any)}
            />
          )}
          contentContainerStyle={styles.mobileListContent}
          ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
          onEndReached={() => { if (!loading && !loadingMore && nextSkip != null) loadItems({ append: true }); }}
          onEndReachedThreshold={0.35}
          ListHeaderComponent={(
            <View style={{ gap: 12 }}>
              <View style={styles.mobileTitleRow}>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={styles.overline}>PURCHASES · {VIEW_META[view].label.toUpperCase()}</Text>
                  <Text style={styles.mobilePageTitle}>Purchases</Text>
                  <Text style={type.bodyMuted}>{total} tracked · {blockedCount} blocked · SLA {slaDays}d</Text>
                </View>
                <Pressable accessibilityLabel="More purchase actions" onPress={() => setShowMobileActions(true)} style={styles.mobileIconButton}>
                  <Feather name="more-vertical" size={20} color={colors.onSurface} />
                </Pressable>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.mobileChips}>
                {VIEW_ORDER.map((mode) => (
                  <Pressable key={mode} testID={`view-${mode}`} onPress={() => { setView(mode); setStage(""); }} style={[styles.mobileChip, view === mode && styles.mobileChipActive]}>
                    <Feather name={VIEW_META[mode].icon} size={15} color={view === mode ? colors.onBrand : colors.onSurfaceMuted} />
                    <Text style={[styles.mobileChipText, view === mode && styles.mobileChipTextActive]}>{VIEW_META[mode].label}</Text>
                    {mode === "today" && blockedCount > 0 ? <Text style={[styles.mobileChipCount, view === mode && { color: colors.onBrand }]}>{blockedCount}</Text> : null}
                  </Pressable>
                ))}
              </ScrollView>
              <View style={styles.mobileControlRow}>
                <View style={styles.mobileSearch}>
                  <Feather name="search" size={18} color={colors.onSurfaceMuted} />
                  <TextInput testID="purchases-search" value={q} onChangeText={setQ} placeholder="Product, SKU or customer" placeholderTextColor={colors.onSurfaceMuted} style={styles.mobileSearchInput} autoCorrect={false} autoCapitalize="none" returnKeyType="search" onSubmitEditing={() => setCommittedQ(q.trim())} />
                  {q ? <Pressable accessibilityLabel="Clear search" onPress={() => setQ("")} style={styles.mobileClear}><Feather name="x" size={18} color={colors.onSurfaceMuted} /></Pressable> : null}
                </View>
                <Pressable testID="purchases-filter-button" onPress={() => setShowMobileFilters(true)} style={[styles.mobileFilterButton, activeFilterCount > 0 && styles.mobileFilterButtonActive]}>
                  <Feather name="sliders" size={18} color={activeFilterCount ? colors.onBrand : colors.onSurface} />
                  {activeFilterCount > 0 ? <Text style={styles.mobileFilterCount}>{activeFilterCount}</Text> : null}
                </Pressable>
              </View>
              {activeFilterCount > 0 ? (
                <View style={styles.activeFilterRow}>
                  <Text style={styles.activeFilterText} numberOfLines={2}>
                    {brand !== "all" ? brands.find((entry) => entry.id === brand)?.name || "Brand" : ""}{brand !== "all" && stage ? " · " : ""}{stage ? stages.find((entry) => entry.key === stage)?.label : ""}
                  </Text>
                  <Pressable onPress={() => { setBrand("all"); setStage(""); }} style={styles.clearFiltersButton}><Text style={styles.clearFiltersText}>Clear</Text></Pressable>
                </View>
              ) : null}
              {selected.size > 0 ? (
                <Pressable testID="mobile-bulk-move" onPress={() => setShowMoveMenu(true)} style={styles.mobileBulkButton}>
                  <Text style={styles.mobileBulkText}>Move {selected.size} selected</Text><Feather name="chevron-down" size={18} color={colors.onBrand} />
                </Pressable>
              ) : null}
              <View style={styles.mobileOperationalSummary}>
                <OpsMetric label="Shown" value={items.length} icon="list" />
                <OpsMetric label="Total" value={total} icon="package" />
                <OpsMetric label="Blocked" value={blockedCount} icon="alert-triangle" tone={blockedCount ? "risk" : "ok"} />
              </View>
              {loading ? <View style={styles.loadingCard}><ActivityIndicator /><Text style={type.caption}>Loading purchases…</Text></View> : null}
              {!loading && items.length === 0 ? <View style={styles.mobileEmpty}><Feather name="package" size={28} color={colors.onSurfaceMuted} /><Text style={styles.actionTitle}>No purchases found</Text><Text style={type.bodyMuted}>Clear filters or try a different search.</Text></View> : null}
            </View>
          )}
          ListFooterComponent={loadingMore ? <View style={styles.mobileFooter}><ActivityIndicator /><Text style={type.caption}>Loading more…</Text></View> : <View style={{ height: 96 }} />}
          initialNumToRender={8}
          maxToRenderPerBatch={8}
          windowSize={7}
          removeClippedSubviews={Platform.OS !== "web"}
          keyboardShouldPersistTaps="handled"
        />
        <MobileFiltersSheet visible={showMobileFilters} brands={brands} stages={stages} brand={brand} stage={stage} onBrand={setBrand} onStage={setStage} onClose={() => setShowMobileFilters(false)} />
        <MobileActionsSheet visible={showMobileActions} shortages={shortages.length} onClose={() => setShowMobileActions(false)} onExport={() => { setShowMobileActions(false); doExport(); }} onShortages={() => { setShowMobileActions(false); setShowShortages(true); }} onSettings={() => { setShowMobileActions(false); setShowSettings(true); }} />
        <MoveMenu visible={showMoveMenu} stages={stages} onClose={() => setShowMoveMenu(false)} onPick={(s) => bulkMove(s)} title={`Move ${selected.size} item${selected.size === 1 ? "" : "s"}`} busy={bulkBusy} />
        <MoveStageSheet visible={!!rowMoveTarget} item={rowMoveTarget ? toMovable(rowMoveTarget) : null} onClose={() => setRowMoveTarget(null)} onMoved={async () => { await Promise.all([loadItems(), loadFacets()]); }} />
        <TransferSheet visible={!!transferItem} item={transferItem ? toMovable(transferItem) : null} onClose={() => setTransferItem(null)} onSuccess={async () => { await Promise.all([loadItems(), loadFacets(), loadShortages()]); }} />
        <HistorySheet visible={!!historyItemId} itemId={historyItemId} onClose={() => setHistoryItemId(null)} />
        <ShortagesModal visible={showShortages} shortages={shortages} onClose={() => setShowShortages(false)} onChanged={async () => { await Promise.all([loadShortages(), loadItems(), loadFacets()]); }} />
        <SettingsModal visible={showSettings} currentSla={slaDays} onClose={() => setShowSettings(false)} onSaved={async (value) => { setSlaDays(value); setShowSettings(false); await loadItems(); }} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={[styles.scroll, !isDesktop && { paddingHorizontal: spacing.md, paddingBottom: 120 }]}>
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
              disabled={selected.size === 0 || bulkBusy}
              style={({ pressed }) => [styles.iconAction, (selected.size === 0 || bulkBusy) && { opacity: 0.5 }, pressed && { opacity: 0.85 }]}
            >
              <Text style={{ color: colors.onSurface, fontWeight: "600", fontSize: 13 }}>
                {bulkBusy ? "Moving…" : `Move Material ${selected.size > 0 ? `(${selected.size})` : ""}`}
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

        {bulkResultTone ? (
          <View
            style={[
              styles.bulkResultBanner,
              bulkResultTone === "success" && styles.bulkResultBannerSuccess,
              bulkResultTone === "partial" && styles.bulkResultBannerPartial,
              bulkResultTone === "error" && styles.bulkResultBannerError,
            ]}
          >
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={styles.bulkResultTitle}>
                {bulkRefreshError
                  ? "Refresh needed"
                  : bulkResultTone === "success"
                    ? "Bulk move completed"
                    : bulkResultTone === "partial"
                      ? "Bulk move partially completed"
                      : "Bulk move failed"}
              </Text>
              <Text style={styles.bulkResultText}>{bulkResultMessage}</Text>
            </View>
            <View style={styles.bulkBannerActions}>
              {bulkRefreshError ? (
                <Pressable
                  testID="bulk-refresh-retry"
                  onPress={async () => {
                    if (bulkBusy) return;
                    setBulkBusy(true);
                    try {
                      await refreshPurchases({ strict: true });
                      setBulkRefreshError(null);
                    } catch (e: any) {
                      setBulkRefreshError(e?.detail || "Refresh failed. Please try again.");
                      toast.error(e?.detail || "Refresh failed");
                    } finally {
                      setBulkBusy(false);
                    }
                  }}
                  disabled={bulkBusy}
                  style={({ pressed }) => [styles.bulkGhostBtn, bulkBusy && { opacity: 0.6 }, pressed && { opacity: 0.85 }]}
                >
                  {bulkBusy ? <ActivityIndicator size="small" color={colors.onSurface} /> : <Text style={styles.bulkGhostText}>Refresh data</Text>}
                </Pressable>
              ) : null}
              {bulkFailedIds.length > 0 && bulkRetryStage ? (
                <Pressable
                  testID="bulk-move-retry"
                  onPress={() => bulkMove(bulkRetryStage, bulkFailedIds)}
                  disabled={bulkBusy}
                  style={({ pressed }) => [styles.bulkRetryBtn, bulkBusy && { opacity: 0.6 }, pressed && { opacity: 0.85 }]}
                >
                  {bulkBusy ? <ActivityIndicator size="small" color={colors.onBrand} /> : <Text style={styles.bulkRetryText}>Retry failed ({bulkFailedIds.length})</Text>}
                </Pressable>
              ) : null}
            </View>
          </View>
        ) : null}

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
            {nextSkip != null ? (
              <Pressable onPress={() => loadItems({ append: true })} disabled={loadingMore} style={styles.desktopLoadMore}>
                {loadingMore ? <ActivityIndicator size="small" /> : <Text style={styles.desktopLoadMoreText}>Load more · {items.length} of {total}</Text>}
              </Pressable>
            ) : null}
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
        busy={bulkBusy}
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
// Phone presentation.  It deliberately owns the only vertical scroll on the
// screen; sheets render outside the FlatList and never compete for gestures.
// -----------------------------------------------------------------------------
function MobilePurchaseCard({ item, selected, onSelect, onMove, onTransfer, onHistory, onOpenPo }: {
  item: Item; selected: boolean; onSelect: () => void; onMove: () => void;
  onTransfer: () => void; onHistory: () => void; onOpenPo: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const tone = STAGE_TONE[item.stage] || item.stage_tone;
  return (
    <View style={[styles.mobilePurchaseCard, item.blocked && styles.mobilePurchaseCardBlocked]}>
      <View style={styles.mobileCardTop}>
        <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: selected }} accessibilityLabel={`Select ${item.name}`} onPress={onSelect} style={styles.mobileSelectTarget}>
          <View style={[styles.chk, selected && styles.chkOn]}>{selected ? <Feather name="check" size={12} color={colors.onBrand} /> : null}</View>
        </Pressable>
        <ProductImage source={item.image} style={styles.mobileCardImage} fallbackLabel={item.sku} disableSkeleton borderRadius={8} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={styles.mobileCardName} numberOfLines={2}>{item.name}</Text>
          <Text style={styles.mobileCardMeta} numberOfLines={2}>{item.sku || "No SKU"} · {item.brand_name || "Unbranded"}</Text>
        </View>
        <Pressable accessibilityLabel={`Actions for ${item.name}`} onPress={() => setMenuOpen(true)} style={styles.mobileIconButton}>
          <Feather name="more-vertical" size={19} color={colors.onSurface} />
        </Pressable>
      </View>
      <View style={styles.mobileCardDetailRow}>
        <View style={{ flex: 1, minWidth: 0 }}><Text style={styles.mobileCardLabel}>CUSTOMER</Text><Text style={styles.mobileCardValue} numberOfLines={2}>{item.customer_name || "—"}</Text></View>
        <View style={{ minWidth: 76 }}><Text style={styles.mobileCardLabel}>QUANTITY</Text><Text style={styles.mobileCardValue}>{item.qty}</Text></View>
        <View style={{ minWidth: 82, alignItems: "flex-end" }}><Text style={styles.mobileCardLabel}>AGE</Text><Text style={[styles.mobileCardValue, item.blocked && { color: colors.error }]}>{item.age_days}d</Text></View>
      </View>
      <View style={styles.mobileCardBottom}>
        <View style={[styles.stageBadge, { backgroundColor: tone.bg }]}><Text style={{ color: tone.fg, fontWeight: "700", fontSize: 12 }}>{item.stage_label}</Text></View>
        <Text style={styles.mobileCardPo} numberOfLines={1}>{item.po_number || "No PO"}</Text>
        {item.blocked ? <View style={styles.mobileBlockedPill}><Text style={styles.mobileBlockedText}>Blocked</Text></View> : null}
      </View>
      <Modal visible={menuOpen} transparent animationType="fade" onRequestClose={() => setMenuOpen(false)}>
        <Pressable style={styles.mobileSheetBackdrop} onPress={() => setMenuOpen(false)}>
          <Pressable style={styles.mobileSheet} onPress={(event) => event.stopPropagation()}>
            <Text style={styles.mobileSheetTitle} numberOfLines={2}>{item.name}</Text>
            <SheetAction icon="repeat" label="Move material" onPress={() => { setMenuOpen(false); onMove(); }} />
            <SheetAction icon="shuffle" label="Transfer customer" onPress={() => { setMenuOpen(false); onTransfer(); }} />
            <SheetAction icon="clock" label="Movement history" onPress={() => { setMenuOpen(false); onHistory(); }} />
            <SheetAction icon="file-text" label="Open purchase order" onPress={() => { setMenuOpen(false); onOpenPo(); }} />
            <Pressable onPress={() => setMenuOpen(false)} style={styles.mobileSheetCancel}><Text style={styles.mobileSheetCancelText}>Cancel</Text></Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

function SheetAction({ icon, label, onPress }: { icon: keyof typeof Feather.glyphMap; label: string; onPress: () => void }) {
  return <Pressable onPress={onPress} style={({ pressed }) => [styles.mobileSheetAction, pressed && { backgroundColor: colors.surfaceTertiary }]}><Feather name={icon} size={19} color={colors.onSurface} /><Text style={styles.mobileSheetActionText}>{label}</Text><Feather name="chevron-right" size={18} color={colors.onSurfaceMuted} /></Pressable>;
}

function MobileFiltersSheet({ visible, brands, stages, brand, stage, onBrand, onStage, onClose }: {
  visible: boolean; brands: BrandFacet[]; stages: StageMeta[]; brand: string; stage: Stage | "";
  onBrand: (value: string) => void; onStage: (value: Stage | "") => void; onClose: () => void;
}) {
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.mobileSheetBackdrop} onPress={onClose}>
        <Pressable style={[styles.mobileSheet, { maxHeight: "82%" }]} onPress={(event) => event.stopPropagation()}>
          <View style={styles.mobileSheetHeader}><Text style={styles.mobileSheetTitle}>Filter purchases</Text><Pressable accessibilityLabel="Close filters" onPress={onClose} style={styles.mobileIconButton}><Feather name="x" size={20} color={colors.onSurface} /></Pressable></View>
          <ScrollView contentContainerStyle={{ paddingBottom: 8 }}>
            <Text style={styles.sectionLabel}>BRAND</Text>
            <View style={styles.mobileFilterOptions}>
              <FilterOption label="All brands" active={brand === "all"} onPress={() => onBrand("all")} />
              {brands.map((entry) => <FilterOption key={entry.id} label={`${entry.name} (${entry.count})`} active={brand === entry.id} onPress={() => onBrand(entry.id)} />)}
            </View>
            <Text style={[styles.sectionLabel, { marginTop: 18 }]}>STAGE</Text>
            <View style={styles.mobileFilterOptions}>
              <FilterOption label="All stages" active={!stage} onPress={() => onStage("")} />
              {stages.map((entry) => <FilterOption key={entry.key} label={`${entry.label} (${entry.count})`} active={stage === entry.key} onPress={() => onStage(entry.key)} />)}
            </View>
          </ScrollView>
          <Pressable testID="apply-purchase-filters" onPress={onClose} style={styles.mobileApplyButton}><Text style={styles.mobileApplyText}>Show results</Text></Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function FilterOption({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return <Pressable onPress={onPress} style={[styles.mobileFilterOption, active && styles.mobileFilterOptionActive]}><Text style={[styles.mobileFilterOptionText, active && { color: colors.brand, fontWeight: "700" }]} numberOfLines={2}>{label}</Text>{active ? <Feather name="check" size={18} color={colors.brand} /> : null}</Pressable>;
}

function MobileActionsSheet({ visible, shortages, onClose, onExport, onShortages, onSettings }: { visible: boolean; shortages: number; onClose: () => void; onExport: () => void; onShortages: () => void; onSettings: () => void }) {
  return <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}><Pressable style={styles.mobileSheetBackdrop} onPress={onClose}><Pressable style={styles.mobileSheet} onPress={(event) => event.stopPropagation()}><Text style={styles.mobileSheetTitle}>Purchase actions</Text><SheetAction icon="download" label="Export Excel" onPress={onExport} />{shortages > 0 ? <SheetAction icon="alert-triangle" label={`${shortages} awaiting reorder`} onPress={onShortages} /> : null}<SheetAction icon="settings" label="Tracker settings" onPress={onSettings} /><Pressable onPress={onClose} style={styles.mobileSheetCancel}><Text style={styles.mobileSheetCancelText}>Cancel</Text></Pressable></Pressable></Pressable></Modal>;
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
  const rowCount = useMemo(() => {
    const counts = new Map<string, number>();
    rows.forEach((row) => counts.set(row.customer_id, (counts.get(row.customer_id) || 0) + 1));
    return counts;
  }, [rows]);
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
          <View style={{ flexDirection: "row", alignItems: "flex-start", gap: 8, flexWrap: "wrap" }}>
          <BulkChk checked={checked} onToggle={onToggle} />
          <ProductImage
            source={row.image}
            style={styles.mobileThumb}
            contentFit="contain"
            disableSkeleton
            fallbackLabel={row.sku}
            borderRadius={8}
          />
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{row.name}</Text>
            <Text style={type.caption} numberOfLines={1}>{row.sku} · {row.customer_name}</Text>
          </View>
          <StageBadge stage={row.stage} tone={row.stage_tone} label={row.stage_label} />
        </View>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 8, flexWrap: "wrap", gap: 6 }}>
          <Text style={[type.caption, { flex: 1, minWidth: 0 }]} numberOfLines={2}>
            Qty {row.qty} · {row.brand_name} · {row.age_days}d{row.supplier_name ? ` · via ${row.supplier_name}` : ""}
          </Text>
          <View style={{ flexDirection: "row", gap: 6 }}>
            <Pressable onPress={onHistory} style={styles.mobileTransferBtn} hitSlop={6}><Feather name="clock" size={14} color={colors.onSurface} /></Pressable>
            <Pressable onPress={onOpenMove} style={styles.mobileMoveBtn} hitSlop={6}><Text style={styles.moveBtnText}>Move</Text></Pressable>
            <Pressable onPress={onTransfer} style={styles.mobileTransferBtn} hitSlop={6}><Feather name="repeat" size={14} color={colors.onSurface} /></Pressable>
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
          contentFit="contain"
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
        contentFit="contain"
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
function MoveMenu({ visible, stages, onClose, onPick, title, currentStage, busy = false }: {
  visible: boolean; stages: StageMeta[]; onClose: () => void;
  onPick: (s: Stage) => void; title: string; currentStage?: Stage; busy?: boolean;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.modalBackdrop} onPress={onClose}>
        <View style={styles.menuCard}>
          <Text style={{ fontSize: 14, fontWeight: "700", marginBottom: 4 }}>{title}</Text>
          <Text style={type.caption}>{busy ? "Moving selected items…" : "Move to any stage"}</Text>
          <View style={{ marginTop: 10, gap: 4 }}>
            {stages.map((s) => (
              <Pressable
                key={s.key}
                testID={`move-to-${s.key}`}
                onPress={() => onPick(s.key)}
                disabled={s.key === currentStage || busy}
                style={({ pressed }) => [
                  styles.menuItem, pressed && { backgroundColor: colors.surfaceTertiary },
                  (s.key === currentStage || busy) && { opacity: 0.4 },
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
              disabled={busy}
              style={({ pressed }) => [styles.menuItem, busy && { opacity: 0.4 }, pressed && { backgroundColor: colors.surfaceTertiary }]}
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
  bulkResultBanner: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    borderWidth: 1, borderRadius: radius.md, padding: spacing.md,
  },
  bulkResultBannerSuccess: { backgroundColor: ds.okTint, borderColor: "rgba(38,110,76,0.24)" },
  bulkResultBannerPartial: { backgroundColor: ds.warnTint, borderColor: "rgba(168,120,44,0.24)" },
  bulkResultBannerError: { backgroundColor: ds.riskTint, borderColor: "rgba(174,74,61,0.24)" },
  bulkResultTitle: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  bulkResultText: { marginTop: 2, fontSize: 12, color: colors.onSurfaceSecondary },
  bulkRetryBtn: {
    minHeight: 36, paddingHorizontal: 12, borderRadius: radius.pill,
    backgroundColor: colors.brand, alignItems: "center", justifyContent: "center",
  },
  bulkRetryText: { color: colors.onBrand, fontSize: 12, fontWeight: "700" },
  bulkBannerActions: { flexDirection: "row", flexWrap: "wrap", gap: 8, alignItems: "center" },
  bulkGhostBtn: {
    minHeight: 36, paddingHorizontal: 12, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
    alignItems: "center", justifyContent: "center",
  },
  bulkGhostText: { color: colors.onSurface, fontSize: 12, fontWeight: "700" },

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
    width: 40, aspectRatio: PRODUCT_IMAGE_ASPECT_RATIO, borderRadius: 8, backgroundColor: colors.surfaceTertiary,
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
  mobileTransferBtn: { width: 44, height: 44, borderRadius: 8, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  mobileMoveBtn: { minWidth: 70, minHeight: 44, paddingHorizontal: 12, borderRadius: 8, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  mobileThumb: {
    width: 48, aspectRatio: PRODUCT_IMAGE_ASPECT_RATIO, borderRadius: 8, backgroundColor: colors.surfaceTertiary,
    alignItems: "center", justifyContent: "center", overflow: "hidden",
  },
  thumb: {
    width: 44, aspectRatio: PRODUCT_IMAGE_ASPECT_RATIO, borderRadius: 8, backgroundColor: colors.surfaceTertiary,
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
  actionThumb: { width: 40, aspectRatio: PRODUCT_IMAGE_ASPECT_RATIO },
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
  desktopLoadMore: { minHeight: 44, paddingHorizontal: 18, alignSelf: "center", alignItems: "center", justifyContent: "center", borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  desktopLoadMoreText: { color: colors.onSurface, fontSize: 13, fontWeight: "700" },

  // Mobile-first Purchases workspace
  mobileSafe: { flex: 1, backgroundColor: colors.surface },
  mobileListContent: { paddingHorizontal: 16, paddingTop: 12 },
  mobileTitleRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  mobilePageTitle: { fontFamily: dsFont.display, fontSize: 28, lineHeight: 34, color: colors.onSurface, letterSpacing: -0.3 },
  mobileIconButton: { width: 44, height: 44, borderRadius: 12, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, flexShrink: 0 },
  mobileChips: { gap: 8, paddingRight: 16 },
  mobileChip: { minHeight: 44, paddingHorizontal: 14, borderRadius: 22, flexDirection: "row", alignItems: "center", gap: 7, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  mobileChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  mobileChipText: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  mobileChipTextActive: { color: colors.onBrand },
  mobileChipCount: { fontSize: 12, fontWeight: "800", color: colors.error },
  mobileControlRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  mobileSearch: { flex: 1, height: 48, minWidth: 0, borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingLeft: 12, flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: colors.surfaceSecondary },
  mobileSearchInput: { flex: 1, minWidth: 0, height: 46, paddingVertical: 0, fontSize: 15, color: colors.onSurface, ...(Platform.OS === "web" ? { outlineStyle: "none" } as any : {}) },
  mobileClear: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  mobileFilterButton: { width: 48, height: 48, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  mobileFilterButtonActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  mobileFilterCount: { position: "absolute", right: 5, top: 4, minWidth: 16, height: 16, borderRadius: 8, textAlign: "center", color: colors.brand, backgroundColor: colors.onBrand, fontWeight: "800", fontSize: 10, lineHeight: 16 },
  activeFilterRow: { minHeight: 44, flexDirection: "row", alignItems: "center", gap: 8, paddingLeft: 12, borderRadius: 10, backgroundColor: ds.brassTint },
  activeFilterText: { flex: 1, minWidth: 0, color: ds.brassDeep, fontSize: 13, fontWeight: "600" },
  clearFiltersButton: { minWidth: 64, minHeight: 44, alignItems: "center", justifyContent: "center" },
  clearFiltersText: { color: ds.brassDeep, fontSize: 13, fontWeight: "800" },
  mobileBulkButton: { minHeight: 48, paddingHorizontal: 16, borderRadius: 12, backgroundColor: colors.brand, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8 },
  mobileBulkText: { color: colors.onBrand, fontSize: 14, fontWeight: "800" },
  mobileOperationalSummary: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  mobileEmpty: { minHeight: 180, alignItems: "center", justifyContent: "center", gap: 8, padding: 24, borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.surfaceSecondary },
  mobileFooter: { height: 96, alignItems: "center", justifyContent: "center", gap: 8 },
  mobilePurchaseCard: { padding: 12, borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.surfaceSecondary, gap: 12, overflow: "hidden" },
  mobilePurchaseCardBlocked: { borderLeftWidth: 4, borderLeftColor: colors.error },
  mobileCardTop: { flexDirection: "row", alignItems: "center", gap: 10 },
  mobileSelectTarget: { width: 44, height: 44, alignItems: "center", justifyContent: "center", marginLeft: -10 },
  mobileCardImage: { width: 58, aspectRatio: PRODUCT_IMAGE_ASPECT_RATIO },
  mobileCardName: { color: colors.onSurface, fontSize: 14, lineHeight: 19, fontWeight: "800" },
  mobileCardMeta: { marginTop: 2, color: colors.onSurfaceMuted, fontSize: 11.5, lineHeight: 16 },
  mobileCardDetailRow: { flexDirection: "row", alignItems: "flex-start", gap: 10, paddingHorizontal: 4 },
  mobileCardLabel: { color: colors.onSurfaceMuted, fontSize: 9, fontWeight: "800", letterSpacing: 0.8 },
  mobileCardValue: { marginTop: 3, color: colors.onSurface, fontSize: 13, lineHeight: 17, fontWeight: "700" },
  mobileCardBottom: { minHeight: 30, flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 4 },
  mobileCardPo: { flex: 1, minWidth: 0, color: colors.onSurfaceMuted, fontSize: 11.5, fontVariant: ["tabular-nums"] },
  mobileBlockedPill: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: ds.riskTint },
  mobileBlockedText: { color: colors.error, fontSize: 11, fontWeight: "800" },
  mobileSheetBackdrop: { flex: 1, backgroundColor: "rgba(15,17,21,0.45)", justifyContent: "flex-end" },
  mobileSheet: { width: "100%", maxHeight: "90%", paddingHorizontal: 16, paddingTop: 18, paddingBottom: 24, borderTopLeftRadius: 22, borderTopRightRadius: 22, backgroundColor: colors.surfaceSecondary, ...shadow.strong },
  mobileSheetHeader: { flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 8 },
  mobileSheetTitle: { flex: 1, minWidth: 0, color: colors.onSurface, fontSize: 17, lineHeight: 22, fontWeight: "800", marginBottom: 8 },
  mobileSheetAction: { minHeight: 52, flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 8, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  mobileSheetActionText: { flex: 1, minWidth: 0, color: colors.onSurface, fontSize: 15, fontWeight: "600" },
  mobileSheetCancel: { minHeight: 48, marginTop: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  mobileSheetCancelText: { color: colors.onSurface, fontSize: 14, fontWeight: "800" },
  mobileFilterOptions: { marginTop: 8, gap: 6 },
  mobileFilterOption: { minHeight: 48, paddingHorizontal: 12, paddingVertical: 9, borderRadius: 10, borderWidth: 1, borderColor: colors.border, flexDirection: "row", alignItems: "center", gap: 8 },
  mobileFilterOptionActive: { borderColor: colors.brand, backgroundColor: ds.brassTint },
  mobileFilterOptionText: { flex: 1, minWidth: 0, color: colors.onSurface, fontSize: 14, lineHeight: 19 },
  mobileApplyButton: { minHeight: 50, marginTop: 10, borderRadius: 12, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  mobileApplyText: { color: colors.onBrand, fontSize: 15, fontWeight: "800" },
});
