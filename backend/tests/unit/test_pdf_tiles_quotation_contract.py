"""Artifact-level contracts for the Ground Floor Tiles quotation PDF."""

from io import BytesIO

from pypdf import PdfReader

import pdf_tiles
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
    assert "2 BOX" in text
    assert "PCS/ BOX" in text
    assert "3 4,340.00" in text
    assert "TOTAL QUANTITY 2 BOX" in text
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

    assert "1 PIECE" in text
    assert "N/A 900.00" in text


def test_tiles_pdf_normalizes_legacy_lowercase_piece_unit():
    text = _pdf_text({
        "customer_name": "Legacy Piece Contract",
        "items": [{
            "qty": 2,
            "unit_price": 900,
            "quantity_unit": "piece",
            "pcs_per_box": "4",
            "name": "Basin",
            "room": "Bath",
        }],
        "subtotal": 1800,
        "grand_total": 1800,
    })

    assert "TOTAL QUANTITY 2 PIECES" in text
    assert "2 PIECES N/A 1,800.00" in text


def test_tiles_quotation_keeps_the_cover_on_page_one_and_starts_details_on_page_two():
    quotation = {
        "customer_name": "Two Page Contract",
        "doc_date": "22-08-2026",
        "items": [{
            "qty": 1,
            "unit_price": 6277.5,
            "rate_sqft": 135,
            "offer_rate": 135,
            "rate_box": 6277.5,
            "quantity_unit": "Box",
            "name": "Aemilia Grigio Dove (1200X1800)",
            "room": "Bathroom",
            "size": "1200X1800",
        }],
        "subtotal": 6277.5,
        "grand_total": 6277.5,
    }

    pages = PdfReader(BytesIO(build_tiles_quotation_pdf(quotation, {"name": "Two Page Contract"}))).pages

    assert len(pages) == 2
    assert "CUSTOMER SIGNATURE" in (pages[0].extract_text() or "")
    assert "PRODUCT DETAILS" in (pages[1].extract_text() or "")
    assert sum(width / pdf_tiles.mm for width in pdf_tiles._QUO_COLS) == 281
    assert pdf_tiles.QUOTATION_PRODUCT_IMAGE_WIDTH_MM == 46


def test_tiles_quotation_does_not_repeat_detail_columns_before_an_overflow_total():
    """A page containing only the trailing total must not show product columns."""
    items = [
        {
            "qty": 10,
            "unit_price": 11160,
            "rate_sqft": 360,
            "offer_rate": 360,
            "rate_box": 11160,
            "quantity_unit": "Box",
            "pcs_per_box": "3",
            "name": f"Tile {index}",
            "room": "Living",
            "size": "1200X2400",
        }
        for index in range(1, 5)
    ]
    total = sum(item["qty"] * item["unit_price"] for item in items)
    pages = PdfReader(BytesIO(build_tiles_quotation_pdf({
        "customer_name": "Overflow Contract",
        "items": items,
        "subtotal": total,
        "grand_total": total,
    }, {"name": "Overflow Contract"}))).pages

    final_page = pages[-1].extract_text() or ""
    assert "TOTAL" in final_page
    assert "PRODUCT IMAGE" not in final_page
