"""Activity timelines — read-model over `activity_events`.

Consumed by:
  * Global recent-activity feed (dashboard)
  * Quotation timeline (inside quotation detail)
  * Purchase order timeline (inside PO detail)
  * Customer profile timeline
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from auth import floor_query, floor_scope_ids, get_current_user, get_floor_scoped_or_404
from db import db
from models import UserPublic
from services.activity_log import timeline_for

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("")
async def global_activity(
    limit: int = Query(50, ge=1, le=500),
    user: UserPublic = Depends(get_current_user),
):
    # `activity_events` now carries `floor_id` (stamped by `log_event`,
    # backfilled by migration 0014), so this feed is filtered in Mongo like
    # every other module rather than being blanked out for floor-restricted
    # staff — which is what the old containment measure did, and which still
    # showed owners/managers a merged cross-unit feed.
    return await timeline_for(limit=limit, floor_ids=floor_scope_ids(user))


async def _assert_quotation_access(user: UserPublic, quotation_id: str) -> dict:
    doc = await db.quotations.find_one(floor_query(user, {"id": quotation_id}), {"_id": 0, "id": 1, "floor_id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return doc


async def _assert_purchase_access(user: UserPublic, purchase_id: str) -> dict:
    doc = await db.purchase_orders.find_one(floor_query(user, {"id": purchase_id}), {"_id": 0, "id": 1, "floor_id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return doc


async def _assert_customer_access(user: UserPublic, customer_id: str) -> dict:
    doc = await db.customers.find_one(floor_query(user, {"id": customer_id}), {"_id": 0, "id": 1, "floor_id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Customer not found")
    return doc


@router.get("/quotation/{quotation_id}")
async def quotation_timeline(
    quotation_id: str,
    limit: int = Query(200, ge=1, le=500),
    user: UserPublic = Depends(get_current_user),
):
    # BACKEND_AUDIT_2026-07-17.md Medium #34: this previously returned a
    # quotation's full activity timeline (customer names, discount changes,
    # internal notes) to ANY authenticated staff member who knew or guessed
    # the ID, with no check that the caller's floor assignment actually
    # covers that quotation — bypassing the same isolation the quotation
    # list/detail endpoints already enforce.
    doc = await _assert_quotation_access(user, quotation_id)
    return await timeline_for(quotation_id=quotation_id, limit=limit, floor_ids=[doc["floor_id"]])


@router.get("/purchase/{purchase_id}")
async def purchase_timeline(
    purchase_id: str,
    limit: int = Query(200, ge=1, le=500),
    user: UserPublic = Depends(get_current_user),
):
    doc = await _assert_purchase_access(user, purchase_id)
    return await timeline_for(purchase_id=purchase_id, limit=limit, floor_ids=[doc["floor_id"]])


@router.get("/customer/{customer_id}")
async def customer_timeline(
    customer_id: str,
    limit: int = Query(200, ge=1, le=500),
    user: UserPublic = Depends(get_current_user),
):
    doc = await _assert_customer_access(user, customer_id)
    return await timeline_for(customer_id=customer_id, limit=limit, floor_ids=[doc["floor_id"]])


@router.get("/product/{product_id}")
async def product_timeline(
    product_id: str,
    limit: int = Query(200, ge=1, le=500),
    user: UserPublic = Depends(get_current_user),
):
    """Audit trail for a product's image uploads/replacements/deletions —
    survives independently of the live `product_media` rows (a deleted
    image's metadata is captured here at delete time, not lost with it).

    Gated the same way the quotation/purchase/customer timelines are: this
    was the one timeline with no access check at all, so any authenticated
    staff member could read another business unit's catalogue history by id.
    """
    await get_floor_scoped_or_404(
        db.products, product_id, user, not_found="Product not found",
        projection={"_id": 0, "id": 1, "floor_id": 1},
    )
    return await timeline_for(entity_type="product", entity_id=product_id, limit=limit)
