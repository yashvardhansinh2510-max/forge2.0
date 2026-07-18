"""Regression test for the shared floor_id inheritance helper. Consolidates
what were four near-identical implementations (domain_outbox.py inlined
three times, transfer_workflow._transfer_floor_id, purchases_tracker.
_source_floor_id, and followup_engine._followup_floor_id's single-source
case) into one rule: a record derived from a source document stays on that
source's floor_id, defaulting to first-floor only when absent."""
from __future__ import annotations

from auth import floor_inherit


def test_inherits_present_floor_id():
    assert floor_inherit({"floor_id": "ground-floor"}) == "ground-floor"


def test_defaults_to_first_floor_when_missing():
    assert floor_inherit({}) == "first-floor"


def test_defaults_to_first_floor_when_source_is_none():
    assert floor_inherit(None) == "first-floor"
