// frontend/app/(admin)/tiles/orders/index.tsx
// Ground Floor → Tiles → Tile Orders — four tabs matching how BuildCon
// staff actually think about this workflow (redesigned 2026-08, replacing
// the old Customer/Company/Dispatch List purchase-order-centric layout):
//   - Customer               — one row per CustomerOrder.
//   - Brands                 — one row per BRAND (Qutone, Dimore,
//     Kajaria…), not per dealer/supplier company. "I need to release
//     Kajaria" is a brand lookup, not a company lookup.
//   - Dispatch List          — the logistics queue.
//   - Material Movement Register — the permanent, chronological audit
//     trail of every box's journey (Order Created → Release → Move to
//     Godown → Dispatch from Released/Godown → Delivered).
//
// Every table on this screen is a <DataTable/>: a column declares its width
// and alignment once and both the header and the body cell read from that
// declaration, which is what stops labels drifting off their columns.
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import {
  tileOrdersApi,
  type BrandLandingCard,
  type CustomerOrderCard,
  type DispatchListRow,
  type MaterialMovementRow,
} from "@/src/api/tileOrders";
import { toast } from "@/src/components/Toast";
import { CreateDispatchSheet } from "@/src/components/tiles/CreateDispatchSheet";
import { DispatchRecordSheet, openChalanPdf } from "@/src/components/tiles/DispatchRecordSheet";
import {
  Button, ButtonGroup, FilterChip, PageHeader, PageShell,
  SearchField, Section, TabBar, Toolbar,
} from "@/src/components/tiles/TileLayout";
import { StatusPill } from "@/src/components/tiles/TileOrderStatusUI";
import {
  CellChevron, CellLink, CellMono, CellNumber, CellStack, CellText, CellTitle, DataTable,
  ProgressCell, type Column,
} from "@/src/components/tiles/TileTable";
import { Sheet } from "@/src/components/ui";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, spacing, type } from "@/src/theme/tokens";

type TabKey = "customer" | "brands" | "dispatch-list" | "material-register";

// These four label strings are pinned by scripts/verify-tile-orders-contract.mjs
// — they are the operator-facing vocabulary for the module and must not be
// abbreviated for layout reasons.
const TABS: [TabKey, string][] = [
  ["customer", "Customer"],
  ["brands", "Brands"],
  ["dispatch-list", "Dispatch List"],
  ["material-register", "Material Movement Register"],
];

// "At Godown" and "Delivered" became reachable once the Dispatch record
// sheet exposed Mark received at Godown / Mark Delivered — until then
// nothing ever set godown_received_at or delivered_at, so both chips would
// have been permanently dead options.
const DISPATCH_STATUS_FILTERS = ["All", "Dispatched", "At Godown", "Delivered"] as const;

const MOVEMENT_LABEL: Record<string, string> = {
  order_created: "Order Created",
  release: "Release",
  move_to_godown: "Move to Godown",
  dispatch_from_released: "Dispatch from Released",
  dispatch_from_godown: "Dispatch from Godown",
  delivered: "Delivered",
};

function dispatchRowKey(row: DispatchListRow, index: number) {
  // A Dispatch/Chalan may legitimately contain multiple lines with the
  // same product name, so the render index is required as a final stable
  // per-response discriminator.
  return `${row.dispatch_id}-${row.chalan_id}-${row.tile_name}-${index}`;
}

function timestamp(value: string | undefined | null) {
  return value ? value.slice(0, 16).replace("T", " ") : "—";
}

export default function TileOrdersScreen() {
  useRequireFloorAccess("ground-floor");
  const router = useRouter();
  // Deep-link params let the Customer workspace jump straight here with the
  // right tab already selected and pre-filtered to that order — "View
  // Register"/"View Dispatches" on a customer order are navigations INTO
  // this screen, not separate screens.
  const params = useLocalSearchParams<{ tab?: string; search?: string }>();
  const initialTab = (TABS.find(([key]) => key === params.tab)?.[0] as TabKey | undefined) ?? "customer";

  const [tab, setTab] = useState<TabKey>(initialTab);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [customerOrders, setCustomerOrders] = useState<CustomerOrderCard[]>([]);
  const [brands, setBrands] = useState<BrandLandingCard[]>([]);
  const [movements, setMovements] = useState<MaterialMovementRow[]>([]);
  const [movementSearch, setMovementSearch] = useState(params.search ?? "");
  const [selectedMovement, setSelectedMovement] = useState<MaterialMovementRow | null>(null);
  const [dispatchRows, setDispatchRows] = useState<DispatchListRow[]>([]);
  const [dispatchSearch, setDispatchSearch] = useState(params.search ?? "");
  const [dispatchStatus, setDispatchStatus] = useState<typeof DISPATCH_STATUS_FILTERS[number]>("All");
  const [openDispatchId, setOpenDispatchId] = useState<string | null>(null);
  const [creatingDispatch, setCreatingDispatch] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      if (tab === "customer") {
        setCustomerOrders((await tileOrdersApi.listCustomerOrders({ page_size: 30 })).orders);
      } else if (tab === "brands") {
        setBrands((await tileOrdersApi.listBrands()).brands);
      } else if (tab === "dispatch-list") {
        setDispatchRows((await tileOrdersApi.listDispatchList({
          search: dispatchSearch || undefined,
          status: dispatchStatus === "All" ? undefined : dispatchStatus,
          page_size: 100,
        })).rows);
      } else {
        setMovements((await tileOrdersApi.listMovements({
          search: movementSearch || undefined,
          page_size: 100,
        })).rows);
      }
    } catch (e: any) {
      const message = e?.detail || "Could not load orders";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [tab, movementSearch, dispatchSearch, dispatchStatus]);

  useEffect(() => { load(); }, [load]);

  const openCustomerOrder = (id: string) => router.push(`/(admin)/tiles/orders/${id}` as any);
  const openBrand = (brandId: string | null) =>
    router.push(`/(admin)/tiles/orders/brands/${brandId || "unassigned"}` as any);

  // ── Column definitions ────────────────────────────────────────────────────
  // Names and descriptions `grow` so a wide monitor is filled by the columns
  // that benefit from width; counters, statuses and action clusters stay at a
  // fixed width so they line up vertically no matter the viewport.

  // Widths are chosen so the whole row fits the content area of a 1512px
  // window beside the 240px app sidebar (≈1208px) without horizontal
  // scrolling — this is the module's landing table and an operator should
  // never have to scroll sideways to see an order's status. Wider monitors
  // spend the surplus on the two `grow` columns.
  const customerColumns = useMemo<Column<CustomerOrderCard>[]>(() => [
    {
      key: "customer", label: "CUSTOMER", grow: 2, minWidth: 200,
      render: (order) => <CellTitle>{order.customer_name}</CellTitle>,
    },
    {
      // An order number is an identifier an operator reads aloud and types
      // into a search box — it gets the width to render in full
      // ("TORD-2026-0003"), where a customer name may ellipsize.
      key: "number", label: "ORDER NO.", width: 164,
      render: (order) => <CellMono>{order.number}</CellMono>,
    },
    {
      key: "brands", label: "BRANDS", grow: 2, minWidth: 160,
      render: (order) => <CellText muted>{order.brands.map((b) => b.brand_name).join(", ") || "—"}</CellText>,
    },
    {
      // 110 is the floor for this column: it is set by the header word
      // "PRODUCTS", not by the one- or two-digit count underneath it.
      key: "products", label: "PRODUCTS", width: 110, align: "right",
      render: (order) => <CellNumber value={order.total_products} />,
    },
    {
      key: "boxes", label: "BOXES", width: 84, align: "right",
      render: (order) => <CellNumber value={order.total_boxes} />,
    },
    {
      // 180px is the narrowest this column can be before the longest pill
      // ("Partially Dispatched") starts to truncate.
      key: "status", label: "STATUS", width: 180, align: "center",
      render: (order) => <StatusPill status={order.overall_status} />,
    },
    {
      key: "waiting", label: "WAITING", width: 90, align: "right",
      render: (order) => <CellNumber value={`${order.waiting_days}d`} dim />,
    },
    {
      key: "progress", label: "PROGRESS", width: 150,
      render: (order) => <ProgressCell percent={order.completion_percentage} />,
    },
    {
      // The row itself is the affordance; this is just the visual cue that
      // says so, so it stays as narrow as a chevron needs to be.
      key: "action", label: "", width: 56, align: "right",
      render: () => <CellChevron />,
    },
  ], []);

  const brandColumns = useMemo<Column<BrandLandingCard>[]>(() => [
    {
      key: "brand", label: "BRAND", grow: 3, minWidth: 260,
      render: (brand) => <CellTitle>{brand.brand_name}</CellTitle>,
    },
    {
      key: "orders", label: "ACTIVE ORDERS", width: 160, align: "right",
      render: (brand) => <CellNumber value={brand.active_orders} />,
    },
    {
      key: "wait", label: "OLDEST WAIT", width: 160, align: "right",
      render: (brand) => (
        <CellNumber value={brand.max_supplier_silent_days ? `${brand.max_supplier_silent_days}d` : "—"} dim />
      ),
    },
    {
      key: "action", label: "", width: 180, align: "right",
      render: () => <CellLink>Release queue →</CellLink>,
    },
  ], []);

  const dispatchColumns = useMemo<Column<DispatchListRow>[]>(() => [
    {
      // Number over date, rather than a separate CREATED column. A dispatch's
      // date is an attribute of the dispatch, not an independent axis to scan,
      // and folding it here buys ~110px back for a table that must otherwise
      // scroll to reach its own data.
      key: "number", label: "DISPATCH NO.", width: 176,
      render: (row) => (
        <CellStack title={row.dispatch_number} subtitle={row.dispatch_date?.slice(0, 10) || "—"} />
      ),
    },
    {
      key: "customer", label: "CUSTOMER", grow: 2, minWidth: 180,
      render: (row) => <CellTitle>{row.customer_name}</CellTitle>,
    },
    {
      key: "product", label: "BRAND / PRODUCT", grow: 3, minWidth: 220,
      render: (row) => <CellStack title={row.tile_name} subtitle={row.brand_name} />,
    },
    {
      key: "boxes", label: "BOXES", width: 88, align: "right",
      render: (row) => <CellNumber value={row.boxes} />,
    },
    {
      // Was two columns, SOURCE and DESTINATION — but a dispatch on this list
      // always terminates at the customer, so DESTINATION rendered the literal
      // word "Customer" on every row of every page. One route column carries
      // the same information and gives ~80px back to the columns that vary.
      // Fits "Released → Customer", the longer of the two possible routes.
      key: "route", label: "ROUTE", width: 180,
      render: (row) => <CellText muted>{row.source} → Customer</CellText>,
    },
    {
      key: "vehicle", label: "VEHICLE / DRIVER", grow: 1, minWidth: 190,
      render: (row) => (
        <CellStack title={row.vehicle_number || "—"} subtitle={row.driver_name || "Driver not recorded"} />
      ),
    },
    {
      key: "status", label: "STATUS", width: 144, align: "center",
      render: (row) => (
        <View style={styles.plainStatus}>
          <Text numberOfLines={1} style={styles.plainStatusText}>{row.status}</Text>
        </View>
      ),
    },
    {
      // Wide enough to hold all four full-length labels on one line — the
      // contract fixes the wording, so the column is sized to the words
      // rather than the words trimmed to fit the column.
      key: "actions", label: "ACTIONS", width: 468,
      render: (row) => (
        <ButtonGroup>
          <Button
            label="View Dispatch" size="sm" variant="primary"
            testID={`tile-orders-open-dispatch-${row.dispatch_id}`}
            onPress={() => setOpenDispatchId(row.dispatch_id)}
          />
          <Button
            label="View Chalan" size="sm"
            testID={`tile-orders-view-chalan-${row.chalan_id}`}
            onPress={() => openChalanPdf(row.chalan_id)}
          />
          <Button
            label="Print Chalan" size="sm"
            testID={`tile-orders-print-chalan-${row.chalan_id}`}
            onPress={() => openChalanPdf(row.chalan_id, "print")}
          />
          {row.customer_order_id ? (
            <Button
              label="Order" size="sm"
              testID={`tile-orders-dispatch-order-${row.dispatch_id}`}
              onPress={() => router.push(`/(admin)/tiles/orders/${row.customer_order_id}` as any)}
            />
          ) : null}
        </ButtonGroup>
      ),
    },
  ], [router]);

  const movementColumns = useMemo<Column<MaterialMovementRow>[]>(() => [
    {
      key: "time", label: "TIMESTAMP", width: 164,
      render: (row) => <CellMono>{timestamp(row.created_at)}</CellMono>,
    },
    {
      key: "customer", label: "CUSTOMER", grow: 2, minWidth: 170,
      render: (row) => <CellTitle>{row.customer_name}</CellTitle>,
    },
    {
      key: "product", label: "BRAND / PRODUCT", grow: 3, minWidth: 220,
      render: (row) => <CellStack title={row.tile_name} subtitle={row.brand_name} />,
    },
    {
      // Sized to render the longest movement label, "Dispatch from Released",
      // in full. Movement names are a closed vocabulary, so unlike a customer
      // or product name they must never ellipsize.
      key: "movement", label: "MOVEMENT", width: 192,
      render: (row) => <CellText>{MOVEMENT_LABEL[row.movement_type] || row.movement_type}</CellText>,
    },
    {
      key: "qty", label: "QTY", width: 96, align: "right",
      render: (row) => <CellNumber value={row.boxes} />,
    },
    {
      // FROM is always a short location word ("Released", "Godown"); TO is
      // usually a customer name, so only TO needs room to grow. Fixing both at
      // 132 truncated every delivery destination by ~77px.
      key: "from", label: "FROM", width: 128,
      render: (row) => <CellText muted>{row.source || "—"}</CellText>,
    },
    {
      key: "to", label: "TO", grow: 1, minWidth: 200,
      render: (row) => <CellText muted>{row.destination || "—"}</CellText>,
    },
    {
      key: "reference", label: "REFERENCE", width: 168,
      render: (row) => <CellMono>{row.chalan_number || row.dispatch_number || "—"}</CellMono>,
    },
    {
      key: "user", label: "USER", grow: 1, minWidth: 156,
      render: (row) => <CellText muted>{row.performed_by_name}</CellText>,
    },
    {
      key: "action", label: "", width: 108, align: "right",
      render: () => <CellLink>Open →</CellLink>,
    },
  ], []);

  const renderBody = () => {
    if (loading) {
      return (
        <View style={styles.stateBlock}>
          <ActivityIndicator color={colors.brand} />
        </View>
      );
    }

    if (loadError) {
      return (
        <View style={styles.stateBlock}>
          <Text style={type.titleSm}>{loadError}</Text>
          <Button label="Retry" variant="primary" testID="tile-orders-retry" onPress={() => load()} />
        </View>
      );
    }

    if (tab === "customer") {
      return (
        <DataTable
          testID="tile-orders-customer-table"
          fillViewport
          columns={customerColumns}
          data={customerOrders}
          rowMinHeight={60}
          keyExtractor={(order) => order.id}
          rowTestID={(order) => `tile-orders-customer-${order.id}`}
          onRowPress={(order) => openCustomerOrder(order.id)}
          emptyMessage="No tile orders yet."
        />
      );
    }

    if (tab === "brands") {
      return (
        <DataTable
          testID="tile-orders-brands-table"
          fillViewport
          columns={brandColumns}
          data={brands}
          rowMinHeight={60}
          keyExtractor={(brand) => brand.brand_id || "unassigned"}
          rowTestID={(brand) => `tile-orders-brand-${brand.brand_id || "unassigned"}`}
          onRowPress={(brand) => openBrand(brand.brand_id)}
          emptyMessage="No brands with active orders yet."
        />
      );
    }

    if (tab === "dispatch-list") {
      return (
        <DataTable
          testID="tile-orders-dispatch-table"
          fillViewport
          columns={dispatchColumns}
          data={dispatchRows}
          rowMinHeight={64}
          keyExtractor={dispatchRowKey}
          emptyMessage="No dispatches match this filter. Use “Create dispatch” above to raise one."
        />
      );
    }

    return (
      <DataTable
        testID="tile-orders-movement-table"
        fillViewport
        columns={movementColumns}
        data={movements}
        rowMinHeight={56}
        keyExtractor={(row) => row.id}
        rowTestID={(row) => `tile-orders-movement-${row.id}`}
        onRowPress={(row) => setSelectedMovement(row)}
        emptyMessage="No material movements recorded yet."
      />
    );
  };

  return (
    <>
      <PageShell testID="tile-orders-screen">
        <PageHeader
          eyebrow="GROUND FLOOR · TILES"
          title="Tile Orders"
          subtitle="Operations queue — release, dispatch and audit in one workspace."
        />

        {/* No WorkflowRail here. On a detail screen the rail answers "where is
            THIS order", which is worth its height. On this screen it was
            hardcoded to `active="quotation"` — the same eight static dots on
            every visit, for a list whose rows are each at a different stage —
            so it cost ~130px above the fold and told an operator nothing.
            Restore with <WorkflowRail active=… /> if a real stage is ever
            derivable for the list as a whole. */}
        <Section>
          <TabBar tabs={TABS} value={tab} onChange={setTab} testIDPrefix="tile-orders-tab" />
        </Section>

        <Section testID="tile-orders-body">
          {tab === "dispatch-list" ? (
            <Toolbar
              search={
                <SearchField
                  testID="tile-orders-dispatch-search"
                  value={dispatchSearch}
                  onChangeText={setDispatchSearch}
                  onSubmit={() => load()}
                  placeholder="Search customer, brand, product, dispatch, chalan…"
                />
              }
              filters={DISPATCH_STATUS_FILTERS.map((status) => (
                <FilterChip
                  key={status}
                  label={status}
                  active={dispatchStatus === status}
                  testID={`tile-orders-dispatch-status-${status.toLowerCase().replaceAll(" ", "-")}`}
                  onPress={() => setDispatchStatus(status)}
                />
              ))}
              actions={
                <Button
                  label="Create dispatch"
                  variant="primary"
                  testID="tile-orders-create-dispatch"
                  onPress={() => setCreatingDispatch(true)}
                />
              }
            />
          ) : null}

          {tab === "material-register" ? (
            <Toolbar
              search={
                <SearchField
                  testID="tile-orders-movement-search"
                  value={movementSearch}
                  onChangeText={setMovementSearch}
                  onSubmit={() => load()}
                  placeholder="Search customer, brand, tile, chalan, dispatch…"
                />
              }
            />
          ) : null}

          {renderBody()}
        </Section>
      </PageShell>

      {openDispatchId ? (
        <DispatchRecordSheet
          dispatchId={openDispatchId}
          onClose={() => setOpenDispatchId(null)}
          onChanged={() => load()}
        />
      ) : null}

      {creatingDispatch ? (
        <CreateDispatchSheet onClose={() => setCreatingDispatch(false)} onCreated={() => load()} />
      ) : null}

      {/* Material Movement Register — every row opens the record behind it,
          with a link to each thing that row touched: the Chalan PDF, the
          Dispatch record, and the customer order/timeline it belongs to. */}
      <Sheet
        visible={selectedMovement !== null}
        onClose={() => setSelectedMovement(null)}
        title={selectedMovement ? MOVEMENT_LABEL[selectedMovement.movement_type] || selectedMovement.movement_type : "Movement"}
        subtitle={selectedMovement ? `${timestamp(selectedMovement.created_at)} · ${selectedMovement.performed_by_name}` : undefined}
        testID="tile-orders-movement-sheet"
      >
        {selectedMovement ? (
          <View style={styles.sheetBody}>
            <View style={styles.sheetFacts}>
              <SheetFact label="Customer" value={selectedMovement.customer_name} />
              <SheetFact label="Product" value={`${selectedMovement.brand_name} · ${selectedMovement.tile_name}`} />
              <SheetFact label="Quantity" value={`${selectedMovement.boxes} boxes`} />
              <SheetFact
                label="Route"
                value={`${selectedMovement.source || "—"} → ${selectedMovement.destination || "—"}`}
              />
              <SheetFact
                label="Reference"
                value={
                  [
                    selectedMovement.dispatch_number && `Dispatch ${selectedMovement.dispatch_number}`,
                    selectedMovement.chalan_number && `Chalan ${selectedMovement.chalan_number}`,
                  ].filter(Boolean).join(" · ") || "No dispatch or chalan attached"
                }
              />
            </View>

            <ButtonGroup>
              {selectedMovement.chalan_id ? (
                <Button
                  label="View Chalan" variant="primary"
                  testID="tile-orders-movement-chalan"
                  onPress={() => openChalanPdf(selectedMovement.chalan_id!)}
                />
              ) : null}
              {selectedMovement.dispatch_id ? (
                <Button
                  label="Open dispatch"
                  testID="tile-orders-movement-dispatch"
                  onPress={() => { setOpenDispatchId(selectedMovement.dispatch_id); setSelectedMovement(null); }}
                />
              ) : null}
              {selectedMovement.customer_order_id ? (
                <Button
                  label="Open customer order"
                  testID="tile-orders-movement-order"
                  onPress={() => {
                    const id = selectedMovement.customer_order_id!;
                    setSelectedMovement(null);
                    openCustomerOrder(id);
                  }}
                />
              ) : null}
              {selectedMovement.customer_order_id ? (
                <Button
                  label="Open timeline"
                  testID="tile-orders-movement-timeline"
                  onPress={() => {
                    const id = selectedMovement.customer_order_id!;
                    setSelectedMovement(null);
                    router.push(`/(admin)/tiles/orders/${id}?timeline=1` as any);
                  }}
                />
              ) : null}
            </ButtonGroup>
          </View>
        ) : null}
      </Sheet>
    </>
  );
}

function SheetFact({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.fact}>
      <Text style={styles.factLabel}>{label}</Text>
      <Text style={type.body}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  stateBlock: { paddingVertical: spacing.s48, alignItems: "center", gap: spacing.lg },
  // The Dispatch List's status is a free-text backend string rather than one
  // of the StatusPill ladder values, so it gets a neutral chip of the same
  // height as a pill instead of pretending to be one.
  plainStatus: {
    height: 24,
    justifyContent: "center",
    paddingHorizontal: 10,
    borderRadius: 999,
    backgroundColor: colors.surfaceTertiary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  plainStatusText: { ...type.captionStrong, fontSize: 12 },
  sheetBody: { padding: spacing.s24, gap: spacing.s24 },
  sheetFacts: { gap: spacing.lg },
  fact: { gap: spacing.s4 },
  factLabel: { ...type.overline, color: colors.onSurfaceMuted },
});
