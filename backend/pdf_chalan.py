"""Chalan (Delivery Release Receipt) PDF — proof that ordered tile material
has been released from the supplier's factory. Generated fresh on every
request from a PurchaseOrder's embedded Chalan subdocument, the same way
quotation PDFs are generated on demand with nothing persisted to storage
(see routes/quotation_routes.py::quotation_pdf).
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from pdf_generator import LOGO_PATH, _escape  # noqa: F401 — LOGO_PATH kept for parity with pdf_tiles imports
from pdf_tiles import DEFAULT_ADDRESS, DEFAULT_EMAIL, DEFAULT_MOBILE, _logo_flowable

INK = colors.HexColor("#111111")
GRID_BLACK = colors.HexColor("#000000")
HEADER_GREY = colors.HexColor("#D3D3D3")


def chalan_pdf_filename(chalan: dict, customer_name: str) -> str:
    """`CH-1052 Nileshbhai Pokiya 22-07-2026.pdf`."""
    created = (chalan.get("created_at") or "").replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(created).strftime("%d-%m-%Y")
    except ValueError:
        stamp = datetime.now().strftime("%d-%m-%Y")
    name = " ".join((customer_name or "Customer").split())
    safe = "".join(ch for ch in f"{chalan.get('number', 'CH')} {name} {stamp}" if ch not in '\\/:*?"<>|')
    return f"{safe}.pdf"


def build_chalan_pdf(chalan: dict, po: dict, customer: dict, branding: dict | None = None) -> bytes:
    b = branding or {}
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=10 * mm, bottomMargin=12 * mm,
        title=f"Chalan {chalan.get('number', '')}",
        author=b.get("footer_company_name") or "Buildcon House",
    )
    base = getSampleStyleSheet()
    styles = {
        "label": ParagraphStyle("label", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=13, textColor=INK),
        "value": ParagraphStyle("value", parent=base["Normal"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK),
        "tableHead": ParagraphStyle("tableHead", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=INK, alignment=1),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontName="Helvetica", fontSize=9, leading=11, textColor=INK, alignment=1),
        "cellLeft": ParagraphStyle("cellLeft", parent=base["Normal"], fontName="Helvetica", fontSize=9, leading=11, textColor=INK),
        "footerLabel": ParagraphStyle("footerLabel", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=INK),
        "footerNote": ParagraphStyle("footerNote", parent=base["Normal"], fontName="Helvetica", fontSize=7.6, leading=10, textColor=colors.HexColor("#555555"), alignment=1),
    }

    story: list[Flowable] = []
    story.append(_logo_flowable(60))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=1.2, color=INK, spaceAfter=4 * mm))

    header_rows = [
        [Paragraph("CHALAN NO:", styles["label"]), Paragraph(_escape(chalan.get("number") or ""), styles["value"]),
         Paragraph("DATE:", styles["label"]), Paragraph(_escape((chalan.get("created_at") or "")[:10]), styles["value"])],
        [Paragraph("CUSTOMER:", styles["label"]), Paragraph(_escape(po.get("customer_name") or ""), styles["value"]),
         Paragraph("SUPPLIER:", styles["label"]), Paragraph(_escape(po.get("supplier_name") or ""), styles["value"])],
        [Paragraph("PHONE:", styles["label"]), Paragraph(_escape(customer.get("phone") or ""), styles["value"]),
         Paragraph("REFERENCE:", styles["label"]), Paragraph(_escape(chalan.get("reference_number") or ""), styles["value"])],
    ]
    header = Table(header_rows, colWidths=[28 * mm, 62 * mm, 28 * mm, 62 * mm], rowHeights=[8 * mm] * 3)
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.extend([header, Spacer(1, 6 * mm)])

    head = [
        Paragraph("SR NO.", styles["tableHead"]), Paragraph("TILE NAME", styles["tableHead"]),
        Paragraph("SIZE", styles["tableHead"]), Paragraph("QUANTITY", styles["tableHead"]),
        Paragraph("UNIT", styles["tableHead"]),
    ]
    rows: list[list[object]] = [head]
    for index, item in enumerate(chalan.get("items") or [], 1):
        rows.append([
            Paragraph(str(index), styles["cell"]),
            Paragraph(_escape(item.get("name") or ""), styles["cellLeft"]),
            Paragraph(_escape(item.get("size") or ""), styles["cell"]),
            Paragraph(f"{float(item.get('qty') or 0):g}", styles["cell"]),
            Paragraph(_escape(item.get("unit") or "Box"), styles["cell"]),
        ])
    table = Table(rows, colWidths=[18 * mm, 72 * mm, 30 * mm, 30 * mm, 30 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.9, GRID_BLACK),
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_GREY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([table, Spacer(1, 14 * mm)])

    receiver_rows = [
        [Paragraph("Receiver Name:", styles["footerLabel"]), Paragraph(_escape(chalan.get("receiver_name") or ""), styles["value"])],
        [Paragraph("Receiver Signature:", styles["footerLabel"]), HRFlowable(width="60%", thickness=0.8, color=INK)],
    ]
    receiver = Table(receiver_rows, colWidths=[85 * mm, 85 * mm], rowHeights=[8 * mm, 14 * mm])
    receiver.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(receiver)
    story.append(Spacer(1, 10 * mm))

    sender_rows = [
        [Paragraph("Supplier Representative:", styles["footerLabel"]), Paragraph(_escape(chalan.get("sender_name") or ""), styles["value"])],
        [Paragraph("Sender Signature:", styles["footerLabel"]), HRFlowable(width="60%", thickness=0.8, color=INK)],
    ]
    sender = Table(sender_rows, colWidths=[85 * mm, 85 * mm], rowHeights=[8 * mm, 14 * mm])
    sender.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(sender)
    story.append(Spacer(1, 10 * mm))

    story.append(HRFlowable(width="100%", thickness=0.9, color=INK, spaceAfter=2 * mm))
    address_line = b.get("company_address") or DEFAULT_ADDRESS
    email = b.get("footer_email") or DEFAULT_EMAIL
    mobile = b.get("footer_phone") or DEFAULT_MOBILE
    story.append(Paragraph(
        f"{_escape(b.get('footer_company_name') or 'Buildcon House')} &middot; {_escape(address_line)} &middot; {_escape(email)} &middot; {_escape(mobile)}",
        styles["footerNote"],
    ))

    doc.build(story)
    return buf.getvalue()
