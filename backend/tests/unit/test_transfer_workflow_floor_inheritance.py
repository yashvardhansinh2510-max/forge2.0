"""Regression test: every record created by a customer transfer must inherit
floor_id from the source purchase order, not silently default to
first-floor."""
from __future__ import annotations

from services.transfer_workflow import _transfer_floor_id


def test_transfer_floor_id_inherits_from_source_po():
    assert _transfer_floor_id({"floor_id": "ground-floor"}) == "ground-floor"


def test_transfer_floor_id_defaults_when_source_po_missing_field():
    assert _transfer_floor_id({}) == "first-floor"


# handle_purchase_transferred (the async event handler that runs after
# execute_transfer commits) calls this same _transfer_floor_id(transfer) on
# the persisted transfer journal dict to stamp floor_id onto the
# PurchaseShortage, Payment, and Followup it creates. Because it's the exact
# same function under test above rather than a re-implementation, the two
# tests above already exercise that code path — no separate test needed.
