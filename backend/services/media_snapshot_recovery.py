"""Deterministic planning helpers for restoring media from a known-good snapshot."""
from __future__ import annotations

from typing import Any


MEDIA_POINTER_FIELDS = (
    "bucket", "storage_key", "public_url", "width", "height", "quality",
    "sha1", "mime", "size_bytes",
)


def _ratio_is(value: dict[str, Any], target: float) -> bool:
    width, height = value.get("width"), value.get("height")
    return bool(width and height and abs((width / height) - target) < 0.02)


def plan_snapshot_media_restore(current_rows: list[dict[str, Any]], snapshot_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only exact ID-matched pointer changes; never invent a replacement.

    Rows created after the snapshot and snapshot rows whose source pointer is
    unchanged are intentionally excluded.  The caller must still verify the
    snapshot object bytes before applying a plan item.
    """
    snapshot_by_id = {row.get("id"): row for row in snapshot_rows if row.get("id")}
    plan: list[dict[str, Any]] = []
    for current in current_rows:
        media_id = current.get("id")
        snapshot = snapshot_by_id.get(media_id)
        if not snapshot or not snapshot.get("bucket") or not snapshot.get("storage_key"):
            continue
        before = {field: current.get(field) for field in MEDIA_POINTER_FIELDS}
        after = {field: snapshot.get(field) for field in MEDIA_POINTER_FIELDS}
        # The forced backfill created a near-16:10 derivative.  Do not roll
        # back ordinary later edits merely because their pointer differs.
        if before == after or not _ratio_is(current, 1.6) or _ratio_is(snapshot, 1.6):
            continue
        plan.append({"media_id": media_id, "before": before, "after": after})
    return plan
