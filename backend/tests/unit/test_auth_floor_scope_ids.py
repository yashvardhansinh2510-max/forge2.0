from auth import floor_for_write, floor_scope_ids
from models import UserPublic


def test_floor_scope_ids_returns_single_item_list_when_a_floor_is_active():
    user = UserPublic(email="x@forge.app", full_name="X", role="sales",
                       floor_ids=["ground-floor", "first-floor"], active_floor_id="ground-floor")
    assert floor_scope_ids(user) == ["ground-floor"]


def test_floor_scope_ids_falls_back_to_floor_for_writes_single_floor_default_when_none_active():
    # Task 5: an all-floors owner/manager with no active_floor_id used to
    # make floor_scope_ids() (like floor_query()) return None -- "unscoped",
    # reading both business units at once -- while floor_for_write() picked
    # a single floor for the very same caller. Both now resolve identically
    # via auth._resolve_floor_scope(); see test_auth_floor_query_write_symmetry.py.
    user = UserPublic(email="x@forge.app", full_name="X", role="owner", active_floor_id=None)
    assert floor_scope_ids(user) == [floor_for_write(user)] == ["first-floor"]
