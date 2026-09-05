// Single source of truth mapping a tiles document's (doc_type, status) to
// its user-facing workflow stage and next available action. Mirrored
// exactly in backend/services/tiles_stage.py — these two implementations
// must never drift. See
// docs/superpowers/specs/2026-07-27-quotation-tiles-workflow-design.md.

export type TilesStage =
  | "selection_draft" | "selection_pending_approval" | "selection_approved"
  | "quotation_draft" | "quotation_pending_approval" | "quotation_confirmed"
  | "ordered";

export function tilesStage(docType: string, status: string): TilesStage {
  if (docType === "tiles_selection") {
    if (status === "approved") return "selection_approved";
    if (status === "pending_approval") return "selection_pending_approval";
    return "selection_draft";
  }
  if (docType === "tiles_quotation") {
    if (status === "ordered") return "ordered";
    if (status === "approved") return "quotation_confirmed";
    if (status === "pending_approval") return "quotation_pending_approval";
    return "quotation_draft";
  }
  throw new Error(`tilesStage() called with non-tiles docType ${JSON.stringify(docType)}`);
}

export const TILES_STAGE_LABELS: Record<TilesStage, string> = {
  selection_draft: "Selection — Draft",
  selection_pending_approval: "Selection — Awaiting approval",
  selection_approved: "Selection — Approved",
  quotation_draft: "Quotation — Draft",
  quotation_pending_approval: "Quotation — Awaiting confirmation",
  quotation_confirmed: "Quotation — Confirmed",
  ordered: "Order placed",
};

export function tilesStageLabel(docType: string, status: string): string {
  return TILES_STAGE_LABELS[tilesStage(docType, status)];
}

export function canMoveToQuotation(docType: string, status: string): boolean {
  return docType === "tiles_selection" && status === "approved";
}

export function canPlaceOrder(docType: string, status: string): boolean {
  if (docType === "tiles_selection") return false;
  if (docType !== "tiles_quotation") return true;
  return status === "approved";
}

export function normalizeTilesStatus(status: string): string {
  if (status === "sent") return "pending_approval";
  if (status === "won") return "approved";
  return status;
}

export type NextTilesAction = {
  label: string;
  kind: "patch_status" | "move_to_quotation";
  nextStatus: string | null;
};

export function nextTilesAction(docType: string, status: string): NextTilesAction | null {
  status = normalizeTilesStatus(status);
  if (docType === "tiles_selection") {
    if (status === "draft") return { label: "Submit for approval", kind: "patch_status", nextStatus: "pending_approval" };
    if (status === "pending_approval") return { label: "Approve", kind: "patch_status", nextStatus: "approved" };
    if (status === "approved") return { label: "Move to Quotation", kind: "move_to_quotation", nextStatus: null };
    return null;
  }
  if (docType === "tiles_quotation") {
    if (status === "draft") return { label: "Submit for confirmation", kind: "patch_status", nextStatus: "pending_approval" };
    if (status === "pending_approval") return { label: "Confirm quotation", kind: "patch_status", nextStatus: "approved" };
    return null;
  }
  return null;
}
