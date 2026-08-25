"""Quotation PDF rendering must never block the async API event loop."""
from __future__ import annotations

import asyncio

import routes.quotation_routes as quotation_routes


def test_render_pdf_dispatches_builder_to_threadpool(monkeypatch):
    call = {}

    def builder(document, customer, branding):
        return b"%PDF-test"

    async def fake_run_in_threadpool(fn, *args):
        call["fn"] = fn
        call["args"] = args
        return fn(*args)

    monkeypatch.setattr(quotation_routes, "run_in_threadpool", fake_run_in_threadpool)
    document = {"number": "FQ-1"}
    customer = {"name": "Mobile Customer"}
    branding = {"footer_company_name": "BuildCon House"}

    result = asyncio.run(quotation_routes._render_pdf(builder, document, customer, branding))

    assert result == b"%PDF-test"
    assert call == {"fn": builder, "args": (document, customer, branding)}
