import { Redirect, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Text, View } from "react-native";

import { executiveApi, type Overview } from "@/src/api/executive";
import {
  salesDataApi,
  type BestSellingProductRow,
  type BrandRevenueRow,
  type CustomerRevenueRow,
  type RecentOrderRow,
  type ReferrerSummaryRow,
  type SalesFilter,
} from "@/src/api/salesData";
import { AdminPage } from "@/src/components/AdminPage";
import { FLOOR_LABEL, SalesFilters } from "@/src/components/salesData/SalesFilters";
import { SalesSection } from "@/src/components/salesData/SalesSection";
import { useSalesPeriod } from "@/src/components/salesData/useSalesPeriod";
import {
  Alert, Badge, Button, Card, ErrorState, KpiCard, SkeletonList,
  Table, TableCell, TableHeader, TableRow,
} from "@/src/components/ui";
import { useBp } from "@/src/design/responsive";
import { fmtMoney, fmtMoneyCompact } from "@/src/design/tokens";
import { getSelectedFloorId, useFloorAccess } from "@/src/hooks/use-floor-access";
import { useAuth } from "@/src/state/auth";
import { colors, layout, spacing, type } from "@/src/theme/tokens";
import { downloadApiFile } from "@/src/utils/downloadFile";

const ANALYTICS_ROLES = ["owner", "admin", "manager"];
const TOP_N = 10;

/**
 * Money inside a table cell.
 *
 * A full ₹25,26,885 does not fit the revenue column at 375px — it truncated
 * to "₹25,26,…", which is worse than a rounded figure because the reader
 * cannot tell the magnitude at all. Phones get the compact form the KPI
 * cards already use; every wider breakpoint keeps the exact rupee value.
 *
 * A hook rather than a prop so every table on the page — including the two
 * referrer workspaces below — formats money identically without threading a
 * formatter through each one.
 */
function useCellMoney() {
  const { isPhone } = useBp();
  return (value: number) => (isPhone ? fmtMoneyCompact(value) : `₹${fmtMoney(value)}`);
}

function shortDate(iso: string | null): string {
  if (!iso) return "—";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
}

type Sections = {
  brands: BrandRevenueRow[] | null;
  customers: CustomerRevenueRow[] | null;
  products: BestSellingProductRow[] | null;
  orders: RecentOrderRow[] | null;
  architects: ReferrerSummaryRow[] | null;
  designers: ReferrerSummaryRow[] | null;
};

const EMPTY_SECTIONS: Sections = {
  brands: null, customers: null, products: null, orders: null, architects: null, designers: null,
};

/**
 * Sales Data — the launch dashboard (Milestone 4), and the permanent entry
 * point for the module.
 *
 * This is Phase 1 of the Sales Data architecture, not a replacement for it.
 * Every figure comes from the Phase 0 analytics layer: the KPI row and
 * Revenue by Floor from `/analytics/overview`, the Referred By workspaces
 * from `/analytics/referrers` unchanged, and the four breakdowns from
 * `/analytics/*` endpoints shaped as standalone filterable resources so the
 * Products, Brands and Customers workspaces on the roadmap extend them
 * rather than replacing them.
 *
 * The one rule the page holds: **nothing on this screen is computed here.**
 * Every total, average and rank is derived by the backend from one canonical
 * definition, so no two blocks can disagree about the same book. The
 * breakdowns all reconcile to the Total Revenue card by construction —
 * verified live at ₹39,77,337 across brand, customer, product and order
 * sums.
 */
export default function SalesDataIndex() {
  const { staff } = useAuth();
  const { floors } = useFloorAccess();
  const cellMoney = useCellMoney();
  const { isPhone } = useBp();
  const router = useRouter();

  // The KPI row used to give each card its own minWidth (160 / 140 / 180),
  // which wrapped into a ragged 2-then-1 block at narrow widths — two
  // half-width cards above one full-width one. Every card now carries the
  // identical rule, so the row is a clean 3-up band from tablet upwards and a
  // clean single stack on a phone, with no in-between state where the cards
  // are different sizes.
  const kpiGap = spacing.md;
  const kpiCardStyle = isPhone
    ? { width: "100%" as const }
    : { flex: 1, minWidth: 200, flexBasis: 0 };

  // Matches SalesSection, so the one hand-rolled Card on this page breathes
  // exactly like the six that go through the shared section component.
  const sectionPadding = isPhone ? layout.cardPadding.base : layout.cardPadding.spacious;

  const [floorId, setFloorId] = useState("");
  useEffect(() => {
    if (floorId) return;
    void getSelectedFloorId().then((id) => setFloorId(id || "all"));
  }, [floorId]);

  const { period, origin, serverDefault, choose, jumpToLatest } = useSalesPeriod(floorId);

  const [overview, setOverview] = useState<Overview | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [sections, setSections] = useState<Sections>(EMPTY_SECTIONS);
  const [sectionError, setSectionError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!floorId || !period) return; // never query before the scope is known
    const filter: SalesFilter = {
      floorId,
      preset: period.preset,
      dateFrom: period.dateFrom,
      dateTo: period.dateTo,
    };
    const executiveQuery = {
      floorId: floorId === "all" ? undefined : floorId,
      preset: period.preset,
      dateFrom: period.preset === "custom" ? period.dateFrom || undefined : undefined,
      dateTo: period.preset === "custom" ? period.dateTo || undefined : undefined,
    };

    setOverviewError(null);
    setOverview(null);
    setSections(EMPTY_SECTIONS);
    setSectionError(null);

    executiveApi.overview(executiveQuery)
      .then(setOverview)
      .catch((e: any) => setOverviewError(e?.detail || "Could not load the sales summary"));

    Promise.all([
      salesDataApi.revenueByBrand(filter),
      salesDataApi.revenueByCustomer(filter),
      salesDataApi.bestSellingProducts(filter, TOP_N),
      salesDataApi.recentOrders(filter, TOP_N),
      salesDataApi.referrers(filter, "architect"),
      salesDataApi.referrers(filter, "interior_designer"),
    ])
      .then(([brands, customers, products, orders, architects, designers]) => {
        setSections({
          brands: brands.rows,
          customers: customers.rows,
          products: products.rows,
          orders: orders.rows,
          architects: architects.rows,
          designers: designers.rows,
        });
      })
      .catch((e: any) => setSectionError(e?.detail || "Could not load the sales breakdowns"));
  }, [floorId, period]);

  useEffect(() => { load(); }, [load]);

  const exportSalesData = useCallback(() => {
    if (!floorId || !period) return;
    const filter: SalesFilter = {
      floorId,
      preset: period.preset,
      dateFrom: period.dateFrom,
      dateTo: period.dateTo,
    };
    void downloadApiFile(
      salesDataApi.salesExportPath(filter),
      "sales-data.xlsx",
      "sales data Excel file",
      floorId === "all" ? undefined : floorId,
    );
  }, [floorId, period]);

  // The role check is a plain `if` AFTER every hook call — an early return
  // before a hook would change this component's hook count between renders.
  if (staff && !ANALYTICS_ROLES.includes(staff.role)) {
    return <Redirect href="/(admin)/dashboard" />;
  }

  const kpis = overview?.kpis;

  /** The unit's own name, preferring what the owner configured. FLOOR_LABEL
   *  carries the two trading names the business uses day to day; anything
   *  else (a third unit) falls back to its configured name rather than
   *  rendering the raw `second-floor` slug. */
  const floorName = (id: string) =>
    FLOOR_LABEL[id] || floors.find((f) => f.id === id)?.name || id;

  const visibleFloorRevenue = (overview?.revenue_by_floor || []).filter(
    (row) => floorId === "all" || row.floor_id === floorId,
  );

  const isEmptyPeriod = !!kpis && kpis.orders === 0;
  // Only offer the jump when the server actually knows of a period that has
  // orders in it, and it is not the one already on screen.
  const canJumpToLatest =
    isEmptyPeriod && !!serverDefault?.latest_order_at && serverDefault.date_from !== period?.dateFrom;

  return (
    <AdminPage
      title="Sales Data"
      subtitle={`Confirmed orders only${period ? ` · ${period.label}` : ""}`}
    >
      {period ? (
        <View style={{ gap: spacing.md }}>
          <SalesFilters
            floors={floors}
            floorId={floorId}
            onFloorChange={setFloorId}
            period={period}
            onPeriodChange={choose}
          />
          <View style={{ flexDirection: "row", justifyContent: "flex-end" }}>
            <Button
              testID="sales-data-export-xlsx"
              label="Export Excel"
              icon="download"
              variant="secondary"
              onPress={exportSalesData}
            />
          </View>
        </View>
      ) : null}

      {origin === "fallback" ? (
        <Alert
          tone="info"
          title="No orders yet this month"
          description={`Showing the most recent available sales period — ${period?.label}.`}
        />
      ) : null}

      {canJumpToLatest ? (
        <Alert
          tone="info"
          title="No confirmed orders in this period"
          description={`The most recent orders are in ${serverDefault?.label}.`}
          action={<Button label={`Show ${serverDefault?.label}`} variant="secondary" onPress={jumpToLatest} />}
        />
      ) : null}

      {/* ---------------------------------------------------------------
          1-3. Total Revenue · Total Orders · Outstanding Payments
          --------------------------------------------------------------- */}
      {overviewError ? <ErrorState subtitle={overviewError} onRetry={load} /> : null}
      {!overviewError && !kpis ? <SkeletonList rows={2} /> : null}
      {kpis ? (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: kpiGap }} testID="sales-data-kpis">
          <KpiCard
            testID="sales-kpi-revenue"
            label="Total Revenue"
            value={fmtMoneyCompact(kpis.revenue)}
            question="What did we sell this period?"
            style={kpiCardStyle}
          />
          <KpiCard
            testID="sales-kpi-orders"
            label="Total Orders"
            value={String(kpis.orders)}
            question="How many deals did we close?"
            style={kpiCardStyle}
          />
          <KpiCard
            testID="sales-kpi-outstanding"
            label="Outstanding Payments"
            value={fmtMoneyCompact(kpis.outstanding.outstanding)}
            question="How much money is still owed to us?"
            tone={kpis.outstanding.outstanding > 0 ? "warning" : "neutral"}
            onPress={() => router.push("/(admin)/payments" as never)}
            style={kpiCardStyle}
          />
        </View>
      ) : null}

      {/* ---------------------------------------------------------------
          4. Revenue by Floor
          --------------------------------------------------------------- */}
      {overview ? (
        <Card testID="sales-revenue-by-floor" variant="flat" padding={sectionPadding}>
          <View style={{ gap: spacing.lg }}>
            <View style={{ gap: spacing.s4 }}>
              <Text style={type.titleMd}>Revenue by Business Unit</Text>
              <Text style={[type.caption, { color: colors.onSurfaceMuted }]}>
                {floorId === "all" ? "Which unit is winning?" : "This unit's share of the book"}
              </Text>
            </View>
            {/* `/analytics/overview` always reports every accessible floor
                here, regardless of the floor filter — it is built as a
                cross-unit comparison. Rendering that unfiltered under a
                single-unit KPI row made the page contradict itself: Total
                Revenue showed one unit while the breakdown below it summed
                to the whole company. Scoping the rows to the active filter
                is what keeps the two halves of the card telling one story. */}
            {visibleFloorRevenue.map((row) => (
              <View
                key={row.floor_id}
                testID={`sales-floor-row-${row.floor_id}`}
                style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: spacing.md }}
              >
                <Text style={type.body}>{floorName(row.floor_id)}</Text>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={[type.bodyStrong, { fontVariant: ["tabular-nums"] }]}>
                    {fmtMoneyCompact(row.revenue)}
                  </Text>
                  <Text style={[type.caption, { color: colors.onSurfaceMuted }]}>
                    {row.orders} {row.orders === 1 ? "order" : "orders"}
                  </Text>
                </View>
              </View>
            ))}
          </View>
        </Card>
      ) : null}

      {/* ---------------------------------------------------------------
          5. Revenue by Brand
          --------------------------------------------------------------- */}
      <SalesSection
        testID="sales-revenue-by-brand"
        title="Revenue by Brand"
        question="Which brands are actually selling?"
        rows={sections.brands}
        error={sectionError}
        onRetry={load}
        emptyTitle="No brand revenue in this period"
      >
        {(rows) => (
          <Table>
            <TableHeader columns={[{ label: "Brand", flex: 2 }, { label: "Qty", align: "right" }, { label: "Revenue", align: "right" }]} />
            {rows.map((row, i) => (
              <TableRow key={row.brand_id} isLast={i === rows.length - 1} testID={`sales-brand-row-${row.brand_id}`}>
                <TableCell flex={2}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flexShrink: 1 }}>
                    <Text numberOfLines={1} style={[type.bodySm, { flexShrink: 1 }]}>{row.name}</Text>
                    {/* Not a brand — revenue from products whose catalog doc
                        is gone. Labelled rather than dropped so this column
                        still totals to the Total Revenue card above. */}
                    {row.is_unlinked ? <Badge label="Unmatched" tone="warning" /> : null}
                  </View>
                </TableCell>
                <TableCell align="right">{String(row.quantity)}</TableCell>
                <TableCell align="right">{cellMoney(row.revenue)}</TableCell>
              </TableRow>
            ))}
          </Table>
        )}
      </SalesSection>

      {/* ---------------------------------------------------------------
          6. Revenue by Customer
          --------------------------------------------------------------- */}
      <SalesSection
        testID="sales-revenue-by-customer"
        title="Revenue by Customer"
        question="Who is buying the most?"
        rows={sections.customers}
        error={sectionError}
        onRetry={load}
        emptyTitle="No customer revenue in this period"
        footer={
          sections.customers && sections.customers.length > TOP_N ? (
            <Text style={[type.caption, { color: colors.onSurfaceMuted }]}>
              Showing the top {TOP_N} of {sections.customers.length} customers.
            </Text>
          ) : null
        }
      >
        {(rows) => (
          <Table>
            <TableHeader columns={[{ label: "Customer", flex: 2 }, { label: "Orders", align: "right" }, { label: "Revenue", align: "right" }]} />
            {rows.slice(0, TOP_N).map((row, i, shown) => (
              <TableRow
                key={row.customer_id || row.name}
                isLast={i === shown.length - 1}
                testID={`sales-customer-row-${row.customer_id}`}
                onPress={row.customer_id ? () => router.push(`/(admin)/customers/${row.customer_id}` as never) : undefined}
              >
                <TableCell flex={2}>{row.name}</TableCell>
                <TableCell align="right">{String(row.orders)}</TableCell>
                <TableCell align="right">{cellMoney(row.revenue)}</TableCell>
              </TableRow>
            ))}
          </Table>
        )}
      </SalesSection>

      {/* ---------------------------------------------------------------
          7. Referred By — two separate workspaces, from the quotation's own
          "Referred By" field. Never fabricated: an empty book renders an
          empty state, not a zero row.
          --------------------------------------------------------------- */}
      <ReferrerWorkspace
        testID="sales-referrals-architects"
        title="Referred By — Architects"
        rows={sections.architects}
        error={sectionError}
        onRetry={load}
        onOpen={(id) => router.push(`/(admin)/sales-data/referrer/${id}` as never)}
      />
      <ReferrerWorkspace
        testID="sales-referrals-designers"
        title="Referred By — Interior Designers"
        rows={sections.designers}
        error={sectionError}
        onRetry={load}
        onOpen={(id) => router.push(`/(admin)/sales-data/referrer/${id}` as never)}
      />

      {/* ---------------------------------------------------------------
          8. Best Selling Products
          --------------------------------------------------------------- */}
      <SalesSection
        testID="sales-best-selling-products"
        title="Best Selling Products"
        question="What is moving off the shelves?"
        rows={sections.products}
        error={sectionError}
        onRetry={load}
        emptyTitle="No products sold in this period"
      >
        {(rows) => (
          <Table>
            <TableHeader columns={[{ label: "Product", flex: 3 }, { label: "Qty", align: "right" }, { label: "Revenue", align: "right" }]} />
            {rows.map((row, i) => (
              <TableRow key={row.product_id} isLast={i === rows.length - 1} testID={`sales-product-row-${row.product_id}`}>
                <TableCell flex={3}>
                  <View style={{ gap: 1, flexShrink: 1 }}>
                    <Text numberOfLines={1} style={type.bodySm}>{row.name}</Text>
                    {row.brand_name ? (
                      <Text numberOfLines={1} style={[type.caption, { color: colors.onSurfaceMuted }]}>
                        {row.brand_name}
                      </Text>
                    ) : null}
                  </View>
                </TableCell>
                <TableCell align="right">{String(row.quantity)}</TableCell>
                <TableCell align="right">{cellMoney(row.revenue)}</TableCell>
              </TableRow>
            ))}
          </Table>
        )}
      </SalesSection>

      {/* ---------------------------------------------------------------
          9. Recent Orders
          --------------------------------------------------------------- */}
      <SalesSection
        testID="sales-recent-orders"
        title="Recent Orders"
        question="What has just been confirmed?"
        rows={sections.orders}
        error={sectionError}
        onRetry={load}
        emptyTitle="No confirmed orders in this period"
        emptySubtitle="Orders appear here the moment a quotation is confirmed."
        footer={
          sections.orders && sections.orders.length >= TOP_N ? (
            <Text style={[type.caption, { color: colors.onSurfaceMuted }]}>
              Showing the {TOP_N} most recent confirmed orders.
            </Text>
          ) : null
        }
      >
        {(rows) => (
          <Table>
            <TableHeader
              columns={[
                { label: "Order", flex: 2 },
                { label: "Date", width: 62, align: "right" },
                { label: "Value", align: "right" },
                { label: "Due", align: "right" },
              ]}
            />
            {rows.map((row, i) => (
              <TableRow
                key={row.id}
                isLast={i === rows.length - 1}
                testID={`sales-order-row-${row.id}`}
                onPress={() => router.push(`/(admin)/quotations/${row.id}` as never)}
              >
                <TableCell flex={2}>
                  <View style={{ gap: 1, flexShrink: 1 }}>
                    <Text numberOfLines={1} style={type.bodySm}>{row.customer_name}</Text>
                    <Text numberOfLines={1} style={[type.caption, { color: colors.onSurfaceMuted }]}>
                      {row.number || "—"}
                    </Text>
                  </View>
                </TableCell>
                <TableCell width={62} align="right">{shortDate(row.ordered_at)}</TableCell>
                <TableCell align="right">{cellMoney(row.grand_total)}</TableCell>
                <TableCell align="right">
                  <Text
                    numberOfLines={1}
                    style={[type.bodySm, { color: row.outstanding > 0 ? colors.warning : colors.success }]}
                  >
                    {row.outstanding > 0 ? cellMoney(row.outstanding) : "Paid"}
                  </Text>
                </TableCell>
              </TableRow>
            ))}
          </Table>
        )}
      </SalesSection>
    </AdminPage>
  );
}

/**
 * One Referred By workspace. Architects and Interior Designers get their own,
 * from the same Phase 0 `/analytics/referrers` endpoint filtered by type.
 *
 * The empty state is the important case, not the edge case: the live book
 * currently has no referral attributed to any quotation at all, so this is
 * what the owner will see at launch. It says why the block is empty rather
 * than rendering a zero row that would imply a referrer earning nothing.
 */
function ReferrerWorkspace({
  title, rows, error, onRetry, onOpen, testID,
}: {
  title: string;
  rows: ReferrerSummaryRow[] | null;
  error?: string | null;
  onRetry?: () => void;
  onOpen: (referrerId: string) => void;
  testID: string;
}) {
  const cellMoney = useCellMoney();
  return (
    <SalesSection
      testID={testID}
      title={title}
      question="Who is sending us business?"
      rows={rows}
      error={error}
      onRetry={onRetry}
      emptyTitle="No referrals recorded in this period"
      emptySubtitle="Set 'Referred By' on a quotation and that person's business appears here."
    >
      {(list) => (
        <Table>
          <TableHeader
            columns={[
              { label: "Name", flex: 2 },
              { label: "Orders", align: "right" },
              { label: "Revenue", align: "right" },
            ]}
          />
          {list.map((row, i) => (
            <TableRow
              key={row.referrer_id}
              isLast={i === list.length - 1}
              testID={`${testID}-row-${row.referrer_id}`}
              onPress={() => onOpen(row.referrer_id)}
            >
              <TableCell flex={2}>{row.name}</TableCell>
              <TableCell align="right">{String(row.quotations_confirmed)}</TableCell>
              <TableCell align="right">{cellMoney(row.revenue)}</TableCell>
            </TableRow>
          ))}
        </Table>
      )}
    </SalesSection>
  );
}
