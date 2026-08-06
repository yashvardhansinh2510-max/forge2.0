import pytest

from services.followup_notebook import (
    NOTEBOOK_FIELDS,
    QUOTATION_FIELDS,
    NotebookValidationError,
    normalize_mobile,
    notebook_query,
    notebook_search_query,
    patch_notebook_row,
    resolve_or_create_customer,
    serialize_notebook_row,
    timeline_event_for_field,
    validate_notebook_patch,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return list(self.rows)


class _Result:
    def __init__(self, matched_count):
        self.matched_count = matched_count


class _Collection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    @staticmethod
    def _matches(row, query):
        if "$and" in query:
            return all(_Collection._matches(row, part) for part in query["$and"])
        for key, value in query.items():
            if isinstance(value, dict) and "$exists" in value:
                if (key in row) != value["$exists"]:
                    return False
            elif isinstance(value, dict) and "$in" in value:
                if row.get(key) not in value["$in"]:
                    return False
            elif row.get(key) != value:
                return False
        return True

    async def find_one(self, query, _projection=None):
        for row in self.rows:
            if self._matches(row, query):
                return dict(row)
        return None

    def find(self, query, _projection=None):
        return _Cursor([dict(row) for row in self.rows if self._matches(row, query)])

    async def insert_one(self, document):
        self.rows.append(dict(document))

    async def update_one(self, query, update):
        for index, row in enumerate(self.rows):
            if self._matches(row, query):
                self.rows[index] = {**row, **update.get("$set", {})}
                return _Result(1)
        return _Result(0)


class _Db:
    def __init__(self, *, customers=None, followups=None):
        self.customers = _Collection(customers)
        self.followups = _Collection(followups)


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


@pytest.mark.asyncio
async def test_resolve_or_create_customer_reuses_floor_scoped_mobile(monkeypatch):
    monkeypatch.setattr("services.followup_notebook.floor_query", lambda _user, base: base)
    db = _Db(customers=[{"id": "c1", "name": "Existing", "phone": "+91 9909906652", "floor_id": "second-floor"}])
    user = object()
    customer = await resolve_or_create_customer(
        db, user=user, floor_id="second-floor", name="New Name", phone="9909906652", address=None,
    )
    assert customer["id"] == "c1"
    assert len(db.customers.rows) == 1


@pytest.mark.asyncio
async def test_patch_notebook_row_updates_only_one_field_and_revision(monkeypatch):
    monkeypatch.setattr("services.followup_notebook.floor_query", lambda _user, base: base)
    db = _Db(followups=[{
        "id": "f1", "floor_id": "second-floor", "notebook_key": "second-floor:c1",
        "customer_name": "A", "customer_phone": "9909906652", "kitchen_type": "GI",
        "notebook_status": "new", "notes": "", "updated_at": "v1", "is_converted": False,
    }])
    row = await patch_notebook_row(
        db, user=object(), floor_id="second-floor", row_id="f1",
        patch={"notes": "Call tomorrow"}, expected_updated_at="v1",
    )
    assert row["notes"] == "Call tomorrow"
    assert db.followups.rows[0]["customer_name"] == "A"
    assert db.followups.rows[0]["updated_at"] != "v1"
