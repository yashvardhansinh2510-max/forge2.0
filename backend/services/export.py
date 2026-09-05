"""Generic rows -> CSV/XLSX export, shared by every Phase 2 table.

CSV and XLSX only. Every PDF export in this codebase (chalan, quotation,
followups) is a bespoke document layout with no generic table pattern to
build on — see the Phase 2 plan's Global Constraints for the full reasoning.
Existing per-route csv/openpyxl exports (executive_analytics_routes.py,
followup_routes.py, purchases_tracker.py, catalog_routes.py) are not
refactored onto this helper; this is new surface only.
"""
from __future__ import annotations

import csv
import io

import openpyxl
from fastapi.responses import StreamingResponse

Column = tuple[str, str]


def spreadsheet_cell(value):
    """Keep untrusted text from becoming an Excel/Sheets formula.

    Real numbers remain numeric (including negative amounts). Only text is
    escaped, including formula prefixes hidden behind leading whitespace.
    """
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def rows_to_csv(rows: list[dict], columns: list[Column]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([spreadsheet_cell(row.get(key, "")) for key, _ in columns])
    # UTF-8 with BOM (byte-order-mark): required for Excel to correctly detect UTF-8
    # and render non-ASCII characters (₹ rupee symbol) when user opens CSV directly.
    # Without BOM, Excel guesses a system ANSI codepage and produces mojibake.
    # The BOM is safe: utf-8-sig decode strips it, utf-8 decode shows it as literal
    # — tests must use utf-8-sig decode to handle the BOM correctly.
    return buf.getvalue().encode("utf-8-sig")


def rows_to_xlsx(rows: list[dict], columns: list[Column], sheet_title: str = "Export") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]  # Excel's own sheet-name length limit
    ws.append([label for _, label in columns])
    for row in rows:
        ws.append([spreadsheet_cell(row.get(key, "")) for key, _ in columns])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_MEDIA_TYPES = {"csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def export_response(rows: list[dict], columns: list[Column], filename_base: str, fmt: str) -> StreamingResponse:
    if fmt not in _MEDIA_TYPES:
        raise ValueError(f"unsupported export format: {fmt}")
    data = rows_to_csv(rows, columns) if fmt == "csv" else rows_to_xlsx(rows, columns, sheet_title=filename_base)
    return StreamingResponse(
        io.BytesIO(data), media_type=_MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename_base}.{fmt}"'},
    )
