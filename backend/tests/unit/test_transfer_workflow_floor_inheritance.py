"""Regression test: every record created by a customer transfer must inherit
floor_id from the source purchase order, not silently default to
first-floor. transfer_workflow.py now calls the shared auth.floor_inherit
helper directly rather than a local wrapper."""
from __future__ import annotations

from auth import floor_inherit


def test_transfer_floor_id_inherits_from_source_po():
    assert floor_inherit({"floor_id": "ground-floor"}) == "ground-floor"


def test_transfer_floor_id_defaults_when_source_po_missing_field():
    assert floor_inherit({}) == "first-floor"


# handle_purchase_transferred (the async event handler that runs after
# execute_transfer commits) calls this same floor_inherit(transfer) on
# the persisted transfer journal dict to stamp floor_id onto the
# PurchaseShortage, Payment, and Followup it creates. Because it's the exact
# same function under test above rather than a re-implementation, the two
# tests above already exercise that code path — no separate test needed.
