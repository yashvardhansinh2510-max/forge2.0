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


def rows_to_csv(rows: list[dict], columns: list[Column]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([row.get(key, "") for key, _ in columns])
    return buf.getvalue().encode("utf-8")  # UTF-8 encoding for compatibility


def rows_to_xlsx(rows: list[dict], columns: list[Column], sheet_title: str = "Export") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]  # Excel's own sheet-name length limit
    ws.append([label for _, label in columns])
    for row in rows:
        ws.append([row.get(key, "") for key, _ in columns])
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
