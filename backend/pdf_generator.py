"""ReportLab-based quotation PDF. Minimal, elegant, timeless."""
from io import BytesIO
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)


def _money(v: float) -> str:
    return f"₹ {v:,.2f}"


def build_quotation_pdf(quotation: dict, customer: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title=quotation.get("number", "Quotation"),
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#71717A"), leading=11)
    label = ParagraphStyle("label", parent=styles["Normal"], fontSize=7, textColor=colors.HexColor("#71717A"), leading=10, spaceAfter=2)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=14, textColor=colors.HexColor("#18181B"))
    right = ParagraphStyle("right", parent=body, alignment=2)

    story = []

    # Header
    header = Table(
        [[
            Paragraph("<b>FORGE</b>", ParagraphStyle("brand", fontSize=14, textColor=colors.HexColor("#18181B"), leading=18)),
            Paragraph(f"<b>QUOTATION</b><br/><font size=9 color='#71717A'>{quotation['number']}</font>", right),
        ]],
        colWidths=[90 * mm, 80 * mm],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header)
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E4E4E7")))
    story.append(Spacer(1, 10))

    # Meta row: customer + dates
    created = (quotation.get("created_at") or "")[:10]
    valid = quotation.get("valid_until") or "—"
    meta = Table(
        [[
            [Paragraph("BILL TO", label), Paragraph(f"<b>{customer.get('company') or customer.get('name','')}</b>", body),
             Paragraph(customer.get("address") or "", small),
             Paragraph(customer.get("email") or "", small)],
            [Paragraph("DATE", label), Paragraph(created, body),
             Paragraph("VALID UNTIL", label), Paragraph(valid, body)],
        ]],
        colWidths=[95 * mm, 75 * mm],
    )
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(meta)
    story.append(Spacer(1, 14))

    # Line items table
    header_row = ["#", "Product", "SKU", "Qty", "Rate", "Disc%", "Amount"]
    rows = [header_row]
    for idx, it in enumerate(quotation.get("items", []), start=1):
        qty = float(it.get("qty", 0) or 0)
        price = float(it.get("unit_price", 0) or 0)
        disc = float(it.get("discount_pct", 0) or 0)
        gross = qty * price
        amount = gross - (gross * disc / 100)
        rows.append([
            str(idx),
            it.get("name", ""),
            it.get("sku", ""),
            f"{qty:g}",
            _money(price),
            f"{disc:g}",
            _money(amount),
        ])

    tbl = Table(rows, colWidths=[10 * mm, 65 * mm, 30 * mm, 15 * mm, 20 * mm, 15 * mm, 25 * mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#71717A")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FAFAFA")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#E4E4E7")),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#E4E4E7")),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 12))

    # Totals block (right aligned) — Forge uses final prices only
    totals_rows = [
        ["Subtotal", _money(quotation.get("subtotal", 0))],
        ["Discount", f"- {_money(quotation.get('discount_total', 0))}"],
        ["Grand Total", _money(quotation.get("grand_total", 0))],
    ]
    totals = Table(totals_rows, colWidths=[40 * mm, 35 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#71717A")),
        ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#111111")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#111111")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(totals)

    if quotation.get("notes"):
        story.append(Spacer(1, 16))
        story.append(Paragraph("NOTES", label))
        story.append(Paragraph(quotation["notes"], small))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E4E4E7")))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"Generated by Forge · {datetime.now().strftime('%d %b %Y, %H:%M')} · This quotation supersedes any previous revision.",
        small,
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()
