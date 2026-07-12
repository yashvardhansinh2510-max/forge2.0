// Customer profile with full activity timeline across quotations, purchases,
// and future payments. DS-aligned rebuild: PageHeader, StatTile, SegmentedControl,
// unified list row, Avatar. Business logic preserved.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ActivityTimeline, TimelineEvent } from "@/src/components/ActivityTimeline";
import {
  Avatar, Badge, Button, Card, EmptyState, PageHeader,
  SegmentedControl, StatTile, StatusBadge,
} from "@/src/components/ui";
import { api } from "@/src/api/client";
import { ProductImage } from "@/src/components/ProductImage";
import { toast } from "@/src/components/Toast";
import { colors, icon as iconSize, money, radius, spacing, type } from "@/src/theme/tokens";
import {
  HistorySheet, MovableItem, MoveStageSheet, STAGE_TONE, TransferSheet,
} from "@/src/components/purchases/MovementEngine";

type Customer = {
  id: string; name: string; company?: string | null; email: string;
  phone?: string | null; city?: string | null; tier: "retail" | "trade" | "vip";
  address?: string | null;
};
type Quotation = { id: string; number: string; status: string; grand_total: number; created_at: string; items: any[] };
type PO = { id: string; number: string; brand_name?: string | null; status: string; grand_total: number; created_at: string };

type WorkspaceProduct = {
  item_id: string; po_id: string; po_number: string; sku: string; name: string; image?: string | null;
  brand_name?: string | null; supplier_name?: string | null; stage: string; stage_label: string;
  qty: number; unit_cost: number; blocked: boolean; age_days: number; customer_id: string; customer_name: string;
};
type WorkspaceShortage = {
  id: string; sku: string; name: string; image?: string | null;
  committed_qty: number; allocated_qty: number; shortage_qty: number;
  reason: string; transferred_to_customer_name?: string | null; status: string;
};
type Workspace = {
  customer: Customer;
  summary: {
    total_items: number; total_value: number; outstanding_value: number; outstanding_count: number;
    open_pos: number; blocked_count: number; delivered_count: number; shortage_count: number;
  };
  shortages: WorkspaceShortage[];
  products: WorkspaceProduct[];
  brands: { id: string | null; name: string; count: number }[];
  stages: { key: string; label: string; count: number }[];
  purchase_orders: { id: string; number: string; status: string; brand_name?: string | null; supplier_name?: string | null; grand_total: number; created_at: string; expected_delivery_at?: string | null; item_count: number }[];
  outstanding_items: WorkspaceProduct[];
  recent_activity: TimelineEvent[];
  expected_delivery: { next_at: string | null; purchase_orders: { po_id: string; po_number: string; expected_delivery_at: string }[] };
};

type Tab = "overview" | "quotations" | "purchases" | "timeline";

export default function CustomerDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 900;

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [quotations, setQuotations] = useState<Quotation[]>([]);
  const [purchases, setPurchases] = useState<PO[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [productFilter, setProductFilter] = useState<"all" | "outstanding" | "blocked">("all");
  const [moveItem, setMoveItem] = useState<WorkspaceProduct | null>(null);
  const [transferItem, setTransferItem] = useState<WorkspaceProduct | null>(null);
  const [historyItemId, setHistoryItemId] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [c, qs, pos, tl, ws] = await Promise.all([
      api.get<Customer>(`/customers/${id}`),
      api.get<Quotation[]>(`/quotations`).then((all) => all.filter((q: any) => q.customer_id === id)).catch(() => []),
      api.get<PO[]>(`/purchase-orders?customer_id=${id}`).catch(() => []),
      api.get<TimelineEvent[]>(`/activity/customer/${id}`).catch(() => []),
      api.get<Workspace>(`/purchases/customers/${id}/workspace`).catch(() => null),
    ]);
    setCustomer(c);
    setQuotations(qs);
    setPurchases(pos);
    setTimeline(tl);
    setWorkspace(ws);
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const toMovable = useCallback((p: WorkspaceProduct): MovableItem => ({
    item_id: p.item_id, sku: p.sku, name: p.name, image: p.image, qty: p.qty,
    stage: p.stage as any, customer_id: p.customer_id, customer_name: p.customer_name,
    po_number: p.po_number, brand_name: p.brand_name, supplier_name: p.supplier_name,
  }), []);

  const [shortageBusy, setShortageBusy] = useState<string | null>(null);
  const createPoForShortage = async (s: WorkspaceShortage) => {
    setShortageBusy(s.id);
    try {
      const r = await api.post<{ po_number: string }>(`/purchases/shortages/${s.id}/create-po`);
      toast.success(`Reorder PO ${r.po_number} created`);
      await load();
    } catch (e: any) {
      toast.error(e?.detail || "Could not create PO");
    } finally { setShortageBusy(null); }
  };
  const dismissShortage = async (s: WorkspaceShortage) => {
    setShortageBusy(s.id);
    try {
      await api.post(`/purchases/shortages/${s.id}/dismiss`, {});
      toast.success("Shortage dismissed");
      await load();
    } catch (e: any) {
      toast.error(e?.detail || "Could not dismiss");
    } finally { setShortageBusy(null); }
  };

  const visibleProducts = useMemo(() => {
    if (!workspace) return [];
    if (productFilter === "outstanding") return workspace.outstanding_items;
    if (productFilter === "blocked") return workspace.products.filter((p) => p.blocked);
    return workspace.products;
  }, [workspace, productFilter]);

  const totalRevenue = useMemo(
    () => quotations.filter((q) => ["won", "ordered"].includes(q.status)).reduce((s, q) => s + q.grand_total, 0),
    [quotations],
  );

  if (!customer) return <View style={{ flex: 1, backgroundColor: colors.surface }} />;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <PageHeader
        title={customer.company || customer.name}
        subtitle={`${customer.email}${customer.city ? ` · ${customer.city}` : ""}`}
        overline={`CUSTOMER · ${customer.tier.toUpperCase()}`}
        back={() => router.back()}
        actions={
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Button
              icon="edit-2"
              label="Edit"
              variant="secondary"
              size="md"
              onPress={() => router.push(`/(admin)/customers/${customer.id}/edit` as any)}
            />
          </View>
        }
      />

      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg, paddingBottom: spacing.xxxl }}>
        {/* Identity row */}
        <Card>
          <View style={{ flexDirection: "row", gap: spacing.lg, alignItems: "center", flexWrap: "wrap" }}>
            <Avatar name={customer.company || customer.name} size={64} tone="brand" />
            <View style={{ flex: 1, minWidth: 240, gap: 6 }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" }}>
                <Text style={type.titleLg} numberOfLines={1}>
                  {customer.company || customer.name}
                </Text>
                <Badge
                  label={customer.tier.toUpperCase()}
                  tone={customer.tier === "vip" ? "success" : customer.tier === "trade" ? "info" : "neutral"}
                />
              </View>
              <View style={{ gap: 6, marginTop: 4 }}>
                <Row icon="mail" text={customer.email} />
                {customer.phone ? <Row icon="phone" text={customer.phone} /> : null}
                {customer.address ? <Row icon="map-pin" text={customer.address} /> : null}
              </View>
            </View>
          </View>
        </Card>

        {/* Stats */}
        <View style={[styles.statsRow, !isDesktop && styles.statsRowMobile]}>
          <StatTile label="Lifetime Revenue" value={money(totalRevenue)} icon="trending-up" tone="success" sub="Won + ordered" />
          <StatTile label="Quotations" value={String(quotations.length)} icon="file-text" tone="brand" sub="All statuses" />
          <StatTile label="Purchase Orders" value={String(purchases.length)} icon="shopping-cart" tone="brand" sub="Across brands" />
          <StatTile label="Activity" value={String(timeline.length)} icon="activity" tone="neutral" sub="Events logged" />
        </View>

        {/* Tabs */}
        {isDesktop ? (
          <SegmentedControl
            value={tab}
            onChange={setTab}
            options={[
              { value: "overview", label: "Overview" },
              { value: "quotations", label: `Quotations · ${quotations.length}` },
              { value: "purchases", label: `Purchases · ${workspace?.summary.total_items ?? purchases.length}` },
              { value: "timeline", label: "Timeline" },
            ]}
            fullWidth
          />
        ) : (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
            {[
              { value: "overview" as const, label: "Overview", icon: "grid" as keyof typeof Feather.glyphMap },
              { value: "quotations" as const, label: `Quotations · ${quotations.length}`, icon: "file-text" as keyof typeof Feather.glyphMap },
              { value: "purchases" as const, label: `Purchases · ${workspace?.summary.total_items ?? purchases.length}`, icon: "shopping-cart" as keyof typeof Feather.glyphMap },
              { value: "timeline" as const, label: "Timeline", icon: "activity" as keyof typeof Feather.glyphMap },
            ].map((t) => (
              <Pressable
                key={t.value}
                testID={`customer-tab-${t.value}`}
                onPress={() => setTab(t.value)}
                style={{
                  flexDirection: "row", alignItems: "center", gap: 6,
                  paddingHorizontal: 14, height: 38, borderRadius: 999,
                  backgroundColor: tab === t.value ? colors.brand : colors.surfaceSecondary,
                  borderWidth: 1, borderColor: tab === t.value ? colors.brand : colors.border,
                }}
              >
                <Feather name={t.icon} size={13} color={tab === t.value ? colors.onBrand : colors.onSurfaceSecondary} />
                <Text style={{ fontSize: 12.5, fontWeight: tab === t.value ? "700" : "500", color: tab === t.value ? colors.onBrand : colors.onSurface }} numberOfLines={1}>
                  {t.label}
                </Text>
              </Pressable>
            ))}
          </ScrollView>
        )}

        {/* Body */}
        {tab === "overview" ? (
          <>
            <Card>
              <Text style={[type.overline, { marginBottom: spacing.md }]}>Latest activity</Text>
              <ActivityTimeline events={timeline.slice(0, 8)} dense emptyLabel="No activity yet" />
            </Card>
          </>
        ) : tab === "quotations" ? (
          quotations.length === 0 ? (
            <Card>
              <EmptyState icon="file-text" title="No quotations yet" subtitle="This customer hasn't received a quotation." />
            </Card>
          ) : (
            <Card padding={0}>
              {quotations.map((q, i) => (
                <Pressable
                  key={q.id}
                  onPress={() => router.push(`/(admin)/quotations/${q.id}` as any)}
                  style={({ pressed, hovered }: any) => [
                    styles.listRow,
                    {
                      borderTopWidth: i > 0 ? StyleSheet.hairlineWidth : 0,
                      borderTopColor: colors.divider,
                      backgroundColor: pressed ? colors.surfaceTertiary : hovered ? colors.surfaceSubtle : "transparent",
                    },
                  ]}
                >
                  <Text style={[type.mono, { width: 120 }]} numberOfLines={1}>{q.number}</Text>
                  <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
                    <Text style={type.titleSm} numberOfLines={1}>{q.items.length} items</Text>
                    <Text style={type.caption}>{fmtDate(q.created_at)}</Text>
                  </View>
                  <Text style={[type.mono, { width: 110, textAlign: "right", fontWeight: "700" }]}>
                    {money(q.grand_total)}
                  </Text>
                  <StatusBadge status={q.status} />
                </Pressable>
              ))}
            </Card>
          )
        ) : tab === "purchases" ? (
          !workspace ? (
            <Card>
              <EmptyState icon="shopping-cart" title="No purchase activity" subtitle="Orders will appear here after placement." />
            </Card>
          ) : (
            <View style={{ gap: spacing.lg }}>
              {/* Shortage / reorder alerts — raised automatically when a transfer left this
                  customer under-fulfilled against their original order. */}
              {workspace.shortages.length > 0 ? (
                <View style={{ gap: spacing.sm }}>
                  {workspace.shortages.map((s) => (
                    <Card key={s.id} style={{ backgroundColor: "#FBEAEA", borderColor: "#EFC2C2" }}>
                      <View style={{ flexDirection: "row", gap: spacing.md, alignItems: "flex-start" }}>
                        <Feather name="alert-triangle" size={16} color={colors.error} style={{ marginTop: 2 }} />
                        <View style={{ flex: 1, minWidth: 0 }}>
                          <Text style={{ fontSize: 13, fontWeight: "700", color: "#8A2C2C" }}>
                            Product transferred · {s.name}
                          </Text>
                          <Text style={{ fontSize: 12.5, color: "#8A2C2C", marginTop: 2 }}>
                            {s.reason}
                          </Text>
                          <View style={styles.awaitingReorderPill}>
                            <Text style={{ fontSize: 10.5, fontWeight: "700", color: "#8A2C2C" }}>
                              STATUS: AWAITING REORDER
                            </Text>
                          </View>
                        </View>
                        <View style={{ gap: 6 }}>
                          <Button
                            label="Create PO"
                            size="sm"
                            icon="plus"
                            loading={shortageBusy === s.id}
                            onPress={() => createPoForShortage(s)}
                            testID={`shortage-create-po-${s.id}`}
                          />
                          <Button
                            label="Dismiss"
                            size="sm"
                            variant="ghost"
                            loading={shortageBusy === s.id}
                            onPress={() => dismissShortage(s)}
                            testID={`shortage-dismiss-${s.id}`}
                          />
                        </View>
                      </View>
                    </Card>
                  ))}
                </View>
              ) : null}

              {/* Expected delivery banner */}
              {workspace.expected_delivery.next_at ? (
                <Card style={{ backgroundColor: "#FBF0DD", borderColor: "#E7C77A" }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                    <View style={styles.deliveryIcon}>
                      <Feather name="truck" size={16} color="#8A6116" />
                    </View>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={{ fontSize: 13, fontWeight: "700", color: "#5C4008" }}>
                        Next expected delivery · {fmtDate(workspace.expected_delivery.next_at)}
                      </Text>
                      <Text style={type.caption} numberOfLines={1}>
                        {workspace.expected_delivery.purchase_orders.map((p) => p.po_number).join(", ")}
                      </Text>
                    </View>
                  </View>
                </Card>
              ) : null}

              {/* Purchase summary */}
              <View style={[styles.statsRow, !isDesktop && styles.statsRowMobile]}>
                <StatTile label="Order Value" value={money(workspace.summary.total_value)} icon="shopping-bag" tone="brand" sub={`${workspace.summary.total_items} products`} />
                <StatTile label="Outstanding" value={money(workspace.summary.outstanding_value)} icon="clock" tone="warning" sub={`${workspace.summary.outstanding_count} pending`} />
                <StatTile label="Open POs" value={String(workspace.summary.open_pos)} icon="file-text" tone="brand" sub={`${purchases.length} total`} />
                <StatTile label="Delayed" value={String(workspace.summary.blocked_count)} icon="alert-triangle" tone={workspace.summary.blocked_count > 0 ? "danger" : "success"} sub="Past SLA" />
              </View>

              {/* Brands + Stages breakdown */}
              <View style={{ flexDirection: isDesktop ? "row" : "column", gap: spacing.lg }}>
                <Card style={{ flex: 1 }}>
                  <Text style={[type.overline, { marginBottom: spacing.sm }]}>Brands ordered</Text>
                  {workspace.brands.length === 0 ? (
                    <Text style={type.caption}>No brand data yet</Text>
                  ) : (
                    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                      {workspace.brands.map((b) => (
                        <View key={b.id || "unbranded"} style={styles.chip}>
                          <Text style={styles.chipText}>{b.name}</Text>
                          <View style={styles.chipCount}><Text style={styles.chipCountText}>{b.count}</Text></View>
                        </View>
                      ))}
                    </View>
                  )}
                </Card>
                <Card style={{ flex: 1 }}>
                  <Text style={[type.overline, { marginBottom: spacing.sm }]}>Current stages</Text>
                  <View style={{ gap: 6 }}>
                    {workspace.stages.filter((s) => s.count > 0).length === 0 ? (
                      <Text style={type.caption}>No items in flight</Text>
                    ) : workspace.stages.filter((s) => s.count > 0).map((s) => {
                      const tone = STAGE_TONE[s.key as keyof typeof STAGE_TONE];
                      const pct = workspace.summary.total_items > 0 ? (s.count / workspace.summary.total_items) * 100 : 0;
                      return (
                        <View key={s.key} style={{ gap: 3 }}>
                          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                            <Text style={{ fontSize: 12.5, color: colors.onSurface, fontWeight: "600" }}>{s.label}</Text>
                            <Text style={{ fontSize: 12.5, color: colors.onSurfaceMuted }}>{s.count}</Text>
                          </View>
                          <View style={styles.barTrack}>
                            <View style={[styles.barFill, { width: `${Math.max(4, pct)}%`, backgroundColor: tone?.fg || colors.onSurfaceMuted }]} />
                          </View>
                        </View>
                      );
                    })}
                  </View>
                </Card>
              </View>

              {/* Products ordered */}
              <Card padding={0}>
                <View style={{ padding: spacing.lg, paddingBottom: spacing.sm, flexDirection: "row", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                  <Text style={type.overline}>Products ordered</Text>
                  <View style={{ flexDirection: "row", gap: 6 }}>
                    <FilterChip label={`All ${workspace.products.length}`} active={productFilter === "all"} onPress={() => setProductFilter("all")} />
                    <FilterChip label={`Outstanding ${workspace.outstanding_items.length}`} active={productFilter === "outstanding"} onPress={() => setProductFilter("outstanding")} />
                    <FilterChip label={`Delayed ${workspace.summary.blocked_count}`} active={productFilter === "blocked"} onPress={() => setProductFilter("blocked")} />
                  </View>
                </View>
                {visibleProducts.length === 0 ? (
                  <View style={{ padding: spacing.lg }}>
                    <Text style={type.caption}>No products in this filter.</Text>
                  </View>
                ) : visibleProducts.map((p, i) => (
                  <View
                    key={p.item_id}
                    style={{
                      flexDirection: "row", alignItems: "center", gap: 10, padding: spacing.md,
                      borderTopWidth: i > 0 ? StyleSheet.hairlineWidth : 0, borderTopColor: colors.divider,
                      backgroundColor: p.blocked ? "#FBEAEA" : "transparent",
                    }}
                  >
                    <Pressable onPress={() => router.push(`/(admin)/purchase-orders/${p.po_id}` as any)} style={{ flex: 1, flexDirection: "row", alignItems: "center", gap: 10, minWidth: 0 }}>
                      <ProductImage
                        source={p.image}
                        style={styles.prodThumb}
                        contentFit="cover"
                        disableSkeleton
                        fallbackLabel={p.sku}
                        borderRadius={6}
                      />
                      <View style={{ flex: 1, minWidth: 0 }}>
                        <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{p.name}</Text>
                        <Text style={type.caption} numberOfLines={1}>
                          {p.sku} · {p.brand_name || "—"}{p.supplier_name ? ` · via ${p.supplier_name}` : ""} · Qty {p.qty}
                        </Text>
                      </View>
                    </Pressable>
                    <View style={[styles.stagePillSm, { backgroundColor: STAGE_TONE[p.stage as keyof typeof STAGE_TONE]?.bg || colors.surfaceTertiary }]}>
                      <Text style={{ fontSize: 11, fontWeight: "600", color: STAGE_TONE[p.stage as keyof typeof STAGE_TONE]?.fg || colors.onSurfaceMuted }}>
                        {p.stage_label}
                      </Text>
                    </View>
                    <View style={{ flexDirection: "row", gap: 6 }}>
                      <Pressable testID={`ws-history-${p.item_id}`} onPress={() => setHistoryItemId(p.item_id)} style={styles.itemActionBtn} hitSlop={6}>
                        <Feather name="clock" size={12} color={colors.onSurface} />
                      </Pressable>
                      <Pressable testID={`ws-move-${p.item_id}`} onPress={() => setMoveItem(p)} style={styles.itemActionBtn} hitSlop={6}>
                        <Feather name="arrow-right" size={12} color={colors.onSurface} />
                      </Pressable>
                      <Pressable testID={`ws-transfer-${p.item_id}`} onPress={() => setTransferItem(p)} style={styles.itemActionBtn} hitSlop={6}>
                        <Feather name="repeat" size={12} color={colors.onSurface} />
                      </Pressable>
                    </View>
                  </View>
                ))}
              </Card>

              {/* Purchase Orders */}
              <Card padding={0}>
                <Text style={[type.overline, { padding: spacing.lg, paddingBottom: spacing.sm }]}>Purchase orders</Text>
                {workspace.purchase_orders.length === 0 ? (
                  <View style={{ padding: spacing.lg, paddingTop: 0 }}><Text style={type.caption}>None yet.</Text></View>
                ) : workspace.purchase_orders.map((p, i) => (
                  <Pressable
                    key={p.id}
                    onPress={() => router.push(`/(admin)/purchase-orders/${p.id}` as any)}
                    style={({ pressed, hovered }: any) => [
                      styles.listRow,
                      {
                        borderTopWidth: i > 0 ? StyleSheet.hairlineWidth : 0,
                        borderTopColor: colors.divider,
                        backgroundColor: pressed ? colors.surfaceTertiary : hovered ? colors.surfaceSubtle : "transparent",
                      },
                    ]}
                  >
                    <Text style={[type.mono, { width: 120 }]} numberOfLines={1}>{p.number}</Text>
                    <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
                      <Text style={type.titleSm} numberOfLines={1}>{p.brand_name || "—"} · {p.item_count} items</Text>
                      <Text style={type.caption}>{fmtDate(p.created_at)}{p.expected_delivery_at ? ` · ETA ${fmtDate(p.expected_delivery_at)}` : ""}</Text>
                    </View>
                    <Text style={[type.mono, { width: 110, textAlign: "right", fontWeight: "700" }]}>
                      {money(p.grand_total)}
                    </Text>
                    <StatusBadge status={p.status} />
                  </Pressable>
                ))}
              </Card>

              {/* Recent activity */}
              <Card>
                <Text style={[type.overline, { marginBottom: spacing.md }]}>Recent activity</Text>
                <ActivityTimeline events={workspace.recent_activity} dense emptyLabel="No activity yet" />
              </Card>
            </View>
          )
        ) : (
          <Card>
            <ActivityTimeline events={timeline} emptyLabel="Nothing yet" />
          </Card>
        )}
      </ScrollView>

      <MoveStageSheet
        visible={!!moveItem}
        item={moveItem ? toMovable(moveItem) : null}
        onClose={() => setMoveItem(null)}
        onMoved={async () => { await load(); }}
      />
      <TransferSheet
        visible={!!transferItem}
        item={transferItem ? toMovable(transferItem) : null}
        onClose={() => setTransferItem(null)}
        onSuccess={async () => { await load(); }}
      />
      <HistorySheet
        visible={!!historyItemId}
        itemId={historyItemId}
        onClose={() => setHistoryItemId(null)}
      />
    </SafeAreaView>
  );
}

function Row({ icon, text }: { icon: keyof typeof Feather.glyphMap; text: string }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
      <Feather name={icon} size={iconSize.sm} color={colors.onSurfaceMuted} />
      <Text style={[type.bodySm, { color: colors.onSurfaceSecondary }]} numberOfLines={1}>{text}</Text>
    </View>
  );
}

function FilterChip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={[
        styles.filterChip,
        active && { backgroundColor: colors.brand, borderColor: colors.brand },
      ]}
    >
      <Text style={{ fontSize: 11.5, fontWeight: "600", color: active ? colors.onBrand : colors.onSurfaceSecondary }}>
        {label}
      </Text>
    </Pressable>
  );
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  } catch { return "—"; }
}

const styles = StyleSheet.create({
  statsRow: { flexDirection: "row", gap: spacing.md },
  statsRowMobile: { flexWrap: "wrap" },
  listRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  deliveryIcon: {
    width: 34, height: 34, borderRadius: 17, backgroundColor: "#F3DFA3",
    alignItems: "center", justifyContent: "center",
  },
  chip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999,
    backgroundColor: colors.surfaceTertiary,
  },
  chipText: { fontSize: 12.5, fontWeight: "600", color: colors.onSurface },
  chipCount: {
    minWidth: 18, height: 18, borderRadius: 9, backgroundColor: colors.surface,
    alignItems: "center", justifyContent: "center", paddingHorizontal: 4,
  },
  chipCountText: { fontSize: 10.5, fontWeight: "700", color: colors.onSurfaceMuted },
  barTrack: { height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary, overflow: "hidden" },
  barFill: { height: 6, borderRadius: 3 },
  prodThumb: {
    width: 36, height: 36, borderRadius: 6, backgroundColor: colors.surfaceTertiary,
    alignItems: "center", justifyContent: "center", overflow: "hidden",
  },
  stagePillSm: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999 },
  itemActionBtn: {
    width: 28, height: 28, borderRadius: radius.sm, alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  filterChip: {
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  awaitingReorderPill: {
    alignSelf: "flex-start", marginTop: 6,
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999,
    backgroundColor: "#F5D5D5",
  },
});
