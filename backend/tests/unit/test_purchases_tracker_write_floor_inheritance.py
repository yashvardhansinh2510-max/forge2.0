"""Regression test: every record the legacy transfer/reorder code paths in
purchases_tracker.py create must inherit floor_id from their source
document, matching the rule applied to the modern transfer_workflow.py path
and the domain_outbox.py automation."""
from __future__ import annotations

from routes.purchases_tracker import _source_floor_id


def test_source_floor_id_inherits_present_value():
    assert _source_floor_id({"floor_id": "ground-floor"}) == "ground-floor"


def test_source_floor_id_defaults_when_missing():
    assert _source_floor_id({}) == "first-floor"
