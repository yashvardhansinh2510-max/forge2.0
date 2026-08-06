"""Artifact-level contracts for the Ground Floor Tiles quotation PDF."""

from io import BytesIO

from pypdf import PdfReader

from pdf_tiles import build_tiles_quotation_pdf


def _pdf_text(quotation: dict) -> str:
    pdf = build_tiles_quotation_pdf(quotation, {"name": quotation["customer_name"]})
    return " ".join(
        " ".join((page.extract_text() or "").split())
        for page in PdfReader(BytesIO(pdf)).pages
    )


def test_tiles_pdf_uses_rate_per_sqft_offer_rate_and_quantity_unit():
    text = _pdf_text({
        "customer_name": "PDF Contract",
        "doc_date": "06-08-2026",
        "items": [{
            "qty": 2,
            "unit_price": 2170,
            "rate_sqft": 70,
            "offer_rate": None,
            "quantity_unit": "Box",
            "pcs_per_box": "3",
            "name": "Tile",
            "room": "Living",
            "size": "600x600",
        }],
        "subtotal": 4340,
        "transportation_fee": 100,
        "grand_total": 4440,
    })

    assert "70 70.00" in text
    assert "2 Box" in text
    assert "PCS/ BOX" in text
    assert "BOX 4,340.00" in text
    assert "₹ 4,340.00" in text
    assert "₹ 100.00" in text
    assert "₹ 4,440.00" in text


def test_tiles_pdf_renders_piece_as_the_quantity_unit():
    text = _pdf_text({
        "customer_name": "PDF Piece Contract",
        "items": [{
            "qty": 1,
            "unit_price": 900,
            "rate_sqft": 30,
            "offer_rate": 30,
            "quantity_unit": "Pieces",
            "pcs_per_box": "1",
            "name": "Basin",
            "room": "Bath",
        }],
        "subtotal": 900,
        "transportation_fee": 0,
        "grand_total": 900,
    })

    assert "1 Pieces" in text
    assert "PIECE 900.00" in text
