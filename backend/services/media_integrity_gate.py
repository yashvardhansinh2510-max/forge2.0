"""Read-only validation primitives for the deployment media-integrity gate."""
from __future__ import annotations

import hashlib
import io
from typing import Any

from PIL import Image, UnidentifiedImageError


def inspect_media_bytes(media: dict[str, Any], data: bytes) -> list[dict[str, str]]:
    """Compare stored metadata against bytes; never mutates Mongo or storage."""
    issues: list[dict[str, str]] = []
    expected_size = media.get("size_bytes")
    if expected_size is not None and int(expected_size) != len(data):
        issues.append({"kind": "size_mismatch", "detail": f"metadata={expected_size}, object={len(data)}"})
    expected_hash = media.get("sha1")
    actual_hash = hashlib.sha1(data).hexdigest()
    if expected_hash and expected_hash != actual_hash:
        issues.append({"kind": "hash_mismatch", "detail": "sha1 differs"})
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            actual_mime = Image.MIME.get(image.format or "", "")
            width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        return issues + [{"kind": "undecodable", "detail": str(exc)[:200]}]
    if media.get("mime") and actual_mime and media["mime"].lower() != actual_mime.lower():
        issues.append({"kind": "mime_mismatch", "detail": f"metadata={media['mime']}, object={actual_mime}"})
    if media.get("width") is not None and int(media["width"]) != width:
        issues.append({"kind": "width_mismatch", "detail": f"metadata={media['width']}, object={width}"})
    if media.get("height") is not None and int(media["height"]) != height:
        issues.append({"kind": "height_mismatch", "detail": f"metadata={media['height']}, object={height}"})
    return issues
