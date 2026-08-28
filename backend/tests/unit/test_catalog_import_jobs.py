from services.catalog_import_jobs import apply_batch_result, pending_rows


def test_pending_rows_excludes_already_successful_rows_for_idempotent_resume():
    rows = [{"row_id": "one", "status": "accepted", "import_state": "succeeded"}, {"row_id": "two", "status": "accepted", "import_state": "failed"}, {"row_id": "three", "status": "rejected"}]
    assert [r["row_id"] for r in pending_rows(rows)] == ["two"]


def test_apply_batch_result_keeps_success_and_error_per_row():
    rows = [{"row_id": "one"}, {"row_id": "two"}]
    succeeded, failed = apply_batch_result(rows, {"attempted_row_ids": ["one", "two"], "errors": [{"row_id": "two", "error": "bad image"}]})
    assert (succeeded, failed) == (1, 1)
    assert rows[0]["import_state"] == "succeeded"
    assert rows[1]["import_state"] == "failed"
    assert rows[1]["import_error"] == "bad image"
