"""Single source of truth mapping a tiles document's (doc_type, status) to
its user-facing workflow stage and the next available workflow action.
Mirrored exactly in frontend/src/components/tiles/tilesStage.ts — these two
implementations must never drift, same discipline as services/pricing.py's
docstring for effective_discount_pct.

Deriving the stage from these two existing Quotation fields (instead of a
new denormalized field) means there is nothing that can drift out of sync
with the source of truth — see the design doc's "Why not a dedicated
`stage` field?" section.
"""
from __future__ import annotations


def tiles_stage(doc_type: str, status: str) -> str:
    if doc_type == "tiles_selection":
        if status == "approved":
            return "selection_approved"
        if status == "pending_approval":
            return "selection_pending_approval"
        return "selection_draft"
    if doc_type == "tiles_quotation":
        if status == "ordered":
            return "ordered"
        if status == "approved":
            return "quotation_confirmed"
        if status == "pending_approval":
            return "quotation_pending_approval"
        return "quotation_draft"
    raise ValueError(f"tiles_stage() called with non-tiles doc_type {doc_type!r}")


TILES_STAGE_LABELS: dict[str, str] = {
    "selection_draft": "Selection — Draft",
    "selection_pending_approval": "Selection — Awaiting approval",
    "selection_approved": "Selection — Approved",
    "quotation_draft": "Quotation — Draft",
    "quotation_pending_approval": "Quotation — Awaiting confirmation",
    "quotation_confirmed": "Quotation — Confirmed",
    "ordered": "Order placed",
}


def tiles_stage_label(doc_type: str, status: str) -> str:
    return TILES_STAGE_LABELS[tiles_stage(doc_type, status)]


def can_move_to_quotation(doc_type: str, status: str) -> bool:
    return doc_type == "tiles_selection" and status == "approved"


def can_place_order(doc_type: str, status: str) -> bool:
    """A tiles quotation must be Confirmed (status=="approved") before
    Place Order is allowed — the workflow's "Confirmation" stage. Standard
    (non-tiles) quotations are untouched by this gate."""
    if doc_type != "tiles_quotation":
        return True
    return status == "approved"


NEXT_TILES_STATUS: dict[str, str] = {
    "draft": "pending_approval",
    "pending_approval": "approved",
}


def next_tiles_action(doc_type: str, status: str) -> dict | None:
    """What the single workflow-action button in the builder topbar should
    do next, or None once there's nothing left (approved quotation —
    Place Order takes over — or an already-ordered document).
    Returns {"label": str, "kind": "patch_status" | "move_to_quotation",
    "next_status": str | None}."""
    if doc_type == "tiles_selection":
        if status == "draft":
            return {"label": "Submit for approval", "kind": "patch_status", "next_status": "pending_approval"}
        if status == "pending_approval":
            return {"label": "Approve", "kind": "patch_status", "next_status": "approved"}
        if status == "approved":
            return {"label": "Move to Quotation", "kind": "move_to_quotation", "next_status": None}
        return None
    if doc_type == "tiles_quotation":
        if status == "draft":
            return {"label": "Submit for confirmation", "kind": "patch_status", "next_status": "pending_approval"}
        if status == "pending_approval":
            return {"label": "Confirm", "kind": "patch_status", "next_status": "approved"}
        return None
    return None
