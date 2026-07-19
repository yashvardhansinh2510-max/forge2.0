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
