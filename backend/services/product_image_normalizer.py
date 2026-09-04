"""Canonical landscape preparation for product photography.

Product imagery is a horizontal document asset.  Persist it as a 16:10
landscape raster so catalog screens, selections and PDFs all obey one
orientation contract rather than relying on each renderer to repair it.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


NORMALIZABLE_IMAGE_MIMES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"})
PRODUCT_IMAGE_ASPECT_RATIO = 16 / 10


class ProductImageNormalizationError(ValueError):
    """Raised when a declared product image cannot be decoded safely."""


def _landscape_canvas_size(width: int, height: int) -> tuple[int, int]:
    """Return the largest exact 16:10 crop contained by the source."""
    if width <= 0 or height <= 0:
        raise ProductImageNormalizationError("The uploaded image has invalid dimensions")
    if width / height >= PRODUCT_IMAGE_ASPECT_RATIO:
        return round(height * PRODUCT_IMAGE_ASPECT_RATIO), height
    return width, round(width / PRODUCT_IMAGE_ASPECT_RATIO)


def _needs_landscape_canvas(width: int, height: int) -> bool:
    return (width, height) != _landscape_canvas_size(width, height)


def normalize_product_image(data: bytes, mime: str, *, force_landscape: bool = False) -> tuple[bytes, str]:
    """Bake EXIF and persist a cropped 16:10 landscape product image.

    Portrait source media is rotated before cropping.  ``force_landscape``
    repairs older landscape files whose photographed tile still needs the
    rotation dictated by its declared portrait dimensions.
    """
    normalized_mime = "image/jpeg" if mime == "image/jpg" else mime
    if normalized_mime not in NORMALIZABLE_IMAGE_MIMES:
        return data, mime
    if normalized_mime == "image/gif":
        return data, mime
    try:
        with Image.open(BytesIO(data)) as opened:
            orientation = opened.getexif().get(274, 1)
            if orientation == 1 and not force_landscape and not _needs_landscape_canvas(*opened.size):
                return data, mime
            image = ImageOps.exif_transpose(opened)
            image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProductImageNormalizationError("The uploaded image could not be decoded") from exc

    if image.height > image.width or force_landscape:
        image = image.rotate(90, expand=True)
    canvas_width, canvas_height = _landscape_canvas_size(image.width, image.height)
    image = ImageOps.fit(
        image.convert("RGB"), (canvas_width, canvas_height),
        method=Image.Resampling.LANCZOS, centering=(0.5, 0.5),
    )
    out = BytesIO()
    if normalized_mime == "image/webp":
        image.save(out, format="WEBP", quality=90, method=6)
        return out.getvalue(), "image/webp"
    if normalized_mime == "image/png":
        image.save(out, format="PNG", optimize=True)
        return out.getvalue(), "image/png"
    image.save(out, format="JPEG", quality=90, optimize=True)
    return out.getvalue(), "image/jpeg"
