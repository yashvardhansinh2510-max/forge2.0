"""Regression test: every record the legacy transfer/reorder code paths in
purchases_tracker.py create must inherit floor_id from their source
document, matching the rule applied to the modern transfer_workflow.py path
and the domain_outbox.py automation. purchases_tracker.py now calls the
shared auth.floor_inherit helper directly rather than a local wrapper."""
from __future__ import annotations

from auth import floor_inherit


def test_source_floor_id_inherits_present_value():
    assert floor_inherit({"floor_id": "ground-floor"}) == "ground-floor"


def test_source_floor_id_defaults_when_missing():
    assert floor_inherit({}) == "first-floor"
