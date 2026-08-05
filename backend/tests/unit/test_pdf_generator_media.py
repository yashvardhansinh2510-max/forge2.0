"""Regression tests for quotation product-image orientation and fit geometry."""

from io import BytesIO

from PIL import Image as PILImage

import pdf_generator


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


def test_contain_box_preserves_portrait_orientation_and_centers_it():
    assert callable(getattr(pdf_generator, "contain_box", None))
    x, y, width, height = pdf_generator.contain_box(600, 1200, 180, 90, 6)

    assert width == 39
    assert height == 78
    assert x == 70.5
    assert y == 6


def test_pdf_image_bytes_do_not_rotate_portrait_sources():
    source = _png_bytes(60, 120)

    assert callable(getattr(pdf_generator, "_prepare_image_bytes", None))
    prepared = pdf_generator._prepare_image_bytes(source)

    with PILImage.open(BytesIO(prepared)) as image:
        assert image.size == (60, 120)


def test_pdf_img_uses_contain_fit_for_portrait_source(monkeypatch):
    monkeypatch.setattr(pdf_generator, "_remote_image_bytes", lambda _url: _png_bytes(60, 120))

    image = pdf_generator._img("https://example.test/product.png")

    assert image.drawWidth == 5.25 * pdf_generator.mm
    assert image.drawHeight == 10.5 * pdf_generator.mm


def test_exif_orientation_is_honored_once_without_forcing_landscape():
    source = _jpeg_with_orientation(60, 120, 6)

    prepared = pdf_generator._prepare_image_bytes(source)

    with PILImage.open(BytesIO(prepared)) as image:
        assert image.size == (120, 60)
