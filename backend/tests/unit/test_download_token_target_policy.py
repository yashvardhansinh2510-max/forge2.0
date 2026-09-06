"""Regression coverage for the browser-download token authorization boundary."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from routes.misc_routes import _download_target_path


@pytest.mark.parametrize("target", [
    "/api/purchases/export.xlsx?stage=received",
    "/api/payments/history/export?fmt=xlsx",
    "/api/followups/export",
    "/api/tile-orders/history/export?date_from=2026-09-01",
    "/api/tile-orders/chalans/chalan-1/pdf",
])
def test_download_token_targets_are_limited_to_known_get_file_routes(target):
    assert _download_target_path(target).startswith("/api/")


@pytest.mark.parametrize("target", [
    "/api/payments/orders",
    "/api/auth/users",
    "/api/purchases/export.xlsx?dl=attacker-token",
    "https://attacker.example/api/purchases/export.xlsx",
    "/api/tile-orders/chalans/chalan-1/pdf#fragment",
])
def test_download_token_rejects_arbitrary_or_pre_tokenized_targets(target):
    with pytest.raises(HTTPException) as exc:
        _download_target_path(target)
    assert exc.value.status_code == 400
