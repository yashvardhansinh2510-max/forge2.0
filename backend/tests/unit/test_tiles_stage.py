"""Pure-function tests for the tiles workflow stage helper — the single
source of truth mapping (doc_type, status) to a user-facing stage and the
next available workflow action. Mirrored in
frontend/src/components/tiles/tilesStage.ts; these two must never drift.
See docs/superpowers/specs/2026-07-27-quotation-tiles-workflow-design.md."""
from __future__ import annotations

import pytest

from services.tiles_stage import (
    can_move_to_quotation, can_place_order, next_tiles_action, tiles_stage, tiles_stage_label,
)


@pytest.mark.parametrize("doc_type,status,expected", [
    ("tiles_selection", "draft", "selection_draft"),
    ("tiles_selection", "pending_approval", "selection_pending_approval"),
    ("tiles_selection", "approved", "selection_approved"),
    ("tiles_quotation", "draft", "quotation_draft"),
    ("tiles_quotation", "pending_approval", "quotation_pending_approval"),
    ("tiles_quotation", "approved", "quotation_confirmed"),
    ("tiles_quotation", "ordered", "ordered"),
])
def test_tiles_stage_mapping(doc_type, status, expected):
    assert tiles_stage(doc_type, status) == expected


def test_tiles_stage_rejects_non_tiles_doc_type():
    with pytest.raises(ValueError):
        tiles_stage("standard", "draft")


def test_tiles_stage_label_is_human_readable():
    assert tiles_stage_label("tiles_selection", "approved") == "Selection — Approved"
    assert tiles_stage_label("tiles_quotation", "approved") == "Quotation — Confirmed"


def test_can_move_to_quotation_only_when_selection_approved():
    assert can_move_to_quotation("tiles_selection", "approved") is True
    assert can_move_to_quotation("tiles_selection", "draft") is False
    assert can_move_to_quotation("tiles_selection", "pending_approval") is False
    assert can_move_to_quotation("tiles_quotation", "approved") is False


def test_can_place_order_gates_tiles_quotation_on_confirmed_status():
    assert can_place_order("tiles_quotation", "approved") is True
    assert can_place_order("tiles_quotation", "draft") is False
    assert can_place_order("tiles_quotation", "pending_approval") is False


@pytest.mark.parametrize("status", ["draft", "pending_approval", "approved"])
def test_can_place_order_never_allows_a_tiles_selection(status):
    """Selections must go through Move to Quotation before order placement."""
    assert can_place_order("tiles_selection", status) is False


def test_can_place_order_never_gates_standard_quotations():
    # Regression guard: the new Confirmed-status gate must not change
    # behavior for the existing sanitaryware quotation flow.
    assert can_place_order("standard", "draft") is True
    assert can_place_order("standard", "pending_approval") is True


def test_next_tiles_action_selection_progression():
    assert next_tiles_action("tiles_selection", "draft") == {
        "label": "Submit for approval", "kind": "patch_status", "next_status": "pending_approval",
    }
    assert next_tiles_action("tiles_selection", "pending_approval") == {
        "label": "Approve", "kind": "patch_status", "next_status": "approved",
    }
    assert next_tiles_action("tiles_selection", "approved") == {
        "label": "Move to Quotation", "kind": "move_to_quotation", "next_status": None,
    }


def test_next_tiles_action_quotation_progression():
    assert next_tiles_action("tiles_quotation", "draft") == {
        "label": "Submit for confirmation", "kind": "patch_status", "next_status": "pending_approval",
    }
    assert next_tiles_action("tiles_quotation", "pending_approval") == {
        "label": "Confirm", "kind": "patch_status", "next_status": "approved",
    }


def test_next_tiles_action_none_when_nothing_left_to_do():
    assert next_tiles_action("tiles_quotation", "approved") is None
    assert next_tiles_action("tiles_quotation", "ordered") is None
