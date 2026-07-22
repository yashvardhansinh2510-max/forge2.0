"""Ground Floor → Tiles document PDFs — faithful replicas of the two official
printed formats:

* Tiles SELECTION  — the grey selection sheet (logo centered, customer header
  with underlined fields, grey product grid, Terms & Conditions, contact strip).
* Tiles QUOTATION  — the light-blue bordered quotation sheet (logo + big
  "Quotation" title, serif-italic column headers, white product grid, right-
  aligned totals stack, centred terms, blue address footer).

Both templates paginate automatically once product rows exceed a page,
repeating their headers on continuation pages. Both reuse the shared image
fetch/placeholder + escaping helpers from pdf_generator so there is exactly
one implementation of those in the codebase.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable, HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from pdf_generator import LOGO_PATH, LOGO_RATIO, _escape, _img, _money

INK = colors.HexColor("#111111")
RED = colors.HexColor("#FF0000")
BLUE_TEXT = colors.HexColor("#2E75B6")
GRID_BLACK = colors.HexColor("#000000")
HEADER_GREY = colors.HexColor("#D3D3D3")
CELL_GREY = colors.HexColor("#BFBFBF")
SHEET_BLUE = colors.HexColor("#CBE7F5")

# ---------------------------------------------------------------------------
# Optional unicode fonts — needed only for the ₹ / ☺ / ☎ glyphs the reference
# documents use. Helvetica/Times (the PDF core fonts) don't carry them, and no
# single macOS font has all three (Arial Unicode MS predates the 2010 rupee
# sign), so each glyph registers the first candidate whose cmap actually maps
# it. When none exists (bare containers) the templates degrade gracefully to
# "Rs." / no dingbat.
# ---------------------------------------------------------------------------
def _register_glyph_font(name: str, codepoint: int, candidates: tuple[str, ...]) -> str | None:
    from reportlab.pdfbase.ttfonts import TTFontFile
    for candidate in candidates:
        if not Path(candidate).exists():
            continue
        try:
            if TTFontFile(candidate).charToGlyph.get(codepoint, 0) == 0:
                continue
            pdfmetrics.registerFont(TTFont(name, candidate))
            return name
        except Exception:
            continue
    return None


_DEJAVU = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",            # Debian/Ubuntu
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",                     # Fedora/Alpine
)
_RUPEE_FONT = _register_glyph_font("BCRupee", 0x20B9, _DEJAVU + ("/System/Library/Fonts/Supplemental/Georgia.ttf",))
_DINGS_FONT = _register_glyph_font("BCDings", 0x263A, _DEJAVU + ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf",))


def _ding(char: str) -> str:
    """☺ / ☎ in the dingbat-capable font — empty string when unavailable."""
    return f"<font name='{_DINGS_FONT}'>{char}</font>" if _DINGS_FONT else ""


def _rupee(value: float) -> str:
    symbol = f"<font name='{_RUPEE_FONT}'>₹</font> " if _RUPEE_FONT else "Rs. "
    return f"{symbol}{_money(value)}"


DEFAULT_ADDRESS = "Nr. Gujarat Housing Board, Kataria Motors, 2nd 150 Ring Road, Rajkot-360005"
DEFAULT_EMAIL = "buildconhouse@gmail.com"
DEFAULT_MOBILE = "+91 99099 06652"


def _parse_doc_date(doc: dict) -> datetime:
    """Best-effort parse of the editable printed date; falls back to created_at,
    then to today — used for the `<Customer> <DD-MM-YYYY>.pdf` filename."""
    raw = (doc.get("doc_date") or "").strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%b-%y", "%d-%b-%Y", "%d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    created = (doc.get("created_at") or "").replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(created)
    except ValueError:
        return datetime.now()


def tiles_pdf_filename(doc: dict) -> str:
    """`<Customer Name> <DD-MM-YYYY>.pdf` — e.g. "Nileshbhai Pokiya 08-07-2026.pdf"."""
    name = " ".join((doc.get("customer_name") or "Customer").split())
    stamp = _parse_doc_date(doc).strftime("%d-%m-%Y")
    safe = "".join(ch for ch in f"{name} {stamp}" if ch not in '\\/:*?"<>|')
    return f"{safe}.pdf"


def _logo_flowable(width_mm: float) -> Flowable:
    if LOGO_PATH.exists():
        image = Image(str(LOGO_PATH), width=width_mm * mm, height=width_mm * mm / LOGO_RATIO, kind="proportional")
        image.hAlign = "CENTER"
        return image
    return Paragraph(
        "<b>BUILDCON HOUSE</b><br/><font size='7'>Let you live better</font>",
        ParagraphStyle("logoFallback", fontName="Helvetica-Bold", fontSize=13, leading=15, alignment=1),
    )


def _fmt_rate_sqft(value, suffix: str = "") -> str:
    """300.0 → "300", 132.5 → "132.5" — the reference sheets never print
    trailing zeros on the per-sqft rate."""
    if value in (None, ""):
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return _escape(value)
    text = f"{num:g}"
    return f"{text}{suffix}"


# ===========================================================================
# TILES SELECTION — grey sheet
# ===========================================================================
def build_tiles_selection_pdf(quotation: dict, customer: dict, branding: dict | None = None) -> bytes:
    b = branding or {}
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=8 * mm, rightMargin=8 * mm,
        topMargin=9 * mm, bottomMargin=10 * mm,
        title=f"Selection — {quotation.get('customer_name') or ''}",
        author=b.get("footer_company_name") or "Buildcon House",
    )
    base = getSampleStyleSheet()
    address_line = b.get("company_address") or DEFAULT_ADDRESS
    styles = {
        "address": ParagraphStyle("address", parent=base["Normal"], fontName="Helvetica", fontSize=8.6, leading=10.5, textColor=colors.HexColor("#3B3B3B"), alignment=1),
        "label": ParagraphStyle("label", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9.4, leading=12, textColor=INK),
        "value": ParagraphStyle("value", parent=base["Normal"], fontName="Helvetica", fontSize=9.2, leading=12, textColor=INK),
        "valueCenter": ParagraphStyle("valueCenter", parent=base["Normal"], fontName="Helvetica", fontSize=9.2, leading=12, textColor=INK, alignment=1),
        "tableHead": ParagraphStyle("tableHead", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9.2, leading=11, textColor=INK, alignment=1),
        "tableHeadRed": ParagraphStyle("tableHeadRed", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9.2, leading=11, textColor=RED, alignment=1),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontName="Helvetica", fontSize=8.6, leading=10.5, textColor=INK, alignment=1),
        "cellRed": ParagraphStyle("cellRed", parent=base["Normal"], fontName="Helvetica", fontSize=8.6, leading=10.5, textColor=RED, alignment=1),
        "termsTitle": ParagraphStyle("termsTitle", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=11.5, leading=14, textColor=colors.HexColor("#2B2B2B")),
        "term": ParagraphStyle("term", parent=base["Normal"], fontName="Helvetica", fontSize=8.2, leading=13, textColor=colors.HexColor("#4A4A4A"), leftIndent=6 * mm),
        "contact": ParagraphStyle("contact", parent=base["Normal"], fontName="Helvetica", fontSize=8.4, leading=10, textColor=INK, alignment=1),
    }

    story: list[Flowable] = []
    # --- Brand block: centered logo + address + double rule -----------------
    story.append(_logo_flowable(74))
    story.extend([Spacer(1, 2 * mm), Paragraph(_escape(address_line), styles["address"]), Spacer(1, 2 * mm)])
    story.append(HRFlowable(width="100%", thickness=1.6, color=INK, spaceAfter=1.1 * mm))
    story.append(HRFlowable(width="100%", thickness=0.9, color=INK, spaceAfter=4 * mm))

    # --- Customer header: left NAME/MOB/REF, right SELECTION DT/ATTENDED/PREPARED
    created = _parse_doc_date(quotation).strftime("%d-%b-%y")
    phone_label = f"{_ding('☎')} :" if _DINGS_FONT else "MOB :"
    left_rows = [
        [Paragraph("NAME:", styles["label"]), Paragraph(_escape(quotation.get("customer_name") or customer.get("name")), styles["value"])],
        [Paragraph(phone_label, styles["label"]), Paragraph(_escape(quotation.get("phone_snapshot") or customer.get("phone") or ""), styles["value"])],
        [Paragraph("REF:", styles["label"]), Paragraph(_escape(quotation.get("reference_source") or ""), styles["value"])],
    ]
    left = Table(left_rows, colWidths=[15 * mm, 99 * mm], rowHeights=[7 * mm] * 3)
    left.setStyle(TableStyle([
        ("LINEBELOW", (1, 0), (1, -1), 0.7, INK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
    ]))
    right_rows = [
        [Paragraph("SELECTION DT:", styles["label"]), Paragraph(_escape(quotation.get("doc_date") or created), styles["valueCenter"])],
        [Paragraph("ATTENDED BY:", styles["label"]), Paragraph(_escape(quotation.get("attended_by") or ""), styles["valueCenter"])],
        [Paragraph("PREPARED BY:", styles["label"]), Paragraph(_escape(quotation.get("prepared_by") or ""), styles["valueCenter"])],
    ]
    right = Table(right_rows, colWidths=[30 * mm, 44 * mm], rowHeights=[7 * mm] * 3)
    right.setStyle(TableStyle([
        ("LINEBELOW", (1, 0), (1, -1), 0.7, INK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 0.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
    ]))
    header = Table([[left, "", right]], colWidths=[114 * mm, 6 * mm, 74 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.extend([header, Spacer(1, 7 * mm)])

    # --- Product grid -------------------------------------------------------
    head = [
        Paragraph("NO.", styles["tableHead"]), Paragraph("AREA", styles["tableHead"]),
        Paragraph("PRODUCT DETAIL", styles["tableHead"]), Paragraph("IMAGE", styles["tableHead"]),
        Paragraph("SIZE", styles["tableHead"]), Paragraph("RATE/SQ.FT", styles["tableHeadRed"]),
    ]
    rows: list[list[object]] = [head]
    for index, item in enumerate(quotation.get("items") or [], 1):
        rows.append([
            Paragraph(str(index), styles["cell"]),
            Paragraph(_escape(item.get("room") or ""), styles["cell"]),
            Paragraph(_escape(item.get("name") or ""), styles["cell"]),
            _img(item.get("image"), width_mm=41, height_mm=24),
            Paragraph(_escape(item.get("size") or ""), styles["cell"]),
            Paragraph(_fmt_rate_sqft(item.get("rate_sqft"), " PER SQFT"), styles["cellRed"]),
        ])
    n_rows = len(rows) - 1
    table = Table(
        rows,
        colWidths=[13 * mm, 37 * mm, 52 * mm, 44 * mm, 23 * mm, 25 * mm],
        rowHeights=[8.5 * mm] + [27 * mm] * n_rows,
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.9, GRID_BLACK),
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_GREY),
        ("BACKGROUND", (0, 1), (2, -1), CELL_GREY),
        ("BACKGROUND", (4, 1), (-1, -1), CELL_GREY),
        ("BACKGROUND", (3, 1), (3, -1), CELL_GREY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))
    story.extend([table, Spacer(1, 4 * mm)])

    # --- Terms & Conditions -------------------------------------------------
    terms = [
        "1. <b>Prices</b> quoted are based on the current <b>NET Prices</b> at the time of selection.",
        "2. <b>Prices revisions</b> by <b>any brands</b> may occur without prior notice.",
        "3. <b>100% advance payment</b> is required to confirm orders.",
        "4. <b>Freight &amp; Unloading charges</b> will be applicable as per actuals.",
        "5. <b>Delivery timelines</b> are subject to the <b>manufacturer's schedule</b>.",
        "6. <b>Rates are valid for 5 Days</b>, unless stated otherwise in writing.",
    ]
    story.append(Paragraph("Terms &amp; Conditions", styles["termsTitle"]))
    story.append(Spacer(1, 1.2 * mm))
    story.extend([Paragraph(term, styles["term"]) for term in terms])
    story.append(Spacer(1, 5 * mm))

    # --- Contact strip ------------------------------------------------------
    email = b.get("footer_email") or DEFAULT_EMAIL
    mobile = b.get("footer_phone") or DEFAULT_MOBILE
    story.append(HRFlowable(width="100%", thickness=0.9, color=INK, spaceAfter=0))
    contact = Table(
        [[
            Paragraph(f"<b>E-MAIL:</b> {_escape(email)}", styles["contact"]),
            "",
            Paragraph(f"<b>MOBILE:</b> {_escape(mobile)}", styles["contact"]),
        ]],
        colWidths=[92 * mm, 10 * mm, 92 * mm], rowHeights=[7 * mm],
    )
    contact.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), HEADER_GREY),
        ("BACKGROUND", (2, 0), (2, 0), HEADER_GREY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(contact)
    story.append(HRFlowable(width="100%", thickness=0.9, color=INK, spaceBefore=0))

    doc.build(story)
    return buf.getvalue()


# ===========================================================================
# TILES QUOTATION — light-blue bordered sheet
# ===========================================================================
# Column widths for the 10-column product grid (sums to the 180mm inner width
# of the bordered box). Shared by the header row and every product row so the
# per-row inner tables always line up into one continuous grid.
_Q_COLS = [12 * mm, 33 * mm, 26 * mm, 24 * mm, 15 * mm, 14.5 * mm, 14.5 * mm, 12.5 * mm, 12.5 * mm, 16 * mm]


def build_tiles_quotation_pdf(quotation: dict, customer: dict, branding: dict | None = None) -> bytes:
    b = branding or {}
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=10 * mm, rightMargin=10 * mm,
        topMargin=10 * mm, bottomMargin=12 * mm,
        title=f"Quotation — {quotation.get('customer_name') or ''}",
        author=b.get("footer_company_name") or "Buildcon House",
    )
    base = getSampleStyleSheet()
    styles = {
        "qTitle": ParagraphStyle("qTitle", parent=base["Normal"], fontName="Times-Bold", fontSize=21, leading=23, textColor=INK, alignment=2),
        "hLabel": ParagraphStyle("hLabel", parent=base["Normal"], fontName="Times-Bold", fontSize=8, leading=11.5, textColor=INK, alignment=2),
        "hValue": ParagraphStyle("hValue", parent=base["Normal"], fontName="Times-Bold", fontSize=8, leading=11.5, textColor=INK),
        "colHead": ParagraphStyle("colHead", parent=base["Normal"], fontName="Times-BoldItalic", fontSize=7.4, leading=8.6, textColor=INK, alignment=1),
        "colHeadRed": ParagraphStyle("colHeadRed", parent=base["Normal"], fontName="Times-BoldItalic", fontSize=7.4, leading=8.6, textColor=RED, alignment=1),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontName="Helvetica", fontSize=7.6, leading=9.4, textColor=INK, alignment=1),
        "cellBold": ParagraphStyle("cellBold", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.6, leading=9.4, textColor=INK, alignment=1),
        "cellRed": ParagraphStyle("cellRed", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.6, leading=9.4, textColor=RED, alignment=1),
        "sumLabel": ParagraphStyle("sumLabel", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.6, leading=9.4, textColor=INK, alignment=1),
        "sumRed": ParagraphStyle("sumRed", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.6, leading=9.4, textColor=RED, alignment=1),
        "noteRed": ParagraphStyle("noteRed", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.4, leading=10, textColor=RED, alignment=1),
        "noteHead": ParagraphStyle("noteHead", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.4, leading=10, textColor=INK, alignment=1),
        "term": ParagraphStyle("qTerm", parent=base["Normal"], fontName="Times-Roman", fontSize=6.6, leading=8.6, textColor=INK, alignment=1),
        "blue": ParagraphStyle("blue", parent=base["Normal"], fontName="Times-Bold", fontSize=6.8, leading=9, textColor=BLUE_TEXT, alignment=1),
    }

    smiley = _ding("☺")

    # --- Outer row 0: brand + title + customer block ------------------------
    brand_row = Table([["", _logo_flowable(50), Paragraph("Quotation", styles["qTitle"])]], colWidths=[45 * mm, 90 * mm, 45 * mm])
    brand_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    date_text = _escape(quotation.get("doc_date") or _parse_doc_date(quotation).strftime("%d-%m-%Y"))
    left_pairs = [
        ("NAME", quotation.get("customer_name") or customer.get("name") or ""),
        ("MO", quotation.get("phone_snapshot") or customer.get("phone") or ""),
        ("REF", quotation.get("reference_source") or ""),
        ("ATTENDED BY", quotation.get("attended_by") or ""),
        ("ADDRESS", quotation.get("address_snapshot") or ""),
    ]
    left_rows = [
        [Paragraph(f"{label}&nbsp;&nbsp;:", styles["hLabel"]), Paragraph(_escape(value), styles["hValue"])]
        for label, value in left_pairs
    ]
    left = Table(left_rows, colWidths=[26 * mm, 94 * mm])
    left.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    right_lines = [
        Paragraph(f"<b>QUOTATION NO:</b> {_escape(quotation.get('doc_number') or quotation.get('number') or '')}", styles["hValue"]),
        Paragraph(f"<b>DATE:</b> {date_text}", styles["hValue"]),
    ]
    if quotation.get("prepared_by"):
        right_lines.append(Paragraph(f"<b>PREPARED BY:</b> {_escape(quotation.get('prepared_by'))}", styles["hValue"]))
    right = Table([[line] for line in right_lines], colWidths=[60 * mm])
    right.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
    ]))
    customer_block = Table([[left, right]], colWidths=[120 * mm, 60 * mm])
    customer_block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    header_cell = [brand_row, Spacer(1, 2 * mm), customer_block, Spacer(1, 2.5 * mm)]

    # --- Column header row ---------------------------------------------------
    col_heads = Table([[
        Paragraph("SR.", styles["colHead"]), Paragraph("PRODUCT NAME", styles["colHead"]),
        Paragraph("PHOTO", styles["colHead"]), Paragraph("Area", styles["colHead"]),
        Paragraph("Size", styles["colHead"]), Paragraph("RATE PER<br/>SQFT", styles["colHeadRed"]),
        Paragraph("RATE PER<br/>BOX", styles["colHead"]), Paragraph("TOTAL BOX", styles["colHead"]),
        Paragraph("PCS|BOX", styles["colHead"]), Paragraph("TOTAL", styles["colHead"]),
    ]], colWidths=_Q_COLS, rowHeights=[8.5 * mm])
    col_heads.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.8, GRID_BLACK),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    # --- Product rows (one outer row each so the sheet can paginate) --------
    product_tables: list[Table] = []
    total_boxes = 0.0
    subtotal = 0.0
    for index, item in enumerate(quotation.get("items") or [], 1):
        qty = float(item.get("qty") or 0)
        rate_box = float(item.get("unit_price") or 0)
        line_total = qty * rate_box
        total_boxes += qty
        subtotal += line_total
        row = Table([[
            Paragraph(str(index), styles["cell"]),
            Paragraph(_escape(item.get("name") or ""), styles["cellBold"]),
            _img(item.get("image"), width_mm=24, height_mm=16),
            Paragraph(_escape(item.get("room") or ""), styles["cell"]),
            Paragraph(_escape(item.get("size") or ""), styles["cellBold"]),
            Paragraph(_fmt_rate_sqft(item.get("rate_sqft")), styles["cellRed"]),
            Paragraph(_money(rate_box) if rate_box else "", styles["cell"]),
            Paragraph(f"{qty:g}" if qty else "", styles["cellBold"]),
            Paragraph(_escape(item.get("pcs_per_box") or "BOX"), styles["cellBold"]),
            Paragraph(_money(line_total) if line_total else "", styles["cell"]),
        ]], colWidths=_Q_COLS, rowHeights=[20 * mm])
        row.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.8, GRID_BLACK),
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1),
            ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        product_tables.append(row)

    # --- Totals stack (right-aligned under the TOTAL columns) ---------------
    summary = Table(
        [
            [Paragraph(f"TOTAL BOX : {total_boxes:g}", styles["sumLabel"]), ""],
            [Paragraph("SUBTOTAL", styles["sumLabel"]), Paragraph(_rupee(subtotal), styles["sumLabel"])],
            [Paragraph("TRANSPORTATION", styles["sumLabel"]), Paragraph("EXTRA", styles["sumLabel"])],
            [Paragraph("TOTAL QUOTE", styles["sumRed"]), Paragraph(_rupee(subtotal), styles["sumRed"])],
        ],
        colWidths=[34 * mm, 25 * mm], rowHeights=[6 * mm] * 4,
    )
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.white),
        ("BACKGROUND", (1, 1), (1, -1), colors.white),
        ("BOX", (0, 0), (0, 0), 0.8, GRID_BLACK),
        ("GRID", (0, 1), (-1, -1), 0.8, GRID_BLACK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]))
    # Right-align by wrapping in a borderless full-width row — a nested
    # table's own hAlign is ignored inside an outer table cell.
    summary_row = Table([["", summary]], colWidths=[121 * mm, 59 * mm])
    summary_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    # --- Centered notes / terms / blue address footer -----------------------
    terms = [
        "•Above given rate are including GST @18%.",
        "•Freight &amp; unloading charges will be extra as applicable.",
        "•Payment - 100% Advance.",
        "•All orders / Deliveries are subject to material availability.",
        "•price tends to change in case of changes in govt. levy.",
        "•cheque should be written in favour of BUILDCON HOUSE.",
        "•After confirmation of P.O. material will be delivered within 15 days.",
        "•RATE VALID FOR 5 DAYS.",
    ]
    address_line = b.get("company_address") or "Before Gujarat housing, Nr.katariya motors, 2nd 150ft ring road, Rajkot-360005"
    email = b.get("footer_email") or DEFAULT_EMAIL
    mobile = b.get("footer_phone") or DEFAULT_MOBILE
    notes_cell: list[Flowable] = [
        Spacer(1, 3 * mm),
        Paragraph(f"{smiley}LABOUR COST EXTRA", styles["noteRed"]),
        Spacer(1, 1.5 * mm),
        Paragraph(f"{smiley}TERMS&amp;CONDITION&nbsp;&nbsp;:", styles["noteHead"]),
        Spacer(1, 1 * mm),
        *[Paragraph(term, styles["term"]) for term in terms],
        Spacer(1, 2.5 * mm),
        Paragraph(f"ADDRESS&nbsp;&nbsp;:- {_escape(address_line)}", styles["blue"]),
        Paragraph(f"Mail :{_escape(email)}", styles["blue"]),
        Paragraph(f"Mo:{_escape(mobile)}", styles["blue"]),
    ]

    # --- Assemble: one outer table = the bordered light-blue sheet ----------
    outer_rows: list[list[object]] = [[header_cell], [col_heads]]
    outer_rows.extend([[row] for row in product_tables])
    outer_rows.append([[Spacer(1, 1.5 * mm), summary_row]])
    outer_rows.append([notes_cell])
    outer = Table(outer_rows, colWidths=[190 * mm], repeatRows=2)
    outer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SHEET_BLUE),
        ("BOX", (0, 0), (-1, -1), 1.1, GRID_BLACK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm),
        ("TOPPADDING", (0, 0), (0, 0), 4 * mm),
        ("TOPPADDING", (0, 1), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -2), 0),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 4 * mm),
    ]))

    doc.build([outer])
    return buf.getvalue()
