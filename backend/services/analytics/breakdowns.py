"""Pure shaping for the Sales Data launch breakdowns — Revenue by Brand,
Revenue by Customer, Best Selling Products, and Recent Orders.

No Mongo access in this file; see gather_breakdowns.py, the only module that
reads the database for these surfaces. Same split as
performance.py/gather_performance.py.

The one rule this module exists to hold: **every breakdown reconciles to
Total Revenue**. Revenue by Brand sums `items.net_amount` (via the canonical
line_revenue_pipeline upstream), and a line whose product no longer resolves
to a catalog doc is folded into an explicit "Unlinked products" bucket rather
than dropped. Dropping it is what makes a By-Brand table quietly total less
than the KPI card above it — 10 of the 30 product ids on the live book's
confirmed orders do not resolve today, which is ~₹2.4L that would have gone
missing.
"""
from __future__ import annotations

from dataclasses import dataclass

# The bucket unresolvable products fold into. A real brand id can never
# collide with it: brand ids are uuid4.
UNLINKED_BRAND_ID = "__unlinked__"
UNLINKED_BRAND_NAME = "Unlinked products"


@dataclass(frozen=True)
class BrandRow:
    brand_id: str
    name: str
    revenue: float
    quantity: float
    orders: int
    is_unlinked: bool


@dataclass(frozen=True)
class ProductRow:
    product_id: str
    name: str
    sku: str | None
    brand_name: str | None
    revenue: float
    quantity: float
    orders: int
    customers: int


@dataclass(frozen=True)
class CustomerRow:
    customer_id: str
    name: str
    revenue: float
    orders: int
    aov: float
    last_order_at: str | None


@dataclass(frozen=True)
class OrderRow:
    id: str
    number: str | None
    customer_id: str | None
    customer_name: str
    floor_id: str | None
    salesperson_name: str | None
    ordered_at: str | None
    grand_total: float
    collected: float
    outstanding: float


def _money(value) -> float:
    return round(float(value or 0), 2)


def brand_rows(
    product_revenue: list[dict],
    product_brand: dict[str, str],
    brand_names: dict[str, str],
) -> list[BrandRow]:
    """Fold per-product revenue up into brands.

    `product_revenue` is line_revenue_pipeline's own output shape (key =
    product id). `product_brand` maps only the products that still resolve to
    a catalog doc carrying a brand; everything else — a deleted product, a
    product with no brand set, a line whose product_id was never in the
    catalog — lands in the Unlinked bucket so the column still totals to
    Total Revenue.

    `orders` is summed rather than unioned: the per-product rows carry a
    count, not the underlying order ids, so a customer who bought two
    different products of one brand in a single order counts twice here.
    That is why the field is exposed as a line-level "orders" figure beside
    revenue and never used to divide revenue into an AOV.
    """
    folded: dict[str, dict] = {}
    for entry in product_revenue:
        product_id = entry.get("key")
        brand_id = product_brand.get(product_id) if product_id else None
        key = brand_id or UNLINKED_BRAND_ID
        bucket = folded.setdefault(key, {"revenue": 0.0, "quantity": 0.0, "orders": 0})
        bucket["revenue"] += float(entry.get("revenue") or 0)
        bucket["quantity"] += float(entry.get("quantity") or 0)
        bucket["orders"] += int(entry.get("orders") or 0)

    rows = [
        BrandRow(
            brand_id=key,
            name=UNLINKED_BRAND_NAME if key == UNLINKED_BRAND_ID else brand_names.get(key, "Unknown brand"),
            revenue=_money(bucket["revenue"]),
            quantity=round(bucket["quantity"], 2),
            orders=bucket["orders"],
            is_unlinked=key == UNLINKED_BRAND_ID,
        )
        for key, bucket in folded.items()
    ]
    # Unlinked always sorts last regardless of size — it is a data-quality
    # note, not a brand competing for the top of the owner's table.
    return sorted(rows, key=lambda r: (r.is_unlinked, -r.revenue))


def product_rows(
    line_revenue: list[dict],
    names: dict[str, str],
    skus: dict[str, str],
    product_brand: dict[str, str],
    brand_names: dict[str, str],
) -> list[ProductRow]:
    """Best sellers, ranked by revenue.

    Names come from the order lines themselves (`items.name`), not from the
    catalog: the line is what was actually sold and it is present for every
    row, whereas a third of the live book's product ids no longer resolve to
    a catalog doc at all.
    """
    rows = []
    for entry in line_revenue:
        product_id = entry.get("key")
        if not product_id:
            continue
        brand_id = product_brand.get(product_id)
        rows.append(
            ProductRow(
                product_id=product_id,
                name=names.get(product_id) or "Unknown product",
                sku=skus.get(product_id),
                brand_name=brand_names.get(brand_id) if brand_id else None,
                revenue=_money(entry.get("revenue")),
                quantity=round(float(entry.get("quantity") or 0), 2),
                orders=int(entry.get("orders") or 0),
                customers=int(entry.get("customers") or 0),
            )
        )
    return sorted(rows, key=lambda r: -r.revenue)


def customer_rows(orders: list[dict]) -> list[CustomerRow]:
    """Revenue by customer, folded in Python over the already-fetched
    confirmed orders — the same convention gather_collections_orders uses,
    and the reason this surface needs no new Mongo aggregation.

    A customer's AOV divides by their own order count, so it stays a real
    per-order average even when one customer dominates the period.
    """
    folded: dict[str, dict] = {}
    for order in orders:
        customer_id = order.get("customer_id") or ""
        bucket = folded.setdefault(
            customer_id,
            {"name": order.get("customer_name") or "Unknown customer", "revenue": 0.0, "orders": 0, "last": None},
        )
        bucket["revenue"] += float(order.get("grand_total") or 0)
        bucket["orders"] += 1
        stamp = order.get("ordered_at")
        # ISO-8601 UTC strings compare correctly as strings; every ordered
        # quotation on the live book carries ordered_at (verified), but a
        # missing one must not win the max and blank the column.
        if stamp and (bucket["last"] is None or stamp > bucket["last"]):
            bucket["last"] = stamp

    rows = [
        CustomerRow(
            customer_id=customer_id,
            name=bucket["name"],
            revenue=_money(bucket["revenue"]),
            orders=bucket["orders"],
            aov=_money(bucket["revenue"] / bucket["orders"]) if bucket["orders"] else 0.0,
            last_order_at=bucket["last"],
        )
        for customer_id, bucket in folded.items()
    ]
    return sorted(rows, key=lambda r: -r.revenue)


def order_rows(orders: list[dict], collected: dict[str, float]) -> list[OrderRow]:
    """Recent orders, newest first.

    `collected` counts only status="completed" payments (Phase 1's
    collected_by_quotation), so Outstanding here uses the same definition as
    the Outstanding KPI card and the Collections workspace.
    """
    rows = []
    for order in orders:
        total = float(order.get("grand_total") or 0)
        paid = float(collected.get(order.get("id"), 0.0))
        rows.append(
            OrderRow(
                id=order.get("id"),
                number=order.get("number"),
                customer_id=order.get("customer_id"),
                customer_name=order.get("customer_name") or "Unknown customer",
                floor_id=order.get("floor_id"),
                salesperson_name=order.get("created_by_name"),
                ordered_at=order.get("ordered_at"),
                grand_total=_money(total),
                collected=_money(paid),
                outstanding=_money(total - paid),
            )
        )
    return sorted(rows, key=lambda r: (r.ordered_at or ""), reverse=True)
