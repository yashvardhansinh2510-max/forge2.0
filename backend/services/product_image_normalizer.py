"""Orientation-safe preparation for product photography.

Static media has its EXIF orientation baked into pixels, but its native aspect
ratio and composition are retained.  Product images must not be rotated from
their physical dimensions or cropped into a synthetic landscape frame: both
operations make legitimate portrait products appear twisted in quotations.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


NORMALIZABLE_IMAGE_MIMES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"})
PRODUCT_IMAGE_ASPECT_RATIO = 16 / 10


class ProductImageNormalizationError(ValueError):
    """Raised when a declared product image cannot be decoded safely."""


def normalize_product_image(data: bytes, mime: str, *, force_landscape: bool = False) -> tuple[bytes, str]:
    """Bake EXIF orientation while preserving the product's native framing.

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
            # `force_landscape` used to rotate assets according to a tile's
            # dimensions. Keep it as a compatible parameter but never use it
            # to change visual orientation.
            if orientation == 1:
                return data, mime
            image = ImageOps.exif_transpose(opened)
            image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProductImageNormalizationError("The uploaded image could not be decoded") from exc

    image = image.convert("RGB") if normalized_mime == "image/jpeg" and image.mode not in ("RGB", "L") else image
    out = BytesIO()
    if normalized_mime == "image/webp":
        image.save(out, format="WEBP", quality=90, method=6)
        return out.getvalue(), "image/webp"
    if normalized_mime == "image/png":
        image.save(out, format="PNG", optimize=True)
        return out.getvalue(), "image/png"
    image.save(out, format="JPEG", quality=90, optimize=True)
    return out.getvalue(), "image/jpeg"
