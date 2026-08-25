"""Orientation-safe, horizontal preparation for product photography.

Every non-animated product image is stored on the same 16:10 landscape
canvas.  The source is never cropped, stretched, or arbitrarily rotated:
EXIF is baked in, then the upright product is centered on a white canvas.
This gives the catalog, quotation PDFs, and exported documents one durable
orientation contract instead of relying on each renderer to repair images.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


NORMALIZABLE_IMAGE_MIMES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"})
PRODUCT_IMAGE_ASPECT_RATIO = 16 / 10


class ProductImageNormalizationError(ValueError):
    """Raised when a declared product image cannot be decoded safely."""


def _landscape_canvas_size(width: int, height: int) -> tuple[int, int]:
    """Largest exact 16:10 crop contained by the source dimensions."""
    if width <= 0 or height <= 0:
        raise ProductImageNormalizationError("The uploaded image has invalid dimensions")
    if width / height >= PRODUCT_IMAGE_ASPECT_RATIO:
        return round(height * PRODUCT_IMAGE_ASPECT_RATIO), height
    return width, round(width / PRODUCT_IMAGE_ASPECT_RATIO)


def _needs_landscape_canvas(width: int, height: int) -> bool:
    canvas_width, canvas_height = _landscape_canvas_size(width, height)
    return (width, height) != (canvas_width, canvas_height)


def normalize_product_image(data: bytes, mime: str, *, force_landscape: bool = False) -> tuple[bytes, str]:
    """Bake EXIF and rotate portrait product media into a 16:10 landscape canvas.

    Animated GIFs remain byte-for-byte intact because flattening them would
    silently discard animation. They are not used by the supplied catalog;
    all static upload formats are canonicalized before persistence.
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
            opened.seek(0)
            image = ImageOps.exif_transpose(opened)
            image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProductImageNormalizationError("The uploaded image could not be decoded") from exc

    # A portrait asset is not merely padded into a landscape card: quotations
    # must show the product itself horizontally. Rotate it before normalising.
    # `force_landscape` also repairs older white-padded tile assets when their
    # product dimensions say the physical tile is portrait.
    if image.height > image.width or force_landscape:
        image = image.rotate(90, expand=True)
    canvas_width, canvas_height = _landscape_canvas_size(image.width, image.height)
    # Crop to the landscape media aspect instead of padding a portrait/square
    # product onto a white (or dark) background. The visible product itself is
    # therefore always a horizontal tile in the app and every PDF.
    canvas = ImageOps.fit(image.convert("RGB"), (canvas_width, canvas_height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    out = BytesIO()
    if normalized_mime == "image/webp":
        canvas.save(out, format="WEBP", quality=90, method=6)
        return out.getvalue(), "image/webp"
    if normalized_mime == "image/png":
        canvas.save(out, format="PNG", optimize=True)
        return out.getvalue(), "image/png"
    canvas.save(out, format="JPEG", quality=90, optimize=True)
    return out.getvalue(), "image/jpeg"
