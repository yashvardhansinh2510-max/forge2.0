"""The Business Health Score (spec §8).

One number, a band, and a direction, so ten KPIs don't have to be interpreted
before breakfast. It is a weighted OPERATIONAL SCORE, not a model: every
component is a bounded 0-100 value produced by a stated rule, and tapping the
score expands to show every component, its raw value, that rule, its weight,
and a link to the workspace that would improve it. Nothing about it is opaque.

Two rules make it honest:

  * **Weights renormalize over available components.** A business with no
    revenue target is scored out of the six signals that CAN be measured,
    rescaled to 100 — not penalised to 75 for a setting the owner never filled
    in, and never scored against an invented benchmark.
  * **No available signals means no score**, not zero. Zero reads as "the
    business is failing"; the honest answer is that it cannot be computed.
"""
from __future__ import annotations

from dataclasses import dataclass

from models import AnalyticsTargets

BAND_HEALTHY = "Healthy"
BAND_WATCH = "Watch"
BAND_AT_RISK = "At risk"


@dataclass(frozen=True)
class Component:
    key: str
    label: str
    weight: int
    rule: str
    destination: str
    needs_target: str | None = None


COMPONENTS: tuple[Component, ...] = (
    Component(
        key="collection_health",
        label="Collection health",
        weight=20,
        rule="Collected ÷ ordered revenue in the period",
        destination="/(admin)/payments",
    ),
    Component(
        key="overdue_money",
        label="Overdue money",
        weight=10,
        rule="1 − (overdue outstanding ÷ total outstanding)",
        destination="/(admin)/payments",
    ),
    Component(
        key="pipeline_health",
        label="Pipeline health",
        weight=15,
        rule="Share of open quotation value newer than the stale threshold",
        destination="/(admin)/quotations",
    ),
    Component(
        key="dispatch_health",
        label="Dispatch health",
        weight=10,
        rule="Share of ready material dispatched within the waiting threshold",
        destination="/(admin)/tiles/orders",
    ),
    Component(
        key="followup_health",
        label="Follow-up health",
        weight=10,
        rule="Share of open follow-ups not overdue",
        destination="/(admin)/followups",
    ),
    Component(
        key="revenue_attainment",
        label="Revenue attainment",
        weight=25,
        rule="Revenue ÷ monthly revenue target, capped at 100",
        destination="/(admin)/sales-data/executive",
        needs_target="monthly_revenue_target",
    ),
    Component(
        key="conversion_health",
        label="Conversion health",
        weight=10,
        rule="Conversion ÷ target conversion, capped at 100",
        destination="/(admin)/sales-data/executive",
        needs_target="target_conversion_pct",
    ),
)

_TARGET_LABELS = {
    "monthly_revenue_target": ("a revenue target", "revenue attainment"),
    "target_conversion_pct": ("a conversion target", "conversion health"),
}


def band_for(score: int) -> str:
    if score >= 85:
        return BAND_HEALTHY
    if score >= 70:
        return BAND_WATCH
    return BAND_AT_RISK


def _missing_note(missing: list[str], available: int, total: int) -> str:
    """§8's exact shape: "Based on N of 7 signals — set a revenue target to
    include revenue attainment"."""
    if not missing:
        return ""
    phrases = [_TARGET_LABELS[key] for key in missing if key in _TARGET_LABELS]
    if not phrases:
        return f"Based on {available} of {total} signals — some signals have no data in this period."
    setting = " and ".join(p[0] for p in phrases)
    included = " and ".join(p[1] for p in phrases)
    return f"Based on {available} of {total} signals — set {setting} to include {included}."


def health_score(signals: dict[str, float | None], targets: AnalyticsTargets) -> dict:
    """Weighted 0-100 score over whichever components have a value.

    `signals` maps a component key to its already-computed 0-100 value, or None
    when it cannot be measured (no denominator, or no owner-declared target).
    """
    components: list[dict] = []
    weighted = 0.0
    total_weight = 0
    available = 0

    for component in COMPONENTS:
        raw = signals.get(component.key)
        if raw is None:
            components.append({
                "key": component.key,
                "label": component.label,
                "value": None,
                "weight": component.weight,
                "rule": component.rule,
                "destination": component.destination,
                "available": False,
            })
            continue
        clamped = max(0.0, min(100.0, float(raw)))
        # Explicit fold rather than sum(): this codebase keeps money-adjacent
        # accumulation off CPython 3.12+'s compensated-summation path so values
        # stay identical to what every other surface computes.
        weighted += clamped * component.weight
        total_weight += component.weight
        available += 1
        components.append({
            "key": component.key,
            "label": component.label,
            "value": round(clamped, 1),
            "weight": component.weight,
            "rule": component.rule,
            "destination": component.destination,
            "available": True,
        })

    missing_targets = [
        c.needs_target for c in COMPONENTS
        if c.needs_target and signals.get(c.key) is None and not getattr(targets, c.needs_target, None)
    ]

    if not total_weight:
        return {
            "score": None,
            "band": None,
            "components": components,
            "available": 0,
            "total": len(COMPONENTS),
            "missing_signal_note": _missing_note(missing_targets, 0, len(COMPONENTS))
            or "Not enough data yet to compute a health score.",
        }

    score = round(weighted / total_weight)
    return {
        "score": score,
        "band": band_for(score),
        "components": components,
        "available": available,
        "total": len(COMPONENTS),
        "missing_signal_note": _missing_note(missing_targets, available, len(COMPONENTS)),
    }
