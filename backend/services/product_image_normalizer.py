"""Orientation-safe preparation for product photography.

Product photos keep their source dimensions.  Their presentation belongs to
the shared client renderer; rewriting every upload into a landscape canvas
made source-quality problems permanent and, briefly, allowed a stretch mode
to distort every brand.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


NORMALIZABLE_IMAGE_MIMES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"})


class ProductImageNormalizationError(ValueError):
    """Raised when a declared product image cannot be decoded safely."""


def normalize_product_image(data: bytes, mime: str) -> tuple[bytes, str]:
    """Return source bytes unchanged unless EXIF orientation needs baking in.

    Baking a non-upright EXIF image is needed so browsers and PDFs agree.  In
    every other case the original bytes, dimensions, animation, and quality
    are retained exactly.
    """
    normalized_mime = "image/jpeg" if mime == "image/jpg" else mime
    if normalized_mime not in NORMALIZABLE_IMAGE_MIMES:
        return data, mime
    try:
        with Image.open(BytesIO(data)) as opened:
            orientation = opened.getexif().get(274, 1)
            if orientation == 1:
                return data, mime
            opened.seek(0)
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProductImageNormalizationError("The uploaded image could not be decoded") from exc

    if image.width <= 0 or image.height <= 0:
        raise ProductImageNormalizationError("The uploaded image has invalid dimensions")
    out = BytesIO()
    if normalized_mime == "image/webp":
        image.save(out, format="WEBP", quality=90, method=6)
        return out.getvalue(), "image/webp"
    if normalized_mime == "image/png" or normalized_mime == "image/gif":
        image.save(out, format="PNG", optimize=True)
        return out.getvalue(), "image/png"
    image.save(out, format="JPEG", quality=90, optimize=True)
    return out.getvalue(), "image/jpeg"
