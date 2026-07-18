"""Customer CRUD (admin) + customer-portal self-serve endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from auth import (
    floor_for_write, floor_query, get_current_customer, get_current_user, hash_password, invalidate_principal_cache, require_min_role,
)
from db import db
from models import (
    CustomerCreate, CustomerPublic, CustomerUpdatePayload, UserPublic, now_iso,
)
from services.activity_log import log_event
from services.invite_service import generate_temp_password, get_invite_service, temp_password_expiry_iso

router = APIRouter(tags=["customers"])


# ---------- Staff-side ----------
# `skip`/`limit` are additive and opt-in — omitting them preserves the exact
# prior behavior (first 500, newest first). `X-Has-More` lets a future caller
# detect truncation without a breaking response-shape change; see
# PRODUCTION_FIXES_2026-07-16.md item 8 (pagination hardening).
@router.get("/customers", response_model=list[CustomerPublic])
async def list_customers(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    user: UserPublic = Depends(get_current_user),
):
    docs = await db.customers.find(
        floor_query(user), {"_id": 0, "password_hash": 0},
    ).sort("created_at", -1).skip(skip).limit(limit + 1).to_list(limit + 1)
    response.headers["X-Has-More"] = "true" if len(docs) > limit else "false"
    return [CustomerPublic(**d) for d in docs[:limit]]


@router.post("/customers", response_model=CustomerPublic)
async def create_customer(
    body: CustomerCreate,
    user: UserPublic = Depends(require_min_role("sales")),
):
    if body.email and await db.customers.find_one({"email": body.email.lower()}):
        raise HTTPException(status_code=409, detail="Customer email already exists")
    if not body.name or not body.name.strip():
        raise HTTPException(status_code=400, detail="Customer name is required")
    data = body.dict()
    data["floor_id"] = floor_for_write(user)
    if data.get("email"):
        data["email"] = data["email"].lower()
    else:
        data["email"] = None
    password = data.pop("password", None)
    from models import CustomerPublic as CP
    cust = CP(**data)
    to_store = cust.dict()
    if password:
        to_store["password_hash"] = hash_password(password)
    await db.customers.insert_one(to_store)
    await log_event(
        event_type="customer.created", entity_type="customer", entity_id=cust.id,
        customer_id=cust.id, actor=user, summary="Customer Created",
    )
    return cust


@router.get("/customers/{customer_id}", response_model=CustomerPublic)
async def get_customer(customer_id: str, user: UserPublic = Depends(get_current_user)):
    doc = await db.customers.find_one(floor_query(user, {"id": customer_id}), {"_id": 0, "password_hash": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Customer not found")
    return CustomerPublic(**doc)


@router.patch("/customers/{customer_id}", response_model=CustomerPublic)
async def update_customer(
    customer_id: str, body: CustomerUpdatePayload, user: UserPublic = Depends(require_min_role("sales")),
):
    """Customers > Edit Customer. Also where Portal Enabled is toggled — the
    only place that flag can be flipped besides Send Invite (which turns it
    on implicitly, see below)."""
    existing = await db.customers.find_one(floor_query(user, {"id": customer_id}), {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Customer not found")

    patch = body.dict(exclude_unset=True)
    if "email" in patch and patch["email"]:
        patch["email"] = patch["email"].lower()
        dupe = await db.customers.find_one({"email": patch["email"], "id": {"$ne": customer_id}}, {"_id": 0, "id": 1})
        if dupe:
            raise HTTPException(status_code=409, detail="Another customer already uses this email")
    if "name" in patch and not (patch["name"] or "").strip():
        raise HTTPException(status_code=400, detail="Customer name is required")

    resulting_email = patch.get("email", existing.get("email"))
    resulting_portal = patch.get("portal_enabled", existing.get("portal_enabled", False))
    if resulting_portal and not resulting_email:
        raise HTTPException(status_code=400, detail="Add an email address before enabling portal access")

    if not patch:
        raise HTTPException(status_code=400, detail="Nothing to update")
    patch["updated_at"] = now_iso()
    await db.customers.update_one({"id": customer_id}, {"$set": patch})

    if "portal_enabled" in patch and patch["portal_enabled"] != existing.get("portal_enabled", False):
        await log_event(
            event_type="customer.portal_enabled" if patch["portal_enabled"] else "customer.portal_disabled",
            entity_type="customer", entity_id=customer_id, customer_id=customer_id, actor=user,
            summary="Customer Portal Enabled" if patch["portal_enabled"] else "Customer Portal Disabled",
        )
    else:
        await log_event(
            event_type="customer.updated", entity_type="customer", entity_id=customer_id,
            customer_id=customer_id, actor=user, summary="Customer Details Updated",
        )

    doc = await db.customers.find_one(floor_query(user, {"id": customer_id}), {"_id": 0, "password_hash": 0})
    return CustomerPublic(**doc)


async def _issue_temp_password(customer_id: str, *, kind: str, user: UserPublic):
    """Shared core for Send Invite + Reset Password — generates, hashes,
    stores, and delivers a temporary password. `kind` only affects the
    delivery message/audit summary."""
    target = await db.customers.find_one(floor_query(user, {"id": customer_id}), {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Customer not found")
    if not target.get("email"):
        raise HTTPException(status_code=400, detail="Add an email address for this customer first")
    if not target.get("portal_enabled"):
        raise HTTPException(status_code=400, detail="Enable Portal Access for this customer first")

    temp_pw = generate_temp_password()
    expires_at = temp_password_expiry_iso()
    await db.customers.update_one(
        floor_query(user, {"id": customer_id}),
        {"$set": {
            "password_hash": hash_password(temp_pw),
            "must_change_password": True,
            "temp_password_expires_at": expires_at,
            "updated_at": now_iso(),
        }},
    )
    invalidate_principal_cache("customer", customer_id)
    result = await get_invite_service().deliver(
        recipient_email=target["email"], recipient_name=target.get("name", "this customer"),
        temp_password=temp_pw, expires_at=expires_at, kind=kind,
    )
    event_type, summary = (
        ("customer.portal_invite_generated", "Customer Portal Invite Generated") if kind == "customer_invite"
        else ("customer.password_reset", "Customer Password Reset")
    )
    await log_event(
        event_type=event_type, entity_type="customer", entity_id=customer_id,
        customer_id=customer_id, actor=user, summary=summary,
    )
    return {
        "delivery_method": result.delivery_method,
        "temporary_password": result.temporary_password,
        "expires_at": result.expires_at,
        "message": result.message,
    }


@router.post("/customers/{customer_id}/send-invite")
async def send_customer_invite(customer_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    """Customers > Edit Customer > Send Invite. Requires Portal Enabled = On
    and an email already saved (see Edit Customer's toggle + Save first)."""
    return await _issue_temp_password(customer_id, kind="customer_invite", user=user)


@router.post("/customers/{customer_id}/reset-password")
async def reset_customer_password(customer_id: str, user: UserPublic = Depends(require_min_role("sales"))):
    """Customers > Edit Customer > Reset Password."""
    return await _issue_temp_password(customer_id, kind="customer_reset", user=user)


# ---------- Customer-portal ----------
@router.get("/portal/quotations")
async def portal_quotations(cust: CustomerPublic = Depends(get_current_customer)):
    docs = await db.quotations.find({"customer_id": cust.id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return docs


@router.get("/portal/quotations/{quotation_id}")
async def portal_quotation_detail(quotation_id: str, cust: CustomerPublic = Depends(get_current_customer)):
    """Read-only detail view for the customer portal — full line items plus a
    lightweight revision index (metadata only, not the full historical
    snapshot) and a per-brand breakdown so the portal can offer brand-wise
    PDF download buttons without a second round trip."""
    doc = await db.quotations.find_one({"id": quotation_id, "customer_id": cust.id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    from routes.quotation_routes import _brand_grouped_preview
    brands_preview = await _brand_grouped_preview(doc)
    revisions = [
        {"revision_no": r.get("revision_no"), "created_at": r.get("created_at"), "reason": r.get("reason")}
        for r in (doc.get("revisions") or [])
    ]
    doc["revisions"] = revisions
    doc["brands"] = brands_preview.get("brands", [])
    return doc
