"""GEBERIT PDF adapter (PyMuPDF-based — rewritten to fix two root causes).

SKU: dotted (e.g. 109.791.00.1 / 116.092.SG.6).
Category comes from top-level headings (Concealed Cisterns, Actuator Plates, …).
Series comes from sub-headings (Sigma80 Square, Monolith, …).

Root causes fixed vs. the previous pypdf-based version:

1. IMAGE SHARING: the old code mapped images by page only and gave the
   FIRST image on the page to every SKU on that page. Geberit pages
   routinely show 3-6 different colour/finish variants side-by-side, each
   with its own photo — so every variant ended up showing the same picture.
   This version uses PyMuPDF to get each image's real (x, y) position on
   the page and geometrically matches it to its own nearest product text
   block (photo directly above the block, same horizontal band). No image
   is ever assigned to more than one product row.

2. MISSING COLOUR/FINISH: the old code grabbed a "nearby text line" via a
   backward search and searched it for a colour word — which routinely
   grabbed spec-sheet bullets, disclaimers or section headers instead of
   the real product line, so colour resolved for <1% of rows. This version
   reads PyMuPDF's text BLOCKS, which the supplier's own PDF already groups
   as one block per product ("Article No.: X / Colour: Y / MRP: Z") for the
   colour/finish grid pages — so the colour is read directly, verbatim,
   with zero guessing.

For pages that don't use the "Article No./Colour/MRP" grid layout (plain
single-line accessory listings, e.g. Duofix elements), a fallback line
parser preserves the previous behaviour — those rows never claimed to have
a colour to begin with, so there's no regression there.
"""
from __future__ import annotations
import re
from collections import defaultdict

from ..base import MISSING, BrandAdapter, ExtractionReport, ProductRow
from ..image_extractor import extract_images_from_pdf_positioned

SKU_RE = re.compile(r"\b(\d{3}\.\d{3}\.[A-Z0-9]{2}\.\d)\b")
PRICE_RE = re.compile(r"MRP:\s*[`₹]?\s*([\d,]+)", re.IGNORECASE)

# Matches the supplier's own structured product block verbatim — no guessing.
STRUCTURED_RE = re.compile(
    r"Article\s*No\.?:?\s*(\d{3}\.\d{3}\.[A-Z0-9]{2}\.\d)\s*"
    r"Colour:\s*(.+?)\s*"
    r"MRP:\s*[`₹]?\s*([\d,]+)",
    re.IGNORECASE | re.DOTALL,
)

JUNK_NAME_RE = re.compile(
    r"^(article\s*no\.?|art\.?\s*no\.?|articleno|sku|description|colou?r|finish|price|mrp)\.?$",
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

# Max vertical gap (PDF points) between an image's bottom edge and a
# product block's top edge for it to be considered "this block's photo".
# Chosen from the real file (typical photo-to-caption gap there is ~3-15pt);
# 60pt gives headroom for slightly taller captions without reaching into
# the next row of products (~130-260pt apart in the observed grid).
MAX_IMAGE_GAP = 60


class GeberitAdapter(BrandAdapter):
    brand = "Geberit"
    supported_extensions = (".pdf",)

    def extract(self, data: bytes, filename: str) -> tuple[list[ProductRow], ExtractionReport]:
        report = ExtractionReport(brand=self.brand, filename=filename, source_type="pdf")
        rows: list[ProductRow] = []
        try:
            import fitz  # PyMuPDF
        except Exception as e:  # pragma: no cover
            report.warnings.append(f"PyMuPDF missing: {e}")
            return rows, report
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as e:
            report.warnings.append(f"pdf open failed: {e}")
            return rows, report

        report.pages = len(doc)
        current_category = MISSING
        current_series = MISSING

        # (page_idx_0based) -> list of (bbox, ProductRow) needing an image
        page_claims: dict[int, list[tuple[tuple[float, float, float, float], ProductRow]]] = defaultdict(list)

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            try:
                blocks = page.get_text("blocks")
            except Exception:
                continue
            # Reading order: rows of the grid top-to-bottom, left-to-right
            # within a row. Round y to bucket blocks that are visually on
            # the same row despite tiny baseline differences.
            blocks = sorted(blocks, key=lambda b: (round(b[1] / 15.0), b[0]))
            report.raw_rows += len(blocks)

            for b in blocks:
                x0, y0, x1, y1, text, _bno, btype = b
                if btype != 0:
                    continue
                clean = text.strip()
                if not clean:
                    continue
                up = clean.upper()

                m = STRUCTURED_RE.search(clean)
                if m:
                    sku, colour_raw, mrp_raw = m.groups()
                    colour = re.sub(r"\s+", " ", colour_raw).strip(" ,.")
                    mrp = self.to_number(mrp_raw)
                    family_key = f"geberit:{(current_series if current_series != MISSING else 'misc').lower().replace(' ', '-')}:{sku.rsplit('.', 2)[0]}"
                    name_series = current_series if current_series != MISSING else ""
                    name = f"{name_series} {colour}".strip() or MISSING
                    pr = ProductRow(
                        brand=self.brand, sku=sku, name=name,
                        category=current_category, series=current_series,
                        family_key=family_key, variant=colour, finish=colour,
                        colour=colour, mrp=mrp, image_page=page_idx + 1,
                        confidence=0.95 if mrp != MISSING and current_category != MISSING else 0.65,
                    )
                    if mrp == MISSING:
                        pr.issues.append("Missing MRP")
                    if current_category == MISSING:
                        pr.issues.append("Category needs manual assignment")
                    rows.append(pr)
                    page_claims[page_idx].append(((x0, y0, x1, y1), pr))
                    continue

                # Heading / section detection (category + series), only on
                # short caption-style blocks — never on a full product block.
                if len(clean) < 80:
                    for k, v in CATEGORY_HINTS.items():
                        if k in up:
                            current_category = v
                            break
                    for s in SERIES_POOL:
                        if s.upper() in up and not SKU_RE.search(clean):
                            current_series = s
                            break

                # Fallback: plain "<sku> - <description>" accessory lines
                # (e.g. Duofix elements) that don't use the colour grid at
                # all. These never claimed a colour before either — no
                # regression, just kept working the same way.
                for line in clean.splitlines():
                    lm = SKU_RE.search(line)
                    if not lm:
                        continue
                    sku = lm.group(1)
                    name = SKU_RE.sub("", line).strip(" -–:")
                    if not name or JUNK_NAME_RE.match(name):
                        name = MISSING
                    mrp = MISSING
                    pm = PRICE_RE.search(clean)
                    if pm:
                        mrp = self.to_number(pm.group(1))
                    family_key = f"geberit:{(current_series if current_series != MISSING else 'misc').lower().replace(' ', '-')}:{sku.rsplit('.', 2)[0]}"
                    pr = ProductRow(
                        brand=self.brand, sku=sku, name=name,
                        category=current_category, series=current_series,
                        family_key=family_key, mrp=mrp, image_page=page_idx + 1,
                        confidence=0.7 if mrp != MISSING and current_category != MISSING else 0.5,
                    )
                    if mrp == MISSING:
                        pr.issues.append("Missing MRP — likely spec/accessory row, needs manual price")
                    if current_category == MISSING:
                        pr.issues.append("Category needs manual assignment")
                    rows.append(pr)
                    page_claims[page_idx].append(((x0, y0, x1, y1), pr))

        # ---- Geometric image matching: each image goes to AT MOST one
        # product block (its nearest one), never borrowed by a second row.
        images_by_page: dict[int, list[tuple[tuple[float, float, float, float], object]]] = defaultdict(list)
        for page_no, bbox, img in extract_images_from_pdf_positioned(data):
            images_by_page[page_no].append((bbox, img))
        report.images_found = sum(len(v) for v in images_by_page.values())

        for page_idx, claims in page_claims.items():
            imgs = images_by_page.get(page_idx + 1, [])
            if not imgs or not claims:
                continue
            candidates: list[tuple[float, int, int]] = []
            for ci, (cbbox, _pr) in enumerate(claims):
                cx0, cy0, cx1, _cy1 = cbbox
                for ii, (ibbox, _img) in enumerate(imgs):
                    ix0, iy0, ix1, iy1 = ibbox
                    overlap = min(cx1, ix1) - max(cx0, ix0)
                    if overlap <= 0:
                        continue
                    if iy1 > cy0 + 20:
                        continue  # image is not above (or overlapping) this block — never borrow from below
                    vgap = max(0.0, cy0 - iy1)
                    if vgap > MAX_IMAGE_GAP:
                        continue
                    candidates.append((vgap, ci, ii))
            candidates.sort(key=lambda t: t[0])
            used_claims: set[int] = set()
            used_imgs: set[int] = set()
            for vgap, ci, ii in candidates:
                if ci in used_claims or ii in used_imgs:
                    continue
                used_claims.add(ci)
                used_imgs.add(ii)
                _, pr = claims[ci]
                _, img = imgs[ii]
                pr.images = [img.data_url]
                pr.image_meta = [img.to_dict()]
                pr.image_quality = img.quality
                report.images_mapped += 1

        # ---- In-document duplicate SKU resolution (a SKU can legitimately
        # reappear on a later page as a cross-reference / "compatible with"
        # mention, usually without its own price). Never guess which
        # occurrence is authoritative:
        #   - if exactly one occurrence carries a real MRP, that one wins,
        #     the priceless mentions are dropped (they were never a
        #     separate sellable line to begin with);
        #   - if more than one occurrence carries a DIFFERENT real MRP for
        #     the same SKU, that's a genuine source-file conflict — flag
        #     every occurrence and let the certifier / human decide, never
        #     silently pick one.
        by_sku: dict[str, list[ProductRow]] = defaultdict(list)
        for r in rows:
            by_sku[r.sku].append(r)
        deduped_rows: list[ProductRow] = []
        for sku, group in by_sku.items():
            if len(group) == 1:
                deduped_rows.append(group[0])
                continue
            priced = [g for g in group if g.mrp != MISSING]
            distinct_prices = {g.mrp for g in priced}
            if len(distinct_prices) > 1:
                for g in group:
                    g.confidence = min(g.confidence, 0.4)
                    g.issues.append(
                        f"Conflict: SKU {sku!r} appears {len(group)}x in the supplier file "
                        f"with different prices {sorted(distinct_prices)} — needs manual review"
                    )
                deduped_rows.extend(group)
            elif priced:
                deduped_rows.append(priced[0])
            else:
                deduped_rows.append(group[0])
        rows = deduped_rows

        report.parsed_rows = len(rows)
        return rows, report
