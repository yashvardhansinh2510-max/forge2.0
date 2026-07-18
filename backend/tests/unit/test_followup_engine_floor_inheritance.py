"""Regression test: the rule-based auto-follow-up engine must inherit
floor_id from whichever source document (quotation or purchase) triggered
the rule, instead of silently defaulting to first-floor on every
automated card."""
from __future__ import annotations

from services.followup_engine import _followup_floor_id


def test_inherits_from_quotation_when_present():
    assert _followup_floor_id(
        quotation={"floor_id": "ground-floor"}, purchase=None,
    ) == "ground-floor"


def test_inherits_from_purchase_when_no_quotation():
    assert _followup_floor_id(
        quotation=None, purchase={"floor_id": "ground-floor"},
    ) == "ground-floor"


def test_defaults_to_first_floor_when_neither_present():
    assert _followup_floor_id(quotation=None, purchase=None) == "first-floor"
