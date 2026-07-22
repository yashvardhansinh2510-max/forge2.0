"""Chalan model defaults — a tile order's material can be released in
multiple batches; each batch is a Chalan embedded on the PurchaseOrder
that produced it (no separate collection, no duplicate order records)."""
from __future__ import annotations

from models import Chalan, ChalanLineItem, PurchaseOrder


def test_chalan_defaults_to_released_stage():
    chalan = Chalan(
        number="CH-0001", created_by="u1", created_by_name="Test User",
        items=[ChalanLineItem(po_item_id="item-1", name="Glossy Ivory", size="600X600", qty=10, unit="Box")],
    )
    assert chalan.stage == "released"
    assert chalan.id
    assert chalan.created_at
    assert chalan.items[0].qty == 10
    assert chalan.godown_received_at is None
    assert chalan.dispatched_at is None


def test_purchase_order_defaults_to_no_chalans():
    po = PurchaseOrder(
        number="FPO-0001", customer_id="c1", customer_name="Test Customer",
        created_by="u1", created_by_name="Test User",
    )
    assert po.chalans == []
