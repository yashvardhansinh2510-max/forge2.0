"""Official BuildCon House quotation PDF — faithful A4 print template."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from io import BytesIO
from typing import Iterable

import httpx
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    Flowable, HRFlowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

BLUE = colors.HexColor("#165D9C")
INK = colors.HexColor("#1C1C1C")
GREY = colors.HexColor("#737373")
LINE = colors.HexColor("#CFCFCF")
LIGHT = colors.HexColor("#F5F5F5")


def _money(value: float) -> str:
    return f"{float(value or 0):,.2f}"


def _escape(value: object) -> str:
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _img(url: str | None, width_mm: float = 22, height_mm: float = 22) -> Flowable:
    """Render a product image when accessible; otherwise retain a neutral cell."""
    if url and str(url).startswith(("https://", "http://")):
        try:
            data = httpx.get(str(url), timeout=5.0).content
            image = Image(BytesIO(data), width=width_mm * mm, height=height_mm * mm, kind="proportional")
            image.hAlign = "CENTER"
            return image
        except Exception:
            pass
    return Paragraph("<font color='#999999' size='7'>[image]</font>", ParagraphStyle("image-placeholder", alignment=1, leading=8))


def _footer(canvas, doc) -> None:
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.35)
    canvas.line(doc.leftMargin, 15 * mm, width - doc.rightMargin, 15 * mm)
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(doc.leftMargin, 10.5 * mm, "Buildcon House")
    canvas.setFillColor(GREY)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(doc.leftMargin, 6.5 * mm, "M: +91 99099 06652  |  buildconhouse10@gmail.com")
    right = width - doc.rightMargin
    canvas.drawRightString(right, 10.5 * mm, f"Page {doc.page}")
    canvas.drawRightString(right, 6.5 * mm, "One Destination. Infinite Possibilities.")
    canvas.restoreState()


def _brand_header(right_title: str, styles: dict) -> Table:
    left = [
        Paragraph("<b>BUILDCON HOUSE</b>", styles["brand"]),
        Paragraph("Let You Live Better", styles["tagline"]),
    ]
    right = Paragraph(right_title, styles["titleRight"])
    table = Table([[left, right]], colWidths=[105 * mm, 65 * mm])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return table


def _room_totals(items: Iterable[dict]) -> tuple[float, float, float]:
    subtotal = discount = 0.0
    for item in items:
        gross = float(item.get("qty") or 0) * float(item.get("unit_price") or 0)
        disc = gross * float(item.get("discount_pct") or 0) / 100
        subtotal += gross
        discount += disc
    return subtotal, discount, subtotal - discount


def build_quotation_pdf(quotation: dict, customer: dict) -> bytes:
    """Generate the supplied BuildCon House template: summary, then one room/page."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=14 * mm, bottomMargin=22 * mm, title=quotation.get("number", "Quotation"),
    )
    base = getSampleStyleSheet()
    styles = {
        "brand": ParagraphStyle("brand", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=18, textColor=BLUE, leading=20),
        "tagline": ParagraphStyle("tagline", parent=base["Normal"], fontSize=8.5, textColor=GREY, leading=10),
        "titleRight": ParagraphStyle("titleRight", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=INK, alignment=2),
        "label": ParagraphStyle("label", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=6.5, leading=8, textColor=GREY),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=8, leading=10, textColor=INK),
        "small": ParagraphStyle("small", parent=base["Normal"], fontSize=7, leading=8.5, textColor=INK),
        "tiny": ParagraphStyle("tiny", parent=base["Normal"], fontSize=6.3, leading=7.5, textColor=INK),
        "section": ParagraphStyle("section", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=INK),
        "right": ParagraphStyle("right", parent=base["Normal"], fontSize=7.5, leading=9, alignment=2, textColor=INK),
    }
    story: list[Flowable] = []
    created = (quotation.get("created_at") or datetime.now().isoformat())[:10]
    revision = len(quotation.get("revisions") or [])

    # Page 1 — official quotation summary.
    story.append(_brand_header("PRICE QUOTATION<br/><font size='8' color='#737373'>Bath &amp; Sanitaryware Solutions</font>", styles))
    story.extend([Spacer(1, 3 * mm), HRFlowable(width="100%", thickness=0.45, color=LINE), Spacer(1, 4 * mm)])
    meta = [
        [Paragraph("CUSTOMER NAME", styles["label"]), Paragraph(_escape(customer.get("company") or customer.get("name") or quotation.get("customer_name")), styles["body"]), Paragraph("QUOTATION DATE", styles["label"]), Paragraph(created, styles["body"])],
        [Paragraph("CONTACT NO.", styles["label"]), Paragraph(_escape(quotation.get("phone_snapshot") or customer.get("phone") or "—"), styles["body"]), Paragraph("QUOTATION NO.", styles["label"]), Paragraph(_escape(quotation.get("number")), styles["body"])],
        [Paragraph("PROJECT", styles["label"]), Paragraph(_escape(quotation.get("project_name") or "—"), styles["body"]), Paragraph("REFERENCE", styles["label"]), Paragraph(_escape(quotation.get("reference_source") or "—"), styles["body"])],
        [Paragraph("REVISION", styles["label"]), Paragraph(str(revision), styles["body"]), "", ""],
    ]
    meta_table = Table(meta, colWidths=[30 * mm, 62 * mm, 30 * mm, 48 * mm])
    meta_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.extend([meta_table, Spacer(1, 4 * mm), Paragraph("Dear Sir/Madam, thank you for your interest in our products. We are pleased to offer our most competitive rates for premium bath and sanitaryware fittings, prepared as per your requirements.", styles["body"]), Spacer(1, 5 * mm), Paragraph("QUOTATION SUMMARY", styles["section"]), Spacer(1, 2 * mm)])

    room_order = quotation.get("rooms") or []
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in quotation.get("items", []):
        grouped[item.get("room") or "General"] .append(item)
    for room in grouped:
        if room not in room_order:
            room_order.append(room)
    summary_rows = [["SL. NO.", "BATHROOM / AREA", "MRP (Rs.)", "OFFER RATE (Rs.)"]]
    for index, room in enumerate(room_order, 1):
        room_items = grouped.get(room, [])
        gross, discount, net = _room_totals(room_items)
        summary_rows.append([str(index), room, _money(gross), _money(net)])
    summary_rows.append(["", "TOTAL", _money(quotation.get("subtotal", 0)), _money(quotation.get("grand_total", 0))])
    summary_rows.append(["", "SPECIAL OFFER RATE", "", _money(quotation.get("grand_total", 0))])
    summary = Table(summary_rows, colWidths=[15 * mm, 72 * mm, 41 * mm, 42 * mm], repeatRows=1)
    summary.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.35, LINE), ("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (1, -2), (-1, -1), "Helvetica-Bold"), ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.extend([summary, Spacer(1, 5 * mm), Paragraph("OUR BRAND PARTNERS", styles["section"]), Spacer(1, 1.5 * mm)])
    partners = [["GROHE", "hansgrohe", "AXOR", "VitrA", "NEXION", "QUTONE"], ["DIMORE", "Oyster", "GEBERIT", "MCM ITTIMI", "VERANTES LIVING", "IMPORTED FURNITURE"]]
    partner_table = Table(partners, colWidths=[28.3 * mm] * 6)
    partner_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, LINE), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"), ("TEXTCOLOR", (0, 0), (-1, -1), GREY), ("FONTSIZE", (0, 0), (-1, -1), 6.5), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story.extend([partner_table, Spacer(1, 5 * mm), Paragraph("TERMS &amp; CONDITIONS", styles["section"]), Spacer(1, 1.5 * mm)])
    terms = [
        "1. Prices are inclusive of the discounts stated and are subject to quotation validity.",
        "2. Material is subject to availability at the time of order confirmation.",
        "3. Delivery timelines commence after order confirmation and agreed payment terms.",
        "4. Any changes in quantities, finishes or models require a revised quotation.",
    ]
    story.extend([Paragraph(term, styles["small"]) for term in terms])
    story.extend([Spacer(1, 4 * mm), Paragraph("I/We have reviewed and agree to the terms and conditions mentioned in this quotation.", styles["small"]), Spacer(1, 8 * mm), Paragraph("CUSTOMER SIGNATURE &amp; DATE", ParagraphStyle("signature", parent=styles["label"], alignment=1))])

    # Pages 2+ — each room always starts on a new page; tables split naturally for long rooms.
    for area_index, room in enumerate(room_order, 1):
        room_items = grouped.get(room, [])
        story.append(PageBreak())
        story.append(_brand_header(f"AREA {area_index}: <font size='10'>{_escape(room)}</font>", styles))
        story.extend([Spacer(1, 3 * mm), HRFlowable(width="100%", thickness=0.45, color=LINE), Spacer(1, 3 * mm)])
        header = ["SR.\nNO.", "PRODUCT\nIMAGE", "ARTICLE NO.", "DESCRIPTION", "Q", "T", "MRP (Rs.)", "OFFER RATE (Rs.)", "TOTAL (Rs.)"]
        rows = [header]
        for index, item in enumerate(room_items, 1):
            qty = float(item.get("qty") or 0)
            rate = float(item.get("unit_price") or 0)
            pct = float(item.get("discount_pct") or 0)
            gross = qty * rate
            total = gross * (1 - pct / 100)
            description = _escape(item.get("name"))
            finish = item.get("finish") or item.get("colour") or ""
            if finish:
                description += f"<br/><font color='#737373'>Finish: {_escape(finish)}</font>"
            rows.append([str(index), _img(item.get("image")), _escape(item.get("sku")), Paragraph(description, styles["tiny"]), f"{qty:g}", f"{pct:g}%", _money(gross), _money(rate), _money(total)])
        _, _, room_net = _room_totals(room_items)
        rows.append(["", "", "", "", "", "", "", Paragraph("<b>TOTAL</b>", styles["right"]), Paragraph(f"<b>{_money(room_net)}</b>", styles["right"])])
        table = Table(rows, colWidths=[8 * mm, 25 * mm, 23 * mm, 43 * mm, 7 * mm, 8 * mm, 18 * mm, 19 * mm, 19 * mm], repeatRows=1)
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, LINE), ("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 6.3), ("ALIGN", (0, 0), (0, -1), "CENTER"), ("ALIGN", (4, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(table)
        room_cfg = (quotation.get("room_discounts") or {}).get(room)
        if room_cfg and float(room_cfg.get("value") or 0) > 0:
            story.extend([Spacer(1, 2 * mm), Paragraph(f"Room discount: {_escape(room_cfg.get('value'))}{'%' if room_cfg.get('type') == 'percent' else ' Rs.'}", styles["small"])])

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
