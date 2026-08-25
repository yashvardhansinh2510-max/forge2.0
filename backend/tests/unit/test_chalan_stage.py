"""Pure-function tests for the tile order stage rollup — no DB, no FastAPI,
just dicts in and a stage string out. See design doc's "Data model" section
for the exact stage semantics this implements."""
from __future__ import annotations

from services.chalan_stage import compute_order_stage, is_fully_released, remaining_qty_by_item


def _po(items, chalans):
    return {"items": items, "chalans": chalans}


def test_order_stage_no_chalans_yet():
    po = _po([{"id": "i1", "qty": 10}], [])
    assert compute_order_stage(po) == "order"
    assert remaining_qty_by_item(po) == {"i1": 10.0}


def test_order_stage_partial_release_stays_order():
    po = _po(
        [{"id": "i1", "qty": 10}],
        [{"stage": "released", "items": [{"po_item_id": "i1", "qty": 4}]}],
    )
    assert compute_order_stage(po) == "order"
    assert remaining_qty_by_item(po) == {"i1": 6.0}
    assert is_fully_released(po) is False


def test_order_stage_material_released_when_single_chalan_covers_everything():
    po = _po(
        [{"id": "i1", "qty": 10}],
        [{"stage": "released", "items": [{"po_item_id": "i1", "qty": 10}]}],
    )
    assert is_fully_released(po) is True
    assert compute_order_stage(po) == "material_released"


def test_order_stage_material_released_when_multiple_chalans_sum_to_full_qty():
    po = _po(
        [{"id": "i1", "qty": 10}],
        [
            {"stage": "released", "items": [{"po_item_id": "i1", "qty": 6}]},
            {"stage": "released", "items": [{"po_item_id": "i1", "qty": 4}]},
        ],
    )
    assert compute_order_stage(po) == "material_released"


def test_order_stage_multi_item_order_not_fully_released_until_every_item_covered():
    po = _po(
        [{"id": "i1", "qty": 10}, {"id": "i2", "qty": 5}],
        [{"stage": "released", "items": [{"po_item_id": "i1", "qty": 10}]}],
    )
    # i2 has zero released qty — order stays "order" even though i1 is fully covered
    assert compute_order_stage(po) == "order"
    assert remaining_qty_by_item(po) == {"i1": 0.0, "i2": 5.0}


def test_order_stage_godown_when_any_batch_at_godown():
    po = _po(
        [{"id": "i1", "qty": 10}],
        [
            {"stage": "at_godown", "items": [{"po_item_id": "i1", "qty": 6}]},
            {"stage": "released", "items": [{"po_item_id": "i1", "qty": 4}]},
        ],
    )
    assert compute_order_stage(po) == "godown"


def test_order_stage_dispatch_when_any_batch_dispatched_but_not_all():
    po = _po(
        [{"id": "i1", "qty": 10}],
        [
            {"stage": "dispatched", "items": [{"po_item_id": "i1", "qty": 6}]},
            {"stage": "at_godown", "items": [{"po_item_id": "i1", "qty": 4}]},
        ],
    )
    assert compute_order_stage(po) == "dispatch"


def test_order_stage_completed_when_every_chalan_dispatched():
    po = _po(
        [{"id": "i1", "qty": 10}],
        [
            {"stage": "dispatched", "items": [{"po_item_id": "i1", "qty": 6}]},
            {"stage": "dispatched", "items": [{"po_item_id": "i1", "qty": 4}]},
        ],
    )
    assert compute_order_stage(po) == "completed"
