"""Regression test: a Ground Floor Tiles Selection/Quotation document saved
by an all-floors (owner/manager) user got silently tagged `floor_id:
"first-floor"` instead of `"ground-floor"`.

Root cause: `create_quotation` (routes/quotation_routes.py) stamps the new
document's `floor_id` from `floor_for_write(user)`, which reads only the
ambient `X-Floor-Id` request header / `active_floor_id`. That header is set
by the sidebar's "Tiles Selection" nav link (`useTilesNav().open()` in
`app/(admin)/_layout.tsx`), which explicitly switches the active floor to
"ground-floor" before navigating — but an owner/manager (who defaults to an
unscoped "All floors" view) who instead reaches the same screen by direct
URL, browser refresh, or a bookmarked/deep link never goes through that
switch, so the header stays unset and `floor_for_write` falls back to
"first-floor" for unrestricted users. Reproduced live against the running
app: saving a Tiles Selection doc that way produced a Mongo `quotations` row
with `floor_id: "first-floor"` even though every line item was a Qutone/
Dimore ground-floor product — invisible to any ground-floor-scoped
colleague and wrongly bucketed into first-floor reporting.

Fix: derive floor_id from the actual product data on the quotation's line
items (the real ground truth for "which floor is this") whenever every item
agrees on one floor and the user is allowed to write there — falling back to
the old `floor_for_write(user)` behavior otherwise (no items, or a
genuinely mixed set)."""
from __future__ import annotations

from models import UserPublic
from routes.quotation_routes import _floor_id_for_new_quotation


def _owner(active_floor_id: str | None = None) -> UserPublic:
    return UserPublic(
        id="u-owner", email="owner@forge.app", full_name="Owner", role="owner",
        floor_ids=[], active_floor_id=active_floor_id,
    )


def _ground_floor_staff() -> UserPublic:
    return UserPublic(
        id="u-staff", email="staff@forge.app", full_name="Staff", role="sales",
        floor_ids=["ground-floor"], active_floor_id=None,
    )


def test_owner_with_no_active_floor_takes_floor_from_single_agreeing_item():
    user = _owner(active_floor_id=None)
    assert _floor_id_for_new_quotation(user, {"ground-floor"}) == "ground-floor"


def test_owner_with_stale_first_floor_header_still_prefers_item_floor():
    # Simulates the exact reported scenario: active_floor_id happens to be
    # unset/stale, but the tiles document's own line items are unambiguous.
    user = _owner(active_floor_id=None)
    assert _floor_id_for_new_quotation(user, {"ground-floor"}) != "first-floor"


def test_empty_items_falls_back_to_floor_for_write():
    user = _owner(active_floor_id=None)
    assert _floor_id_for_new_quotation(user, set()) == "first-floor"


def test_mixed_floor_items_falls_back_to_floor_for_write():
    user = _owner(active_floor_id=None)
    assert _floor_id_for_new_quotation(user, {"ground-floor", "first-floor"}) == "first-floor"


def test_restricted_ground_floor_staff_cannot_be_overridden_to_a_floor_they_lack():
    """Defense in depth: even if a crafted payload's items somehow resolved
    to a floor the caller doesn't have access to, never stamp the document
    with a floor outside their `floor_ids`."""
    user = _ground_floor_staff()
    assert _floor_id_for_new_quotation(user, {"first-floor"}) != "first-floor"


def test_restricted_staff_own_floor_item_is_used():
    user = _ground_floor_staff()
    assert _floor_id_for_new_quotation(user, {"ground-floor"}) == "ground-floor"
