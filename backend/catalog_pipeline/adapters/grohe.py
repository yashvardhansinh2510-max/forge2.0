"""GROHE PDF adapter.
SKU: 8-digit numeric (e.g. 24397000).
Prices: ₹ followed by a large number.
Product name usually contains series + size (M-Size / L-Size / XL-Size) + finish description.
"""
from __future__ import annotations
import io
import logging
import re
from typing import Iterable

from ..base import MISSING, BrandAdapter, ExtractionReport, ProductRow
from ..image_extractor import extract_images_from_pdf

logger = logging.getLogger("forge.catalog_pipeline.grohe")

SKU_RE = re.compile(r"^(\d{8})$")
PRICE_RE = re.compile(r"[`₹]\s*([\d,]+)")
SIZE_RE = re.compile(r"\b([MLXS]{1,2}|X{1,2}L)-Size\b", re.IGNORECASE)

# Detect finish tokens
FINISH_TOKENS = [
    "Chrome", "Matt Black", "Warm Sunset", "Cool Sunrise", "SuperSteel",
    "Brushed Cool Sunrise", "Brushed Warm Sunset", "Brushed Nickel",
    "Hard Graphite", "Moon White", "Nickel", "Gold",
]
CATEGORY_HINTS = {
    "Bathroom Fittings": "Faucets",
    "Bath Fittings": "Faucets",
    "Showers": "Showers",
    "Shower Systems": "Showers",
    "Hand Showers": "Showers",
    "Shower Railsets": "Showers",
    "Kitchen": "Faucets",
    "Sinks": "Kitchen Sinks",
    "Bath Tubs": "Bathtubs",
    "Bathtubs": "Bathtubs",
    "Urinals": "Urinals",
    "Flushing Systems": "Flush Plates",
    "Sensor Faucets": "Faucets",
    "Thermostats & Smart Control Mixers": "Faucets",
    "Accessories": "Accessories",
    "Bathroom Accessories": "Accessories",
    "Shower Accessories": "Accessories",
}


def _sniff_series(text: str, series_pool: list[str]) -> str:
    """Guess series (Allure / Grohtherm / Essence …) from product line text."""
    for s in series_pool:
        if s and s.lower() in text.lower():
            return s
    return MISSING


class GroheAdapter(BrandAdapter):
    brand = "Grohe"
    supported_extensions = (".pdf",)

    def extract(self, data: bytes, filename: str) -> tuple[list[ProductRow], ExtractionReport]:
        report = ExtractionReport(brand=self.brand, filename=filename, source_type="pdf")
        rows: list[ProductRow] = []
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception as e:
            report.warnings.append(f"pypdf missing: {e}")
            return rows, report

        try:
            reader = PdfReader(io.BytesIO(data))
        except Exception as e:
            report.warnings.append(f"pdf open failed: {e}")
            return rows, report

        report.pages = len(reader.pages)

        # Pass 1 — walk text pages, capture section headings + product lines
        current_category = MISSING
        current_series = MISSING
        # Common Grohe series we'll auto-detect
        SERIES_POOL = [
            "Allure Brilliant", "Allure", "Atrio Private", "Atrio", "Grohtherm Cube",
            "Grohtherm", "Essence", "Eurosmart Cosmopolitan", "Eurosmart", "Eurocube",
            "Cubeo", "Lineare", "Bau", "Rainshower SmartActive", "Rainshower",
            "SmartControl", "Vitalio", "Grandera",
        ]

        for page_idx, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                continue
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            report.raw_rows += len(lines)

            i = 0
            while i < len(lines):
                line = lines[i]

                # Section heading
                if len(line) < 40 and line in CATEGORY_HINTS:
                    current_category = CATEGORY_HINTS[line]
                    i += 1; continue

                # Series heading
                if len(line) < 80 and SKU_RE.match(line) is None and PRICE_RE.search(line) is None:
                    guessed = _sniff_series(line, SERIES_POOL)
                    if guessed != MISSING:
                        current_series = guessed

                # Multi-line product block: SKU · Name · Price
                if SKU_RE.match(line):
                    sku = line
                    name = lines[i + 1] if i + 1 < len(lines) else MISSING
                    price_line = lines[i + 2] if i + 2 < len(lines) else ""
                    mrp = MISSING
                    pm = PRICE_RE.search(price_line)
                    if pm:
                        mrp = self.to_number(pm.group(1))
                    else:
                        # sometimes price is same line as name
                        pm2 = PRICE_RE.search(name)
                        if pm2:
                            mrp = self.to_number(pm2.group(1))
                            name = PRICE_RE.sub("", name).strip()

                    if not name or name == MISSING or SKU_RE.match(name) or PRICE_RE.search(name):
                        # this block doesn't look like a real product
                        i += 1; continue

                    size_m = SIZE_RE.search(name)
                    size = size_m.group(0) if size_m else MISSING

                    finish = MISSING
                    for t in FINISH_TOKENS:
                        if t.lower() in name.lower():
                            finish = t
                            break

                    series = current_series if current_series != MISSING else _sniff_series(name, SERIES_POOL)

                    base = SIZE_RE.sub("", name)
                    for t in FINISH_TOKENS:
                        base = re.sub(re.escape(t), "", base, flags=re.IGNORECASE)
                    family_key = f"grohe:{(series or MISSING).lower()}:{re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-')[:60]}"

                    pr = ProductRow(
                        brand=self.brand, name=name, sku=sku,
                        category=current_category, series=series, family_key=family_key,
                        variant=f"{size} {finish}".strip() if finish != MISSING else size,
                        finish=finish, dimensions=size if size != MISSING else MISSING,
                        mrp=mrp, dealer_price=MISSING, image_page=page_idx,
                        confidence=0.94 if mrp != MISSING and current_category != MISSING else 0.6,
                    )
                    if pr.mrp == MISSING:
                        pr.issues.append("Missing MRP")
                    if pr.category == MISSING:
                        pr.issues.append("Category needs manual assignment")
                    rows.append(pr)
                    i += 3
                    continue
                i += 1

        # Pass 2 — image extraction. Map images to nearest product row by page.
        images_by_page: dict[int, list[str]] = {}
        for page_idx, _h, url in extract_images_from_pdf(data):
            images_by_page.setdefault(page_idx, []).append(url)
        report.images_found = sum(len(v) for v in images_by_page.values())

        for pr in rows:
            imgs = images_by_page.get(pr.image_page or -1, [])
            if imgs:
                pr.images = imgs[:1]  # first image on the page is a heuristic starting point
                report.images_mapped += 1

        report.parsed_rows = len(rows)
        return rows, report
