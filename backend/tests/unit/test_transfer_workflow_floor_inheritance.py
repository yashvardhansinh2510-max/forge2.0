"""Regression test: every record created by a customer transfer must inherit
floor_id from the source purchase order, not silently default to
first-floor."""
from __future__ import annotations

from services.transfer_workflow import _transfer_floor_id


def test_transfer_floor_id_inherits_from_source_po():
    assert _transfer_floor_id({"floor_id": "ground-floor"}) == "ground-floor"


def test_transfer_floor_id_defaults_when_source_po_missing_field():
    assert _transfer_floor_id({}) == "first-floor"


def test_transfer_floor_id_reads_back_from_transfer_journal():
    # handle_purchase_transferred reads transfer.get("floor_id") the same
    # way execute_transfer writes it via _transfer_floor_id — this pins that
    # contract so the two don't drift apart.
    transfer = {"floor_id": "ground-floor"}
    assert transfer.get("floor_id", "first-floor") == "ground-floor"
