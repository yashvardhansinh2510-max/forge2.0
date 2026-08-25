"""Validation + Certification engine.
Every import produces a numeric certification score across every axis.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field, asdict

from .base import MISSING, ProductRow


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
    cross_family_skus: int = 0
    duplicates_family: int = 0
    missing_images: int = 0
    missing_mrp: int = 0
    missing_categories: int = 0
    image_quality: dict = field(default_factory=dict)   # ImageQualityReport dump
    excellent_images: int = 0
    good_images: int = 0
    acceptable_images: int = 0
    poor_images: int = 0
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

    # 1) SKU dedupe with cross-family whitelist.
    #    A "true duplicate" is the same SKU appearing more than once *inside the
    #    same family_key* (real data-entry error → reject).
    #    A "cross-family listing" is the same SKU appearing across *different*
    #    family_keys, which is legitimate for brands like Geberit and Vitra
    #    where a single flush plate or trim SKU is bundled into several product
    #    families. Those rows stay accepted; the importer's `find_one({sku})`
    #    path naturally merges them onto the canonical product.
    sku_seen: dict[str, list[ProductRow]] = defaultdict(list)
    for r in rows:
        if r.sku and r.sku != MISSING:
            sku_seen[r.sku].append(r)

    true_dupes = 0
    cross_dupes = 0
    for sku, group in sku_seen.items():
        if len(group) <= 1:
            continue
        canonical = group[0]
        canonical_family = canonical.family_key if canonical.family_key and canonical.family_key != MISSING else None
        for r in group[1:]:
            r_family = r.family_key if r.family_key and r.family_key != MISSING else None
            same_family = (canonical_family is not None and r_family == canonical_family)
            if same_family:
                # True duplicate — same SKU under the same family: reject the copy.
                true_dupes += 1
                r.issues.append(f"Duplicate SKU '{sku}' within same family — will be skipped on import")
                r.status = "rejected"
            else:
                # Legitimate cross-family listing — merge on import, keep for review.
                cross_dupes += 1
                r.issues.append(
                    f"SKU '{sku}' also listed under another family — will merge onto the canonical product on import"
                )
                # Preserve current status (accepted / pending); do NOT reject.
    report.duplicates_sku = true_dupes
    report.cross_family_skus = cross_dupes
    if cross_dupes:
        report.warnings.append(
            f"{cross_dupes} cross-family SKU listing(s) detected — treated as legitimate re-listings, not errors"
        )

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

    # 5) Missing data + category validity + image quality tally
    edges: list[int] = []
    q_counts = {"excellent": 0, "good": 0, "acceptable": 0, "poor": 0}
    by_src: dict[str, int] = {}
    for r in rows:
        if not r.images:
            report.missing_images += 1
            r.issues.append("No image mapped")
        else:
            for meta in (r.image_meta or []):
                q = str(meta.get("quality") or "poor")
                if q in q_counts:
                    q_counts[q] += 1
                src = str(meta.get("source_format") or "unknown")
                by_src[src] = by_src.get(src, 0) + 1
                w, h = int(meta.get("width", 0)), int(meta.get("height", 0))
                if max(w, h) > 0:
                    edges.append(max(w, h))
        if r.mrp in (MISSING, None):
            report.missing_mrp += 1
        if r.category in (MISSING, None):
            report.missing_categories += 1

    report.excellent_images = q_counts["excellent"]
    report.good_images = q_counts["good"]
    report.acceptable_images = q_counts["acceptable"]
    report.poor_images = q_counts["poor"]
    total_imgs = sum(q_counts.values())
    if total_imgs > 0:
        edges.sort()
        median_edge = edges[len(edges) // 2] if edges else 0
        min_edge = edges[0] if edges else 0
        max_edge = edges[-1] if edges else 0
        premium_pct = (q_counts["excellent"] + q_counts["good"]) * 100 // total_imgs
        if premium_pct >= 80:
            verdict = f"Supplier ships production-quality artwork ({premium_pct}% excellent/good)"
        elif premium_pct >= 50:
            verdict = f"Mixed quality — {premium_pct}% premium, remainder is thumbnail-grade"
        else:
            verdict = (
                f"Supplier file only contains thumbnail-grade artwork "
                f"({premium_pct}% premium; median longest edge = {median_edge}px). "
                "Recommend sourcing official product photography separately."
            )
        report.image_quality = {
            "total": total_imgs,
            "excellent": q_counts["excellent"], "good": q_counts["good"],
            "acceptable": q_counts["acceptable"], "poor": q_counts["poor"],
            "by_source": by_src,
            "min_edge_px": min_edge, "median_edge_px": median_edge, "max_edge_px": max_edge,
            "premium_pct": premium_pct,
            "verdict": verdict,
        }
    else:
        report.image_quality = {
            "total": 0, "excellent": 0, "good": 0, "acceptable": 0, "poor": 0,
            "by_source": {}, "min_edge_px": 0, "median_edge_px": 0, "max_edge_px": 0,
            "premium_pct": 0, "verdict": "No images extracted from supplier file",
        }

    # 6) Certification scores
    n = report.total_products or 1
    total_with_sku = len([r for r in rows if r.sku and r.sku != MISSING])
    report.extraction_accuracy = _rate(n - report.missing_categories, n)
    # sku_accuracy: count only *true* duplicates against total SKUs. Cross-family
    # listings are legitimate and don't penalise the score.
    report.sku_accuracy = _rate(total_with_sku - report.duplicates_sku, total_with_sku or 1)
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
    # production_ready: only *true* SKU duplicates gate certification.
    report.production_ready = (
        report.overall_score >= 95
        and report.duplicates_sku <= max(3, int(0.02 * report.total_products))
    )

    return rows, report
