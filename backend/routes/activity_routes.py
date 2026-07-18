"""Activity timelines — read-model over `activity_events`.

Consumed by:
  * Global recent-activity feed (dashboard)
  * Quotation timeline (inside quotation detail)
  * Purchase order timeline (inside PO detail)
  * Customer profile timeline
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from auth import accessible_floor_ids, floor_query, get_current_user
from db import db
from models import UserPublic
from services.activity_log import timeline_for

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("")
async def global_activity(
    limit: int = Query(50, ge=1, le=500),
    user: UserPublic = Depends(get_current_user),
):
    # BACKEND_AUDIT_2026-07-17.md Medium #34: `activity_events` documents
    # don't carry floor_id (that would need every log_event call site across
    # the backend updated to pass it — too large a mechanical sweep to do
    # safely here), so the global feed cannot be precisely floor-filtered
    # yet. As a containment measure, floor-restricted staff see nothing from
    # this endpoint rather than an unfiltered cross-floor feed; owners/
    # managers (unrestricted) are unaffected. Real per-event floor scoping
    # is tracked as follow-up work, not silently shipped as "fixed".
    if accessible_floor_ids(user) is not None:
        return []
    return await timeline_for(limit=limit)


async def _assert_quotation_access(user: UserPublic, quotation_id: str) -> None:
    doc = await db.quotations.find_one(floor_query(user, {"id": quotation_id}), {"_id": 0, "id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")


async def _assert_purchase_access(user: UserPublic, purchase_id: str) -> None:
    doc = await db.purchase_orders.find_one(floor_query(user, {"id": purchase_id}), {"_id": 0, "id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Purchase order not found")


async def _assert_customer_access(user: UserPublic, customer_id: str) -> None:
    doc = await db.customers.find_one(floor_query(user, {"id": customer_id}), {"_id": 0, "id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Customer not found")


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
    await _assert_quotation_access(user, quotation_id)
    return await timeline_for(quotation_id=quotation_id, limit=limit)


@router.get("/purchase/{purchase_id}")
async def purchase_timeline(
    purchase_id: str,
    limit: int = Query(200, ge=1, le=500),
    user: UserPublic = Depends(get_current_user),
):
    await _assert_purchase_access(user, purchase_id)
    return await timeline_for(purchase_id=purchase_id, limit=limit)


@router.get("/customer/{customer_id}")
async def customer_timeline(
    customer_id: str,
    limit: int = Query(200, ge=1, le=500),
    user: UserPublic = Depends(get_current_user),
):
    await _assert_customer_access(user, customer_id)
    return await timeline_for(customer_id=customer_id, limit=limit)


@router.get("/product/{product_id}")
async def product_timeline(
    product_id: str,
    limit: int = Query(200, ge=1, le=500),
    _: UserPublic = Depends(get_current_user),
):
    """Audit trail for a product's image uploads/replacements/deletions —
    survives independently of the live `product_media` rows (a deleted
    image's metadata is captured here at delete time, not lost with it)."""
    return await timeline_for(entity_type="product", entity_id=product_id, limit=limit)
