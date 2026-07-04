"""PDF + XLSX image extraction. Preserves originals as base64 data-URLs."""
from __future__ import annotations
import base64
import hashlib
import logging
from io import BytesIO
from typing import Iterator

logger = logging.getLogger("forge.catalog_pipeline.image")


def _as_data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:16]


def extract_images_from_pdf(pdf_bytes: bytes) -> Iterator[tuple[int, str, str]]:
    """Yield (page_index_1based, sha1, data_url) for each image inside the PDF.
    Uses pypdf's low-level image accessor. Silently skips corrupted images."""
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as e:  # pragma: no cover
        logger.warning("pypdf missing: %s", e)
        return
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception as e:
        logger.warning("Cannot open PDF: %s", e)
        return

    seen: set[str] = set()
    for i, page in enumerate(reader.pages, start=1):
        try:
            imgs = list(page.images)
        except Exception as e:  # pragma: no cover
            logger.debug("page %s image list failed: %s", i, e)
            continue
        for im in imgs:
            try:
                data = im.data
                if not data:
                    continue
                h = _hash(data)
                if h in seen:
                    continue
                seen.add(h)
                mime = "image/jpeg"
                if data[:8].startswith(b"\x89PNG\r\n\x1a\n"):
                    mime = "image/png"
                yield i, h, _as_data_url(data, mime)
            except Exception:
                continue


def extract_images_from_xlsx(xlsx_bytes: bytes) -> Iterator[tuple[str, int, str, str]]:
    """Yield (sheet_name, anchor_row_1based, sha1, data_url) for each embedded image
    in every worksheet. Uses openpyxl's drawing anchors."""
    try:
        from openpyxl import load_workbook  # type: ignore
    except Exception as e:  # pragma: no cover
        logger.warning("openpyxl missing: %s", e)
        return
    try:
        wb = load_workbook(BytesIO(xlsx_bytes), data_only=True)
    except Exception as e:
        logger.warning("Cannot open XLSX: %s", e)
        return

    seen: set[str] = set()
    for ws in wb.worksheets:
        images = getattr(ws, "_images", []) or []
        for img in images:
            try:
                # Read underlying bytes
                if hasattr(img, "ref") and hasattr(img.ref, "read"):
                    data = img.ref.read()
                elif hasattr(img, "_data") and callable(img._data):
                    data = img._data()
                elif hasattr(img, "_data"):
                    data = img._data
                else:
                    continue
                if not data:
                    continue
                h = _hash(data)
                if h in seen:
                    continue
                seen.add(h)
                anchor = getattr(img, "anchor", None)
                row_idx = 0
                try:
                    row_idx = int(anchor._from.row) + 1  # type: ignore[attr-defined]
                except Exception:
                    row_idx = 0
                mime = "image/png" if data[:8].startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
                yield ws.title, row_idx, h, _as_data_url(data, mime)
            except Exception:
                continue
