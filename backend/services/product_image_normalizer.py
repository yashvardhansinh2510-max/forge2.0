"""Canonical stretched landscape treatment for product photography."""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


PRODUCT_IMAGE_ASPECT_RATIO = 16 / 10
NORMALIZABLE_IMAGE_MIMES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"})


class ProductImageNormalizationError(ValueError):
    """Raised when a declared product image cannot be decoded safely."""


def normalize_product_image(data: bytes, mime: str) -> tuple[bytes, str]:
    """Return an upright 16:10 raster by stretching the source into the frame.

    The product-image contract is visual: portrait sources must not remain
    portrait inside a landscape canvas. We therefore resize both axes to the
    canonical 16:10 dimensions (non-uniformly when necessary), rather than
    padding with white space. GIF input is flattened to its first frame as PNG.
    """
    normalized_mime = "image/jpeg" if mime == "image/jpg" else mime
    if normalized_mime not in NORMALIZABLE_IMAGE_MIMES:
        return data, mime
    try:
        with Image.open(BytesIO(data)) as opened:
            opened.seek(0)
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProductImageNormalizationError("The uploaded image could not be decoded") from exc

    source_width, source_height = image.size
    if source_width <= 0 or source_height <= 0:
        raise ProductImageNormalizationError("The uploaded image has invalid dimensions")
    canvas_width = max(16, int(round(max(source_width, source_height * PRODUCT_IMAGE_ASPECT_RATIO))))
    canvas_height = max(10, int(round(canvas_width / PRODUCT_IMAGE_ASPECT_RATIO)))
    canvas = image.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)
    out = BytesIO()
    if normalized_mime == "image/webp":
        canvas.save(out, format="WEBP", quality=90, method=6)
        return out.getvalue(), "image/webp"
    if normalized_mime == "image/png" or normalized_mime == "image/gif":
        canvas.save(out, format="PNG", optimize=True)
        return out.getvalue(), "image/png"
    canvas.save(out, format="JPEG", quality=90, optimize=True)
    return out.getvalue(), "image/jpeg"
