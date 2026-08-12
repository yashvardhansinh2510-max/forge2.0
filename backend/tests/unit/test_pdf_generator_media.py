"""Regression tests for quotation product-image orientation and fit geometry."""

from io import BytesIO

from PIL import Image as PILImage

import pdf_generator
import pdf_tiles


def _png_bytes(width: int, height: int) -> bytes:
    image = PILImage.new("RGB", (width, height), "red")
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _jpeg_with_orientation(width: int, height: int, orientation: int) -> bytes:
    image = PILImage.new("RGB", (width, height), "blue")
    exif = PILImage.Exif()
    exif[274] = orientation
    out = BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def test_contain_box_centers_a_horizontal_product_image():
    assert callable(getattr(pdf_generator, "contain_box", None))
    x, y, width, height = pdf_generator.contain_box(1200, 600, 180, 90, 6)

    assert width == 156
    assert height == 78
    assert x == 12
    assert y == 6


def test_pdf_image_bytes_rotate_portrait_sources_horizontal():
    source = _png_bytes(60, 120)

    assert callable(getattr(pdf_generator, "_prepare_image_bytes", None))
    prepared = pdf_generator._prepare_image_bytes(source)

    with PILImage.open(BytesIO(prepared)) as image:
        assert image.size == (120, 60)


def test_pdf_img_uses_contain_fit_after_rotating_portrait_source(monkeypatch):
    monkeypatch.setattr(pdf_generator, "_remote_image_bytes", lambda _url: _png_bytes(60, 120))

    image = pdf_generator._img("https://example.test/product.png")

    assert image.drawWidth == 10.5 * pdf_generator.mm
    assert image.drawHeight == 5.25 * pdf_generator.mm
    assert image.hAlign == "CENTER"


def test_exif_orientation_is_honored_once_and_remains_horizontal():
    source = _jpeg_with_orientation(60, 120, 6)

    prepared = pdf_generator._prepare_image_bytes(source)

    with PILImage.open(BytesIO(prepared)) as image:
        assert image.size == (120, 60)


def test_standard_selection_and_tiles_quotation_pdfs_all_use_horizontal_images(monkeypatch):
    """All product-bearing PDF variants must share the horizontal renderer."""
    monkeypatch.setattr(pdf_generator, "_remote_image_bytes", lambda _url: _png_bytes(60, 120))
    original_img = pdf_generator._img
    rendered_sizes: list[tuple[float, float]] = []

    def capture_img(*args, **kwargs):
        image = original_img(*args, **kwargs)
        rendered_sizes.append((image.drawWidth, image.drawHeight))
        return image

    monkeypatch.setattr(pdf_generator, "_img", capture_img)
    monkeypatch.setattr(pdf_tiles, "_img", capture_img)
    item = {
        "image": "https://example.test/portrait.png", "sku": "HORIZONTAL-1",
        "name": "Horizontal Product", "room": "Living", "qty": 1,
        "unit_price": 1000, "rate_sqft": 100, "rate_box": 1000,
        "offer_rate": 100, "net_amount": 1000, "quantity_unit": "Box",
    }
    standard = {"customer_name": "PDF Test", "items": [item], "subtotal": 1000, "grand_total": 1000}
    tiles = {**standard, "doc_date": "12-08-2026"}

    assert pdf_generator.build_quotation_pdf(standard, {"name": "PDF Test"}).startswith(b"%PDF-")
    assert pdf_tiles.build_tiles_selection_pdf(tiles, {"name": "PDF Test"}).startswith(b"%PDF-")
    assert pdf_tiles.build_tiles_quotation_pdf(tiles, {"name": "PDF Test"}).startswith(b"%PDF-")
    assert len(rendered_sizes) == 3
    assert all(width > height for width, height in rendered_sizes)
