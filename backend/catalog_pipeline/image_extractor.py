"""PDF + XLSX image extraction.

For XLSX we parse the zip archive directly (not via openpyxl) because openpyxl
silently drops images from sheets that contain any unsupported format (WMF, WDP).
Every raster image (PNG/JPEG/JPG) is read as-is; EMF is converted to PNG via
ImageMagick when available; WDP (JPEG XR / HD Photo) is decoded natively via
`imagecodecs` and re-encoded as PNG — this closes the ~2.7% VITRA image gap
without any external system dependency.
"""
from __future__ import annotations
import base64
import hashlib
import logging
import re
import subprocess
import tempfile
import zipfile
from io import BytesIO
from typing import Iterator
from xml.etree import ElementTree as ET

logger = logging.getLogger("forge.catalog_pipeline.image")

# --- Optional JPEG XR / HD Photo (.wdp / .jxr) decoder ----------------------
# imagecodecs bundles libjxr statically so we don't need libjxr/JxrDecApp
# installed on the OS. If the wheel isn't present the extractor still runs;
# WDP frames are simply skipped as before.
try:
    from imagecodecs import jpegxr_decode as _jxr_decode  # type: ignore
    from imagecodecs import png_encode as _png_encode  # type: ignore
    _HAS_JXR = True
except Exception as _e:  # pragma: no cover
    _jxr_decode = None  # type: ignore
    _png_encode = None  # type: ignore
    _HAS_JXR = False
    logger.info("imagecodecs unavailable — WDP frames will be skipped (%s)", _e)

NS = {
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "r":   "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "wb":  "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
}
RASTER_EXT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}


def _hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:16]


def _as_data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _convert_emf_to_png(emf_bytes: bytes) -> bytes | None:
    """Convert EMF to PNG using ImageMagick, if available."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".emf", delete=False) as inp:
            inp.write(emf_bytes); inp.flush()
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as out:
                res = subprocess.run(
                    ["convert", inp.name, out.name],
                    capture_output=True, timeout=8,
                )
                if res.returncode != 0:
                    return None
                with open(out.name, "rb") as f:
                    return f.read()
    except Exception as e:  # pragma: no cover
        logger.debug("EMF conversion failed: %s", e)
        return None


def _convert_wdp_to_png(wdp_bytes: bytes) -> bytes | None:
    """Decode a JPEG XR / HD Photo (.wdp / .jxr) image and re-encode as PNG.

    Uses `imagecodecs` (bundles libjxr) so we don't need JxrDecApp or ImageMagick
    with a JXR delegate installed on the OS. Returns None on any failure so the
    caller can fall through to "skip" behaviour identical to before.
    """
    if not _HAS_JXR or _jxr_decode is None or _png_encode is None:
        return None
    try:
        arr = _jxr_decode(wdp_bytes)
        if arr is None:
            return None
        # png_encode handles uint8/uint16 grayscale, RGB and RGBA arrays.
        return bytes(_png_encode(arr))
    except Exception as e:  # pragma: no cover
        logger.debug("WDP → PNG conversion failed: %s", e)
        return None


# ---------- PDF ----------

def extract_images_from_pdf(pdf_bytes: bytes) -> Iterator[tuple[int, str, str]]:
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
        except Exception:
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
                mime = "image/png" if data[:8].startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
                yield i, h, _as_data_url(data, mime)
            except Exception:
                continue


# ---------- XLSX (zip-first) ----------

def extract_images_from_xlsx(xlsx_bytes: bytes) -> Iterator[tuple[str, int, str, str]]:
    """Yield (sheet_name, anchor_row_1based, sha1, data_url) for every embedded
    raster image. Also decodes EMF via ImageMagick when possible."""
    try:
        z = zipfile.ZipFile(BytesIO(xlsx_bytes), "r")
    except Exception as e:
        logger.warning("xlsx zip open failed: %s", e)
        return

    # Map sheet_name → sheet_file_path (e.g. worksheets/sheet1.xml)
    sheet_map: dict[str, str] = {}
    try:
        wb_xml = z.read("xl/workbook.xml")
        wb_rels_xml = z.read("xl/_rels/workbook.xml.rels")
        wb_tree = ET.fromstring(wb_xml)
        rels_tree = ET.fromstring(wb_rels_xml)
        rid_to_target = {
            r.get("Id"): r.get("Target") for r in rels_tree.findall("{%s}Relationship" % NS["rel"])
        }
        for sh in wb_tree.findall("{%s}sheets/{%s}sheet" % (NS["wb"], NS["wb"])):
            rid = sh.get("{%s}id" % NS["r"])
            name = sh.get("name") or ""
            target = rid_to_target.get(rid) or ""
            # Two conventions in the wild:
            #   • relative: "worksheets/sheet1.xml" → resolve against "xl/"
            #   • absolute: "/xl/worksheets/sheet1.xml" → use directly
            if target.startswith("/"):
                sheet_map[name] = target.lstrip("/")
            else:
                sheet_map[name] = "xl/" + target
    except Exception as e:
        logger.warning("xlsx workbook parse failed: %s", e); return

    seen: set[str] = set()

    # For each sheet, find its drawing (via sheet rels), parse anchors + images.
    for sheet_name, sheet_path in sheet_map.items():
        rels_path = sheet_path.rsplit("/", 1)[0] + "/_rels/" + sheet_path.rsplit("/", 1)[1] + ".rels"
        try:
            sheet_rels = z.read(rels_path)
        except KeyError:
            continue
        drawing_target = None
        try:
            for r in ET.fromstring(sheet_rels).findall("{%s}Relationship" % NS["rel"]):
                if r.get("Type", "").endswith("/drawing"):
                    drawing_target = r.get("Target")  # e.g. "../drawings/drawing1.xml"
                    break
        except Exception:
            continue
        if not drawing_target:
            continue

        drawing_path = _resolve_relative("xl/worksheets/", drawing_target)
        drawing_rels_path = drawing_path.rsplit("/", 1)[0] + "/_rels/" + drawing_path.rsplit("/", 1)[1] + ".rels"

        try:
            drawing_xml = z.read(drawing_path)
            drawing_rels_xml = z.read(drawing_rels_path)
        except KeyError:
            continue

        # rId → image path
        rid_to_image: dict[str, str] = {}
        try:
            for r in ET.fromstring(drawing_rels_xml).findall("{%s}Relationship" % NS["rel"]):
                if r.get("Type", "").endswith("/image"):
                    rid_to_image[r.get("Id")] = _resolve_relative(drawing_path.rsplit("/", 1)[0] + "/", r.get("Target"))
        except Exception:
            continue

        # Parse anchors
        try:
            dtree = ET.fromstring(drawing_xml)
        except Exception:
            continue
        for anchor_tag in ("oneCellAnchor", "twoCellAnchor", "absoluteAnchor"):
            for anchor in dtree.findall("{%s}%s" % (NS["xdr"], anchor_tag)):
                # anchor row (1-based)
                row_idx = 0
                frm = anchor.find("{%s}from" % NS["xdr"])
                if frm is not None:
                    row_el = frm.find("{%s}row" % NS["xdr"])
                    if row_el is not None and row_el.text and row_el.text.isdigit():
                        row_idx = int(row_el.text) + 1
                # embed rId
                blip = anchor.find(".//{%s}blip" % "http://schemas.openxmlformats.org/drawingml/2006/main")
                if blip is None:
                    continue
                rid = blip.get("{%s}embed" % NS["r"])
                img_path = rid_to_image.get(rid or "")
                if not img_path:
                    continue

                ext = img_path.rsplit(".", 1)[-1].lower()
                try:
                    raw = z.read(img_path)
                except KeyError:
                    continue
                if not raw:
                    continue

                mime = RASTER_EXT.get(ext)
                if mime is None:
                    if ext == "emf":
                        conv = _convert_emf_to_png(raw)
                        if not conv:
                            continue
                        raw, mime = conv, "image/png"
                    elif ext in ("wdp", "jxr", "hdp"):
                        conv = _convert_wdp_to_png(raw)
                        if not conv:
                            continue
                        raw, mime = conv, "image/png"
                    else:
                        # Other unsupported vector formats: skip
                        continue

                h = _hash(raw)
                if h in seen:
                    continue
                seen.add(h)
                yield sheet_name, row_idx, h, _as_data_url(raw, mime)


def _resolve_relative(base: str, target: str) -> str:
    """Resolve a target like '../drawings/drawing1.xml' against a base path."""
    parts = (base + target).split("/")
    stack: list[str] = []
    for p in parts:
        if p == "..":
            if stack:
                stack.pop()
        elif p and p != ".":
            stack.append(p)
    return "/".join(stack)
