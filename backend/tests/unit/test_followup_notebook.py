import pytest

from services.followup_notebook import (
    NOTEBOOK_FIELDS,
    QUOTATION_FIELDS,
    NotebookValidationError,
    normalize_mobile,
    notebook_search_query,
    serialize_notebook_row,
    timeline_event_for_field,
    validate_notebook_patch,
)


def test_normalize_mobile_accepts_indian_formatting():
    assert normalize_mobile("+91 99099-06652") == "9909906652"
    assert normalize_mobile("9909906652") == "9909906652"


def test_notebook_contract_rejects_unlisted_fields():
    with pytest.raises(NotebookValidationError, match="unsupported field"):
        validate_notebook_patch({"project_stage": "production"}, converted=False, current={})


def test_notebook_contract_requires_identity_and_kitchen_type():
    with pytest.raises(NotebookValidationError, match="customer_phone"):
        validate_notebook_patch(
            {"customer_name": "A", "kitchen_type": "GI"}, converted=False, current={}, creating=True,
        )
    with pytest.raises(NotebookValidationError, match="kitchen_type"):
        validate_notebook_patch(
            {"customer_name": "A", "customer_phone": "9909906652", "kitchen_type": "Wood"},
            converted=False, current={}, creating=True,
        )


def test_quotation_fields_are_rejected_before_conversion():
    with pytest.raises(NotebookValidationError, match="require conversion"):
        validate_notebook_patch({"quotation_price": 100}, converted=False, current={})
    assert QUOTATION_FIELDS == {"quotation_price", "estimated_value", "quotation_date"}


def test_lost_requires_notes():
    with pytest.raises(NotebookValidationError, match="Notes"):
        validate_notebook_patch({"notebook_status": "lost"}, converted=False, current={"notes": ""})


def test_won_followup_is_locked_but_quotation_fields_can_change():
    current = {"notebook_status": "won", "is_converted": True}
    with pytest.raises(NotebookValidationError, match="locked"):
        validate_notebook_patch({"notes": "change"}, converted=True, current=current)
    assert validate_notebook_patch({"quotation_price": 100}, converted=True, current=current) == {"quotation_price": 100}


def test_projection_hides_shared_followup_metadata_and_adds_quote_fields_only_after_conversion():
    source = {
        "id": "1", "customer_name": "A", "customer_phone": "9909906652", "notebook_status": "new",
        "priority_score": 90, "reason": "internal", "is_converted": False,
    }
    row = serialize_notebook_row(source)
    assert row["status"] == "new"
    assert "priority_score" not in row and "reason" not in row
    assert "quotation_price" not in row
    converted = serialize_notebook_row({**source, "is_converted": True, "quotation_price": 100})
    assert converted["quotation_price"] == 100


def test_search_query_contains_only_notebook_text_fields():
    query = notebook_search_query("architect")
    fields = {next(iter(item)) for item in query["$or"]}
    assert fields == {
        "customer_name", "customer_phone", "address", "architect_interior_designer", "referred_by", "notes",
    }
    assert "quotation_price" not in fields


def test_timeline_event_names_are_stable():
    assert timeline_event_for_field("notebook_status", "new", "won")[0] == "project_followup.status_changed"
    assert timeline_event_for_field("quotation_price", None, 100)[0] == "project_followup.quotation_updated"

