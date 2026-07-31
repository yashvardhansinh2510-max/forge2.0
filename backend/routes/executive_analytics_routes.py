"""Database-driven executive analytics. Legacy ``/sales-data`` stays isolated.

Revenue is deliberately derived only from confirmed orders (``ordered``
quotations). Every query starts with the same floor/date/brand/owner/referrer
match so cards, tables and exports cannot drift from the books.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from auth import accessible_floor_ids, require_roles
from db import db
from models import UserPublic

router = APIRouter(prefix="/executive-analytics", tags=["executive-analytics"])
Granularity = Literal["day", "week", "month", "quarter", "year"]


def _date_range(preset: str, custom_from: Optional[str], custom_to: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if preset == "custom":
        return custom_from, custom_to
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if preset == "today": start, end = today, now
    elif preset == "yesterday": start, end = today - timedelta(days=1), today
    elif preset.startswith("last_") and preset.endswith("_days"):
        start, end = today - timedelta(days=int(preset.split("_")[1]) - 1), now
    elif preset == "this_month": start, end = today.replace(day=1), now
    elif preset == "last_month":
        end = today.replace(day=1); start = (end - timedelta(days=1)).replace(day=1)
    elif preset == "quarter": start, end = today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1), now
    elif preset == "year": start, end = today.replace(month=1, day=1), now
    else: return None, None
    return start.isoformat(), end.isoformat()


async def _match(
    user: UserPublic, floor_id: Optional[str], preset: str, date_from: Optional[str], date_to: Optional[str],
    brand_id: Optional[str], salesperson_id: Optional[str], referrer_type: Optional[str], customer_id: Optional[str] = None, referrer_id: Optional[str] = None,
) -> dict:
    allowed = accessible_floor_ids(user)
    floors = [floor_id] if floor_id and floor_id != "all" else allowed
    if floor_id and floor_id != "all" and allowed is not None and floor_id not in allowed:
        raise HTTPException(status_code=403, detail="You do not have access to this floor")
    start, end = _date_range(preset, date_from, date_to)
    query: dict = {"status": "ordered"}
    if floors is not None: query["floor_id"] = {"$in": floors}
    if salesperson_id: query["created_by"] = salesperson_id
    if referrer_type: query["referrer_type"] = referrer_type
    if customer_id: query["customer_id"] = customer_id
    if referrer_id: query["referrer_id"] = referrer_id
    if start or end:
        query["updated_at"] = {k: v for k, v in (("$gte", start), ("$lte", end)) if v}
    if brand_id:
        ids = [p["id"] for p in await db.products.find({"brand_id": brand_id}, {"_id": 0, "id": 1}).to_list(100000)]
        query["items.product_id"] = {"$in": ids}
    return query


async def _rows(collection: str, pipeline: list[dict]) -> list[dict]:
    return await getattr(db, collection).aggregate(pipeline, allowDiskUse=True).to_list(1000)


@router.get("/filters")
async def filters(user: UserPublic = Depends(require_roles("owner", "admin", "manager"))):
    allowed = accessible_floor_ids(user)
    floor_query = {"id": {"$in": allowed}} if allowed is not None else {}
    floors, brands, people, refs = await __import__("asyncio").gather(
        db.floors.find({**floor_query, "active": True}, {"_id": 0, "id": 1, "name": 1}).sort("name", 1).to_list(200),
        db.brands.find({}, {"_id": 0, "id": 1, "name": 1, "floor_id": 1}).sort("name", 1).to_list(5000),
        db.users.find({"active": True}, {"_id": 0, "id": 1, "full_name": 1, "role": 1}).sort("full_name", 1).to_list(500),
        db.referrers.find({}, {"_id": 0, "id": 1, "name": 1, "type": 1}).sort("name", 1).to_list(5000),
    )
    return {"floors": floors, "brands": brands, "salespeople": people, "referrers": refs}


@router.get("/dashboard")
async def dashboard(
    floor_id: Optional[str] = None, preset: str = "this_month", date_from: Optional[str] = None,
    date_to: Optional[str] = None, brand_id: Optional[str] = None, salesperson_id: Optional[str] = None,
    referrer_type: Optional[str] = None, granularity: Granularity = "month", customer_id: Optional[str] = None, referrer_id: Optional[str] = None,
    user: UserPublic = Depends(require_roles("owner", "admin", "manager")),
):
    match = await _match(user, floor_id, preset, date_from, date_to, brand_id, salesperson_id, referrer_type, customer_id, referrer_id)
    dt = {"$dateFromString": {"dateString": "$updated_at"}}
    fmt = {"day": "%Y-%m-%d", "week": "%G-W%V", "month": "%Y-%m", "year": "%Y"}.get(granularity, "%Y-Q")
    bucket = {"$dateToString": {"format": fmt, "date": dt}}
    if granularity == "quarter": bucket = {"$concat": [{"$toString": {"$year": dt}}, "-Q", {"$toString": {"$ceil": {"$divide": [{"$month": dt}, 3]}}}]}
    kpi, trend, floors, brands, products, customers, salespeople, referrals = await __import__("asyncio").gather(
        _rows("quotations", [{"$match": match}, {"$group": {"_id": None, "revenue": {"$sum": "$grand_total"}, "orders": {"$sum": 1}, "customers": {"$addToSet": "$customer_id"}, "gross_sales": {"$sum": "$subtotal"}}}]),
        _rows("quotations", [{"$match": match}, {"$group": {"_id": bucket, "revenue": {"$sum": "$grand_total"}, "orders": {"$sum": 1}}}, {"$sort": {"_id": 1}}, {"$project": {"_id": 0, "bucket": "$_id", "revenue": 1, "orders": 1}}]),
        _rows("quotations", [{"$match": match}, {"$group": {"_id": "$floor_id", "revenue": {"$sum": "$grand_total"}, "orders": {"$sum": 1}, "aov": {"$avg": "$grand_total"}}}, {"$sort": {"revenue": -1}}, {"$project": {"_id": 0, "floor_id": "$_id", "revenue": 1, "orders": 1, "aov": 1}}]),
        _rows("quotations", [{"$match": match}, {"$unwind": "$items"}, {"$lookup": {"from": "products", "localField": "items.product_id", "foreignField": "id", "as": "product"}}, {"$unwind": {"path": "$product", "preserveNullAndEmptyArrays": True}}, {"$lookup": {"from": "brands", "localField": "product.brand_id", "foreignField": "id", "as": "brand"}}, {"$unwind": {"path": "$brand", "preserveNullAndEmptyArrays": True}}, {"$group": {"_id": {"id": "$product.brand_id", "name": "$brand.name"}, "revenue": {"$sum": {"$multiply": ["$items.qty", "$items.unit_price"]}}, "quantity": {"$sum": "$items.qty"}, "orders": {"$addToSet": "$id"}}}, {"$sort": {"revenue": -1}}, {"$limit": 50}, {"$project": {"_id": 0, "brand_id": "$_id.id", "brand_name": "$_id.name", "revenue": 1, "quantity": 1, "orders": {"$size": "$orders"}}}]),
        _rows("quotations", [{"$match": match}, {"$unwind": "$items"}, {"$group": {"_id": {"id": "$items.product_id", "name": "$items.name"}, "revenue": {"$sum": {"$multiply": ["$items.qty", "$items.unit_price"]}}, "quantity": {"$sum": "$items.qty"}, "customers": {"$addToSet": "$customer_id"}}}, {"$sort": {"revenue": -1}}, {"$limit": 25}, {"$project": {"_id": 0, "product_id": "$_id.id", "name": "$_id.name", "revenue": 1, "quantity": 1, "customers": {"$size": "$customers"}}}]),
        _rows("quotations", [{"$match": match}, {"$group": {"_id": {"id": "$customer_id", "name": "$customer_name"}, "revenue": {"$sum": "$grand_total"}, "orders": {"$sum": 1}, "aov": {"$avg": "$grand_total"}, "last_purchase": {"$max": "$updated_at"}}}, {"$sort": {"revenue": -1}}, {"$limit": 25}, {"$project": {"_id": 0, "customer_id": "$_id.id", "name": "$_id.name", "revenue": 1, "orders": 1, "aov": 1, "last_purchase": 1}}]),
        _rows("quotations", [{"$match": match}, {"$group": {"_id": {"id": "$created_by", "name": "$created_by_name"}, "revenue": {"$sum": "$grand_total"}, "orders": {"$sum": 1}, "aov": {"$avg": "$grand_total"}}}, {"$sort": {"revenue": -1}}, {"$limit": 25}, {"$project": {"_id": 0, "salesperson_id": "$_id.id", "name": "$_id.name", "revenue": 1, "orders": 1, "aov": 1}}]),
        _rows("quotations", [{"$match": {**match, "referrer_id": {"$ne": None}}}, {"$group": {"_id": {"id": "$referrer_id", "name": "$referrer_name", "type": "$referrer_type"}, "revenue": {"$sum": "$grand_total"}, "orders": {"$sum": 1}, "aov": {"$avg": "$grand_total"}}}, {"$sort": {"revenue": -1}}, {"$limit": 25}, {"$project": {"_id": 0, "referrer_id": "$_id.id", "name": "$_id.name", "type": "$_id.type", "revenue": 1, "orders": 1, "aov": 1}}]),
    )
    floor_scope = {"floor_id": match["floor_id"]} if "floor_id" in match else {}
    activity_dates = {"created_at": match["updated_at"]} if "updated_at" in match else {}
    walkin_counts, selection_counts, quotation_counts, followup_counts = await __import__("asyncio").gather(
        _rows("walkins", [{"$match": {**floor_scope, **activity_dates, "is_deleted": False}}, {"$group": {"_id": "$salesperson_id", "walkins": {"$sum": 1}}}]),
        _rows("quotations", [{"$match": {**floor_scope, **activity_dates, "doc_type": "tiles_selection"}}, {"$group": {"_id": "$created_by", "selections": {"$sum": 1}}}]),
        _rows("quotations", [{"$match": {**floor_scope, **activity_dates, "doc_type": {"$in": ["tiles_quotation", "standard"]}}}, {"$group": {"_id": "$created_by", "quotations": {"$sum": 1}}}]),
        _rows("followups", [{"$match": {**floor_scope}}, {"$group": {"_id": "$assigned_to", "total": {"$sum": 1}, "completed": {"$sum": {"$cond": [{"$eq": ["$status", "done"]}, 1, 0]}}}}]),
    )
    activity_maps = [{row.get("_id"): row for row in rows} for rows in (walkin_counts, selection_counts, quotation_counts, followup_counts)]
    for row in salespeople:
        sid = row.get("salesperson_id")
        walks, selections, quotes, followups = (m.get(sid, {}) for m in activity_maps)
        row.update({"walkins": walks.get("walkins", 0), "selections": selections.get("selections", 0), "quotations": quotes.get("quotations", 0), "conversion_rate": round(row.get("orders", 0) / walks.get("walkins", 1) * 100, 1) if walks.get("walkins") else 0, "followup_completion_rate": round(followups.get("completed", 0) / followups.get("total", 1) * 100, 1) if followups.get("total") else 0})
    totals = kpi[0] if kpi else {"revenue": 0, "orders": 0, "customers": [], "gross_sales": 0}
    start, end = _date_range(preset, date_from, date_to)
    previous_revenue = 0
    if start and end:
        start_dt, end_dt = datetime.fromisoformat(start), datetime.fromisoformat(end)
        span = end_dt - start_dt
        previous_match = {**match, "updated_at": {"$gte": (start_dt - span).isoformat(), "$lt": start}}
        previous = await _rows("quotations", [{"$match": previous_match}, {"$group": {"_id": None, "revenue": {"$sum": "$grand_total"}}}])
        previous_revenue = previous[0]["revenue"] if previous else 0
    growth = round((totals["revenue"] - previous_revenue) / previous_revenue * 100, 1) if previous_revenue else (100 if totals["revenue"] else 0)
    return {"meta": {"revenue_definition": "Confirmed and completed orders only", "previous_period_revenue": round(previous_revenue, 2)}, "kpis": {"revenue": round(totals["revenue"], 2), "orders": totals["orders"], "aov": round(totals["revenue"] / totals["orders"], 2) if totals["orders"] else 0, "gross_sales": round(totals["gross_sales"], 2), "customers": len(totals["customers"]), "revenue_growth_pct": growth}, "trend": trend, "floors": floors, "brands": brands, "products": products, "customers": customers, "salespeople": salespeople, "referrals": referrals}


@router.get("/funnel")
async def funnel(
    floor_id: Optional[str] = None, preset: str = "this_month", date_from: Optional[str] = None, date_to: Optional[str] = None,
    user: UserPublic = Depends(require_roles("owner", "admin", "manager")),
):
    order_match = await _match(user, floor_id, preset, date_from, date_to, None, None, None)
    floor_match = {"floor_id": order_match["floor_id"]} if "floor_id" in order_match else {}
    start, end = _date_range(preset, date_from, date_to)
    date_match = {"created_at": {k: v for k, v in (("$gte", start), ("$lte", end)) if v}} if start or end else {}
    walkins, selections, quotes, orders, releases, dispatches, payments = await __import__("asyncio").gather(
        db.walkins.count_documents({**floor_match, **date_match, "is_deleted": False}),
        db.quotations.count_documents({**floor_match, **date_match, "doc_type": "tiles_selection"}),
        db.quotations.count_documents({**floor_match, **date_match, "doc_type": {"$in": ["tiles_quotation", "standard"]}, "status": {"$nin": ["rejected", "lost"]}}),
        db.quotations.count_documents(order_match),
        db.purchase_orders.count_documents({**floor_match, "ready_boxes": {"$gt": 0}}),
        db.purchase_orders.count_documents({**floor_match, "dispatched_boxes": {"$gt": 0}}),
        db.payments.count_documents({**floor_match, "status": "completed", **({"paid_at": {"$gte": start, "$lte": end}} if start and end else {})}),
    )
    counts = [walkins, selections, quotes, orders, releases, dispatches, payments]
    names = ["Walk-ins", "Selections", "Quotations", "Confirmed Orders", "Release", "Dispatch", "Payments"]
    revenue = (await _rows("quotations", [{"$match": order_match}, {"$group": {"_id": None, "revenue": {"$sum": "$grand_total"}}}]))
    total = revenue[0]["revenue"] if revenue else 0
    return {"stages": [{"key": name.lower().replace(" ", "_"), "label": name, "count": count, "conversion_pct": round(count / counts[0] * 100, 1) if counts[0] else 0, "dropoff_pct": round((counts[i - 1] - count) / counts[i - 1] * 100, 1) if i and counts[i - 1] else 0, "revenue": round(total if i >= 3 else 0, 2)} for i, (name, count) in enumerate(zip(names, counts))]}


@router.get("/products")
async def products(
    floor_id: Optional[str] = None, preset: str = "this_month", date_from: Optional[str] = None, date_to: Optional[str] = None,
    page: int = Query(1, ge=1), limit: int = Query(25, ge=1, le=100), user: UserPublic = Depends(require_roles("owner", "admin", "manager")),
):
    match = await _match(user, floor_id, preset, date_from, date_to, None, None, None)
    pipeline = [{"$match": match}, {"$unwind": "$items"}, {"$group": {"_id": {"id": "$items.product_id", "name": "$items.name"}, "revenue": {"$sum": {"$multiply": ["$items.qty", "$items.unit_price"]}}, "quantity": {"$sum": "$items.qty"}, "customers": {"$addToSet": "$customer_id"}, "average_price": {"$avg": "$items.unit_price"}}}, {"$sort": {"revenue": -1}}, {"$skip": (page - 1) * limit}, {"$limit": limit}, {"$project": {"_id": 0, "product_id": "$_id.id", "name": "$_id.name", "revenue": 1, "quantity": 1, "average_price": 1, "customers": {"$size": "$customers"}}}]
    return {"page": page, "items": await _rows("quotations", pipeline)}


@router.get("/brands/{brand_id}")
async def brand_detail(
    brand_id: str, floor_id: Optional[str] = None, preset: str = "this_month", date_from: Optional[str] = None,
    date_to: Optional[str] = None, granularity: Granularity = "month", user: UserPublic = Depends(require_roles("owner", "admin", "manager")),
):
    brand = await db.brands.find_one({"id": brand_id}, {"_id": 0, "id": 1, "name": 1, "floor_id": 1})
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    analytics = await dashboard(floor_id, preset, date_from, date_to, brand_id, None, None, granularity, user)
    return {"brand": brand, **analytics}


@router.get("/customers/{customer_id}")
async def customer_lifetime(
    customer_id: str, floor_id: Optional[str] = None, user: UserPublic = Depends(require_roles("owner", "admin", "manager")),
):
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    analytics = await dashboard(floor_id=floor_id, preset="all", customer_id=customer_id, user=user)
    return {"customer": customer, "lifetime": analytics}


@router.get("/salespeople/{salesperson_id}")
async def salesperson_detail(
    salesperson_id: str, floor_id: Optional[str] = None, preset: str = "this_month", user: UserPublic = Depends(require_roles("owner", "admin", "manager")),
):
    salesperson = await db.users.find_one({"id": salesperson_id}, {"_id": 0, "id": 1, "full_name": 1, "role": 1})
    if not salesperson:
        raise HTTPException(status_code=404, detail="Salesperson not found")
    analytics = await dashboard(floor_id=floor_id, preset=preset, salesperson_id=salesperson_id, user=user)
    return {"salesperson": salesperson, **analytics}


@router.get("/referrers/{referrer_id}")
async def referrer_detail(
    referrer_id: str, floor_id: Optional[str] = None, preset: str = "this_month", user: UserPublic = Depends(require_roles("owner", "admin", "manager")),
):
    referrer = await db.referrers.find_one({"id": referrer_id}, {"_id": 0})
    if not referrer:
        raise HTTPException(status_code=404, detail="Referrer not found")
    analytics = await dashboard(floor_id=floor_id, preset=preset, referrer_id=referrer_id, user=user)
    return {"referrer": referrer, **analytics}


@router.get("/export")
async def export_orders(
    format: Literal["csv", "xlsx", "pdf"] = "csv", floor_id: Optional[str] = None, preset: str = "this_month",
    date_from: Optional[str] = None, date_to: Optional[str] = None, user: UserPublic = Depends(require_roles("owner", "admin", "manager")),
):
    match = await _match(user, floor_id, preset, date_from, date_to, None, None, None)
    orders = await db.quotations.find(match, {"_id": 0, "number": 1, "updated_at": 1, "floor_id": 1, "customer_name": 1, "created_by_name": 1, "grand_total": 1, "status": 1}).sort("updated_at", -1).to_list(100000)
    rows = [[o.get("number"), o.get("updated_at"), o.get("floor_id"), o.get("customer_name"), o.get("created_by_name"), o.get("grand_total"), o.get("status")] for o in orders]
    headers = ["Order", "Confirmed at", "Floor", "Customer", "Salesperson", "Revenue", "Status"]
    filename = f"buildcon-executive-sales-{preset}"
    if format == "csv":
        output = StringIO(); writer = csv.writer(output); writer.writerow(headers); writer.writerows(rows)
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'})
    if format == "xlsx":
        from openpyxl import Workbook
        book = Workbook(); sheet = book.active; sheet.title = "Confirmed Orders"; sheet.append(headers)
        for row in rows: sheet.append(row)
        blob = BytesIO(); book.save(blob); blob.seek(0)
        return StreamingResponse(blob, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'})
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas
    blob = BytesIO(); pdf = Canvas(blob, pagesize=A4); pdf.setTitle("BuildCon House Executive Sales")
    pdf.setFont("Helvetica-Bold", 14); pdf.drawString(40, 805, "BuildCon House — Confirmed Orders")
    pdf.setFont("Helvetica", 9); y = 780
    for row in rows[:500]:
        pdf.drawString(40, y, f"{row[0]}  |  {row[3]}  |  ₹{row[5]:,.2f}")
        y -= 14
        if y < 40: pdf.showPage(); y = 800; pdf.setFont("Helvetica", 9)
    pdf.save(); blob.seek(0)
    return StreamingResponse(blob, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'})