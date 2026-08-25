"""Status ladder / location / ageing derivation — pure functions, no DB.
The 20/12/8 case is the exact simultaneity example from the design doc:
20 ordered, 12 marked ready, 8 of those dispatched → 4 still ready, 8
dispatched, 8 never touched — status must be Partially Dispatched, not a
single "Ready" or "Dispatched" label that would hide the split."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.tile_order_status import (
    ageing_band, completion_percentage, derive_current_location, derive_item_status,
    rollup_status, supplier_silent_days, waiting_days,
)


def test_pending_when_nothing_ready_or_dispatched():
    assert derive_item_status(20, 0, 0) == "Pending"


def test_ready_when_some_ready_none_dispatched():
    assert derive_item_status(20, 12, 0) == "Ready"


def test_partially_dispatched_simultaneity_case():
    # 20 ordered / 12 marked ready / 8 of those dispatched → boxes_ready=4 remaining
    assert derive_item_status(20, 4, 8) == "Partially Dispatched"


def test_dispatched_when_fully_dispatched():
    assert derive_item_status(20, 0, 20) == "Dispatched"


def test_delivered_only_when_flagged_and_fully_dispatched():
    assert derive_item_status(20, 0, 20, all_delivered=True) == "Delivered"
    assert derive_item_status(20, 0, 15, all_delivered=True) == "Partially Dispatched"


def test_zero_ordered_is_pending_not_a_division_error():
    assert derive_item_status(0, 0, 0) == "Pending"


def test_current_location_decoupled_from_status():
    # Fully dispatched but still sitting at Buildcon's own godown — status
    # is Dispatched, location is Godown, simultaneously.
    assert derive_current_location(20, 0, 20, any_at_godown=True) == "Godown"
    assert derive_item_status(20, 0, 20) == "Dispatched"


def test_current_location_ladder():
    assert derive_current_location(20, 0, 0) == "Pending"
    assert derive_current_location(20, 12, 0) == "Ready"
    assert derive_current_location(20, 4, 8) == "Dispatched"
    assert derive_current_location(20, 0, 20, all_delivered=True) == "Delivered"


def test_completion_percentage():
    assert completion_percentage(20, 8) == 40.0
    assert completion_percentage(0, 0) == 0.0


def test_rollup_status_is_furthest_progress():
    assert rollup_status(["Pending", "Ready", "Dispatched"]) == "Dispatched"
    assert rollup_status(["Delivered", "Pending"]) == "Delivered"
    assert rollup_status([]) == "Pending"
    assert rollup_status(["Partially Dispatched", "Ready"]) == "Partially Dispatched"


def test_waiting_days():
    created = (datetime.now(timezone.utc) - timedelta(days=11)).isoformat()
    assert waiting_days(created) == 11


def test_ageing_band_boundaries():
    assert ageing_band(0) == "green"
    assert ageing_band(7) == "green"
    assert ageing_band(8) == "amber"
    assert ageing_band(14) == "amber"
    assert ageing_band(15) == "red"
    assert ageing_band(40) == "red"


def test_supplier_silent_days_falls_back_to_created_at():
    created = (datetime.now(timezone.utc) - timedelta(days=18)).isoformat()
    assert supplier_silent_days(None, created) == 18


def test_supplier_silent_days_uses_last_activity_when_present():
    created = (datetime.now(timezone.utc) - timedelta(days=18)).isoformat()
    last_activity = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert supplier_silent_days(last_activity, created) == 1
