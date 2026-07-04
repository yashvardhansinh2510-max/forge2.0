"""Framework helpers shared by every brand adapter (Iteration 2A).

Ruleset
-------
Every adapter uses these resolvers so hierarchy, finish, and image quality
tagging behave identically across suppliers. That is the whole point of the
framework: adding a new brand only requires a `SupplierManifest` + a small
adapter that reads the supplier's file layout.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .base import ALLOWED_CATEGORIES, MISSING


# ---------------------------------------------------------------------------
# Category classification
# ---------------------------------------------------------------------------
_DEFAULT_DETAIL_PRIORITY: list[tuple[str, str]] = [
    ("bidet",     "Bidets"),
    ("urinal",    "Urinals"),
    ("shower",    "Showers"),
    ("bathtub",   "Bathtubs"),
    ("tub",       "Bathtubs"),
    ("cistern",   "Concealed Cisterns"),
    ("flush",     "Flush Plates"),
    ("mixer",     "Faucets"),
    ("faucet",    "Faucets"),
    ("tap",       "Faucets"),
    ("basin",     "Basins"),
    ("washbasin", "Basins"),
    ("counter",   "Basins"),
    ("vanity",    "Basins"),
    ("sink",      "Kitchen Sinks"),
    ("wc",        "Water Closets"),
    ("toilet",    "Water Closets"),
    ("closet",    "Water Closets"),
    ("accessor",  "Accessories"),
]


def classify_category(detail: str, *, section: str = "", extra_rules: Optional[list[tuple[str, str]]] = None) -> str:
    """Return an ALLOWED_CATEGORIES label. Never fabricates — returns MISSING
    when nothing matches.

    Args:
        detail: primary text describing the row (e.g. Vitra 'Detail' column,
            Grohe product family name).
        section: optional supplier section / sheet / page label used as a
            weaker fallback signal (e.g. 'CSW', 'Kitchen', 'Bathroom').
        extra_rules: brand-specific `(keyword, category)` overrides applied
            with higher priority than the default rules.
    """
    haystack = (detail or "").lower()
    rules = list(extra_rules or []) + _DEFAULT_DETAIL_PRIORITY
    for kw, cat in rules:
        if kw in haystack:
            return cat
    # Section fallback
    sec = (section or "").lower()
    for kw, cat in rules:
        if kw in sec:
            return cat
    return MISSING


# ---------------------------------------------------------------------------
# Subcategory extraction
# ---------------------------------------------------------------------------
_DEFAULT_SUBCATEGORY_KEYWORDS: list[str] = [
    "Wall Hung WC", "Back to Wall WC", "Rimless WC", "Rim-Ex WC", "One-Piece WC",
    "Wall Hung Bidet", "Floor Bidet",
    "Console Basin", "Vanity Basin", "Countertop Basin",
    "Under Counter Basin", "Wall Hung Basin", "Semi-Recessed Basin",
    "Concealed Cistern", "Exposed Cistern", "Actuator Plate", "Flush Plate",
    "Wall Hung Urinal", "Floor Urinal",
    "Single Lever Basin Mixer", "Basin Mixer", "Wall Mixer",
    "Kitchen Mixer", "Sink Mixer",
    "Bath Mixer", "Shower Mixer", "Thermostatic Mixer",
    "Rain Shower", "Hand Shower", "Shower Head", "Shower Set",
    "Freestanding Bathtub", "Built-in Bathtub", "Whirlpool",
    "Kitchen Sink", "Single Bowl Sink", "Double Bowl Sink",
]


def extract_subcategory(
    detail: str, category: str, *, section: str = "",
    keywords: Optional[list[str]] = None,
) -> str:
    """Best-effort subcategory. Priority:

    1. Keyword match against controlled `keywords`.
    2. Cleaned-up form of `detail` if it looks like a product-form label
       (all letters, 3-30 chars, no digits).
    3. `category` itself.
    4. MISSING.
    """
    hay = f"{section} {detail}"
    kws = keywords or _DEFAULT_SUBCATEGORY_KEYWORDS
    for kw in kws:
        if kw.lower() in hay.lower():
            return kw
    d = (detail or "").strip()
    letters = sum(1 for c in d if c.isalpha())
    if 3 <= len(d) <= 30 and letters >= 3 and not any(c.isdigit() for c in d):
        return d.title()
    if category and category != MISSING:
        return category
    return MISSING


# ---------------------------------------------------------------------------
# Finish resolution
# ---------------------------------------------------------------------------
_FINISH_CODE_RE = re.compile(r"\b(\d{2,4})\b")

# Curated normalisation table — add new codes here as brands are onboarded.
_FINISH_ALIASES: dict[str, tuple[str, str]] = {
    # (canonical_finish, colour)
    "chrome":       ("Chrome", "Chrome"),
    "matt chrome":  ("Matt Chrome", "Chrome"),
    "brushed chrome":("Brushed Chrome", "Chrome"),
    "black":        ("Matt Black", "Black"),
    "matt black":   ("Matt Black", "Black"),
    "gloss black":  ("Gloss Black", "Black"),
    "white":        ("White", "White"),
    "matt white":   ("Matt White", "White"),
    "stone grey":   ("Matt Stone Grey", "Grey"),
    "matt stone grey":("Matt Stone Grey", "Grey"),
    "taupe":        ("Matt Taupe", "Taupe"),
    "matt taupe":   ("Matt Taupe", "Taupe"),
    "brass":        ("Brushed Brass", "Brass"),
    "brushed brass":("Brushed Brass", "Brass"),
    "gold":         ("Polished Gold", "Gold"),
    "polished gold":("Polished Gold", "Gold"),
    "nickel":       ("Brushed Nickel", "Nickel"),
    "brushed nickel":("Brushed Nickel", "Nickel"),
    "copper":       ("Brushed Copper", "Copper"),
    "bronze":       ("Bronze", "Bronze"),
    "steel":        ("Stainless Steel", "Steel"),
    "stainless":    ("Stainless Steel", "Steel"),
}


@dataclass
class ResolvedFinish:
    label: str = MISSING       # canonical finish, e.g. "Matt Black"
    colour: str = MISSING      # canonical colour token, e.g. "Black"
    code: str = MISSING        # supplier finish code (e.g. "483")

    @property
    def is_missing(self) -> bool:
        return self.label == MISSING and self.code == MISSING


def resolve_finish(raw: str) -> ResolvedFinish:
    """Normalise a supplier finish label into (finish, colour, code).

    Accepts strings like:
        "MATT BLACK 483", "Chrome", "WHITE 003/403", "Brushed Brass".
    Never fabricates data — unknown finishes flow through unchanged but the
    canonical `label` still holds the raw text (title-cased) for display.
    """
    if not raw:
        return ResolvedFinish()
    raw_s = str(raw).strip()
    if not raw_s:
        return ResolvedFinish()

    code_match = _FINISH_CODE_RE.search(raw_s)
    code = code_match.group(1) if code_match else MISSING

    text = _FINISH_CODE_RE.sub("", raw_s).strip(" /,-").lower()
    if text in _FINISH_ALIASES:
        label, colour = _FINISH_ALIASES[text]
        return ResolvedFinish(label=label, colour=colour, code=code)
    # Substring match fallback
    for key, (label, colour) in _FINISH_ALIASES.items():
        if key in text:
            return ResolvedFinish(label=label, colour=colour, code=code)
    # Unknown finish — keep raw label (title-cased), no colour fabricated.
    return ResolvedFinish(
        label=text.title() if text else MISSING,
        colour=MISSING,
        code=code,
    )


# ---------------------------------------------------------------------------
# Family key builder
# ---------------------------------------------------------------------------
def make_family_key(*parts: str) -> str:
    """Deterministic family key. All parts are slugified and joined by ':'.

    Example:
        make_family_key("vitra", "csw", "metropole", "wall hung wc")
        -> "vitra:csw:metropole:wall-hung-wc"
    """
    def _slug(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "_"
    return ":".join(_slug(p) for p in parts if p and p != MISSING)


# ---------------------------------------------------------------------------
# Supplier Manifest — declarative config for a brand adapter
# ---------------------------------------------------------------------------
@dataclass
class SupplierManifest:
    """Declarative description of a supplier's catalogue.

    Concrete adapters read this manifest to drive their parsing, so onboarding
    a new brand is (usually) a matter of writing a manifest + a slim
    file-format-specific parser.
    """
    brand: str                                     # "Vitra", "Grohe", "Geberit"
    slug: str                                      # "vitra"
    source_format: str = "excel"                   # excel | pdf | csv
    supported_extensions: tuple[str, ...] = (".xlsx",)

    # Category classification
    category_overrides: list[tuple[str, str]] = field(default_factory=list)
    subcategory_keywords: Optional[list[str]] = None

    # Column mapping (Excel adapters)
    columns: dict[str, Any] = field(default_factory=dict)

    # Finish handling
    finish_column_pattern: Optional[str] = None    # regex for spotting finish headers

    # Pricing
    price_field: str = "mrp"                       # or "dealer_price"
    currency: str = "INR"

    # Image extraction
    image_min_edge: int = 240                       # minimum longest-edge to accept
    accept_wmf_emf: bool = True

    # Row filter
    sku_regex: str = r"[A-Z0-9\-]+"

    # Adapter-specific extras
    extras: dict[str, Any] = field(default_factory=dict)


SUPPLIER_MANIFESTS: dict[str, SupplierManifest] = {
    "vitra": SupplierManifest(
        brand="Vitra",
        slug="vitra",
        source_format="excel",
        supported_extensions=(".xlsx", ".xls"),
        category_overrides=[],                       # default rules cover Vitra fully
        columns={
            "design_col": 0,           # Column A — series/design
            "detail_col": 1,           # Column B — detail / form
            "header_row": 0,           # 0-indexed row with finish headers
            "subheader_row": 1,        # 0-indexed row with Code/Image/MRP labels
        },
        finish_column_pattern=r".*",
        sku_regex=r"[A-Z]?\d{3,6}B[A-Z0-9]+H\d{2,6}",
    ),
    # New brands drop in here as they're onboarded:
    # "grohe":   SupplierManifest(brand="Grohe",   slug="grohe",   source_format="pdf", ...),
    # "geberit": SupplierManifest(brand="Geberit", slug="geberit", source_format="pdf", ...),
}


def get_manifest(brand_or_slug: str) -> SupplierManifest:
    key = (brand_or_slug or "").strip().lower()
    if key not in SUPPLIER_MANIFESTS:
        raise KeyError(f"No supplier manifest registered for {brand_or_slug!r}")
    return SUPPLIER_MANIFESTS[key]
