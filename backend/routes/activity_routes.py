"""Activity timelines — read-model over `activity_events`.

Consumed by:
  * Global recent-activity feed (dashboard)
  * Quotation timeline (inside quotation detail)
  * Purchase order timeline (inside PO detail)
  * Customer profile timeline
"""
from fastapi import APIRouter, Depends, Query

from auth import get_current_user
from models import UserPublic
from services.activity_log import timeline_for

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("")
async def global_activity(
    limit: int = Query(50, ge=1, le=500),
    _: UserPublic = Depends(get_current_user),
):
    # Latest across the whole system.
    return await timeline_for(limit=limit)


@router.get("/quotation/{quotation_id}")
async def quotation_timeline(
    quotation_id: str,
    limit: int = Query(200, ge=1, le=500),
    _: UserPublic = Depends(get_current_user),
):
    return await timeline_for(quotation_id=quotation_id, limit=limit)


@router.get("/purchase/{purchase_id}")
async def purchase_timeline(
    purchase_id: str,
    limit: int = Query(200, ge=1, le=500),
    _: UserPublic = Depends(get_current_user),
):
    return await timeline_for(purchase_id=purchase_id, limit=limit)


@router.get("/customer/{customer_id}")
async def customer_timeline(
    customer_id: str,
    limit: int = Query(200, ge=1, le=500),
    _: UserPublic = Depends(get_current_user),
):
    return await timeline_for(customer_id=customer_id, limit=limit)
