from __future__ import annotations

import asyncio

from routes import tile_orders as router_module


class _Result:
    matched_count = 1


class _Collection:
    def __init__(self):
        self.calls = []

    async def update_one(self, query, update, session=None):
        self.calls.append((query, update, session))
        return _Result()


class _Db:
    def __init__(self):
        self.quotations = _Collection()
        self.payments = _Collection()
        self.customer_orders = _Collection()


def test_labor_cost_increases_the_collection_balance_and_pending_payment(monkeypatch):
    fake_db = _Db()
    monkeypatch.setattr(router_module, "db", fake_db)

    po = {"quotation_id": "q-1", "customer_order_id": "co-1", "floor_id": "ground-floor"}
    asyncio.run(router_module._apply_dispatch_labor_cost(po, 450.0, session=None))

    quote_query, quote_update, _ = fake_db.quotations.calls[0]
    assert quote_query == {"id": "q-1", "floor_id": "ground-floor"}
    assert quote_update["$inc"] == {"grand_total": 450.0, "labor_cost_total": 450.0}

    payment_query, payment_update, _ = fake_db.payments.calls[0]
    assert payment_query == {"quotation_id": "q-1", "status": "pending"}
    assert payment_update["$inc"] == {"amount": 450.0}

    customer_query, customer_update, _ = fake_db.customer_orders.calls[0]
    assert customer_query == {"id": "co-1", "floor_id": "ground-floor"}
    assert customer_update["$inc"] == {"total_value": 450.0}
