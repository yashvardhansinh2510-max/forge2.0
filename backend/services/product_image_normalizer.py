"""Orientation-safe preparation for product photography.

Media must retain the supplier's intended orientation.  Responsive catalog
and quotation frames use an aspect-preserving ``contain`` fit, so rotating or
cropping a portrait product just to manufacture a landscape raster destroys
the product presentation.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


NORMALIZABLE_IMAGE_MIMES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"})
PRODUCT_IMAGE_ASPECT_RATIO = 16 / 10


class ProductImageNormalizationError(ValueError):
    """Raised when a declared product image cannot be decoded safely."""


def normalize_product_image(data: bytes, mime: str, *, force_landscape: bool = False) -> tuple[bytes, str]:
    """Bake EXIF orientation while preserving the product pixels.

    ``force_landscape`` remains accepted for API compatibility with existing
    PDF callers, but is deliberately non-destructive: a declared tile size is
    not evidence that the supplier photograph should be rotated.
    """
    normalized_mime = "image/jpeg" if mime == "image/jpg" else mime
    if normalized_mime not in NORMALIZABLE_IMAGE_MIMES:
        return data, mime
    if normalized_mime == "image/gif":
        return data, mime
    try:
        with Image.open(BytesIO(data)) as opened:
            orientation = opened.getexif().get(274, 1)
            if orientation == 1:
                return data, mime
            image = ImageOps.exif_transpose(opened)
            image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProductImageNormalizationError("The uploaded image could not be decoded") from exc

    image = image.convert("RGB")
    out = BytesIO()
    if normalized_mime == "image/webp":
        image.save(out, format="WEBP", quality=90, method=6)
        return out.getvalue(), "image/webp"
    if normalized_mime == "image/png":
        image.save(out, format="PNG", optimize=True)
        return out.getvalue(), "image/png"
    image.save(out, format="JPEG", quality=90, optimize=True)
    return out.getvalue(), "image/jpeg"
