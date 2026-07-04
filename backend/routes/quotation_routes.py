"""Quotation Builder API. Includes create, update, revision, approve, PDF."""
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


def _recalc(items: list[QuotationLineItem]) -> dict:
    subtotal = sum(i.qty * i.unit_price for i in items)
    discount_total = sum((i.qty * i.unit_price) * i.discount_pct / 100 for i in items)
    net = subtotal - discount_total
    tax_total = sum(i.tax for i in items)
    grand_total = net + tax_total
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


@router.get("")
async def list_quotations(user: UserPublic = Depends(get_current_user)):
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
    number = await _next_number()
    items = body.items or []
    totals = _recalc(items)
    quot = Quotation(
        number=number,
        customer_id=customer["id"],
        customer_name=customer.get("company") or customer["name"],
        items=items,
        rooms=body.rooms or [],
        notes=body.notes,
        valid_until=body.valid_until,
        created_by=user.id,
        created_by_name=user.full_name,
        **totals,
    )
    await db.quotations.insert_one(quot.dict())
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

    changed = False
    update: dict = {}
    if body.items is not None:
        items_typed = [QuotationLineItem(**i.dict()) if not isinstance(i, dict) else QuotationLineItem(**i) for i in body.items]
        update["items"] = [i.dict() for i in items_typed]
        update.update(_recalc(items_typed))
        changed = True
    if body.rooms is not None:
        update["rooms"] = body.rooms
        changed = True
    if body.notes is not None:
        update["notes"] = body.notes
        changed = True
    if body.valid_until is not None:
        update["valid_until"] = body.valid_until
        changed = True
    if body.status is not None:
        update["status"] = body.status
        if body.status == "approved":
            update["approved_by"] = user.id
        changed = True

    if changed:
        # revision snapshot
        revisions = doc.get("revisions", [])
        rev = QuotationRevision(
            revision_no=len(revisions) + 1,
            created_by=user.id,
            reason=body.reason,
            snapshot={k: doc.get(k) for k in ("items", "rooms", "notes", "status", "grand_total")},
        )
        update["revisions"] = revisions + [rev.dict()]
        update["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.quotations.update_one({"id": quotation_id}, {"$set": update})

    doc = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    return Quotation(**doc)


@router.delete("/{quotation_id}")
async def delete_quotation(
    quotation_id: str,
    _: UserPublic = Depends(require_min_role("manager")),
):
    res = await db.quotations.delete_one({"id": quotation_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return {"ok": True}


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
