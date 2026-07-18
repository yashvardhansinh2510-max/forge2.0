from auth import floor_scope_ids
from models import UserPublic


def test_floor_scope_ids_returns_single_item_list_when_a_floor_is_active():
    user = UserPublic(email="x@forge.app", full_name="X", role="sales",
                       floor_ids=["ground-floor", "first-floor"], active_floor_id="ground-floor")
    assert floor_scope_ids(user) == ["ground-floor"]


def test_floor_scope_ids_falls_back_to_accessible_floor_ids_when_none_active():
    user = UserPublic(email="x@forge.app", full_name="X", role="owner", active_floor_id=None)
    assert floor_scope_ids(user) is None  # owners/managers: unscoped
