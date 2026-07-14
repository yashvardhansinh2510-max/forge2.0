"""Official BuildCon House quotation PDF — faithful A4 print template."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import functools
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Iterable

import httpx
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    Flowable, HRFlowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

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

# --- Dynamic pagination geometry (item/product table, pages 2+) -----------
# Page size + margins are unchanged (preserving the exact print template),
# but rows now render only for real content — no fixed 16-row block padded
# with blank filler rows. `_max_item_rows_per_page` derives the true capacity
# from real geometry so it automatically adapts if row height/typography
# ever changes, instead of a hardcoded magic number.
PAGE_H_MM = 297.0  # A4 portrait
TOP_MARGIN_MM = 13.0
BOTTOM_MARGIN_MM = 22.0
AREA_HEADER_BLOCK_MM = 21.0     # brand/area title block + rule + spacers above the table
ITEM_HEADER_ROW_MM = 10.0
ITEM_ROW_MM = 16.0
ITEM_TOTAL_ROW_MM = 8.0
SUMMARY_HEADER_ROW_MM = 7.0
SUMMARY_ROW_MM = 5.6
SUMMARY_TOTAL_ROW_MM = 6.2


def _max_item_rows_per_page() -> int:
    available = PAGE_H_MM - TOP_MARGIN_MM - BOTTOM_MARGIN_MM - AREA_HEADER_BLOCK_MM - ITEM_HEADER_ROW_MM - ITEM_TOTAL_ROW_MM
    return max(1, int(available // ITEM_ROW_MM))


def _money(value: float) -> str:
    return f"{float(value or 0):,.2f}"


def _escape(value: object) -> str:
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@lru_cache(maxsize=256)
def _remote_image_bytes(url: str) -> bytes | None:
    try:
        response = httpx.get(url, timeout=6.0, follow_redirects=True)
        response.raise_for_status()
        return response.content if response.content else None
    except Exception:
        return None


def _img(url: str | None, width_mm: float = 13, height_mm: float = 13) -> Flowable:
    """Render the supplied product image inside the official narrow image cell.

    Sized to the largest dimension that still fits inside the item row without
    ever stretching/distorting (kind="proportional" preserves aspect ratio;
    the row height itself is sized to comfortably fit this image — see
    ITEM_ROW_MM below)."""
    if url and str(url).startswith(("https://", "http://")):
        data = _remote_image_bytes(str(url))
        if data:
            try:
                image = Image(BytesIO(data), width=width_mm * mm, height=height_mm * mm, kind="proportional")
                image.hAlign = "CENTER"
                return image
            except Exception:
                pass
    return Paragraph("<i><font color='#999999' size='7'>[image]</font></i>", ParagraphStyle("image-placeholder", alignment=1, leading=8))


def _draw_footer(cv, doc, branding: dict | None = None) -> None:
    b = branding or {}
    cv.saveState()
    page_width, _ = A4
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


def _draw_room_watermark(cv, doc, branding: dict | None = None) -> None:
    _draw_footer(cv, doc, branding)
    b = branding or {}
    if not b.get("show_watermark", True):
        return
    if not LOGO_PATH.exists():
        return
    cv.saveState()
    if hasattr(cv, "setFillAlpha"):
        cv.setFillAlpha(0.10)
    cv.translate(A4[0] / 2, A4[1] / 2 - 8 * mm)
    cv.rotate(26)
    watermark_w = 87 * mm
    watermark_h = watermark_w / (1913 / 474)
    cv.drawImage(str(LOGO_PATH), -watermark_w / 2, -watermark_h / 2, width=watermark_w, height=watermark_h, mask="auto")
    cv.restoreState()


def _brand_header(right_title: str, styles: dict, style_key: str = "titleRight") -> Table:
    logo: Flowable
    if LOGO_PATH.exists():
        logo_width = 43 * mm
        logo = Image(str(LOGO_PATH), width=logo_width, height=logo_width / (1913 / 474), kind="proportional")
    else:
        logo = Paragraph("<b>BUILDCON HOUSE</b><br/><font size='8'>Let You Live Better</font>", styles["brandFallback"])
    table = Table([[logo, Paragraph(right_title, styles[style_key])]], colWidths=[105 * mm, 65 * mm])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return table


def _room_totals(items: Iterable[dict]) -> tuple[float, float, float]:
    subtotal = discount = 0.0
    for item in items:
        gross = float(item.get("qty") or 0) * float(item.get("unit_price") or 0)
        disc = gross * float(item.get("discount_pct") or 0) / 100
        subtotal += gross
        discount += disc
    return subtotal, discount, subtotal - discount


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
    b = branding or {}
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
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
        "tiny": ParagraphStyle("tiny", parent=base["Normal"], fontName="Helvetica", fontSize=7.2, leading=8.8, textColor=INK),
        "section": ParagraphStyle("section", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=INK),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontName="Helvetica", fontSize=7.4, leading=9, textColor=INK),
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
    created = (quotation.get("created_at") or datetime.now().isoformat())[:10]
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
    story.extend([Spacer(1, 4 * mm), HRFlowable(width="100%", thickness=1.25, color=BLUE), Spacer(1, 3.5 * mm)])
    meta = [
        [Paragraph("CUSTOMER NAME", styles["label"]), Paragraph("CONTACT NO.", styles["label"]), Paragraph("QUOTATION DATE", styles["label"])],
        [Paragraph(_escape(customer.get("company") or customer.get("name") or quotation.get("customer_name")), styles["body"]), Paragraph(_escape(quotation.get("phone_snapshot") or customer.get("phone") or ""), styles["body"]), Paragraph(created, styles["body"])],
        [Paragraph("QUOTATION NO.", styles["label"]), Paragraph("REFERENCE", styles["label"]), Paragraph("PROJECT", styles["label"])],
        [Paragraph(_escape(quotation.get("number")), styles["body"]), Paragraph(_escape(quotation.get("reference_source") or ""), styles["body"]), Paragraph(_escape(quotation.get("project_name") or ""), styles["body"])],
    ]
    meta_table = Table(meta, colWidths=[60 * mm, 60 * mm, 50 * mm], rowHeights=[7 * mm, 7 * mm, 7 * mm, 7 * mm])
    meta_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 1), (-1, 1), 0.4, LINE),
        ("LINEBELOW", (0, 3), (-1, 3), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.extend([meta_table, Spacer(1, 3 * mm)])
    story.append(Paragraph("Dear Sir/Madam, thank you for your interest in our products. We are pleased to offer our most competitive rates for premium bath and sanitaryware fittings, prepared as per your requirements.", styles["body"]))
    story.extend([Spacer(1, 3 * mm), Paragraph("QUOTATION SUMMARY", styles["section"]), Spacer(1, 1.5 * mm)])

    # ---- Dynamic Quotation Summary: exactly one row per room, no filler ----
    n_rooms = len(room_order)
    if has_discount:
        summary_header = ["SL. NO.", "BATHROOM / AREA", "MRP (Rs.)", "OFFER TOTAL (Rs.)"]
        summary_col_widths = [17 * mm, 75 * mm, 39 * mm, 39 * mm]
    else:
        summary_header = ["SL. NO.", "BATHROOM / AREA", "TOTAL (Rs.)"]
        summary_col_widths = [17 * mm, 88 * mm, 65 * mm]
    summary_rows: list[list[object]] = [[Paragraph(h, styles["tableHead"]) for h in summary_header]]
    for index, room in enumerate(room_order):
        gross, _, net = _room_totals(grouped.get(room, []))
        if has_discount:
            summary_rows.append([
                Paragraph(str(index + 1), styles["cellCenter"]), Paragraph(_escape(room), styles["cell"]),
                Paragraph(_money(gross), styles["cellCenter"]), Paragraph(_money(net), styles["cellCenter"]),
            ])
        else:
            summary_rows.append([
                Paragraph(str(index + 1), styles["cellCenter"]), Paragraph(_escape(room), styles["cell"]),
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
    story.extend([summary, Spacer(1, 3 * mm), Paragraph("OUR BRAND PARTNERS", styles["section"]), Spacer(1, 1 * mm)])

    partners = [
        [("GROHE", "Pure Freude an Wasser"), ("hansgrohe", "Life is Waterful"), ("AXOR", "Form Follows Perfection"), ("VitrA", "Design Meets Life"), ("NEXION", "The Surface Experience"), ("QUTONE", "Let's Build Together")],
        [("DIMORE", "Reflection of Your Style"), ("Oyster", "Indulge in Luxury"), ("GEBERIT", "Engineered for Hygiene"), ("MCM ITTIMI", "Innovation into Inspiration"), ("VERANTES LIVING", "Kitchens &amp; Wardrobes"), ("IMPORTED<br/>FURNITURE", "Crafted Beyond Borders")],
    ]
    partner_rows = [[Paragraph(f"<b>{name}</b><br/><font size='5.4'><i>{tagline}</i></font>", ParagraphStyle("partner", parent=styles["cell"], fontSize=6.6, leading=8, alignment=1)) for name, tagline in row] for row in partners]
    partner_table = Table(partner_rows, colWidths=[28.3 * mm] * 6, rowHeights=[12 * mm, 12 * mm])
    partner_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.35, GRID), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
    story.extend([partner_table, Spacer(1, 2 * mm), Paragraph("TERMS &amp; CONDITIONS", styles["section"]), Spacer(1, 0.6 * mm)])

    terms = [
        "1. All rates are as per current MRP.",
        "2. Brands may revise MRP without prior notice.",
        "3. 100% advance payment is required to confirm the order.",
        "4. All MRP mentioned is inclusive of applicable tax.",
        "5. Quotation remains valid till the company MRP remains unchanged, subject to force majeure w.r.t. tax or MRP.",
        "6. For items with escalated MRP, order confirmation requires 100% payment prior to the cut-off timeline.",
        "7. Delivery as per company schedule. Freight extra, as per actuals.",
        "8. Rate valid for the current month only.",
        "9. Any damage in transit must be reported within 24 hours of delivery with photographic proof.",
        "10. Cancellations after order confirmation may be subject to a restocking charge.",
        "11. GST and other applicable taxes will be charged extra as per government norms.",
    ]
    story.extend([Paragraph(term, styles["small"]) for term in terms])
    if b.get("terms_text"):
        story.extend([Spacer(1, 1 * mm), Paragraph(f"<b>Additional terms:</b> {_escape(b['terms_text'])}", styles["small"])])
    story.extend([Spacer(1, 2 * mm), Paragraph("CUSTOMER CARE — TOLL FREE NUMBERS", styles["section"]), Spacer(1, 0.5 * mm)])
    care_rows = [[Paragraph("BRAND", styles["tableHead"]), Paragraph("TOLL FREE", styles["tableHead"])]] + [[brand, number] for brand, number in [
        ("GEBERIT", "1800 102 4323"), ("GROHE", "1800 102 4475"), ("HANSGROHE", "1800 209 3246"), ("VITRA", "70451 32132"), ("OYSTER", "1800 120 8999"),
    ]]
    care = Table(care_rows, colWidths=[48 * mm, 48 * mm], rowHeights=[5 * mm] * 6, hAlign="CENTER")
    care.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, GRID), ("BACKGROUND", (0, 0), (-1, 0), HEADER_GREY), ("FONTNAME", (0, 1), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 1), (-1, -1), 6.5), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 4)]))
    enquiry_phone = b.get("footer_phone") or "+91 99099 06652"
    enquiry_email = b.get("footer_email") or "buildconhouse10@gmail.com"
    story.extend([care, Spacer(1, 1.7 * mm), Paragraph(f"For general enquiries: <b>M: {enquiry_phone}</b>  |  <b>Email: {enquiry_email}</b>", styles["small"]), Spacer(1, 2 * mm)])
    signature = Table([[Paragraph("I/We have reviewed and agree to the terms and conditions mentioned in this quotation.", styles["small"]), Paragraph("CUSTOMER SIGNATURE &amp; DATE", styles["signature"])]], colWidths=[104 * mm, 66 * mm], rowHeights=[13 * mm])
    signature.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.45, GRID), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
    story.append(signature)
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
            Paragraph("OFFER<br/>RATE", styles["tableHead"]), Paragraph("OFFER<br/>TOTAL (Rs.)", styles["tableHead"]),
        ]
        item_widths = [12 * mm, 33 * mm, 18 * mm, 38 * mm, 18 * mm, 8 * mm, 20 * mm, 23 * mm]
    else:
        item_header = [
            Paragraph("SR.<br/>NO.", styles["tableHead"]), Paragraph("PRODUCT IMAGE", styles["tableHead"]),
            Paragraph("ARTICLE<br/>NO.", styles["tableHead"]), Paragraph("DESCRIPTION", styles["tableHead"]),
            Paragraph("RATE<br/>(Rs.)", styles["tableHead"]), Paragraph("QTY", styles["tableHead"]),
            Paragraph("TOTAL<br/>(Rs.)", styles["tableHead"]),
        ]
        item_widths = [12 * mm, 33 * mm, 20 * mm, 48 * mm, 20 * mm, 8 * mm, 29 * mm]
    max_rows = _max_item_rows_per_page()
    for area_index, room in enumerate(room_order, 1):
        room_items = grouped.get(room, [])
        blocks = [room_items[i:i + max_rows] for i in range(0, len(room_items), max_rows)] or [[]]
        sr_offset = 0
        for block_index, block in enumerate(blocks):
            story.append(PageBreak())
            area_label = f"AREA {area_index}: <u>{_escape(room)}</u>"
            if block_index:
                area_label += " <font size='9'>(continued)</font>"
            story.append(_brand_header(area_label, styles, style_key="areaTitle"))
            story.extend([Spacer(1, 4 * mm), HRFlowable(width="100%", thickness=1.25, color=BLUE), Spacer(1, 3 * mm)])
            rows: list[list[object]] = [item_header]
            for offset_in_block, item in enumerate(block):
                sr_no = sr_offset + offset_in_block + 1
                qty = float(item.get("qty") or 0)
                base_rate = float(item.get("unit_price") or 0)
                pct = float(item.get("discount_pct") or 0)
                offer_rate = base_rate * (1 - pct / 100)   # discounted per-unit rate
                line_total = qty * offer_rate
                listed_mrp = float(item.get("mrp") or base_rate)
                description = _escape(item.get("description") or item.get("name"))
                finish = item.get("finish") or item.get("colour") or ""
                if finish:
                    description += f"<br/><font color='#737373'>Finish: {_escape(finish)}</font>"
                if has_discount:
                    rows.append([
                        Paragraph(str(sr_no), styles["cellCenter"]), _img(item.get("image")),
                        Paragraph(_escape(item.get("sku")), styles["cell"]), Paragraph(description, styles["tiny"]),
                        Paragraph(_money(listed_mrp), styles["cellCenter"]), Paragraph(f"{qty:g}", styles["cellCenter"]),
                        Paragraph(_money(offer_rate), styles["cellCenter"]), Paragraph(_money(line_total), styles["cellCenter"]),
                    ])
                else:
                    rows.append([
                        Paragraph(str(sr_no), styles["cellCenter"]), _img(item.get("image")),
                        Paragraph(_escape(item.get("sku")), styles["cell"]), Paragraph(description, styles["tiny"]),
                        Paragraph(_money(base_rate), styles["cellCenter"]), Paragraph(f"{qty:g}", styles["cellCenter"]),
                        Paragraph(_money(qty * base_rate), styles["cellCenter"]),
                    ])
            block_net = sum(
                float(item.get("qty") or 0) * float(item.get("unit_price") or 0) * (1 - float(item.get("discount_pct") or 0) / 100)
                for item in block
            )
            n_data_rows = len(block)
            total_label_col = 3  # DESCRIPTION column — same position in both layouts
            last_col = len(item_header) - 1
            total_row: list[object] = ["" for _ in item_header]
            total_row[total_label_col] = Paragraph("<b>TOTAL</b>", styles["cellCenter"])
            total_row[last_col] = Paragraph(f"<b>{_money(block_net)}</b>", styles["cellCenter"])
            rows.append(total_row)
            row_heights = [ITEM_HEADER_ROW_MM * mm] + [ITEM_ROW_MM * mm] * n_data_rows + [ITEM_TOTAL_ROW_MM * mm]
            numeric_col_start = 4  # MRP/RATE column onward — center-aligned per the print spec
            item_style_cmds = [
                ("GRID", (0, 0), (-1, -1), 0.3, GRID), ("BACKGROUND", (0, 0), (-1, 0), HEADER_GREY),
                ("BACKGROUND", (0, -1), (-1, -1), HEADER_GREY), ("ALIGN", (0, 1), (0, -1), "CENTER"),
                ("ALIGN", (numeric_col_start, 1), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
            for r in range(2, n_data_rows + 1, 2):  # zebra every 2nd item row
                item_style_cmds.append(("BACKGROUND", (0, r), (-1, r), ZEBRA))
            table = Table(rows, colWidths=item_widths, rowHeights=row_heights, repeatRows=1)
            table.setStyle(TableStyle(item_style_cmds))
            story.append(table)
            sr_offset += n_data_rows

    doc.build(
        story,
        onFirstPage=functools.partial(_draw_footer, branding=b),
        onLaterPages=functools.partial(_draw_room_watermark, branding=b),
    )
    return buf.getvalue()
