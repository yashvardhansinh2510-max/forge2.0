"""Quotation Builder API — v2 with multi-level discounts, autosave, duplicate."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import get_current_customer, get_current_user, require_min_role
from db import db
from models import (
    CustomerPublic, PurchaseOrder, PurchaseOrderItem, PurchaseStatusEvent, PurchaseStageEvent,
    Quotation, QuotationCreate, QuotationLineItem, QuotationRevision,
    QuotationUpdate, UserPublic, now_iso,
)
from pdf_generator import build_quotation_pdf
from services.activity_log import log_event

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

    for it in items:
        gross = it.qty * it.unit_price
        pct, _ = _effective_discount_pct(it, category_discounts, project_discount_pct)
        disc = gross * pct / 100
        subtotal += gross
        discount_total += disc

    grand_total = subtotal - discount_total
    return {
        "subtotal": round(subtotal, 2),
        "discount_total": round(discount_total, 2),
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
    await log_event(
        event_type="quotation.created",
        entity_type="quotation",
        entity_id=quot.id,
        actor=user,
        customer_id=customer["id"],
        quotation_id=quot.id,
        summary=f"{quot.number} · {quot.customer_name} · {len(items)} items",
        payload={"items": len(items), "grand_total": quot.grand_total},
    )
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

    # Activity logging (non-silent only — silent = autosave)
    if not body.silent:
        events: list[tuple[str, str, dict]] = []
        prev_items = doc.get("items", [])
        new_items = update.get("items", prev_items)
        if "items" in update:
            prev_ids = {i["product_id"] for i in prev_items}
            new_ids = {i["product_id"] for i in new_items}
            added = new_ids - prev_ids
            removed = prev_ids - new_ids
            for pid in added:
                match = next((i for i in new_items if i["product_id"] == pid), None)
                if match:
                    events.append(("quotation.product_added", f"Added {match.get('name', 'product')}", {"sku": match.get("sku")}))
            for pid in removed:
                match = next((i for i in prev_items if i["product_id"] == pid), None)
                if match:
                    events.append(("quotation.product_removed", f"Removed {match.get('name', 'product')}", {"sku": match.get("sku")}))
            if not added and not removed and prev_items != new_items:
                events.append(("quotation.product_reordered", "Line items updated", {}))
        if "project_discount_pct" in update or "category_discounts" in update:
            events.append(("quotation.discount_changed", "Discount changed", {
                "project": update.get("project_discount_pct", doc.get("project_discount_pct")),
                "categories": update.get("category_discounts", doc.get("category_discounts")),
            }))
        if "rooms" in update:
            prev = doc.get("rooms", [])
            new = update["rooms"]
            added = [r for r in new if r not in prev]
            removed = [r for r in prev if r not in new]
            for r in added:
                events.append(("quotation.room_created", f"Room '{r}' added", {"room": r}))
            for r in removed:
                events.append(("quotation.room_deleted", f"Room '{r}' removed", {"room": r}))
        if "status" in update:
            events.append((
                "quotation.status_changed",
                f"Status changed to {update['status'].replace('_', ' ')}",
                {"from": doc.get("status"), "to": update["status"]},
            ))
        if "notes" in update:
            events.append(("quotation.saved", "Notes updated", {}))
        # revision event captured separately below (already appended to revisions)
        events.append(("quotation.revision_created", f"Revision {len(revisions) + 1} saved", {"reason": body.reason}))

        for etype, summary, payload in events:
            await log_event(
                event_type=etype, entity_type="quotation", entity_id=quotation_id,
                actor=user, customer_id=doc.get("customer_id"), quotation_id=quotation_id,
                summary=summary, payload=payload,
            )

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
            discount_pct=i.get("discount_pct"),
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
        lines_out.append({
            "line_id": it.id, "product_id": it.product_id, "sku": it.sku, "name": it.name,
            "qty": it.qty, "unit_price": it.unit_price, "gross": round(gross, 2),
            "discount_pct": pct, "discount_source": source, "discount_amount": round(disc, 2),
            "net": round(net, 2),
            "total": round(net, 2),
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
async def quotation_pdf(quotation_id: str, user: UserPublic = Depends(get_current_user)):
    doc = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    customer = await db.customers.find_one({"id": doc["customer_id"]}, {"_id": 0, "password_hash": 0}) or {}
    pdf_bytes = build_quotation_pdf(doc, customer)
    await log_event(
        event_type="quotation.pdf_generated",
        entity_type="quotation",
        entity_id=quotation_id,
        actor=user,
        customer_id=doc.get("customer_id"),
        quotation_id=quotation_id,
        summary="Quotation PDF generated",
    )
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


# =============================================================================
# Place Order — brand-grouped preview + confirmation → seeds Purchase Orders.
# =============================================================================
class PlaceOrderConfirmPayload(BaseModel):
    """Optional supplier assignment + notes when confirming the order."""
    supplier_by_brand: dict[str, str] = {}          # {brand_id: supplier_id}
    notes_by_brand: dict[str, str] = {}             # {brand_id: internal_notes}
    expected_delivery_at: str | None = None
    project_name: str | None = None


async def _brand_grouped_preview(doc: dict) -> dict:
    """Group quotation lines by BRAND. Returns cards ready for the review screen."""
    items = doc.get("items", [])
    if not items:
        return {"quotation_id": doc["id"], "quotation_number": doc.get("number"), "brands": []}

    # Fetch products (once) so we can enrich items with brand info + supplier hint.
    product_ids = list({i["product_id"] for i in items})
    products = await db.products.find(
        {"id": {"$in": product_ids}}, {"_id": 0, "id": 1, "brand_id": 1, "mrp": 1, "price": 1},
    ).to_list(len(product_ids) + 5)
    product_map = {p["id"]: p for p in products}

    brand_ids = list({product_map.get(i["product_id"], {}).get("brand_id") for i in items if product_map.get(i["product_id"])})
    brands = await db.brands.find({"id": {"$in": brand_ids}}, {"_id": 0}).to_list(len(brand_ids) + 5)
    brand_map = {b["id"]: b for b in brands}

    # Pick a default supplier per brand (first active one).
    suppliers = await db.suppliers.find({"brand_id": {"$in": brand_ids}, "active": True}, {"_id": 0}).to_list(200)
    default_supplier_by_brand: dict[str, dict] = {}
    for s in suppliers:
        if s.get("brand_id") and s["brand_id"] not in default_supplier_by_brand:
            default_supplier_by_brand[s["brand_id"]] = s

    grouped: dict[str, dict] = defaultdict(lambda: {
        "brand_id": None, "brand_name": "Unassigned", "items": [], "subtotal": 0.0,
        "default_supplier": None,
    })
    for it in items:
        prod = product_map.get(it["product_id"], {})
        brand_id = prod.get("brand_id") or "__unassigned__"
        brand_name = brand_map.get(brand_id, {}).get("name", "Unassigned") if brand_id != "__unassigned__" else "Unassigned"
        # Cost = quotation unit_price by default (dealer margin adjusted later)
        unit_cost = float(it.get("unit_price", 0))
        grouped[brand_id]["brand_id"] = brand_id if brand_id != "__unassigned__" else None
        grouped[brand_id]["brand_name"] = brand_name
        grouped[brand_id]["items"].append({
            "line_id": it.get("id"),
            "product_id": it["product_id"],
            "sku": it["sku"],
            "name": it["name"],
            "image": it.get("image"),
            "category_id": it.get("category_id"),
            "room": it.get("room"),
            "qty": float(it.get("qty", 1)),
            "unit_cost": unit_cost,
        })
        grouped[brand_id]["subtotal"] += unit_cost * float(it.get("qty", 1))
        if default_supplier_by_brand.get(brand_id) and not grouped[brand_id]["default_supplier"]:
            s = default_supplier_by_brand[brand_id]
            grouped[brand_id]["default_supplier"] = {"id": s["id"], "name": s["name"]}

    cards = []
    for b in grouped.values():
        b["subtotal"] = round(b["subtotal"], 2)
        b["item_count"] = len(b["items"])
        cards.append(b)
    cards.sort(key=lambda c: c["brand_name"])

    return {
        "quotation_id": doc["id"],
        "quotation_number": doc.get("number"),
        "customer_id": doc.get("customer_id"),
        "customer_name": doc.get("customer_name"),
        "brands": cards,
        "total_value": round(sum(c["subtotal"] for c in cards), 2),
    }


@router.get("/{quotation_id}/place-order/preview")
async def place_order_preview(
    quotation_id: str,
    _: UserPublic = Depends(require_min_role("sales")),
):
    """Preview brand-grouped POs before creating them. Non-mutating."""
    doc = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if not doc.get("items"):
        raise HTTPException(status_code=400, detail="Cannot place order — quotation has no items")
    return await _brand_grouped_preview(doc)


async def _next_po_number_local() -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"FPO-{year}-"
    n = await db.purchase_orders.count_documents({"number": {"$regex": f"^{prefix}"}})
    return f"{prefix}{n + 1:04d}"


@router.post("/{quotation_id}/place-order/confirm")
async def place_order_confirm(
    quotation_id: str,
    body: PlaceOrderConfirmPayload,
    user: UserPublic = Depends(require_min_role("sales")),
):
    """Create Draft POs (one per brand), mark quotation as ordered."""
    doc = await db.quotations.find_one({"id": quotation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if doc.get("status") == "ordered":
        raise HTTPException(status_code=400, detail="Order already placed for this quotation")

    preview = await _brand_grouped_preview(doc)
    if not preview["brands"]:
        raise HTTPException(status_code=400, detail="Quotation has no items")

    created_pos: list[dict] = []
    for card in preview["brands"]:
        brand_id = card.get("brand_id")
        supplier_id = body.supplier_by_brand.get(brand_id or "") or None
        supplier_name = None
        if supplier_id:
            s = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0, "name": 1})
            if s:
                supplier_name = s["name"]
        elif card.get("default_supplier"):
            supplier_id = card["default_supplier"]["id"]
            supplier_name = card["default_supplier"]["name"]

        # Build PO items — each carries denormalized customer + brand info so
        # the material tracker can filter without joins.
        now = now_iso()
        po_items = [
            PurchaseOrderItem(
                product_id=it["product_id"], sku=it["sku"], name=it["name"],
                image=it.get("image"), category_id=it.get("category_id"),
                room=it.get("room"), qty=it["qty"], unit_cost=it["unit_cost"],
                quotation_line_id=it.get("line_id"),
                stage="order_in_company",
                customer_id=doc["customer_id"],
                customer_name=doc.get("customer_name", ""),
                brand_id=brand_id,
                brand_name=card.get("brand_name"),
                last_moved_at=now,
                last_moved_by=user.id,
                last_moved_by_name=user.full_name,
                stage_history=[
                    PurchaseStageEvent(
                        from_stage=None, to_stage="order_in_company",
                        by_user_id=user.id, by_user_name=user.full_name,
                        note=f"Created from {doc.get('number')}",
                        action="create",
                    )
                ],
            )
            for it in card["items"]
        ]
        subtotal = sum(i.qty * i.unit_cost for i in po_items)

        number = await _next_po_number_local()
        po = PurchaseOrder(
            number=number,
            quotation_id=quotation_id,
            quotation_number=doc.get("number"),
            customer_id=doc["customer_id"],
            customer_name=doc.get("customer_name", ""),
            project_name=body.project_name,
            brand_id=brand_id,
            brand_name=card.get("brand_name"),
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            status="draft",
            items=po_items,
            internal_notes=body.notes_by_brand.get(brand_id or "") if body.notes_by_brand else None,
            expected_delivery_at=body.expected_delivery_at,
            subtotal=round(subtotal, 2),
            grand_total=round(subtotal, 2),
            created_by=user.id,
            created_by_name=user.full_name,
            status_history=[
                PurchaseStatusEvent(
                    from_status=None, to_status="draft",
                    by_user_id=user.id, by_user_name=user.full_name,
                    note=f"Auto-generated from {doc.get('number')}",
                ).dict()
            ],
        )
        await db.purchase_orders.insert_one(po.dict())
        created_pos.append(po.dict())

        # Activity events
        await log_event(
            event_type="purchase.created",
            entity_type="purchase",
            entity_id=po.id,
            actor=user,
            customer_id=doc["customer_id"],
            quotation_id=quotation_id,
            purchase_id=po.id,
            summary=f"{po.number} · {po.brand_name} · {len(po_items)} items",
            payload={"brand_id": brand_id, "supplier_id": supplier_id, "item_count": len(po_items)},
        )

    # Mark quotation ordered
    await db.quotations.update_one(
        {"id": quotation_id},
        {"$set": {
            "status": "ordered",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    await log_event(
        event_type="quotation.order_placed",
        entity_type="quotation",
        entity_id=quotation_id,
        actor=user,
        customer_id=doc["customer_id"],
        quotation_id=quotation_id,
        summary=f"Order placed — {len(created_pos)} Purchase Orders generated",
        payload={"po_count": len(created_pos), "po_ids": [p["id"] for p in created_pos]},
    )
    await log_event(
        event_type="quotation.status_changed",
        entity_type="quotation",
        entity_id=quotation_id,
        actor=user,
        customer_id=doc["customer_id"],
        quotation_id=quotation_id,
        summary=f"Status changed to ordered",
        payload={"from": doc.get("status"), "to": "ordered"},
    )

    return {
        "quotation_id": quotation_id,
        "purchase_orders": created_pos,
        "count": len(created_pos),
    }
