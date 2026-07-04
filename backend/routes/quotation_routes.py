"""Quotation Builder API — v2 with multi-level discounts, autosave, duplicate."""
from copy import deepcopy
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from auth import get_current_customer, get_current_user, require_min_role
from db import db
from models import (
    CustomerPublic, Quotation, QuotationCreate, QuotationLineItem,
    QuotationRevision, QuotationUpdate, UserPublic,
)
from pdf_generator import build_quotation_pdf

router = APIRouter(prefix="/quotations", tags=["quotations"])


def _effective_discount_pct(
    line: QuotationLineItem,
    category_discounts: dict[str, float],
    project_discount_pct: float,
) -> tuple[float, str]:
    """Return (pct, source) — Product override > Category > Project."""
    if line.discount_pct is not None:
        return float(line.discount_pct), "product"
    if line.category_id and line.category_id in category_discounts:
        return float(category_discounts[line.category_id]), "category"
    if project_discount_pct:
        return float(project_discount_pct), "project"
    return 0.0, "none"


def _recalc(
    items: list[QuotationLineItem],
    project_discount_pct: float = 0.0,
    category_discounts: dict[str, float] | None = None,
) -> dict:
    category_discounts = category_discounts or {}
    subtotal = 0.0
    discount_total = 0.0
    tax_total = 0.0

    for it in items:
        gross = it.qty * it.unit_price
        pct, _ = _effective_discount_pct(it, category_discounts, project_discount_pct)
        disc = gross * pct / 100
        net = gross - disc
        tax = net * (it.tax_pct or 0) / 100
        subtotal += gross
        discount_total += disc
        tax_total += tax

    grand_total = subtotal - discount_total + tax_total
    return {
        "subtotal": round(subtotal, 2),
        "discount_total": round(discount_total, 2),
        "tax_total": round(tax_total, 2),
        "grand_total": round(grand_total, 2),
    }


async def _next_number() -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"FQ-{year}-"
    count = await db.quotations.count_documents({"number": {"$regex": f"^{prefix}"}})
    return f"{prefix}{count + 1:04d}"


async def _track_product_usage(user_id: str, product_ids: list[str]):
    """Bump usage counters for the picker's Recent/Frequent tabs."""
    now = datetime.now(timezone.utc).isoformat()
    for pid in set(product_ids):
        await db.product_usage.update_one(
            {"user_id": user_id, "product_id": pid},
            {"$inc": {"count": 1}, "$set": {"last_used_at": now}},
            upsert=True,
        )


@router.get("")
async def list_quotations(_: UserPublic = Depends(get_current_user)):
    docs = await db.quotations.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return docs


@router.post("", response_model=Quotation)
async def create_quotation(
    body: QuotationCreate,
    user: UserPublic = Depends(require_min_role("sales")),
):
    customer = await db.customers.find_one({"id": body.customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Fill category_id on items so category discounts can resolve later.
    items = body.items or []
    for it in items:
        if not it.category_id:
            p = await db.products.find_one({"id": it.product_id}, {"_id": 0, "category_id": 1})
            if p:
                it.category_id = p.get("category_id")

    totals = _recalc(items, body.project_discount_pct or 0, body.category_discounts or {})
    quot = Quotation(
        number=await _next_number(),
        customer_id=customer["id"],
        customer_name=customer.get("company") or customer["name"],
        items=items,
        rooms=body.rooms or [],
        project_discount_pct=body.project_discount_pct or 0,
        category_discounts=body.category_discounts or {},
        notes=body.notes,
        valid_until=body.valid_until,
        created_by=user.id,
        created_by_name=user.full_name,
        **totals,
    )
    await db.quotations.insert_one(quot.dict())
    await _track_product_usage(user.id, [it.product_id for it in items])
    return quot


@router.get("/{quotation_id}", response_model=Quotation)
async def get_quotation(quotation_id: str, _: UserPublic = Depends(get_current_user)):
    doc = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return Quotation(**doc)


@router.patch("/{quotation_id}", response_model=Quotation)
async def update_quotation(
    quotation_id: str,
    body: QuotationUpdate,
    user: UserPublic = Depends(require_min_role("sales")),
):
    doc = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")

    update: dict = {}
    if body.items is not None:
        items_typed = [
            QuotationLineItem(**i.dict()) if not isinstance(i, dict) else QuotationLineItem(**i)
            for i in body.items
        ]
        # Backfill category_id
        for it in items_typed:
            if not it.category_id:
                p = await db.products.find_one({"id": it.product_id}, {"_id": 0, "category_id": 1})
                if p:
                    it.category_id = p.get("category_id")
        update["items"] = [i.dict() for i in items_typed]
        await _track_product_usage(user.id, [it.product_id for it in items_typed])

    if body.rooms is not None:
        update["rooms"] = body.rooms
    if body.collapsed_rooms is not None:
        update["collapsed_rooms"] = body.collapsed_rooms
    if body.notes is not None:
        update["notes"] = body.notes
    if body.valid_until is not None:
        update["valid_until"] = body.valid_until
    if body.project_discount_pct is not None:
        update["project_discount_pct"] = float(body.project_discount_pct)
    if body.category_discounts is not None:
        update["category_discounts"] = body.category_discounts
    if body.status is not None:
        update["status"] = body.status
        if body.status == "approved":
            update["approved_by"] = user.id

    # Recalc totals if anything pricing-related changed
    if any(k in update for k in ("items", "project_discount_pct", "category_discounts")):
        items_for_calc = [
            QuotationLineItem(**i) for i in update.get("items", doc.get("items", []))
        ]
        totals = _recalc(
            items_for_calc,
            update.get("project_discount_pct", doc.get("project_discount_pct", 0)),
            update.get("category_discounts", doc.get("category_discounts", {})),
        )
        update.update(totals)

    if not update:
        return Quotation(**doc)

    # revision snapshot (unless silent autosave)
    if not body.silent:
        revisions = doc.get("revisions", [])
        rev = QuotationRevision(
            revision_no=len(revisions) + 1,
            created_by=user.id,
            reason=body.reason,
            snapshot={k: doc.get(k) for k in ("items", "rooms", "notes", "status", "grand_total", "project_discount_pct", "category_discounts")},
        )
        update["revisions"] = revisions + [rev.dict()]

    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.quotations.update_one({"id": quotation_id}, {"$set": update})

    fresh = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    return Quotation(**fresh)


@router.delete("/{quotation_id}")
async def delete_quotation(
    quotation_id: str,
    _: UserPublic = Depends(require_min_role("manager")),
):
    res = await db.quotations.delete_one({"id": quotation_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return {"ok": True}


@router.post("/{quotation_id}/duplicate", response_model=Quotation)
async def duplicate_quotation(
    quotation_id: str,
    user: UserPublic = Depends(require_min_role("sales")),
):
    src = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Quotation not found")

    body = QuotationCreate(
        customer_id=src["customer_id"],
        items=[],
        rooms=src.get("rooms", []),
        notes=src.get("notes"),
        valid_until=src.get("valid_until"),
        project_discount_pct=src.get("project_discount_pct", 0),
        category_discounts=src.get("category_discounts", {}),
    )
    # Build fresh line items so ids are regenerated by the default_factory.
    body.items = [
        QuotationLineItem(
            product_id=i["product_id"], sku=i["sku"], name=i["name"], image=i.get("image"),
            category_id=i.get("category_id"), room=i.get("room"),
            qty=i["qty"], unit_price=i["unit_price"],
            discount_pct=i.get("discount_pct"), tax_pct=i.get("tax_pct", 18),
            notes=i.get("notes"), description=i.get("description"),
            sort_order=i.get("sort_order", 0),
        )
        for i in src.get("items", [])
    ]
    return await create_quotation(body, user)


# --- Breakdown (for line + totals transparency) ---
@router.get("/{quotation_id}/breakdown")
async def quotation_breakdown(quotation_id: str, _: UserPublic = Depends(get_current_user)):
    """How the final numbers were calculated — per line + summary."""
    doc = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")

    project_pct = doc.get("project_discount_pct", 0)
    cat_discs = doc.get("category_discounts", {}) or {}
    lines_out = []
    for raw in doc.get("items", []):
        it = QuotationLineItem(**raw)
        gross = it.qty * it.unit_price
        pct, source = _effective_discount_pct(it, cat_discs, project_pct)
        disc = gross * pct / 100
        net = gross - disc
        tax = net * (it.tax_pct or 0) / 100
        lines_out.append({
            "line_id": it.id, "product_id": it.product_id, "sku": it.sku, "name": it.name,
            "qty": it.qty, "unit_price": it.unit_price, "gross": round(gross, 2),
            "discount_pct": pct, "discount_source": source, "discount_amount": round(disc, 2),
            "net": round(net, 2), "tax_pct": it.tax_pct, "tax_amount": round(tax, 2),
            "total": round(net + tax, 2),
        })

    totals = _recalc([QuotationLineItem(**i) for i in doc.get("items", [])], project_pct, cat_discs)
    return {
        "lines": lines_out,
        "totals": totals,
        "project_discount_pct": project_pct,
        "category_discounts": cat_discs,
    }


# --- PDF (staff) ---
@router.get("/{quotation_id}/pdf")
async def quotation_pdf(quotation_id: str, _: UserPublic = Depends(get_current_user)):
    doc = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    customer = await db.customers.find_one({"id": doc["customer_id"]}, {"_id": 0, "password_hash": 0}) or {}
    pdf_bytes = build_quotation_pdf(doc, customer)
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc["number"]}.pdf"'},
    )


# --- PDF (customer portal) ---
@router.get("/{quotation_id}/portal-pdf")
async def portal_pdf(quotation_id: str, cust: CustomerPublic = Depends(get_current_customer)):
    doc = await db.quotations.find_one({"id": quotation_id, "customer_id": cust.id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    pdf_bytes = build_quotation_pdf(doc, cust.dict())
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc["number"]}.pdf"'},
    )
