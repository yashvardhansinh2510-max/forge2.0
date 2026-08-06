"""Shared follow-up adapter for the Kitchen/Furniture digital notebook.

The notebook is a projection and constrained write surface over the existing
``followups`` collection. It deliberately does not expose the broader CRM
and automation fields carried by :class:`models.Followup`.
"""
from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from pymongo.errors import DuplicateKeyError

from auth import floor_query
from models import NotebookField, NotebookStatus, now_iso


NOTEBOOK_STATUSES: frozenset[str] = frozenset({"new", "pending", "won", "lost"})
KITCHEN_TYPES: frozenset[str] = frozenset({"GI", "SS"})

NOTEBOOK_FIELDS: frozenset[str] = frozenset({
    "customer_name", "customer_phone", "address", "kitchen_type",
    "referred_by", "architect_interior_designer", "notebook_status", "notes",
})
QUOTATION_FIELDS: frozenset[str] = frozenset({
    "quotation_price", "estimated_value", "quotation_date",
})
SEARCH_FIELDS: tuple[str, ...] = (
    "customer_name", "customer_phone", "address",
    "architect_interior_designer", "referred_by", "notes",
)


class NotebookValidationError(ValueError):
    """Raised when a notebook write violates its public contract."""


class NotebookConflictError(RuntimeError):
    """Raised when a row changed after the client read its revision."""

    def __init__(self, row: dict[str, Any], changed_fields: list[str] | None = None):
        self.row = row
        self.changed_fields = changed_fields or []
        super().__init__("Notebook row changed by another user")


def normalize_mobile(value: str) -> str:
    """Normalize common Indian phone formatting to the last ten digits."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


def notebook_projection(*, converted: bool) -> dict[str, int]:
    fields = {
        "id": 1,
        "customer_name": 1,
        "customer_phone": 1,
        "address": 1,
        "kitchen_type": 1,
        "referred_by": 1,
        "architect_interior_designer": 1,
        "notebook_status": 1,
        "notes": 1,
        "is_converted": 1,
        "updated_at": 1,
        "floor_id": 1,
    }
    if converted:
        fields.update({field: 1 for field in QUOTATION_FIELDS})
    return fields


def serialize_notebook_row(document: dict[str, Any]) -> dict[str, Any]:
    """Return only notebook-facing fields plus stable identity metadata."""
    converted = bool(document.get("is_converted"))
    row = {
        "id": document.get("id"),
        "customer_name": document.get("customer_name") or "",
        "customer_phone": document.get("customer_phone") or "",
        "address": document.get("address") or "",
        "kitchen_type": document.get("kitchen_type") or "",
        "referred_by": document.get("referred_by") or "",
        "architect_interior_designer": document.get("architect_interior_designer") or "",
        "status": document.get("notebook_status") or "new",
        "notes": document.get("notes") or "",
        "is_converted": converted,
        "updated_at": document.get("updated_at"),
    }
    if converted:
        row.update({
            "quotation_price": document.get("quotation_price"),
            "estimated_value": document.get("estimated_value"),
            "quotation_date": document.get("quotation_date"),
        })
    return row


def _merged(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = dict(current)
    result.update(patch)
    return result


def validate_notebook_patch(
    patch: dict[str, Any], *, converted: bool, current: dict[str, Any], creating: bool = False,
) -> dict[str, Any]:
    """Validate and normalize a notebook patch; return a safe copy."""
    # Quote fields are known notebook fields even before conversion; reporting
    # the specific conversion error is more useful than treating them as an
    # unknown field.
    allowed = NOTEBOOK_FIELDS | QUOTATION_FIELDS
    unknown = set(patch) - allowed
    if unknown:
        raise NotebookValidationError(f"unsupported field: {sorted(unknown)[0]}")

    clean = dict(patch)
    if "customer_phone" in clean:
        clean["customer_phone"] = normalize_mobile(str(clean["customer_phone"]))
    merged = _merged(current, clean)

    if creating or "customer_name" in clean:
        if not str(merged.get("customer_name") or "").strip():
            raise NotebookValidationError("customer_name is required")
    if creating or "customer_phone" in clean:
        if not normalize_mobile(str(merged.get("customer_phone") or "")):
            raise NotebookValidationError("customer_phone is required")
    if creating or "kitchen_type" in clean:
        if merged.get("kitchen_type") not in KITCHEN_TYPES:
            raise NotebookValidationError("kitchen_type must be GI or SS")

    status = merged.get("notebook_status") or "new"
    if status not in NOTEBOOK_STATUSES:
        raise NotebookValidationError("notebook_status is invalid")
    previous_status = current.get("notebook_status") or "new"
    if previous_status == "won" and any(field not in QUOTATION_FIELDS for field in clean):
        raise NotebookValidationError("Won follow-ups are locked")
    if previous_status == "won" and status != "won":
        raise NotebookValidationError("Won cannot return to another status")
    if status == "lost" and not str(merged.get("notes") or "").strip():
        raise NotebookValidationError("Notes are required before marking Lost")
    if status == "won" and previous_status == "new" and not creating:
        # Confirmation is a client concern; the server only enforces the
        # resulting transition and its immutable audit event.
        pass
    for field in QUOTATION_FIELDS:
        if field in clean and not converted:
            raise NotebookValidationError("quotation fields require conversion")
    return clean


def timeline_event_for_field(field: str, old_value: Any, new_value: Any) -> tuple[str, str]:
    if field == "notebook_status":
        status = str(new_value or "").replace("_", " ").title()
        return "project_followup.status_changed", f"Status changed to {status}"
    if field == "notes" and str(new_value or "").strip():
        return "project_followup.lost_note" if str(new_value) and old_value != new_value else "project_followup.edited", "Lost note recorded" if str(new_value) and old_value != new_value else "Notes updated"
    if field in QUOTATION_FIELDS:
        return "project_followup.quotation_updated", f"{field.replace('_', ' ').title()} updated"
    if field in {"customer_name", "customer_phone", "address"}:
        return "project_followup.customer_updated", f"{field.replace('_', ' ').title()} updated"
    return "project_followup.edited", f"{field.replace('_', ' ').title()} updated"


def notebook_search_query(query: str) -> dict[str, Any] | None:
    if not query.strip():
        return None
    escaped = re.escape(query.strip())
    term = {"$regex": escaped, "$options": "i"}
    return {"$or": [{field: term} for field in SEARCH_FIELDS]}


def notebook_query(user: Any, floor_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a floor-scoped query for notebook rows."""
    base = {"floor_id": floor_id, "notebook_key": {"$exists": True}}
    if extra:
        base.update(extra)
    return floor_query(user, base)


async def resolve_or_create_customer(
    db: Any, *, user: Any, floor_id: str, name: str, phone: str, address: str | None,
) -> dict[str, Any]:
    """Find or create one floor-scoped customer for a notebook row."""
    normalized = normalize_mobile(phone)
    if not normalized:
        raise NotebookValidationError("customer_phone is required")
    query = floor_query(user, {"floor_id": floor_id, "phone_normalized": normalized})
    customer = await db.customers.find_one(query, {"_id": 0})
    if not customer:
        # Compatibility fallback for customers written before the normalized
        # field existed. The migration backfills it for indexed lookups.
        cursor = db.customers.find(floor_query(user, {"floor_id": floor_id}), {"_id": 0})
        for candidate in await cursor.to_list(10000):
            if normalize_mobile(candidate.get("phone") or "") == normalized:
                customer = candidate
                break
    if customer:
        return customer

    now = now_iso()
    document = {
        "id": str(uuid4()), "name": name.strip(), "phone": phone.strip(),
        "phone_normalized": normalized, "address": address, "tier": "retail",
        "floor_id": floor_id, "created_at": now, "updated_at": now,
        "portal_enabled": False, "tags": [],
    }
    try:
        await db.customers.insert_one(document)
    except DuplicateKeyError:
        customer = await db.customers.find_one(query, {"_id": 0})
        if customer:
            return customer
        raise
    return document


async def patch_notebook_row(
    db: Any, *, user: Any, floor_id: str, row_id: str, patch: dict[str, Any], expected_updated_at: str,
) -> dict[str, Any]:
    """Atomically apply one notebook patch against the observed revision."""
    query = notebook_query(user, floor_id, {"id": row_id})
    current = await db.followups.find_one(query, {"_id": 0})
    if not current:
        raise KeyError("Notebook row not found")
    if current.get("updated_at") != expected_updated_at:
        raise NotebookConflictError(serialize_notebook_row(current))
    clean = validate_notebook_patch(
        patch, converted=bool(current.get("is_converted")), current=current,
    )
    if not clean:
        return serialize_notebook_row(current)
    now = now_iso()
    result = await db.followups.update_one(
        {**query, "updated_at": expected_updated_at},
        {"$set": {**clean, "updated_at": now}},
    )
    if not result.matched_count:
        changed = await db.followups.find_one(query, {"_id": 0})
        raise NotebookConflictError(serialize_notebook_row(changed or current))
    updated = await db.followups.find_one(query, {"_id": 0})
    return serialize_notebook_row(updated)
