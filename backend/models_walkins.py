"""Walk-ins — Phase 4 of the Follow-ups 2.0 / CRM redesign (2026-07-30).

Entry point of the whole BuildCon ERP pipeline:
    Walk-in -> Customer -> Selection -> Quotation -> Order -> Dispatch -> Payment

Deliberately department-agnostic: `floor_id` doubles as "Interested
Department" (Floor is already a generic, admin-configurable name+slug
entity — see models.FloorPublic — used today for Ground Floor/Tiles and
First Floor/Sanitary). No new department taxonomy was introduced.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from models import TimestampedModel

WalkInStatus = Literal[
    "new", "contacted", "selection_scheduled", "selection_completed",
    "quotation_created", "converted", "lost",
]

# Statuses in which a Walk-in is still "waiting" and should carry an open
# Follow-up card. Once a Selection document actually exists
# (selection_completed / quotation_created / converted), the walk_in_new
# follow-up rule stops matching and auto-closes for free — same mechanism
# used by the Tile Selections/Quotations producers.
WALKIN_OPEN_STATUSES: tuple[str, ...] = ("new", "contacted", "selection_scheduled")


class WalkIn(TimestampedModel):
    number: str                              # e.g. "WI-2026-0001"
    customer_id: str
    customer_name: str                       # denormalized snapshot, same pattern as Quotation.customer_name
    customer_phone: Optional[str] = None
    alternate_phone: Optional[str] = None
    visited_at: str                           # ISO datetime — visit date + time combined
    salesperson_id: Optional[str] = None
    salesperson_name: Optional[str] = None
    source: str = "Walk-in"                   # configurable — see routes/walkin_routes.py lead-sources config
    floor_id: str                             # "Interested Department" — reuses the existing Floor entity
    interested_products: list[str] = []
    budget: Optional[float] = None
    notes: Optional[str] = None
    manual_priority_override: Optional[Literal["low", "medium", "high", "critical"]] = None
    status: WalkInStatus = "new"
    next_followup_at: Optional[str] = None
    lost_reason: Optional[str] = None
    selection_quotation_id: Optional[str] = None   # set once a Selection doc is created for this customer
    converted_at: Optional[str] = None
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    is_deleted: bool = False


class WalkInCreate(BaseModel):
    customer_name: str
    customer_phone: str
    alternate_phone: Optional[str] = None
    email: Optional[str] = None
    visited_at: Optional[str] = None          # defaults to now if omitted
    salesperson_id: Optional[str] = None
    source: str = "Walk-in"
    floor_id: str
    interested_products: list[str] = []
    budget: Optional[float] = None
    notes: Optional[str] = None
    priority: Optional[Literal["low", "medium", "high", "critical"]] = None
    next_followup_at: Optional[str] = None


class WalkInUpdate(BaseModel):
    status: Optional[WalkInStatus] = None
    salesperson_id: Optional[str] = None
    notes: Optional[str] = None
    manual_priority_override: Optional[Literal["low", "medium", "high", "critical"]] = None
    next_followup_at: Optional[str] = None
    lost_reason: Optional[str] = None
    alternate_phone: Optional[str] = None
    budget: Optional[float] = None
    interested_products: Optional[list[str]] = None


class LeadSourcesSettings(BaseModel):
    sources: list[str] = [
        "Walk-in", "Reference", "Architect", "Builder", "Interior Designer",
        "Social Media", "Instagram", "Facebook", "Google", "Advertisement",
        "Existing Customer", "Other",
    ]
