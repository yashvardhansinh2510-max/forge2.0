"""Pure shaping for the Collections workspace — the payments-focused view of
Outstanding. Reuses metrics.outstanding_pipeline's own figures; this module
only buckets and sorts what the gather layer already fetched, per spec
("no new definition")."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from services.analytics.attention import age_days

AGE_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("0-30", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("90+", 91, None),
)


def _bucket_for(age: int) -> str:
    for label, low, high in AGE_BUCKETS:
        if age >= low and (high is None or age <= high):
            return label
    return AGE_BUCKETS[-1][0]


@dataclass(frozen=True)
class CollectionRow:
    customer_id: str
    customer_name: str
    ordered_at: str | None
    grand_total: float
    collected: float
    outstanding: float
    age_days: int | None
    age_bucket: str | None


def collections_by_customer(rows: list[dict], now: datetime) -> list[CollectionRow]:
    result: list[CollectionRow] = []
    for row in rows:
        outstanding = round(float(row.get("grand_total") or 0) - float(row.get("collected") or 0), 2)
        if outstanding <= 0:
            continue
        age = age_days(row.get("ordered_at"), now)
        result.append(CollectionRow(
            customer_id=row["customer_id"], customer_name=row.get("customer_name") or "Unknown",
            ordered_at=row.get("ordered_at"), grand_total=float(row.get("grand_total") or 0),
            collected=float(row.get("collected") or 0), outstanding=outstanding,
            age_days=age, age_bucket=_bucket_for(age) if age is not None else None,
        ))
    return sorted(result, key=lambda r: -r.outstanding)


def collections_by_age(rows: list[dict], now: datetime) -> dict[str, dict]:
    buckets = {label: {"count": 0, "outstanding": 0.0} for label, _, _ in AGE_BUCKETS}
    for row in collections_by_customer(rows, now):
        if row.age_bucket is None:
            continue
        buckets[row.age_bucket]["count"] += 1
        buckets[row.age_bucket]["outstanding"] = round(buckets[row.age_bucket]["outstanding"] + row.outstanding, 2)
    return buckets
