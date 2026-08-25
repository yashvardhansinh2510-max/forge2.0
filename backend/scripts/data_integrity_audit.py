"""Phase 2 — Production Data Integrity Audit (read-only).

Cross-collection referential integrity across the full domain graph:
Customer <-> Quotation <-> Purchase Order <-> Payment <-> Follow-up <-> Product.

This performs NO writes. It only reports. Run with:
    python scripts/data_integrity_audit.py
"""
from __future__ import annotations
import asyncio
import json
import sys
from collections import Counter

sys.path.insert(0, ".")
from db import db  # noqa: E402


async def _ids(collection: str) -> set[str]:
    docs = await db[collection].find({}, {"_id": 0, "id": 1}).to_list(200000)
    return {d["id"] for d in docs if d.get("id")}


async def main() -> dict:
    report: dict = {"errors": [], "warnings": [], "info": {}}

    customer_ids = await _ids("customers")
    quotation_ids = await _ids("quotations")
    product_ids = await _ids("products")
    user_ids = await _ids("users")
    po_ids = await _ids("purchase_orders")
    brand_ids = await _ids("brands")
    category_ids = await _ids("categories")

    report["info"]["counts"] = {
        "customers": len(customer_ids), "quotations": len(quotation_ids),
        "products": len(product_ids), "users": len(user_ids),
        "purchase_orders": len(po_ids), "brands": len(brand_ids), "categories": len(category_ids),
    }

    # ---- Quotations -> customers, users, products ------------------------
    quotations = await db.quotations.find(
        {}, {"_id": 0, "id": 1, "number": 1, "customer_id": 1, "created_by": 1, "items": 1},
    ).to_list(200000)
    orphan_q_customer = [q["id"] for q in quotations if q.get("customer_id") not in customer_ids]
    orphan_q_creator = [q["id"] for q in quotations if q.get("created_by") and q["created_by"] not in user_ids]
    dangling_line_products = []
    numbers = Counter(q.get("number") for q in quotations)
    for q in quotations:
        for it in q.get("items", []) or []:
            if it.get("product_id") and it["product_id"] not in product_ids:
                dangling_line_products.append({"quotation_id": q["id"], "product_id": it["product_id"], "sku": it.get("sku")})
    dup_numbers = {n: c for n, c in numbers.items() if c > 1}

    if orphan_q_customer:
        report["errors"].append({"check": "quotations.customer_id -> customers", "orphans": orphan_q_customer})
    if orphan_q_creator:
        report["warnings"].append({"check": "quotations.created_by -> users", "orphans": orphan_q_creator})
    if dangling_line_products:
        report["warnings"].append({"check": "quotations.items[].product_id -> products", "count": len(dangling_line_products), "sample": dangling_line_products[:10]})
    if dup_numbers:
        report["errors"].append({"check": "quotations.number uniqueness", "duplicates": dup_numbers})
    report["info"]["quotations_checked"] = len(quotations)

    # ---- Purchase orders -> customers, quotations, products --------------
    pos = await db.purchase_orders.find(
        {}, {"_id": 0, "id": 1, "number": 1, "customer_id": 1, "quotation_id": 1, "brand_id": 1, "items": 1},
    ).to_list(200000)
    orphan_po_customer = [p["id"] for p in pos if p.get("customer_id") and p["customer_id"] not in customer_ids]
    orphan_po_quotation = [p["id"] for p in pos if p.get("quotation_id") and p["quotation_id"] not in quotation_ids]
    orphan_po_brand = [p["id"] for p in pos if p.get("brand_id") and p["brand_id"] not in brand_ids]
    po_numbers = Counter(p.get("number") for p in pos)
    dup_po_numbers = {n: c for n, c in po_numbers.items() if c > 1}
    dangling_po_line_products = []
    for p in pos:
        for it in p.get("items", []) or []:
            if it.get("product_id") and it["product_id"] not in product_ids:
                dangling_po_line_products.append({"po_id": p["id"], "product_id": it["product_id"]})

    if orphan_po_customer:
        report["errors"].append({"check": "purchase_orders.customer_id -> customers", "orphans": orphan_po_customer})
    if orphan_po_quotation:
        report["errors"].append({"check": "purchase_orders.quotation_id -> quotations", "orphans": orphan_po_quotation})
    if orphan_po_brand:
        report["errors"].append({"check": "purchase_orders.brand_id -> brands", "orphans": orphan_po_brand})
    if dup_po_numbers:
        report["errors"].append({"check": "purchase_orders.number uniqueness", "duplicates": dup_po_numbers})
    if dangling_po_line_products:
        report["warnings"].append({"check": "purchase_orders.items[].product_id -> products", "count": len(dangling_po_line_products), "sample": dangling_po_line_products[:10]})
    report["info"]["purchase_orders_checked"] = len(pos)

    # ---- Payments -> quotations, customers --------------------------------
    payments = await db.payments.find({}, {"_id": 0, "id": 1, "quotation_id": 1, "customer_id": 1}).to_list(200000)
    orphan_pay_quotation = [p["id"] for p in payments if p.get("quotation_id") not in quotation_ids]
    orphan_pay_customer = [p["id"] for p in payments if p.get("customer_id") and p["customer_id"] not in customer_ids]
    if orphan_pay_quotation:
        report["errors"].append({"check": "payments.quotation_id -> quotations", "orphans": orphan_pay_quotation})
    if orphan_pay_customer:
        report["errors"].append({"check": "payments.customer_id -> customers", "orphans": orphan_pay_customer})
    report["info"]["payments_checked"] = len(payments)

    # Payment overpayment check — sum(payments) should never exceed grand_total materially
    quot_by_id = {q["id"]: q for q in quotations}
    quot_full = await db.quotations.find({}, {"_id": 0, "id": 1, "grand_total": 1}).to_list(200000)
    grand_by_id = {q["id"]: float(q.get("grand_total") or 0) for q in quot_full}
    paid_by_quotation: dict[str, float] = {}
    for p in payments:
        qid = p.get("quotation_id")
        if qid:
            paid_by_quotation[qid] = paid_by_quotation.get(qid, 0.0) + 0.0  # placeholder, amounts fetched below
    payments_full = await db.payments.find({"status": "completed"}, {"_id": 0, "quotation_id": 1, "amount": 1}).to_list(200000)
    paid_by_quotation = {}
    for p in payments_full:
        qid = p.get("quotation_id")
        if qid:
            paid_by_quotation[qid] = paid_by_quotation.get(qid, 0.0) + float(p.get("amount") or 0)
    overpaid = [
        {"quotation_id": qid, "paid": round(paid, 2), "grand_total": round(grand_by_id.get(qid, 0), 2)}
        for qid, paid in paid_by_quotation.items()
        if grand_by_id.get(qid) is not None and paid > grand_by_id.get(qid, 0) + 1.0
    ]
    if overpaid:
        report["warnings"].append({"check": "payments sum <= quotation.grand_total", "overpaid": overpaid})

    # ---- Follow-ups -> customers, quotations ------------------------------
    followups = await db.followups.find({}, {"_id": 0, "id": 1, "customer_id": 1, "quotation_id": 1}).to_list(200000)
    orphan_f_customer = [f["id"] for f in followups if f.get("customer_id") and f["customer_id"] not in customer_ids]
    orphan_f_quotation = [f["id"] for f in followups if f.get("quotation_id") and f["quotation_id"] not in quotation_ids]
    if orphan_f_customer:
        report["errors"].append({"check": "followups.customer_id -> customers", "orphans": orphan_f_customer})
    if orphan_f_quotation:
        report["warnings"].append({"check": "followups.quotation_id -> quotations", "orphans": orphan_f_quotation})
    report["info"]["followups_checked"] = len(followups)

    # ---- Idempotency: automation_key duplicates ---------------------------
    for coll, field in [("payments", "automation_key"), ("followups", "automation_key"), ("purchase_orders", "automation_key")]:
        docs = await db[coll].find({field: {"$exists": True, "$ne": None}}, {"_id": 0, field: 1}).to_list(200000)
        keys = Counter(d[field] for d in docs)
        dupes = {k: c for k, c in keys.items() if c > 1}
        if dupes:
            report["errors"].append({"check": f"{coll}.{field} idempotency", "duplicates": dupes})
        report["info"][f"{coll}_{field}_checked"] = len(docs)

    # ---- Duplicate prevention: user / customer email uniqueness -----------
    users = await db.users.find({}, {"_id": 0, "email": 1}).to_list(2000)
    user_emails = Counter((u.get("email") or "").lower() for u in users if u.get("email"))
    dup_user_emails = {e: c for e, c in user_emails.items() if c > 1}
    if dup_user_emails:
        report["errors"].append({"check": "users.email uniqueness", "duplicates": dup_user_emails})

    customers_all = await db.customers.find({}, {"_id": 0, "email": 1}).to_list(200000)
    cust_emails = Counter((c.get("email") or "").lower() for c in customers_all if c.get("email"))
    dup_cust_emails = {e: c for e, c in cust_emails.items() if c > 1}
    if dup_cust_emails:
        report["warnings"].append({"check": "customers.email uniqueness (informational — email is optional/non-unique by design)", "duplicates": dup_cust_emails})

    # ---- Product media / category refs (cross-check vs integrity_guard) ---
    prods = await db.products.find({}, {"_id": 0, "id": 1, "brand_id": 1, "category_id": 1}).to_list(200000)
    orphan_p_brand = [p["id"] for p in prods if p.get("brand_id") and p["brand_id"] not in brand_ids]
    orphan_p_category = [p["id"] for p in prods if p.get("category_id") and p["category_id"] not in category_ids]
    if orphan_p_brand:
        report["errors"].append({"check": "products.brand_id -> brands", "orphans": orphan_p_brand})
    if orphan_p_category:
        report["errors"].append({"check": "products.category_id -> categories", "orphans": orphan_p_category})

    report["healthy"] = len(report["errors"]) == 0
    return report


if __name__ == "__main__":
    result = asyncio.run(main())
    print(json.dumps(result, indent=2, default=str))
    raise SystemExit(0 if result["healthy"] else 1)
