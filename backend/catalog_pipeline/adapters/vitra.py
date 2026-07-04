"""VITRA XLSX adapter.

The 2026 Price Table stores each product family on ONE row, then repeats
Code / IMAGE / MRP for every finish (WHITE 003/403, MATT WHITE 401, MATT TAUPE 420,
MATT STONE GREY 476, MATT BLACK 483). We fan those out into one ProductRow per
non-empty finish variant.

Row layout observed in the real 2026 file:
  Row 1 : finish headers (spanning across 4 columns each)
  Row 2 : per-finish sub-headers: Code, IMAGE, MRP, (blank)
  Row 3+: product rows. Col A = Family (Design). Col B = Detail. Then 4-col groups.
"""
from __future__ import annotations
import io
import re

from ..base import MISSING, BrandAdapter, ExtractionReport, ProductRow
from ..image_extractor import extract_images_from_xlsx

SKU_RE = re.compile(r"[A-Z]?\d{3,6}B[A-Z0-9]+H\d{2,6}", re.IGNORECASE)

SHEET_TO_CATEGORY = {
    "csw": "Water Closets",     # Ceramic Sanitary Ware
    "wc": "Water Closets", "toilet": "Water Closets", "closet": "Water Closets",
    "urinal": "Urinals", "bidet": "Bidets",
    "basin": "Basins", "washbasin": "Basins", "counter": "Basins", "vanity": "Basins",
    "mixer": "Faucets", "faucet": "Faucets", "tap": "Faucets",
    "shower": "Showers",
    "cistern": "Concealed Cisterns", "flush": "Flush Plates",
    "bathtub": "Bathtubs", "tub": "Bathtubs",
    "accessor": "Accessories",
}


def _classify(sheet_name: str, detail: str) -> str:
    combined = f"{sheet_name} {detail}".lower()
    for k, v in SHEET_TO_CATEGORY.items():
        if k in combined:
            return v
    return MISSING


class VitraAdapter(BrandAdapter):
    brand = "Vitra"
    supported_extensions = (".xlsx", ".xls")

    def extract(self, data: bytes, filename: str) -> tuple[list[ProductRow], ExtractionReport]:
        report = ExtractionReport(brand=self.brand, filename=filename, source_type="excel")
        rows: list[ProductRow] = []
        try:
            from openpyxl import load_workbook  # type: ignore
        except Exception as e:  # pragma: no cover
            report.warnings.append(f"openpyxl missing: {e}")
            return rows, report
        try:
            wb = load_workbook(io.BytesIO(data), data_only=True)
        except Exception as e:
            report.warnings.append(f"xlsx open failed: {e}")
            return rows, report

        last_design = MISSING

        # Extract every raster image up front, keyed by (sheet, anchor_row_1based).
        images_by_key: dict[tuple[str, int], list[str]] = {}
        for sheet, row_idx, _h, url in extract_images_from_xlsx(data):
            images_by_key.setdefault((sheet, row_idx), []).append(url)
        report.images_found = sum(len(v) for v in images_by_key.values())

        for ws in wb.worksheets:
            all_rows: list[list] = [list(r) for r in ws.iter_rows(values_only=True)]
            if len(all_rows) < 3:
                continue

            # Row 1 (index 0) = finish group headers spanning ≥4 cols each.
            finish_header = all_rows[0]
            # Row 2 (index 1) = per-finish sub-headers: Code / IMAGE / MRP repeating
            sub_header = all_rows[1]

            # Detect finish groups strictly (skip DESIGN/DETAIL columns):
            # only accept a finish label if the sub-header row has "Code" within its own
            # column block (not stealing from a later group's Code column).
            raw_groups: list[tuple[str, int]] = []
            for col, val in enumerate(finish_header):
                if val and str(val).strip():
                    raw_groups.append((str(val).strip(), col))
            group_columns: list[tuple[str, int, int]] = []  # (finish, code_col, mrp_col)
            for gi, (finish, start_col) in enumerate(raw_groups):
                # Block ends where the next group starts
                next_col = raw_groups[gi + 1][1] if gi + 1 < len(raw_groups) else len(sub_header)
                code_col: int | None = None
                mrp_col: int | None = None
                for c in range(start_col, min(next_col, len(sub_header))):
                    label = str(sub_header[c] or "").strip().lower()
                    if label == "code" and code_col is None:
                        code_col = c
                    elif label == "mrp" and mrp_col is None:
                        mrp_col = c
                if code_col is not None and mrp_col is not None:
                    group_columns.append((finish, code_col, mrp_col))

            if not group_columns:
                # Fallback: probably a narrow sheet — read first non-empty column as code
                report.warnings.append(f"Sheet '{ws.title}' has no recognizable finish groups; fell back to narrow parser")

            for r_idx, row in enumerate(all_rows[2:], start=3):
                design = str(row[0] or "").strip() or last_design
                detail = str(row[1] or "").strip() if len(row) > 1 else ""
                if design:
                    last_design = design

                if group_columns:
                    for finish, code_col, mrp_col in group_columns:
                        code_cell = str(row[code_col]).strip() if code_col < len(row) and row[code_col] not in (None, "") else ""
                        if not code_cell:
                            continue
                        # Some cells hold multiple codes on separate lines — take the first
                        primary_sku = code_cell.splitlines()[0].strip()
                        extras = [s.strip() for s in code_cell.splitlines()[1:] if s.strip()]
                        mrp_raw = row[mrp_col] if mrp_col < len(row) else None
                        mrp = self.to_number(mrp_raw)
                        cat = _classify(ws.title, detail)
                        family_key = f"vitra:{ws.title.lower()}:{re.sub(r'[^a-z0-9]+', '-', design.lower())}:{re.sub(r'[^a-z0-9]+', '-', detail.lower())}"

                        # Try to map an image anchored at this row (row is 1-based
                        # in openpyxl but embedded images anchor at the row above
                        # for tall row heights). Try several offsets.
                        imgs: list[str] = []
                        for delta in (0, -1, 1, -2, 2):
                            imgs = images_by_key.get((ws.title, r_idx + delta)) or []
                            if imgs:
                                break
                        if imgs:
                            report.images_mapped += 1

                        pr = ProductRow(
                            brand=self.brand, sku=primary_sku,
                            name=f"{design} · {detail}".strip(" ·") or design or MISSING,
                            category=cat,
                            subcategory=ws.title if ws.title else MISSING,
                            series=design or MISSING, family_key=family_key,
                            variant=finish, finish=finish, colour=finish,
                            dimensions=detail if detail else MISSING,
                            mrp=mrp, dealer_price=MISSING,
                            images=imgs[:1], image_page=None,
                            accessories=extras,   # any secondary codes are related SKUs
                            confidence=0.96 if mrp != MISSING and cat != MISSING else 0.7,
                        )
                        if mrp == MISSING:
                            pr.issues.append("Missing MRP for this finish")
                        if cat == MISSING:
                            pr.issues.append("Category not derivable from sheet + detail")
                        rows.append(pr)
                else:
                    # Narrow fallback: search row for one SKU
                    joined = " | ".join(str(c) for c in row if c)
                    m = SKU_RE.search(joined)
                    if m:
                        rows.append(ProductRow(
                            brand=self.brand, sku=m.group(0),
                            name=(design + " · " + detail).strip(" ·") or MISSING,
                            category=_classify(ws.title, detail),
                            series=design or MISSING,
                            family_key=f"vitra:{ws.title.lower()}:{design.lower()}",
                            confidence=0.55,
                        ))

        report.parsed_rows = len(rows)
        return rows, report
