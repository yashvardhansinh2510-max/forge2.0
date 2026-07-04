"""Validation + Certification engine.
Every import produces a numeric certification score across every axis.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Iterable

from .base import ALLOWED_CATEGORIES, MISSING, ProductRow


@dataclass
class CertificationReport:
    extraction_accuracy: float = 0.0
    sku_accuracy: float = 0.0
    price_accuracy: float = 0.0
    category_accuracy: float = 0.0
    variant_accuracy: float = 0.0
    image_accuracy: float = 0.0
    duplicate_score: float = 0.0
    missing_data_score: float = 0.0
    total_products: int = 0
    products_ready: int = 0
    products_needing_review: int = 0
    families_detected: int = 0
    duplicates_sku: int = 0
    duplicates_family: int = 0
    missing_images: int = 0
    missing_mrp: int = 0
    missing_categories: int = 0
    variant_conflicts: list[str] = field(default_factory=list)
    category_conflicts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    overall_score: float = 0.0
    production_ready: bool = False

    def to_public(self) -> dict:
        return asdict(self)


def _rate(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 1) if denominator else 0.0


def validate(rows: list[ProductRow]) -> tuple[list[ProductRow], CertificationReport]:
    report = CertificationReport(total_products=len(rows))

    # 1) SKU dedupe
    sku_seen: dict[str, list[ProductRow]] = defaultdict(list)
    for r in rows:
        if r.sku and r.sku != MISSING:
            sku_seen[r.sku].append(r)

    unique_skus = len(sku_seen)
    dupes = 0
    for sku, group in sku_seen.items():
        if len(group) > 1:
            dupes += len(group) - 1
            for r in group[1:]:
                r.issues.append(f"Duplicate SKU '{sku}' — will be skipped on import")
                r.status = "rejected"
    report.duplicates_sku = dupes

    # 2) Family detection: rows sharing family_key are variants
    families: dict[str, list[ProductRow]] = defaultdict(list)
    for r in rows:
        if r.family_key and r.family_key != MISSING:
            families[r.family_key].append(r)
    report.families_detected = len(families)

    # 3) Category conflicts within a family
    for fk, members in families.items():
        cats = {m.category for m in members if m.category and m.category != MISSING}
        if len(cats) > 1:
            report.category_conflicts.append(f"Family '{fk}' spans multiple categories: {sorted(cats)}")
            for m in members:
                m.issues.append("Family assigned to multiple categories — please review")

    # 4) Variant conflicts: same family + same variant label = suspicious
    for fk, members in families.items():
        seen_variant: dict[str, list[ProductRow]] = defaultdict(list)
        for m in members:
            if m.variant and m.variant != MISSING:
                seen_variant[m.variant].append(m)
        for v, dupset in seen_variant.items():
            if len(dupset) > 1:
                report.variant_conflicts.append(f"Family '{fk}' has {len(dupset)} rows for variant '{v}'")

    # 5) Missing data + category validity
    for r in rows:
        if not r.images:
            report.missing_images += 1
            r.issues.append("No image mapped")
        if r.mrp in (MISSING, None):
            report.missing_mrp += 1
        if r.category in (MISSING, None):
            report.missing_categories += 1
        elif r.category not in ALLOWED_CATEGORIES:
            report.warnings.append(f"Unknown category '{r.category}' on SKU {r.sku}")

    # 6) Certification scores
    n = report.total_products or 1
    report.extraction_accuracy = _rate(n - report.missing_categories, n)
    report.sku_accuracy = _rate(unique_skus, len([r for r in rows if r.sku and r.sku != MISSING]) or 1)
    report.price_accuracy = _rate(n - report.missing_mrp, n)
    report.category_accuracy = _rate(n - report.missing_categories, n)
    report.variant_accuracy = _rate(n - len(report.variant_conflicts), n)
    report.image_accuracy = _rate(n - report.missing_images, n)
    report.duplicate_score = _rate(n - report.duplicates_sku, n)
    ready = sum(1 for r in rows if (
        r.status != "rejected"
        and r.sku != MISSING
        and r.mrp != MISSING
        and r.category != MISSING
        and r.images
    ))
    report.products_ready = ready
    report.products_needing_review = n - ready
    report.missing_data_score = _rate(ready, n)

    scores = [
        report.extraction_accuracy, report.sku_accuracy, report.price_accuracy,
        report.category_accuracy, report.variant_accuracy, report.image_accuracy,
        report.duplicate_score, report.missing_data_score,
    ]
    report.overall_score = round(sum(scores) / len(scores), 1)
    report.production_ready = report.overall_score >= 90 and report.duplicates_sku == 0

    return rows, report
