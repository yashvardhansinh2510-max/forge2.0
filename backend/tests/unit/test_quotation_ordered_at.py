"""Revenue is dated by ordered_at, so the stamp must be write-once. If a
later edit could move it, editing an old order would move its revenue into
the current reporting period."""
from __future__ import annotations

from routes.quotation_routes import _ordered_at_patch


def test_stamps_on_transition_to_ordered():
    patch = _ordered_at_patch({"status": "approved"}, "ordered")
    assert "ordered_at" in patch and patch["ordered_at"]


def test_never_overwrites_an_existing_stamp():
    doc = {"status": "ordered", "ordered_at": "2026-07-01T00:00:00+00:00"}
    assert _ordered_at_patch(doc, "ordered") == {}


def test_no_stamp_for_any_other_status():
    for status in ("draft", "sent", "approved", "rejected", "lost"):
        assert _ordered_at_patch({"status": "draft"}, status) == {}


def test_stamp_is_iso_utc():
    stamped = _ordered_at_patch({}, "ordered")["ordered_at"]
    assert "T" in stamped and ("+00:00" in stamped or stamped.endswith("Z"))


def test_re_ordering_after_a_cancellation_keeps_the_original_date():
    """An order that went ordered -> lost -> ordered again still dates to the
    first confirmation: the stamp is keyed on the stored value, not on the
    status it is transitioning from."""
    doc = {"status": "lost", "ordered_at": "2026-06-02T10:00:00+00:00"}
    assert _ordered_at_patch(doc, "ordered") == {}


def test_blank_stored_stamp_is_treated_as_missing():
    """The 0012 backfill skips documents with no usable timestamp, so a doc
    can legitimately carry "" — the next real confirmation must fill it."""
    assert "ordered_at" in _ordered_at_patch({"ordered_at": ""}, "ordered")


def test_every_quotation_born_ordered_also_sets_ordered_at():
    """Structural guard. The status transitions are not the only way a
    quotation becomes "ordered": the transfer flows construct one that is
    born ordered (purchases_tracker's auto-quotation, transfer_workflow's
    destination quote). A born-ordered row with no ordered_at is invisible to
    every revenue report, so any future constructor must stamp it too."""
    import ast
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]
    offenders = []
    for path in backend.rglob("*.py"):
        rel = path.relative_to(backend).as_posix()
        if rel.startswith((".venv/", "tests/", "migrations/")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Quotation"):
                continue
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            status = kwargs.get("status")
            born_ordered = isinstance(status, ast.Constant) and status.value == "ordered"
            if born_ordered and "ordered_at" not in kwargs:
                offenders.append(f"{rel}:{node.lineno}")
    assert offenders == [], f"Quotation(status='ordered') without ordered_at at: {offenders}"
