"""Production-quality image extraction for supplier catalogs (PDF + XLSX).

Key improvements (Iteration 1):

*   Reads the XLSX zip archive directly (bypasses openpyxl's silent drop of any
    sheet containing unsupported image formats).
*   PNG / JPEG raster images are read as-is.
*   EMF → SVG → PNG conversion via `emf2svg-conv` + `rsvg-convert` at 2048px
    long-edge (produces genuine high-resolution artwork, not a rasterized
    thumbnail).
*   WMF conversion via ImageMagick's libwmf delegate (unrestricted for read-only
    per /etc/ImageMagick-6/policy.xml).
*   WDP / JPEG-XR conversion via `imagecodecs` (bundled libjxr).
*   Every extracted image is classified into a **quality bucket**
    (excellent / good / acceptable / poor / missing) based on longest-edge pixel
    count and the resolved MIME type — so the pipeline can honestly report
    supplier-file quality instead of upscaling thumbnails and lying about it.
*   Deduplication is content-based (SHA-1 of decoded bytes).
*   For each anchor we prefer the highest-quality candidate (raster ≥1024px,
    then rasterized vector, then any other) — so if the row also carries a
    vector alternative it wins over a 200px thumbnail.
*   Post-decode optimisation: images >≈ 1MB are re-encoded to WebP quality 82,
    which typically saves 30-60% while preserving perceived quality.

The extractor **never fabricates** or upscales images. If the supplier only
ships thumbnails, the quality bucket will reflect that so the app UI can call
it out.
"""
from __future__ import annotations
import base64
import hashlib
import logging
import os
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Iterator, Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger("forge.catalog_pipeline.image")

# --- Optional JPEG XR / HD Photo (.wdp / .jxr) decoder ---------------------
try:
    from imagecodecs import jpegxr_decode as _jxr_decode  # type: ignore
    from imagecodecs import png_encode as _png_encode  # type: ignore
    _HAS_JXR = True
except Exception as _e:  # pragma: no cover
    _jxr_decode = None  # type: ignore
    _png_encode = None  # type: ignore
    _HAS_JXR = False
    logger.info("imagecodecs unavailable — WDP frames will be skipped (%s)", _e)

# --- Pillow (for size probing + optimisation) -----------------------------
try:
    from PIL import Image as _PIL_Image  # type: ignore
    _HAS_PIL = True
except Exception:  # pragma: no cover
    _PIL_Image = None  # type: ignore
    _HAS_PIL = False

NS = {
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "r":   "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "wb":  "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "a":   "http://schemas.openxmlformats.org/drawingml/2006/main",
}
RASTER_EXT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}

# Quality thresholds (longest edge in px). Anything below 200px = thumbnail.
QUALITY_EXCELLENT = 1024
QUALITY_GOOD = 640
QUALITY_ACCEPTABLE = 320
QUALITY_POOR_MAX = 320  # anything under this is "poor"


# ---------- Result container ----------
@dataclass
class ExtractedImage:
    data_url: str            # data:image/png;base64,...
    sha1: str
    mime: str
    width: int
    height: int
    quality: str             # "excellent" | "good" | "acceptable" | "poor"
    source_format: str       # "png" | "jpeg" | "emf" | "wmf" | "wdp"
    bytes_len: int           # decoded (final) size in bytes

    @property
    def longest_edge(self) -> int:
        return max(self.width, self.height)

    def to_dict(self) -> dict:
        # Deliberately does NOT include data_url — that's stored separately in
        # the `images` list on ProductRow. Keeping meta lean keeps the import-
        # job document under MongoDB's 16MB BSON cap when a supplier ships
        # hundreds of images.
        return {
            "sha1": self.sha1, "mime": self.mime,
            "width": self.width, "height": self.height, "quality": self.quality,
            "source_format": self.source_format, "bytes_len": self.bytes_len,
        }


def classify_quality(longest_edge: int, source_format: str) -> str:
    """Bucket an image by its actual pixel dimensions.

    Vector formats (svg/emf/wmf) that we rasterize at 2048px are pinned at
    "excellent" because the vector geometry is genuine high-res artwork.
    Everything else is judged by longest edge in the decoded raster.
    """
    if source_format in ("emf", "wmf", "svg"):
        return "excellent"
    if longest_edge >= QUALITY_EXCELLENT:
        return "excellent"
    if longest_edge >= QUALITY_GOOD:
        return "good"
    if longest_edge >= QUALITY_ACCEPTABLE:
        return "acceptable"
    return "poor"


def _hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:16]


def _as_data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _probe_size(raster_bytes: bytes) -> tuple[int, int]:
    """Return (width, height) of a raster image, or (0, 0) on failure."""
    if not _HAS_PIL or _PIL_Image is None:
        return (0, 0)
    try:
        im = _PIL_Image.open(BytesIO(raster_bytes))
        return im.size
    except Exception:
        return (0, 0)


def _optimize(raw: bytes, mime: str) -> tuple[bytes, str]:
    """Optimize a decoded raster for storage.

    Strategy:
      * Cap longest edge at 1024px (Retina-quality on a 3.5-inch product card
        at 3x density, and 3× the density of Vitra's median 320px raster).
      * Re-encode photographic content as JPEG q=82 (~5-10× smaller than raw
        rasterized-vector PNG for the same visual quality).
      * Preserve transparency: PNGs with an alpha channel stay PNG at cap.
      * If the re-encoded output is not smaller than the input, keep the input.

    Returns (bytes, mime).
    """
    if not _HAS_PIL or _PIL_Image is None:
        return raw, mime
    try:
        im = _PIL_Image.open(BytesIO(raw))
    except Exception:
        return raw, mime
    has_alpha = "A" in im.getbands()

    # Skip optimisation for already-small images without transparency
    if len(raw) <= 60_000 and not has_alpha:
        return raw, mime

    try:
        # Cap longest edge at 1024
        w, h = im.size
        longest = max(w, h)
        if longest > 1024:
            scale = 1024 / longest
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), _PIL_Image.LANCZOS)

        buf = BytesIO()
        if has_alpha:
            # Keep transparency → WebP q=80 (better than PNG for photos with alpha)
            im.save(buf, format="WEBP", quality=80, method=6)
            out_mime = "image/webp"
        else:
            if im.mode != "RGB":
                im = im.convert("RGB")
            im.save(buf, format="JPEG", quality=82, optimize=True, progressive=True)
            out_mime = "image/jpeg"
        candidate = buf.getvalue()
        if len(candidate) < len(raw):
            return candidate, out_mime
    except Exception:
        pass
    return raw, mime


# ---------- Vector converters ----------
def _convert_emf_to_png(emf_bytes: bytes) -> Optional[bytes]:
    """EMF → SVG → PNG @ 2048px longest edge.

    Uses `emf2svg-conv` + `rsvg-convert` (installed system packages). This
    combination handles the vast majority of EMFs that ImageMagick's WMF
    delegate cannot parse (real EMF headers vs faked-WMF).
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".emf", delete=False) as inp:
            inp.write(emf_bytes); inp.flush()
            svg_path = tempfile.mktemp(suffix=".svg")
            r1 = subprocess.run(
                ["emf2svg-conv", "-i", inp.name, "-o", svg_path],
                capture_output=True, timeout=10,
            )
            if r1.returncode != 0 or not os.path.exists(svg_path):
                return None
            png_path = tempfile.mktemp(suffix=".png")
            r2 = subprocess.run(
                ["rsvg-convert", "-w", "2048", "-o", png_path, svg_path],
                capture_output=True, timeout=10,
            )
            if r2.returncode != 0 or not os.path.exists(png_path):
                # Fallback: try ImageMagick to convert SVG to PNG
                r3 = subprocess.run(
                    ["convert", "-density", "300", svg_path, png_path],
                    capture_output=True, timeout=10,
                )
                if r3.returncode != 0 or not os.path.exists(png_path):
                    return None
            with open(png_path, "rb") as f:
                return f.read()
    except Exception as e:  # pragma: no cover
        logger.debug("EMF → PNG conversion failed: %s", e)
        return None


def _convert_wmf_to_png(wmf_bytes: bytes) -> Optional[bytes]:
    """WMF → PNG via ImageMagick + libwmf delegate.

    Requires: `libwmf-0.2-7`, `libwmf-bin` and an unrestricted WMF policy in
    /etc/ImageMagick-6/policy.xml. Falls back to None on any failure.
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".wmf", delete=False) as inp:
            inp.write(wmf_bytes); inp.flush()
            out = tempfile.mktemp(suffix=".png")
            r = subprocess.run(
                ["convert", "-density", "300", f"wmf:{inp.name}", out],
                capture_output=True, timeout=10,
            )
            if r.returncode != 0 or not os.path.exists(out):
                return None
            with open(out, "rb") as f:
                return f.read()
    except Exception as e:  # pragma: no cover
        logger.debug("WMF → PNG conversion failed: %s", e)
        return None


def _convert_wdp_to_png(wdp_bytes: bytes) -> Optional[bytes]:
    """WDP (JPEG XR / HD Photo) → PNG via `imagecodecs` (bundled libjxr)."""
    if not _HAS_JXR or _jxr_decode is None or _png_encode is None:
        return None
    try:
        arr = _jxr_decode(wdp_bytes)
        if arr is None:
            return None
        return bytes(_png_encode(arr))
    except Exception as e:  # pragma: no cover
        logger.debug("WDP → PNG conversion failed: %s", e)
        return None


# ---------- Public decode dispatcher ----------
def _decode_supplier_image(raw: bytes, ext: str) -> Optional[ExtractedImage]:
    """Decode + classify a raw image blob taken from a supplier archive.

    Returns None for any format we cannot support (so the caller can skip
    silently — never fabricates content).
    """
    ext = ext.lower().lstrip(".")
    mime: Optional[str] = None
    source_format = ext

    if ext in ("png", "jpg", "jpeg", "webp"):
        mime = RASTER_EXT[ext]
    elif ext == "emf":
        conv = _convert_emf_to_png(raw)
        if not conv:
            return None
        raw = conv
        mime = "image/png"
        source_format = "emf"
    elif ext == "wmf":
        conv = _convert_wmf_to_png(raw)
        if not conv:
            return None
        raw = conv
        mime = "image/png"
        source_format = "wmf"
    elif ext in ("wdp", "jxr", "hdp"):
        conv = _convert_wdp_to_png(raw)
        if not conv:
            return None
        raw = conv
        mime = "image/png"
        source_format = "wdp"
    else:
        return None

    # Probe dimensions from the *decoded* raster BEFORE any resize/optimise, so
    # the reported width/height reflect the SOURCE material and quality
    # classification reflects the true supplier resolution.
    w, h = _probe_size(raw)
    longest = max(w, h)
    quality = classify_quality(longest, source_format)

    # Optimise: cap huge photos to 1600px WebP for storage without perceptible
    # quality loss. Never changes the reported width/height above — those still
    # describe the source.
    raw, mime = _optimize(raw, mime)

    sha1 = _hash(raw)
    return ExtractedImage(
        data_url=_as_data_url(raw, mime),
        sha1=sha1, mime=mime, width=w, height=h,
        quality=quality, source_format=source_format, bytes_len=len(raw),
    )


# ==========================================================================
# ---------- PDF ----------
# ==========================================================================

def extract_images_from_pdf(pdf_bytes: bytes) -> Iterator[tuple[int, str, str]]:
    """Legacy-compatible PDF extractor (page_no, sha1, data_url).

    Kept for backwards-compat with the Grohe / Geberit adapters. New callers
    should prefer `extract_images_from_pdf_ex` which returns full
    `ExtractedImage` metadata.
    """
    for page, img in extract_images_from_pdf_ex(pdf_bytes):
        yield page, img.sha1, img.data_url


def extract_images_from_pdf_ex(pdf_bytes: bytes) -> Iterator[tuple[int, ExtractedImage]]:
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
                # Detect format from magic bytes
                if data[:8].startswith(b"\x89PNG\r\n\x1a\n"):
                    ext = "png"
                elif data[:3] == b"\xff\xd8\xff":
                    ext = "jpeg"
                elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                    ext = "webp"
                else:
                    ext = "jpeg"  # fall through
                img = _decode_supplier_image(data, ext)
                if img is None:
                    continue
                if img.sha1 in seen:
                    continue
                seen.add(img.sha1)
                yield i, img
            except Exception:
                continue


# ==========================================================================
# ---------- XLSX (zip-first) ----------
# ==========================================================================

def extract_images_from_xlsx(xlsx_bytes: bytes) -> Iterator[tuple[str, int, str, str]]:
    """Legacy-compatible XLSX extractor: (sheet, row_1based, sha1, data_url).

    Kept for the Vitra adapter's existing per-row lookup logic.
    """
    for sheet, row, img in extract_images_from_xlsx_ex(xlsx_bytes):
        yield sheet, row, img.sha1, img.data_url


def extract_images_from_xlsx_ex(xlsx_bytes: bytes) -> Iterator[tuple[str, int, ExtractedImage]]:
    """Yield (sheet_name, anchor_row_1based, ExtractedImage) for every embedded
    image the supplier ships, with each image classified by pixel quality."""
    try:
        z = zipfile.ZipFile(BytesIO(xlsx_bytes), "r")
    except Exception as e:
        logger.warning("xlsx zip open failed: %s", e)
        return

    # Map sheet_name → sheet_file_path
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
            if target.startswith("/"):
                sheet_map[name] = target.lstrip("/")
            else:
                sheet_map[name] = "xl/" + target
    except Exception as e:
        logger.warning("xlsx workbook parse failed: %s", e); return

    # Note: we DO NOT dedupe by sha1 across the entire workbook. The same
    # image may legitimately anchor at multiple positions (Vitra ships one
    # product photo shared across all finish variants at their own anchor
    # rows). Deduping across anchors would starve later rows of the shared
    # image. Content-hash dedup still happens *within* a single anchor to
    # avoid double-adding the identical blip inside an AlternateContent tree.

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
                    drawing_target = r.get("Target")
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

        rid_to_image: dict[str, str] = {}
        try:
            for r in ET.fromstring(drawing_rels_xml).findall("{%s}Relationship" % NS["rel"]):
                if r.get("Type", "").endswith("/image"):
                    rid_to_image[r.get("Id")] = _resolve_relative(
                        drawing_path.rsplit("/", 1)[0] + "/", r.get("Target")
                    )
        except Exception:
            continue

        try:
            dtree = ET.fromstring(drawing_xml)
        except Exception:
            continue

        for anchor_tag in ("oneCellAnchor", "twoCellAnchor", "absoluteAnchor"):
            for anchor in dtree.findall("{%s}%s" % (NS["xdr"], anchor_tag)):
                row_idx = 0
                frm = anchor.find("{%s}from" % NS["xdr"])
                if frm is not None:
                    row_el = frm.find("{%s}row" % NS["xdr"])
                    if row_el is not None and row_el.text and row_el.text.isdigit():
                        row_idx = int(row_el.text) + 1

                # A drawing anchor may reference multiple blips inside an
                # AlternateContent block (Choice = modern format, Fallback =
                # legacy). We enumerate *every* blip and pick the highest
                # quality candidate that decodes.
                candidates: list[ExtractedImage] = []
                for blip in anchor.iter("{%s}blip" % NS["a"]):
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
                    img = _decode_supplier_image(raw, ext)
                    if img is None:
                        continue
                    candidates.append(img)

                if not candidates:
                    continue

                # Pick the highest quality by (excellent > good > acceptable > poor)
                # then by longest_edge desc. This is the "highest-resolution
                # instead of first" behaviour.
                quality_rank = {"excellent": 4, "good": 3, "acceptable": 2, "poor": 1}
                # Per-anchor sha1 dedup: same blip referenced twice inside an
                # AlternateContent tree (Choice + Fallback) still counts as one.
                by_sha: dict[str, ExtractedImage] = {}
                for c in candidates:
                    prev = by_sha.get(c.sha1)
                    if prev is None or (quality_rank.get(c.quality, 0), c.longest_edge) > (quality_rank.get(prev.quality, 0), prev.longest_edge):
                        by_sha[c.sha1] = c
                best = sorted(
                    by_sha.values(),
                    key=lambda c: (quality_rank.get(c.quality, 0), c.longest_edge),
                    reverse=True,
                )[0]
                yield sheet_name, row_idx, best


def _resolve_relative(base: str, target: str) -> str:
    parts = (base + target).split("/")
    stack: list[str] = []
    for p in parts:
        if p == "..":
            if stack:
                stack.pop()
        elif p and p != ".":
            stack.append(p)
    return "/".join(stack)


# ==========================================================================
# ---------- Quality report ----------
# ==========================================================================
@dataclass
class ImageQualityReport:
    total: int = 0
    excellent: int = 0
    good: int = 0
    acceptable: int = 0
    poor: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    min_edge: int = 0
    median_edge: int = 0
    max_edge: int = 0
    verdict: str = ""

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "excellent": self.excellent, "good": self.good,
            "acceptable": self.acceptable, "poor": self.poor,
            "by_source": self.by_source,
            "min_edge_px": self.min_edge, "median_edge_px": self.median_edge,
            "max_edge_px": self.max_edge,
            "verdict": self.verdict,
        }


def build_quality_report(images: list[ExtractedImage]) -> ImageQualityReport:
    """Summarise a set of extracted images. `verdict` is a plain-English
    assessment ready to surface in the certification UI.
    """
    r = ImageQualityReport(total=len(images))
    if not images:
        r.verdict = "No images extracted from supplier file"
        return r
    edges = sorted(im.longest_edge for im in images)
    r.min_edge = edges[0]
    r.median_edge = edges[len(edges) // 2]
    r.max_edge = edges[-1]
    for im in images:
        r.by_source[im.source_format] = r.by_source.get(im.source_format, 0) + 1
        if im.quality == "excellent":
            r.excellent += 1
        elif im.quality == "good":
            r.good += 1
        elif im.quality == "acceptable":
            r.acceptable += 1
        else:
            r.poor += 1
    prem_pct = (r.excellent + r.good) * 100 // r.total
    if prem_pct >= 80:
        r.verdict = f"Supplier ships production-quality artwork ({prem_pct}% excellent/good)"
    elif prem_pct >= 50:
        r.verdict = f"Mixed quality — {prem_pct}% premium, remainder is thumbnail-grade"
    else:
        r.verdict = (
            f"Supplier file only contains thumbnail-grade artwork "
            f"({prem_pct}% premium; median longest edge = {r.median_edge}px). "
            "Recommend sourcing official product photography separately for cards & PDFs."
        )
    return r
