# Oyster Brand Catalog Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import the "Oyster" sanitaryware brand (Brook CP Fittings collection) into the production BuildCon House catalog — 4 categories (Body Jet, Shower, Outlet/Hand Shower/Angle Valve, Basin Mixer), ~220 finish-variant products with embedded supplier photography — using the exact same `catalog_pipeline` architecture as Hansgrohe/Axor/Grohe/Vitra/Geberit.

**Architecture:** Add one new `BrandAdapter` (`OysterAdapter`) that parses the 4 source XLSX files and extracts embedded images via the existing `extract_images_from_xlsx_ex` engine — no new extraction code needed, Oyster's layout (one photo per data row, single "Product Image" column) matches the already-solved Hansgrohe case. Register it in the adapter registry and the HTTP import allowlist. Import via a new standalone script modeled byte-for-byte on the most rigorous existing precedent (`run_hansgrohe_batch.py`): pre-import integrity scan → DB snapshot backup → adapter extract → `certifier.validate()` → auto-accept → `orchestrator.import_accepted()` (which itself handles Brand/Category autocreate, dedupe-by-`(sku,brand_id)`, and Supabase image upload via `services/media_service.upload_and_register`) → post-import integrity diff → resumable manifest → QA report. Every write happens through the existing pipeline; nothing bypasses it.

**Tech Stack:** Python 3.14, FastAPI backend, MongoDB Atlas (Motor async driver), Supabase Storage (via `media_storage/supabase_driver.py`), openpyxl for XLSX parsing, pytest for tests.

## Global Constraints

- **No new storage pattern.** Products are flat `Product` documents (one per finish variant) grouped by a shared `family_key` string — there is no separate parent/variant collection in this codebase, despite the original brief's "Parent → Variants" wording. Follow the real, live architecture.
- **SKU scheme (user-confirmed):** slug-based, human-readable, deterministic: `OYSTER-{CATEGORY_COMPACT}-{FAMILY_COMPACT}-{FINISH_CODE}` (e.g. `OYSTER-BODYJET-WAVEJET-CR`). Same family+finish always regenerates the identical SKU, so re-running the import updates the existing row instead of duplicating it. This is necessary because **none of the 4 source files contain real manufacturer article numbers** — the Shower sheet's "Article No." column actually holds size text (e.g. "1000 x 700"), not a code; that text is recovered into the `dimensions` field instead of being discarded.
- **Category mapping is literal, one file = one category, no inference** (per the original brief: "Do not infer different categories unless the data explicitly requires it"). This means creating one new category `"Outlet / Hand Shower / Angle Valve"` even though the existing catalog already has finer-grained categories (`Angle Valve`, `Hand Showers`, `Spout`) used by other brands — a deliberate, documented divergence from the rest of the catalog's taxonomy, not an oversight.
- **`floor_id` defaults to `"first-floor"`** for every Oyster product/brand/category doc, matching 100% of existing brands. No floor override requested.
- **Never fabricate missing data.** Article Number, Material, Warranty, Product Group/Series, and Technical Information do not exist anywhere in these 4 source files — left `null`/`MISSING` on every row, not guessed. This is documented in the QA report, not silently dropped.
- **Finish normalization is an explicit lookup table**, not fuzzy regex guessing — the 4 files contain exactly 18 distinct raw finish strings (verified by direct inspection); any new/unrecognized string encountered at run time is flagged for manual review rather than silently mapped.
- **Production write safety gate:** the import script must support a `--dry-run` mode (extract + validate + certify only, zero DB/Supabase writes) that is run and reviewed before the real import (which writes directly to the live `buildcon_house` Atlas DB and the `forge-products` Supabase bucket).
- Reuse `catalog_pipeline.orchestrator.import_accepted()` for all writes — it already handles Brand/Category autocreate-or-reuse, `(sku, brand_id)` dedup (idempotent), and Supabase image upload via `services/media_service.upload_and_register`. Do not hand-roll any of this.

---

## File Structure

- **Create:** `backend/catalog_pipeline/adapters/oyster.py` — `OysterAdapter` class: filename→category mapping, finish normalization table, family/description parsing, deterministic SKU generation, row-anchored image extraction.
- **Modify:** `backend/catalog_pipeline/adapters/__init__.py` — register `"oyster": OysterAdapter` in `REGISTRY`.
- **Modify:** `backend/routes/catalog_import_routes.py` — add `"Oyster"` to `SUPPORTED_BRANDS` (enables the human-review HTTP upload flow for future Oyster file updates).
- **Create:** `backend/tests/unit/test_oyster_adapter.py` — unit tests for finish normalization, SKU/family_key determinism, filename→category mapping, and full `extract()` against a tiny synthetic in-memory workbook.
- **Create:** `backend/scripts/run_oyster_import.py` — standalone runner script (modeled on `run_hansgrohe_batch.py`): reads the 4 local source files, runs the full pipeline, supports `--dry-run`.
- **Output (generated by the script, not hand-written):** `memory/oyster_import_manifest.json` (resumability tracking), `memory/oyster_qa_report.json` / `.md` (deliverables summary).

---

### Task 1: OysterAdapter — category mapping, finish normalization, family/SKU generation

**Files:**
- Create: `backend/catalog_pipeline/adapters/oyster.py`
- Test: `backend/tests/unit/test_oyster_adapter.py`

**Interfaces:**
- Produces: `OysterAdapter` class (subclass of `catalog_pipeline.base.BrandAdapter`), plus module-level helpers `normalize_finish(raw: str) -> tuple[str|None, str|None, str|None]`, `sku_for(category_compact: str, family_name: str, finish_code: str) -> str`, `family_key_for(category_slug: str, family_name: str) -> str`, `category_from_filename(filename: str) -> tuple[str, str]` (raises `ValueError` on no match) — consumed by Task 3.

- [ ] **Step 1: Write the failing tests for finish normalization**

```python
# backend/tests/unit/test_oyster_adapter.py
from catalog_pipeline.adapters.oyster import normalize_finish, sku_for, family_key_for, category_from_filename


def test_normalize_finish_covers_all_known_supplier_variants():
    cases = {
        "CROME": "Chrome", "CHROME": "Chrome", "CEROME": "Chrome", "CEOME": "Chrome",
        "MAAT BLACK": "Matt Black", "MAAT BALCK": "Matt Black",
        "MATE BLACK": "Matt Black", "MATT BLACK": "Matt Black",
        "BRUSHED GOLD": "Brushed Gold", "Brushed\xa0GOLD": "Brushed Gold",
        "ROSE GOLD": "Rose Gold", "ROSE GOLD ": "Rose Gold",
        "BRUSHED ROSE GOLD": "Brushed Rose Gold", "BRUSHE ROSE GLOD": "Brushed Rose Gold",
        "Brushed ROSE\xa0GOLD": "Brushed Rose Gold",
        "BRUSHED GUN METAL": "Brushed Gun Metal", "Brushed GUN METAL": "Brushed Gun Metal",
        "GUN METAL": "Gun Metal",
    }
    for raw, expected_label in cases.items():
        label, code, note = normalize_finish(raw)
        assert label == expected_label, f"{raw!r} -> {label!r}, expected {expected_label!r}"
        assert code and code.isupper()


def test_normalize_finish_repairs_corrupted_merged_cell_values():
    # Two real cells in the source files literally contain "CROME+B3:E16" /
    # "CROME+B3:L44" — a corrupted merged-cell artifact. The finish name is
    # recoverable (everything before the "+"); flag it via the returned note.
    label, code, note = normalize_finish("CROME+B3:E16")
    assert label == "Chrome"
    assert code == "CR"
    assert note and "repaired" in note.lower()


def test_normalize_finish_flags_unrecognized_values_for_manual_review():
    label, code, note = normalize_finish("SOME NEW TYPO NOBODY HAS SEEN")
    assert label is None
    assert code is None
    assert note and "manual review" in note.lower()


def test_category_from_filename_matches_all_four_real_source_files():
    assert category_from_filename("OYSTER BODY JET.xlsx") == ("Body Jet", "BODYJET")
    assert category_from_filename("OYSTER SHOWER.xlsx") == ("Shower", "SHOWER")
    assert category_from_filename("OYSTER SPOUT&HS&ANGLE W& TIGGER.xlsx") == (
        "Outlet / Hand Shower / Angle Valve", "OUTLETHSANGLE",
    )
    assert category_from_filename("OYSTER BESIN MIXER.xlsx") == ("Basin Mixer", "BASINMIXER")


def test_category_from_filename_raises_on_unknown_file():
    import pytest
    with pytest.raises(ValueError):
        category_from_filename("some_unrelated_file.xlsx")


def test_sku_and_family_key_are_deterministic_across_calls():
    # Idempotency requirement: re-running the import must regenerate the
    # SAME sku/family_key for the same inputs, so orchestrator.import_accepted
    # updates the existing product instead of creating a duplicate.
    sku1 = sku_for("BODYJET", "Brook CP Fittings WAVE JET", "CR")
    sku2 = sku_for("BODYJET", "Brook CP Fittings WAVE JET", "CR")
    assert sku1 == sku2 == "OYSTER-BODYJET-BROOKCPFITTINGSWAVEJET-CR"

    fk1 = family_key_for("body-jet", "Brook CP Fittings WAVE JET")
    fk2 = family_key_for("body-jet", "Brook CP Fittings WAVE JET")
    assert fk1 == fk2 == "oyster:body-jet:brook-cp-fittings-wave-jet"


def test_sku_differs_by_finish_within_same_family():
    sku_chrome = sku_for("BODYJET", "Wave Jet", "CR")
    sku_black = sku_for("BODYJET", "Wave Jet", "MB")
    assert sku_chrome != sku_black
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_oyster_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'catalog_pipeline.adapters.oyster'`

- [ ] **Step 3: Write the adapter module (part 1 — mapping, normalization, SKU generation)**

```python
# backend/catalog_pipeline/adapters/oyster.py
"""OYSTER XLSX adapter (Brook CP Fittings collection, sold under the Oyster brand).

Ships as one workbook per category (Body Jet / Shower / Outlet+HS+Angle Valve /
Basin Mixer), single sheet each, one row per finish variant:

  Row 1  : title ("OYSTER <CATEGORY>")
  Row 2  : column headers (Sr. No., finishes, [Article No. — Shower only],
           Product Discription, Product Image, MRP, QTY, MRP TOTAL, DISCOUNT,
           <blank>, OFFER RATE, TOTAL)
  Row 3+ : one finish variant per row. The embedded product photo floats over
           the "Product Image" cell of that exact row — verified 1:1 row
           anchoring across all 4 files (no side-by-side finishes sharing a
           row, unlike Vitra), so row-only anchor matching (Hansgrohe-style)
           is safe here.

Rules:
* Category comes from the source FILENAME (one file = one category, per
  business rule) — never inferred from row content.
* Brand is always "Oyster"; collection is always "Brook" (the sub-line name
  embedded in every "Product Discription" cell, e.g. "Brook CP Fittings ...").
* "finishes" column is heavily typo'd by the supplier (CROME/CEROME/MAAT
  BALCK/etc.) — normalized via an explicit FINISH_LOOKUP table (not fuzzy
  regex) built from the 18 distinct raw strings actually observed across all
  4 files. Anything new is flagged for manual review, never guessed.
* No real manufacturer article numbers exist anywhere in these files. The
  Shower sheet's "Article No." column actually holds a size string (e.g.
  "1000 x 700"), not a code — recovered into `dimensions` instead of
  discarded. SKU is therefore synthesized, not supplier-provided:
  `OYSTER-{CATEGORY_COMPACT}-{FAMILY_COMPACT}-{FINISH_CODE}`, deterministic
  from category+family+finish so re-running the import always regenerates
  the same SKU (required for idempotency).
* Family key groups sibling finishes of the same product:
  `oyster:{category_slug}:{family_slug}`.
* "OFFER RATE" column is the dealer/selling price (supplier-computed as
  MRP × (1 − discount%); falls back to MRP when no discount was applied).
"""
from __future__ import annotations
import io
import re

from ..base import MISSING, BrandAdapter, ExtractionReport, ProductRow, dedupe_iter
from ..image_extractor import ExtractedImage, extract_images_from_xlsx_ex

BRAND = "Oyster"
COLLECTION_NAME = "Brook"

# Filename -> (category display name, compact SKU code). Order matters only
# in that patterns must stay mutually exclusive for the 4 real filenames.
FILE_TO_CATEGORY: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"body\s*jet", re.I), "Body Jet", "BODYJET"),
    (re.compile(r"shower", re.I), "Shower", "SHOWER"),
    (re.compile(r"spout|angle|tigger|hs\s*&", re.I), "Outlet / Hand Shower / Angle Valve", "OUTLETHSANGLE"),
    (re.compile(r"besin|basin", re.I), "Basin Mixer", "BASINMIXER"),
]

# Explicit lookup, not regex guessing — built from the 18 distinct raw
# "finishes" cell values actually present across all 4 Oyster files
# (verified by direct inspection before writing this table).
FINISH_LOOKUP: dict[str, tuple[str, str]] = {
    "CROME": ("Chrome", "CR"),
    "CHROME": ("Chrome", "CR"),
    "CEROME": ("Chrome", "CR"),
    "CEOME": ("Chrome", "CR"),
    "MAAT BLACK": ("Matt Black", "MB"),
    "MAAT BALCK": ("Matt Black", "MB"),
    "MATE BLACK": ("Matt Black", "MB"),
    "MATT BLACK": ("Matt Black", "MB"),
    "BRUSHED GOLD": ("Brushed Gold", "BG"),
    "ROSE GOLD": ("Rose Gold", "RG"),
    "BRUSHED ROSE GOLD": ("Brushed Rose Gold", "BRG"),
    "BRUSHE ROSE GLOD": ("Brushed Rose Gold", "BRG"),
    "BRUSHED GUN METAL": ("Brushed Gun Metal", "BGM"),
    "GUN METAL": ("Gun Metal", "GM"),
}


def category_from_filename(filename: str) -> tuple[str, str]:
    for pat, label, code in FILE_TO_CATEGORY:
        if pat.search(filename or ""):
            return label, code
    raise ValueError(f"Oyster adapter: cannot map filename {filename!r} to a known category")


def normalize_finish(raw: str) -> tuple[str | None, str | None, str | None]:
    """Returns (finish_label, finish_code, note). `note` is set either when a
    corrupted cell was repaired (informational) or when the value is
    unrecognized (needs manual review) — callers should surface it either
    way rather than silently swallowing it."""
    s = str(raw or "").replace("\xa0", " ")
    repaired_from = None
    if "+" in s:
        # Repairs the two known corrupted merged-cell artifacts in the
        # source files: "CROME+B3:E16" / "CROME+B3:L44" — everything before
        # the "+" is the real finish name.
        repaired_from = s
        s = s.split("+", 1)[0]
    s = re.sub(r"\s+", " ", s).strip().upper()
    hit = FINISH_LOOKUP.get(s)
    if hit:
        note = f"corrupted finish cell {repaired_from!r} repaired to {s!r}" if repaired_from else None
        return hit[0], hit[1], note
    return None, None, f"unrecognized finish {raw!r} — needs manual review"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _compact(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def family_key_for(category_slug: str, family_name: str) -> str:
    return f"oyster:{category_slug}:{_slug(family_name)}"


def sku_for(category_compact: str, family_name: str, finish_code: str) -> str:
    family_compact = _compact(family_name)[:32] or "FAMILY"
    return f"OYSTER-{category_compact}-{family_compact}-{finish_code}"
```

- [ ] **Step 4: Run tests to verify the mapping/normalization/SKU tests pass**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_oyster_adapter.py -v -k "not extract"`
Expected: PASS (the `extract()`-based test from Task 3 doesn't exist yet, so filter it out for now)

- [ ] **Step 5: Commit**

```bash
git add backend/catalog_pipeline/adapters/oyster.py backend/tests/unit/test_oyster_adapter.py
git commit -m "feat: add Oyster adapter category mapping, finish normalization, SKU generation"
```

---

### Task 2: OysterAdapter — description parsing, family grouping, and full extract()

**Files:**
- Modify: `backend/catalog_pipeline/adapters/oyster.py`
- Modify: `backend/tests/unit/test_oyster_adapter.py`

**Interfaces:**
- Consumes: `MISSING`, `BrandAdapter`, `ExtractionReport`, `ProductRow`, `dedupe_iter` from `catalog_pipeline.base`; `ExtractedImage`, `extract_images_from_xlsx_ex` from `catalog_pipeline.image_extractor` (both already used identically by `catalog_pipeline/adapters/hansgrohe.py`).
- Produces: `OysterAdapter.extract(data: bytes, filename: str) -> tuple[list[ProductRow], ExtractionReport]` — the `BrandAdapter` interface method, consumed by `orchestrator.run_pipeline()` and Task 5's runner script.

- [ ] **Step 1: Write the failing test for full extraction against a synthetic workbook**

```python
# Append to backend/tests/unit/test_oyster_adapter.py
import io
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage

from catalog_pipeline.adapters.oyster import OysterAdapter
from catalog_pipeline.base import MISSING


def _tiny_png_bytes() -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (200, 200), color=(120, 120, 120)).save(buf, format="PNG")
    return buf.getvalue()


def _build_body_jet_workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BODY JET"
    ws.append(["OYSTER BODY JET"])
    ws.append(["Sr.\nNo.", "finishes", "Product Discription", "Product Image", "MRP",
               "QTY", "MRP TOTAL", "DISCOUNT", None, "OFFER RATE", "TOTAL"])
    # One family ("Wave Jet"), two finishes — one WITH a discount/offer rate,
    # one WITHOUT (offer rate must fall back to MRP), one row has NO image.
    ws.append([1, "CROME", "Brook CP Fittings WAVE JET", None, 18500, None, 0, 50, 9250, 9250, 0])
    ws.append([2, "MAAT BALCK", "Brook CP Fittings WAVE JET", None, 19500, None, 0, None, 0, 19500, 0])
    # A second family with only one finish and no MRP (missing-data case).
    ws.append([3, "GUN METAL", "BROOK UP FITTINGS JET-X", None, None, None, 0, None, 0, 0, 0])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    # openpyxl doesn't easily re-embed a floating image keyed to a specific
    # cell through the public API after save+reload in one step here, so this
    # fixture builds the image via a second pass using openpyxl's own
    # add_image on row 3 (Sr.No.=1) only, leaving rows 4 and 5 imageless —
    # exactly mirroring the real Basin Mixer/Shower files' "a few rows have
    # no image" reality.
    wb2 = Workbook()
    ws2 = wb2.active
    ws2.title = "BODY JET"
    for row in ws.iter_rows(values_only=True):
        ws2.append(list(row))
    img = XLImage(io.BytesIO(_tiny_png_bytes()))
    img.anchor = "D3"  # row 3 = first data row (Sr.No.=1, CROME)
    ws2.add_image(img)
    out = io.BytesIO()
    wb2.save(out)
    return out.getvalue()


def test_extract_groups_variants_into_one_family_and_generates_stable_skus():
    data = _build_body_jet_workbook()
    adapter = OysterAdapter()
    rows, report = adapter.extract(data, "OYSTER BODY JET.xlsx")

    assert report.parsed_rows == 3
    wave_jet_rows = [r for r in rows if "WAVE JET" in (r.description or "")]
    assert len(wave_jet_rows) == 2
    assert wave_jet_rows[0].family_key == wave_jet_rows[1].family_key == "oyster:body-jet:brook-cp-fittings-wave-jet"
    assert {r.finish for r in wave_jet_rows} == {"Chrome", "Matt Black"}
    assert len({r.sku for r in wave_jet_rows}) == 2  # different finishes -> different SKUs

    chrome_row = next(r for r in wave_jet_rows if r.finish == "Chrome")
    assert chrome_row.sku == "OYSTER-BODYJET-BROOKCPFITTINGSWAVEJET-CR"
    assert chrome_row.mrp == 18500.0
    assert chrome_row.dealer_price == 9250.0
    assert chrome_row.images  # image anchored at D3

    matt_black_row = next(r for r in wave_jet_rows if r.finish == "Matt Black")
    assert matt_black_row.dealer_price == 19500.0  # no discount -> falls back to MRP
    assert not matt_black_row.images  # no image anchored on this row
    assert "No image mapped" in " ".join(matt_black_row.issues)

    jetx_row = next(r for r in rows if "JET-X" in (r.description or ""))
    assert jetx_row.mrp == MISSING
    assert "Missing MRP" in jetx_row.issues


def test_extract_returns_empty_with_warning_for_unmappable_filename():
    data = _build_body_jet_workbook()
    adapter = OysterAdapter()
    rows, report = adapter.extract(data, "totally_unrelated.xlsx")
    assert rows == []
    assert report.warnings
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_oyster_adapter.py -v -k extract`
Expected: FAIL with `AttributeError: module 'catalog_pipeline.adapters.oyster' has no attribute 'OysterAdapter'`

- [ ] **Step 3: Append the family/description parser and `OysterAdapter.extract()` to the adapter module**

```python
# Append to backend/catalog_pipeline/adapters/oyster.py

# "Brook CP FITTINGS ..." / "BROOK UP FITINGS ..." prefix appears (with
# inconsistent spacing/typos) at the start of every "Product Discription"
# cell across all 4 files — strip it to get a clean family display name.
_COLLECTION_PREFIX_RE = re.compile(r"^\s*BROOK\s+(CP|UP)\s+FIT[TI]*INGS?\s*[-:]?\s*", re.I)


def _family_name(raw_description) -> str:
    """The Shower sheet ships a two-line description
    ("<collection line>\\n<product line>") for every row; the other 3 files
    ship one line with the "Brook CP/UP Fit(t)ings" prefix inline. Either
    way, strip the collection prefix to get the family display name."""
    s = str(raw_description or "").strip()
    if "\n" in s:
        _, _, rest = s.partition("\n")
        s = rest.strip() or s
    s = _COLLECTION_PREFIX_RE.sub("", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s or "Unnamed"


def _find_header_row(all_rows: list[list]) -> int:
    for i, r in enumerate(all_rows[:5]):
        cells = [str(c or "").lower().replace("\n", " ").strip() for c in r]
        if "finishes" in cells:
            return i
    return 1  # fallback: row 2 (0-indexed 1), the observed layout in all 4 files


def _build_col_map(header_row: list) -> dict[str, int]:
    col_map: dict[str, int] = {}
    for c, val in enumerate(header_row):
        key = str(val or "").lower().replace("\n", " ").strip()
        if not key:
            continue
        if key == "finishes":
            col_map["finish"] = c
        elif key.startswith("article"):
            # Shower-only column; its content is actually a size string
            # (e.g. "1000 x 700"), recovered into `dimensions`.
            col_map["article_no"] = c
        elif "discription" in key or "description" in key:
            col_map["description"] = c
        elif "image" in key:
            col_map["image"] = c
        elif key == "mrp":
            col_map["mrp"] = c
        elif key == "offer rate":
            col_map["offer_rate"] = c
    return col_map


class OysterAdapter(BrandAdapter):
    brand = BRAND
    supported_extensions = (".xlsx", ".xls")

    def extract(self, data: bytes, filename: str) -> tuple[list[ProductRow], ExtractionReport]:
        report = ExtractionReport(brand=self.brand, filename=filename, source_type="excel")
        rows: list[ProductRow] = []
        try:
            from openpyxl import load_workbook
        except Exception as e:  # pragma: no cover
            report.warnings.append(f"openpyxl missing: {e}")
            return rows, report

        try:
            category, category_code = category_from_filename(filename)
        except ValueError as e:
            report.warnings.append(str(e))
            return rows, report
        category_slug = _slug(category)

        try:
            wb = load_workbook(io.BytesIO(data), data_only=True)
        except Exception as e:
            report.warnings.append(f"xlsx open failed: {e}")
            return rows, report

        # Image mapping: one photo per data row — verified 1:1 across all 4
        # files (no side-by-side finishes sharing a row, unlike Vitra), so
        # row-only anchoring (Hansgrohe-style) is safe. Highest-quality
        # candidate wins if an anchor somehow has more than one blip.
        by_sheet_row: dict[tuple[str, int], ExtractedImage] = {}
        for sheet, row_idx, _col_idx, img in extract_images_from_xlsx_ex(data):
            key = (sheet, row_idx)
            prev = by_sheet_row.get(key)
            qrank = {"excellent": 4, "good": 3, "acceptable": 2, "poor": 1}
            if prev is None or (qrank.get(img.quality, 0), img.longest_edge) > (qrank.get(prev.quality, 0), prev.longest_edge):
                by_sheet_row[key] = img
        report.images_found = len(by_sheet_row)

        for ws in wb.worksheets:
            all_rows = [list(r) for r in ws.iter_rows(values_only=True)]
            if not all_rows:
                continue
            hdr_idx = _find_header_row(all_rows)
            col_map = _build_col_map(all_rows[hdr_idx])
            if not {"finish", "description", "mrp"} <= col_map.keys():
                report.warnings.append(
                    f"Sheet {ws.title!r} in {filename}: could not locate finish/description/MRP columns"
                )
                continue

            for r_idx, row in enumerate(all_rows[hdr_idx + 1:], start=hdr_idx + 2):
                desc_cell = row[col_map["description"]] if col_map["description"] < len(row) else None
                finish_cell = row[col_map["finish"]] if col_map["finish"] < len(row) else None
                if not desc_cell or not finish_cell:
                    continue  # blank / section / trailer row

                family_name = _family_name(desc_cell)
                finish_label, finish_code, finish_note = normalize_finish(finish_cell)

                mrp = self.to_number(row[col_map["mrp"]] if col_map["mrp"] < len(row) else None)
                offer_rate = self.to_number(
                    row[col_map["offer_rate"]] if "offer_rate" in col_map and col_map["offer_rate"] < len(row) else None
                )
                dealer_price = offer_rate if offer_rate not in (MISSING, None, 0) else mrp

                dimensions = MISSING
                if "article_no" in col_map:
                    art_cell = row[col_map["article_no"]] if col_map["article_no"] < len(row) else None
                    if art_cell:
                        dimensions = str(art_cell).strip()

                family_key = family_key_for(category_slug, family_name)
                sku = sku_for(category_code, family_name, finish_code) if finish_code else MISSING

                img = by_sheet_row.get((ws.title, r_idx))
                image_urls = [img.data_url] if img else []
                image_meta = [img.to_dict()] if img else []
                image_quality = img.quality if img else "missing"
                if img:
                    report.images_mapped += 1

                pr = ProductRow(
                    brand=self.brand,
                    sku=sku,
                    name=f"{family_name} - {finish_label}" if finish_label else family_name,
                    category=category,
                    subcategory=MISSING,
                    series=MISSING,
                    family_key=family_key,
                    variant=finish_label or MISSING,
                    finish=finish_label or MISSING,
                    finish_code=finish_code or MISSING,
                    colour=finish_label or MISSING,
                    material=MISSING,
                    dimensions=dimensions,
                    description=str(desc_cell).strip(),
                    mrp=mrp,
                    dealer_price=dealer_price,
                    warranty=MISSING,
                    collection=COLLECTION_NAME,
                    images=image_urls,
                    image_meta=image_meta,
                    image_quality=image_quality,
                    image_page=None,
                    specs={"collection": COLLECTION_NAME, "source_file": filename},
                    tags=dedupe_iter([
                        category.lower(), self.brand.lower(), COLLECTION_NAME.lower(), (finish_label or "").lower(),
                    ]),
                    confidence=0.94 if (finish_label and mrp != MISSING) else 0.5,
                )
                if not finish_label:
                    pr.issues.append(finish_note or f"Unrecognized finish {finish_cell!r} — needs manual review")
                elif finish_note:
                    pr.issues.append(finish_note)
                if mrp == MISSING:
                    pr.issues.append("Missing MRP")
                if not img:
                    pr.issues.append("No image mapped from supplier file")
                rows.append(pr)

        report.parsed_rows = len(rows)
        return rows, report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_oyster_adapter.py -v`
Expected: PASS (all tests from Task 1 and Task 2)

- [ ] **Step 5: Commit**

```bash
git add backend/catalog_pipeline/adapters/oyster.py backend/tests/unit/test_oyster_adapter.py
git commit -m "feat: implement Oyster adapter family grouping and full extract()"
```

---

### Task 3: Register the adapter in the pipeline and the HTTP import allowlist

**Files:**
- Modify: `backend/catalog_pipeline/adapters/__init__.py`
- Modify: `backend/routes/catalog_import_routes.py`
- Test: `backend/tests/unit/test_oyster_adapter_registration.py`

**Interfaces:**
- Consumes: `OysterAdapter` from Task 2.
- Produces: `catalog_pipeline.adapters.get_adapter("oyster")` returns `OysterAdapter`; `SUPPORTED_BRANDS` includes `"Oyster"` for the human-review upload endpoint.

- [ ] **Step 1: Write the failing registration test**

```python
# backend/tests/unit/test_oyster_adapter_registration.py
def test_oyster_adapter_is_registered():
    from catalog_pipeline.adapters import get_adapter
    from catalog_pipeline.adapters.oyster import OysterAdapter
    assert isinstance(get_adapter("oyster"), OysterAdapter)
    assert isinstance(get_adapter("Oyster"), OysterAdapter)  # registry lookup is case-insensitive


def test_oyster_is_in_supported_brands_for_http_upload():
    from routes.catalog_import_routes import SUPPORTED_BRANDS
    assert "Oyster" in SUPPORTED_BRANDS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_oyster_adapter_registration.py -v`
Expected: FAIL (adapter not in `REGISTRY`, `"Oyster"` not in `SUPPORTED_BRANDS`)

- [ ] **Step 3: Register the adapter**

Read `backend/catalog_pipeline/adapters/__init__.py` first to confirm the exact current `REGISTRY` dict literal before editing (it was, at research time: `{"grohe": GroheAdapter, "geberit": GeberitAdapter, "vitra": VitraAdapter, "hansgrohe": HansgroheAdapter, "axor": HansgroheAdapter}`), then add the import and entry:

```python
# backend/catalog_pipeline/adapters/__init__.py — add alongside the existing imports
from .oyster import OysterAdapter
```

```python
# and add to the REGISTRY dict literal:
    "oyster": OysterAdapter,
```

- [ ] **Step 4: Add "Oyster" to the HTTP upload allowlist**

In `backend/routes/catalog_import_routes.py`, locate `SUPPORTED_BRANDS = [...]` (confirmed at research time to read `["Hansgrohe", "Axor", "Grohe", "Vitra", "Geberit"]`) and add the new entry:

```python
SUPPORTED_BRANDS = ["Hansgrohe", "Axor", "Grohe", "Vitra", "Geberit", "Oyster"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_oyster_adapter_registration.py backend/tests/unit/test_oyster_adapter.py -v`
Expected: PASS

- [ ] **Step 6: Run the full existing unit suite to confirm no regression**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit -v`
Expected: PASS (all pre-existing tests plus the new Oyster ones)

- [ ] **Step 7: Commit**

```bash
git add backend/catalog_pipeline/adapters/__init__.py backend/routes/catalog_import_routes.py backend/tests/unit/test_oyster_adapter_registration.py
git commit -m "feat: register Oyster adapter in pipeline registry and HTTP import allowlist"
```

---

### Task 4: Standalone import runner script with dry-run mode

**Files:**
- Create: `backend/scripts/run_oyster_import.py`

**Interfaces:**
- Consumes: `OysterAdapter` (Task 2), `catalog_pipeline.certifier.validate`, `catalog_pipeline.orchestrator.import_accepted`, `catalog_pipeline.integrity_guard.scan_catalog`, `scripts.backup_db.backup`, `db.db`, `models.CatalogImportJob`.
- Produces: CLI script runnable as `python scripts/run_oyster_import.py --dry-run` (extract+validate+certify only, zero writes) or `python scripts/run_oyster_import.py` (full import); writes `memory/oyster_import_manifest.json` and `memory/oyster_qa_report.json`/`.md`.

- [ ] **Step 1: Write the script**

This mirrors `run_hansgrohe_batch.py`'s structure exactly (pre-import integrity scan → backup → per-file extract → validate → auto-accept → job persist → `import_accepted` → post-import integrity diff → manifest → report), adapted to read local files instead of downloading by URL, and adding the `--dry-run` gate the Global Constraints require.

```python
# backend/scripts/run_oyster_import.py
"""Oyster brand batch importer — processes the 4 Oyster category files
(Body Jet, Shower, Outlet/Hand Shower/Angle Valve, Basin Mixer) idempotently,
tracking progress in memory/oyster_import_manifest.json so re-running never
reprocesses an already-completed file.

Usage:
    python scripts/run_oyster_import.py --dry-run   # extract+validate+certify only, NO db writes
    python scripts/run_oyster_import.py              # full import (writes to Mongo + Supabase)
"""
from __future__ import annotations
import argparse
import asyncio
import json
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from catalog_pipeline.adapters.oyster import OysterAdapter  # noqa: E402
from catalog_pipeline.certifier import validate  # noqa: E402
from catalog_pipeline.base import MISSING  # noqa: E402
from catalog_pipeline.orchestrator import import_accepted  # noqa: E402
from catalog_pipeline.integrity_guard import scan_catalog  # noqa: E402
from db import db  # noqa: E402
from models import CatalogImportJob  # noqa: E402
from backup_db import backup as backup_db  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "memory" / "oyster_import_manifest.json"
REPORT_PATH = REPO_ROOT / "memory" / "oyster_qa_report.json"

# Local absolute paths to the 4 source files (WhatsApp-forwarded, not tracked
# in the repo). Each maps 1:1 to a category — see oyster.py FILE_TO_CATEGORY.
SOURCE_FILES = [
    "/Users/yashvardhansinhjhala/Library/Containers/net.whatsapp.WhatsApp/Data/tmp/documents/B1E380AC-8A21-45BD-8C12-15C4A6F54C43/OYSTER BODY JET.xlsx",
    "/Users/yashvardhansinhjhala/Library/Containers/net.whatsapp.WhatsApp/Data/tmp/documents/F2E32EBF-98EE-467D-B3FD-548197F58C13/OYSTER SHOWER.xlsx",
    "/Users/yashvardhansinhjhala/Library/Containers/net.whatsapp.WhatsApp/Data/tmp/documents/26A837B9-F18D-463C-854F-D3638C3A49DD/OYSTER SPOUT&HS&ANGLE W& TIGGER.xlsx",
    "/Users/yashvardhansinhjhala/Library/Containers/net.whatsapp.WhatsApp/Data/tmp/documents/3B5CD583-BE86-4304-884E-1A7DE7FFBEBD/OYSTER BESIN MIXER.xlsx",
]


def _norm(path: str) -> str:
    return Path(path).stem.strip().lower().replace(" ", "_")


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"processed_files": [], "batches": []}


def _save_manifest(m: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(m, indent=2), encoding="utf-8")


def _auto_accept(row_objs):
    for r in row_objs:
        if (
            r.status == "pending"
            and r.confidence >= 0.85
            and r.sku not in (MISSING, None)
            and r.mrp not in (MISSING, None)
            and r.category not in (MISSING, None)
        ):
            r.status = "accepted"
    return row_objs


async def main(dry_run: bool) -> None:
    t0 = time.time()
    manifest = _load_manifest()
    already_done = set(manifest["processed_files"])

    to_process = [f for f in SOURCE_FILES if _norm(f) not in already_done]
    already_skipped = [f for f in SOURCE_FILES if _norm(f) in already_done]

    if not dry_run:
        pre_report = await scan_catalog()
        if not pre_report.ok:
            print("ABORTING — catalog integrity check FAILED before this import even started.")
            print(json.dumps(pre_report.to_public(), indent=2))
            raise SystemExit(1)
        print(f"Pre-import integrity check: PASS ({pre_report.total_products} products)")

        pre_snapshot_dir = await backup_db(["products", "product_media", "brands", "categories"])
        print(f"Pre-import snapshot: {pre_snapshot_dir}")

    adapter = OysterAdapter()
    all_rows = []
    per_file: list[dict] = []
    errors: list[str] = []

    for path in to_process:
        filename = Path(path).name
        try:
            data = Path(path).read_bytes()
        except Exception as e:
            errors.append(f"{filename}: read failed - {e}")
            continue
        try:
            rows, rep = adapter.extract(data, filename)
        except Exception as e:
            errors.append(f"{filename}: extraction failed - {e}")
            continue
        all_rows.extend(rows)
        per_file.append({
            "file": filename, "rows": rep.parsed_rows,
            "images_found": rep.images_found, "images_mapped": rep.images_mapped,
            "warnings": rep.warnings,
        })
        print(f"[{filename}] rows={rep.parsed_rows} images_mapped={rep.images_mapped}/{rep.images_found}")

    if not all_rows:
        print("Nothing new to process.")
        return

    row_objs, cert = validate(all_rows)
    row_objs = _auto_accept(row_objs)
    all_rows_dicts = [r.to_public() for r in row_objs]
    accepted = sum(1 for r in all_rows_dicts if r.get("status") == "accepted")
    rejected = sum(1 for r in all_rows_dicts if r.get("status") == "rejected")
    needs_review = [r for r in all_rows_dicts if r.get("status") == "pending"]

    summary = {
        "mode": "dry-run" if dry_run else "import",
        "files_processed": [Path(f).name for f in to_process],
        "already_done_skipped": [Path(f).name for f in already_skipped],
        "per_file": per_file,
        "total_rows": len(all_rows_dicts),
        "accepted": accepted,
        "rejected_true_duplicates": rejected,
        "needs_manual_review": len(needs_review),
        "needs_manual_review_detail": [
            {"sku": r.get("sku"), "description": r.get("description"), "issues": r.get("issues")}
            for r in needs_review
        ],
        "certification": cert.to_public(),
        "errors": errors,
        "runtime_s": round(time.time() - t0, 1),
    }

    if dry_run:
        print("\n" + "=" * 70)
        print("DRY RUN — no database or storage writes performed")
        print("=" * 70)
        print(json.dumps(summary, indent=2, default=str)[:20000])
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"\nFull dry-run report written to {REPORT_PATH}")
        return

    owner = await db.users.find_one({"email": "owner@forge.app"}, {"id": 1, "_id": 0})
    cats_before = {c["name"] for c in await db.categories.find({}, {"_id": 0, "name": 1}).to_list(200)}

    job = CatalogImportJob(
        filename=f"Oyster batch ({len(to_process)} files)",
        source_type="excel",  # type: ignore[arg-type]
        supplier_name="Oyster",
        total_rows=len(all_rows_dicts),
        accepted_rows=accepted,
        rejected_rows=rejected,
        status="classified",  # type: ignore[arg-type]
        rows=all_rows_dicts,
        created_by=(owner or {}).get("id", "system"),
    )
    doc = job.dict()
    doc["extraction"] = {"per_file": per_file}
    doc["certification"] = cert.to_public()
    await db.catalog_imports.insert_one(doc)
    doc.pop("_id", None)

    stats = {"imported": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
    if accepted:
        stats = await import_accepted(doc, (owner or {}).get("id", "system"))
        await db.catalog_imports.update_one(
            {"id": doc["id"]},
            {"$set": {"status": "imported", "accepted_rows": stats["imported"] + stats["updated"],
                      "rejected_rows": stats["skipped"]}},
        )

    cats_after = {c["name"] for c in await db.categories.find({}, {"_id": 0, "name": 1}).to_list(200)}
    missing_images = sum(1 for r in all_rows_dicts if r.get("status") == "accepted" and not r.get("images"))

    manifest["processed_files"].extend(_norm(f) for f in to_process)
    manifest["batches"].append({
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": [Path(f).name for f in to_process],
        "stats": stats,
    })
    _save_manifest(manifest)

    post_report = await scan_catalog(baseline_snapshot_dir=str(pre_snapshot_dir))
    integrity_ok = post_report.ok
    post_snapshot_dir = await backup_db(
        ["products", "product_media", "brands", "categories", "customers",
         "quotations", "purchase_orders", "payments", "followups", "users", "suppliers"]
    )

    summary.update({
        "batch_result": "SUCCESS" if integrity_ok else "FAILED — INTEGRITY VIOLATION, MANUAL REVIEW REQUIRED",
        "categories_created": sorted(cats_after - cats_before),
        "products_imported": stats["imported"],
        "products_updated": stats["updated"],
        "products_skipped": stats["skipped"],
        "import_errors": stats.get("errors", []),
        "missing_images": missing_images,
        "pre_import_snapshot": str(pre_snapshot_dir),
        "post_import_snapshot": str(post_snapshot_dir),
        "integrity_guard": post_report.to_public(),
    })
    print("\n" + "=" * 70)
    print(f"IMPORT REPORT — {summary['batch_result']}")
    print("=" * 70)
    print(json.dumps(summary, indent=2, default=str)[:20000])

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    if not integrity_ok:
        print(f"\n!!! INTEGRITY GUARD FAILED — restore from {pre_snapshot_dir} if needed. !!!")
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Extract+validate+certify only, no DB/storage writes")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
```

- [ ] **Step 2: Verify the script imports cleanly**

Run: `cd "backend" && .venv/bin/python -c "import ast; ast.parse(open('scripts/run_oyster_import.py').read())"`
Expected: no output (valid syntax)

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/run_oyster_import.py
git commit -m "feat: add Oyster batch import runner with dry-run mode"
```

---

### Task 5: Dry run against the real 4 files — produce and review the validation summary

**Files:** none (execution only)

**Interfaces:**
- Consumes: `run_oyster_import.py` from Task 4 against the real files listed in `SOURCE_FILES`.
- Produces: `memory/oyster_qa_report.json` — the validation summary the original brief requires before any insert.

- [ ] **Step 1: Run the dry-run**

Run: `cd "backend" && .venv/bin/python scripts/run_oyster_import.py --dry-run`
Expected: exits 0, prints a JSON summary, writes `memory/oyster_qa_report.json`. Confirm:
- `total_rows` ≈ 220 (24 Body Jet + 88 Shower + 52 Outlet/HS/Angle + 56 Basin Mixer)
- `certification.duplicates_sku` == 0 (SKU scheme is deterministic per family+finish; a nonzero count here means two different families collapsed onto the same slug and needs the `_family_compact` truncation length revisited)
- `needs_manual_review_detail` lists only rows with genuinely unrecognized finish strings (should be empty, since Task 1's `FINISH_LOOKUP` covers all 18 observed variants) or missing MRP
- `missing_images` matches the known gaps found during source-file inspection (1 row in Shower, 3 rows in Basin Mixer)

- [ ] **Step 2: Present the summary to the user for explicit go-ahead**

This is a production database + storage write about to happen — per the plan's safety gate, do not proceed to Task 6 without the user confirming the dry-run numbers look right (especially: correct total product count, zero unexpected duplicate SKUs, and an acceptable missing-image count).

---

### Task 6: Execute the real import (writes to production Mongo + Supabase)

**Files:** none (execution only) — gated on explicit user confirmation from Task 5.

- [ ] **Step 1: Run the real import**

Run: `cd "backend" && .venv/bin/python scripts/run_oyster_import.py`
Expected: exits 0, `batch_result: "SUCCESS"`, writes `memory/oyster_qa_report.json` and `memory/oyster_import_manifest.json`. If it exits 1 with `INTEGRITY VIOLATION`, stop and investigate before re-running — do not re-run blindly, since the manifest already marks processed files as done and a second run will only touch newly-added files.

- [ ] **Step 2: Commit the generated manifest/report**

```bash
git add memory/oyster_import_manifest.json memory/oyster_qa_report.json
git commit -m "chore: record Oyster brand import manifest and QA report"
```

---

### Task 7: Post-import verification and deliverables summary

**Files:** none (verification only)

- [ ] **Step 1: Verify counts directly against MongoDB**

```python
# one-off verification, run via: .venv/bin/python - <<'EOF' (paste below)
import asyncio, os
from pymongo import MongoClient

env = {}
with open("backend/.env") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k] = v.strip().strip('"').strip("'")

client = MongoClient(env["MONGO_URL"])
db = client[env["DB_NAME"]]
brand = db.brands.find_one({"name": "Oyster"})
assert brand, "Oyster brand was not created"
print("Brand:", brand["id"])
product_count = db.products.count_documents({"brand_id": brand["id"]})
print("Products:", product_count)
media_count = db.product_media.count_documents({"brand_id": brand["id"]})
print("Media rows:", media_count)
families = db.products.distinct("family_key", {"brand_id": brand["id"]})
print("Families:", len(families))
missing_img = db.products.count_documents({"brand_id": brand["id"], "image_quality": "missing"})
print("Products with no image:", missing_img)
dupe_check = list(db.products.aggregate([
    {"$match": {"brand_id": brand["id"]}},
    {"$group": {"_id": "$sku", "n": {"$sum": 1}}},
    {"$match": {"n": {"$gt": 1}}},
]))
print("Duplicate SKUs:", len(dupe_check))
```

Expected: `product_count` ≈ accepted rows from Task 6's report; `Duplicate SKUs` == 0; `media_count` > 0 and roughly matches `images_mapped` totals from the dry run minus the known missing-image rows.

- [ ] **Step 2: Verify at least one image URL is publicly reachable**

Run (replace with a real `public_url` read from `db.product_media.find_one({"brand_id": <oyster_id>})`):
`curl -sI "<public_url>" | head -1`
Expected: `HTTP/2 200`

- [ ] **Step 3: Make new products visible to search/listing**

The `catalog_service` in-memory snapshot cache lives inside the *running backend process*, not in this standalone script — the script talked directly to MongoDB, so the live snapshot cache doesn't know new data landed until its own 300-second staleness timer fires on the next request, or the backend process restarts. Restart the backend (or wait 5 minutes) before verifying search in the browser:

Check what's currently running: `curl 127.0.0.1:8010/api/health`. If a uvicorn process is already up, restart it via whatever mechanism started it (e.g. `.claude/launch.json`'s configured process), or simply wait 5 minutes and re-check.

- [ ] **Step 4: Verify search/filters/quotation builder in the browser**

Use the Browser pane: start the frontend dev server, log in, open Catalog, search "Oyster", filter by brand=Oyster and by each of the 4 new categories, open a product with multiple finishes and confirm the variant swatches show each finish's own photo (not a sibling's — this is a documented past bug class per `test_catalog_variant_image_contamination.py`), and add one Oyster product to a new quotation via the Quotation Builder to confirm it's selectable there too.

- [ ] **Step 5: Write the deliverables summary**

Compose the final summary (products imported, parent families, variants/finishes, images uploaded, categories created vs. reused, duplicates skipped, validation warnings, any rows flagged for manual review) directly from `memory/oyster_qa_report.json` — every number in the deliverable must trace back to that file, not be re-estimated.

---

## Self-Review

**1. Spec coverage:**
- MongoDB Brand/Category/Product/ProductVariant/media, UUID conventions, indexes → Task 3 registration + Task 6 import reuses `orchestrator.import_accepted()` verbatim, which already handles all of this per the real (not literal-spec) architecture documented in Global Constraints.
- Supabase storage, existing bucket/folder structure → handled automatically by `services/media_service.upload_and_register()`, invoked inside `orchestrator._upload_supplier_images()` — no new code needed, covered by reusing `import_accepted`.
- Per-category file separation, no cross-category inference → Task 1's `FILE_TO_CATEGORY` filename-only mapping.
- Article Number / MRP / Dealer Price / Finish / Family / Dimensions / Technical Info extraction, "never discard without documenting" → Task 2's `extract()` (dealer_price from OFFER RATE with MRP fallback, dimensions recovered from the mislabeled Shower "Article No." column, absent fields left `MISSING` and surfaced via `issues`).
- Parent/variant/finish-variant structure → Global Constraints documents the real flat-product-plus-`family_key` architecture as the faithful equivalent; Task 2's tests assert family grouping.
- Image extraction (no screenshots/manual crop, preserve aspect ratio, highest quality) → reuses `extract_images_from_xlsx_ex`, the exact same engine Hansgrohe/Vitra use, already handling quality classification and re-optimization.
- Category dedup (create only if missing) → handled inside `orchestrator.import_accepted()`'s category-by-name lookup, exercised in Task 6.
- Brand dedup → same, via `import_accepted()`'s brand-by-name lookup.
- Validation before insert (duplicate article numbers, missing prices/descriptions/finishes/images) → `certifier.validate()`, surfaced in Task 5's dry run.
- Transactional/resumable/idempotent import → snapshot-based rollback (`orchestrator.rollback_job`, already existing, not reinvoked unless something goes wrong), manifest-based file-level resumability (Task 4), and deterministic SKU-based idempotency (Task 1) so re-running never duplicates.
- Search/filters/quotation builder work without manual steps → Task 7 Step 3 addresses the one real gap found (in-memory snapshot staleness for script-driven imports) and Step 4 verifies it live.
- Verification (counts, missing images/prices, duplicate SKUs, broken URLs) → Task 7 Steps 1–2.
- Deliverables summary → Task 7 Step 5.
- "Improve the importer rather than hard-code brand-specific logic" → the only genuinely new code is the adapter (matching the established one-adapter-per-brand convention used by all 4 existing brands) plus two one-line registry additions; no ad-hoc bypass of `orchestrator`/`certifier`/`integrity_guard` anywhere.

**2. Placeholder scan:** No TBD/TODO markers; every step has complete, runnable code or an exact command with expected output.

**3. Type consistency:** `normalize_finish` → `(label, code, note)` tuple used consistently in Task 1 tests and Task 2's `extract()`. `category_from_filename` → `(label, code)` tuple used consistently. `sku_for(category_compact, family_name, finish_code)` and `family_key_for(category_slug, family_name)` signatures match between Task 1's definition and Task 2's call sites.
