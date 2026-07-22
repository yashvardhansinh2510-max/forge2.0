"""Smoke tests for the Chalan PDF builder — confirms it produces a real PDF
and the exact filename format the spec requires, not full visual/layout
correctness (matches this repo's existing PDF test coverage, i.e. none —
this is new, minimal, valuable coverage)."""
from __future__ import annotations

from pdf_chalan import build_chalan_pdf, chalan_pdf_filename


def _chalan():
    return {
        "number": "CH-1052", "created_at": "2026-07-22T10:00:00+00:00",
        "items": [{"po_item_id": "i1", "name": "Glossy Ivory", "size": "600X600", "qty": 40, "unit": "Box"}],
        "receiver_name": "Nileshbhai Pokiya", "sender_name": "Kajaria Rep",
        "reference_number": "REF-9",
    }


def _po():
    return {"customer_name": "Nileshbhai Pokiya", "supplier_name": "Kajaria"}


def _customer():
    return {"phone": "+91 98765 43210"}


def test_build_chalan_pdf_returns_pdf_bytes():
    pdf_bytes = build_chalan_pdf(_chalan(), _po(), _customer())
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")


def test_build_chalan_pdf_handles_missing_optional_fields():
    chalan = {"number": "CH-0001", "created_at": "2026-07-22T10:00:00+00:00", "items": []}
    pdf_bytes = build_chalan_pdf(chalan, {}, {})
    assert pdf_bytes.startswith(b"%PDF")


def test_chalan_pdf_filename_format():
    filename = chalan_pdf_filename(_chalan(), "Nileshbhai Pokiya")
    assert filename == "CH-1052 Nileshbhai Pokiya 22-07-2026.pdf"
