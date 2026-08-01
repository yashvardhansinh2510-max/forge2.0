"""The backfill must reproduce exactly what the write path now stamps."""
from __future__ import annotations

import importlib

migration = importlib.import_module("migrations.0011_backfill_quotation_net_amounts")


def test_computes_nets_for_every_line():
    doc = {
        "items": [
            {"id": "a", "product_id": "p1", "sku": "S1", "name": "A", "qty": 1, "unit_price": 100.0},
            {"id": "b", "product_id": "p2", "sku": "S2", "name": "B", "qty": 2, "unit_price": 50.0},
        ],
        "project_discount_pct": 10,
    }
    assert [i["net_amount"] for i in migration.compute_net_amount_items(doc)] == [90.0, 90.0]


def test_preserves_all_other_line_fields():
    doc = {"items": [{"id": "a", "product_id": "p1", "sku": "S1", "name": "A", "qty": 1, "unit_price": 100.0, "room": "Bath", "mrp": 120.0}]}
    out = migration.compute_net_amount_items(doc)[0]
    assert out["room"] == "Bath" and out["mrp"] == 120.0 and out["net_amount"] == 100.0


def test_quotation_with_no_items_yields_empty_list():
    assert migration.compute_net_amount_items({"items": []}) == []


def test_duplicate_line_ids_are_not_collapsed():
    """Line ids are client-supplied and unenforced. An id-keyed backfill would
    stamp both lines with one value; the write path matches positionally, so
    the backfill must too."""
    doc = {
        "items": [
            {"id": "dup", "product_id": "p1", "sku": "S1", "name": "A", "qty": 1, "unit_price": 100.0},
            {"id": "dup", "product_id": "p2", "sku": "S2", "name": "B", "qty": 3, "unit_price": 100.0},
        ],
        "project_discount_pct": 10,
    }
    assert [i["net_amount"] for i in migration.compute_net_amount_items(doc)] == [90.0, 270.0]


def test_legacy_line_without_an_id_still_gets_its_real_net():
    """Documents written before line ids existed have no "id" key. An id-keyed
    lookup resolves those to 0.0 and would zero out real revenue."""
    doc = {"items": [{"product_id": "p1", "sku": "S1", "name": "A", "qty": 2, "unit_price": 100.0}], "project_discount_pct": 25}
    assert migration.compute_net_amount_items(doc)[0]["net_amount"] == 150.0


def test_does_not_mutate_the_source_document():
    doc = {"items": [{"id": "a", "product_id": "p1", "sku": "S1", "name": "A", "qty": 1, "unit_price": 100.0}]}
    migration.compute_net_amount_items(doc)
    assert "net_amount" not in doc["items"][0]
