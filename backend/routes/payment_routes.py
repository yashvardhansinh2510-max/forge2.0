"""Payments module — customer collection tracker for confirmed sales orders.

An "order" in this module is a Quotation whose status is `ordered` or `won`
(i.e. a confirmed sale). Each order accrues Payment records against it; the
outstanding balance is derived as `grand_total - sum(payments)`.

There are NO taxes anywhere in Forge — the quotation's grand_total is the
final price the customer pays, and payments accumulate against it directly.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_user, require_min_role
from db import db
from models import Payment, PaymentCreate, UserPublic
from services.activity_log import log_event

router = APIRouter(prefix="/payments", tags=["payments"])


# The set of quotation statuses we treat as "collectable orders".
ORDER_STATUSES = ("ordered", "won")

MODE_LABELS = {
    "cash": "Cash",
    "upi": "UPI",
    "bank": "Bank Transfer",
    "cheque": "Cheque",
    "card": "Credit Card",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _paid_by_quotation(quotation_ids: list[str]) -> dict[str, float]:
    """Sum completed payment amounts per quotation."""
    if not quotation_ids:
        return {}
    pipeline = [
        {"$match": {"quotation_id": {"$in": quotation_ids}, "status": "completed"}},
        {"$group": {"_id": "$quotation_id", "total": {"$sum": "$amount"}}},
    ]
    rows = await db.payments.aggregate(pipeline).to_list(len(quotation_ids) + 5)
    return {r["_id"]: float(r.get("total", 0)) for r in rows}


async def _mrp_for_quotation(quotation: dict) -> float:
    """Return the sum of qty × product.mrp for the quotation's line items.
    Falls back to unit_price when the product record is missing."""
    items = quotation.get("items", [])
    if not items:
        return 0.0
    product_ids = list({i.get("product_id") for i in items if i.get("product_id")})
    products = await db.products.find(
        {"id": {"$in": product_ids}}, {"_id": 0, "id": 1, "mrp": 1}
    ).to_list(len(product_ids) + 5) if product_ids else []
    mrp_by_id = {p["id"]: float(p.get("mrp") or 0) for p in products}
    total = 0.0
    for it in items:
        pid = it.get("product_id")
        qty = float(it.get("qty") or 0)
        mrp = mrp_by_id.get(pid) or float(it.get("unit_price") or 0)
        total += qty * mrp
    return round(total, 2)


def _payment_status(paid: float, grand: float) -> str:
    """Derived status for the order card: paid | partial | due."""
    if grand <= 0:
        return "due"
    if paid + 1e-6 >= grand:
        return "paid"
    if paid > 0:
        return "partial"
    return "due"


def _short_amount(amount: float) -> str:
    """Compact Indian rupee display used in the sidebar badge: ₹10.9L / ₹8.5L."""
    if amount >= 1_00_00_000:
        return f"₹{amount / 1_00_00_000:.1f}Cr"
    if amount >= 1_00_000:
        return f"₹{amount / 1_00_000:.1f}L"
    if amount >= 1_000:
        return f"₹{amount / 1_000:.1f}k"
    return f"₹{int(amount)}"


def _iso_month(iso_ts: str) -> str:
    return (iso_ts or "")[:7]  # "2026-08"


# ---------------------------------------------------------------------------
# Stats (KPI cards at the top of the page)
# ---------------------------------------------------------------------------
@router.get("/stats")
async def payment_stats(_: UserPublic = Depends(get_current_user)):
    """Four KPIs: Total Outstanding · Collected This Month · Active Orders · Fully Paid."""
    orders = await db.quotations.find(
        {"status": {"$in": list(ORDER_STATUSES)}},
        {"_id": 0, "id": 1, "grand_total": 1},
    ).to_list(2000)
    ids = [o["id"] for o in orders]
    paid_map = await _paid_by_quotation(ids)

    total_outstanding = 0.0
    active_orders = 0
    fully_paid = 0
    for o in orders:
        grand = float(o.get("grand_total") or 0)
        paid = paid_map.get(o["id"], 0.0)
        status = _payment_status(paid, grand)
        if status == "paid":
            fully_paid += 1
        else:
            active_orders += 1
            total_outstanding += max(0.0, grand - paid)

    # Collected this month
    this_month = _iso_month(datetime.now(timezone.utc).isoformat())
    pipeline = [
        {"$match": {"status": "completed"}},
        {"$group": {"_id": {"$substr": [{"$ifNull": ["$paid_at", "$created_at"]}, 0, 7]}, "total": {"$sum": "$amount"}}},
    ]
    rows = await db.payments.aggregate(pipeline).to_list(60)
    collected_this_month = 0.0
    for r in rows:
        if r["_id"] == this_month:
            collected_this_month = float(r.get("total", 0))
            break

    return {
        "total_outstanding": round(total_outstanding, 2),
        "collected_this_month": round(collected_this_month, 2),
        "active_orders": active_orders,
        "fully_paid": fully_paid,
    }


# ---------------------------------------------------------------------------
# Orders list (left column)
# ---------------------------------------------------------------------------
@router.get("/orders")
async def list_orders(
    q: Optional[str] = None,
    status_filter: Optional[str] = Query(None, description="paid | partial | due | all"),
    limit: int = Query(200, ge=1, le=1000),
    _: UserPublic = Depends(get_current_user),
):
    """Collectable orders sorted by outstanding-first."""
    query: dict = {"status": {"$in": list(ORDER_STATUSES)}}
    if q:
        term = {"$regex": q, "$options": "i"}
        query["$or"] = [
            {"number": term}, {"customer_name": term},
        ]

    docs = await db.quotations.find(
        query, {"_id": 0, "id": 1, "number": 1, "customer_id": 1, "customer_name": 1,
                "grand_total": 1, "status": 1, "updated_at": 1, "created_at": 1, "notes": 1},
    ).sort("updated_at", -1).to_list(limit * 2)

    ids = [d["id"] for d in docs]
    paid_map = await _paid_by_quotation(ids)

    out = []
    for d in docs:
        grand = float(d.get("grand_total") or 0)
        paid = paid_map.get(d["id"], 0.0)
        outstanding = max(0.0, grand - paid)
        pay_status = _payment_status(paid, grand)
        pct = 0 if grand <= 0 else min(100, int(round(paid / grand * 100)))
        out.append({
            "id": d["id"],
            "number": d.get("number"),
            "customer_id": d.get("customer_id"),
            "customer_name": d.get("customer_name"),
            "grand_total": grand,
            "paid": round(paid, 2),
            "outstanding": round(outstanding, 2),
            "percent_collected": pct,
            "payment_status": pay_status,       # paid | partial | due
            "confirmed_at": d.get("updated_at") or d.get("created_at"),
            "outstanding_short": _short_amount(outstanding) if outstanding > 0 else None,
        })

    if status_filter and status_filter != "all":
        out = [o for o in out if o["payment_status"] == status_filter]

    # Sort: outstanding desc, then most recently confirmed
    out.sort(key=lambda o: (-o["outstanding"], -(o.get("confirmed_at") or "").__hash__()))
    return out[:limit]


# ---------------------------------------------------------------------------
# Order detail (right column)
# ---------------------------------------------------------------------------
@router.get("/orders/{order_id}")
async def order_detail(order_id: str, _: UserPublic = Depends(get_current_user)):
    doc = await db.quotations.find_one({"id": order_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    if doc.get("status") not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Quotation is not a confirmed order yet")

    paid_map = await _paid_by_quotation([order_id])
    paid = paid_map.get(order_id, 0.0)
    grand = float(doc.get("grand_total") or 0)
    mrp = await _mrp_for_quotation(doc)
    outstanding = max(0.0, grand - paid)

    customer = await db.customers.find_one({"id": doc["customer_id"]}, {"_id": 0, "password_hash": 0}) or {}

    payments = await db.payments.find(
        {"quotation_id": order_id}, {"_id": 0},
    ).sort("paid_at", -1).to_list(500)
    # Ensure legacy payments (without paid_at) still sort sensibly
    payments.sort(key=lambda p: (p.get("paid_at") or p.get("created_at") or ""), reverse=True)

    return {
        "id": doc["id"],
        "number": doc.get("number"),
        "status": doc.get("status"),
        "customer": {
            "id": customer.get("id"),
            "name": customer.get("name"),
            "company": customer.get("company"),
            "phone": customer.get("phone"),
            "email": customer.get("email"),
            "city": customer.get("city"),
            "address": customer.get("address"),
        },
        "customer_name": doc.get("customer_name"),
        "confirmed_at": doc.get("updated_at") or doc.get("created_at"),
        "notes": doc.get("notes"),
        "project_name": None,
        "mrp": round(mrp, 2),
        "discounted_rate": round(grand, 2),
        "grand_total": round(grand, 2),
        "paid": round(paid, 2),
        "outstanding": round(outstanding, 2),
        "percent_collected": 0 if grand <= 0 else min(100, int(round(paid / grand * 100))),
        "payment_status": _payment_status(paid, grand),
        "payments": payments,
    }


# ---------------------------------------------------------------------------
# Record a payment
# ---------------------------------------------------------------------------
@router.post("", response_model=Payment)
async def create_payment(
    body: PaymentCreate,
    user: UserPublic = Depends(require_min_role("accounts")),
):
    quot = await db.quotations.find_one({"id": body.quotation_id}, {"_id": 0})
    if not quot:
        raise HTTPException(status_code=404, detail="Order not found")
    if quot.get("status") not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Quotation is not a confirmed order yet")
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")

    now = datetime.now(timezone.utc).isoformat()
    paid_at = body.paid_at or now
    payment = Payment(
        quotation_id=body.quotation_id,
        quotation_number=quot.get("number"),
        customer_id=quot["customer_id"],
        customer_name=quot.get("customer_name"),
        amount=round(float(body.amount), 2),
        mode=body.mode,
        status="completed",
        reference=body.reference,
        note=body.note,
        paid_at=paid_at,
        recorded_by=user.id,
        recorded_by_name=user.full_name,
    )
    await db.payments.insert_one(payment.dict())

    # If this settled the balance, we auto-flip the quotation to "won" ONLY if
    # it was already an ordered/won-tracked order; otherwise we leave it as-is.
    paid_map = await _paid_by_quotation([body.quotation_id])
    total_paid = paid_map.get(body.quotation_id, 0.0)
    grand = float(quot.get("grand_total") or 0)
    fully_paid = total_paid + 1e-6 >= grand

    await log_event(
        event_type="payment.recorded",
        entity_type="payment",
        entity_id=payment.id,
        actor=user,
        customer_id=quot["customer_id"],
        quotation_id=body.quotation_id,
        summary=(
            f"{MODE_LABELS.get(body.mode, body.mode).title()} · "
            f"₹{payment.amount:,.0f} received on {quot.get('number')}"
        ),
        payload={
            "amount": payment.amount,
            "mode": body.mode,
            "reference": body.reference,
            "fully_paid": fully_paid,
        },
    )
    return payment


# Backwards-compat: keep GET /api/payments returning the raw list (used elsewhere).
@router.get("")
async def list_payments(_: UserPublic = Depends(get_current_user)):
    docs = await db.payments.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return docs


# ---------------------------------------------------------------------------
# WhatsApp reminder builder
# ---------------------------------------------------------------------------
def _format_amount(v: float) -> str:
    """Indian-style comma formatting: 12,34,567."""
    s = f"{int(round(v))}"
    if len(s) <= 3:
        return s
    last3, rest = s[-3:], s[:-3]
    parts = []
    while len(rest) > 2:
        parts.append(rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.append(rest)
    return ",".join(reversed(parts)) + "," + last3


def _clean_phone(phone: Optional[str]) -> Optional[str]:
    """Strip everything but digits; if it starts with 0 or has no country code assume India (+91)."""
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not digits:
        return None
    if len(digits) == 10:                     # 98200 12345 → +91
        return "91" + digits
    if digits.startswith("0") and len(digits) == 11:
        return "91" + digits[1:]
    return digits


@router.get("/orders/{order_id}/whatsapp-reminder")
async def whatsapp_reminder(order_id: str, _: UserPublic = Depends(get_current_user)):
    """Build a wa.me link + message body for a payment reminder."""
    doc = await db.quotations.find_one({"id": order_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    customer = await db.customers.find_one({"id": doc["customer_id"]}, {"_id": 0}) or {}
    paid_map = await _paid_by_quotation([order_id])
    paid = paid_map.get(order_id, 0.0)
    grand = float(doc.get("grand_total") or 0)
    outstanding = max(0.0, grand - paid)

    phone = _clean_phone(customer.get("phone"))
    name = (customer.get("name") or doc.get("customer_name") or "there").split()[0]
    number = doc.get("number") or ""

    lines = [
        f"Hi {name},",
        "",
        f"This is a gentle reminder for your order *{number}*.",
        "",
        f"• Order total: ₹{_format_amount(grand)}",
        f"• Already received: ₹{_format_amount(paid)}",
        f"• Outstanding balance: *₹{_format_amount(outstanding)}*",
        "",
        "Kindly complete the pending payment at your earliest convenience. Please share the reference (UTR / cheque no.) once done so we can update our records.",
        "",
        "Thank you for your business!",
        "— Forge",
    ]
    message = "\n".join(lines)

    return {
        "customer_name": customer.get("name") or doc.get("customer_name"),
        "phone": phone,
        "phone_display": customer.get("phone"),
        "message": message,
        "outstanding": round(outstanding, 2),
        "wa_url": (
            f"https://wa.me/{phone}?text={quote_plus(message)}"
            if phone else
            f"https://wa.me/?text={quote_plus(message)}"
        ),
    }
