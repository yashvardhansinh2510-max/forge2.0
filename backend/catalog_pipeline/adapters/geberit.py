"""GEBERIT PDF adapter.
SKU: dotted (e.g. 109.791.00.1 / 116.092.SG.6).
Section demarcation: SIGMA80 SQUARE / SIGMA70 SQUARE, etc. — becomes 'series'.
Category comes from top-level headings (Concealed Cisterns, Actuator Plates, …).
"""
from __future__ import annotations
import io
import re

from ..base import MISSING, BrandAdapter, ExtractionReport, ProductRow
from ..image_extractor import extract_images_from_pdf

SKU_RE = re.compile(r"\b(\d{3}\.\d{3}\.[A-Z0-9]{2}\.\d)\b")
PRICE_RE = re.compile(r"MRP:\s*[`₹]?\s*([\d,]+)", re.IGNORECASE)

COLOUR_RE = re.compile(
    r"(black glass|glass reflective|black matt|stainless steel brushed|glass lava|glass sand grey|"
    r"white matt|red gold|black chrome|brushed chrome|matt black|matt chrome|chrome|white|"
    r"umber glass|brushed steel|black|grey)",
    re.IGNORECASE,
)

CATEGORY_HINTS = {
    "CONCEALED CISTERN": "Concealed Cisterns",
    "INSTALLATION": "Concealed Cisterns",
    "ACTUATOR PLATES": "Flush Plates",
    "FLUSH PLATES": "Flush Plates",
    "URINAL": "Urinals",
    "SHOWER DRAIN": "Accessories",
    "FLOOR DRAIN": "Accessories",
    "BATHROOM SYSTEM": "Basins",
    "MONOLITH": "Water Closets",
    "AQUACLEAN": "Water Closets",
    "WC": "Water Closets",
    "BIDET": "Bidets",
}

SERIES_POOL = [
    "Sigma80 Square", "Sigma70 Square", "Sigma70", "Sigma80", "Sigma60", "Sigma50",
    "Sigma20", "Sigma10", "Sigma8", "Sigma", "Omega", "Duofix", "Kombifix",
    "Monolith Plus", "Monolith", "AquaClean Mera", "AquaClean Sela", "AquaClean Tuma",
    "AquaClean",
]


JUNK_NAME_RE = re.compile(
    r"^(article\s*no\.?|art\.?\s*no\.?|articleno|sku|description|colou?r|finish|price|mrp)\.?$",
    re.IGNORECASE,
)


class GeberitAdapter(BrandAdapter):
    brand = "Geberit"
    supported_extensions = (".pdf",)

    def extract(self, data: bytes, filename: str) -> tuple[list[ProductRow], ExtractionReport]:
        report = ExtractionReport(brand=self.brand, filename=filename, source_type="pdf")
        rows: list[ProductRow] = []
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception as e:  # pragma: no cover
            report.warnings.append(f"pypdf missing: {e}")
            return rows, report
        try:
            reader = PdfReader(io.BytesIO(data))
        except Exception as e:
            report.warnings.append(f"pdf open failed: {e}")
            return rows, report

        report.pages = len(reader.pages)
        current_category = MISSING
        current_series = MISSING

        for page_idx, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                continue
            lines_all = [ln.rstrip() for ln in text.splitlines()]
            lines = [ln.strip() for ln in lines_all if ln.strip()]
            report.raw_rows += len(lines)

            for idx, line in enumerate(lines):
                up = line.upper()

                # Detect category heading
                for k, v in CATEGORY_HINTS.items():
                    if k in up and len(line) < 60:
                        current_category = v
                        break

                # Detect series
                for s in SERIES_POOL:
                    if s.upper() in up and len(line) < 60 and not SKU_RE.search(line):
                        current_series = s
                        break

                m = SKU_RE.search(line)
                if not m:
                    continue
                sku = m.group(1)

                # Look for MRP on this line first, then nearby lines (up to 4 above/below)
                mrp = MISSING
                for cand in [line] + [lines[j] for j in range(max(0, idx - 2), min(len(lines), idx + 5)) if j != idx]:
                    pm = PRICE_RE.search(cand)
                    if pm:
                        mrp = self.to_number(pm.group(1))
                        break

                # Everything between sku and price = name/description; also strip 'MRP: ...' trailer
                text_without = SKU_RE.sub("", line)
                text_without = re.sub(r"MRP:\s*[`₹]?\s*[\d,]+", "", text_without, flags=re.IGNORECASE)
                name = text_without.strip(" ·-|:")
                # A bare table-header label (e.g. "Article No.") sometimes leaks onto the
                # same extracted text line as the SKU for certain multi-column variant-grid
                # tables (colour/finish price grids). Treat that as no name at all so the
                # existing backward-search fallback below finds the real description line —
                # never let a header label become the product's name.
                if name and JUNK_NAME_RE.match(name.strip()):
                    name = ""
                # If name still empty, try previous non-header non-SKU line as description
                if not name or name == "":
                    for j in range(idx - 1, max(-1, idx - 5), -1):
                        cand = lines[j]
                        if SKU_RE.search(cand) or PRICE_RE.search(cand):
                            continue
                        # skip section/scope lines
                        if cand.upper().startswith(("SCOPE OF DELIVERY", "•", "MRP")):
                            continue
                        if len(cand) > 15:
                            name = cand
                            break
                if not name:
                    name = MISSING

                colour = MISSING
                cm = COLOUR_RE.search(name if name != MISSING else "")
                if cm:
                    colour = cm.group(1).title()

                variant = colour if colour != MISSING else MISSING
                family_key = f"geberit:{(current_series or MISSING).lower()}:{sku.rsplit('.', 2)[0]}"

                pr = ProductRow(
                    brand=self.brand, sku=sku, name=name or MISSING,
                    category=current_category, series=current_series,
                    family_key=family_key, variant=variant,
                    finish=colour, colour=colour, mrp=mrp, image_page=page_idx,
                    confidence=0.92 if mrp != MISSING and current_category != MISSING else 0.6,
                )
                if pr.mrp == MISSING:
                    pr.issues.append("Missing MRP — likely accessory or spare")
                if pr.category == MISSING:
                    pr.issues.append("Category needs manual assignment")
                rows.append(pr)

        # Image mapping
        images_by_page: dict[int, list[str]] = {}
        for pi, _h, url in extract_images_from_pdf(data):
            images_by_page.setdefault(pi, []).append(url)
        report.images_found = sum(len(v) for v in images_by_page.values())
        for pr in rows:
            imgs = images_by_page.get(pr.image_page or -1, [])
            if imgs:
                pr.images = imgs[:1]
                report.images_mapped += 1

        report.parsed_rows = len(rows)
        return rows, report
