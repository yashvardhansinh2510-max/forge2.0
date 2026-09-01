"""Official BuildCon House quotation PDF — faithful A4 print template."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import functools
from io import BytesIO
import logging
from pathlib import Path
from time import monotonic
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    Flowable, HRFlowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)
from services.pdf_image_loader import image_loader_metrics, prefetch_urls, remote_image_bytes

logger = logging.getLogger("forge.pdf")

BLUE = colors.HexColor("#1D5D98")
INK = colors.HexColor("#111111")
GREY = colors.HexColor("#6F6F6F")
LINE = colors.HexColor("#8E8E8E")
GRID = colors.HexColor("#9C9C9C")
HEADER_GREY = colors.HexColor("#C8C8C8")
ZEBRA = colors.HexColor("#F0F0F0")
WHITE = colors.white
PDF_DIR = Path(__file__).resolve().parent
LOGO_PATH = PDF_DIR / "buildcon_logo.png"
LOGO_RATIO = 1414 / 412  # native W/H of buildcon_logo.png — size by one edge only
# A single page contract for every customer-facing quotation artifact.  Keep
# this shared instead of allowing individual generators to silently fall back
# to portrait A4.
LANDSCAPE_A4 = landscape(A4)

# Original page-1 partner layout from the supplied quotation template.
BRAND_PARTNERS = [
    [("GROHE", "Pure Freude an Wasser"), ("hansgrohe", "Life is Waterful"), ("AXOR", "Form Follows Perfection"), ("VitrA", "Design Meets Life"), ("NEXION", "The Surface Experience"), ("QUTONE", "Let's Build Together")],
    [("DIMORE", "Reflection of Your Style"), ("Oyster", "Indulge in Luxury"), ("GEBERIT", "Engineered for Hygiene"), ("MCM ITTIMI", "Innovation into Inspiration"), ("VERANTES LIVING", "Kitchens &amp; Wardrobes"), ("IMPORTED<br/>FURNITURE", "Crafted Beyond Borders")],
]


def brand_partners_table(base_cell_style: ParagraphStyle, col_width_mm: float = 44.5, grid_color=None) -> Table:
    """The original 2x6 partner grid used on quotation page 1."""
    partner_style = ParagraphStyle("partner", parent=base_cell_style, fontSize=6.6, leading=8, alignment=1)
    rows = [[Paragraph(f"<b>{name}</b><br/><font size='5.4'><i>{tagline}</i></font>", partner_style) for name, tagline in row] for row in BRAND_PARTNERS]
    table = Table(rows, colWidths=[col_width_mm * mm] * 6, rowHeights=[12 * mm, 12 * mm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, grid_color or GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table

# --- Dynamic pagination geometry (item/product table, pages 2+) -----------
# Page size + margins are unchanged (preserving the exact print template),
# but rows now render only for real content — no fixed 16-row block padded
# with blank filler rows. `_max_item_rows_per_page` derives the true capacity
# from real geometry so it automatically adapts if row height/typography
# ever changes, instead of a hardcoded magic number.
PAGE_H_MM = 210.0  # A4 landscape
TOP_MARGIN_MM = 13.0
BOTTOM_MARGIN_MM = 22.0
AREA_HEADER_BLOCK_MM = 25.75    # brand/area title block + rule + spacers above the table
ITEM_HEADER_ROW_MM = 10.0
# A sanitary bathroom detail page can hold up to seventeen products. The
# available table height is shared by only the real rows on a page, so an
# eight- or ten-product sheet fills the page without blank product rows.
MAX_ITEM_ROWS_PER_PAGE = 17
PRODUCT_IMAGE_ASPECT_RATIO = 16 / 10
STANDARD_PRODUCT_IMAGE_WIDTH_MM = 16.0
STANDARD_PRODUCT_IMAGE_HEIGHT_MM = STANDARD_PRODUCT_IMAGE_WIDTH_MM / PRODUCT_IMAGE_ASPECT_RATIO
# This is the minimum row height used for capacity calculation.  Actual rows
# are expanded per page to occupy all usable space.
ITEM_ROW_MM = 14.0
ITEM_TOTAL_ROW_MM = 8.0
SUMMARY_HEADER_ROW_MM = 7.0
SUMMARY_ROW_MM = 5.6
SUMMARY_TOTAL_ROW_MM = 6.2


def _max_item_rows_per_page() -> int:
    # Row height is allocated dynamically by `_item_row_height_mm`; capacity
    # is therefore the business/print limit, not a stale minimum-row division.
    return MAX_ITEM_ROWS_PER_PAGE


def _item_row_height_mm(item_count: int) -> float:
    """Height assigned to each real product row on one sanitary detail page."""
    usable = PAGE_H_MM - TOP_MARGIN_MM - BOTTOM_MARGIN_MM - AREA_HEADER_BLOCK_MM - ITEM_HEADER_ROW_MM - ITEM_TOTAL_ROW_MM
    return usable / max(1, item_count)


def _money(value: float) -> str:
    return f"{float(value or 0):,.2f}"


def _escape(value: object) -> str:
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ellipsize(value: object, limit: int) -> str:
    """Escape a bounded, table-safe representation of user-provided text.

    Detail rows have an intentionally fixed maximum height so a full 17-row
    page remains printable.  Paragraphs otherwise overflow the row for a
    very long SKU/name/finish; ellipsizing preserves the useful prefix and
    makes that capacity explicit instead of allowing drawing over grid lines.
    """
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip() + "…"
    return _escape(text)


def quotation_pdf_filename(customer_name: object) -> str:
    """Return the sanitary quotation download name, based on the customer.

    Keep this deliberately separate from the document number: customers use
    the PDF as a shareable selection sheet, so its filename should identify
    the customer in the same way the Ground Floor documents do.  Strip only
    characters that are invalid or unsafe in a cross-platform filename.
    """
    name = " ".join(str(customer_name or "Customer").split())
    safe = " ".join("".join(ch for ch in name if ch not in '\\\\/:*?\"<>|').split()).strip(".")
    return f"{safe or 'Customer'}.pdf"


# Kept as a local alias so quotation/PDF callers and existing tests can
# instrument image loading without importing the security implementation.
_remote_image_bytes = remote_image_bytes


def _prepare_image_bytes(data: bytes, *, force_landscape: bool = False) -> bytes:
    """Bake EXIF orientation without rotating, cropping, or stretching media.

    ``force_landscape`` is retained only as a backwards-compatible keyword for
    callers saved before the orientation fix.  PDF rendering must never infer
    rotation from a product's physical dimensions: a portrait basin and a
    portrait tile are both valid portrait photographs.
    """
    from PIL import Image as PILImage
    from PIL import ImageOps

    try:
        with PILImage.open(BytesIO(data)) as opened:
            # Animated GIFs cannot be safely re-encoded without discarding
            # frames, and ReportLab will use the first frame as before.
            if (opened.format or "").upper() == "GIF":
                return data
            image = ImageOps.exif_transpose(opened)
            image.load()
            fmt = (opened.format or "PNG").upper()
        output_format = {"JPG": "JPEG", "JPEG": "JPEG", "PNG": "PNG", "WEBP": "WEBP"}.get(fmt)
        if not output_format:
            return data
        out = BytesIO()
        save_image = image.convert("RGB") if output_format == "JPEG" and image.mode not in ("RGB", "L") else image
        save_image.save(out, format=output_format)
        return out.getvalue()
    except Exception:
        return data


def prefetch_product_images(items: Iterable[dict], *, workers: int = 6, timeout: float = 8.0) -> None:
    """Warm the bounded image cache concurrently under one total deadline.

    ReportLab itself remains synchronous, but after this pass every `_img`
    lookup is normally an in-memory cache hit. Missing, corrupt and timed-out
    images retain the existing placeholder behavior.
    """
    urls = list(dict.fromkeys(
        str(item.get("image")) for item in items
        if str(item.get("image") or "").startswith(("https://", "http://"))
    ))
    if not urls:
        return
    prefetch_urls(urls, _remote_image_bytes, workers=workers, timeout=timeout)


def contain_box(
    source_width: float,
    source_height: float,
    box_width: float,
    box_height: float,
    inset: float = 0,
) -> tuple[float, float, float, float]:
    """Return a centered aspect-preserving box inside a target rectangle."""
    inner_width = max(0.0, box_width - (inset * 2))
    inner_height = max(0.0, box_height - (inset * 2))
    if source_width <= 0 or source_height <= 0 or inner_width <= 0 or inner_height <= 0:
        return inset, inset, 0.0, 0.0
    scale = min(inner_width / source_width, inner_height / source_height)
    width = source_width * scale
    height = source_height * scale
    return (
        inset + (inner_width - width) / 2,
        inset + (inner_height - height) / 2,
        width,
        height,
    )


class _CoverImage(Flowable):
    """An aspect-preserving product image clipped to fill its whole cell."""

    def __init__(self, data: bytes, width_mm: float, height_mm: float):
        super().__init__()
        self.reader = ImageReader(BytesIO(data))
        self.width = width_mm * mm
        self.height = height_mm * mm
        # Match ReportLab Image's public geometry attributes so instrumentation
        # and layout checks can inspect every image flowable consistently.
        self.drawWidth = self.width
        self.drawHeight = self.height
        self.source_width, self.source_height = self.reader.getSize()

    def wrap(self, avail_width, avail_height):
        return self.width, self.height

    def draw(self):
        if self.source_width <= 0 or self.source_height <= 0:
            return
        scale = max(self.width / self.source_width, self.height / self.source_height)
        drawn_width = self.source_width * scale
        drawn_height = self.source_height * scale
        path = self.canv.beginPath()
        path.rect(0, 0, self.width, self.height)
        self.canv.saveState()
        self.canv.clipPath(path, stroke=0, fill=0)
        self.canv.drawImage(
            self.reader, (self.width - drawn_width) / 2, (self.height - drawn_height) / 2,
            width=drawn_width, height=drawn_height, mask="auto",
        )
        self.canv.restoreState()


def _img(
    url: str | None,
    width_mm: float = STANDARD_PRODUCT_IMAGE_WIDTH_MM,
    height_mm: float = STANDARD_PRODUCT_IMAGE_HEIGHT_MM,
    force_landscape: bool = False,
    cover: bool = False,
) -> Flowable:
    """Render the supplied product image inside the quotation image cell.

    Preserve the full image in a centered contain box. Product imagery is a
    product-selection aid, so it must never be cropped merely to fill a table
    cell; blank space is preferable to hiding the item being quoted.
    """
    if url and str(url).startswith(("https://", "http://")):
        data = _remote_image_bytes(str(url))
        if data:
            try:
                prepared = _prepare_image_bytes(data, force_landscape=force_landscape)
                reader = ImageReader(BytesIO(prepared))
                source_width, source_height = reader.getSize()
                _, _, image_width, image_height = contain_box(
                    source_width, source_height, width_mm, height_mm, inset=1.25,
                )
                image = Image(
                    BytesIO(prepared), width=image_width * mm, height=image_height * mm,
                )
                image.hAlign = "CENTER"
                return image
            except Exception:
                pass
    return Paragraph("<i><font color='#999999' size='7'>[image]</font></i>", ParagraphStyle("image-placeholder", alignment=1, leading=8))


def _draw_footer(cv, doc, branding: dict | None = None) -> None:
    b = branding or {}
    cv.saveState()
    page_width, _ = LANDSCAPE_A4
    cv.setStrokeColor(LINE)
    cv.setLineWidth(0.45)
    cv.line(0, 15 * mm, page_width, 15 * mm)
    cv.setFillColor(INK)
    cv.setFont("Helvetica-Bold", 8)
    cv.drawString(doc.leftMargin, 10.5 * mm, b.get("footer_company_name") or "Buildcon House")
    cv.setFillColor(INK)
    cv.setFont("Helvetica", 7)
    cv.drawString(doc.leftMargin, 6.5 * mm, f"M: {b.get('footer_phone') or '+91 99099 06652'}   |   {b.get('footer_email') or 'buildconhouse10@gmail.com'}")
    right = page_width - doc.rightMargin
    cv.setFont("Helvetica", 7)
    cv.drawRightString(right, 10.5 * mm, f"Page {doc.page}")
    cv.setFillColor(BLUE)
    cv.setFont("Helvetica-Oblique", 7)
    cv.drawRightString(right, 6.5 * mm, b.get("footer_tagline") or "One Destination. Infinite Possibilities.")
    cv.restoreState()


def watermark_geometry(page_width: float, page_height: float) -> tuple[float, float, float, float]:
    """Return the full-page logo placement (x, y, width, height)."""
    height = page_height
    width = height * LOGO_RATIO
    return (page_width - width) / 2, 0, width, height


def _draw_room_watermark(cv, doc, branding: dict | None = None) -> None:
    b = branding or {}
    if not b.get("show_watermark", True):
        return
    if not LOGO_PATH.exists():
        return
    cv.saveState()
    # Cover the entire landscape sheet while retaining the logo's aspect
    # ratio.  ReportLab clips the oversized image to the media box.
    if hasattr(cv, "setFillAlpha"):
        cv.setFillAlpha(0.055)
    page_width, page_height = LANDSCAPE_A4
    watermark_x, watermark_y, watermark_w, watermark_h = watermark_geometry(page_width, page_height)
    cv.drawImage(str(LOGO_PATH), watermark_x, watermark_y, width=watermark_w, height=watermark_h, mask="auto")
    cv.restoreState()


def _draw_quotation_page_chrome(cv, doc, branding: dict | None = None) -> None:
    """Shared footer/watermark chrome for the summary and area pages."""
    _draw_room_watermark(cv, doc, branding)
    _draw_footer(cv, doc, branding)


def _brand_header(right_title: str, styles: dict, style_key: str = "titleRight") -> Table:
    logo: Flowable
    if LOGO_PATH.exists():
        logo_width = 43 * mm
        logo = Image(str(LOGO_PATH), width=logo_width, height=logo_width / LOGO_RATIO, kind="proportional")
    else:
        logo = Paragraph("<b>BUILDCON HOUSE</b><br/><font size='8'>Let You Live Better</font>", styles["brandFallback"])
    table = Table([[logo, Paragraph(right_title, styles[style_key])]], colWidths=[165 * mm, 102 * mm])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return table


def _room_totals(items: Iterable[dict]) -> tuple[float, float, float]:
    """Returns (mrp_total, discount, net). `mrp_total` uses each line's real
    catalog MRP (falling back to unit_price for older quotations saved before
    the mrp field existed) — it is NOT the pre-discount offer subtotal."""
    mrp_total = subtotal = discount = 0.0
    for item in items:
        qty = float(item.get("qty") or 0)
        unit_price = float(item.get("unit_price") or 0)
        mrp = float(item.get("mrp") or unit_price)
        gross = qty * unit_price
        disc = gross * float(item.get("discount_pct") or 0) / 100
        mrp_total += qty * mrp
        subtotal += gross
        discount += disc
    return mrp_total, discount, subtotal - discount


def _format_pdf_date(raw: str | None) -> str:
    """Human-readable "15 Jul 2026" — matches the en-IN date formatting used
    everywhere else in the app (Quotations list, Customer Portal, etc.)
    instead of a raw ISO slice like "2026-07-15" which is what every
    quotation PDF showed before this fix."""
    value = raw or datetime.now().isoformat()
    try:
        # Handles both "...Z" and "+00:00"-style offsets.
        cleaned = value.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).strftime("%d %b %Y")
    except (ValueError, TypeError):
        return value[:10] if isinstance(value, str) else datetime.now().strftime("%d %b %Y")


def build_quotation_pdf(quotation: dict, customer: dict, branding: dict | None = None) -> bytes:
    """Render the supplied BuildCon House A4 quotation template.

    Page one is the commercial summary / contractual page, with a dynamic
    per-room summary table (exactly one row per room — never padded, never
    truncated). Each room then starts on its own itemised page(s); item rows
    are fully dynamic (only real products render, no blank filler rows) and
    paginate automatically once a room's item count exceeds one page's real
    capacity (`_max_item_rows_per_page`), repeating the brand/area header and
    column headers on every continuation page while keeping SR NO. counting
    up instead of restarting. Pricing columns switch automatically for the
    whole document depending on whether ANY line item carries a discount —
    MRP/Offer Rate/Offer Total when discounted, plain Rate/Total otherwise —
    never mixing the two within a single PDF.

    `branding` (optional) is the merged Settings > Company + Settings > PDF
    dict — footer text, watermark on/off, an appended "additional terms" line,
    and an appended signatory line. Every key has a fallback identical to what
    was hardcoded here before Settings > PDF existed, so passing None (or a
    partial dict) renders the same document as before.
    """
    started_at = monotonic()
    b = branding or {}
    prefetch_product_images(quotation.get("items") or [])
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LANDSCAPE_A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=13 * mm, bottomMargin=22 * mm, title=quotation.get("number", "Quotation"),
        author=b.get("footer_company_name") or "Buildcon House",
    )
    base = getSampleStyleSheet()
    styles = {
        "brandFallback": ParagraphStyle("brandFallback", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=14, leading=15, textColor=INK),
        "titleRight": ParagraphStyle("titleRight", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=14, leading=16, textColor=INK, alignment=2),
        "areaTitle": ParagraphStyle("areaTitle", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=15.5, leading=17.5, textColor=INK, alignment=2),
        "label": ParagraphStyle("label", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=6.8, leading=8, textColor=INK),
        "body": ParagraphStyle("body", parent=base["Normal"], fontName="Helvetica", fontSize=8.4, leading=11.5, textColor=INK),
        "small": ParagraphStyle("small", parent=base["Normal"], fontName="Helvetica", fontSize=6.7, leading=8, textColor=INK),
        "terms": ParagraphStyle("terms", parent=base["Normal"], fontName="Helvetica", fontSize=6.1, leading=7.0, textColor=INK),
        "tiny": ParagraphStyle("tiny", parent=base["Normal"], fontName="Helvetica", fontSize=7.2, leading=8.8, textColor=INK, alignment=1),
        "itemText": ParagraphStyle("itemText", parent=base["Normal"], fontName="Helvetica", fontSize=5.2, leading=5.2, textColor=INK, alignment=1),
        "itemCenter": ParagraphStyle("itemCenter", parent=base["Normal"], fontName="Helvetica", fontSize=5.4, leading=5.4, textColor=INK, alignment=1),
        "section": ParagraphStyle("section", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=INK),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontName="Helvetica", fontSize=7.4, leading=9, textColor=INK, alignment=1),
        "cellRight": ParagraphStyle("cellRight", parent=base["Normal"], fontName="Helvetica", fontSize=7.4, leading=9, textColor=INK, alignment=2),
        "cellCenter": ParagraphStyle("cellCenter", parent=base["Normal"], fontName="Helvetica", fontSize=7.4, leading=9, textColor=INK, alignment=1),
        "tableHead": ParagraphStyle("tableHead", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.4, leading=8.6, textColor=INK, alignment=1),
        "signature": ParagraphStyle("signature", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7, leading=8, textColor=INK, alignment=2),
    }
    # Discount-aware layout mode — decided ONCE for the whole document so the
    # summary table and every item table switch columns consistently (never
    # mixed within a single PDF). Signal: the quotation's own resolved
    # discount_total, backed up by a direct scan of line-item discount_pct
    # (both should always agree since callers resolve effective pct into
    # each item before invoking this function — see _enriched_items_for_pdf).
    has_discount = float(quotation.get("discount_total") or 0) > 0.005 or any(
        float(item.get("discount_pct") or 0) > 0 for item in quotation.get("items", [])
    )
    story: list[Flowable] = []
    created = _format_pdf_date(quotation.get("created_at"))
    room_order = list(quotation.get("rooms") or [])
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in quotation.get("items", []):
        grouped[item.get("room") or "General"].append(item)
    for room in grouped:
        if room not in room_order:
            room_order.append(room)
    room_order = [r for r in room_order if grouped.get(r)]  # never render a room with 0 items

    # --- PAGE 1: Header and commercial summary --------------------------------
    story.append(_brand_header("PRICE QUOTATION<br/><font name='Helvetica' size='8'>Bath &amp; Sanitaryware Solutions</font>", styles))
    story.extend([Spacer(1, 3 * mm), HRFlowable(width="100%", thickness=1.25, color=BLUE), Spacer(1, 2.5 * mm)])
    meta = [
        [Paragraph("CUSTOMER NAME", styles["label"]), Paragraph("CONTACT NO.", styles["label"]), Paragraph("QUOTATION DATE", styles["label"])],
        [Paragraph(_escape(customer.get("company") or customer.get("name") or quotation.get("customer_name")), styles["body"]), Paragraph(_escape(quotation.get("phone_snapshot") or customer.get("phone") or ""), styles["body"]), Paragraph(created, styles["body"])],
        [Paragraph("QUOTATION NO.", styles["label"]), Paragraph("REFERENCE", styles["label"]), Paragraph("PROJECT", styles["label"])],
        [Paragraph(_escape(quotation.get("number")), styles["body"]), Paragraph(_escape(quotation.get("reference_source") or ""), styles["body"]), Paragraph(_escape(quotation.get("project_name") or ""), styles["body"])],
    ]
    meta_row_heights = [5 * mm, 5 * mm, 5 * mm, 5 * mm]
    meta_style = [
        ("LINEBELOW", (0, 1), (-1, 1), 0.4, LINE),
        ("LINEBELOW", (0, 3), (-1, 3), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]
    for label, value in [
        ("REFERRED BY", quotation.get("referrer_name")),
        ("SITE / DELIVERY ADDRESS", quotation.get("address_snapshot") or customer.get("address")),
    ]:
        if value:
            row = len(meta)
            meta.extend([[Paragraph(label, styles["label"]), "", ""], [Paragraph(_escape(value), styles["body"]), "", ""]])
            meta_row_heights.extend([4 * mm, 6 * mm])
            meta_style.extend([
                ("SPAN", (0, row), (-1, row)), ("SPAN", (0, row + 1), (-1, row + 1)),
                ("LINEBELOW", (0, row + 1), (-1, row + 1), 0.4, LINE),
            ])
    meta_table = Table(meta, colWidths=[90 * mm, 90 * mm, 87 * mm], rowHeights=meta_row_heights)
    meta_table.setStyle(TableStyle(meta_style))
    story.extend([meta_table, Spacer(1, 2 * mm)])
    story.append(Paragraph("Dear Sir/Madam, thank you for your interest in our products. We are pleased to offer our most competitive rates for premium bath and sanitaryware fittings, prepared as per your requirements.", styles["body"]))
    story.extend([Spacer(1, 3 * mm), Paragraph("QUOTATION SUMMARY", styles["section"]), Spacer(1, 1.5 * mm)])

    # ---- Dynamic Quotation Summary: exactly one row per room, no filler ----
    n_rooms = len(room_order)
    if has_discount:
        summary_header = ["SL. NO.", "BATHROOM / AREA", "MRP (Rs.)", "OFFER TOTAL (Rs.)"]
        summary_col_widths = [20 * mm, 120 * mm, 63 * mm, 64 * mm]
    else:
        summary_header = ["SL. NO.", "BATHROOM / AREA", "TOTAL (Rs.)"]
        summary_col_widths = [20 * mm, 135 * mm, 112 * mm]
    summary_rows: list[list[object]] = [[Paragraph(h, styles["tableHead"]) for h in summary_header]]
    for index, room in enumerate(room_order):
        gross, _, net = _room_totals(grouped.get(room, []))
        if has_discount:
            summary_rows.append([
                Paragraph(str(index + 1), styles["cellCenter"]), Paragraph(_ellipsize(room, 180), styles["cell"]),
                Paragraph(_money(gross), styles["cellCenter"]), Paragraph(_money(net), styles["cellCenter"]),
            ])
        else:
            summary_rows.append([
                Paragraph(str(index + 1), styles["cellCenter"]), Paragraph(_ellipsize(room, 180), styles["cell"]),
                Paragraph(_money(net), styles["cellCenter"]),
            ])
    if has_discount:
        summary_rows.extend([
            ["", Paragraph("<b>TOTAL</b>", styles["cellCenter"]), Paragraph(f"<b>{_money(quotation.get('subtotal', 0))}</b>", styles["cellCenter"]), Paragraph(f"<b>{_money(quotation.get('grand_total', 0))}</b>", styles["cellCenter"])],
            ["", Paragraph("<b>SPECIAL OFFER TOTAL</b>", styles["cellCenter"]), "", Paragraph(f"<b>{_money(quotation.get('grand_total', 0))}</b>", styles["cellCenter"])],
        ])
    else:
        summary_rows.extend([
            ["", Paragraph("<b>TOTAL</b>", styles["cellCenter"]), Paragraph(f"<b>{_money(quotation.get('subtotal', 0))}</b>", styles["cellCenter"])],
            ["", Paragraph("<b>GRAND TOTAL</b>", styles["cellCenter"]), Paragraph(f"<b>{_money(quotation.get('grand_total', 0))}</b>", styles["cellCenter"])],
        ])
    summary_row_heights = [SUMMARY_HEADER_ROW_MM * mm] + [SUMMARY_ROW_MM * mm] * n_rooms + [SUMMARY_TOTAL_ROW_MM * mm] * 2
    summary_style_cmds = [
        ("GRID", (0, 0), (-1, -1), 0.35, GRID), ("BACKGROUND", (0, 0), (-1, 0), HEADER_GREY),
        ("BACKGROUND", (0, -2), (-1, -1), HEADER_GREY), ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in range(2, n_rooms + 1, 2):  # zebra every 2nd room row (1-indexed data rows)
        summary_style_cmds.append(("BACKGROUND", (0, r), (-1, r), ZEBRA))
    summary = Table(summary_rows, colWidths=summary_col_widths, rowHeights=summary_row_heights, repeatRows=1)
    summary.setStyle(TableStyle(summary_style_cmds))
    story.extend([summary, Spacer(1, 2 * mm), Paragraph("OUR BRAND PARTNERS", styles["section"]), Spacer(1, 0.8 * mm)])
    story.extend([brand_partners_table(styles["cell"]), Spacer(1, 1.2 * mm)])

    terms = [
        "1. All rates are as per current MRP.",
        "2. Brands may revise MRP without prior notice.",
        "3. 100% advance payment is required to confirm the order.",
        "4. All MRP mentioned is inclusive of applicable tax.",
        "5. This quotation is valid for the current month or until the company MRP changes — whichever is earlier — subject to force majeure w.r.t. tax or MRP.",
        "6. For items with escalated MRP, order confirmation requires 100% payment prior to the cut-off timeline.",
        "7. Delivery as per company schedule. Freight extra, as per actuals.",
        "8. Any damage in transit must be reported within 24 hours of delivery with photographic proof.",
        "9. Cancellations after order confirmation may be subject to a restocking charge.",
        "10. GST and other applicable taxes will be charged extra as per government norms.",
    ]
    if b.get("terms_text"):
        terms.append(f"Additional terms: {_escape(b['terms_text'])}")
    # Use the full landscape width for contractual copy. The earlier narrow
    # left panel forced terms into cramped lines while the adjacent customer
    # care panel left a conspicuous amount of unused space.
    terms_rows = []
    for index in range(0, len(terms), 2):
        terms_rows.append([
            Paragraph(terms[index], styles["terms"]),
            Paragraph(terms[index + 1], styles["terms"]) if index + 1 < len(terms) else "",
        ])
    terms_table = Table(terms_rows, colWidths=[133.5 * mm, 133.5 * mm])
    terms_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        # Keep the contractual block together on page one even when an
        # address/reference adds metadata rows. The previous 12 mm of table
        # padding forced only the signature into an otherwise blank page two.
        ("TOPPADDING", (0, 0), (-1, -1), 0.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.4),
    ]))
    care_entries = [
        ("GEBERIT", "1800 102 4323"), ("GROHE", "1800 102 4475"), ("HANSGROHE", "1800 209 3246"), ("VITRA", "70451 32132"), ("OYSTER", "1800 120 8999"),
    ]
    care_rows = [
        [Paragraph(brand, styles["tableHead"]) for brand, _ in care_entries],
        [Paragraph(number, styles["cellCenter"]) for _, number in care_entries],
    ]
    care = Table(care_rows, colWidths=[53.4 * mm] * len(care_entries), rowHeights=[5 * mm, 5.5 * mm])
    care.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, GRID), ("BACKGROUND", (0, 0), (-1, 0), HEADER_GREY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    signature = Table([[Paragraph("I/We have reviewed and agree to the terms and conditions mentioned in this quotation.", styles["small"]), Paragraph("CUSTOMER SIGNATURE &amp; DATE", styles["signature"])]], colWidths=[160 * mm, 107 * mm], rowHeights=[8 * mm])
    signature.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.45, GRID), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
    story.extend([
        Paragraph("TERMS &amp; CONDITIONS", styles["section"]), Spacer(1, 0.8 * mm), terms_table,
        Spacer(1, 1.4 * mm), Paragraph("CUSTOMER CARE — TOLL FREE NUMBERS", styles["section"]),
        Spacer(1, 0.8 * mm), care, Spacer(1, 1.5 * mm), signature,
    ])
    if b.get("signature_name"):
        sig_line = _escape(b["signature_name"]) + (f", {_escape(b['signature_title'])}" if b.get("signature_title") else "")
        story.append(Paragraph(f"For {_escape(b.get('footer_company_name') or 'Buildcon House')} — {sig_line}", ParagraphStyle("sigLine", parent=styles["small"], alignment=2, spaceBefore=2)))

    # --- PAGES 2+: dynamic item rows per area page -----------------------------
    # Every room renders only its real item rows, paginated at
    # `_max_item_rows_per_page()` capacity (derived from real print geometry,
    # not a hardcoded count) — no blank filler rows, ever. Continuation pages
    # of the same room repeat the brand/area header + column headers and
    # continue the SR NO sequence rather than restarting at 1.
    if has_discount:
        item_header = [
            Paragraph("SR.<br/>NO.", styles["tableHead"]), Paragraph("PRODUCT IMAGE", styles["tableHead"]),
            Paragraph("ARTICLE<br/>NO.", styles["tableHead"]), Paragraph("DESCRIPTION", styles["tableHead"]),
            Paragraph("MRP<br/>(Rs.)", styles["tableHead"]), Paragraph("QTY", styles["tableHead"]),
            Paragraph("MRP<br/>TOTAL (Rs.)", styles["tableHead"]),
            Paragraph("OFFER<br/>RATE", styles["tableHead"]), Paragraph("OFFER<br/>TOTAL (Rs.)", styles["tableHead"]),
        ]
        item_widths = [12 * mm, 20 * mm, 36 * mm, 88 * mm, 24 * mm, 12 * mm, 25 * mm, 25 * mm, 25 * mm]
    else:
        item_header = [
            Paragraph("SR.<br/>NO.", styles["tableHead"]), Paragraph("PRODUCT IMAGE", styles["tableHead"]),
            Paragraph("ARTICLE<br/>NO.", styles["tableHead"]), Paragraph("DESCRIPTION", styles["tableHead"]),
            Paragraph("RATE<br/>(Rs.)", styles["tableHead"]), Paragraph("QTY", styles["tableHead"]),
            Paragraph("TOTAL<br/>(Rs.)", styles["tableHead"]),
        ]
        item_widths = [12 * mm, 20 * mm, 38 * mm, 117 * mm, 28 * mm, 12 * mm, 40 * mm]
    max_rows = _max_item_rows_per_page()
    for area_index, room in enumerate(room_order, 1):
        room_items = grouped.get(room, [])
        blocks = [room_items[i:i + max_rows] for i in range(0, len(room_items), max_rows)] or [[]]
        sr_offset = 0
        for block_index, block in enumerate(blocks):
            story.append(PageBreak())
            # The large area title has a fixed vertical band above a 17-row
            # table; one line is required to retain that capacity.
            area_label = f"AREA {area_index}: <u>{_ellipsize(room, 24)}</u>"
            if block_index:
                area_label += " <font size='9'>(continued)</font>"
            story.append(_brand_header(area_label, styles, style_key="areaTitle"))
            story.extend([Spacer(1, 4 * mm), HRFlowable(width="100%", thickness=1.25, color=BLUE), Spacer(1, 3 * mm)])
            n_data_rows = len(block)
            item_row_mm = _item_row_height_mm(n_data_rows)
            # Table padding consumes 3 mm on each side of the image column.
            image_width_mm = item_widths[1] / mm - 6
            image_height_mm = max(2.0, item_row_mm - 1.0)
            rows: list[list[object]] = [item_header]
            for offset_in_block, item in enumerate(block):
                sr_no = sr_offset + offset_in_block + 1
                qty = float(item.get("qty") or 0)
                base_rate = float(item.get("unit_price") or 0)
                pct = float(item.get("discount_pct") or 0)
                offer_rate = base_rate * (1 - pct / 100)   # discounted per-unit rate
                line_total = qty * offer_rate
                listed_mrp = float(item.get("mrp") or base_rate)
                description = _ellipsize(item.get("description") or item.get("name"), 40)
                finish = item.get("finish") or item.get("colour") or ""
                if finish:
                    description += f"<br/><font color='#737373'>Finish: {_ellipsize(finish, 12)}</font>"
                if has_discount:
                    rows.append([
                        Paragraph(str(sr_no), styles["cellCenter"]), _img(
                            item.get("image"),
                            width_mm=image_width_mm, height_mm=image_height_mm,
                        ),
                        Paragraph(_ellipsize(item.get("sku"), 20), styles["itemCenter"]), Paragraph(description, styles["itemText"]),
                        Paragraph(_money(listed_mrp), styles["itemCenter"]), Paragraph(f"{qty:g}", styles["itemCenter"]),
                        Paragraph(_money(qty * listed_mrp), styles["itemCenter"]),
                        Paragraph(_money(offer_rate), styles["itemCenter"]), Paragraph(_money(line_total), styles["itemCenter"]),
                    ])
                else:
                    rows.append([
                        Paragraph(str(sr_no), styles["cellCenter"]), _img(
                            item.get("image"), width_mm=image_width_mm, height_mm=image_height_mm,
                        ),
                        Paragraph(_ellipsize(item.get("sku"), 20), styles["itemCenter"]), Paragraph(description, styles["itemText"]),
                        Paragraph(_money(base_rate), styles["itemCenter"]), Paragraph(f"{qty:g}", styles["itemCenter"]),
                        Paragraph(_money(qty * base_rate), styles["itemCenter"]),
                    ])
            block_net = sum(
                float(item.get("qty") or 0) * float(item.get("unit_price") or 0) * (1 - float(item.get("discount_pct") or 0) / 100)
                for item in block
            )
            total_label_col = 3  # DESCRIPTION column — same position in both layouts
            last_col = len(item_header) - 1
            total_row: list[object] = ["" for _ in item_header]
            total_row[total_label_col] = Paragraph("<b>TOTAL</b>", styles["cellCenter"])
            total_row[last_col] = Paragraph(f"<b>{_money(block_net)}</b>", styles["cellCenter"])
            rows.append(total_row)
            # A detail page has no reserved/filler product rows. Expand the
            # real rows into the available print area so 8, 10, or 17 items
            # use the full page while the eighteenth starts a continuation.
            row_heights = [ITEM_HEADER_ROW_MM * mm] + [item_row_mm * mm] * n_data_rows + [ITEM_TOTAL_ROW_MM * mm]
            numeric_col_start = 4  # MRP/RATE column onward — center-aligned per the print spec
            item_style_cmds = [
                ("GRID", (0, 0), (-1, -1), 0.3, GRID), ("BACKGROUND", (0, 0), (-1, 0), HEADER_GREY),
                ("BACKGROUND", (0, -1), (-1, -1), HEADER_GREY), ("ALIGN", (0, 1), (0, -1), "CENTER"),
                ("ALIGN", (numeric_col_start, 1), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 1), (-1, -2), 0.5 * mm), ("BOTTOMPADDING", (0, 1), (-1, -2), 0.5 * mm),
                ("TOPPADDING", (0, 0), (-1, 0), 2), ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                ("TOPPADDING", (0, -1), (-1, -1), 2), ("BOTTOMPADDING", (0, -1), (-1, -1), 2),
            ]
            for r in range(2, n_data_rows + 1, 2):  # zebra every 2nd item row
                item_style_cmds.append(("BACKGROUND", (0, r), (-1, r), ZEBRA))
            table = Table(rows, colWidths=item_widths, rowHeights=row_heights, repeatRows=1)
            table.setStyle(TableStyle(item_style_cmds))
            story.append(table)
            sr_offset += n_data_rows

    doc.build(
        story,
        onFirstPage=functools.partial(_draw_quotation_page_chrome, branding=b),
        onLaterPages=functools.partial(_draw_quotation_page_chrome, branding=b),
    )
    rendered = buf.getvalue()
    logger.info(
        "quotation_pdf_complete duration_ms=%.1f bytes=%d image_loader=%s",
        (monotonic() - started_at) * 1000,
        len(rendered),
        image_loader_metrics(),
    )
    return rendered
