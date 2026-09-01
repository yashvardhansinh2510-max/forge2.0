from __future__ import annotations

import asyncio

from routes import tile_orders as router_module


class _Result:
    matched_count = 1


class _Collection:
    def __init__(self):
        self.calls = []

    async def update_one(self, query, update, session=None, upsert=False):
        self.calls.append((query, update, session, upsert))
        return _Result()


class _Db:
    def __init__(self):
        self.quotations = _Collection()
        self.payments = _Collection()
        self.customer_orders = _Collection()


def test_labor_cost_creates_a_visible_idempotent_pending_payment(monkeypatch):
    fake_db = _Db()
    monkeypatch.setattr(router_module, "db", fake_db)

    po = {
        "quotation_id": "q-1", "quotation_number": "FQ-0001", "customer_order_id": "co-1",
        "customer_id": "cust-1", "customer_name": "Asha", "floor_id": "ground-floor",
    }
    dispatch = {"id": "dispatch-1", "dispatch_number": "DSP-0001", "created_by": "user-1", "created_by_name": "Warehouse"}
    asyncio.run(router_module._apply_dispatch_labor_cost(po, dispatch, 3000.0, session=None))

    quote_query, quote_update, _, _ = fake_db.quotations.calls[0]
    assert quote_query == {"id": "q-1", "floor_id": "ground-floor"}
    assert quote_update["$inc"] == {"grand_total": 3000.0, "labor_cost_total": 3000.0}

    payment_query, payment_update, _, payment_upsert = fake_db.payments.calls[0]
    assert payment_query == {"automation_key": "dispatch:dispatch-1:labor_cost"}
    assert payment_upsert is True
    payment = payment_update["$setOnInsert"]
    assert payment["amount"] == 3000.0
    assert payment["status"] == "pending"
    assert payment["label"] == "labor cost"
    assert payment["note"] == "₹3,000 labor cost added via dispatch DSP-0001"
    assert "idempotency_key" not in payment

    customer_query, customer_update, _, _ = fake_db.customer_orders.calls[0]
    assert customer_query == {"id": "co-1", "floor_id": "ground-floor"}
    assert customer_update["$inc"] == {"total_value": 3000.0}
