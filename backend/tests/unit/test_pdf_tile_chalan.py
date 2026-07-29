"""Field-presence check, not pixel-perfect layout — extracts PDF text via
reportlab's own byte stream markers is fragile, so this asserts the
function runs and produces non-trivial PDF bytes with the right filename
convention, matching the existing test_pdf_chalan.py's level of rigor."""
from __future__ import annotations

from pdf_chalan import build_tile_chalan_pdf, tile_chalan_pdf_filename


def _chalan() -> dict:
    return {
        "number": "CH-000123", "dispatch_id": "d-1", "supplier_name": "Qutone Rajkot",
        "supplier_contact": "9909900001", "supplier_address": "Morbi, Gujarat",
        "customer_name": "Nileshbhai Pokiya", "customer_phone": "9909900000",
        "delivery_address": "123 Ring Road", "delivery_city": "Rajkot",
        "reference_number": "TORD-2026-0001",
        "items": [{"po_item_id": "item-1", "tile_name": "Glossy Ivory 600x600", "series": "Metropole", "finish": None, "size": "600X600", "sku": "SKU-1", "boxes": 5, "pieces_per_box": "4", "quantity": 5}],
        "receiver_name": "Nileshbhai Pokiya", "sender_name": "Qutone Rep",
        "vehicle_number": None, "driver_name": None,
        "generated_at": "2026-07-29T14:23:00+00:00", "generated_by_name": "Aarav Kapoor", "system_version": "BuildCon ERP v2",
    }


def test_filename_matches_convention():
    filename = tile_chalan_pdf_filename(_chalan(), "Nileshbhai Pokiya")
    assert filename.startswith("CH-000123 Nileshbhai Pokiya ")
    assert filename.endswith(".pdf")


def test_build_tile_chalan_pdf_produces_bytes():
    pdf_bytes = build_tile_chalan_pdf(_chalan())
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 500
