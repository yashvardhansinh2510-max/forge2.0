"""Outbox dispatch must atomically claim a pending event before processing it."""
from __future__ import annotations

import asyncio

import services.domain_outbox as domain_outbox


def test_claim_event_uses_compare_and_set_pending_filter(monkeypatch):
    captured = {}

    class _Events:
        async def find_one_and_update(self, query, update, **kwargs):
            captured.update(query=query, update=update, kwargs=kwargs)
            return {"id": "evt-1", "claim_id": "claim-1", "status": "processing"}

    class _FakeDb:
        event_outbox = _Events()

    monkeypatch.setattr(domain_outbox, "db", _FakeDb())

    claimed = asyncio.run(domain_outbox._claim_event("evt-1"))

    assert claimed["claim_id"] == "claim-1"
    assert captured["query"]["id"] == "evt-1"
    assert {"status": "pending"} in captured["query"]["$or"]
    assert captured["update"]["$set"]["status"] == "processing"
    assert captured["kwargs"]["return_document"] == domain_outbox.ReturnDocument.AFTER
