"""Pydantic models for Forge. Every persisted doc uses a UUID id string."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, EmailStr, Field


Role = Literal[
    "owner", "admin", "manager", "sales",
    "purchase", "warehouse", "accounts", "worker",
]

QuotationStatus = Literal[
    "draft", "pending_approval", "approved", "rejected", "sent", "won", "lost", "expired",
    "ordered",  # order placed — POs generated
]

# Purchase Order lifecycle. Ordering matters — the frontend Kanban / status
# selectors reflect this canonical sequence.
PurchaseStatus = Literal[
    "draft",              # PO generated, not yet reviewed
    "awaiting_review",    # sent for internal approval
    "ordered",            # sent to supplier
    "awaiting_supplier",  # supplier acknowledged, awaiting production/ship
    "partial_received",   # some line items received
    "fully_received",     # all line items received
    "packed",             # goods packed for customer dispatch
    "ready_for_dispatch", # awaiting final dispatch to customer
    "cancelled",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TimestampedModel(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


# ---------- Users (staff) ----------
class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: Role
    phone: Optional[str] = None
    active: bool = True
    avatar_url: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserPublic(UserBase, TimestampedModel):
    pass


class UserInDB(UserPublic):
    password_hash: str


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# ---------- Customers ----------
class CustomerBase(BaseModel):
    name: str
    company: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    gstin: Optional[str] = None
    tier: Literal["retail", "trade", "vip"] = "retail"
    notes: Optional[str] = None
    avatar_url: Optional[str] = None


class CustomerCreate(CustomerBase):
    password: Optional[str] = None  # for portal login


class CustomerPublic(CustomerBase, TimestampedModel):
    pass


class CustomerInDB(CustomerPublic):
    password_hash: Optional[str] = None


class CustomerLoginPayload(BaseModel):
    email: EmailStr
    password: str


class CustomerTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer: CustomerPublic


class GoogleSessionPayload(BaseModel):
    session_id: str


class UserSession(BaseModel):
    """One device/browser login — lets a user see & revoke their active
    sessions ('remember trusted devices' / 'logout from all devices')."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_type: Literal["staff", "customer"]
    user_id: str
    login_method: Literal["password", "google"] = "password"
    device_label: Optional[str] = None
    user_agent: Optional[str] = None
    ip: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    last_seen_at: str = Field(default_factory=now_iso)
    revoked: bool = False


class SessionInfo(BaseModel):
    id: str
    device_label: Optional[str] = None
    login_method: str
    created_at: str
    last_seen_at: str
    current: bool = False


# ---------- Catalog ----------
class Brand(TimestampedModel):
    name: str
    slug: str
    logo_url: Optional[str] = None
    country: Optional[str] = None


class Category(TimestampedModel):
    name: str
    slug: str
    parent_id: Optional[str] = None
    icon: Optional[str] = None


class ProductVariant(BaseModel):
    sku: str
    finish: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    mrp: float
    price: float
    stock: int = 0
    # Populated dynamically at read-time (media_service.hydrate_variants_batch)
    # from family-sibling products — NOT persisted on the stored embedded
    # field. Lets every variant chip show its own real photo + link back to
    # the sibling product it represents.
    id: Optional[str] = None
    image: Optional[str] = None


class Product(TimestampedModel):
    name: str
    sku: str
    brand_id: str
    category_id: str
    subcategory: Optional[str] = None      # e.g. "Wall Hung WC", "Console Basin"
    series: Optional[str] = None            # e.g. "Metropole", "Sento", "Zentrum"
    collection: Optional[str] = None        # e.g. "AXOR" (premium line under Hansgrohe brand)
    family_key: Optional[str] = None        # variants that share this key are the same family
    family_name: Optional[str] = None       # human-readable family label
    variant_label: Optional[str] = None     # e.g. "Matt Black", "Chrome"
    finish_code: Optional[str] = None       # supplier finish code (e.g. "483" for Vitra Matt Black)
    colour: Optional[str] = None
    description: Optional[str] = None
    finish: Optional[str] = None            # e.g. "Chrome", "Matt Black", "Brushed Brass"
    material: Optional[str] = None
    dimensions: Optional[str] = None
    warranty: Optional[str] = None
    mrp: float
    price: float                            # trade price
    stock: int = 0
    # DEPRECATED (kept for read-back compatibility) — new media lives in
    # `product_media` collection referenced via ProductMedia.
    images: list[str] = []
    image_meta: list[dict] = []             # per-image {width,height,quality,source_format}
    image_quality: Optional[str] = None     # aggregate: excellent|good|acceptable|poor|missing
    # NEW media architecture (Iteration 2A). These fields are populated from
    # the `product_media` collection at query-time so business code stays
    # decoupled from storage. Never write directly to these fields.
    media_summary: Optional[dict] = None    # {"supplier": n, "manufacturer": n, "internal": n, "best_quality": "..."}
    hero_image_url: Optional[str] = None    # canonical public URL of the primary image
    gallery: list[dict] = []                # [{url, role, source_type, width, height, quality}]
    specs: dict = {}                        # freeform key/value spec extras
    tags: list[str] = []
    variants: list[ProductVariant] = []
    # Curated relationships (populated in Phase 2C but modelled now)
    related_ids: list[str] = []             # manual "you might also like"
    compatible_ids: list[str] = []          # curated compatible parts
    accessory_ids: list[str] = []           # curated accessories
    downloads: list[dict] = []              # [{title, type, url, size_bytes}] — kept for Downloads tab
    is_custom: bool = False                 # created inline from the builder (custom product flow)
    active: bool = True


class ProductCreate(BaseModel):
    name: str
    sku: str
    brand_id: str
    category_id: str
    description: Optional[str] = None
    finish: Optional[str] = None
    material: Optional[str] = None
    dimensions: Optional[str] = None
    warranty: Optional[str] = None
    mrp: float
    price: float
    stock: int = 0
    images: list[str] = []
    tags: list[str] = []
    is_custom: bool = False


# ---------- Quotations ----------
class QuotationLineItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    product_id: str
    sku: str
    name: str
    image: Optional[str] = None
    finish: Optional[str] = None
    colour: Optional[str] = None
    category_id: Optional[str] = None      # denormalized for category-level discounts
    room: Optional[str] = None
    qty: float = 1
    unit_price: float = 0                  # final selling price per unit
    discount_pct: Optional[float] = None   # None → inherit from category/project
    notes: Optional[str] = None
    description: Optional[str] = None      # inline override of product description
    sort_order: int = 0

    @property
    def net(self) -> float:
        """Line total after discount — final price the customer pays for this line."""
        gross = self.qty * self.unit_price
        disc_pct = self.discount_pct or 0
        disc = gross * disc_pct / 100
        return round(gross - disc, 2)

    @property
    def total(self) -> float:
        """Alias for net — Forge uses final prices only, no tax layered on top."""
        return self.net


class QuotationRevision(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    revision_no: int
    created_at: str = Field(default_factory=now_iso)
    created_by: str
    reason: Optional[str] = None
    snapshot: dict


class RoomDiscountCfg(BaseModel):
    """Room-level discount — either a flat % off every line in the room, or a
    fixed rupee amount off the room's subtotal (allocated proportionally
    across the room's lines). Sits between product-level overrides and
    category/project discounts in the precedence chain:
        Product override > Room discount > Category discount > Project discount
    """
    type: Literal["percent", "amount"] = "percent"
    value: float = 0


class Quotation(TimestampedModel):
    number: str                          # human-readable e.g. FQ-2026-0001
    customer_id: str
    customer_name: str
    # V4 header fields — captured on the builder header so the sales rep never
    # leaves the workspace. All optional and safely backward-compatible.
    project_name: Optional[str] = None
    phone_snapshot: Optional[str] = None      # frozen at quote time (customer.phone can change)
    reference_source: Optional[str] = None    # "Walk-in", "Reference", "Instagram", "Architect", etc.
    status: QuotationStatus = "draft"
    items: list[QuotationLineItem] = []
    rooms: list[str] = []                # ordered list of room labels
    collapsed_rooms: list[str] = []      # ui state — persisted so it survives reloads
    project_discount_pct: float = 0      # applied on top of item net (after item discount)
    category_discounts: dict[str, float] = {}  # {category_id: discount_pct}
    room_discounts: dict[str, RoomDiscountCfg] = {}  # {room_name: {type, value}}
    # Full UI state blob — active_room, scroll positions, expanded panels,
    # last-opened filter, favourite chips. Written on silent autosave so
    # reopening the quotation puts the salesperson EXACTLY where they left off.
    ui_state: dict = {}
    subtotal: float = 0
    discount_total: float = 0            # total of all discounts (item + cat + project)
    grand_total: float = 0
    notes: Optional[str] = None
    valid_until: Optional[str] = None
    created_by: str                      # user id
    created_by_name: str
    approved_by: Optional[str] = None
    revisions: list[QuotationRevision] = []
    # Set only when this order was auto-generated by the Purchases "Transfer to
    # another customer" workflow — lets Payments/Timeline explain WHY an order
    # exists even though no one manually built a quotation for it.
    source: Optional[Literal["transfer"]] = None
    source_purchase_order_id: Optional[str] = None
    source_item_id: Optional[str] = None


class QuotationCreate(BaseModel):
    customer_id: str
    items: list[QuotationLineItem] = []
    rooms: list[str] = []
    notes: Optional[str] = None
    valid_until: Optional[str] = None
    project_name: Optional[str] = None
    phone_snapshot: Optional[str] = None
    reference_source: Optional[str] = None
    project_discount_pct: float = 0
    category_discounts: dict[str, float] = {}
    room_discounts: dict[str, RoomDiscountCfg] = {}


class QuotationUpdate(BaseModel):
    customer_id: Optional[str] = None    # change the customer on an existing quotation
    items: Optional[list[QuotationLineItem]] = None
    rooms: Optional[list[str]] = None
    collapsed_rooms: Optional[list[str]] = None
    notes: Optional[str] = None
    valid_until: Optional[str] = None
    status: Optional[QuotationStatus] = None
    project_name: Optional[str] = None
    phone_snapshot: Optional[str] = None
    reference_source: Optional[str] = None
    ui_state: Optional[dict] = None
    project_discount_pct: Optional[float] = None
    category_discounts: Optional[dict[str, float]] = None
    room_discounts: Optional[dict[str, RoomDiscountCfg]] = None
    reason: Optional[str] = None         # for revision log
    silent: bool = False                 # if true, skip revision snapshot (autosave)


# ---------- Ops modules (scaffold) ----------
class Supplier(TimestampedModel):
    """A dealership/supplier we buy from — normally one per brand but not strict."""
    name: str
    brand_id: Optional[str] = None
    brand_name: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    gstin: Optional[str] = None
    payment_terms: Optional[str] = None   # e.g. "30 days credit"
    notes: Optional[str] = None
    active: bool = True


class SupplierCreate(BaseModel):
    name: str
    brand_id: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    gstin: Optional[str] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None


PURCHASE_STAGES = (
    "order_in_company",
    "company_billing",
    "in_box",
    "dispatched",
    "in_transit",
    "delivered",
)
PurchaseStage = Literal[
    "order_in_company",
    "company_billing",
    "in_box",
    "dispatched",
    "in_transit",
    "delivered",
]


class PurchaseStageEvent(BaseModel):
    """Immutable log of a stage transition on a PurchaseOrderItem."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    at: str = Field(default_factory=now_iso)
    from_stage: Optional[PurchaseStage] = None
    to_stage: PurchaseStage
    by_user_id: str
    by_user_name: str
    note: Optional[str] = None
    action: Literal["move", "transfer_in", "transfer_out", "create", "split_in", "split_out"] = "move"
    ref_item_id: Optional[str] = None   # opposite side of a transfer/split
    ref_po_id: Optional[str] = None
    qty: Optional[float] = None          # units affected — set for split events


class PurchaseOrderItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    product_id: str
    sku: str
    name: str
    image: Optional[str] = None
    finish: Optional[str] = None
    category_id: Optional[str] = None
    room: Optional[str] = None
    qty: float = 1
    qty_received: float = 0
    unit_cost: float = 0                  # final cost per unit paid to supplier
    notes: Optional[str] = None
    quotation_line_id: Optional[str] = None
    sort_order: int = 0

    # ---- Material-tracking fields (per-line lifecycle) ----
    stage: PurchaseStage = "order_in_company"
    # Denormalized so the tracker table doesn't need a join for every row.
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    brand_id: Optional[str] = None
    brand_name: Optional[str] = None
    # Timestamps for the "Last Move / Dispatched By" column and Blocked SLA.
    last_moved_at: Optional[str] = None
    last_moved_by: Optional[str] = None
    last_moved_by_name: Optional[str] = None
    # Immutable stage history — append-only.
    stage_history: list[PurchaseStageEvent] = []
    # Transfer bookkeeping
    transferred_from_item_id: Optional[str] = None   # set on the destination item
    transferred_from_po_id: Optional[str] = None
    transferred_from_customer_id: Optional[str] = None
    # Split bookkeeping (partial-quantity stage move — e.g. "3 of 20")
    split_from_item_id: Optional[str] = None          # set on the new (moved) piece
    split_into_item_id: Optional[str] = None           # set on the remainder, if any


class PurchaseStatusEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    at: str = Field(default_factory=now_iso)
    from_status: Optional[str] = None
    to_status: str
    by_user_id: str
    by_user_name: str
    note: Optional[str] = None


class PurchaseAttachment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    at: str = Field(default_factory=now_iso)
    by_user_id: str
    by_user_name: str
    filename: str
    mime: str = "application/octet-stream"
    data_url: str                          # base64 data URL (kept simple per system rules)
    size_bytes: int = 0
    note: Optional[str] = None


class PurchaseOrder(TimestampedModel):
    number: str                            # human — e.g. FPO-2026-0001
    quotation_id: Optional[str] = None
    quotation_number: Optional[str] = None
    customer_id: str
    customer_name: str
    project_id: Optional[str] = None       # future: multi-project customers
    project_name: Optional[str] = None
    brand_id: Optional[str] = None
    brand_name: Optional[str] = None
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    status: PurchaseStatus = "draft"
    items: list[PurchaseOrderItem] = []
    status_history: list[PurchaseStatusEvent] = []
    attachments: list[PurchaseAttachment] = []
    internal_notes: Optional[str] = None
    expected_delivery_at: Optional[str] = None
    delivered_at: Optional[str] = None
    subtotal: float = 0
    grand_total: float = 0
    created_by: str
    created_by_name: str
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None


class PurchaseOrderUpdate(BaseModel):
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    internal_notes: Optional[str] = None
    expected_delivery_at: Optional[str] = None
    assigned_to: Optional[str] = None
    items: Optional[list[PurchaseOrderItem]] = None


# ---------- Shortage / Reorder tracking (Workflow Integrity Sprint) ----------
# Purely additive collection — created the moment a transfer leaves a
# customer's originally-committed quantity under-allocated. Never blocks a
# transfer; purchasing sees it as a recommendation, not an error.
ShortageStatus = Literal["awaiting_reorder", "reordered", "resolved", "dismissed"]


class PurchaseShortage(TimestampedModel):
    customer_id: str
    customer_name: str
    quotation_id: Optional[str] = None
    quotation_number: Optional[str] = None
    quotation_line_id: Optional[str] = None
    product_id: str
    sku: str
    name: str
    image: Optional[str] = None
    committed_qty: float = 0        # what the customer originally ordered on this line
    allocated_qty: float = 0        # what's still allocated to them right now
    shortage_qty: float = 0         # committed - allocated (> 0 while open)
    status: ShortageStatus = "awaiting_reorder"
    reason: str = ""
    transferred_to_customer_id: Optional[str] = None
    transferred_to_customer_name: Optional[str] = None
    resolved_po_id: Optional[str] = None
    resolved_po_number: Optional[str] = None
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_by_name: Optional[str] = None


class PurchaseStatusPayload(BaseModel):
    to_status: PurchaseStatus
    note: Optional[str] = None


class PurchaseReceivePayload(BaseModel):
    """Mark quantities received (per line). Backend infers status transition."""
    receipts: dict[str, float]             # {item_id: qty_received}
    note: Optional[str] = None


class PurchaseAttachmentCreate(BaseModel):
    filename: str
    mime: str = "application/octet-stream"
    data_url: str
    note: Optional[str] = None


# ---------- Activity Log (audit trail) ----------
ActivityEntity = Literal["quotation", "purchase", "customer", "project", "payment", "followup"]


class ActivityEvent(TimestampedModel):
    """Immutable audit entry. Timelines are read models over this collection."""
    event_type: str                        # e.g. quotation.created, purchase.status_changed
    entity_type: ActivityEntity
    entity_id: str
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    # De-normalised references so timelines resolve without extra joins.
    customer_id: Optional[str] = None
    quotation_id: Optional[str] = None
    purchase_id: Optional[str] = None
    payload: dict = {}
    # Human-readable summary rendered by the frontend as-is when present.
    summary: Optional[str] = None


class PurchaseOrder_Legacy(TimestampedModel):
    """Kept temporarily so anything still typing against the old scaffold doesn't
    crash. New code should use PurchaseOrder above."""
    number: str
    supplier_name: str
    status: Literal["draft", "sent", "received", "cancelled"] = "draft"
    total: float = 0
    items: list[dict] = []


class Payment(TimestampedModel):
    quotation_id: Optional[str] = None
    quotation_number: Optional[str] = None
    customer_id: str
    customer_name: Optional[str] = None
    amount: float
    mode: Literal["cash", "upi", "bank", "card", "cheque"] = "upi"
    status: Literal["pending", "completed", "failed"] = "completed"
    reference: Optional[str] = None            # cheque no. / UTR / short note
    note: Optional[str] = None                 # freeform note (optional)
    paid_at: Optional[str] = None              # ISO date of receipt (defaults to created_at)
    recorded_by: Optional[str] = None          # user id
    recorded_by_name: Optional[str] = None


class PaymentCreate(BaseModel):
    quotation_id: str
    amount: float
    mode: Literal["cash", "upi", "bank", "card", "cheque"] = "cash"
    reference: Optional[str] = None
    note: Optional[str] = None
    paid_at: Optional[str] = None


# ---------- Follow-ups (Sales Command Center) ----------
FollowupRuleType = Literal[
    "quotation_new", "quotation_inactive", "quotation_expiring", "quotation_expired",
    "payment_overdue", "payment_partial", "purchase_dispatched", "purchase_delivered",
    "customer_inactive", "shortage_reorder", "manual",
]
FollowupCategory = Literal[
    "quotation", "payment", "purchase", "dispatch", "delivery",
    "complaint", "general", "sales", "support",
]
FollowupChannel = Literal["call", "whatsapp", "email", "visit"]
FollowupPriorityLevel = Literal["critical", "high", "medium", "low"]
FollowupStatus = Literal["open", "snoozed", "done", "dismissed"]
FollowupOutcome = Literal["interested", "call_back", "no_answer", "rejected", "converted"]


class Followup(TimestampedModel):
    """A single actionable card in the Follow-ups workspace. Automated rows are
    produced (and kept in sync / auto-resolved) by services/followup_engine.py —
    never created ad-hoc elsewhere. Manual rows (is_automated=False) are created
    by staff via the '+ New Follow-up' action or a logged call outcome."""
    source_key: Optional[str] = None        # dedupe key for automated rules, e.g. "payment_overdue:<qid>"
    rule_type: FollowupRuleType = "manual"
    category: FollowupCategory = "general"
    customer_id: str
    customer_name: str
    customer_phone: Optional[str] = None
    customer_tier: Literal["retail", "trade", "vip"] = "retail"
    quotation_id: Optional[str] = None
    quotation_number: Optional[str] = None
    purchase_id: Optional[str] = None
    purchase_number: Optional[str] = None
    project_name: Optional[str] = None
    value: float = 0                        # quotation value / outstanding amount — powers scoring + Today's Mission
    reason: str = ""                        # one-line headline shown on the card
    reason_factors: list[str] = []          # explainability bullets behind the priority score
    next_action: str = ""                   # deterministic recommendation, e.g. "Call customer"
    next_action_reason: str = ""            # WHY — shown under the action
    suggested_channel: FollowupChannel = "call"
    priority_score: int = 0                 # 0-100, deterministic (see services/followup_engine.py)
    priority_level: FollowupPriorityLevel = "medium"
    manual_priority_override: Optional[FollowupPriorityLevel] = None
    due_at: str
    status: FollowupStatus = "open"
    snoozed_until: Optional[str] = None
    is_automated: bool = True
    auto_resolved: bool = False
    resolution_note: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    last_contacted_at: Optional[str] = None
    contact_attempts: int = 0
    tags: list[str] = []
    completed_at: Optional[str] = None
    completed_outcome: Optional[FollowupOutcome] = None
    notes: Optional[str] = None


class FollowupCreate(BaseModel):
    customer_id: str
    quotation_id: Optional[str] = None
    purchase_id: Optional[str] = None
    category: FollowupCategory = "general"
    channel: FollowupChannel = "call"
    reason: str
    notes: Optional[str] = None
    due_at: Optional[str] = None
    assigned_to: Optional[str] = None
    priority_level: Optional[FollowupPriorityLevel] = None


class FollowupUpdate(BaseModel):
    notes: Optional[str] = None
    due_at: Optional[str] = None
    assigned_to: Optional[str] = None
    manual_priority_override: Optional[FollowupPriorityLevel] = None
    reason: Optional[str] = None
    status: Optional[Literal["open", "dismissed"]] = None


class FollowupSnoozePayload(BaseModel):
    minutes: Optional[int] = None
    until: Optional[str] = None
    preset: Optional[Literal["15m", "1h", "tomorrow", "next_week", "custom"]] = None


class FollowupCompletePayload(BaseModel):
    notes: Optional[str] = None
    channel: Optional[FollowupChannel] = None


class FollowupCallOutcomePayload(BaseModel):
    outcome: FollowupOutcome
    notes: Optional[str] = None


class FollowupContactPayload(BaseModel):
    channel: FollowupChannel


class FollowupSavedView(TimestampedModel):
    """A persisted filter configuration for the Follow-ups workspace."""
    user_id: str
    name: str
    filters: dict = {}          # {kpiFilter, priorityFilter, categoryFilter, tierFilter, ownerFilter, q}


class FollowupSavedViewCreate(BaseModel):
    name: str
    filters: dict = {}


class Notification(TimestampedModel):
    user_id: str
    kind: Literal["info", "success", "warning", "error"] = "info"
    title: str
    body: Optional[str] = None
    read: bool = False
    link: Optional[str] = None


# ---------- Catalog Import Pipeline ----------
class CatalogImportJob(TimestampedModel):
    filename: str
    source_type: Literal["excel", "pdf", "csv"]
    status: Literal["extracted", "normalized", "classified", "validated", "reviewed", "imported", "failed"] = "extracted"
    supplier_name: Optional[str] = None
    total_rows: int = 0
    accepted_rows: int = 0
    rejected_rows: int = 0
    rows: list[dict] = []
    error: Optional[str] = None
    created_by: str



# ---------- Product Media (Iteration 2A) ----------
MediaSourceType = Literal["supplier", "manufacturer", "internal"]
MediaRole = Literal["hero", "gallery", "line-drawing", "lifestyle", "swatch", "spec-sheet", "cad"]
MediaQuality = Literal["excellent", "good", "acceptable", "poor", "missing"]


class ProductMedia(TimestampedModel):
    """Media asset attached to a product (variant) or a whole family.

    Binaries live in Supabase Storage (via MediaStorage); this document holds
    ONLY metadata + a stable reference (`bucket`, `storage_key`, `public_url`).
    Business code MUST NOT deal with the storage layer directly.
    """
    product_id: Optional[str] = None        # attach to specific variant (SKU-level)
    family_key: Optional[str] = None        # attach to the whole family (shared across variants)
    brand_id: Optional[str] = None
    source_type: MediaSourceType = "supplier"
    role: MediaRole = "gallery"
    bucket: str                              # "forge-products" | "forge-private"
    storage_key: str                         # object key inside the bucket
    public_url: Optional[str] = None         # for public bucket; None for private
    width: Optional[int] = None
    height: Optional[int] = None
    quality: MediaQuality = "acceptable"
    sha1: str                                # for dedupe + cache-busting
    mime: str = "image/png"
    size_bytes: int = 0
    is_primary: bool = False                 # hero image for this product/family
    sort_order: int = 100
    uploaded_by: Optional[str] = None        # user id
    notes: Optional[str] = None


class ProductMediaCreate(BaseModel):
    product_id: Optional[str] = None
    family_key: Optional[str] = None
    brand_id: Optional[str] = None
    source_type: MediaSourceType = "manufacturer"
    role: MediaRole = "gallery"
    is_primary: bool = False
    sort_order: int = 100
    notes: Optional[str] = None
    # file is uploaded via multipart, not JSON
