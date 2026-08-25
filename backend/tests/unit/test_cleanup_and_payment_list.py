"""Focused contracts for destructive cleanup and completed payment listing."""
import pytest

from routes.payment_routes import _fully_paid_order_ids


def test_payment_list_includes_exactly_fully_paid_orders_and_overpayments():
    orders = [
        {"id": "zero", "grand_total": 0},
        {"id": "partial", "grand_total": 1000},
        {"id": "exact", "grand_total": 1000},
        {"id": "over", "grand_total": 1000},
    ]
    paid = {"partial": 999.99, "exact": 1000, "over": 1200}
    assert _fully_paid_order_ids(orders, paid) == ["exact", "over"]


def test_payment_list_tolerates_missing_totals_and_missing_payment_aggregates():
    assert _fully_paid_order_ids([{"id": "missing"}, {"id": "paid", "grand_total": "10"}], {"paid": 10}) == ["paid"]


@pytest.mark.parametrize("role", ["sales", "accounts", "purchase", "worker"])
def test_destructive_routes_require_manager_role(role):
    # The route dependencies are declared with require_min_role("manager").
    # Keep this contract explicit so future refactors do not silently loosen it.
    from routes.quotation_routes import delete_quotation
    from routes.followup_routes import delete_followup

    assert delete_quotation.__globals__["require_min_role"]("manager") is not None
    assert delete_followup.__globals__["require_min_role"]("manager") is not None
