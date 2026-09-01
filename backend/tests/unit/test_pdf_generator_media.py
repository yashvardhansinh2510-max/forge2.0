"""Regression tests for upright quotation product images and fit geometry."""

from io import BytesIO
from pathlib import Path
import shutil
import subprocess

from PIL import Image as PILImage
from pypdf import PdfReader
import pytest

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


def _render_pdf_pages(pdf: bytes, output_dir: Path) -> list[Path]:
    """Rasterize a generated PDF so layout regressions are tested as pixels."""
    source = output_dir / "quotation.pdf"
    source.write_bytes(pdf)
    subprocess.run(
        ["pdftoppm", "-png", "-r", "96", str(source), str(output_dir / "page")],
        check=True,
        capture_output=True,
    )
    return sorted(output_dir.glob("page-*.png"))


def test_contain_box_centers_a_horizontal_product_image():
    assert callable(getattr(pdf_generator, "contain_box", None))
    x, y, width, height = pdf_generator.contain_box(1200, 600, 180, 90, 6)

    assert width == 156
    assert height == 78
    assert x == 12
    assert y == 6


def test_sanitary_pdf_filename_uses_the_customer_name():
    assert pdf_generator.quotation_pdf_filename("myrubai") == "myrubai.pdf"
    assert pdf_generator.quotation_pdf_filename('  Myruba / Sons  ') == "Myruba Sons.pdf"


def test_standard_item_tables_fill_the_landscape_printable_width():
    source = Path(pdf_generator.__file__).read_text()

    assert "item_widths = [12 * mm, 20 * mm, 36 * mm, 88 * mm, 24 * mm, 12 * mm, 25 * mm, 25 * mm, 25 * mm]" in source
    assert "item_widths = [12 * mm, 20 * mm, 38 * mm, 117 * mm, 28 * mm, 12 * mm, 40 * mm]" in source


def test_standard_pdf_keeps_full_width_terms_care_and_signature_on_page_one():
    quotation = {
        "customer_name": "Page One Contract",
        "items": [{"sku": "ART-100", "name": "Wall Mixer", "room": "Master Bath", "qty": 1, "unit_price": 1000}],
        "rooms": ["Master Bath"], "subtotal": 1000, "grand_total": 1000,
        "address_snapshot": "Rajkot, Gujarat - detailed delivery address",
    }

    pages = PdfReader(BytesIO(pdf_generator.build_quotation_pdf(quotation, {"name": "Page One Contract"}))).pages
    first_page_text = pages[0].extract_text()

    assert "TERMS & CONDITIONS" in first_page_text
    assert "CUSTOMER CARE" in first_page_text
    assert "CUSTOMER SIGNATURE & DATE" in first_page_text
    assert len(pages) == 2


def test_three_products_in_one_room_share_a_single_detail_page():
    """The compact image frame keeps a typical three-item room together."""
    items = [
        {"sku": f"MB-{index}", "name": f"Master Bathroom Product {index}", "room": "Master Bathroom", "qty": 1, "unit_price": 1000}
        for index in range(1, 4)
    ]
    quotation = {"customer_name": "Master Bath", "items": items, "rooms": ["Master Bathroom"], "subtotal": 3000, "grand_total": 3000}

    pages = PdfReader(BytesIO(pdf_generator.build_quotation_pdf(quotation, {"name": "Master Bath"}))).pages

    assert len(pages) == 2  # cover + one room-detail page
    detail_text = pages[1].extract_text() or ""
    assert all(item["sku"] in detail_text for item in items)
    assert pdf_generator._max_item_rows_per_page() == 17


def test_sanitary_detail_pages_hold_seventeen_products_and_start_next_area_on_page_four():
    """A room continuation consumes its own pages; a new area never shares one."""
    primary_area = [
        {"sku": f"BATH-1-{index:02}", "name": f"Bathroom One Product {index}", "room": "Bathroom One", "qty": 1, "unit_price": 1000}
        for index in range(1, 21)
    ]
    next_area = [{"sku": "BATH-2-01", "name": "Bathroom Two Product", "room": "Bathroom Two", "qty": 1, "unit_price": 1000}]
    quotation = {
        "customer_name": "Seventeen Per Page", "items": primary_area + next_area,
        "rooms": ["Bathroom One", "Bathroom Two"], "subtotal": 21000, "grand_total": 21000,
    }

    pages = PdfReader(BytesIO(pdf_generator.build_quotation_pdf(quotation, {"name": "Seventeen Per Page"}))).pages
    page_text = [page.extract_text() or "" for page in pages]

    assert len(pages) == 4  # summary + 17 + 3-item continuation + next area
    assert all(item["sku"] in page_text[1] for item in primary_area[:17])
    assert all(item["sku"] not in page_text[1] for item in primary_area[17:])
    assert all(item["sku"] in page_text[2] for item in primary_area[17:])
    assert "AREA 1: Bathroom One" in page_text[2]
    assert "(continued)" in page_text[2]
    assert "AREA 2: Bathroom Two" in page_text[3]
    assert "BATH-2-01" in page_text[3]


def test_seventeen_long_products_are_bounded_to_one_detail_page_without_overflow():
    items = [
        {
            "sku": f"LONG-{index}-" + "SKU" * 40,
            "name": "Premium wall-mounted sanitary fitting " * 30,
            "description": "Long description " * 50,
            "finish": "Brushed nickel with a deliberately verbose factory colour name " * 8,
            "room": "Master suite bathroom with a deliberately verbose room name " * 6,
            "qty": 1,
            "unit_price": 1000,
        }
        for index in range(17)
    ]
    quotation = {"customer_name": "Long detail rows", "items": items, "subtotal": 17000, "grand_total": 17000}

    pages = PdfReader(BytesIO(pdf_generator.build_quotation_pdf(quotation, {"name": "Long detail rows"}))).pages

    # Summary plus a single 17-row item page: no hidden overflow/blank page.
    assert len(pages) == 2
    text = pages[1].extract_text() or ""
    assert "LONG-0" in text
    assert "…" in text


def test_watermark_geometry_covers_the_full_landscape_page():
    page_width, page_height = pdf_generator.LANDSCAPE_A4
    x, y, width, height = pdf_generator.watermark_geometry(page_width, page_height)

    assert height == page_height
    assert width >= page_width
    assert x <= 0 and x + width >= page_width
    assert y <= 0 and y + height >= page_height


def test_watermark_is_drawn_on_the_first_and_detail_pages():
    quotation = {
        "customer_name": "Watermark contract",
        "items": [{"sku": "WM-1", "name": "Mixer", "room": "Bath", "qty": 1, "unit_price": 1000}],
        "subtotal": 1000,
        "grand_total": 1000,
    }
    pages = PdfReader(BytesIO(pdf_generator.build_quotation_pdf(quotation, {"name": "Watermark contract"}))).pages

    # The logo XObject is reused, but each page must invoke it in its stream.
    assert all(b"/FormXob" in page.get_contents().get_data() for page in pages)


def test_sanitary_detail_page_expands_eight_or_ten_products_without_padding_rows():
    for count in (8, 10):
        items = [
            {"sku": f"FILL-{count}-{index}", "name": "Bathroom Product", "room": "Bath", "qty": 1, "unit_price": 1000}
            for index in range(count)
        ]
        pages = PdfReader(BytesIO(pdf_generator.build_quotation_pdf(
            {"customer_name": "Adaptive layout", "items": items, "rooms": ["Bath"], "subtotal": count * 1000, "grand_total": count * 1000},
            {"name": "Adaptive layout"},
        ))).pages
        assert len(pages) == 2
        assert pdf_generator._item_row_height_mm(count) > pdf_generator._item_row_height_mm(17)


@pytest.mark.skipif(shutil.which("pdftoppm") is None, reason="Poppler pdftoppm is required for PDF raster regression testing")
@pytest.mark.parametrize("count,discounted,expected_pages", [
    (1, False, 2), (8, False, 2), (10, True, 2), (17, True, 2), (18, False, 3),
])
def test_sanitary_pdf_raster_regressions_cover_counts_discount_and_image_orientations(
    monkeypatch, tmp_path, count, discounted, expected_pages,
):
    """Rendered pixels retain all rows with no unexpected blank PDF page."""
    monkeypatch.setattr(pdf_generator, "_remote_image_bytes", lambda url: _png_bytes(80, 140) if "portrait" in url else _png_bytes(140, 80))
    items = [
        {
            "sku": f"RASTER-{index}", "name": "Long product name " * 8,
            "description": "Detailed description " * 12, "finish": "Brushed nickel " * 6,
            "room": "Main Bathroom", "qty": 1, "unit_price": 1000,
            "discount_pct": 10 if discounted else 0,
            "image": f"https://cdn.example.test/{'portrait' if index % 2 else 'landscape'}.png",
        }
        for index in range(count)
    ]
    quotation = {"customer_name": "Raster regression", "items": items, "subtotal": count * 1000, "grand_total": count * (900 if discounted else 1000)}
    pages = _render_pdf_pages(pdf_generator.build_quotation_pdf(quotation, {"name": "Raster regression"}), tmp_path)

    assert len(pages) == expected_pages
    for page in pages:
        with PILImage.open(page) as image:
            assert image.width > image.height
            # An all-white page indicates an unwanted blank rendering page.
            assert image.getbbox() is not None


def test_pdf_image_bytes_keep_portrait_sources_upright():
    source = _png_bytes(60, 120)

    assert callable(getattr(pdf_generator, "_prepare_image_bytes", None))
    prepared = pdf_generator._prepare_image_bytes(source)

    with PILImage.open(BytesIO(prepared)) as image:
        assert image.size == (60, 120)


def test_pdf_image_bytes_never_force_rotates_an_old_landscape_asset():
    source = _png_bytes(192, 120)

    prepared = pdf_generator._prepare_image_bytes(source, force_landscape=True)

    with PILImage.open(BytesIO(prepared)) as image:
        assert image.size == (192, 120)


def test_pdf_img_contains_and_centers_a_portrait_source(monkeypatch):
    monkeypatch.setattr(pdf_generator, "_remote_image_bytes", lambda _url: _png_bytes(60, 120))

    image = pdf_generator._img("https://example.test/product.png")

    assert image.drawHeight == (pdf_generator.STANDARD_PRODUCT_IMAGE_HEIGHT_MM - 2.5) * pdf_generator.mm
    assert image.drawWidth == (pdf_generator.STANDARD_PRODUCT_IMAGE_HEIGHT_MM - 2.5) / 2 * pdf_generator.mm
    assert image.hAlign == "CENTER"


def test_exif_orientation_six_is_honored_once():
    source = _jpeg_with_orientation(60, 120, 6)

    prepared = pdf_generator._prepare_image_bytes(source)

    with PILImage.open(BytesIO(prepared)) as image:
        assert image.size == (120, 60)


def test_exif_orientation_eight_is_honored_once():
    source = _jpeg_with_orientation(60, 120, 8)

    prepared = pdf_generator._prepare_image_bytes(source)

    with PILImage.open(BytesIO(prepared)) as image:
        assert image.size == (120, 60)


def test_standard_selection_and_tiles_quotation_pdfs_fill_centered_product_image_frames(monkeypatch):
    """Every PDF variant uses a centered, full-size product image frame."""
    monkeypatch.setattr(pdf_generator, "_remote_image_bytes", lambda _url: _png_bytes(60, 120))
    original_img = pdf_generator._img
    rendered_sizes: list[tuple[float, float]] = []
    requested_boxes: list[tuple[float, float]] = []
    cover_values: list[bool] = []

    def capture_img(*args, **kwargs):
        requested_boxes.append((
            kwargs.get("width_mm", pdf_generator.STANDARD_PRODUCT_IMAGE_WIDTH_MM),
            kwargs.get("height_mm", pdf_generator.STANDARD_PRODUCT_IMAGE_HEIGHT_MM),
        ))
        cover_values.append(bool(kwargs.get("cover", False)))
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
        (14.0, pdf_generator._item_row_height_mm(1) - 1.0),
        (pdf_tiles.SELECTION_PRODUCT_IMAGE_WIDTH_MM, pdf_tiles.SELECTION_PRODUCT_IMAGE_HEIGHT_MM),
        (pdf_tiles.QUOTATION_PRODUCT_IMAGE_WIDTH_MM, pdf_tiles.QUOTATION_PRODUCT_IMAGE_HEIGHT_MM),
    ]
    assert all(width > 0 and height > 0 for width, height in rendered_sizes)
    assert cover_values == [True, True, True]
    assert all(
        (width, height) == (box_width * pdf_generator.mm, box_height * pdf_generator.mm)
        for (width, height), (box_width, box_height) in zip(rendered_sizes, requested_boxes, strict=True)
    )


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
