"""Transactional domain event outbox for the quotation production workflow.

Commands write only their primary aggregate state plus one EventOutbox record in
one MongoDB transaction. The dispatcher runs after commit and handlers own the
secondary read models. Every handler is keyed by event.idempotency_key so a
retry is safe after a process/network failure.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from auth import floor_inherit
from db import client, db
from models import ActivityEvent, Followup, Payment, PurchaseOrder, PurchaseOrderItem, PurchaseStageEvent, PurchaseStatusEvent, UserPublic
from services.notifications import notify
from services.pricing import per_line_net_amounts
from services.sequence import next_number

EVENT_QUOTATION_GENERATED = "QuotationGenerated"
EVENT_ORDER_PLACED = "OrderPlaced"
EVENT_PURCHASE_TRANSFERRED = "PurchaseTransferred"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ensure_outbox_indexes() -> None:
    """Indexes make command/outbox and handler effects idempotent at the DB level."""
    await db.event_outbox.create_index("idempotency_key", unique=True, name="outbox_idempotency")
    await db.event_outbox.create_index([("status", 1), ("created_at", 1)], name="outbox_dispatch_queue")
    await db.purchase_orders.create_index("automation_key", unique=True, sparse=True, name="po_automation_key")
    await db.payments.create_index("automation_key", unique=True, sparse=True, name="payment_automation_key")
    await db.payments.create_index("idempotency_key", unique=True, sparse=True, name="payment_idempotency_key")
    await db.activity_events.create_index("automation_key", unique=True, sparse=True, name="activity_automation_key")
    await db.followups.create_index("automation_key", unique=True, sparse=True, name="followup_automation_key")


async def enqueue_after_primary_commit(
    *,
    event_type: str,
    idempotency_key: str,
    payload: dict[str, Any],
    actor: UserPublic,
    session: Any,
) -> dict:
    """Insert exactly one outbox journal row inside the caller transaction."""
    event = {
        "id": str(uuid4()),
        "event_type": event_type,
        "idempotency_key": idempotency_key,
        "payload": payload,
        "actor_id": actor.id,
        "actor_name": actor.full_name,
        "status": "pending",
        "attempts": 0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.event_outbox.insert_one(event, session=session)
    return event


async def _upsert_activity(*, key: str, event_type: str, entity_type: str, entity_id: str, actor_id: str, actor_name: str, customer_id: str | None, quotation_id: str | None, purchase_id: str | None, summary: str, payload: dict, session: Any) -> None:
    event = ActivityEvent(
        event_type=event_type,
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_id=entity_id,
        actor_id=actor_id,
        actor_name=actor_name,
        customer_id=customer_id,
        quotation_id=quotation_id,
        purchase_id=purchase_id,
        summary=summary,
        payload=payload,
    ).dict()
    event["automation_key"] = key
    await db.activity_events.update_one({"automation_key": key}, {"$setOnInsert": event}, upsert=True, session=session)


async def _upsert_followup(*, key: str, quotation: dict, reason: str, category: str, session: Any) -> None:
    customer = await db.customers.find_one({"id": quotation["customer_id"]}, {"_id": 0}, session=session) or {}
    followup = Followup(
        source_key=key,
        rule_type="manual",
        category=category,  # type: ignore[arg-type]
        customer_id=quotation["customer_id"],
        customer_name=quotation.get("customer_name", ""),
        customer_phone=customer.get("phone"),
        customer_tier=customer.get("tier", "retail"),
        quotation_id=quotation["id"],
        quotation_number=quotation.get("number"),
        project_name=quotation.get("project_name"),
        value=round(float(quotation.get("grand_total") or 0), 2),
        reason=reason,
        next_action="Review with customer",
        next_action_reason="Created by the quotation workflow.",
        suggested_channel="call",
        due_at=now_iso(),
        is_automated=False,
        floor_id=floor_inherit(quotation),
    ).dict()
    followup["automation_key"] = key
    await db.followups.update_one({"automation_key": key}, {"$setOnInsert": followup}, upsert=True, session=session)


async def _next_po_number(session: Any) -> str:
    year = datetime.now(timezone.utc).year
    return await next_number("purchase_order", f"FPO-{year}-", collection="purchase_orders", session=session)


async def _brand_groups(quotation: dict, session: Any) -> list[dict]:
    product_ids = list({item["product_id"] for item in quotation.get("items", [])})
    products = await db.products.find({"id": {"$in": product_ids}}, {"_id": 0, "id": 1, "brand_id": 1}, session=session).to_list(len(product_ids) + 5)
    product_by_id = {product["id"]: product for product in products}
    brand_ids = list({p.get("brand_id") for p in products if p.get("brand_id")})
    brands = await db.brands.find({"id": {"$in": brand_ids}}, {"_id": 0}, session=session).to_list(len(brand_ids) + 5)
    brand_by_id = {brand["id"]: brand for brand in brands}
    suppliers = await db.suppliers.find({"brand_id": {"$in": brand_ids}, "active": True}, {"_id": 0}, session=session).to_list(200)
    supplier_by_brand: dict[str, dict] = {}
    for supplier in suppliers:
        supplier_by_brand.setdefault(supplier.get("brand_id"), supplier)

    groups: dict[str, dict] = {}
    for item in quotation.get("items", []):
        product = product_by_id.get(item["product_id"], {})
        brand_id = product.get("brand_id") or "__unassigned__"
        group = groups.setdefault(brand_id, {
            "brand_id": None if brand_id == "__unassigned__" else brand_id,
            "brand_name": brand_by_id.get(brand_id, {}).get("name", "Unassigned"),
            "supplier": supplier_by_brand.get(brand_id),
            "items": [],
        })
        group["items"].append(item)
    return list(groups.values())


async def _handle_quotation_generated(event: dict, session: Any) -> dict:
    quotation_id = event["payload"]["quotation_id"]
    quotation = await db.quotations.find_one({"id": quotation_id}, {"_id": 0}, session=session)
    if not quotation:
        raise RuntimeError(f"Quotation {quotation_id} no longer exists")
    key = event["idempotency_key"]
    await _upsert_activity(
        key=f"{key}:timeline", event_type="quotation.pdf_generated", entity_type="quotation", entity_id=quotation_id,
        actor_id=event["actor_id"], actor_name=event["actor_name"], customer_id=quotation.get("customer_id"), quotation_id=quotation_id, purchase_id=None,
        summary=f"Quotation generated · revision {event['payload']['revision']}",
        payload={"event": EVENT_QUOTATION_GENERATED, "revision": event["payload"]["revision"], "pdf": True}, session=session,
    )
    await _upsert_followup(key=f"{key}:followup", quotation=quotation, reason=f"Quotation {quotation.get('number')} generated — review with customer.", category="quotation", session=session)
    return {"quotation_id": quotation_id, "revision": event["payload"]["revision"]}


async def _handle_order_placed(event: dict, session: Any) -> dict:
    quotation_id = event["payload"]["quotation_id"]
    quotation = await db.quotations.find_one({"id": quotation_id}, {"_id": 0}, session=session)
    if not quotation:
        raise RuntimeError(f"Quotation {quotation_id} no longer exists")
    key = event["idempotency_key"]
    groups = await _brand_groups(quotation, session)
    # Resolve every line's EFFECTIVE (post product/room/category/project
    # discount) total ONCE, from the full quotation — not per brand-group —
    # so a discount configured at room/category/project level (rather than
    # stamped on the line itself) is preserved into the PO's unit_cost
    # instead of silently falling back to the full undiscounted price.
    net_by_line = per_line_net_amounts(quotation)
    created_po_ids: list[str] = []
    for group in groups:
        brand_key = group["brand_id"] or "unassigned"
        po_key = f"{key}:po:{brand_key}"
        existing = await db.purchase_orders.find_one({"automation_key": po_key}, {"_id": 0, "id": 1}, session=session)
        if existing:
            created_po_ids.append(existing["id"])
            continue
        now = now_iso()
        po_items = []
        for raw in group["items"]:
            qty = float(raw.get("qty") or 0)
            net_total = net_by_line.get(raw.get("id"))
            if net_total is None:
                # Line wasn't found in the breakdown (shouldn't happen) — fall
                # back to the raw per-line discount rather than full price.
                unit_cost = round(float(raw.get("unit_price") or 0) * (1 - float(raw.get("discount_pct") or 0) / 100), 2)
            else:
                unit_cost = round(net_total / qty, 2) if qty else 0.0
            po_items.append(PurchaseOrderItem(
                product_id=raw["product_id"], sku=raw["sku"], name=raw["name"], image=raw.get("image"), finish=raw.get("finish"), category_id=raw.get("category_id"), room=raw.get("room"),
                qty=qty, unit_cost=unit_cost, quotation_line_id=raw.get("id"), stage="order_in_company",
                customer_id=quotation["customer_id"], customer_name=quotation.get("customer_name", ""), brand_id=group["brand_id"], brand_name=group["brand_name"],
                last_moved_at=now, last_moved_by=event["actor_id"], last_moved_by_name=event["actor_name"],
                stage_history=[PurchaseStageEvent(from_stage=None, to_stage="order_in_company", by_user_id=event["actor_id"], by_user_name=event["actor_name"], note=f"Created from {quotation.get('number')}", action="create")],
            ))
        supplier = group.get("supplier") or {}
        po = PurchaseOrder(
            number=await _next_po_number(session), quotation_id=quotation_id, quotation_number=quotation.get("number"),
            customer_id=quotation["customer_id"], customer_name=quotation.get("customer_name", ""), project_name=quotation.get("project_name"),
            brand_id=group["brand_id"], brand_name=group["brand_name"], supplier_id=supplier.get("id"), supplier_name=supplier.get("name"),
            status="draft", items=po_items, subtotal=round(sum(item.qty * item.unit_cost for item in po_items), 2),
            grand_total=round(sum(item.qty * item.unit_cost for item in po_items), 2), created_by=event["actor_id"], created_by_name=event["actor_name"],
            floor_id=floor_inherit(quotation),
            status_history=[PurchaseStatusEvent(from_status=None, to_status="draft", by_user_id=event["actor_id"], by_user_name=event["actor_name"], note=f"Created from {quotation.get('number')}")],
        ).dict()
        po["automation_key"] = po_key
        await db.purchase_orders.insert_one(po, session=session)
        created_po_ids.append(po["id"])

    payment_key = f"{key}:payment"
    payment = Payment(
        quotation_id=quotation_id, quotation_number=quotation.get("number"), customer_id=quotation["customer_id"], customer_name=quotation.get("customer_name"),
        amount=round(float(quotation.get("grand_total") or 0), 2), mode="bank", status="pending", note="Outstanding balance created by OrderPlaced automation.",
        recorded_by=event["actor_id"], recorded_by_name=event["actor_name"],
        floor_id=floor_inherit(quotation),
    ).dict()
    payment["automation_key"] = payment_key
    await db.payments.update_one({"automation_key": payment_key}, {"$setOnInsert": payment}, upsert=True, session=session)
    await _upsert_activity(
        key=f"{key}:timeline", event_type="quotation.order_placed", entity_type="quotation", entity_id=quotation_id,
        actor_id=event["actor_id"], actor_name=event["actor_name"], customer_id=quotation.get("customer_id"), quotation_id=quotation_id, purchase_id=None,
        summary=f"Order placed — {len(created_po_ids)} purchase order(s) created",
        payload={"event": EVENT_ORDER_PLACED, "purchase_order_ids": created_po_ids, "outstanding": payment["amount"]}, session=session,
    )
    await _upsert_followup(key=f"{key}:followup", quotation=quotation, reason=f"Order {quotation.get('number')} placed — confirm payment and delivery plan.", category="payment", session=session)
    asyncio.create_task(notify(
        quotation.get("created_by"),
        f"Order confirmed · {quotation.get('number')}",
        body=f"{len(created_po_ids)} purchase order(s) created for {quotation.get('customer_name')} — outstanding ₹{payment['amount']:,.0f}",
        kind="success",
        link=f"/quotations/{quotation_id}",
    ))
    return {"quotation_id": quotation_id, "purchase_order_ids": created_po_ids, "payment_amount": payment["amount"], "count": len(created_po_ids)}


async def dispatch_event(event_id: str) -> dict:
    """Run one committed outbox event. Any failure leaves it pending for retry."""
    event = await db.event_outbox.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise RuntimeError("Outbox event not found")
    if event.get("status") == "completed":
        return event.get("result") or {"already_processed": True}
    async with await client.start_session() as session:
        async with session.start_transaction():
            current = await db.event_outbox.find_one({"id": event_id}, {"_id": 0}, session=session)
            if not current or current.get("status") == "completed":
                return (current or {}).get("result") or {"already_processed": True}
            if current["event_type"] == EVENT_QUOTATION_GENERATED:
                result = await _handle_quotation_generated(current, session)
            elif current["event_type"] == EVENT_ORDER_PLACED:
                result = await _handle_order_placed(current, session)
            elif current["event_type"] == EVENT_PURCHASE_TRANSFERRED:
                from services.transfer_workflow import handle_purchase_transferred
                result = await handle_purchase_transferred(current, session)
            else:
                raise RuntimeError(f"Unsupported outbox event type {current['event_type']}")
            await db.event_outbox.update_one({"id": event_id}, {"$set": {"status": "completed", "result": result, "processed_at": now_iso(), "updated_at": now_iso()}, "$inc": {"attempts": 1}}, session=session)
            return result


MAX_DISPATCH_ATTEMPTS = 8
WORKER_INTERVAL_SECONDS = 30


async def dispatch_pending(limit: int = 100) -> list[dict]:
    events = await db.event_outbox.find(
        {"status": "pending", "attempts": {"$lt": MAX_DISPATCH_ATTEMPTS}},
        {"_id": 0, "id": 1, "attempts": 1},
    ).sort("created_at", 1).to_list(limit)
    results = []
    for event in events:
        try:
            results.append(await dispatch_event(event["id"]))
        except Exception as exc:  # Persist failure safely; retry remains possible.
            exhausted = int(event.get("attempts") or 0) + 1 >= MAX_DISPATCH_ATTEMPTS
            patch: dict = {"last_error": str(exc), "updated_at": now_iso()}
            if exhausted:
                # Dead-letter: stop retrying, keep the event for operator review
                # via GET /api/ops/outbox. Nothing is deleted.
                patch["status"] = "dead_letter"
            await db.event_outbox.update_one({"id": event["id"]}, {"$set": patch, "$inc": {"attempts": 1}})
    return results


async def outbox_worker() -> None:
    """Continuously drain committed events so automation never waits for a
    restart or a lucky request. Runs for the process lifetime; each cycle is
    isolated so one bad event or a transient DB error can't kill the loop."""
    import logging
    logger = logging.getLogger("forge.outbox")
    while True:
        try:
            await dispatch_pending()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Outbox dispatch cycle failed; retrying next cycle")
        await asyncio.sleep(WORKER_INTERVAL_SECONDS)
