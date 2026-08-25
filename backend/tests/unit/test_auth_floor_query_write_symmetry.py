"""Task 5: `floor_query()` / `floor_for_write()` asymmetry.

An all-floors caller (owner/manager) with no `active_floor_id` set is what a
direct API call with no `X-Floor-Id` header looks like. The product itself
can never produce this state in normal use -- the shell pins a concrete
floor immediately after login (frontend/src/state/auth.tsx:76-89,
frontend/src/hooks/use-floor-access.ts:39-59) -- but it is reachable at the
HTTP boundary, and it used to be handled inconsistently:

  * `floor_query()` returned an *unrestricted* Mongo filter (no floor_id
    clause at all) -- reads across BOTH business units in one call.
  * `floor_for_write()` for the exact same caller/request picked a single
    floor (Sanitary / "first-floor").

So the same user, on the same request, could read everything but write to
one floor. This test pins the fixed behavior: both now resolve to the same
single-floor scope, using floor_for_write's existing (already-tested, see
test_quotation_floor_id_from_items.py) single-floor default rather than
inventing a new fallback -- see task-5-report.md for why "reads as narrow as
writes" was chosen over "writes as broad as reads" or a hard error.
"""
from __future__ import annotations

from auth import floor_for_write, floor_query, floor_scope_ids
from models import UserPublic


def _owner_all_floors() -> UserPublic:
    return UserPublic(
        id="u-owner", email="owner@forge.app", full_name="Owner", role="owner",
        floor_ids=[], active_floor_id=None,
    )


def test_floor_query_and_floor_for_write_agree_on_scope_for_an_ambiguous_all_floors_caller():
    user = _owner_all_floors()

    write_floor = floor_for_write(user)
    read_query = floor_query(user)

    assert read_query == {"floor_id": {"$in": [write_floor]}}


def test_floor_scope_ids_agrees_with_floor_for_write_too():
    user = _owner_all_floors()

    write_floor = floor_for_write(user)
    assert floor_scope_ids(user) == [write_floor]


def test_floor_query_no_longer_returns_an_unrestricted_filter_for_that_caller():
    user = _owner_all_floors()
    base = {"status": "won"}
    query = floor_query(user, base)

    # Pre-fix, floor_query(user, base) for this caller returned `base`
    # completely unfiltered -- no floor_id clause anywhere in the composed
    # query, meaning the response could mix both business units' records.
    assert query != base
    assert "floor_id" in str(query)
