"""Regression tests for upright quotation product images and fit geometry."""

from io import BytesIO

from PIL import Image as PILImage
from pypdf import PdfReader

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


def test_pdf_image_bytes_rotate_portrait_sources_to_horizontal_product_media():
    source = _png_bytes(60, 120)

    assert callable(getattr(pdf_generator, "_prepare_image_bytes", None))
    prepared = pdf_generator._prepare_image_bytes(source)

    with PILImage.open(BytesIO(prepared)) as image:
        assert image.size == (96, 60)


def test_pdf_image_bytes_force_rotates_an_old_landscape_padded_asset():
    # An older asset can already be landscape at the file boundary while its
    # actual product remains portrait. The tile size rule must still rotate it.
    source = _png_bytes(192, 120)

    prepared = pdf_generator._prepare_image_bytes(source, force_landscape=True)

    with PILImage.open(BytesIO(prepared)) as image:
        assert image.size[0] > image.size[1]


def test_pdf_img_uses_a_horizontal_canvas_for_portrait_source(monkeypatch):
    monkeypatch.setattr(pdf_generator, "_remote_image_bytes", lambda _url: _png_bytes(60, 120))

    image = pdf_generator._img("https://example.test/product.png")

    assert image.drawWidth == 23.0 * pdf_generator.mm
    assert image.drawHeight == 14.375 * pdf_generator.mm
    assert image.hAlign == "CENTER"


def test_exif_orientation_six_is_honored_once():
    source = _jpeg_with_orientation(60, 120, 6)

    prepared = pdf_generator._prepare_image_bytes(source)

    with PILImage.open(BytesIO(prepared)) as image:
        assert image.size == (96, 60)


def test_exif_orientation_eight_is_honored_once():
    source = _jpeg_with_orientation(60, 120, 8)

    prepared = pdf_generator._prepare_image_bytes(source)

    with PILImage.open(BytesIO(prepared)) as image:
        assert image.size == (96, 60)


def test_standard_selection_and_tiles_quotation_pdfs_use_horizontal_product_images(monkeypatch):
    """Every PDF variant receives a 16:10 horizontal image, centered in its cell."""
    monkeypatch.setattr(pdf_generator, "_remote_image_bytes", lambda _url: _png_bytes(60, 120))
    original_img = pdf_generator._img
    rendered_sizes: list[tuple[float, float]] = []
    requested_boxes: list[tuple[float, float]] = []

    def capture_img(*args, **kwargs):
        requested_boxes.append((
            kwargs.get("width_mm", pdf_generator.STANDARD_PRODUCT_IMAGE_WIDTH_MM),
            kwargs.get("height_mm", pdf_generator.STANDARD_PRODUCT_IMAGE_HEIGHT_MM),
        ))
        image = original_img(*args, **kwargs)
        rendered_sizes.append((image.drawWidth, image.drawHeight))
        return image

    monkeypatch.setattr(pdf_generator, "_img", capture_img)
    monkeypatch.setattr(pdf_tiles, "_img", capture_img)
    item = {
        "image": "https://example.test/portrait.png", "sku": "UPRIGHT-1",
        "name": "Upright Product", "room": "Living", "qty": 1,
        "unit_price": 1000, "rate_sqft": 100, "rate_box": 1000,
        "offer_rate": 100, "net_amount": 1000, "quantity_unit": "Box",
    }
    standard = {"customer_name": "PDF Test", "items": [item], "subtotal": 1000, "grand_total": 1000}
    tiles = {**standard, "doc_date": "12-08-2026"}

    assert pdf_generator.build_quotation_pdf(standard, {"name": "PDF Test"}).startswith(b"%PDF-")
    assert pdf_tiles.build_tiles_selection_pdf(tiles, {"name": "PDF Test"}).startswith(b"%PDF-")
    assert pdf_tiles.build_tiles_quotation_pdf(tiles, {"name": "PDF Test"}).startswith(b"%PDF-")
    assert len(rendered_sizes) == 3
    assert requested_boxes == [
        (pdf_generator.STANDARD_PRODUCT_IMAGE_WIDTH_MM, pdf_generator.STANDARD_PRODUCT_IMAGE_HEIGHT_MM),
        (pdf_tiles.SELECTION_PRODUCT_IMAGE_WIDTH_MM, pdf_tiles.SELECTION_PRODUCT_IMAGE_HEIGHT_MM),
        (pdf_tiles.QUOTATION_PRODUCT_IMAGE_WIDTH_MM, pdf_tiles.QUOTATION_PRODUCT_IMAGE_HEIGHT_MM),
    ]
    assert all(width / height == pdf_generator.PRODUCT_IMAGE_ASPECT_RATIO for width, height in requested_boxes)
    assert all(width > height for width, height in rendered_sizes)


def test_every_quotation_pdf_is_landscape_a4(monkeypatch):
    monkeypatch.setattr(pdf_generator, "_remote_image_bytes", lambda _url: _png_bytes(60, 120))
    item = {
        "image": "https://example.test/portrait.png", "sku": "LANDSCAPE-1",
        "name": "Portrait Source", "room": "Living", "qty": 1,
        "unit_price": 1000, "rate_sqft": 100, "rate_box": 1000,
        "offer_rate": 100, "net_amount": 1000, "quantity_unit": "Box",
    }
    quotation = {"customer_name": "Landscape Contract", "items": [item], "subtotal": 1000, "grand_total": 1000}
    for pdf in (
        pdf_generator.build_quotation_pdf(quotation, {"name": "Landscape Contract"}),
        pdf_tiles.build_tiles_selection_pdf(quotation, {"name": "Landscape Contract"}),
        pdf_tiles.build_tiles_quotation_pdf(quotation, {"name": "Landscape Contract"}),
    ):
        page = PdfReader(BytesIO(pdf)).pages[0]
        assert float(page.mediabox.width) > float(page.mediabox.height)


def test_product_images_are_prefetched_concurrently(monkeypatch):
    import threading
    import time

    active = 0
    peak = 0
    lock = threading.Lock()

    def fetch(_url):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return None

    monkeypatch.setattr(pdf_generator, "_remote_image_bytes", fetch)
    pdf_generator.prefetch_product_images(
        [{"image": f"https://example.test/{index}.png"} for index in range(8)],
        workers=4,
        timeout=1,
    )

    assert peak == 4
