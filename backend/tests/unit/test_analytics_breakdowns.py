"""Pure shaping tests for the Sales Data launch breakdowns.

The invariant every test here defends is the one the launch page lives or
dies on: **each breakdown must total to the same number as the Total Revenue
KPI card above it**. A table that quietly drops a row is worse than one that
shows an ugly row, because the owner has no way to see the difference.
"""
from __future__ import annotations

from services.analytics.breakdowns import (
    UNLINKED_BRAND_ID,
    brand_rows,
    customer_rows,
    order_rows,
    product_rows,
)

# line_revenue_pipeline's own output shape: key = the grouped field.
LINES = [
    {"key": "p-vitra-1", "revenue": 1000.0, "quantity": 4, "orders": 2, "customers": 2},
    {"key": "p-vitra-2", "revenue": 500.0, "quantity": 1, "orders": 1, "customers": 1},
    {"key": "p-qutone-1", "revenue": 250.0, "quantity": 10, "orders": 1, "customers": 1},
    {"key": "p-deleted", "revenue": 125.0, "quantity": 3, "orders": 1, "customers": 1},
]
PRODUCT_BRAND = {"p-vitra-1": "b-vitra", "p-vitra-2": "b-vitra", "p-qutone-1": "b-qutone"}
BRAND_NAMES = {"b-vitra": "Vitra", "b-qutone": "Qutone"}

TOTAL_LINE_REVENUE = 1875.0


# ---------------------------------------------------------------------------
# Revenue by Brand
# ---------------------------------------------------------------------------

def test_brand_revenue_folds_products_up_into_their_brand():
    rows = brand_rows(LINES, PRODUCT_BRAND, BRAND_NAMES)
    by_name = {r.name: r for r in rows}
    assert by_name["Vitra"].revenue == 1500.0
    assert by_name["Qutone"].revenue == 250.0


def test_a_product_with_no_resolvable_brand_is_bucketed_not_dropped():
    """The live book has 10 of 30 ordered product ids that no longer resolve
    to a catalog doc — ~13.7% of revenue. Dropping them would make the
    By-Brand table total less than the KPI card."""
    rows = brand_rows(LINES, PRODUCT_BRAND, BRAND_NAMES)
    unlinked = [r for r in rows if r.is_unlinked]
    assert len(unlinked) == 1
    assert unlinked[0].brand_id == UNLINKED_BRAND_ID
    assert unlinked[0].revenue == 125.0


def test_brand_revenue_totals_to_the_full_line_revenue():
    rows = brand_rows(LINES, PRODUCT_BRAND, BRAND_NAMES)
    assert round(sum(r.revenue for r in rows), 2) == TOTAL_LINE_REVENUE


def test_unlinked_sorts_last_even_when_it_is_the_largest_bucket():
    """It is a data-quality note, not a brand competing for the top row."""
    huge = [{"key": "p-deleted", "revenue": 999_999.0, "quantity": 1, "orders": 1, "customers": 1}] + LINES[:1]
    rows = brand_rows(huge, PRODUCT_BRAND, BRAND_NAMES)
    assert rows[-1].is_unlinked
    assert rows[0].name == "Vitra"


def test_brands_are_ranked_by_revenue_descending():
    rows = [r for r in brand_rows(LINES, PRODUCT_BRAND, BRAND_NAMES) if not r.is_unlinked]
    assert [r.name for r in rows] == ["Vitra", "Qutone"]


def test_a_brand_id_with_no_name_doc_still_reports_its_revenue():
    rows = brand_rows(LINES, PRODUCT_BRAND, {})
    assert round(sum(r.revenue for r in rows), 2) == TOTAL_LINE_REVENUE
    assert {r.name for r in rows if not r.is_unlinked} == {"Unknown brand"}


def test_no_lines_produces_no_rows_rather_than_a_zero_row():
    assert brand_rows([], PRODUCT_BRAND, BRAND_NAMES) == []


# ---------------------------------------------------------------------------
# Best Selling Products
# ---------------------------------------------------------------------------

def test_products_are_named_from_the_order_line_not_the_catalog():
    """A third of live ordered product ids have no catalog doc; the line
    records what was actually sold."""
    rows = product_rows(LINES, {"p-deleted": "Discontinued Basin"}, {}, PRODUCT_BRAND, BRAND_NAMES)
    deleted = next(r for r in rows if r.product_id == "p-deleted")
    assert deleted.name == "Discontinued Basin"
    assert deleted.brand_name is None


def test_products_carry_their_brand_name_when_it_resolves():
    rows = product_rows(LINES, {"p-vitra-1": "Integra WC"}, {"p-vitra-1": "SKU-1"}, PRODUCT_BRAND, BRAND_NAMES)
    top = rows[0]
    assert (top.name, top.sku, top.brand_name) == ("Integra WC", "SKU-1", "Vitra")


def test_products_are_ranked_by_revenue_and_total_to_line_revenue():
    rows = product_rows(LINES, {}, {}, PRODUCT_BRAND, BRAND_NAMES)
    assert [r.revenue for r in rows] == sorted((r.revenue for r in rows), reverse=True)
    assert round(sum(r.revenue for r in rows), 2) == TOTAL_LINE_REVENUE


def test_a_line_with_no_product_id_is_skipped_rather_than_keyed_on_none():
    rows = product_rows([{"key": None, "revenue": 10.0}], {}, {}, {}, {})
    assert rows == []


# ---------------------------------------------------------------------------
# Revenue by Customer
# ---------------------------------------------------------------------------

ORDERS = [
    {"id": "q1", "customer_id": "c1", "customer_name": "Malhotra Interiors",
     "grand_total": 300.0, "ordered_at": "2026-07-01T00:00:00+00:00"},
    {"id": "q2", "customer_id": "c1", "customer_name": "Malhotra Interiors",
     "grand_total": 100.0, "ordered_at": "2026-07-20T00:00:00+00:00"},
    {"id": "q3", "customer_id": "c2", "customer_name": "Menon Architects",
     "grand_total": 500.0, "ordered_at": "2026-07-10T00:00:00+00:00"},
]


def test_customer_revenue_sums_and_counts_each_customers_orders():
    rows = {r.customer_id: r for r in customer_rows(ORDERS)}
    assert (rows["c1"].revenue, rows["c1"].orders) == (400.0, 2)
    assert (rows["c2"].revenue, rows["c2"].orders) == (500.0, 1)


def test_customer_aov_divides_by_that_customers_own_order_count():
    rows = {r.customer_id: r for r in customer_rows(ORDERS)}
    assert rows["c1"].aov == 200.0
    assert rows["c2"].aov == 500.0


def test_last_order_at_is_the_newest_stamp_not_the_last_one_seen():
    rows = {r.customer_id: r for r in customer_rows(ORDERS)}
    assert rows["c1"].last_order_at == "2026-07-20T00:00:00+00:00"


def test_a_missing_ordered_at_does_not_blank_a_customers_last_order():
    orders = ORDERS + [{"id": "q4", "customer_id": "c1", "customer_name": "Malhotra Interiors",
                        "grand_total": 1.0, "ordered_at": None}]
    rows = {r.customer_id: r for r in customer_rows(orders)}
    assert rows["c1"].last_order_at == "2026-07-20T00:00:00+00:00"


def test_customer_revenue_totals_to_the_orders_it_was_given():
    rows = customer_rows(ORDERS)
    assert round(sum(r.revenue for r in rows), 2) == 900.0


def test_customers_are_ranked_by_revenue_descending():
    assert [r.name for r in customer_rows(ORDERS)] == ["Menon Architects", "Malhotra Interiors"]


# ---------------------------------------------------------------------------
# Recent Orders
# ---------------------------------------------------------------------------

def test_outstanding_is_order_value_minus_completed_payments():
    rows = order_rows(ORDERS, {"q1": 120.0})
    q1 = next(r for r in rows if r.id == "q1")
    assert (q1.collected, q1.outstanding) == (120.0, 180.0)


def test_an_order_with_no_payment_row_is_fully_outstanding():
    rows = order_rows(ORDERS, {})
    assert all(r.outstanding == r.grand_total for r in rows)


def test_recent_orders_are_newest_first():
    rows = order_rows(ORDERS, {})
    assert [r.id for r in rows] == ["q2", "q3", "q1"]


def test_an_order_with_no_ordered_at_sorts_last_rather_than_raising():
    rows = order_rows(ORDERS + [{"id": "q9", "customer_name": "X", "grand_total": 5.0}], {})
    assert rows[-1].id == "q9"


def test_a_missing_customer_name_renders_a_label_not_an_empty_cell():
    rows = order_rows([{"id": "q1", "grand_total": 10.0, "ordered_at": "2026-07-01T00:00:00+00:00"}], {})
    assert rows[0].customer_name == "Unknown customer"
